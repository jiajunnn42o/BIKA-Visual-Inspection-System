"""Continuous LIVE overlay compositor for BIKA's opt-in YOLO video worker.

Never re-uses an analysed JPEG as a frozen video frame. Every published JPEG
contains the newest camera frame. Intermediate masks are translated by measured
image motion (phase correlation), NOT newly AI-inferred segmentation. If motion
is unreliable or the analysis is stale, masks are hidden instead of guessed.

AI detection, classification, tracking IDs and counting are unchanged and run in
RealtimeInspectionEngine; this service only handles visual presentation.
"""
from __future__ import annotations

import os
import threading
import time

import cv2
import numpy as np


PALETTE = {
    'normal': (55, 181, 109),
    'too_dark': (255, 0, 170),
    'too_short': (45, 190, 255),
    'fractured': (230, 70, 76),
    'bent_snack': (140, 92, 246),
}


def _gray(frame, size=(320, 180)):
    return cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), size,
                      interpolation=cv2.INTER_AREA).astype(np.float32)


class LiveMaskProjector:
    """Thread-safe detector anchor + latest-frame visual-only mask projection."""
    def __init__(self, state, generation, direction='rtl', line=.75, target_fps=12):
        self.state = state
        self.generation = generation
        self.direction = direction
        self.line = line
        self.target_fps = max(2, min(20, int(target_fps)))
        self.lock = threading.RLock()
        self.anchor = None
        self.objects = []
        self.anchor_time = 0.0
        self.max_age = max(.2, min(1.2, float(os.getenv('BIKA_LIVE_MASK_MAX_AGE','0.9'))))
        self.response_min = max(.05, min(.80, float(os.getenv('BIKA_LIVE_FLOW_MIN_RESPONSE','.22'))))
        self.frames_rendered = 0
        self.fps = 0.0
        self.mask_status = 'Waiting for first detection'
        self._window = cv2.createHanningWindow((320,180), cv2.CV_32F)

    def clear_anchor(self):
        """Discard prior AI masks immediately when Camo stops delivering video."""
        with self.lock:
            self.anchor = None
            self.objects = []
            self.anchor_time = 0.0

    def publish_detection(self, frame, result):
        """Called by slow AI thread; original frame aligns exactly with its masks."""
        height, width = frame.shape[:2]
        objs = []
        for o in result.get('objects', []):
            p = np.asarray(o.get('poly'), np.float32)
            if p.ndim != 2 or p.shape[0] < 3 or p.shape[1] != 2:
                continue
            objs.append((p.copy(), o.get('label'), int(o.get('sid',-1))))
        with self.lock:
            self.anchor = (_gray(frame), width, height)
            self.objects = objs
            self.anchor_time = time.monotonic()

    def _alignment(self, frame, now):
        with self.lock:
            anchor, objs, age = self.anchor, self.objects, now-self.anchor_time
        if anchor is None or age > self.max_age:
            return [], (0.0,0.0), 'Waiting for fresh AI masks'
        source_gray, source_w, source_h = anchor
        h,w = frame.shape[:2]
        if w != source_w or h != source_h:
            return [], (0.0,0.0), 'Camera resolution changed — reacquiring'
        try:
            delta, response = cv2.phaseCorrelate(source_gray, _gray(frame), self._window)
        except cv2.error:
            return [], (0.0,0.0), 'Motion alignment unavailable'
        dx = float(delta[0]) * w/320.
        dy = float(delta[1]) * h/180.
        if not np.isfinite(dx+dy) or response < self.response_min or abs(dx) > w*.32 or abs(dy) > h*.32:
            return [], (0.0,0.0), 'Motion uncertain — masks hidden'
        return objs, (dx,dy), 'Flow-aligned masks (estimated between AI frames)'

    def render(self, frame):
        """The BASE IMAGE is always the newest camera frame, never an old AI image."""
        now = time.monotonic()
        h,w = frame.shape[:2]
        objs, (dx,dy), status = self._alignment(frame, now)
        base = frame.copy()
        overlay = frame.copy()
        mask = np.zeros((h,w), dtype=np.uint8)
        contours=[]
        for poly,label,sid in objs[:200]:
            if label is None:
                continue
            pts = poly + np.array((dx,dy),np.float32)
            points = np.rint(pts).astype(np.int32)
            if len(points) < 3:
                continue
            colour_rgb = PALETTE.get(label,(170,170,170))
            bgr = colour_rgb[::-1]
            cv2.fillPoly(overlay,[points],bgr)
            cv2.fillPoly(mask,[points],255)
            contours.append((points,bgr))
        if contours:
            mixed = cv2.addWeighted(base,.60,overlay,.40,0)
            base[mask>0]=mixed[mask>0]
            for pts,colour in contours:
                cv2.polylines(base,[pts],True,colour,1,cv2.LINE_AA)
        # Counting line is display-only. No counting is done on projected masks.
        if os.getenv('BIKA_LIVE_SHOW_COUNT_LINE','0') == '1':
            if self.direction in ('rtl','ltr'):
                x=int(w*(1-self.line if self.direction=='rtl' else self.line))
                cv2.line(base,(x,0),(x,h),(0,226,244),1)
            elif self.direction in ('ttb','btt'):
                y=int(h*(1-self.line if self.direction=='btt' else self.line))
                cv2.line(base,(0,y),(w,y),(0,226,244),1)
        cv2.rectangle(base,(0,0),(min(w,650),28),(20,23,29),-1)
        label = ('LIVE MASK · MOTION-ALIGNED' if contours else 'LIVE CAMERA · REACQUIRING MASKS')
        cv2.putText(base,label,(9,19),cv2.FONT_HERSHEY_SIMPLEX,.50,(245,245,245),1,cv2.LINE_AA)
        self.mask_status=status
        return base, bool(contours)

    def loop(self,camera,stopped):
        last_seq = None
        before = 0.0
        interval=1.0/self.target_fps
        while not stopped.is_set():
            if camera.status().get('state') != 'online':
                stopped.wait(.05)
                continue
            started=time.monotonic()
            # Newer Camo provides raw 30 FPS frames; existing Hikvision/Camo
            # uses camera.latest() JPEG as an equally safe fallback.
            raw=getattr(camera, 'latest_raw',None)
            if callable(raw):
                seq,frame,_ = raw()
            else:
                seq,jpg=camera.latest()
                frame=cv2.imdecode(np.frombuffer(jpg,np.uint8),cv2.IMREAD_COLOR) if jpg is not None else None
            if frame is None or seq==last_seq:
                stopped.wait(.01)
                continue
            last_seq=seq
            canvas,_=self.render(frame)
            ok,encoded=cv2.imencode('.jpg',canvas,[cv2.IMWRITE_JPEG_QUALITY,72])
            if ok:
                with self.state.lock:
                    if self.generation != self.state.generation or stopped.is_set():
                        return
                    # The visual stream updates independently of AI detections.
                    self.state.jpeg=encoded.tobytes()
                    self.state.jpeg_sequence+=1
                    self.state.live_mask_mode=self.mask_status
                    self.state.live_display_fps=self.fps
            self.frames_rendered+=1
            if before:
                instant=1/max(.001,started-before)
                self.fps=instant if not self.fps else .80*self.fps+.20*instant
            before=started
            stopped.wait(max(0.,interval-(time.monotonic()-started)))
