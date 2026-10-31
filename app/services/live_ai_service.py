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



def _live_mask_roi():
    """Optional NORMALISED belt area: left,top,right,bottom. Unset -> whole frame.

    Only affects the live UI's observations and overlays; the validated
    Inspection pipeline and its calibrated outputs are left unchanged.
    """
    text = os.getenv('BIKA_LIVE_MASK_ROI', '').strip()
    if not text:
        return None
    try:
        left, top, right, bottom = (float(v.strip()) for v in text.split(','))
        if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
            raise ValueError('invalid range')
        if (right - left) < .10 or (bottom - top) < .10:
            raise ValueError('area too small')
        return (left, top, right, bottom)
    except (TypeError, ValueError):
        import logging
        logging.getLogger(__name__).warning('Ignoring invalid BIKA_LIVE_MASK_ROI; expected normalized left,top,right,bottom.')
        return None


def _live_mask_candidates(objects, frame_shape, model_version='', roi=None):
    """Conservative, live-only sanity gate to reduce obvious SAM3 false masks.

    Does not assert an object is a biscuit: a model trained with explicit
    background/negative examples is needed for a reliable such guarantee.
    Keeps object ordering and classification without altering Inspection.
    """
    height, width = frame_shape[:2]
    is_prawn_model = str(model_version).lower().startswith(('v3', 'v4')) or 'prawn' in str(model_version).lower()
    try:
        max_fraction = max(.01, min(.50, float(os.getenv('BIKA_LIVE_MASK_MAX_FRAME_FRACTION', '.15'))))
    except (ValueError, TypeError):
        max_fraction = .15
    try:
        min_aspect = max(1., min(5., float(os.getenv('BIKA_LIVE_MASK_MIN_PRAWN_ASPECT', '1.25'))))
    except (ValueError, TypeError):
        min_aspect = 1.25
    try:
        min_detection_conf = max(0., min(1., float(os.getenv('BIKA_LIVE_MASK_MIN_DETECTION_CONF', '0.0'))))
    except (ValueError, TypeError):
        min_detection_conf = 0.0

    selected = []
    for item in objects:
        if not isinstance(item, dict):
            continue
        # Ignore edge / occluded / not-judged candidates rather than painting
        # every SAM3 proposal returned by the serialized Inspection result.
        if not item.get('in_safe_zone') or str(item.get('decision', '')).lower() not in ('normal', 'defect'):
            continue
        if not item.get('polygons'):
            continue
        box = item.get('bbox') or {}
        try:
            x0, y0 = float(box['x0']), float(box['y0'])
            x1, y1 = float(box['x1']), float(box['y1'])
            area = float(item.get('mask_area') or 0)
            confidence = float(item.get('detection_confidence') or 0)
        except (ValueError, TypeError, KeyError):
            continue
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        if bw <= 1 or bh <= 1 or area <= 0 or area > height * width * max_fraction:
            continue
        if confidence < min_detection_conf:
            continue
        if is_prawn_model and max(bw, bh) / max(1., min(bw, bh)) < min_aspect:
            continue
        if roi is not None:
            cx = float((item.get('centre') or {}).get('x', (x0 + x1) / 2)) / max(1, width)
            cy = float((item.get('centre') or {}).get('y', (y0 + y1) / 2)) / max(1, height)
            if not (roi[0] <= cx <= roi[2] and roi[1] <= cy <= roi[3]):
                continue
        selected.append(item)
    return selected


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
        self.mask_suppressed_last = 0

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
        self.mask_suppressed_last = 0

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
        if os.environ.get('BIKA_REALTIME_LIVE_ENABLED', '0').strip().lower() in ('1','true','yes','on'):
            return True, 'Starting YOLO + selective v4 camera tracking (provisional counts).'
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
                'events': [{k: v for k, v in ev.items() if k not in ('preview', 'mask_preview')} for ev in self.events[:30]] if include_events else [],
                'event_total': len(self.events),
                'mask_suppressed_last': self.mask_suppressed_last,
                'mask_filter_mode': 'live-preview-only',
                'counts_are_observations': not (os.environ.get('BIKA_REALTIME_LIVE_ENABLED','0').strip().lower() in ('1','true','yes','on')),
                'counts_are_provisional': os.environ.get('BIKA_REALTIME_LIVE_ENABLED','0').strip().lower() in ('1','true','yes','on'),
            }

    def latest_overlay(self):
        with self.lock:
            return self.jpeg_sequence, self.jpeg

    def event_preview(self, key, variant="original"):
        with self.lock:
            for ev in self.events:
                if ev['id'] == key:
                    return ev.get('mask_preview' if variant == 'mask' else 'preview')
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
            left = max(0, x0 - margin)
            top = max(0, y0 - margin)
            right = min(W, max(x0+1, x1) + margin)
            bottom = min(H, max(y0+1, y1) + margin)
            crop = frame[top:bottom, left:right]
            jpeg = None
            mask_jpeg = None
            if crop.size:
                # Render ONLY this candidate's polygon onto the companion crop.
                # This uses its already-computed SAM3 polygons; no second GPU call.
                import numpy as np
                masked_crop = crop.copy()
                colour = _colour_bgr(obj.get('mask_colour'))
                for poly in (obj.get('polygons') or [])[:16]:
                    if len(poly) < 3:
                        continue
                    coords = np.asarray(poly, dtype=np.float32)
                    if coords.ndim != 2 or coords.shape[1] != 2:
                        continue
                    coords[:, 0] = np.clip(coords[:, 0] - left, 0, crop.shape[1]-1)
                    coords[:, 1] = np.clip(coords[:, 1] - top, 0, crop.shape[0]-1)
                    contour = coords.astype(np.int32)
                    if len(contour) < 3:
                        continue
                    region = np.zeros(crop.shape[:2], np.uint8)
                    cv2.fillPoly(region, [contour], 255)
                    tinted = np.empty_like(masked_crop)
                    tinted[:] = colour
                    blend = cv2.addWeighted(masked_crop, .61, tinted, .39, 0)
                    cv2.copyTo(blend, region, masked_crop)
                    cv2.polylines(masked_crop, [contour], True, (255, 255, 255), 2, cv2.LINE_AA)
                scale = min(1.0, 320 / max(crop.shape[:2]))
                if scale < 1.0:
                    size = (max(1, int(round(crop.shape[1]*scale))), max(1, int(round(crop.shape[0]*scale))))
                    crop = cv2.resize(crop, size, interpolation=cv2.INTER_AREA)
                    masked_crop = cv2.resize(masked_crop, size, interpolation=cv2.INTER_AREA)
                ok, encoded = cv2.imencode('.jpg', crop, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ok:
                    jpeg = encoded.tobytes()
                ok, encoded = cv2.imencode('.jpg', masked_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
                if ok:
                    mask_jpeg = encoded.tobytes()
            new_events.append({
                'id': uuid.uuid4().hex,
                'time': datetime.now().astimezone().strftime('%H:%M:%S'),
                'label': klass,
                'confidence': obj.get('class_confidence'),
                'detection_confidence': obj.get('detection_confidence'),
                'decision': obj.get('decision', 'defect'),
                'model_version': self.model_version,
                'preview': jpeg,
                'mask_preview': mask_jpeg,
            })
        self.last_events = {k: v for k, v in self.last_events.items() if moment - v < 30}
        self.events = (new_events + self.events)[:50]

    def _worker(self, app, camera, stopped, generation):
        # Only the worker loads model modules. The preview/status endpoints never do.
        try:
            if os.environ.get('BIKA_REALTIME_LIVE_ENABLED','0').strip().lower() in ('1','true','yes','on'):
                from app.services.realtime_inspection_service import run_realtime_live_worker
                return run_realtime_live_worker(self, app, camera, stopped, generation)
            import cv2
            import numpy as np
            from app.services.inspection_pipeline_service import inspect_image_bytes_with_progress
            roi = _live_mask_roi()
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
                    all_objects = result.get('objects') or []
                    model_version = (result.get('model') or {}).get('version') or ''
                    objects = _live_mask_candidates(all_objects, frame.shape, model_version, roi)
                    annotated = _annotate(frame, objects)
                    valid, snapshot = cv2.imencode('.jpg', annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                    duration = time.monotonic()-start
                    from app.services.inspection_device_status_service import runtime_model_device_snapshot
                    model_device = runtime_model_device_snapshot().get('label', 'Unverified')
                    with self.lock:
                        if generation != self.generation:
                            return
                        self.sample_count += 1
                        # Live statistics must match masks actually shown, not
                        # the unfiltered offline Inspection summary.
                        self.mask_suppressed_last = max(0, len(all_objects) - len(objects))
                        self.observed += len(objects)
                        self.normal += sum(str(o.get('decision', '')).lower() == 'normal' for o in objects)
                        self.defective += sum(str(o.get('decision', '')).lower() == 'defect' for o in objects)
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
