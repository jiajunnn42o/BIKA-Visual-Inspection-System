"""CPU-only stable ID and once-per-object event gate for YOLO+ByteTrack.

Conservative re-identification for *temporarily* missing tracks. It cannot
promise unique physical identities after long occlusions or large movements.
No Torch, SAM3, Flask, or GPU allocations here.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import hypot


@dataclass
class StableTrack:
    stable_id: int
    box: tuple[float, float, float, float]
    last_frame: int
    hits: int = 1
    confirmed: bool = False


def box_iou(a, b):
    x0 = max(a[0], b[0]); y0 = max(a[1], b[1])
    x1 = min(a[2], b[2]); y1 = min(a[3], b[3])
    inter = max(0.0, x1-x0)*max(0.0, y1-y0)
    aa = max(0.0,a[2]-a[0])*max(0.0,a[3]-a[1])
    bb = max(0.0,b[2]-b[0])*max(0.0,b[3]-b[1])
    return inter / max(1e-9, aa + bb - inter)


def _similar(a, b, min_iou):
    if box_iou(a, b) < min_iou:
        return False
    wa,ha = max(1.0,a[2]-a[0]),max(1.0,a[3]-a[1])
    wb,hb = max(1.0,b[2]-b[0]),max(1.0,b[3]-b[1])
    if not (0.55 <= (wb*hb)/(wa*ha) <= 1.8):
        return False
    return hypot((a[0]+a[2]-b[0]-b[2])/2,(a[1]+a[3]-b[1]-b[3])/2) <= 0.45 * max(hypot(wa,ha),hypot(wb,hb))


def _plausible_raw_continuity(previous_box, current_box, age):
    """Guard against recycled/wrong raw tracker IDs jumping to a new object.

    ByteTrack IDs are useful but not infallible. Allow normal displacement,
    yet require compatible size and a finite movement bound. This is a safety
    guard, NOT long-term physical-object re-identification.
    """
    wa = max(1.0, previous_box[2]-previous_box[0])
    ha = max(1.0, previous_box[3]-previous_box[1])
    wb = max(1.0, current_box[2]-current_box[0])
    hb = max(1.0, current_box[3]-current_box[1])
    area_ratio = (wb * hb) / (wa * ha)
    if not (0.40 <= area_ratio <= 2.50):
        return False
    previous_center = ((previous_box[0]+previous_box[2])/2,
                       (previous_box[1]+previous_box[3])/2)
    current_center = ((current_box[0]+current_box[2])/2,
                      (current_box[1]+current_box[3])/2)
    displacement = hypot(current_center[0]-previous_center[0],
                         current_center[1]-previous_center[1])
    # Short gaps may allow more travel. Cap growth so a very old ID is not
    # silently attached to a completely different object after occlusion.
    scale = max(hypot(wa,ha), hypot(wb,hb))
    budget = 2.5 * scale * min(max(int(age), 1), 3)
    return displacement <= budget


class StableTracks:
    def __init__(self, min_hits=4, lost_frames=28, reid_iou=0.50):
        assert min_hits >= 1 and lost_frames >= 1 and 0 <= reid_iou <= 1
        self.min_hits=min_hits
        self.lost_frames=lost_frames
        self.reid_iou=reid_iou
        self.tracks: dict[int,StableTrack]={}
        self.raw_to_stable: dict[int,int]={}
        self.next_id=1
        self.confirmed_ids=set()
        self.event_emitted=set()
        self.recovered_switches=0

    def update(self, observations, frame_index):
        """observations: sequence of (raw_id, (x0,y0,x1,y1), confidence).

        Return list of (raw_id, bbox, conf, stable_id, is_confirmed, just_confirmed).
        Each stable ID may be associated to only one observation per frame.
        """
        obs=[]
        seen_raw=set()
        for raw,box,conf in observations:
            raw=int(raw)
            if raw in seen_raw:
                continue
            seen_raw.add(raw)
            obs.append((raw,tuple(float(v) for v in box),float(conf)))
        assigned={}
        occupied=set()
        # First preserve ByteTrack's existing mapping where it is still recent.
        for i,(raw,box,conf) in enumerate(obs):
            sid=self.raw_to_stable.get(raw)
            state=self.tracks.get(sid) if sid is not None else None
            age = frame_index-state.last_frame if state is not None else 0
            if (state and 1 <= age <= self.lost_frames+1
                    and sid not in occupied
                    and _plausible_raw_continuity(state.box, box, age)):
                assigned[i]=sid; occupied.add(sid)
        # Then recover recently-lost objects only if their boxes match strongly.
        # Sort candidates by overlap; do not allow two new tracks to steal one ID.
        pairs=[]
        for i,(raw,box,conf) in enumerate(obs):
            if i in assigned:
                continue
            for sid,state in self.tracks.items():
                age=frame_index-state.last_frame
                if sid in occupied or not (1 <= age <= self.lost_frames):
                    continue
                if _similar(state.box, box, self.reid_iou):
                    pairs.append((box_iou(state.box,box),i,sid))
        for _,i,sid in sorted(pairs,reverse=True):
            if i not in assigned and sid not in occupied:
                assigned[i]=sid; occupied.add(sid)
                raw=obs[i][0]
                if self.raw_to_stable.get(raw)!=sid:
                    self.recovered_switches+=1
        output=[]
        for i,(raw,box,conf) in enumerate(obs):
            sid=assigned.get(i)
            if sid is None:
                sid=self.next_id
                self.next_id+=1
                self.tracks[sid]=StableTrack(sid,box,frame_index)
            else:
                st=self.tracks[sid]
                # No duplicate hit count in a single frame.
                if frame_index>st.last_frame:
                    st.hits+=1
                st.box=box
                st.last_frame=frame_index
            self.raw_to_stable[raw]=sid
            st=self.tracks[sid]
            new_confirmed=False
            if not st.confirmed and st.hits>=self.min_hits:
                st.confirmed=True
                self.confirmed_ids.add(sid)
                new_confirmed=True
            output.append((raw,box,conf,sid,st.confirmed,new_confirmed))
        # Prune long-inactive tracks to avoid unbounded CPU RAM usage.
        # The confirmed ID set is retained as a count of session observations.
        if frame_index % 60 == 0:
            cutoff=frame_index-self.lost_frames-1
            self.tracks={
                sid:st for sid,st in self.tracks.items() if st.last_frame>=cutoff
            }
            self.raw_to_stable={raw:sid for raw,sid in self.raw_to_stable.items() if sid in self.tracks}
        return output

    def emit_once(self, stable_id):
        """Use only after confirmed tracking AND a separately validated defect class.
        Returns False for duplicates; does not itself assert a quality defect.
        """
        if stable_id not in self.confirmed_ids or stable_id in self.event_emitted:
            return False
        self.event_emitted.add(stable_id)
        return True
