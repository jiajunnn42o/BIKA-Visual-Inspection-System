"""Persistent, per-user alerts for Live camera failures.

No AI models are loaded. Camera health is sampled when logged-in browsers poll;
notifications survive manual Disconnect, navigation, and Python restarts.
Single-process demo integration; multi-worker production should use a shared
state/unique episode store and a scheduled health monitor.
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone

from app.extensions import db
from app.services.live_camera_router import camera_router
from app.services.live_ai_service import live_ai
from app.services.notification_service import create_notification
from app.workflow_models import Notification

_ALERT_TYPE = "live_camera_health_fault"
_LOCK = threading.RLock()
_LAST_STATE = None
_LAST_STREAM = None
_ATTEMPTED = False
_WAS_ONLINE = False
_CONNECTING_SINCE = None
_CURRENT_FAULT = None  # (episode_id, title, message)
_INTENTIONAL_DISCONNECT = False


def note_intentional_disconnect():
    """Called only by the explicit user Disconnect route."""
    global _INTENTIONAL_DISCONNECT
    with _LOCK:
        _INTENTIONAL_DISCONNECT = True


def _fault_for(status, now):
    state = str(status.get("state") or "disconnected").lower()
    if state == "online":
        if status.get("feed_usable") is False:
            return ("Live camera feed unavailable",
                    str(status.get("feed_unavailable_reason") or
                        "Camera is connected, but is not providing usable video.")[:260])
        for k in ("last_decoded_frame_seconds_ago", "last_frame_seconds_ago"):
            age = status.get(k)
            try:
                if age is not None and float(age) >= 4.0:
                    return ("Live camera stopped updating",
                            "Camera is connected, but no fresh camera frames have arrived.")
            except (ValueError, TypeError):
                pass
    if state == "error":
        return ("Live camera connection error",
                "Camera capture failed or was interrupted. Check the camera and Camo Studio/RTSP source.")
    if state == "connecting" and _CONNECTING_SINCE is not None and now - _CONNECTING_SINCE >= 15:
        return ("Live camera connection timeout",
                "The selected camera has not delivered a usable frame. Check the source and connection.")
    if state == "disconnected" and _WAS_ONLINE and not _INTENTIONAL_DISCONNECT:
        return ("Live camera disconnected unexpectedly",
                "Camera disconnected without an operator Disconnect action.")
    return None


def _record_if_needed(user_id, fault):
    episode_id, title, message = fault
    recent = db.session.execute(
        db.select(Notification)
        .where(Notification.recipient_user_id == user_id,
               Notification.notification_type == _ALERT_TYPE)
        .order_by(Notification.id.desc()).limit(50)
    ).scalars().all()
    for item in recent:
        payload = item.payload_json or {}
        if isinstance(payload, dict) and payload.get("episode_id") == episode_id:
            return
    create_notification(
        recipient_user_id=user_id,
        notification_type=_ALERT_TYPE,
        title=title,
        message=message,
        link="/live-inspection",
        payload_json={"episode_id": episode_id, "kind": "camera_health"},
        force=True,  # Safety/operational alerts should not rely on marketing preferences.
    )
    db.session.commit()


def poll_camera_alerts(user_id):
    """Sample active camera, persist new fault for this user, return unread history."""
    global _LAST_STATE, _LAST_STREAM, _ATTEMPTED, _WAS_ONLINE
    global _CURRENT_FAULT, _INTENTIONAL_DISCONNECT, _CONNECTING_SINCE
    status = camera_router.status()
    ai = live_ai.status(include_events=False)
    state = str(status.get("state") or "disconnected").lower()
    stream = str(status.get("stream") or "")
    now = time.monotonic()
    with _LOCK:
        # A different camera source starts a fresh health monitoring episode.
        if _LAST_STREAM is not None and stream != _LAST_STREAM:
            _WAS_ONLINE = False
            _ATTEMPTED = False
            _CURRENT_FAULT = None
            _CONNECTING_SINCE = None
        _LAST_STREAM = stream
        if state == "connecting" and _LAST_STATE != "connecting":
            _CONNECTING_SINCE = now
            _ATTEMPTED = True
            _INTENTIONAL_DISCONNECT = False
        if state == "online":
            _WAS_ONLINE = True
            _ATTEMPTED = True
            _INTENTIONAL_DISCONNECT = False
        detail = _fault_for(status, now)
        if detail is None and state == 'online' and str(ai.get('state', '')).lower() == 'error':
            detail = ('Live AI inspection stopped unexpectedly',
                      'The Live inspection worker encountered an error. Check the Live Stream page and server logs.')
        if detail is not None and (_ATTEMPTED or state == "error"):
            if _CURRENT_FAULT is None:
                _CURRENT_FAULT = (uuid.uuid4().hex, detail[0], detail[1])
            try:
                _record_if_needed(user_id, _CURRENT_FAULT)
            except Exception:
                db.session.rollback()
                raise
        elif state == "online":
            # Actual recovery permits a new distinct future alert.
            _CURRENT_FAULT = None
        elif state == "disconnected":
            _CURRENT_FAULT = None
            _WAS_ONLINE = False
            _ATTEMPTED = False
            _CONNECTING_SINCE = None
            _INTENTIONAL_DISCONNECT = False
        _LAST_STATE = state

    unread = db.session.execute(
        db.select(Notification)
        .where(Notification.recipient_user_id == user_id,
               Notification.notification_type == _ALERT_TYPE,
               Notification.is_read.is_(False))
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(10)
    ).scalars().all()
    return {
        "ok": True,
        "camera_state": state,
        "camera_feed_usable": status.get("feed_usable", state == "online"),
        "unread_alerts": [
            {"id": n.id, "title": n.title, "message": n.message,
             "created_at": n.created_at.isoformat() if n.created_at else None,
             "open_url": "/live-inspection"} for n in unread
        ],
    }
