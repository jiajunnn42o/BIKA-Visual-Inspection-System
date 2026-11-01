"""Read-only Dashboard telemetry from the active BIKA camera and Live AI worker.

No model loads or database writes. Values describe the current server process
and current camera/AI session, not persistent historical throughput.
"""
from __future__ import annotations


def _bika_current_live_runtime() -> dict:
    from app.services.live_camera_router import camera_router
    from app.services.live_ai_service import live_ai

    camera = camera_router.status()
    ai = live_ai.status(include_events=False)
    online = camera.get('state') == 'online'
    usable = online and camera.get('feed_usable', True) is not False
    # A camera that is outputting a Camo placeholder is not usable video.
    if not usable:
        return {
            'uptime_seconds': None,
            'frames_processed': None,
            'average_fps': None,
            'camera_state': 'feed_unavailable' if online else camera.get('state', 'disconnected'),
            'camera_fps': camera.get('camera_fps') if online else None,
            'ai_state': ai.get('state', 'stopped'),
            'note': 'No usable live camera feed',
        }
    ai_active = bool(ai.get('active'))
    frames = ai.get('sample_count')
    fps = ai.get('ai_fps')
    return {
        'uptime_seconds': camera.get('stream_uptime_seconds'),
        'frames_processed': int(frames) if ai_active and isinstance(frames, (int,float)) else None,
        'average_fps': round(float(fps), 2) if ai_active and isinstance(fps, (int,float)) else None,
        'camera_state': camera.get('state'),
        'camera_fps': camera.get('camera_fps'),
        'ai_state': ai.get('state', 'stopped'),
        'note': 'Live AI inference frames in the current process; not unique biscuits',
    }


# BIKA-LIVE-SESSION-HISTORY-V1 — use the last saved session when Live is stopped.
def current_live_runtime() -> dict:
    current = _bika_current_live_runtime()
    if current.get('uptime_seconds') is not None and current.get('frames_processed') is not None:
        current['origin'] = 'current'
        return current
    try:
        from flask import current_app
        from flask_login import current_user
        from app.services.live_session_history import latest_session
        if not current_user.is_authenticated:
            return current
        saved = latest_session(current_app.instance_path, current_user.get_id())
    except Exception:
        return current
    if saved is None:
        return current
    return {
        'uptime_seconds': saved.get('duration_seconds'),
        'frames_processed': saved.get('ai_frames'),
        'average_fps': saved.get('ai_fps'),
        'origin': 'last_session',
        'camera_state': current.get('camera_state', 'disconnected'),
        'note': 'Last saved Live Session; historical AI frames are NOT unique products',
    }
