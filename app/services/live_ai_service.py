"""Single-process, opt-in CCTV AI sampler for the existing validated 09b pipeline.

Camera MJPEG capture is never paused while GPU analysis executes. The annotated
image corresponds to the *analysed keyframe*, not a stale mask mapped onto
moving video. Observations are sampled and must not be treated as distinct
products or saved inspection runs. No DB/filesystem writes.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
import os
import threading
import time
import uuid


def _safe_int(value, default, low, high):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return min(high, max(low, number))


def _colour_bgr(value):
    if isinstance(value, str) and len(value) == 7 and value.startswith('#'):
        try:
            r, g, b = (int(value[i:i+2], 16) for i in (1, 3, 5))
            return b, g, r
        except ValueError:
            pass
    return (55, 55, 160)


def _annotate(frame, objects):
    import cv2
    import numpy as np
    canvas = frame.copy()
    # Per-mask overlays avoid allocating enormous full-frame tensors for all masks.
    for obj in objects[:100]:
        polygons = obj.get('polygons') or []
        colour = _colour_bgr(obj.get('mask_colour'))
        for poly in polygons[:16]:
            if len(poly) < 3:
                continue
            points = np.asarray(poly, dtype=np.float32)
            if points.ndim != 2 or points.shape[1] != 2:
                continue
            points[:, 0] = np.clip(points[:, 0], 0, frame.shape[1]-1)
            points[:, 1] = np.clip(points[:, 1], 0, frame.shape[0]-1)
            contour = points.astype(np.int32)
            if contour.shape[0] < 3:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            if w < 1 or h < 1:
                continue
            roi = canvas[y:y+h, x:x+w]
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(mask, [contour - [x, y]], 255)
            tinted = np.empty_like(roi)
            tinted[:] = colour
            blended = cv2.addWeighted(roi, 0.62, tinted, 0.38, 0)
            cv2.copyTo(blended, mask, roi)
            cv2.polylines(canvas, [contour], True, colour, 2, cv2.LINE_AA)
        bbox = obj.get('bbox') or {}
        x = _safe_int(bbox.get('x0', 0), 0, 0, frame.shape[1]-1)
        y = _safe_int(bbox.get('y0', 0), 0, 0, frame.shape[0]-1)
        label = str(obj.get('display_name') or obj.get('class_name') or 'Object')[:28]
        conf = obj.get('class_confidence')
        if isinstance(conf, (float, int)):
            label += f' {float(conf):.2f}'
        cv2.putText(canvas, label, (x, max(17, y-7)), cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                    (255, 255, 255), 3, cv2.LINE_AA)
        cv2.putText(canvas, label, (x, max(17, y-7)), cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                    colour, 1, cv2.LINE_AA)
    return canvas


class LiveAI:
    def __init__(self):
        self.lock = threading.RLock()
        self.stop_signal = threading.Event()
        self.thread = None
        self.generation = 0
        self.state = 'stopped'
        self.error = ''
        self.stage = 'Idle'
        self.sample_count = 0
        self.observed = 0
        self.normal = 0
        self.defective = 0
        self.last_duration = None
        self.ai_fps = None
        self.device = 'Awaiting model load'
        self.model_version = None
        self.jpeg = None
        self.jpeg_sequence = 0
        self.annotated_at = None
        self.events = []
        self.last_events = {}
        self._sample_sequence = -1

    def _reset(self):
        self.error = ''
        self.stage = 'Waiting for first keyframe'
        self.sample_count = self.observed = self.normal = self.defective = 0
        self.last_duration = self.ai_fps = None
        self.device = 'Awaiting model load'
        self.model_version = None
        self.jpeg = None
        self.jpeg_sequence = 0
        self.annotated_at = None
        self.events = []
        self.last_events = {}
        self._sample_sequence = -1

    def start(self, app, camera):
        if camera.status().get('state') != 'online':
            return False, 'Connect the camera before starting AI detection.'
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return False, 'AI worker is already active or stopping; please wait.'
            self.generation += 1
            self._reset()
            self.state = 'starting'
            self.stop_signal = threading.Event()
            self.thread = threading.Thread(target=self._worker,
                                           args=(app, camera, self.stop_signal, self.generation),
                                           daemon=True, name='bika-live-ai-09b')
            self.thread.start()
        return True, 'Starting sampled 09b AI inspection on the latest camera frames.'

    def stop(self):
        with self.lock:
            self.stop_signal.set()
            self.generation += 1
            self.state = 'stopped'
            self.stage = 'Stopped'
            self.jpeg = None
            self.annotated_at = None
        return True

    def status(self, include_events=True):
        with self.lock:
            rate = (100 * self.defective / self.observed) if self.observed else None
            active = self.state in ('starting', 'running')
            return {
                'state': self.state,
                'active': active,
                'stage': self.stage,
                'message': self.error,
                'sample_count': self.sample_count,
                'judged_observations': self.observed,
                'normal_observations': self.normal,
                'defect_observations': self.defective,
                'sampled_reject_rate': round(rate, 1) if rate is not None else None,
                'ai_fps': round(self.ai_fps, 3) if self.ai_fps is not None else None,
                'inference_seconds': round(self.last_duration, 2) if self.last_duration is not None else None,
                'last_sample_at': self.annotated_at,
                'overlay_ready': self.jpeg is not None,
                'model_device': self.device,
                'model_version': self.model_version,
                'events': [{k: v for k, v in ev.items() if k != 'preview'} for ev in self.events[:30]] if include_events else [],
                'event_total': len(self.events),
                'counts_are_observations': True,
            }

    def latest_overlay(self):
        with self.lock:
            return self.jpeg_sequence, self.jpeg

    def event_preview(self, key):
        with self.lock:
            for ev in self.events:
                if ev['id'] == key:
                    return ev.get('preview')
        return None

    def _record_events(self, frame, objects, moment):
        import cv2
        H, W = frame.shape[:2]
        new_events = []
        for obj in objects:
            if not obj.get('in_safe_zone') or str(obj.get('decision', '')).lower() != 'defect':
                continue
            centre = obj.get('centre') or {}
            x = float(centre.get('x', 0)); y = float(centre.get('y', 0))
            klass = str(obj.get('display_name') or obj.get('class_name') or 'Defect')[:60]
            # Approximate same-position suppression, NOT full multi-frame tracking.
            key = (klass, round(x / max(1, W) * 12), round(y / max(1, H) * 12))
            if moment - self.last_events.get(key, -1e9) < 12:
                continue
            self.last_events[key] = moment
            bbox = obj.get('bbox') or {}
            x0 = _safe_int(bbox.get('x0', x-35), 0, 0, W-1)
            y0 = _safe_int(bbox.get('y0', y-35), 0, 0, H-1)
            x1 = _safe_int(bbox.get('x1', x+35), W-1, 0, W)
            y1 = _safe_int(bbox.get('y1', y+35), H-1, 0, H)
            margin = 18
            crop = frame[max(0, y0-margin): min(H, max(y0+1, y1)+margin),
                         max(0, x0-margin): min(W, max(x0+1, x1)+margin)]
            jpeg = None
            if crop.size:
                scale = min(1.0, 260 / max(crop.shape[:2]))
                if scale < 1.0:
                    crop = cv2.resize(crop, None, fx=scale, fy=scale)
                ok, encoded = cv2.imencode('.jpg', crop, [int(cv2.IMWRITE_JPEG_QUALITY), 76])
                if ok:
                    jpeg = encoded.tobytes()
            new_events.append({
                'id': uuid.uuid4().hex,
                'time': datetime.now().astimezone().strftime('%H:%M:%S'),
                'label': klass,
                'confidence': obj.get('class_confidence'),
                'preview': jpeg,
            })
        self.last_events = {k: v for k, v in self.last_events.items() if moment - v < 30}
        self.events = (new_events + self.events)[:50]

    def _worker(self, app, camera, stopped, generation):
        # Only the worker loads model modules. The preview/status endpoints never do.
        try:
            import cv2
            import numpy as np
            from app.services.inspection_pipeline_service import inspect_image_bytes_with_progress
            width_limit = _safe_int(os.getenv('BIKA_LIVE_AI_MAX_WIDTH', '1280'), 1280, 640, 1920)
            interval = max(2.0, min(30.0, float(os.getenv('BIKA_LIVE_AI_MIN_INTERVAL', '3'))))
            with app.app_context():
                while not stopped.is_set():
                    if camera.status().get('state') != 'online':
                        # Graceful shutdown if camera goes offline.
                        with self.lock:
                            if generation == self.generation:
                                self.state = 'stopped'; self.stage = 'Camera offline'
                        return
                    seq, jpg = camera.latest()
                    if jpg is None or seq == self._sample_sequence:
                        stopped.wait(0.15)
                        continue
                    self._sample_sequence = seq
                    start = time.monotonic()
                    frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is None:
                        stopped.wait(0.25)
                        continue
                    height, width = frame.shape[:2]
                    scale = min(1.0, width_limit / width, 720 / height)
                    if scale < 1.0:
                        frame = cv2.resize(frame, (max(1, round(width*scale)), max(1, round(height*scale))),
                                           interpolation=cv2.INTER_AREA)
                    valid, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
                    if not valid:
                        continue
                    with self.lock:
                        if generation != self.generation:
                            return
                        self.state = 'running'
                        self.stage = 'Analysing latest keyframe (09b)'
                    def progress(_, label):
                        with self.lock:
                            if generation == self.generation:
                                self.stage = str(label)[:90]
                    result = inspect_image_bytes_with_progress(
                        encoded.tobytes(), progress_callback=progress,
                        cancel_check=stopped.is_set,
                    )
                    if stopped.is_set():
                        return
                    objects = result.get('objects') or []
                    annotated = _annotate(frame, objects)
                    valid, snapshot = cv2.imencode('.jpg', annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                    summary = result.get('summary') or {}
                    duration = time.monotonic()-start
                    from app.services.inspection_device_status_service import runtime_model_device_snapshot
                    model_device = runtime_model_device_snapshot().get('label', 'Unverified')
                    with self.lock:
                        if generation != self.generation:
                            return
                        self.sample_count += 1
                        self.observed += int(summary.get('judged') or 0)
                        self.normal += int(summary.get('normal') or 0)
                        self.defective += int(summary.get('defect') or 0)
                        self.last_duration = duration
                        self.ai_fps = 1 / max(duration, interval) if duration > 0 else None
                        self.device = model_device
                        self.model_version = (result.get('model') or {}).get('version')
                        self.annotated_at = datetime.now().astimezone().isoformat(timespec='seconds')
                        if valid:
                            self.jpeg = snapshot.tobytes()
                            self.jpeg_sequence += 1
                        self._record_events(frame, objects, time.monotonic())
                        self.stage = 'Ready · awaiting next keyframe'
                    stopped.wait(max(0.0, interval - duration))
        except Exception as exc:
            # No internal exception strings from the 09b backend are sent to clients:
            # they might contain local paths, model metadata or configuration secrets.
            import logging
            logging.getLogger(__name__).exception('Live AI worker failed: %s', type(exc).__name__)
            with self.lock:
                if generation == self.generation and not stopped.is_set():
                    self.error = 'AI processing failed. Check the Flask terminal for details.'
                    self.state = 'error'
                    self.stage = 'Stopped after processing error'
        finally:
            with self.lock:
                if generation == self.generation and self.state in ('running', 'starting'):
                    self.state = 'stopped'
                    self.stage = 'Stopped'


live_ai = LiveAI()
