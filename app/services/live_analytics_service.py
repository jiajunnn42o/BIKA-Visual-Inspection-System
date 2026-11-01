"""Read-only, per-user provisional Live Session statistics for Data Analytics.

The source is the separate SQLite Live history journal; no InspectionBatch joins
or modifications. Individual Track IDs are NOT verified unique physical snacks.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, time, timezone
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo('Asia/Kuala_Lumpur')
LABELS = ('Fractured', 'Too Dark', 'Too Short', 'Bent Snack')


def _local_date(iso):
    ts = datetime.fromisoformat(str(iso).replace('Z', '+00:00'))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(LOCAL_TZ).date()


def _bounds(range_key, begin, end):
    today = datetime.now(LOCAL_TZ).date()
    if range_key == 'all':
        return None, None
    if range_key in ('today', '7d', '30d', '90d'):
        days = {'today': 1, '7d': 7, '30d': 30, '90d': 90}[range_key]
        return today - timedelta(days=days - 1), today
    if range_key != 'custom':
        raise ValueError('Invalid period')
    if not begin or not end:
        raise ValueError('Custom period requires from and to dates')
    try:
        d1, d2 = date.fromisoformat(begin), date.fromisoformat(end)
    except (ValueError, TypeError) as exc:
        raise ValueError('Invalid custom dates') from exc
    if d1 > d2 or (d2 - d1).days > 3650:
        raise ValueError('Invalid custom date range')
    return d1, d2


def _category(value):
    value = str(value or '').strip().lower().replace('_', ' ').replace('-', ' ')
    return {'fractured': 'Fractured', 'too dark': 'Too Dark',
            'too short': 'Too Short', 'bent snack': 'Bent Snack'}.get(value, 'Other')


def build_live_analytics(instance_path, owner_id, *, range_key='30d', date_from=None, date_to=None):
    """Aggregate authenticated user's sessions by session start date (Malaysia time)."""
    low, high = _bounds(range_key, date_from, date_to)
    path = Path(instance_path) / 'live_session_history.sqlite3'
    empty = {'sessions': 0, 'ai_frames': 0, 'defect_observations': 0,
             'duration_seconds': 0.0, 'effective_fps': None,
             'classes': {key: 0 for key in LABELS}, 'other_observations': 0,
             'daily': [], 'recent_session': None, 'range': range_key,
             'note': 'Provisional Track ID observations; NOT verified unique products or official quality rates.'}
    if not path.is_file():
        return empty
    try:
        # Read-only connection prevents accidental changes to the existing history database.
        db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            sessions = db.execute('''SELECT session_id, started_at, ended_at, status,
                    ai_frames, duration_seconds, event_count, ai_fps
                    FROM live_session_history WHERE owner_id=? ORDER BY started_at DESC''',
                    (str(owner_id),)).fetchall()
            chosen = []
            for row in sessions:
                try:
                    day = _local_date(row['started_at'])
                except (ValueError, TypeError):
                    continue
                if (low is not None and not low <= day <= high):
                    continue
                chosen.append((row, day))
            if not chosen:
                return empty
            ids = [row['session_id'] for row, _ in chosen]
            # Query only session IDs from this user's session list. SQLite variable limit safe.
            by_class = Counter()
            for start in range(0, len(ids), 400):
                chunk = ids[start:start+400]
                placeholders = ','.join('?' for _ in chunk)
                rows = db.execute(f'''SELECT label, COUNT(*) AS n
                    FROM live_observation_history WHERE session_id IN ({placeholders})
                    GROUP BY label''', chunk).fetchall()
                for row in rows:
                    by_class[_category(row['label'])] += int(row['n'])
        finally:
            db.close()
    except sqlite3.Error:
        # Invalid existing DB should be surfaced, not silently treated as no data.
        raise
    frames = sum(max(0, int(row['ai_frames'] or 0)) for row, _ in chosen)
    duration = sum(max(0., float(row['duration_seconds'] or 0)) for row, _ in chosen)
    observed = sum(by_class.values())
    by_day = Counter(day.isoformat() for _,day in chosen)
    recent = chosen[0][0]
    return {
        'sessions': len(chosen), 'ai_frames': frames,
        'defect_observations': observed,
        'duration_seconds': round(duration, 1),
        'effective_fps': round(frames / duration, 2) if duration > 0 else None,
        'classes': {key: by_class[key] for key in LABELS},
        'other_observations': by_class['Other'],
        'daily': [{'date': day, 'sessions': count} for day,count in sorted(by_day.items())[-14:]],
        'recent_session': {'started_at': recent['started_at'],
                           'status': recent['status'],
                           'duration_seconds': round(float(recent['duration_seconds'] or 0), 1)},
        'range': range_key,
        'note': empty['note']
    }
