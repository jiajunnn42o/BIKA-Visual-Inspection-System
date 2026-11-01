"""LIVE-only defect observation events. No line crossing; one event per stable ID.
Only confirmed classified defect tracks are recorded, with extra persistence.
Not a guaranteed unique-physical-product counter.
"""
from __future__ import annotations
import math


def iou(a,b):
    xa=max(float(a[0]),float(b[0]));ya=max(float(a[1]),float(b[1]))
    xb=min(float(a[2]),float(b[2]));yb=min(float(a[3]),float(b[3]))
    area=max(0,xb-xa)*max(0,yb-ya)
    sa=max(0,float(a[2])-float(a[0]))*max(0,float(a[3])-float(a[1]))
    sb=max(0,float(b[2])-float(b[0]))*max(0,float(b[3])-float(b[1]))
    return area/max(sa+sb-area,1e-9)


class LiveDefectObserver:
    def __init__(self, min_hits=2, min_class_conf=.55, min_det_conf=.35):
        self.min_hits=int(min_hits)
        self.min_class_conf=float(min_class_conf)
        self.min_det_conf=float(min_det_conf)
        self.hits={}
        self.seen=set()
        self.recent=[]
        self.event_count=0
        self.seen_class={}

    def observe(self, objects, now):
        new=[]
        for o in objects:
            if not o.get('confirmed'):continue
            sid=int(o['sid'])
            label=o.get('label')
            conf=o.get('confidence')
            det=o.get('det_conf')
            if label is not None and conf is not None:
                self.seen_class.setdefault(sid,label)
            if (label in (None,'normal') or conf is None or det is None
                    or not math.isfinite(float(conf)) or not math.isfinite(float(det))
                    or float(conf)<self.min_class_conf or float(det)<self.min_det_conf):
                self.hits.pop(sid,None)
                continue
            if sid in self.seen:continue
            old_label, count=self.hits.get(sid,(label,0))
            count=count+1 if old_label==label else 1
            self.hits[sid]=(label,count)
            if count<self.min_hits:continue
            self.seen.add(sid)
            # Conservative short-term ID fragmentation suppression; distinct
            # adjacent objects should not be merged merely by proximity.
            box=o.get('bbox')
            dupe=bool(box and any(lb==label and now-t<1.1 and iou(box,b)>0.82
                                  for t,lb,b in self.recent))
            if box:self.recent.append((now,label,tuple(box)))
            self.recent=[r for r in self.recent if now-r[0]<1.1]
            if dupe:continue
            self.event_count+=1
            new.append(o)
        return new
