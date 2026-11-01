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

from app.services.live_feed_quality import FeedVisualGuard


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
        self._capture_resolution = None
        self._capture_backend = None
        self._framing_mode = 'auto'
        self._framing_applied = False
        self._online_since = 0.0
        self._black_since = 0.0  # BIKA-LIVE-HEALTH-LEGEND-V1
        self._feed_visual_guard = FeedVisualGuard()  # BIKA-LIVE-OBSERVE-CAMO-V3

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
                'capture_resolution': self._capture_resolution if online else None,
                'capture_backend': self._capture_backend if online else None,
                'framing_mode': self._framing_mode if online else None,
                'framing_applied': self._framing_applied if online else False,
                'last_frame_seconds_ago': round(now - self._frame_time, 3) if online and self._frame_time else None,
                'last_decoded_frame_seconds_ago': round(now - self._raw_frame_time, 3) if online and self._raw_frame_time else None,
                'stream_uptime_seconds': round(now - self._online_since, 1) if online and self._online_since else None,
                'snapshot_ready': online and self._jpeg is not None,
                'black_frame_seconds': round(now - self._black_since, 2) if online and self._black_since else 0.0,
                'placeholder_frame_seconds': self._feed_visual_guard.seconds(now) if online else 0.0,
                'feed_usable': (online and not self._feed_visual_guard.placeholder_active
                                and not (self._black_since and now-self._black_since >= 3)
                                and bool(self._raw_frame_time and now-self._raw_frame_time <= 3.5)),
                'feed_unavailable_reason': (
                    'Camo virtual camera is showing a neutral-grey placeholder (iPhone feed may have stopped).'
                    if self._feed_visual_guard.placeholder_active else
                    'Camera is returning a black feed.' if self._black_since and now-self._black_since >= 3 else
                    'Camera frames have stopped updating.' if online and self._raw_frame_time and now-self._raw_frame_time > 3.5 else
                    ''),
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
            self._capture_resolution = None
            self._capture_backend = None
            self._framing_applied = False
            self._online_since = 0.0
            self._black_since = 0.0  # BIKA-LIVE-HEALTH-LEGEND-V1
            self._feed_visual_guard = FeedVisualGuard()  # BIKA-LIVE-OBSERVE-CAMO-V3
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
            self._capture_resolution = None
            self._capture_backend = None
            self._framing_applied = False
            self._online_since = 0.0
            self._black_since = 0.0  # BIKA-LIVE-HEALTH-LEGEND-V1
            self._feed_visual_guard = FeedVisualGuard()  # BIKA-LIVE-OBSERVE-CAMO-V3
        return True

    def latest(self):
        with self._lock:
            return self._sequence, self._jpeg if self._status == 'online' else None

    def latest_raw(self):
        """Newest decoded frame for continuous AI display (never a stale JPEG)."""
        with self._lock:
            if self._status != 'online' or self._raw_frame is None:
                return self._raw_sequence, None, self._raw_frame_time
            return self._raw_sequence, self._raw_frame.copy(), self._raw_frame_time

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

    @staticmethod
    def _backend_choices(cv2):
        """Prefer the Windows Camera-compatible API; allow a safe override.

        This setting is intentionally limited to the Camo source.  Hikvision
        RTSP capture is handled by a completely separate service.
        """
        if sys.platform != 'win32':
            return [('ANY', cv2.CAP_ANY)]
        configured = os.getenv('BIKA_CAMO_BACKEND', 'MSMF').strip().upper()
        options = {
            'MSMF': cv2.CAP_MSMF,
            'DSHOW': cv2.CAP_DSHOW,
            'ANY': cv2.CAP_ANY,
        }
        if configured not in options:
            configured = 'MSMF'
        priority = [configured] + [name for name in ('MSMF', 'DSHOW', 'ANY') if name != configured]
        return [(name, options[name]) for name in priority]

    @staticmethod
    def _format_frame(frame, mode='auto'):
        """Optionally fill 16:9 by cropping clearly embedded black side bars.

        We never stretch or rotate the image.  Crop *before* supplying the
        frame to both the viewer and AI so overlays retain correct coordinates.
        An upstream portrait-only Camo source cannot be reconstructed as a
        genuinely wide camera view by cropping; the fill mode is a zoom.
        """
        if mode == 'original':
            return frame, False
        import cv2
        import numpy as np
        height, width = frame.shape[:2]
        if width < 200 or height < 120:
            return frame, False
        # Inspect columns well away from the top/bottom overlays and watermark.
        scale_width = 192
        scale_height = max(48, round(height * scale_width / width))
        thumb = cv2.resize(frame, (scale_width, scale_height), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(thumb, cv2.COLOR_BGR2GRAY) if thumb.ndim == 3 else thumb
        middle = gray[max(1, int(scale_height * .13)):max(2, int(scale_height * .82)):2, :]
        if middle.size == 0:
            return frame, False
        # Matte on both sides must be overwhelmingly black throughout the frame.
        matte = np.mean(middle <= 19, axis=0) >= .96
        left = 0
        while left < scale_width and matte[left]:
            left += 1
        right = scale_width - 1
        while right >= 0 and matte[right]:
            right -= 1
        # Ignore ordinary low-light scenes and small borders.
        if left < .10 * scale_width or (scale_width - 1 - right) < .10 * scale_width:
            return frame, False
        if right - left < .14 * scale_width:
            return frame, False
        # Exclude the matte-to-content transition to avoid thin black edges.
        left = min(scale_width - 2, left + 1)
        right = max(left + 1, right - 1)
        x0 = round(left / scale_width * width)
        x1 = round(right / scale_width * width)
        content = frame[:, x0:x1]
        ch, cw = content.shape[:2]
        target_ratio = 16.0 / 9.0
        if cw / ch < target_ratio:
            crop_height = min(ch, max(1, round(cw / target_ratio)))
            top = (ch - crop_height) // 2
            content = content[top:top + crop_height]
        else:
            crop_width = min(cw, max(1, round(ch * target_ratio)))
            left_crop = (cw - crop_width) // 2
            content = content[:, left_crop:left_crop + crop_width]
        # Use native requested 1280x720 output, same for previews and inference.
        content = cv2.resize(content, (1280, 720), interpolation=cv2.INTER_LINEAR)
        return content, True

    def _capture_loop(self, generation, stop, index):
        cap = None
        encoder = None
        try:
            import cv2
            # Windows Camera commonly uses Media Foundation (MSMF).  Try it
            # first, unlike the older DSHOW-first implementation.  A device
            # index may differ across backends; a user can override via .env.
            first_frame = None
            selected_backend = None
            for backend_name, backend in self._backend_choices(cv2):
                candidate = None
                try:
                    candidate = cv2.VideoCapture(index, backend)
                    if not candidate.isOpened():
                        continue
                    # Apply mode before the first read: some drivers negotiate
                    # the format only when streaming starts.
                    candidate.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                    candidate.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                    candidate.set(cv2.CAP_PROP_FPS, 30)
                    candidate.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    # Opening a device is not enough; require a real video frame.
                    ok, initial = candidate.read()
                    if not ok or initial is None:
                        continue
                    cap = candidate
                    selected_backend = backend_name
                    first_frame = initial
                    candidate = None  # ownership transferred to capture loop
                    break
                except (cv2.error, RuntimeError):
                    pass
                finally:
                    if candidate is not None:
                        candidate.release()
            if cap is None:
                raise RuntimeError(
                    f'Cannot read local camera {index}. Check Camo Studio and '
                    'the Compatibility Add-on, or try another Device Index. '
                    'You can also try BIKA_CAMO_BACKEND=DSHOW.'
                )
            framing_mode = os.getenv('BIKA_CAMO_FRAMING', 'auto').strip().lower()
            if framing_mode not in ('auto', 'original'):
                framing_mode = 'auto'
            with self._lock:
                if generation != self._generation or stop.is_set():
                    return
                self._capture_backend = selected_backend
                self._framing_mode = framing_mode
            encoder = threading.Thread(target=self._encode_loop, args=(generation, stop),
                                       daemon=True, name='bika-camo-jpeg')
            encoder.start()
            prior_at = time.monotonic()
            fps_smooth = 0.0
            misses = 0
            while not stop.is_set():
                if first_frame is not None:
                    frame, first_frame = first_frame, None
                    ok = True
                else:
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
                # Sample raw camera frames occasionally for sustained near-black output.
                # This is a health warning only: a legitimately dark scene can trigger it.
                near_black = None
                if self._raw_sequence % 10 == 0:
                    small = cv2.resize(frame, (48, 27), interpolation=cv2.INTER_AREA)
                    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small
                    near_black = bool(float(gray.mean()) <= 12 and float((gray < 18).mean()) >= .97)
                captured_h, captured_w = frame.shape[:2]
                frame, framed = self._format_frame(frame, framing_mode)
                h, w = frame.shape[:2]
                with self._lock:
                    if generation != self._generation or stop.is_set():
                        break
                    if not self._online_since:
                        self._online_since = now
                    if near_black is True and not self._black_since:
                        self._black_since = now
                    elif near_black is False:
                        self._black_since = 0.0
                    self._raw_frame = frame
                    self._raw_sequence += 1
                    self._raw_frame_time = now
                    self._fps = fps_smooth
                    self._resolution = f'{w} × {h}'
                    self._capture_resolution = f'{captured_w} × {captured_h}'
                    self._framing_applied = framed
                    if self._raw_sequence % 5 == 0:
                        self._feed_visual_guard.update(frame, now)
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
