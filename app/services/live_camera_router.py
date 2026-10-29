"""Source selector for BIKA Live Stream: existing Hikvision RTSP or Camo local webcam.

This router intentionally does not change the existing Hikvision capture service.
Its public methods match the LiveCamera interface used by the live AI worker.
"""
from __future__ import annotations

import threading

from app.services.live_camera_service import live_camera as hikvision_camera
from app.services.live_camo_service import live_camo


class CameraRouter:
    def __init__(self):
        self._lock = threading.RLock()
        self._current = hikvision_camera

    def _service(self):
        with self._lock:
            return self._current

    def status(self):
        return self._service().status()

    def latest(self):
        return self._service().latest()

    def connect(self, stream='main'):
        # Restrict sources; never let clients request an arbitrary video URL/path.
        if not isinstance(stream, str) or (stream not in ('main', 'sub') and not
            (stream.startswith('camo:') and stream[5:].isascii() and stream[5:].isdecimal() and 0 <= int(stream[5:]) <= 7)):
            return False, 'Invalid camera source or device index.'
        target = live_camo if stream.startswith('camo:') else hikvision_camera
        with self._lock:
            current = self._current
            if current.status()['state'] not in ('disconnected', 'error'):
                return False, 'Disconnect the current camera before changing the source.'
            if current is not target:
                current.disconnect()
                self._current = target
            return target.connect(stream)

    def disconnect(self):
        with self._lock:
            return self._current.disconnect()


camera_router = CameraRouter()
