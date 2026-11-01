"""BIKA demo realtime engine, shared by opt-in Video and Live services.

Image Inspection is intentionally untouched (SAM3). Model predictions, track IDs
and motion-gated counts remain PROVISIONAL until verified against annotated GT.
"""
from __future__ import annotations

import base64
import json
import logging
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from datetime import datetime
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np

from app.services.inspection_pipeline_service import InspectionCancelled, InspectionPipelineError
from app.services.video_safe_zone import DEFAULT_ZONE, validate_zone

_LOG = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]     # D:/BDS/BIKA_inspectionWebsite
BRIDGE = ROOT / 'realtime_v4_bridge'
MODEL_NAMES = ('normal', 'too_dark', 'too_short', 'fractured', 'bent_snack')
DISPLAY = {'normal': 'Normal', 'too_dark': 'Too Dark', 'too_short': 'Too Short',
           'fractured': 'Fractured', 'bent_snack': 'Bent Snack'}
RGB = {'normal': (55, 181, 109), 'too_dark': (255, 0, 170),
       'too_short': (72, 161, 226), 'fractured': (230, 70, 76),
       'bent_snack': (184, 93, 222)}
# Video and Live cannot run two full 8GB GPU sessions concurrently on a laptop.
_RT_SESSION_LOCK = threading.Lock()


def _enabled(var):
    return os.environ.get(var, '0').strip().lower() in ('1', 'true', 'yes', 'on')


def _read_int(var, default, low, high):
    try:
        return max(low, min(high, int(os.environ.get(var, default))))
    except (TypeError, ValueError):
        return default


def _check_cancel(callback):
    if callback and callback():
        raise InspectionCancelled('Video inspection cancelled by user.')


def _ffmpeg():
    binary = shutil.which('ffmpeg')
    if binary:
        return binary
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, OSError, RuntimeError):
        raise InspectionPipelineError('FFmpeg is required to export annotated MP4.')


def _bridge():
    # The tested bridge is standalone code importing sibling modules by name.
    # Only add its known local folder, never an external/user-controlled path.
    if not (BRIDGE / 'v4_selective_adapter.py').is_file():
        raise InspectionPipelineError('Realtime bridge files missing: realtime_v4_bridge')
    if str(BRIDGE) not in sys.path:
        sys.path.insert(0, str(BRIDGE))
    from tracking import StableTracks
    from counting_motion import MotionGatedCounter
    from v4_selective_adapter import SelectiveV4Adapter
    from preview_selective import choose_indices
    return StableTracks, MotionGatedCounter, SelectiveV4Adapter, choose_indices


class RealtimeInspectionEngine:
    """One continuously advancing stream. Do not share between two inputs."""
    def __init__(self, device='0', direction='rtl', line=.75, quota=16,
                 conf=.25, imgsz=640, max_det=200):
        from ultralytics import YOLO
        StableTracks, MotionGatedCounter, SelectiveV4Adapter, choose_indices = _bridge()
        checkpoint = ROOT / 'lightweight_quickstart' / 'runs' / 'prawn_tiles_v2' / 'weights' / 'best.pt'
        if not checkpoint.is_file():
            raise InspectionPipelineError('YOLO realtime checkpoint missing: lightweight_quickstart/runs/prawn_tiles_v2/weights/best.pt')
        self.yolo = YOLO(str(checkpoint))
        if self.yolo.task != 'segment' or len(self.yolo.names) != 1:
            raise InspectionPipelineError('Expected the validated ONE-class YOLO segmentation checkpoint.')
        self.classifier = SelectiveV4Adapter(ROOT, device)
        self.tracker = StableTracks(min_hits=3, lost_frames=28, reid_iou=.5)
        self.make_counter = MotionGatedCounter
        self.choose_indices = choose_indices
        self.counter = None
        self.direction, self.line = direction, float(line)
        self.device, self.quota = str(device), int(quota)
        self.conf, self.imgsz, self.max_det = float(conf), int(imgsz), int(max_det)
        self.frame_index = 0
        self.cache = {}
        self.last_classified = {}
        self.totals = Counter()
        self.last_fps = 0.
        self.processed_frames = 0
        self.tracker_config = str(BRIDGE / 'bytetrack_bika.yaml')

    def process(self, frame):
        """Return a frame's real YOLO masks, stable IDs, cached predictions and count events."""
        h, w = frame.shape[:2]
        self.frame_index += 1
        i = self.frame_index
        if self.counter is None:
            self.counter = self.make_counter(direction=self.direction, position=self.line,
                                              width=w, height=h)
        start = time.perf_counter()
        result = self.yolo.track(frame, persist=True, tracker=self.tracker_config,
                                 device=self.device, imgsz=self.imgsz,
                                 conf=self.conf, max_det=self.max_det,
                                 iou=.5, verbose=False)[0]
        objs = []
        if (result.boxes is not None and result.masks is not None and
                result.boxes.id is not None):
            boxes = result.boxes.xyxy.cpu().numpy()
            rawids = result.boxes.id.int().cpu().numpy()
            confs = result.boxes.conf.cpu().numpy()
            polygons = result.masks.xy
            n = min(len(boxes), len(rawids), len(confs), len(polygons))
            stable = self.tracker.update(
                [(int(rawids[j]), boxes[j], float(confs[j])) for j in range(n)], i)
            objs = [(*stable[j], polygons[j]) for j in range(min(n, len(stable)))]
        else:
            self.tracker.update([], i)
        selection, pending = self.choose_indices(
            objs, self.cache, self.last_classified, i, self.quota, 12, .65,
            self.direction, w, h, 2)
        if selection:
            fresh = self.classifier.predict_selected(
                frame, [o[6] for o in objs], [o[3] for o in objs], selection)
            for j, prediction in fresh.items():
                sid = objs[j][3]
                self.cache[sid] = prediction
                self.last_classified[sid] = i
        self.counter.observe_frame(i, objs, w, h)
        observations, events = [], []
        for raw, box, det_conf, sid, confirmed, just_confirmed, poly in objs:
            pred = self.cache.get(sid)
            label, probability = (pred[0], float(pred[1])) if pred is not None else (None, None)
            counted = self.counter.update(sid, confirmed, label, probability,
                                           self.tracker, .50)
            entry = {'sid':int(sid), 'raw_id':int(raw), 'bbox':tuple(float(x) for x in box),
                     'poly':np.asarray(poly, dtype=np.float32), 'det_conf':float(det_conf),
                     'label':label, 'confidence':probability, 'confirmed':bool(confirmed),
                     'counted':counted}
            observations.append(entry)
            if counted:
                self.totals[label] += 1
                events.append({**entry, 'frame':i,
                               'motion':dict(self.counter.last_event)})
        if i % 60 == 0:
            active = set(self.tracker.tracks)
            self.classifier.prune(active)
            self.cache = {k:v for k,v in self.cache.items() if k in active}
            self.last_classified = {k:v for k,v in self.last_classified.items() if k in active}
            self.counter.prune(active)
        elapsed = max(time.perf_counter()-start, .000001)
        self.last_fps = 1. / elapsed
        self.processed_frames += 1
        return {'objects':observations, 'events':events, 'pending':pending,
                'visible':len(observations), 'fps':self.last_fps,
                'elapsed':elapsed, 'frame':i,
                'motion_active':self.counter.scene_active,
                'count':len(self.counter.counted)}


def _polygons_and_bounds(o, scale_x=1., scale_y=1.):
    poly = np.asarray(o['poly'], np.float32)
    if poly.ndim != 2 or poly.shape[0] < 3:
        return []
    # Keep enough shape detail for the existing click-to-select video UI.
    if len(poly) > 64:
        poly = poly[::math.ceil(len(poly)/64)]
    pts = [[int(round(float(x)*scale_x)), int(round(float(y)*scale_y))] for x,y in poly]
    return [pts] if len(pts) >= 3 else []


def annotate(frame, state, *, direction='rtl', line=.75, show_labels=False,
             max_masks=200):
    """Fast single-blend frame overlay and optional clickable polygon metadata."""
    h,w = frame.shape[:2]
    overlay = frame.copy()
    mask_union = np.zeros((h,w), np.uint8)
    clickable = []
    for idx, o in enumerate(state['objects']):
        if idx >= max_masks:
            break
        poly = o['poly']
        if len(poly) < 3:
            continue
        contour = np.rint(poly).astype(np.int32)
        label = o['label']
        rgb = RGB.get(label, (180,180,180))
        colour = (rgb[2],rgb[1],rgb[0])
        cv2.fillPoly(overlay, [contour], colour)
        cv2.fillPoly(mask_union, [contour], 255)
        cv2.polylines(frame, [contour], True, colour, 1, cv2.LINE_AA)
        if show_labels and (o['counted'] or idx < 15):
            x0,y0,_,_ = o['bbox']
            cv2.putText(frame, f"#{o['sid']} {DISPLAY.get(label, 'Pending')}",
                        (max(0,int(x0)), max(15,int(y0)-4)),
                        cv2.FONT_HERSHEY_SIMPLEX,.35,colour,1,cv2.LINE_AA)
        polys = _polygons_and_bounds(o)
        if polys:
            x0,y0,x1,y1 = o['bbox']
            clickable.append([o['sid'], [int(x0),int(y0),int(x1),int(y1)], polys])
    mixed = cv2.addWeighted(frame, .65, overlay, .35, 0)
    frame[mask_union > 0] = mixed[mask_union > 0]
    if direction in ('rtl','ltr'):
        x = int(w*(1-line if direction=='rtl' else line))
        cv2.line(frame,(x,0),(x,h),(0,226,244),2)
    else:
        y = int(h*(1-line if direction=='btt' else line))
        cv2.line(frame,(0,y),(w,y),(0,226,244),2)
    cv2.rectangle(frame,(0,0),(min(w,680),53),(20,24,27),-1)
    cv2.putText(frame, f"BIKA Selective v4 | visible {state['visible']} | pending {state['pending']}",
                (9,19),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1,cv2.LINE_AA)
    cv2.putText(frame, f"Count {state['count']} (provisional) | Track IDs | {state['fps']:.1f} inference FPS",
                (9,41),cv2.FONT_HERSHEY_SIMPLEX,.44,(80,230,230),1,cv2.LINE_AA)
    return frame, clickable


def _preview_frame(frame, index, time_seconds, counts):
    ok, jpg = cv2.imencode('.webp', frame, [cv2.IMWRITE_WEBP_QUALITY, 75])
    if not ok:
        return None
    return {'index': index, 'time_seconds':round(time_seconds, 3),
            'annotated_preview':'data:image/webp;base64,'+base64.b64encode(jpg.tobytes()).decode('ascii'),
            'summary':{'judged':sum(counts.values()), 'normal':counts.get('normal',0),
                       'defect':sum(n for k,n in counts.items() if k != 'normal')}}


def inspect_realtime_video_bytes_with_progress(video_bytes, *, filename, output_path,
                                                 progress_callback=None, cancel_check=None,
                                                 safe_zone=DEFAULT_ZONE):
    """Offline video export: analyze source frames sequentially, encode bounded output FPS.

    NEVER call the SAM3 image pipeline. Output is actual YOLO masks, not flow estimates.
    Existing job routes, authentication, output URLs and cleanup remain unchanged.
    """
    safe_zone = validate_zone(safe_zone)
    if not video_bytes or Path(filename).suffix.lower() not in ('.mp4','.mov','.avi','.webm'):
        raise InspectionPipelineError('Upload a supported, nonempty MP4/MOV/AVI/WEBM video.')
    if len(video_bytes) > 80 * 1024 * 1024:
        raise InspectionPipelineError('Video is larger than the 80MB demo limit.')
    output_path = Path(output_path)
    if not _RT_SESSION_LOCK.acquire(blocking=False):
        raise InspectionPipelineError('Realtime Video/Live GPU engine is busy. Stop Live AI and retry.')
    source, cap, proc = None, None, None
    temporary = output_path.with_suffix('.partial.mp4')
    side_tmp = output_path.with_suffix('.tracks.partial.json')
    success = False
    try:
        suffix = Path(filename).suffix.lower()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as file:
            file.write(video_bytes)
            source = Path(file.name)
        cap = cv2.VideoCapture(str(source))
        if not cap.isOpened():
            raise InspectionPipelineError('Could not decode uploaded video.')
        source_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if (not 0 < source_fps <= 240 or total <= 0 or width<1 or height<1 or
                width*height > 3840*2160 or total/source_fps > 120):
            raise InspectionPipelineError('Unsupported video metadata or duration (>120s).')
        direction = os.getenv('BIKA_REALTIME_DIRECTION','rtl').lower()
        if direction not in ('rtl','ltr','ttb','btt'):
            raise InspectionPipelineError('Invalid BIKA_REALTIME_DIRECTION.')
        try:
            line = float(os.environ.get('BIKA_REALTIME_LINE','.75'))
        except ValueError:
            raise InspectionPipelineError('Invalid BIKA_REALTIME_LINE.')
        if not .05 < line < .95:
            raise InspectionPipelineError('BIKA_REALTIME_LINE must be within (0.05,0.95).')
        if progress_callback: progress_callback(2, 'Loading YOLO11n-Seg and v4 Classifier (no SAM3)')
        engine = RealtimeInspectionEngine(
            device=os.getenv('BIKA_REALTIME_DEVICE','0'), direction=direction,
            line=line, quota=_read_int('BIKA_REALTIME_CLASSIFY_BUDGET',16,1,100))
        # Keep tracking at native source FPS: skipping frames changes motion/ID persistence.
        # Encode a smaller FPS movie for demo playback, without double-counting objects.
        output_fps = min(source_fps, 24.)
        output_count = max(1, int(math.ceil(total * output_fps/source_fps)))
        scale = min(1., 1280/width, 720/height)
        out_w = max(2, int(width*scale)//2*2)
        out_h = max(2, int(height*scale)//2*2)
        sx, sy = out_w/width, out_h/height
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [_ffmpeg(),'-nostdin','-hide_banner','-loglevel','error','-y',
               '-f','rawvideo','-vcodec','rawvideo','-pix_fmt','bgr24',
               '-s',f'{out_w}x{out_h}','-r',f'{output_fps:.6f}',
               '-i','pipe:0','-an','-c:v','libx264','-preset','veryfast',
               '-crf','24','-pix_fmt','yuv420p','-movflags','+faststart',
               '-f','mp4',str(temporary)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        history, timelines, activations, previews = {}, [], [], []
        next_output = 0
        event_count = Counter()
        events_total = 0
        for i in range(total):
            _check_cancel(cancel_check)
            ok, frame = cap.read()
            if not ok:
                raise InspectionPipelineError(f'Video decoding stopped early (frame {i+1}/{total}).')
            state = engine.process(frame)
            for e in state['events']:
                event_count[e['label']] += 1
                events_total += 1
                activations.append({'track_id':e['sid'], 'entry_frame':i,
                                    'class_name':e['label'], 'confidence':e['confidence']})
            if progress_callback and (i % max(1,int(source_fps)) == 0 or i==total-1):
                progress_callback(5 + round((i+1)/total*89),
                                  f'YOLO + Tracking + v4: frame {i+1}/{total} (provisional count {events_total})')
            # Output frames at source-time-aligned positions, not more than once per source frame.
            if next_output < output_count and i >= min(total-1, int(next_output*source_fps/output_fps)):
                rendered = (cv2.resize(frame, (out_w,out_h), interpolation=cv2.INTER_AREA)
                            if (out_w,out_h)!=(width,height) else frame.copy())
                # Work in output pixels, but leave model/tracking at native resolution.
                remapped=[]
                for o in state['objects']:
                    r=dict(o)
                    r['bbox']=(o['bbox'][0]*sx,o['bbox'][1]*sy,o['bbox'][2]*sx,o['bbox'][3]*sy)
                    r['poly']=o['poly']*np.asarray([sx,sy],np.float32)
                    remapped.append(r)
                # Safe Zone filters which whole masks are visible/clickable; the
                # motion-gated counter remains tied to its independently configured line.
                visible_in_zone = [o for o in remapped if
                    safe_zone[0] <= (o['bbox'][0]+o['bbox'][2])/(2*out_w) < safe_zone[2]]
                painted, clickable = annotate(rendered, {**state,'objects':visible_in_zone},
                                              direction=direction,line=line)
                try:
                    proc.stdin.write(painted.tobytes())
                except (BrokenPipeError, OSError) as exc:
                    raise InspectionPipelineError('H.264 export failed; check FFmpeg installation.') from exc
                timelines.append([next_output, clickable])
                for o in remapped:
                    sid = str(o['sid'])
                    meta = {'track_id':o['sid'], 'class_name':o['label'] or 'pending',
                            'display_name':DISPLAY.get(o['label'],'Pending'),
                            'class_confidence':o['confidence'],
                            'detection_confidence':o['det_conf'],
                            'decision':('normal' if o['label']=='normal' else 'defect' if o['label'] else 'pending'),
                            'mask_colour':'#%02x%02x%02x'%RGB.get(o['label'],(160,160,160))}
                    entries = history.setdefault(sid, [])
                    if not entries or entries[-1][1] != meta:
                        entries.append([next_output,meta])
                if len(previews) < 12 and (next_output == 0 or next_output % max(1,int(output_fps*2))==0):
                    preview = _preview_frame(painted, next_output, i/source_fps, event_count)
                    if preview: previews.append(preview)
                next_output += 1
        # Defensive duration padding for a fractional final output frame.
        while next_output < output_count:
            proc.stdin.write(painted.tobytes())
            timelines.append([next_output,clickable])
            next_output += 1
        proc.stdin.close()
        errors = (proc.stderr.read() or b'').decode('utf-8','replace')[-500:]
        code = proc.wait(timeout=45)
        if code != 0 or not temporary.exists() or temporary.stat().st_size==0:
            raise InspectionPipelineError('Video export failed: '+(errors or 'FFmpeg error'))
        _check_cancel(cancel_check)
        sidecar = {'fps':output_fps,'width':out_w,'height':out_h,
                   'method':'yolo11n_seg_selective_v4_motion_guard',
                   'safe_zone':list(safe_zone), 'tracks':history,
                   'frames':timelines,'activations':activations}
        with side_tmp.open('w', encoding='utf-8') as out:
            json.dump(sidecar,out,ensure_ascii=False,separators=(',',':'))
        os.replace(temporary,output_path)
        os.replace(side_tmp,output_path.with_suffix('.tracks.json'))
        success = True
        judged = sum(event_count.values())
        normal = event_count['normal']
        if progress_callback: progress_callback(100, 'YOLO tracked video export complete')
        return {'ok':True,'kind':'video', 'method':'yolo11n_seg_selective_v4_motion_guard',
                'model':{'version':'Realtime YOLO11n-Seg + Website v4 classifier',
                         'segmenter':'YOLO11n-Seg','classifier':'v4 (5-class)'},
                'video':{'duration_seconds':round(total/source_fps,2),
                         'source_fps':round(source_fps,2),'frame_count':total,
                         'width':width,'height':height,'sampled_frames':total,
                         'ai_inspection_frames':total,'preview_frames':len(previews),
                         'yolo_checked_frames':total, 'entry_trigger_count':events_total,
                         'sample_interval_note':'YOLO and tracking processed all source frames; classification is selectively cached.'},
                'annotated_video':{'available':True,'format':'MP4 (H.264)',
                                   'width':out_w,'height':out_h,'fps':round(output_fps,2),
                                   'size_bytes':output_path.stat().st_size,
                                   'note':'Actual YOLO masks + Stable IDs; Safe Zone filters visible masks, while the line controls provisional counts. No physical-identity guarantee.',
                                   'audio_preserved':False,'tracked_ids':len(history),
                                   'safe_zone':list(safe_zone),'zone_triggered_tracks':events_total,
                                   'tracking_method':'yolo_bytetrack_stable_id_motion_guard'},
                'frames':previews,
                'summary':{'judged':judged,'normal':normal,'defect':judged-normal,
                           'detected_boxes':len(engine.tracker.confirmed_ids),
                           'kept':judged,'yield_percent':None},
                'defect_counts':[{'class_name':key,'display_name':DISPLAY.get(key,key),
                                  'count':int(n), 'colour':'#%02x%02x%02x' % RGB.get(key,(122,122,122))} for key,n in event_count.items() if key!='normal'],
                'counting_note':('PROVISIONAL: counted at most once per Stable ID after motion-gated line crossing. '
                                 'ID switches can still count the same physical biscuit twice; '
                                 'classification F1 is not validated on live-video ground truth.'),
                'record':{'saved':False,'reason':'Demo video runs are not production reports.'}}
    except (cv2.error, OSError) as exc:
        _LOG.exception('Realtime video failed')
        raise InspectionPipelineError('Realtime video decoding or encoding failed; check server logs.') from exc
    finally:
        if cap is not None: cap.release()
        if proc is not None and proc.poll() is None:
            proc.kill()
            try: proc.communicate(timeout=4)
            except (OSError, subprocess.TimeoutExpired): pass
        if source is not None: source.unlink(missing_ok=True)
        if not success:
            temporary.unlink(missing_ok=True)
            side_tmp.unlink(missing_ok=True)
        _RT_SESSION_LOCK.release()


def _cropped_live_event(frame, o, model_version):
    x0,y0,x1,y1 = o['bbox']
    h,w=frame.shape[:2]
    left=max(0,int(x0)-16); right=min(w,int(x1)+17)
    top=max(0,int(y0)-16); bottom=min(h,int(y1)+17)
    crop = frame[top:bottom,left:right].copy()
    if crop.size == 0:
        return None
    masked = crop.copy()
    poly = (o['poly'] - np.asarray([left,top],np.float32)).astype(np.int32)
    if len(poly)>=3: cv2.polylines(masked,[poly],True,(0,255,255),2)
    ok, before = cv2.imencode('.jpg',crop,[cv2.IMWRITE_JPEG_QUALITY,80])
    ok2, after = cv2.imencode('.jpg',masked,[cv2.IMWRITE_JPEG_QUALITY,80])
    if not ok: return None
    return {'id':__import__('uuid').uuid4().hex,
            'time':datetime.now().astimezone().strftime('%H:%M:%S'),
            'label':DISPLAY.get(o['label'],o['label'] or 'Pending'),
            'confidence':o['confidence'],'detection_confidence':o['det_conf'],
            'decision':'defect','model_version':model_version,'track_id':o['sid'],
            'preview':before.tobytes(), 'mask_preview':after.tobytes() if ok2 else before.tobytes()}


def run_realtime_live_worker(state, app, camera, stopped, generation):
    """AI inference and a genuinely continuous newest-camera-frame mask view.

    Detected masks are exact ONLY on AI frames. Intermediate frames use motion
    projection; the visual projector never changes AI classes, Track IDs or counts.
    """
    from app.services.live_mask_projection_service import LiveMaskProjector
    from app.services.live_defect_observer import LiveDefectObserver

    if not _RT_SESSION_LOCK.acquire(blocking=False):
        raise InspectionPipelineError('Video/Live realtime GPU engine is already busy.')
    projector_thread = None
    try:
        with app.app_context():
            direction = os.getenv('BIKA_REALTIME_DIRECTION', 'rtl').lower()
            line = float(os.getenv('BIKA_REALTIME_LINE', '.75'))
            engine = RealtimeInspectionEngine(
                device=os.getenv('BIKA_REALTIME_DEVICE','0'), direction=direction,
                line=line, quota=_read_int('BIKA_REALTIME_CLASSIFY_BUDGET',16,1,100))
            observer = LiveDefectObserver()  # BIKA-LIVE-OBSERVE-CAMO-V3
            projector = LiveMaskProjector(
                state, generation, direction=direction, line=line,
                target_fps=_read_int('BIKA_LIVE_MASK_DISPLAY_FPS',12,2,20))
            projector_thread = threading.Thread(
                target=projector.loop, args=(camera, stopped), daemon=True,
                name='bika-live-continuous-mask')
            projector_thread.start()
            while not stopped.is_set():
                if camera.status().get('state') != 'online':
                    with state.lock:
                        if generation == state.generation:
                            state.state='stopped'; state.stage='Camera offline'
                    break
                camera_health = camera.status()
                if camera_health.get('feed_usable', True) is False:
                    projector.clear_anchor()
                    with state.lock:
                        if generation == state.generation:
                            state.stage = 'Camera feed unavailable — AI suspended (no logo detection)'
                    stopped.wait(.10)
                    continue
                # AI always reads the freshest complete input. Its processing
                # cadence is independent from the visual display frame cadence.
                sequence, jpg = camera.latest()
                if jpg is None or sequence == state._sample_sequence:
                    stopped.wait(.025)
                    continue
                state._sample_sequence = sequence
                frame = cv2.imdecode(np.frombuffer(jpg,np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    continue
                started=time.monotonic()
                with state.lock:
                    if generation != state.generation:
                        return
                    state.state='running'
                    state.stage='YOLO tracking + continuous motion-aligned mask display'
                result=engine.process(frame)
                # Publish detections AND the exact source frame together.
                # The projector aligns these polygons to NEW camera frames.
                projector.publish_detection(frame,result)
                observed = observer.observe(result['objects'], time.monotonic())
                fresh_events=[_cropped_live_event(frame,e,'Realtime YOLO11n-Seg + v4')
                              for e in observed]
                fresh_events=[e for e in fresh_events if e]
                with state.lock:
                    if generation != state.generation:
                        return
                    state.sample_count += 1
                    # Live metrics: unique classified TRACK IDs, not conveyor throughput.
                    state.observed=len(observer.seen_class)
                    state.normal=sum(v=='normal' for v in observer.seen_class.values())
                    state.defective=state.observed-state.normal
                    state.mask_suppressed_last=0
                    state.last_duration=time.monotonic()-started
                    state.ai_fps=1/max(state.last_duration,1e-3)
                    state.device='CUDA GPU '+engine.device if engine.device!='cpu' else 'CPU'
                    state.model_version='Realtime YOLO11n-Seg + v4'
                    state.annotated_at=datetime.now().astimezone().isoformat(timespec='seconds')
                    state.events=(fresh_events+state.events)[:50]
                    state.stage=(f"Live tracked {result['visible']} objects · pending {result['pending']}"
                                 f" · on-screen defect observations {observer.event_count} (provisional)")
                    # DO NOT publish a whole-frame AI snapshot here: only the
                    # projector thread publishes continuous newest-camera frames.
    finally:
        stopped.set()
        if projector_thread is not None:
            projector_thread.join(timeout=2.0)
        _RT_SESSION_LOCK.release()
