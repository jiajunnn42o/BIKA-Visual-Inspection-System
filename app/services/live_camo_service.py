"""BIKA: local video-capture source for Camo Studio virtual webcam.

Camo Camera on iPhone forwards video to Camo Studio on the Windows host;
BIKA reads a user-selected LOCAL webcam index through OpenCV. No iPhone
network service, Bluetooth, new Python package or model change is involved.
"""
from __future__ import annotations

import os
import sys
import threading
import time


class LiveCamoCamera:
    """Keep OpenCV capture and JPEG encoding on independent threads."""

    DEVICE_LIMIT = 7  # selectable indices 0 through 7

    def __init__(self):
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._generation = 0
        self._status = 'disconnected'
        self._error = ''
        self._device_index = 0
        self._jpeg = None
        self._sequence = 0
        self._raw_frame = None
        self._raw_sequence = 0
        self._raw_frame_time = 0.0
        self._frame_time = 0.0
        self._fps = 0.0
        self._jpeg_fps = 0.0
        self._jpeg_encode_ms = 0.0
        self._resolution = None
        self._online_since = 0.0

    def status(self):
        with self._lock:
            online = self._status == 'online'
            now = time.monotonic()
            return {
                'state': self._status,
                'message': self._error,
                'configured': True,  # No Hikvision .env required for local capture.
                'source': 'iPhone Camera (Camo / Local Webcam)',
                'source_type': 'local_webcam',
                'stream': f'camo:{self._device_index}',
                'device_index': self._device_index,
                'camera_fps': round(self._fps, 1) if online else None,
                'jpeg_fps': round(self._jpeg_fps, 1) if online else None,
                'jpeg_encode_ms': round(self._jpeg_encode_ms, 1) if online else None,
                'resolution': self._resolution if online else None,
                'last_frame_seconds_ago': round(now - self._frame_time, 3) if online and self._frame_time else None,
                'last_decoded_frame_seconds_ago': round(now - self._raw_frame_time, 3) if online and self._raw_frame_time else None,
                'stream_uptime_seconds': round(now - self._online_since, 1) if online and self._online_since else None,
                'snapshot_ready': online and self._jpeg is not None,
                'ai_enabled': False,
            }

    def connect(self, stream='camo:0'):
        try:
            if not isinstance(stream, str) or not stream.startswith('camo:'):
                raise ValueError('Select an iPhone/Camo camera device first.')
            index_text = stream.split(':', 1)[1]
            if not index_text.isascii() or not index_text.isdecimal():
                raise ValueError('Invalid local camera device index.')
            index = int(index_text)
            if not 0 <= index <= self.DEVICE_LIMIT:
                raise ValueError('Local camera device index must be 0–7.')
        except ValueError as exc:
            return False, str(exc)

        with self._lock:
            if self._thread and self._thread.is_alive():
                return False, 'Camera is already starting or streaming. Disconnect first.'
            self._generation += 1
            generation = self._generation
            self._stop = threading.Event()
            self._device_index = index
            self._status = 'connecting'
            self._error = ''
            self._jpeg = None
            self._raw_frame = None
            self._raw_sequence = 0
            self._raw_frame_time = 0.0
            self._frame_time = 0.0
            self._fps = 0.0
            self._jpeg_fps = 0.0
            self._jpeg_encode_ms = 0.0
            self._resolution = None
            self._online_since = 0.0
            self._thread = threading.Thread(target=self._capture_loop,
                                            args=(generation, self._stop, index),
                                            daemon=True, name='bika-camo-capture')
            self._thread.start()
        return True, f'Opening local camera device {index}. Keep Camo Studio and Camo Camera running.'

    def disconnect(self):
        with self._lock:
            self._generation += 1
            self._stop.set()
            self._status = 'disconnected'
            self._error = ''
            self._jpeg = None
            self._raw_frame = None
            self._raw_frame_time = 0.0
            self._frame_time = 0.0
            self._fps = 0.0
            self._jpeg_fps = 0.0
            self._jpeg_encode_ms = 0.0
            self._resolution = None
            self._online_since = 0.0
        return True

    def latest(self):
        with self._lock:
            return self._sequence, self._jpeg if self._status == 'online' else None

    def _encode_loop(self, generation, stop):
        import cv2
        try:
            fps = max(1.0, min(20.0, float(os.getenv('BIKA_LIVE_JPEG_FPS', '10'))))
        except (ValueError, OverflowError):
            fps = 10.0
        try:
            quality = max(45, min(90, int(os.getenv('BIKA_LIVE_JPEG_QUALITY', '72'))))
        except ValueError:
            quality = 72
        prior_sequence = -1
        previous_at = 0.0
        next_due = 0.0
        while not stop.is_set():
            now = time.monotonic()
            if now < next_due:
                stop.wait(min(.05, next_due - now))
                continue
            with self._lock:
                if generation != self._generation:
                    return
                frame = self._raw_frame
                raw_seq = self._raw_sequence
                frame_time = self._raw_frame_time
            if frame is None or raw_seq == prior_sequence:
                stop.wait(.01)
                continue
            prior_sequence = raw_seq
            started = time.monotonic()
            ok, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            finished = time.monotonic()
            next_due = finished + 1.0 / fps
            if not ok:
                continue
            with self._lock:
                if generation != self._generation or stop.is_set():
                    return
                self._jpeg = encoded.tobytes()
                self._sequence += 1
                self._frame_time = frame_time
                elapsed_ms = (finished - started) * 1000
                self._jpeg_encode_ms = elapsed_ms if not self._jpeg_encode_ms else .85 * self._jpeg_encode_ms + .15 * elapsed_ms
                if previous_at and finished > previous_at:
                    actual = 1.0 / (finished - previous_at)
                    self._jpeg_fps = actual if not self._jpeg_fps else .85 * self._jpeg_fps + .15 * actual
                previous_at = finished
                self._status = 'online'
                self._error = ''

    def _capture_loop(self, generation, stop, index):
        cap = None
        encoder = None
        try:
            import cv2
            # DirectShow is often suitable for Camo's Windows compatibility camera;
            # fall back to Media Foundation / CAP_ANY for other drivers.
            backends = ([cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
                        if sys.platform == 'win32' else [cv2.CAP_ANY])
            for backend in backends:
                candidate = cv2.VideoCapture(index, backend)
                if candidate.isOpened():
                    cap = candidate
                    break
                candidate.release()
            if cap is None:
                raise RuntimeError(
                    f'Cannot open local camera {index}. Start Camo Studio and Camo Camera; '
                    'ensure the virtual webcam compatibility add-on is installed. '
                    'Try another Device Index (0–7).'
                )
            # These are requests, not guarantees; negotiated format is reported.
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_FPS, 30)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            encoder = threading.Thread(target=self._encode_loop, args=(generation, stop),
                                       daemon=True, name='bika-camo-jpeg')
            encoder.start()
            prior_at = time.monotonic()
            fps_smooth = 0.0
            misses = 0
            while not stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    misses += 1
                    if misses >= 30:
                        raise RuntimeError('Local camera stopped providing frames. Check Camo Studio or try another device index.')
                    stop.wait(.05)
                    continue
                misses = 0
                now = time.monotonic()
                delta = now - prior_at
                prior_at = now
                if delta > 0:
                    instant = min(120.0, 1.0 / delta)
                    fps_smooth = instant if not fps_smooth else .85 * fps_smooth + .15 * instant
                h, w = frame.shape[:2]
                with self._lock:
                    if generation != self._generation or stop.is_set():
                        break
                    if not self._online_since:
                        self._online_since = now
                    self._raw_frame = frame
                    self._raw_sequence += 1
                    self._raw_frame_time = now
                    self._fps = fps_smooth
                    self._resolution = f'{w} × {h}'
        except Exception as exc:
            # Deliberately avoid exposing device-driver details to the web UI.
            message = str(exc) if isinstance(exc, RuntimeError) else 'Local webcam capture failed. Check Camo Studio and camera permissions.'
            with self._lock:
                if generation == self._generation:
                    self._status = 'error'
                    self._error = message
                    self._jpeg = None
        finally:
            stop.set()
            if cap is not None:
                cap.release()
            if encoder is not None and encoder.is_alive():
                encoder.join(timeout=1.0)


live_camo = LiveCamoCamera()
