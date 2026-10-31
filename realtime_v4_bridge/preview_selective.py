"""BIKA read-only track-selective video benchmark. No Website/database writes."""
from __future__ import annotations
import argparse
import csv
import sys
import time
from pathlib import Path
from statistics import mean
import cv2
import numpy as np
from ultralytics import YOLO

from v4_selective_adapter import SelectiveV4Adapter
from tracking import StableTracks
from counting import LineCounter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def choose_indices(objects, cache, last_classified, frame_i, quota, refresh_gap,
                   threshold, direction, width, height, refresh_quota):
    """Prioritize new near-exit tracks, then a bounded number of uncertain refreshes."""
    axis = 0 if direction in ('ltr', 'rtl') else 1
    span = width if axis == 0 else height
    def progress(obj):
        box = obj[1]
        coord = (box[axis]+box[axis+2])*0.5/span
        return 1-coord if direction in ('rtl', 'btt') else coord
    new = [i for i,o in enumerate(objects) if o[3] not in cache]
    # Prioritize tracks nearing exit line. Very crowded first frame will
    # generate a pending queue; low-latency first-frame classification for all
    # 150+ visible objects is physically impossible with this slow classifier.
    new.sort(key=lambda i: (progress(objects[i]), objects[i][2]), reverse=True)
    chosen = new[:quota]
    remaining = quota - len(chosen)
    if remaining > 0 and refresh_gap > 0:
        uncertain = [i for i,o in enumerate(objects)
                     if o[3] in cache and cache[o[3]][1] < threshold
                     and frame_i-last_classified.get(o[3],frame_i) >= refresh_gap]
        uncertain.sort(key=lambda i: progress(objects[i]), reverse=True)
        chosen.extend(uncertain[:min(remaining, refresh_quota)])
    return chosen, max(0, len(new)-sum(i in set(chosen) for i in new))


def run():
    ap = argparse.ArgumentParser(description='Track based selective v4 classification. Research only.')
    ap.add_argument('--source', required=True)
    ap.add_argument('--device', default='0')
    ap.add_argument('--imgsz', type=int, default=640)
    ap.add_argument('--conf', type=float, default=0.25)
    ap.add_argument('--max-det', type=int, default=200)
    ap.add_argument('--max-frames', type=int, default=100)
    ap.add_argument('--classify-per-frame', type=int, default=8)
    ap.add_argument('--refresh-every', type=int, default=12)
    ap.add_argument('--refresh-quota', type=int, default=2)
    ap.add_argument('--uncertain-below', type=float, default=.65)
    ap.add_argument('--min-hits', type=int, default=3)
    ap.add_argument('--min-prob', type=float, default=.50)
    ap.add_argument('--direction', choices=['ltr','rtl','ttb','btt'], default='ltr')
    ap.add_argument('--line', type=float, default=.75)
    ap.add_argument('--no-display', action='store_true')
    ap.add_argument('--output', type=Path, default=HERE/'events_selective.csv')
    args = ap.parse_args()
    if not (1 <= args.classify_per_frame <= 100): ap.error('classify-per-frame must be 1..100')
    if not (0 <= args.refresh_quota <= args.classify_per_frame): ap.error('refresh-quota out of range')
    if not (0 <= args.refresh_every <= 10000): ap.error('refresh-every out of range')
    if not (.05 < args.line < .95): ap.error('line must be .05..95')
    weights = ROOT/'lightweight_quickstart'/'runs'/'prawn_tiles_v2'/'weights'/'best.pt'
    if not weights.is_file(): ap.error(f'Weights missing: {weights}')
    print('Loading YOLO11n-Seg + track-selective v4; no SAM3, no Website writes', flush=True)
    yolo = YOLO(str(weights))
    if yolo.task != 'segment' or len(yolo.names) != 1:
        ap.error('Expected one-class segmentation checkpoint')
    model = SelectiveV4Adapter(ROOT, args.device)
    tracker = StableTracks(min_hits=args.min_hits, lost_frames=28, reid_iou=.5)
    counter = LineCounter(direction=args.direction, position=args.line)
    cap_source = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(cap_source, cv2.CAP_DSHOW) if isinstance(cap_source,int) and sys.platform=='win32' else cv2.VideoCapture(cap_source)
    if not cap.isOpened(): ap.error(f'Cannot open source: {args.source}')
    args.output.parent.mkdir(exist_ok=True, parents=True)
    cache, last_seen, last_classified = {}, {}, {}
    stats = []
    frame_i = 0
    begun = time.perf_counter()
    try:
        with args.output.open('w', newline='', encoding='utf-8-sig') as out:
            writer = csv.DictWriter(out, fieldnames=['frame','sid','raw_id','label','confidence'])
            writer.writeheader()
            while True:
                ok, frame = cap.read()
                if not ok: break
                frame_i += 1
                t0 = time.perf_counter()
                result = yolo.track(frame, persist=True,
                                    tracker=str(HERE/'bytetrack_bika.yaml'),
                                    device=args.device, imgsz=args.imgsz,
                                    conf=args.conf, max_det=args.max_det,
                                    iou=.5, verbose=False)[0]
                objects=[]
                if result.boxes is not None and result.masks is not None and result.boxes.id is not None:
                    b=result.boxes.xyxy.cpu().numpy()
                    rid=result.boxes.id.int().cpu().numpy()
                    scores=result.boxes.conf.cpu().numpy()
                    polys=result.masks.xy
                    n=min(len(b),len(rid),len(scores),len(polys))
                    obs=[(int(rid[j]),b[j],float(scores[j])) for j in range(n)]
                    stable=tracker.update(obs,frame_i)
                    objects=[(*stable[j],polys[j]) for j in range(n)]
                else:
                    tracker.update([],frame_i)
                t1=time.perf_counter()
                for o in objects:
                    last_seen[o[3]]=frame_i
                h,w=frame.shape[:2]
                selected,pending=choose_indices(objects,cache,last_classified,frame_i,
                                               args.classify_per_frame,args.refresh_every,
                                               args.uncertain_below,args.direction,w,h,
                                               args.refresh_quota)
                if selected:
                    new_results=model.predict_selected(frame,[o[6] for o in objects],
                                                       [o[3] for o in objects],selected)
                    for idx,pred in new_results.items():
                        sid=objects[idx][3]
                        cache[sid]=pred
                        last_classified[sid]=frame_i
                t2=time.perf_counter()
                counted=0
                for o in objects:
                    raw, box, det_conf, sid, confirmed, just_confirmed, poly = o
                    pred=cache.get(sid)
                    if pred is None: continue
                    label, conf, probs=pred
                    if counter.update(sid,counter.coordinate(box,w,h),confirmed,label,conf,tracker,args.min_prob):
                        counted+=1
                        writer.writerow({'frame':frame_i,'sid':sid,'raw_id':raw,
                                         'label':label,'confidence':f'{conf:.4f}'})
                t3=time.perf_counter()
                if not args.no_display:
                    rendered=frame.copy()
                    if args.direction in ('ltr','rtl'):
                        x=int(w*(args.line if args.direction=='ltr' else 1-args.line))
                        cv2.line(rendered,(x,0),(x,h),(0,240,255),2)
                    else:
                        y=int(h*(args.line if args.direction=='ttb' else 1-args.line))
                        cv2.line(rendered,(0,y),(w,y),(0,240,255),2)
                    cv2.rectangle(rendered,(0,0),(min(920,w),76),(20,20,20),-1)
                    cv2.putText(rendered,f'Selective v4 | frame {frame_i} | visible {len(objects)} | pending {pending}',
                                (12,25),cv2.FONT_HERSHEY_SIMPLEX,.52,(255,255,255),1,cv2.LINE_AA)
                    cv2.putText(rendered,f'Selected for classification {len(selected)} max {args.classify_per_frame} | Counted {len(counter.counted)} (unverified)',
                                (12,50),cv2.FONT_HERSHEY_SIMPLEX,.52,(255,255,255),1,cv2.LINE_AA)
                    cv2.imshow('BIKA Selective v4 EXPERIMENT',rendered)
                    key=cv2.waitKey(1)&0xff
                else: key=-1
                t4=time.perf_counter()
                stats.append(((t1-t0)*1000,(t2-t1)*1000,(t4-t0)*1000,len(selected),pending))
                if frame_i % 20 == 0:
                    part=stats[-20:]
                    print(f'Frame={frame_i} SEG+TRACK={mean(row[0] for row in part):.0f}ms '
                          f'v4-SELECTIVE={mean(row[1] for row in part):.0f}ms '
                          f'TOTAL={mean(row[2] for row in part):.0f}ms '
                          f'FPS={1000/max(mean(row[2] for row in part),1):.2f} '
                          f'visible={len(objects)} pending={pending} '
                          f'classified_in_window={sum(row[3] for row in part)} '
                          f'confirmed_IDs={len(tracker.confirmed_ids)}',flush=True)
                if frame_i % 60 == 0:
                    active=set(tracker.tracks)
                    model.prune(active)
                    cache={sid:v for sid,v in cache.items() if sid in active}
                    last_classified={sid:v for sid,v in last_classified.items() if sid in active}
                    last_seen={sid:v for sid,v in last_seen.items() if sid in active}
                if key in (ord('q'),27): break
                if args.max_frames and frame_i>=args.max_frames: break
    finally:
        cap.release()
        if not args.no_display: cv2.destroyAllWindows()
    elapsed=time.perf_counter()-begun
    print(f'Finished frames={frame_i} elapsed={elapsed:.1f}s wall FPS={frame_i/max(elapsed,.001):.2f}')
    if stats:
        print(f'AVG SEG+TRACK={mean(v[0] for v in stats):.0f}ms '
              f'v4-SELECTIVE={mean(v[1] for v in stats):.0f}ms '
              f'TOTAL={mean(v[2] for v in stats):.0f}ms '
              f'pending_final={stats[-1][4]} counted_unverified={len(counter.counted)}')
    print('WARNING: cached classes are provisional. Count once by Stable ID is NOT guaranteed once per physical biscuit.')
    print('WARNING: cached geometry scale is approximate; measure real-video F1 against original v4.')


if __name__=='__main__':
    run()
