"""Motion-gated, hysteresis line counter for BIKA's right-to-left conveyor.

Research-only: not a proof of unique physical objects. Counted event IDs are
StableTracks IDs. A reset/reassigned ID can still be a duplicate object.
Dependencies: Python standard library only.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from math import isfinite
from statistics import median


@dataclass
class _TrackMotion:
    positions: deque = field(default_factory=lambda: deque(maxlen=12))
    armed: bool = False
    emitted: bool = False


class MotionGatedCounter:
    """Coordinate is direction-normalized progress 0->1 along conveyor.

    A count requires: seen before line - band; center reaches line + band;
    confirmed track; valid class; directional movement on >=N recent frame
    transitions; and (optionally) conveyor-wide median motion active.
    """
    def __init__(self, direction='rtl', position=.75, width=832, height=464,
                 hysteresis_px=8., min_motion_px=12., min_step_px=1.5,
                 min_direction_steps=3, motion_window=8,
                 scene_gate=True, scene_speed_px=2., scene_confirm_frames=2,
                 min_scene_pairs=10):
        if direction not in ('ltr','rtl','ttb','btt'):
            raise ValueError('Invalid direction')
        if not (0.05 < position < 0.95):
            raise ValueError('Invalid counting line')
        if hysteresis_px < 0 or min_motion_px < 0:
            raise ValueError('Pixel distances cannot be negative')
        if not 1 <= min_direction_steps <= motion_window:
            raise ValueError('min_direction_steps must fit motion_window')
        self.direction = direction
        self.position = float(position)
        self.span = float(width if direction in ('ltr','rtl') else height)
        if self.span <= 0: raise ValueError('Invalid image span')
        self.hysteresis = hysteresis_px / self.span
        self.min_motion_px = float(min_motion_px)
        self.min_step_px = float(min_step_px)
        self.min_direction_steps = int(min_direction_steps)
        self.motion_window = int(motion_window)
        self.scene_gate = bool(scene_gate)
        self.scene_speed_px = float(scene_speed_px)
        self.scene_confirm_frames = max(1,int(scene_confirm_frames))
        self.min_scene_pairs = max(1,int(min_scene_pairs))
        self.states: dict[int,_TrackMotion] = {}
        self.counted: set[int] = set()
        self._previous = {}
        self._latest = {}
        self._frame = 0
        self.scene_streak = 0
        self.scene_speed = 0.
        self.scene_active = False
        self.stats = Counter()

    def coordinate(self, box, width=None, height=None):
        cx=(float(box[0])+float(box[2]))/2.
        cy=(float(box[1])+float(box[3]))/2.
        width = float(width) if width else self.span
        height = float(height) if height else self.span
        if self.direction=='ltr': return cx / width
        if self.direction=='rtl': return 1.-cx / width
        if self.direction=='ttb': return cy / height
        return 1.-cy / height

    def observe_frame(self, frame_index, objects, width, height):
        """Call exactly once per video frame, BEFORE update().

        objects: tracker output tuples whose box is at [1] and sid is [3].
        A shared motion gate refuses conveyor-stationary jitter counts.
        """
        if frame_index <= self._frame:
            raise ValueError('frame_index must increase')
        self._frame=int(frame_index)
        now={}
        velocities=[]
        for obj in objects:
            sid=int(obj[3]); coord=self.coordinate(obj[1],width,height)
            if not isfinite(coord): continue
            now[sid]=(self._frame,coord)
            last=self._previous.get(sid)
            if last and self._frame-last[0]==1:
                velocities.append((coord-last[1])*self.span)
        self.scene_speed=float(median(velocities)) if len(velocities)>=self.min_scene_pairs else 0.
        moving=len(velocities)>=self.min_scene_pairs and self.scene_speed>=self.scene_speed_px
        self.scene_streak = self.scene_streak+1 if moving else 0
        self.scene_active = (not self.scene_gate) or self.scene_streak>=self.scene_confirm_frames
        self._previous=now
        self._latest=now
        self.stats['observed_frames']+=1
        if self.scene_active: self.stats['scene_active_frames']+=1

    def _strong_forward_motion(self, positions):
        # Insist on consecutive observations, so an ID jumping across the
        # counting line after occlusion is NOT counted as genuine motion.
        deltas=[]
        for (fa,pa),(fb,pb) in zip(positions, list(positions)[1:]):
            if fb-fa!=1:
                deltas=[]
            else:
                deltas.append((pb-pa)*self.span)
        deltas=deltas[-self.motion_window:]
        if not deltas: return False, 0., 0
        count_good=sum(d>=self.min_step_px for d in deltas)
        count_reverse=sum(d<=-self.min_step_px for d in deltas)
        total=sum(deltas)
        ok=(count_good>=self.min_direction_steps and
            count_reverse<=1 and total>=self.min_motion_px)
        return ok,float(total),int(count_good)

    def update(self, sid, confirmed, label, confidence, tracker, min_prob):
        sid=int(sid)
        current=self._latest.get(sid)
        if current is None:
            return False
        st=self.states.setdefault(sid,_TrackMotion())
        frame,coord=current
        if st.positions and frame-st.positions[-1][0]>2:
            # Long dropouts can produce apparent line crossing by teleportation.
            st.positions.clear()
            st.armed=False
        if not st.positions or frame>st.positions[-1][0]:
            st.positions.append((frame,coord))
        if coord <= self.position - self.hysteresis:
            st.armed=True
        if sid in self.counted or st.emitted or not st.armed:
            return False
        if coord < self.position + self.hysteresis:
            return False
        if not self.scene_active:
            self.stats['blocked_scene_motion']+=1
            return False
        is_moving, forward_px, good_steps = self._strong_forward_motion(st.positions)
        if not is_moving:
            self.stats['blocked_track_motion']+=1
            return False
        if not confirmed or label is None or confidence is None or confidence < min_prob:
            self.stats['blocked_unconfirmed_or_class']+=1
            return False
        if not tracker.emit_once(sid):
            return False
        st.emitted=True
        self.counted.add(sid)
        self.stats['counted']+=1
        self.last_event={'sid':sid,'frame':frame,'progress':coord,
                         'track_forward_px':round(forward_px,2),
                         'forward_steps':good_steps,
                         'scene_speed_px':round(self.scene_speed,2)}
        return True

    def prune(self, active_sids):
        """Optional RAM cleanup. Preserve counted IDs and tracker once-gate."""
        active=set(active_sids)
        self.states={sid:s for sid,s in self.states.items() if sid in active}
