"""Lightweight frame-to-frame detector-box association for video entry triggers.

This tracker determines *when* to request a fresh validated 09b inspection.
It does not create segmentation masks, assign defect classes or count products.
"""
from __future__ import annotations

from dataclasses import dataclass


def _iou(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    overlap = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if overlap == 0:
        return 0.0
    a_area = max(1.0, (a[2] - a[0]) * (a[3] - a[1]))
    b_area = max(1.0, (b[2] - b[0]) * (b[3] - b[1]))
    return overlap / (a_area + b_area - overlap)


@dataclass
class _BoxTrack:
    bbox: tuple
    last_seen: int
    entered: bool = False


class VideoEntryTrigger:
    """Trigger once per detector identity when its centre enters the x-only zone."""

    def __init__(self, *, width: int, zone_x0: float, zone_x1: float, max_lost: int = 8):
        self.width = width
        self.xmin = width * zone_x0
        self.xmax = width * zone_x1
        self.max_lost = max_lost
        self.tracks: dict[int, _BoxTrack] = {}
        self.next_id = 0
        self.total_triggered = 0

    def update(self, boxes, frame_index: int) -> list[int]:
        """Return newly entered detection track IDs on *this* frame."""
        boxes = [tuple(float(v) for v in box[:4]) for box in boxes]
        for track_id, track in list(self.tracks.items()):
            if frame_index - track.last_seen > self.max_lost:
                del self.tracks[track_id]
        pairs = []
        for index, bbox in enumerate(boxes):
            cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
            size = max(1.0, bbox[2] - bbox[0], bbox[3] - bbox[1])
            for track_id, track in self.tracks.items():
                old = track.bbox
                ocx, ocy = (old[0] + old[2]) / 2, (old[1] + old[3]) / 2
                move = ((cx - ocx) ** 2 + (cy - ocy) ** 2) ** .5
                overlap = _iou(bbox, old)
                # Object can move between successive frames, but a distant
                # unrelated detection must never inherit its entered status.
                if overlap < .12 and move > size * .50:
                    continue
                score = overlap + max(0.0, .25 * (1 - move / size))
                pairs.append((score, index, track_id))
        assigned = {}
        claimed = set()
        for score, index, track_id in sorted(pairs, reverse=True):
            if index in assigned or track_id in claimed:
                continue
            assigned[index] = track_id
            claimed.add(track_id)
        newly_entered = []
        for index, bbox in enumerate(boxes):
            track_id = assigned.get(index)
            if track_id is None:
                self.next_id += 1
                track_id = self.next_id
                self.tracks[track_id] = _BoxTrack(bbox=bbox, last_seen=frame_index)
            track = self.tracks[track_id]
            track.bbox = bbox
            track.last_seen = frame_index
            center_x = (bbox[0] + bbox[2]) / 2
            if self.xmin <= center_x < self.xmax and not track.entered:
                track.entered = True
                newly_entered.append(track_id)
                self.total_triggered += 1
        return newly_entered


def detect_video_frame_boxes(frame_bgr, cancel_check=None) -> list[list[float]]:
    """Observe YOLO boxes with the *existing* locked 09b detector context.

    This helper lives only in the video add-on. The validated Image Inspection
    pipeline remains completely unchanged; no alternate detector weights or
    thresholds are introduced. Boxes are ONLY arrival triggers, not masks.
    """
    import cv2
    import numpy as np
    from PIL import Image
    from app.services import inspection_pipeline_service as pipeline

    if cancel_check and cancel_check():
        raise pipeline.InspectionCancelled("Video inspection cancelled by user.")
    context = pipeline.get_inspection_context()
    acquired = False
    try:
        while not acquired:
            if cancel_check and cancel_check():
                raise pipeline.InspectionCancelled("Video inspection cancelled by user.")
            acquired = pipeline._inference_lock.acquire(timeout=0.2)
        if cancel_check and cancel_check():
            raise pipeline.InspectionCancelled("Video inspection cancelled by user.")
        image_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        try:
            boxes, _ = pipeline.pipeline09b.detect(
                context["detector"], Image.fromarray(np.ascontiguousarray(image_rgb)),
                context["det_cfg"],
            )
        except pipeline.torch.cuda.OutOfMemoryError as exc:
            pipeline.torch.cuda.empty_cache()
            raise pipeline.InspectionPipelineError(
                "CUDA ran out of memory during video entry detection."
            ) from exc
        return boxes.tolist()
    finally:
        if acquired:
            pipeline._inference_lock.release()
