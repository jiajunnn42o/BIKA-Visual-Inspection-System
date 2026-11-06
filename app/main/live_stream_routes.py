"""BIKA Live Stream routes for Hikvision RTSP and local Camo virtual webcam."""
from __future__ import annotations

import io
import time
from datetime import datetime

from flask import Response, abort, jsonify, render_template, request, send_file, stream_with_context
from flask_login import current_user, login_required

from app.main import main_bp
from app.services.live_camera_router import camera_router as live_camera
from app.services.live_ai_service import live_ai
from app.services.live_system_alerts import poll_camera_alerts, note_intentional_disconnect  # BIKA-LIVE-GLOBAL-ALERTS-V1


CONTROL_ROLES = {"admin", "superadmin"}


def can_control():
    return current_user.is_authenticated and current_user.role in CONTROL_ROLES


def live_camera_combined_status():
    state = live_camera.status()
    state["ai_enabled"] = live_ai.status(include_events=False)["active"]
    return state


@main_bp.get("/live-inspection")
@login_required
def live_inspection():
    return render_template("live_stream.html", can_control_camera=can_control())


@main_bp.get("/live-inspection/api/status")
@login_required
def live_inspection_status():
    from app.services.live_recording_service import active_recording_status
    return jsonify(ok=True, camera=live_camera_combined_status(), ai=live_ai.status(),
                   recording=active_recording_status(), can_control=can_control())


@main_bp.post("/live-inspection/api/connect")
@login_required
def live_inspection_connect():
    if not can_control():
        abort(403)
    payload = request.get_json(silent=True) or {}
    stream = payload.get("stream", "main")
    if not isinstance(stream, str):
        return jsonify(ok=False, message="Invalid stream type."), 400
    live_ai.stop()
    ok, message = live_camera.connect(stream)
    return jsonify(ok=ok, message=message, camera=live_camera_combined_status()), 200 if ok else 409


@main_bp.post("/live-inspection/api/disconnect")
@login_required
def live_inspection_disconnect():
    if not can_control():
        abort(403)
    # Capture an existing fault BEFORE a deliberate disconnect clears status.
    try:
        poll_camera_alerts(current_user.id)
    except Exception:
        from flask import current_app
        current_app.logger.exception('Live camera alert snapshot failed')
    note_intentional_disconnect()
    # BIKA-LIVE-SESSION-HISTORY-V1: snapshot before AI buffers are cleared.
    try:
        from app.services.live_session_history import finish_live_session
        finish_live_session()
    except Exception:
        from flask import current_app
        current_app.logger.exception('Could not finalize Live Session History')
    live_ai.stop()
    live_camera.disconnect()
    return jsonify(ok=True, camera=live_camera_combined_status())


@main_bp.get("/live-inspection/video-feed")
@login_required
def live_inspection_video_feed():
    if live_camera.status()["state"] != "online":
        return jsonify(ok=False, message="Camera is not online."), 409

    def frames():
        previous = -1
        idle = time.monotonic()
        while True:
            seq, frame = live_camera.latest()
            if frame and seq != previous:
                previous = seq
                idle = time.monotonic()
                yield (b"--frame\r\nContent-Type: image/jpeg\r\nCache-Control: no-store\r\n\r\n" + frame + b"\r\n")
            elif time.monotonic() - idle > 8:
                break
            time.sleep(0.08)

    response = Response(stream_with_context(frames()), mimetype="multipart/x-mixed-replace; boundary=frame")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@main_bp.get("/live-inspection/latest-frame.jpg")
@login_required
def live_inspection_latest_frame():
    """Return only the newest decoded camera frame, never a browser MJPEG backlog.

    204 means the client's last-seen sequence is still current. The header age
    measures server capture freshness, not true camera-to-display latency.
    The previous MJPEG endpoint remains available as a compatibility fallback.
    """
    seq, jpeg = live_camera.latest()
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "X-BIKA-Frame-Sequence": str(seq),
    }
    if jpeg is None:
        return jsonify(ok=False, message="Camera is not online."), 409
    seconds = live_camera.status().get("last_frame_seconds_ago")
    if seconds is not None:
        headers["X-BIKA-Server-Frame-Age-Ms"] = str(max(0, int(float(seconds) * 1000)))
    if request.args.get("seq") == str(seq):
        return Response(status=204, headers=headers)
    return Response(jpeg, mimetype="image/jpeg", headers=headers)


@main_bp.get("/live-inspection/api/snapshot")
@login_required
def live_inspection_snapshot():
    if not can_control():
        abort(403)
    _, frame = live_camera.latest()
    if not frame:
        return jsonify(ok=False, message="No camera frame available."), 409
    name = f"bika-camera-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jpg"
    return send_file(io.BytesIO(frame), mimetype="image/jpeg", as_attachment=True, download_name=name)

@main_bp.get("/inspection/api/device-status")
@login_required
def inspection_device_status():
    """Current process' loaded model devices and user's inspection job state.

    No inference/model loading is initiated by visiting this endpoint.
    """
    from app.main import inspection_routes
    from app.services.inspection_device_status_service import runtime_model_device_snapshot

    user_id = str(current_user.get_id())
    with inspection_routes._INSPECTION_JOBS_LOCK:
        user_jobs = [
            {"status": job.get("status"), "updated_at": job.get("updated_at", 0),
             "kind": (job.get("result") or {}).get("kind")}
            for job in inspection_routes._INSPECTION_JOBS.values()
            if str(job.get("user_id")) == user_id
        ]
    user_jobs.sort(key=lambda job: job["updated_at"], reverse=True)
    current = next(
        (job for job in user_jobs if job["status"] in {"queued", "running"}),
        None,
    )
    last = user_jobs[0] if user_jobs else None
    response = jsonify(
        ok=True,
        models=runtime_model_device_snapshot(),
        inspection={
            "state": current["status"] if current else "idle",
            "last_status": last["status"] if last else None,
        },
        live_ai_enabled=live_ai.status(include_events=False)["active"],
        live_preview="CPU (OpenCV)",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@main_bp.post("/live-inspection/api/ai/start")
@login_required
def live_inspection_ai_start():
    if not can_control():
        abort(403)
    from flask import current_app
    # BIKA-REALTIME-MASK-RESTORE-V2: never silently fall back to the old 09b sampler.
    # Only selects the already-installed real-time worker; no mask/YOLO code changed.
    import os
    from pathlib import Path
    realtime_worker = Path(current_app.root_path) / "services" / "realtime_inspection_service.py"
    if not realtime_worker.is_file():
        return jsonify(ok=False,
                       message="Real-time YOLO mask worker is missing. Detection was not started; sampled keyframes were not substituted.",
                       ai=live_ai.status(include_events=False)), 409
    os.environ["BIKA_REALTIME_LIVE_ENABLED"] = "1"
    ok, message = live_ai.start(current_app._get_current_object(), live_camera)
    if ok:
        try:
            from app.services.live_session_history import begin_live_session
            from app.services.live_recording_service import start_recording
            live_session_id = begin_live_session(current_app.instance_path, current_user.get_id(), live_camera, live_ai)
            record_result = start_recording(current_app.instance_path, live_session_id, current_user.get_id(), live_camera)
            if not record_result['ok']:
                current_app.logger.warning('Live recording unavailable: %s', record_result['message'])
        except Exception:
            current_app.logger.exception('Could not start Live Session History')
    from app.services.live_recording_service import active_recording_status
    return jsonify(ok=ok, message=message, ai=live_ai.status(), recording=active_recording_status()), 200 if ok else 409


@main_bp.post("/live-inspection/api/ai/stop")
@login_required
def live_inspection_ai_stop():
    if not can_control():
        abort(403)
    # Snapshot the last events before stopping the AI worker.
    try:
        from app.services.live_session_history import finish_live_session
        finish_live_session()
    except Exception:
        from flask import current_app
        current_app.logger.exception('Could not finalize Live Session History')
    live_ai.stop()
    return jsonify(ok=True, message="AI stopped. Camera preview remains online.", ai=live_ai.status())


@main_bp.get("/live-inspection/ai-feed")
@login_required
def live_inspection_ai_feed():
    sequence, jpeg = live_ai.latest_overlay()
    if not jpeg:
        return jsonify(ok=False, message="AI keyframe not available yet."), 409

    def frames():
        last = -1
        idle = time.monotonic()
        while True:
            seq, encoded = live_ai.latest_overlay()
            if encoded is not None and seq != last:
                last = seq
                idle = time.monotonic()
                yield (b"--frame\r\nContent-Type: image/jpeg\r\nCache-Control: no-store\r\n\r\n" + encoded + b"\r\n")
            elif encoded is None or time.monotonic() - idle > 65:
                break
            time.sleep(0.15)

    response = Response(stream_with_context(frames()), mimetype="multipart/x-mixed-replace; boundary=frame")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@main_bp.get("/live-inspection/ai-latest.jpg")
@login_required
def live_inspection_ai_latest():
    """Return newest complete annotated frame, or 204 when unchanged.

    A single JPEG response avoids keeping a long-lived MJPEG stream open while
    GPU inference is much slower than camera FPS. Never starts inference.
    """
    sequence, image = live_ai.latest_overlay()
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "X-BIKA-AI-Sequence": str(sequence),
    }
    if image is None:
        return Response(status=204, headers=headers)
    if request.args.get("seq") == str(sequence):
        return Response(status=204, headers=headers)
    return Response(image, mimetype="image/jpeg", headers=headers)


@main_bp.get("/live-inspection/api/ai/events/<event_id>/image")
@login_required
def live_inspection_event_image(event_id):
    if not (len(event_id) == 32 and all(c in "0123456789abcdef" for c in event_id)):
        abort(404)
    image = live_ai.event_preview(event_id, variant="mask" if request.args.get("view") == "mask" else "original")
    if image is None:
        abort(404)
    response = send_file(io.BytesIO(image), mimetype="image/jpeg")
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

# BIKA-LIVE-SESSION-HISTORY-V1
