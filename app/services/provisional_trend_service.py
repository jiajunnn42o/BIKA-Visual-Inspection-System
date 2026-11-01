"""Read-only mixed-source *provisional* trend/report-review adapter.

Official judged/SPC values are never modified. Image/Video share InspectionBatch;
Live remains in its own per-user SQLite journal. Dates are Malaysia local dates.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from app.extensions import db
from app.models.inspection_batch import InspectionBatch
from app.services.live_analytics_service import _bounds

MY = ZoneInfo('Asia/Kuala_Lumpur')


def _local(instant):
    if isinstance(instant, datetime):
        ts = instant
    else:
        ts = datetime.fromisoformat(str(instant).replace('Z', '+00:00'))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(MY).date()


def _n(value):
    try:
        v = int(value)
        return v if v >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _add(bucket, good, bad, total):
    g, b, t = _n(good), _n(bad), _n(total)
    if None in (g, b, t) or t <= 0 or g + b != t:
        return False
    bucket['good'] += g
    bucket['bad'] += b
    bucket['total'] += t
    return True


def _within(day, lo, hi):
    return (lo is None or day >= lo) and (hi is None or day <= hi)


def build_provisional_views(instance_path, owner_id, *, range_key='30d', date_from=None, date_to=None, include_review=False):
    low, high = _bounds(range_key, date_from, date_to)
    daily = defaultdict(lambda: {'video': {'good': 0, 'bad': 0, 'total': 0, 'runs': 0},
                                  'live': {'good': 0, 'bad': 0, 'total': 0, 'runs': 0}})
    reviews = []
    records = db.session.scalars(db.select(InspectionBatch).where(InspectionBatch.source_type == 'video')
                                  .order_by(InspectionBatch.inspection_date.desc()).limit(1500)).all()
    for rec in records:
        try:
            day = _local(rec.inspection_date)
        except (ValueError, TypeError):
            continue
        if not _within(day, low, high):
            continue
        sm = rec.summary_json or {}
        if not sm.get('_bika_provisional_video'):
            continue
        observed = sm.get('observation_counts') or {}
        good = observed.get('normal')
        bad = sm.get('observation_defects')
        total = sm.get('observation_total')
        bkt = daily[day.isoformat()]['video']
        bkt['runs'] += 1
        eligible = _add(bkt, good, bad, total)
        if include_review:
            reviews.append({'batch_id':rec.batch_id, 'file_name':rec.original_filename or 'Video Inspection',
                'source_type':'video', 'date':day.isoformat(), 'model_version':rec.model_version,
                'judged':_n(total) or 0,
                'reasons':['Provisional track counts · physical uniqueness not validated'] if eligible
                          else ['Incomplete provisional counts · review output'],
                'reviewed':0,'preview_url':None,'reviewable':False})

    path = Path(instance_path) / 'live_session_history.sqlite3'
    if path.is_file():
        conn = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            cols = {r[1] for r in conn.execute('PRAGMA table_info(live_session_history)')}
            extra = ',estimated_total,estimated_good,estimated_bad' if {'estimated_total','estimated_good','estimated_bad'} <= cols else ''
            rows = conn.execute('SELECT session_id,started_at,status,ai_frames,event_count'+extra+
                ' FROM live_session_history WHERE owner_id=? ORDER BY started_at DESC LIMIT 1500',
                (str(owner_id),)).fetchall()
            for r in rows:
                try:
                    day = _local(r['started_at'])
                except (ValueError, TypeError):
                    continue
                if not _within(day, low, high):
                    continue
                bkt = daily[day.isoformat()]['live']
                bkt['runs'] += 1
                available = bool(extra) and _add(bkt, r['estimated_good'],r['estimated_bad'],r['estimated_total'])
                if include_review:
                    reviews.append({'batch_id':'live:'+str(r['session_id']),
                        'file_name':'Live · Camo Camera', 'source_type':'live','date':day.isoformat(),
                        'model_version':'Realtime YOLO + v4',
                        'judged':_n(r['estimated_total']) if available else (_n(r['event_count']) or 0),
                        'reasons':['Provisional track counts · physical uniqueness not validated'] if available
                                   else ['Live observations · complete GOOD / Total not recorded'],
                        'reviewed':0,'preview_url':None,'reviewable':False})
        finally:
            conn.close()
    result=[]
    for date_key,both in sorted(daily.items()):
        item={'date':date_key}
        for name in ('video','live'):
            bkt=both[name]
            item[f'{name}_runs']=bkt['runs']
            item[f'{name}_total']=bkt['total']
            item[f'{name}_good_rate']=round(100*bkt['good']/bkt['total'],1) if bkt['total'] else None
            item[f'{name}_defect_rate']=round(100*bkt['bad']/bkt['total'],1) if bkt['total'] else None
        result.append(item)
    reviews.sort(key=lambda r:(r['date'],r['batch_id']), reverse=True)
    return {'daily':result[-90:], 'recent_runs':reviews[:40] if include_review else [],
            'note':'Provisional Video/Live estimates are excluded from official SPC control limits.'}
