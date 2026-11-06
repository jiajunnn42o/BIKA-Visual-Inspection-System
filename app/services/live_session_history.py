"""BIKA: small, separate SQLite journal for *provisional* live observations.

Not an InspectionBatch or production-quality denominator. Camera/YOLO data are
saved from the background worker rather than from an open browser page.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import threading
import time
import uuid

_DB_LOCK = threading.RLock()
_MONITOR_LOCK = threading.RLock()
_MONITOR = None


def _iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


@contextmanager
def _db(db_file):
    path = Path(db_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=8)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=8000')
    conn.execute('''CREATE TABLE IF NOT EXISTS live_session_history (
        session_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
        started_at TEXT NOT NULL, ended_at TEXT,
        updated_at TEXT NOT NULL, status TEXT NOT NULL,
        camera_source TEXT, ai_frames INTEGER NOT NULL DEFAULT 0,
        ai_fps REAL, camera_fps REAL, duration_seconds REAL NOT NULL DEFAULT 0,
        event_count INTEGER NOT NULL DEFAULT 0
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS live_observation_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL, source_event_id TEXT NOT NULL,
        detected_at TEXT NOT NULL, label TEXT NOT NULL,
        confidence REAL, detection_confidence REAL,
        UNIQUE(session_id, source_event_id)
    )''')
    # Forward-compatible additive columns. Existing session rows are preserved.
    cols={r[1] for r in conn.execute('PRAGMA table_info(live_session_history)').fetchall()}
    for col in ('estimated_total','estimated_good','estimated_bad'):
        if col not in cols:
            conn.execute(f'ALTER TABLE live_session_history ADD COLUMN {col} INTEGER')
    conn.execute('CREATE INDEX IF NOT EXISTS live_session_owner_idx ON live_session_history(owner_id,started_at DESC)')
    conn.commit()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _num(value):
    try:
        n = float(value)
        return n if n == n and abs(n) < 1e8 else None
    except (ValueError, TypeError):
        return None


def _snapshot(camera, ai):
    cs = camera.status() or {}
    a = ai.status(include_events=False) or {}
    # Copy the bounded latest event buffer under the worker lock.
    with ai.lock:
        events = [dict(e) for e in getattr(ai, 'events', ())]
    return cs, a, events


class _MonitorWorker:
    def __init__(self, db_file, owner_id, camera, ai):
        self.db_file = str(db_file)
        self.owner_id = str(owner_id)
        self.camera = camera
        self.ai = ai
        self.session_id = uuid.uuid4().hex
        self.started = time.monotonic()
        self.closed = threading.Event()
        self.seen = set()
        self.last_ai_frames = 0
        self.last_ai_fps = None
        self.last_camera_fps = None
        self.last_estimated_total = None
        self.last_estimated_good = None
        self.last_estimated_bad = None
        self.source = ''

    def begin(self):
        camera, _, _ = _snapshot(self.camera, self.ai)
        self.source = str(camera.get('source') or camera.get('stream') or 'Live Camera')[:120]
        with _DB_LOCK, _db(self.db_file) as conn:
            conn.execute('''INSERT INTO live_session_history
                (session_id,owner_id,started_at,updated_at,status,camera_source)
                VALUES (?,?,?,?,?,?)''',
                (self.session_id, self.owner_id, _iso(), _iso(), 'running', self.source))
        threading.Thread(target=self.run, name='bika-live-session-journal', daemon=True).start()

    def capture(self, *, final=False, outcome='completed'):
        if self.closed.is_set() and not final:
            return
        cs, ai, events = _snapshot(self.camera, self.ai)
        frames = ai.get('sample_count')
        if isinstance(frames, (int, float)):
            self.last_ai_frames = max(self.last_ai_frames, int(frames))
        for key, attr in (('ai_fps','last_ai_fps'), ('camera_fps','last_camera_fps')):
            v = _num((ai if key == 'ai_fps' else cs).get(key))
            if v is not None and v >= 0:
                setattr(self, attr, v)
        # Only continuous realtime YOLO Track IDs can be counted here. The
        # legacy 09b sampler repeats objects across frames and is excluded.
        model_name=str(ai.get('model_version') or '').lower()
        if 'realtime yolo' in model_name:
            total=ai.get('judged_observations')
            good=ai.get('normal_observations')
            bad=ai.get('defect_observations')
            if all(isinstance(v,(int,float)) for v in (total,good,bad)):
                total,good,bad=(max(0,int(v)) for v in (total,good,bad))
                if total==good+bad:
                    self.last_estimated_total=total
                    self.last_estimated_good=good
                    self.last_estimated_bad=bad
        elapsed = round(time.monotonic() - self.started, 1)
        rows = []
        for ev in events:
            uid = str(ev.get('id') or '')
            if not uid or uid in self.seen:
                continue
            self.seen.add(uid)
            rows.append((self.session_id, uid, _iso(),
                        str(ev.get('label') or 'Defect')[:60],
                        _num(ev.get('confidence')),
                        _num(ev.get('detection_confidence'))))
        state = outcome if final else ('feed_unavailable' if cs.get('feed_usable') is False
                                      else ('running' if ai.get('active') else 'paused'))
        with _DB_LOCK, _db(self.db_file) as conn:
            if rows:
                conn.executemany('''INSERT OR IGNORE INTO live_observation_history
                    (session_id,source_event_id,detected_at,label,confidence,detection_confidence)
                    VALUES (?,?,?,?,?,?)''', rows)
            conn.execute('''UPDATE live_session_history SET updated_at=?,status=?,
                ended_at=COALESCE(ended_at, ?),ai_frames=?,ai_fps=?,camera_fps=?,duration_seconds=?,
                event_count=(SELECT COUNT(*) FROM live_observation_history WHERE session_id=?),
                estimated_total=COALESCE(?,estimated_total),
                estimated_good=COALESCE(?,estimated_good),
                estimated_bad=COALESCE(?,estimated_bad)
                WHERE session_id=?''',
                (_iso(),state,_iso() if final else None,self.last_ai_frames,self.last_ai_fps,
                 self.last_camera_fps,elapsed,self.session_id,
                 self.last_estimated_total,self.last_estimated_good,self.last_estimated_bad,
                 self.session_id))

    def run(self):
        while not self.closed.wait(1.0):
            try:
                self.capture()
                cs, ai, _ = _snapshot(self.camera, self.ai)
                if cs.get('state') in ('disconnected','error') or ai.get('state') == 'error':
                    self.finish('interrupted' if cs.get('state') == 'error' or ai.get('state') == 'error' else 'completed')
                    return
            except Exception:
                # Never crash/interrupt live inference because history storage failed.
                import logging
                logging.getLogger(__name__).exception('BIKA live history snapshot failed')

    def finish(self, outcome='completed'):
        if self.closed.is_set():
            return
        self.closed.set()
        try:
            self.capture(final=True, outcome=outcome)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('BIKA live history final save failed')


def begin_live_session(instance_path, owner_id, camera, ai):
    global _MONITOR
    db_file = Path(instance_path) / 'live_session_history.sqlite3'
    with _MONITOR_LOCK:
        if _MONITOR is not None:
            _MONITOR.finish()
        worker = _MonitorWorker(db_file, owner_id, camera, ai)
        worker.begin()
        _MONITOR = worker
        return worker.session_id


def finish_live_session(outcome='completed'):
    # Close recorder before publishing a completed report. Also called by the
    # history monitor if camera feed fails without a browser API request.
    try:
        from app.services.live_recording_service import stop_active_recording
        stop_active_recording()
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Could not finalize Live recording')
    with _MONITOR_LOCK:
        if _MONITOR is not None:
            _MONITOR.finish(outcome)


def latest_session(instance_path, owner_id):
    path = Path(instance_path) / 'live_session_history.sqlite3'
    if not path.exists():
        return None
    with _DB_LOCK, _db(path) as conn:
        row = conn.execute('''SELECT * FROM live_session_history WHERE owner_id=?
                              ORDER BY started_at DESC LIMIT 1''',(str(owner_id),)).fetchone()
        return dict(row) if row is not None else None


def list_sessions(instance_path, owner_id, limit=30):
    path = Path(instance_path) / 'live_session_history.sqlite3'
    if not path.exists():
        return []
    limit = min(max(1,int(limit)),60)
    with _DB_LOCK, _db(path) as conn:
        sessions = [dict(r) for r in conn.execute('''SELECT * FROM live_session_history
                  WHERE owner_id=? ORDER BY started_at DESC LIMIT ?''',(str(owner_id),limit))]
        for session in sessions:
            # If Flask was killed without a clean stop, mark an old open session
            # interrupted in the report response without changing historical rows.
            if not session.get('ended_at'):
                try:
                    last = datetime.fromisoformat(session['updated_at'])
                    age = (datetime.now(timezone.utc) - last).total_seconds()
                    if age > 30:
                        session['status'] = 'interrupted'
                except (ValueError,TypeError):
                    pass
            rows = conn.execute('''SELECT label,COUNT(*) AS n FROM live_observation_history
                WHERE session_id=? GROUP BY label ORDER BY n DESC''',(session['session_id'],)).fetchall()
            session['class_breakdown'] = {r['label']:int(r['n']) for r in rows}
            events = conn.execute('''SELECT detected_at,label,confidence FROM live_observation_history
                WHERE session_id=? ORDER BY id DESC LIMIT 20''', (session['session_id'],)).fetchall()
            session['recent_events'] = [dict(e) for e in events]
            session['is_provisional'] = True
        return sessions

# BIKA-REPORT-COUNTS-V4
