"""BIKA Live session recorder: isolated JPEG capture -> segmented H.264 MP4.

The recording thread reads the same camera.latest() snapshots as browser preview.
It does not open a second RTSP stream, and failure never stops live AI.
Video files live under the Flask instance directory (never /static).

This first stage records and serves video. Retention is recorded as an expiry
marker, but *automatic deletion is deliberately NOT enabled*.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time

LOG = logging.getLogger(__name__)
_ACTIVE_LOCK = threading.RLock()
_ACTIVE = None
_LAST_STATUS = {'status': 'idle', 'active': False, 'message': ''}
_VALID_ID = re.compile(r'^[0-9a-f]{32}$')
_SEGMENT = re.compile(r'^segment_\d{4}\.mp4$')
FPS = 8
SEGMENT_SECONDS = 600
MIN_FREE_BYTES = 600 * 1024**2


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _root(instance_path):
    return Path(instance_path) / 'live_recordings'


def _session_dir(instance_path, session_id):
    if not _VALID_ID.fullmatch(str(session_id)):
        raise ValueError('Invalid Live Session identifier.')
    return _root(instance_path) / session_id


def _config(instance_path):
    result = {'full_days': 7, 'storage_limit_gb': 50}
    path = Path(instance_path) / 'about_system_state.json'
    try:
        saved = json.loads(path.read_text(encoding='utf-8')).get('video_retention', {})
        for key, max_allowed in (('full_days', 365), ('storage_limit_gb', 1000)):
            value = saved.get(key)
            if type(value) is int and 1 <= value <= max_allowed:
                result[key] = value
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return result


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


def _space_usage(folder):
    total = 0
    if not folder.exists():
        return 0
    for parent, _dirs, files in os.walk(folder):
        for name in files:
            if _SEGMENT.fullmatch(name):
                try:
                    total += (Path(parent) / name).stat().st_size
                except OSError:
                    pass
    return total


def _owner_has_session(instance_path, owner_id, session_id):
    path = Path(instance_path) / 'live_session_history.sqlite3'
    if not path.exists() or not _VALID_ID.fullmatch(str(session_id)):
        return False
    try:
        with sqlite3.connect(str(path), timeout=5) as conn:
            return conn.execute(
                'SELECT 1 FROM live_session_history WHERE session_id=? AND owner_id=?',
                (session_id, str(owner_id)),
            ).fetchone() is not None
    except sqlite3.Error:
        return False


def recording_manifest(instance_path, owner_id, session_id):
    """Owner-authorized, path-safe manifest for a Reports session.

    Only completed segments are advertised while the encoder is running.
    """
    if not _owner_has_session(instance_path, owner_id, session_id):
        return None
    folder = _session_dir(instance_path, session_id)
    path = folder / 'meta.json'
    if not path.exists():
        return {'status': 'not_recorded', 'segments': [], 'size_bytes': 0}
    try:
        meta = json.loads(path.read_text(encoding='utf-8'))
        if meta.get('session_id') != session_id or str(meta.get('owner_id')) != str(owner_id):
            return None
    except (OSError, ValueError, TypeError):
        return {'status': 'unavailable', 'segments': [], 'size_bytes': 0}
    candidates = sorted(folder.glob('segment_*.mp4'))
    valid = [p for p in candidates if _SEGMENT.fullmatch(p.name) and p.is_file() and p.stat().st_size > 1024]
    # Encoder is still writing the last segment. MP4 isn't ready for playback.
    if meta.get('status') in ('starting', 'recording', 'finalizing') and valid:
        valid = valid[:-1]
    segments = [{'index': i, 'name': p.name, 'size_bytes': p.stat().st_size,
                 'url': f'/reports/api/live-recordings/{session_id}/segments/{i}'}
                for i, p in enumerate(valid)]
    return {
        'status': str(meta.get('status') or 'unavailable'),
        'error': str(meta.get('error') or '')[:250],
        'started_at': meta.get('started_at'),
        'finished_at': meta.get('finished_at'),
        'expires_at': meta.get('expires_at'),
        'fps': meta.get('fps', FPS),
        'segment_seconds': SEGMENT_SECONDS,
        'segments': segments,
        'size_bytes': sum(item['size_bytes'] for item in segments),
    }


def recording_segment_path(instance_path, owner_id, session_id, index):
    """Only serve own indexed MP4 segments. Never use a client-supplied path."""
    if type(index) is not int or not 0 <= index <= 9999:
        return None
    manifest = recording_manifest(instance_path, owner_id, session_id)
    if manifest is None:
        return None
    segments = manifest['segments']
    if index >= len(segments):
        return None
    path = _session_dir(instance_path, session_id) / segments[index]['name']
    return path if path.is_file() else None


class _Recorder:
    def __init__(self, instance_path, session_id, owner_id, camera, ffmpeg):
        self.instance_path = str(instance_path)
        self.session_id = str(session_id)
        self.owner_id = str(owner_id)
        self.camera = camera
        self.ffmpeg = ffmpeg
        self.folder = _session_dir(instance_path, session_id)
        self.stop_event = threading.Event()
        self.thread = None
        self.proc = None
        self.guard = threading.RLock()
        self.settings = _config(instance_path)
        self.meta = {
            'session_id': self.session_id, 'owner_id': self.owner_id,
            'started_at': _now(), 'finished_at': None, 'expires_at': None,
            'status': 'starting', 'error': '', 'fps': FPS,
        }

    def _save(self):
        with self.guard:
            _write_json(self.folder / 'meta.json', self.meta)

    def _set(self, status, error=''):
        with self.guard:
            self.meta['status'] = status
            self.meta['error'] = str(error)[:240]
            self._save()

    def start(self):
        self.folder.mkdir(parents=True, exist_ok=False)
        self._save()
        self.thread = threading.Thread(target=self._run, name='bika-live-mp4-recorder', daemon=True)
        self.thread.start()

    def _ffmpeg_cmd(self):
        return [self.ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                '-f', 'image2pipe', '-framerate', str(FPS), '-vcodec', 'mjpeg', '-i', 'pipe:0',
                '-an', '-vf', 'scale=w=min(960\\,iw):h=-2:flags=fast_bilinear',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '29',
                '-maxrate', '1800k', '-bufsize', '3600k', '-pix_fmt', 'yuv420p',
                '-g', str(FPS*2), '-sc_threshold', '0',
                '-force_key_frames', f'expr:gte(t,n_forced*{SEGMENT_SECONDS})',
                '-f', 'segment', '-segment_time', str(SEGMENT_SECONDS),
                '-reset_timestamps', '1', '-segment_format', 'mp4',
                '-segment_format_options', 'movflags=+faststart',
                str(self.folder / 'segment_%04d.mp4')]

    def _capacity_ok(self):
        try:
            if shutil.disk_usage(self.folder).free < MIN_FREE_BYTES:
                return False, 'Disk free space is below the 600 MB safety reserve.'
            limit = int(self.settings['storage_limit_gb']) * 1024**3
            if _space_usage(_root(self.instance_path)) >= limit:
                return False, 'Video storage limit has been reached.'
        except OSError as exc:
            return False, f'Cannot check recording storage: {exc}'
        return True, ''

    def _run(self):
        last_jpeg = None
        last_fresh = time.monotonic()
        last_sequence = None
        last_capacity = 0.0
        outcome = 'completed'
        issue = ''
        try:
            good, reason = self._capacity_ok()
            if not good:
                outcome, issue = 'unavailable', reason
                return
            creation_flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            self.proc = subprocess.Popen(self._ffmpeg_cmd(), stdin=subprocess.PIPE,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         creationflags=creation_flags)
            self._set('recording')
            # Real-time fixed frame cadence. Reuse an unchanged frame only while
            # the camera reports a healthy, fresh feed; never invent activity
            # across a prolonged disconnect.
            tick = 1.0 / FPS
            next_tick = time.monotonic()
            while not self.stop_event.is_set():
                now = time.monotonic()
                if now < next_tick:
                    self.stop_event.wait(min(0.1, next_tick-now))
                    continue
                next_tick += tick
                if now-next_tick > 1.0:
                    next_tick = now+tick
                if now-last_capacity > 15:
                    good, reason = self._capacity_ok()
                    last_capacity = now
                    if not good:
                        outcome, issue = 'storage_full', reason
                        break
                status = self.camera.status() or {}
                if status.get('state') in ('disconnected', 'error'):
                    outcome, issue = 'interrupted', 'Camera disconnected during recording.'
                    break
                seq, jpeg = self.camera.latest()
                if jpeg and seq != last_sequence:
                    last_sequence = seq
                    last_jpeg = jpeg
                    last_fresh = now
                if now-last_fresh > 6:
                    outcome, issue = 'interrupted', 'Camera frames stopped arriving.'
                    break
                if not last_jpeg:
                    continue
                if self.proc.poll() is not None:
                    outcome, issue = 'error', 'FFmpeg exited before recording finished.'
                    break
                try:
                    self.proc.stdin.write(last_jpeg)
                except (BrokenPipeError, OSError) as exc:
                    outcome, issue = 'error', f'FFmpeg recording pipe closed: {exc}'
                    break
        except Exception as exc:
            LOG.exception('Live recording failed')
            outcome, issue = 'error', str(exc)
        finally:
            with self.guard:
                if self.meta['status'] == 'recording':
                    self.meta['status'] = 'finalizing'
                    self._save()
            try:
                if self.proc is not None:
                    if self.proc.stdin is not None:
                        self.proc.stdin.close()
                        self.proc.stdin = None
                    try:
                        return_code = self.proc.wait(timeout=12)
                    except subprocess.TimeoutExpired:
                        self.proc.kill()
                        self.proc.wait(timeout=3)
                        return_code = -1
                    if return_code and outcome == 'completed':
                        outcome, issue = 'error', 'FFmpeg did not finalize the recording.'
            except (OSError, subprocess.TimeoutExpired) as exc:
                outcome, issue = 'error', f'Failed to finalize video: {exc}'
            with self.guard:
                self.meta['finished_at'] = _now()
                self.meta['expires_at'] = (datetime.now(timezone.utc) + timedelta(days=int(self.settings['full_days']))).isoformat(timespec='seconds')
                files = [p for p in self.folder.glob('segment_*.mp4') if p.stat().st_size > 1024]
                self.meta['status'] = outcome if files else ('unavailable' if outcome == 'completed' else outcome)
                self.meta['error'] = issue if files or issue else 'No camera footage was recorded.'
                self._save()
            self.stop_event.set()
            with _ACTIVE_LOCK:
                global _ACTIVE, _LAST_STATUS
                _LAST_STATUS = {'status': self.meta['status'], 'active': False,
                                'session_id': self.session_id, 'message': self.meta['error']}
                if _ACTIVE is self:
                    _ACTIVE = None

    def stop(self):
        self.stop_event.set()
        if self.thread is not None and threading.current_thread() is not self.thread:
            self.thread.join(timeout=14)
        return self.meta.copy()


def start_recording(instance_path, session_id, owner_id, camera):
    """Return {ok,message}; keep the AI session alive on any recorder error."""
    global _ACTIVE, _LAST_STATUS
    ffmpeg = os.environ.get('BIKA_FFMPEG_PATH') or shutil.which('ffmpeg')
    if not ffmpeg:
        message = 'FFmpeg is not installed or not on PATH. Detection continues without recording.'
        with _ACTIVE_LOCK:
            _LAST_STATUS = {'status': 'unavailable', 'active': False, 'message': message}
        return {'ok': False, 'message': message}
    if not _owner_has_session(instance_path, owner_id, session_id):
        return {'ok': False, 'message': 'Live Session not found. No recording started.'}
    with _ACTIVE_LOCK:
        if _ACTIVE and not _ACTIVE.stop_event.is_set():
            return {'ok': False, 'message': 'Another recording is already active in this server process.'}
        try:
            recorder = _Recorder(instance_path, session_id, owner_id, camera, ffmpeg)
            recorder.start()
            _ACTIVE = recorder
            _LAST_STATUS = {'status': 'starting', 'active': True, 'session_id': session_id, 'message': ''}
        except (OSError, ValueError) as exc:
            LOG.exception('Could not start Live recorder')
            _LAST_STATUS = {'status': 'error', 'active': False, 'message': f'Could not start recorder: {exc}'}
            return {'ok': False, 'message': f'Could not start recorder: {exc}'}
    return {'ok': True, 'message': 'Recording started. Files will appear in Reports after a segment finalizes.'}


def stop_active_recording():
    with _ACTIVE_LOCK:
        recorder = _ACTIVE
    return recorder.stop() if recorder else None


def active_recording_status():
    with _ACTIVE_LOCK:
        recorder = _ACTIVE
        if not recorder:
            return dict(_LAST_STATUS)
        with recorder.guard:
            return {'status': recorder.meta['status'], 'active': not recorder.stop_event.is_set(),
                    'session_id': recorder.session_id, 'message': recorder.meta['error']}


def recording_inventory(instance_path):
    """Safe recording usage summary for About System; never deletes files."""
    root = _root(instance_path)
    sessions = 0
    total_bytes = 0
    expiring_soon = 0
    now = datetime.now(timezone.utc)
    if root.exists():
        for folder in root.iterdir():
            if not folder.is_dir() or not _VALID_ID.fullmatch(folder.name):
                continue
            meta_path = folder / 'meta.json'
            if not meta_path.is_file():
                continue
            sessions += 1
            try:
                meta = json.loads(meta_path.read_text(encoding='utf-8'))
                if meta.get('expires_at'):
                    expiry = datetime.fromisoformat(meta['expires_at'])
                    if now <= expiry <= now + timedelta(days=2):
                        expiring_soon += 1
            except (OSError, ValueError, TypeError):
                pass
            for p in folder.glob('segment_*.mp4'):
                if p.is_file() and _SEGMENT.fullmatch(p.name):
                    try:
                        total_bytes += p.stat().st_size
                    except OSError:
                        pass
    configured_ffmpeg = os.environ.get('BIKA_FFMPEG_PATH') or shutil.which('ffmpeg')
    available = bool(configured_ffmpeg and Path(configured_ffmpeg).is_file())
    return {'recording_connected': available, 'cleanup_enabled': False, 'recordings': sessions,
            'storage_bytes': total_bytes, 'expiring_soon': expiring_soon,
            'protected_recordings': 0, 'dry_run': True}
