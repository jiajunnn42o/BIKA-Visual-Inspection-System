"""Read-only unified Image + Video + Live *estimated* inspection totals.

Use consistent sums for Dashboard and Analytics without writing to model data.
Video/Live track counts are provisional, not proven physically unique products.
SPC control limits remain on judged (official) image records only.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from flask import current_app
from app.extensions import db
from app.models.inspection_batch import InspectionBatch

CLASSES = ('normal', 'too_dark', 'too_short', 'bent_snack', 'fractured')
MY = timezone(timedelta(hours=8))


def _integer(value):
    if isinstance(value, bool):
        return None
    try:
        x = int(value)
        return x if x >= 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def _day(value, localize=False):
    if value is None:
        return None
    try:
        d = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if localize:
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            d = d.astimezone(MY)
        return d.date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _pct(n, d):
    return round(n * 100 / d, 1) if d else None


def _valid(good, bad, total):
    g, b, t = (_integer(good), _integer(bad), _integer(total))
    return None if None in (g, b, t) or t <= 0 or g + b != t else (g, b, t)


def summarize_rows(rows, target=85):
    """Pure aggregator, one independent row per saved run. Never imputes missing GOOD."""
    days = defaultdict(lambda: {'runs':0,'complete_runs':0,'incomplete_live':0,
                                'good':0,'bad':0,'total':0,'passing':0,
                                'classes':{k:0 for k in CLASSES}})
    for row in rows:
        day = row.get('date')
        if not day:
            continue
        d = days[day]
        d['runs'] += 1
        valid = _valid(row.get('good'), row.get('bad'), row.get('total'))
        if valid is None:
            if row.get('source') == 'live':
                d['incomplete_live'] += 1
            continue
        good, bad, total = valid
        d['good'] += good
        d['bad'] += bad
        d['total'] += total
        d['complete_runs'] += 1
        if 100 * good >= float(target) * total:
            d['passing'] += 1
        counts = row.get('classes') or {}
        if _integer(counts.get('normal')) != good or sum((_integer(counts.get(c)) or 0) for c in CLASSES if c != 'normal') != bad:
            # Don't invent a breakdown when source's classes aren't reconciled.
            counts = {'normal': good}
        for key in CLASSES:
            d['classes'][key] += _integer(counts.get(key)) or 0
    out = []
    for day, r in sorted(days.items()):
        r = dict(r)
        r['date'] = day
        r['good_rate'] = _pct(r['good'], r['total'])
        r['defect_rate'] = _pct(r['bad'], r['total'])
        out.append(r)
    total = {'runs':sum(r['runs'] for r in out), 'complete_runs':sum(r['complete_runs'] for r in out),
             'incomplete_live':sum(r['incomplete_live'] for r in out),
             'good':sum(r['good'] for r in out), 'bad':sum(r['bad'] for r in out),
             'total':sum(r['total'] for r in out), 'passing':sum(r['passing'] for r in out),
             'classes':{c:sum(r['classes'][c] for r in out) for c in CLASSES}}
    total['good_rate'] = _pct(total['good'], total['total'])
    total['defect_rate'] = _pct(total['bad'], total['total'])
    total['pass_rate'] = _pct(total['passing'], total['complete_runs'])
    return {'daily':out,'total':total}


def _load_rows(owner_id, lo=None, hi=None):
    results = []
    # Image + saved Video belong to the same InspectionBatch database as Reports.
    records = db.session.scalars(db.select(InspectionBatch).order_by(InspectionBatch.inspection_date.desc())).all()
    for rec in records:
        source = str(rec.source_type or 'image').lower()
        if source not in ('image', 'video'):
            continue
        day = _day(rec.inspection_date or rec.created_at)
        if day is None or (lo and day < lo) or (hi and day > hi):
            continue
        sm = rec.summary_json or {}
        if source == 'video' and sm.get('_bika_provisional_video'):
            counts = sm.get('observation_counts') or {}
            good = counts.get('normal')
            bad = sm.get('observation_defects')
            total = sm.get('observation_total')
        else:
            counts = rec.classes_json or {}
            total, good = sm.get('judged'), sm.get('normal')
            bad = (int(total) - int(good)) if _integer(total) is not None and _integer(good) is not None else None
        results.append({'source':source,'date':day,'good':good,'bad':bad,'total':total,'classes':counts})

    # Do not re-add Video from another source; Live is a distinct saved session.
    path = Path(current_app.instance_path) / 'live_session_history.sqlite3'
    if not path.is_file():
        return results
    conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=4)
    conn.row_factory = sqlite3.Row
    try:
        columns = {r[1] for r in conn.execute('PRAGMA table_info(live_session_history)')}
        necessary = {'session_id','owner_id','started_at'}
        if not necessary <= columns:
            return results
        estimates = {'estimated_total','estimated_good','estimated_bad'} <= columns
        fields = 'session_id,started_at' + (',estimated_total,estimated_good,estimated_bad' if estimates else '')
        sessions = conn.execute(f'SELECT {fields} FROM live_session_history WHERE owner_id=? ORDER BY started_at DESC',
                                (str(owner_id),)).fetchall()
        for s in sessions:
            day = _day(s['started_at'], localize=True)
            if day is None or (lo and day < lo) or (hi and day > hi):
                continue
            if estimates:
                classes = {'normal':s['estimated_good']}
                # Defect events can be sampled differently from classified-track totals:
                # only use a breakdown if it sums exactly to estimated_bad.
                try:
                    detail = conn.execute('SELECT label,COUNT(*) FROM live_observation_history WHERE session_id=? GROUP BY label',(s['session_id'],)).fetchall()
                    for label, n in detail:
                        k = str(label or '').lower().replace(' ','_').replace('-','_')
                        if k in CLASSES and k != 'normal':
                            classes[k] = classes.get(k,0) + n
                except sqlite3.OperationalError:
                    pass
                results.append({'source':'live','date':day,'total':s['estimated_total'],
                                'good':s['estimated_good'],'bad':s['estimated_bad'],'classes':classes})
            else:
                results.append({'source':'live','date':day,'total':None,'good':None,'bad':None,'classes':{}})
    finally:
        conn.close()
    return results


def _analytics_range(data):
    f = data.get('filter') or {}
    return f.get('from') or None, f.get('to') or None


def _set_source_counts(data, owner_id, lo, hi, dashboard=False):
    target = (data.get('targets') or {}).get('yield_percent',85) if dashboard else (data.get('kpi') or {}).get('target_good',85)
    result = summarize_rows(_load_rows(owner_id, lo, hi), target)
    return result


def merge_analytics_data(data, owner_id):
    lo, hi = _analytics_range(data)
    result = _set_source_counts(data,owner_id,lo,hi)
    grand = result['total']
    k = data['kpi']
    data['official_trend'] = [dict(row) for row in (data.get('trend') or [])]
    data['official_kpi'] = dict(k)
    k.update(inspections=grand['runs'], judged=grand['total'], normal=grand['good'], defects=grand['bad'],
             good_rate=grand['good_rate'], defect_rate=grand['defect_rate'],
             meeting_standard_count=grand['passing'], meeting_standard_rate=grand['pass_rate'],
             incomplete_live_sessions=grand['incomplete_live'])
    data['combined_trend'] = [dict(date=r['date'],judged=r['total'],normal=r['good'],defect=r['bad'],
                                  yield_rate=r['good_rate'],defect_rate=r['defect_rate'],
                                  rolling_yield=None,lcl=None,ucl=None,inspections=r['runs'],
                                  incomplete_live=r['incomplete_live']) for r in result['daily']]
    # Preserve the original weighted 7-observed-day rolling display, now based
    # on the same combined daily counts. Official SPC stays unmodified.
    for idx, point in enumerate(data['combined_trend']):
        previous = data['combined_trend'][max(0, idx-6):idx+1]
        point['rolling_yield'] = _pct(sum(v['normal'] for v in previous),
                                      sum(v['judged'] for v in previous))
    # SPC uses official_trend; other chart modes use this fully aggregated trend.
    # Keep Bayesian, SPC, heatmap and forecasting on their original data basis.
    k['combined_basis'] = 'estimated_tracks_and_judged'
    data['combined_note'] = ('Image judged + Video estimated + Live estimated counts. '
                             f"{grand['incomplete_live']} older Live session(s) lack GOOD/Total and are excluded from numerical output." )
    data['note'] = ((data.get('note') or '').strip() + ' ' + data['combined_note']).strip()
    # Do not misrepresent class breakdown if some sessions have incomplete classes.
    for item in data.get('defects') or []:
        key = item.get('key')
        if key in CLASSES:
            item['count'] = grand['classes'].get(key,0)
            item['percent'] = _pct(item['count'],grand['bad'])
    return data


def merge_dashboard_data(data, owner_id, range_key='all', custom_from=None,custom_to=None):
    f = data.get('filter') or {}
    lo, hi = (None,None) if range_key == 'all' else (f.get('from') or None, f.get('to') or None)
    grand_data = _set_source_counts(data,owner_id,lo,hi,dashboard=True)
    grand = grand_data['total']
    k = data['kpi']
    data['official_kpi'] = dict(k)
    goal = float((data.get('targets') or {}).get('yield_percent') or 85)
    defect_goal = float((data.get('targets') or {}).get('defect_percent') or 15)
    pass_goal = float((data.get('targets') or {}).get('batch_pass_percent') or 80)
    good_pct = grand['good_rate']
    bad_pct = grand['defect_rate']
    passing_pct = grand['pass_rate']
    k.update(total_batches=grand['runs'], total_products=grand['total'], normal=grand['good'], defect=grand['bad'],
             yield_percent=good_pct,defect_percent=bad_pct,
             batch_pass_count=grand['passing'],batch_pass_percent=passing_pct,
             yield_gap=round(good_pct-goal,1) if good_pct is not None else None,
             defect_gap=round(bad_pct-defect_goal,1) if bad_pct is not None else None,
             batch_pass_gap=round(passing_pct-pass_goal,1) if passing_pct is not None else None,
             incomplete_live_sessions=grand['incomplete_live'])
    for c in data.get('composition') or []:
        label = c.get('key')
        if label in CLASSES:
            c['count'] = grand['classes'].get(label,0)
            c['percent'] = _pct(c['count'],grand['total']) or 0
    data['trend'] = [dict(date=r['date'],label=datetime.fromisoformat(r['date']).strftime('%d %b'),
                          batches=r['runs'],judged=r['total'],yield_percent=r['good_rate'],
                          defect_percent=r['defect_rate']) for r in grand_data['daily'] if r['total']]
    cum = data.get('cumulative') or {}
    cum['average_products_per_batch'] = round(grand['total']/grand['complete_runs'],1) if grand['complete_runs'] else 0
    data['cumulative'] = cum
    fmt=lambda x: f'{int(x):,}'
    if good_pct is None:
        data['summary_sentence']='No complete Image / Video / Live quality totals recorded in the selected period.'
    else:
        note = f" {grand['incomplete_live']} older Live session(s) lack complete totals." if grand['incomplete_live'] else ''
        data['summary_sentence']=(f"Across {fmt(grand['runs'])} Image / Video / Live sessions and "
                                   f"{fmt(grand['total'])} combined judged/estimated classifications, "
                                   f"the provisional good snack rate is {good_pct:.1f}%.{note}")
    data['combined_basis']='provisional_mixed_sources'
    return data
