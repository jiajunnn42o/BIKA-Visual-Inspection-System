"""Optional, read-only AI mask video recorder for BIKA Live Sessions.

Never invokes YOLO, modifies LiveAI/LiveMaskProjector, grabs a camera device, or
modifies the browser's live display. Samples the *existing continuous* annotated
JPEG stream and records a separately stored, lower-priority MP4. During initial
loading or a stale AI view, writes current camera JPEG instead of repeating a
frozen AI image. This preserves recording time without misrepresenting stale masks.

All errors are isolated from the original recording and live detection.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time

LOG = logging.getLogger(__name__)
MASK_FILE = re.compile(r'^mask_segment_\d{4}\.mp4$')


def _bounded(name: str, default: int, low: int, high: int) -> int:
    try:
        return min(high, max(low, int(os.environ.get(name, str(default)))))
    except (ValueError, TypeError):
        return default


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class LiveMaskSidecar:
    """Low-priority sidecar; the caller owns the shared stop_event."""

    def __init__(self, session_folder, ffmpeg, camera, stop_event):
        self.folder = Path(session_folder)
        self.ffmpeg = ffmpeg
        self.camera = camera
        self.stop_event = stop_event
        self.fps = _bounded('BIKA_LIVE_MASK_RECORDING_FPS', 3, 1, 4)
        self.width = _bounded('BIKA_LIVE_MASK_RECORDING_WIDTH', 640, 320, 720)
        self.thread = None
        self.meta = {
            'status': 'starting', 'started_at': _now(), 'finished_at': None,
            'error': '', 'fps': self.fps, 'mask_frames': 0, 'fallback_frames': 0,
            'first_mask_offset_seconds': None,
        }

    def _write_meta(self):
        path = self.folder / 'mask_meta.json'
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.meta, indent=2), encoding='utf-8')
        os.replace(tmp, path)

    def start(self):
        self._write_meta()
        self.thread = threading.Thread(target=self._run, name='bika-mask-mp4-sidecar', daemon=True)
        self.thread.start()

    def join(self, timeout=14):
        if self.thread is not None and threading.current_thread() is not self.thread:
            self.thread.join(timeout=timeout)

    def _command(self):
        return [self.ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                '-f', 'image2pipe', '-framerate', str(self.fps),
                '-vcodec', 'mjpeg', '-i', 'pipe:0', '-an', '-filter_threads', '1',
                '-vf', f'scale=w=min({self.width}\\,iw):h=-2:flags=fast_bilinear',
                '-c:v', 'libx264', '-threads:v', '1', '-preset', 'ultrafast',
                '-crf', '31', '-maxrate', '1200k', '-bufsize', '2400k',
                '-pix_fmt', 'yuv420p', '-g', str(self.fps*2), '-sc_threshold', '0',
                '-force_key_frames', 'expr:gte(t,n_forced*600)',
                '-f', 'segment', '-segment_time', '600', '-reset_timestamps', '1',
                '-segment_format', 'mp4', '-segment_format_options', 'movflags=+faststart',
                str(self.folder / 'mask_segment_%04d.mp4')]

    def _run(self):
        proc = None
        outcome, issue = 'completed', ''
        started = time.monotonic()
        previous_seq = None
        last_ai_at = 0.0
        last_ai_jpeg = None
        last_write_meta = started
        tick = 1.0 / self.fps
        next_tick = started
        try:
            # Import the singleton only when the sidecar starts, so this feature
            # never causes a second LiveAI worker or any model initialization.
            from app.services.live_ai_service import live_ai
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            if os.name == 'nt':
                flags |= getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0x00004000)
            proc = subprocess.Popen(self._command(), stdin=subprocess.PIPE,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=flags)
            if os.name != 'nt' and hasattr(os, 'setpriority'):
                try:
                    os.setpriority(os.PRIO_PROCESS, proc.pid, 10)
                except (OSError, PermissionError):
                    pass
            self.meta['status'] = 'recording'
            self._write_meta()
            while not self.stop_event.is_set():
                now = time.monotonic()
                if now < next_tick:
                    self.stop_event.wait(min(.12, next_tick-now))
                    continue
                next_tick += tick
                if now - next_tick > 1:
                    next_tick = now + tick
                if proc.poll() is not None:
                    outcome, issue = 'error', 'AI mask encoder stopped unexpectedly.'
                    break
                try:
                    if shutil.disk_usage(self.folder).free < 600 * 1024 * 1024:
                        outcome, issue = 'storage_full', 'Insufficient disk space for masked video.'
                        break
                except OSError:
                    pass
                # read-only snapshot from the EXISTING motion-tracked compositor
                seq, annotated = live_ai.latest_overlay()
                if annotated is not None and seq != previous_seq:
                    previous_seq = seq
                    last_ai_jpeg = annotated
                    last_ai_at = now
                # Never repeat a frozen AI JPEG for more than one tick or use
                # 09b's sampled-keyframe stream as a substitute.
                runtime = live_ai.status(include_events=False)
                continuous = runtime.get('live_runtime_mode') == 'continuous_yolo'
                mode = runtime.get('live_mask_mode', '')
                fresh = continuous and last_ai_jpeg and now-last_ai_at < .65
                mask_drawn = fresh and str(mode).startswith('Flow-aligned masks')
                if fresh:
                    frame = last_ai_jpeg
                else:
                    _seq, frame = self.camera.latest()
                if not frame:
                    continue
                try:
                    proc.stdin.write(frame)
                except (BrokenPipeError, OSError) as exc:
                    outcome, issue = 'error', f'Mask encoder pipe closed: {exc}'
                    break
                if mask_drawn:
                    self.meta['mask_frames'] += 1
                    if self.meta['first_mask_offset_seconds'] is None:
                        self.meta['first_mask_offset_seconds'] = round(now-started,2)
                else:
                    self.meta['fallback_frames'] += 1
                if now - last_write_meta > 6:
                    self._write_meta()
                    last_write_meta = now
        except Exception as exc:
            LOG.exception('Optional AI-mask recording failed; original recording unaffected')
            outcome, issue = 'error', str(exc)[:240]
        finally:
            if proc is not None:
                try:
                    if proc.stdin is not None:
                        proc.stdin.close()
                        proc.stdin = None
                    try:
                        code = proc.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=3)
                        code = -1
                    if code and outcome == 'completed':
                        outcome, issue = 'error', 'AI mask encoder failed to finalize.'
                except (OSError, subprocess.TimeoutExpired) as exc:
                    outcome, issue = 'error', str(exc)[:240]
            self.meta['finished_at'] = _now()
            has_video = any(p.is_file() and p.stat().st_size > 1024
                            for p in self.folder.glob('mask_segment_*.mp4'))
            if not self.meta['mask_frames'] or not has_video:
                outcome = 'unavailable' if outcome == 'completed' else outcome
                if not issue:
                    issue = 'No continuous motion-aligned AI masks captured.'
            self.meta['status'] = outcome
            self.meta['error'] = issue
            try:
                self._write_meta()
            except OSError:
                LOG.exception('Could not write AI mask video metadata')


def start_mask_sidecar(session_folder, ffmpeg, camera, stop_event):
    if os.getenv('BIKA_LIVE_MASK_RECORDING_ENABLED','1').strip().lower() in ('0','false','off','no'):
        return None
    sidecar = LiveMaskSidecar(session_folder, ffmpeg, camera, stop_event)
    sidecar.start()
    return sidecar
