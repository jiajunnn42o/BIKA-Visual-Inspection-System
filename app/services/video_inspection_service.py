"""Offline on-entry 09b video inspection with x-only Safe Zone triggering.

A fast YOLO observation on every exported frame detects new arrivals and
immediately schedules a validated 09b segmentation/classification on that
source frame. Optical flow moves masks between 09b keyframes; the output is
an annotated MP4 without a Safe Zone rectangle. This is not real-time CUDA
inference and not a guarantee of catching objects missed by YOLO/SAM2.
"""
from __future__ import annotations

import base64
import math
import json
import os
import shutil
import subprocess
import tempfile
from collections import defaultdict
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.services.inspection_pipeline_service import (
    InspectionCancelled,
    InspectionPipelineError,
    inspect_image_bytes_with_progress,
)
from app.services.video_entry_trigger import VideoEntryTrigger, detect_video_frame_boxes
from app.services.mask_overlay_service import render_mask_overlay_webp
from app.services.video_mask_tracking import VideoMaskTracker
from app.services.video_safe_zone import DEFAULT_ZONE, validate_zone

MAX_DURATION_SECONDS = 120.0
MAX_PREVIEW_FRAMES = 12  # cap returned base64 preview images, not AI inspection frames
PERIODIC_REFRESH_SECONDS = 3.0  # additional 09b keyframes for drift correction
JPEG_QUALITY = 90
PREVIEW_SIZE = (960, 540)
OUTPUT_MAX_WIDTH = 1280
OUTPUT_MAX_HEIGHT = 720
OUTPUT_MAX_FPS = 24.0


def _check_cancel(cancel_check):
    if cancel_check and cancel_check():
        raise InspectionCancelled("Video inspection cancelled by user.")


def _preview_url(webp: bytes) -> str:
    with Image.open(BytesIO(webp)) as original:
        image = original.convert("RGB")
        image.thumbnail(PREVIEW_SIZE, Image.Resampling.LANCZOS)
        stream = BytesIO()
        image.save(stream, format="WEBP", quality=78, method=4)
    return "data:image/webp;base64," + base64.b64encode(stream.getvalue()).decode("ascii")


def _ffmpeg_path():
    binary = shutil.which("ffmpeg")
    if binary:
        return binary
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError):
        return None


def _resize_image(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    if frame.shape[1] == width and frame.shape[0] == height:
        return frame.copy()
    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)


def _make_annotated_video(
    input_path: Path, output_path: Path, *, fps: float, frame_count: int,
    width: int, height: int, samples: list[dict], safe_zone=DEFAULT_ZONE,
    progress_callback=None, cancel_check=None,
) -> dict:
    """Write full-length coloured video and tracking sidecar using optical flow.

    The 09b pipeline only analyses keyframes. Optical flow propagates their
    masks to adjacent frames; it is not an AI classification on every frame.
    """
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        raise InspectionPipelineError(
            "MP4 export requires FFmpeg (H.264). Install FFmpeg and add it to PATH, "
            "or install imageio-ffmpeg in the active Python environment."
        )
    scale = min(1.0, OUTPUT_MAX_WIDTH / width, OUTPUT_MAX_HEIGHT / height)
    out_width = max(2, int(width * scale) // 2 * 2)
    out_height = max(2, int(height * scale) // 2 * 2)
    out_fps = min(fps, OUTPUT_MAX_FPS)
    total_output_frames = max(1, int(math.ceil((frame_count / fps) * out_fps)))
    # 09b polygons are in SOURCE-frame coordinates. The encoded movie can
    # be resized to 720p, so map geometry before painting or hit testing.
    geometry_x = out_width / width
    geometry_y = out_height / height
    sample_at = {}
    for sample in samples:
        objects = []
        for obj in sample.get("objects") or []:
            scaled = dict(obj)
            scaled["polygons"] = [
                [[float(point[0]) * geometry_x, float(point[1]) * geometry_y]
                 for point in polygon]
                for polygon in obj.get("polygons") or []
            ]
            bbox = obj.get("bbox") or {}
            scaled["bbox"] = {key: float(value) * (geometry_x if key in ("x0", "x1") else geometry_y)
                              for key, value in bbox.items()}
            objects.append(scaled)
        out_index = sample.get("output_frame_index")
        if out_index is None:
            out_index = round(sample["time_seconds"] * out_fps)
        sample_at[min(total_output_frames - 1, max(0, int(out_index)))] = {
            "objects": objects,
        }
    capture = cv2.VideoCapture(str(input_path))
    if not capture.isOpened():
        raise InspectionPipelineError("Could not reopen video for MP4 export.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".partial.mp4")
    timeline_path = output_path.with_suffix(".tracks.json")
    temporary_json = output_path.with_suffix(".tracks.partial.json")
    process = None
    tracker = VideoMaskTracker(out_width, out_height, safe_zone=safe_zone)
    timeline = []
    try:
        command = [
            ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{out_width}x{out_height}", "-r", f"{out_fps:.6f}",
            "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-f", "mp4", str(temporary),
        ]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        current_src_frame = -1
        source_frame = None
        for out_index in range(total_output_frames):
            _check_cancel(cancel_check)
            desired_index = min(frame_count - 1, int(out_index * fps / out_fps))
            while current_src_frame < desired_index:
                ok, source_frame = capture.read()
                if not ok:
                    raise InspectionPipelineError("Could not decode the complete video while exporting MP4.")
                current_src_frame += 1
            frame = _resize_image(source_frame, out_width, out_height)
            tracker.update(frame, sample_at.get(out_index))
            frame, clickable = tracker.paint_and_metadata(frame)
            timeline.append([out_index, clickable])
            try:
                process.stdin.write(frame.tobytes())
            except BrokenPipeError as exc:
                details = (process.stderr.read() or b"").decode("utf-8", "replace")[-600:]
                raise InspectionPipelineError(f"FFmpeg could not encode H.264 MP4: {details}") from exc
            if progress_callback and (out_index % max(1, int(out_fps * 2)) == 0):
                progress_callback(86 + round(out_index / total_output_frames * 13),
                                  f"Tracking masks / encoding MP4: {out_index + 1}/{total_output_frames}")
        process.stdin.close()
        details = (process.stderr.read() or b"").decode("utf-8", "replace")[-600:]
        code = process.wait(timeout=40)
        if code != 0 or not temporary.exists() or temporary.stat().st_size == 0:
            raise InspectionPipelineError(f"H.264 video export failed: {details or 'FFmpeg returned an error.'}")
        _check_cancel(cancel_check)
        with temporary_json.open("w", encoding="utf-8") as fp:
            json.dump({"fps": out_fps, "width": out_width, "height": out_height,
                       "method": "yolo_per_frame_on_entry_09b_flow_x_zone",
                       "safe_zone": list(tracker.safe_zone),
                       "activations": tracker.activations,
                       "tracks": tracker.track_history, "frames": timeline},
                      fp, ensure_ascii=False, separators=(",", ":"))
        os.replace(temporary, output_path)
        os.replace(temporary_json, timeline_path)
        return {
            "available": True,
            "format": "MP4 (H.264)",
            "width": out_width,
            "height": out_height,
            "fps": round(out_fps, 2),
            "size_bytes": output_path.stat().st_size,
            "note": "YOLO checks every output frame. New entries trigger full 09b inspection on the arrival frame. The complete biscuit mask is visible (no top/bottom clipping), and the Safe Zone boundary is not drawn. Optical flow estimates intermediate masks; objects missed by the detector or segmentation may still be absent.",
            "audio_preserved": False,
            "tracked_ids": len(tracker.track_history),
            "safe_zone": list(tracker.safe_zone),
            "zone_triggered_tracks": len(tracker.activations),
            "tracking_method": "per_frame_yolo_on_entry_09b_with_optical_flow",
        }
    finally:
        capture.release()
        if process is not None and process.poll() is None:
            process.kill()
            try:
                process.communicate(timeout=4)
            except (OSError, subprocess.TimeoutExpired):
                pass
        temporary.unlink(missing_ok=True)
        temporary_json.unlink(missing_ok=True)


def inspect_video_bytes_with_progress(
    video_bytes: bytes, *, filename: str, output_path: str | Path | None = None,
    progress_callback=None, cancel_check=None, safe_zone=DEFAULT_ZONE,
) -> dict:
    safe_zone = validate_zone(safe_zone)
    if not video_bytes:
        raise InspectionPipelineError("Video file is empty.")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".mp4", ".mov", ".avi", ".webm"}:
        raise InspectionPipelineError("Supported videos: MP4, MOV, AVI, WEBM.")
    if output_path is None:
        raise InspectionPipelineError("Annotated MP4 output path is required.")
    output_path = Path(output_path)
    path = None
    cap = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(video_bytes)
            path = Path(tmp.name)
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise InspectionPipelineError("Video decoder could not open this file. Try H.264 MP4 or verify OpenCV FFmpeg support.")
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if width <= 0 or height <= 0 or width * height > 3840 * 2160:
            raise InspectionPipelineError("Unsupported video resolution (maximum 3840×2160).")
        if not math.isfinite(fps) or fps <= 0 or fps > 240 or frame_count < 1:
            raise InspectionPipelineError("Video metadata is invalid or unsupported (missing FPS or frame count).")
        duration_seconds = frame_count / fps
        if duration_seconds > MAX_DURATION_SECONDS:
            raise InspectionPipelineError(f"For this video inspection, use clips up to {int(MAX_DURATION_SECONDS)} seconds.")
        if duration_seconds <= 0:
            raise InspectionPipelineError("Video duration could not be determined.")
        # Analyse every frame that will appear in the encoded output, using
        # the faster YOLO detector to trigger full 09b only on new entries or
        # periodic drift-correction frames. No 12-keyframe inference limit.
        out_fps = min(fps, OUTPUT_MAX_FPS)
        total_output_frames = max(1, int(math.ceil(duration_seconds * out_fps)))
        trigger = VideoEntryTrigger(width=width, zone_x0=safe_zone[0], zone_x1=safe_zone[2])
        refresh_interval = max(1, round(PERIODIC_REFRESH_SECONDS * out_fps))
        next_refresh = 0
        source_frame = None
        current_src_index = -1
        frames = []
        samples = []
        summed = defaultdict(int)
        defect_counts = {}
        model = None
        for out_index in range(total_output_frames):
            _check_cancel(cancel_check)
            desired_index = min(frame_count - 1, int(out_index * fps / out_fps))
            while current_src_index < desired_index:
                ok, source_frame = cap.read()
                if not ok:
                    raise InspectionPipelineError(
                        f"Video frame {desired_index} could not be decoded during entry detection."
                    )
                current_src_index += 1
            if progress_callback and (out_index == 0 or out_index % max(1, int(out_fps)) == 0):
                progress_callback(
                    5 + round(out_index / total_output_frames * 78),
                    f"Checking biscuit entries: frame {out_index + 1}/{total_output_frames}"
                )
            # The active 09b detector is reused with identical weights and
            # thresholds; lightweight detection does NOT assign defect class.
            boxes = detect_video_frame_boxes(source_frame, cancel_check=cancel_check)
            arrived = trigger.update(boxes, out_index)
            inside_box = any(
                safe_zone[0] * width <= (b[0] + b[2]) * .5 < safe_zone[2] * width
                for b in boxes
            )
            should_inspect = bool(arrived) or (inside_box and out_index >= next_refresh)
            if not should_inspect:
                continue
            next_refresh = out_index + refresh_interval
            time_seconds = desired_index / fps
            if progress_callback:
                progress_callback(
                    5 + round(out_index / total_output_frames * 78),
                    f"Running 09b on {'new biscuit entry' if arrived else 'drift refresh'} "
                    f"at {time_seconds:.2f}s (AI frame {len(samples) + 1})"
                )
            encoded, jpeg = cv2.imencode(".jpg", source_frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if not encoded:
                raise InspectionPipelineError("Failed to encode video detection frame.")
            source_bytes = jpeg.tobytes()
            result = inspect_image_bytes_with_progress(source_bytes, cancel_check=cancel_check)
            _check_cancel(cancel_check)
            summary = result.get("summary") or {}
            model = model or result.get("model")
            for key in ("judged", "normal", "defect", "detected_boxes", "kept"):
                summed[key] += int(summary.get(key, 0) or 0)
            for defect in result.get("defect_counts") or []:
                name = defect.get("class_name", "unknown")
                if name not in defect_counts:
                    defect_counts[name] = dict(defect, count=0)
                defect_counts[name]["count"] += int(defect.get("count", 0) or 0)
            samples.append({
                "time_seconds": time_seconds,
                "output_frame_index": out_index,
                "objects": result.get("objects") or [],
            })
            if len(frames) < MAX_PREVIEW_FRAMES:
                overlay_bytes = render_mask_overlay_webp(source_bytes, result)
                arr = np.frombuffer(overlay_bytes, dtype=np.uint8)
                annotated_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if annotated_bgr is None:
                    raise InspectionPipelineError("Could not decode annotated AI frame overlay.")
                preview_ok, preview_webp = cv2.imencode(
                    ".webp", annotated_bgr, [cv2.IMWRITE_WEBP_QUALITY, 80]
                )
                if not preview_ok:
                    raise InspectionPipelineError("Could not encode AI preview.")
                frames.append({
                    "index": len(samples),
                    "time_seconds": round(time_seconds, 3),
                    "annotated_preview": _preview_url(preview_webp.tobytes()),
                    "summary": {k: summary.get(k, 0) for k in ("judged", "normal", "defect")},
                })
        # A valid video with zero recognized biscuits is still a valid
        # inspection. Export the unannotated frames with zero observations.
        cap.release()
        cap = None
        if progress_callback:
            progress_callback(86, "Propagating full masks / encoding clean H.264 MP4")
        export_meta = _make_annotated_video(
            path, output_path, fps=fps, frame_count=frame_count, width=width,
            height=height, samples=samples, safe_zone=safe_zone, progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
        _check_cancel(cancel_check)
        judged = summed["judged"]
        summary_out = {
            "judged": judged,
            "normal": summed["normal"],
            "defect": summed["defect"],
            "detected_boxes": summed["detected_boxes"],
            "kept": summed["kept"],
            "yield_percent": round(100 * summed["normal"] / judged, 2) if judged else None,
        }
        if progress_callback:
            progress_callback(100, "Annotated video export complete")
        return {
            "ok": True,
            "kind": "video",
            "method": "yolo_per_frame_on_entry_09b_flow_x_zone",
            "model": model or {},
            "video": {
                "duration_seconds": round(duration_seconds, 2),
                "source_fps": round(fps, 2),
                "frame_count": frame_count,
                "width": width,
                "height": height,
                "sampled_frames": len(samples),
                "ai_inspection_frames": len(samples),
                "preview_frames": len(frames),
                "yolo_checked_frames": total_output_frames,
                "entry_trigger_count": trigger.total_triggered,
                "sample_interval_note": "YOLO checks every output frame; full 09b runs when a new box enters and periodically to correct drift. Between AI frames, masks are optical-flow estimates. This is offline and can take time.",
            },
            "annotated_video": export_meta,
            "frames": frames,
            "summary": summary_out,
            "defect_counts": list(defect_counts.values()),
            "counting_note": "Summary statistics count repeated AI-frame observations, NOT unique biscuits or production yield. YOLO tracks may switch identity and models can miss/overlap objects; optical-flow frames are not new AI classifications.",
            "record": {"saved": False, "reason": "Video inspections are not yet saved into production Reports."},
        }
    except cv2.error as exc:
        raise InspectionPipelineError("OpenCV could not decode or annotate video frames.") from exc
    finally:
        if cap is not None:
            cap.release()
        if path is not None:
            path.unlink(missing_ok=True)
        # The service removes failed/partially completed outputs. Successful files
        # are owned by the route's authenticated, expiring inspection job.
        if output_path.exists() and (not output_path.is_file() or output_path.stat().st_size == 0):
            output_path.unlink(missing_ok=True)
            output_path.with_suffix(".tracks.json").unlink(missing_ok=True)
