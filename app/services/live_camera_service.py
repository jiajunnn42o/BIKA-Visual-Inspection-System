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
                "last_frame_seconds_ago": round(time.monotonic()-self._frame_time, 1) if self._frame_time and self._status == "online" else None,
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
            # Actual OpenCV capture release occurs in worker, preventing cross-thread race.
        return True

    def latest(self):
        with self._lock:
            return self._sequence, self._jpeg if self._status == "online" else None

    def _capture_loop(self, generation, stopped, stream):
        cap = None
        try:
            import cv2
            url = self._rtsp_url(stream)
            # Hikvision cameras commonly negotiate RTSP more reliably over TCP.
            # Do not override a deliberate operator-supplied OpenCV setting.
            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
            if not cv2.videoio_registry.hasBackend(cv2.CAP_FFMPEG):
                raise RuntimeError("OpenCV FFmpeg backend is unavailable. Check your OpenCV installation.")
            # FFmpeg timeout properties are supported by modern OpenCV builds.
            # Older builds fall back to the normal constructor.
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
            last = time.monotonic()
            smooth_fps = 0.0
            failures = 0
            while not stopped.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    failures += 1
                    if failures >= 15:
                        raise RuntimeError("Camera stopped sending frames. Check connection and RTSP settings.")
                    time.sleep(0.08)
                    continue
                failures = 0
                now = time.monotonic()
                dt = now-last
                last = now
                if dt > 0:
                    smooth_fps = (0.85 * smooth_fps + 0.15 / dt) if smooth_fps else (1 / dt)
                # Save only the latest JPEG frame; avoid expensive simultaneous viewers.
                image_ok, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 78])
                if not image_ok:
                    continue
                height, width = frame.shape[:2]
                with self._lock:
                    if generation != self._generation or stopped.is_set():
                        break
                    if not self._online_since:
                        self._online_since = now
                    self._jpeg = encoded.tobytes()
                    self._sequence += 1
                    self._fps = smooth_fps
                    self._resolution = f"{width} × {height}"
                    self._frame_time = now
                    self._status = "online"
                    self._error = ""
        except Exception as exc:
            # Never expose raw OpenCV/FFmpeg exceptions: they can include RTSP credentials.
            error = str(exc) if isinstance(exc, RuntimeError) else "Camera capture failed. Verify network, RTSP codec and camera settings."
            with self._lock:
                if generation == self._generation:
                    self._status = "error"
                    self._error = error
                    self._jpeg = None
                    self._fps = 0.0
                    self._online_since = 0.0
        finally:
            if cap is not None:
                cap.release()
            with self._lock:
                if generation == self._generation and self._status == "connecting":
                    self._status = "disconnected"


live_camera = LiveCamera()
