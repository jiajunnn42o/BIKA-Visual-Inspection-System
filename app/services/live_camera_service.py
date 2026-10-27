"""BIKA phase-one Hikvision capture service (single-process development use).

Camera credentials stay in server-side .env, never in browser parameters, API
responses, or application logs. No AI inference and no database writes.
"""
from __future__ import annotations

import ipaddress
import os
import re
import threading
import time
from urllib.parse import quote


class LiveCamera:
    def __init__(self):
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._capture = None
        self._generation = 0
        self._status = "disconnected"
        self._error = ""
        self._stream = "main"
        self._jpeg = None
        self._sequence = 0
        self._fps = 0.0
        self._resolution = None
        self._frame_time = 0.0
        self._online_since = 0.0
        # RTSP decode and JPEG delivery must not share the same loop: JPEG
        # compression can be slower than the camera's frame interval.
        self._raw_frame = None
        self._raw_sequence = 0
        self._raw_frame_time = 0.0
        self._jpeg_fps = 0.0
        self._jpeg_encode_ms = 0.0

    @staticmethod
    def configured():
        return bool(os.getenv("HIKVISION_CAMERA_HOST", "").strip()
                    and os.getenv("HIKVISION_CAMERA_USER", "").strip()
                    and os.getenv("HIKVISION_CAMERA_PASSWORD", ""))

    @staticmethod
    def _rtsp_url(stream):
        host = os.getenv("HIKVISION_CAMERA_HOST", "").strip()
        username = os.getenv("HIKVISION_CAMERA_USER", "").strip()
        password = os.getenv("HIKVISION_CAMERA_PASSWORD", "")
        if not host or not username or not password:
            raise ValueError("Configure HIKVISION_CAMERA_HOST, USER and PASSWORD in .env.")
        # Local controlled camera hostname/IP, never request-supplied network targets.
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", host):
                raise ValueError("Invalid camera hostname/IP configuration.")
        try:
            port = int(os.getenv("HIKVISION_RTSP_PORT", "554"))
        except ValueError as exc:
            raise ValueError("Invalid HIKVISION_RTSP_PORT setting.") from exc
        if not (1 <= port <= 65535):
            raise ValueError("Invalid HIKVISION_RTSP_PORT setting.")
        channel = "101" if stream == "main" else "102"
        return f"rtsp://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}/Streaming/Channels/{channel}"

    def status(self):
        with self._lock:
            return {
                "state": self._status,
                "message": self._error,
                "configured": self.configured(),
                "source": "Hikvision Network Camera",
                "stream": self._stream,
                "camera_fps": round(self._fps, 1) if self._status == "online" else None,
                "resolution": self._resolution if self._status == "online" else None,
                # Both ages start at decoding on this server. Neither measures
                # time already spent inside the camera or FFmpeg's input buffer.
                "last_frame_seconds_ago": round(time.monotonic()-self._frame_time, 3) if self._frame_time and self._status == "online" else None,
                "last_decoded_frame_seconds_ago": round(time.monotonic()-self._raw_frame_time, 3) if self._raw_frame_time and self._status == "online" else None,
                "jpeg_fps": round(self._jpeg_fps, 1) if self._status == "online" else None,
                "jpeg_encode_ms": round(self._jpeg_encode_ms, 1) if self._status == "online" else None,
                "stream_uptime_seconds": round(time.monotonic()-self._online_since, 1) if self._online_since and self._status == "online" else None,
                "snapshot_ready": self._jpeg is not None and self._status == "online",
                "ai_enabled": False,
            }

    def connect(self, stream="main"):
        if stream not in {"sub", "main"}:
            return False, "Invalid stream selection."
        try:
            # Validate configuration without ever logging/returning the full RTSP URL.
            self._rtsp_url(stream)
        except ValueError as exc:
            return False, str(exc)
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False, "Camera is already connecting or streaming. Disconnect first."
            self._generation += 1
            generation = self._generation
            self._stop = threading.Event()
            self._status = "connecting"
            self._error = ""
            self._stream = stream
            self._jpeg = None
            self._fps = 0.0
            self._resolution = None
            self._frame_time = 0.0
            self._online_since = 0.0
            self._raw_frame = None
            self._raw_sequence = 0
            self._raw_frame_time = 0.0
            self._jpeg_fps = 0.0
            self._jpeg_encode_ms = 0.0
            self._thread = threading.Thread(
                target=self._capture_loop, args=(generation, self._stop, stream),
                daemon=True, name="bika-live-camera",
            )
            self._thread.start()
        return True, "Connecting to configured Hikvision camera."

    def disconnect(self):
        with self._lock:
            self._generation += 1
            self._stop.set()
            self._status = "disconnected"
            self._error = ""
            self._jpeg = None
            self._fps = 0.0
            self._resolution = None
            self._frame_time = 0.0
            self._online_since = 0.0
            self._raw_frame = None
            self._raw_frame_time = 0.0
            self._jpeg_fps = 0.0
            self._jpeg_encode_ms = 0.0
            # Actual OpenCV capture release occurs in worker, preventing cross-thread race.
        return True

    def latest(self):
        with self._lock:
            return self._sequence, self._jpeg if self._status == "online" else None

    def _encode_latest_loop(self, generation, stopped):
        """JPEG-encode only the latest decoded frame, never a FIFO of old frames.

        Heavy OpenCV JPEG compression happens here, not inside RTSP cap.read().
        The stream worker can continue draining/decoding the camera independently.
        """
        import cv2
        try:
            jpeg_rate = max(1.0, min(15.0, float(os.getenv("BIKA_LIVE_JPEG_FPS", "10"))))
        except (ValueError, OverflowError):
            jpeg_rate = 10.0
        try:
            quality = max(45, min(90, int(os.getenv("BIKA_LIVE_JPEG_QUALITY", "72"))))
        except ValueError:
            quality = 72
        interval = 1.0 / jpeg_rate
        previous_raw_sequence = -1
        previous_sent_at = 0.0
        next_due = time.monotonic()
        while not stopped.is_set():
            now = time.monotonic()
            if now < next_due:
                stopped.wait(min(0.05, next_due - now))
                continue
            with self._lock:
                if generation != self._generation:
                    return
                raw = self._raw_frame
                raw_sequence = self._raw_sequence
                raw_time = self._raw_frame_time
            if raw is None or raw_sequence == previous_raw_sequence:
                stopped.wait(0.012)
                continue
            previous_raw_sequence = raw_sequence
            encode_started = time.monotonic()
            ok, encoded = cv2.imencode(".jpg", raw, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            emitted_at = time.monotonic()
            next_due = emitted_at + interval
            if not ok:
                continue
            with self._lock:
                if generation != self._generation or stopped.is_set():
                    return
                # Timestamp is when this frame was decoded on the server;
                # avoid falsely presenting JPEG completion time as capture time.
                self._jpeg = encoded.tobytes()
                self._sequence += 1
                self._frame_time = raw_time
                duration_ms = (emitted_at - encode_started) * 1000.0
                self._jpeg_encode_ms = duration_ms if not self._jpeg_encode_ms else 0.85 * self._jpeg_encode_ms + 0.15 * duration_ms
                if previous_sent_at:
                    gap = emitted_at - previous_sent_at
                    if gap > 0:
                        new_fps = 1.0 / gap
                        self._jpeg_fps = new_fps if not self._jpeg_fps else 0.85 * self._jpeg_fps + 0.15 * new_fps
                previous_sent_at = emitted_at
                self._status = "online"
                self._error = ""

    def _capture_loop(self, generation, stopped, stream):
        cap = None
        encoder = None
        try:
            import cv2
            url = self._rtsp_url(stream)
            # Keep operator-provided FFmpeg opts. Optional low-latency
            # camera settings take effect on the NEXT full Flask restart.
            if os.getenv("BIKA_RTSP_LOW_LATENCY", "0").strip() == "1":
                capture_options = (
                    "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|"
                    "max_delay;0|reorder_queue_size;0"
                )
            else:
                capture_options = "rtsp_transport;tcp"
            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", capture_options)
            if not cv2.videoio_registry.hasBackend(cv2.CAP_FFMPEG):
                raise RuntimeError("OpenCV FFmpeg backend is unavailable. Check your OpenCV installation.")
            try:
                cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, [
                    cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 7000,
                    cv2.CAP_PROP_READ_TIMEOUT_MSEC, 7000,
                ])
            except (TypeError, AttributeError, cv2.error):
                cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                raise RuntimeError(
                    "RTSP video could not be opened. Port 554 may be reachable while "
                    "RTSP authentication, channel 101/102 or the camera codec fails. "
                    "Test both streams with the included Hikvision diagnostic tool."
                )

            # This worker consumes camera frames as fast as possible. A second
            # worker compresses sampled, freshest frames for browser/API use.
            encoder = threading.Thread(
                target=self._encode_latest_loop, args=(generation, stopped),
                daemon=True, name="bika-live-jpeg-encoder",
            )
            encoder.start()
            previous_capture_at = time.monotonic()
            smooth_fps = 0.0
            failures = 0
            while not stopped.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    failures += 1
                    if failures >= 15:
                        raise RuntimeError("Camera stopped sending frames. Check connection and RTSP settings.")
                    stopped.wait(0.08)
                    continue
                failures = 0
                now = time.monotonic()
                dt = now - previous_capture_at
                previous_capture_at = now
                if dt > 0:
                    instant_fps = 1.0 / dt
                    smooth_fps = (0.85 * smooth_fps + 0.15 * instant_fps) if smooth_fps else instant_fps
                height, width = frame.shape[:2]
                with self._lock:
                    if generation != self._generation or stopped.is_set():
                        break
                    if not self._online_since:
                        self._online_since = now
                    self._raw_frame = frame
                    self._raw_sequence += 1
                    self._raw_frame_time = now
                    self._fps = smooth_fps
                    self._resolution = f"{width} × {height}"
        except Exception as exc:
            # Never expose raw OpenCV/FFmpeg exceptions: URLs can contain credentials.
            error = str(exc) if isinstance(exc, RuntimeError) else "Camera capture failed. Verify network, RTSP codec and camera settings."
            with self._lock:
                if generation == self._generation:
                    self._status = "error"
                    self._error = error
                    self._jpeg = None
                    self._fps = 0.0
                    self._online_since = 0.0
        finally:
            stopped.set()
            if cap is not None:
                cap.release()
            if encoder is not None and encoder.is_alive():
                encoder.join(timeout=1.0)
            with self._lock:
                if generation == self._generation and self._status == "connecting":
                    self._status = "disconnected"


live_camera = LiveCamera()
