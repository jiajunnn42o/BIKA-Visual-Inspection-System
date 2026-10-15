"""Isolated BIKA Live Stream Inspection phase-one routes."""
from __future__ import annotations

import io
import time
from datetime import datetime

from flask import Response, abort, jsonify, render_template, request, send_file, stream_with_context
from flask_login import current_user, login_required

from app.main import main_bp
from app.services.live_camera_service import live_camera


CONTROL_ROLES = {"admin", "superadmin"}


def can_control():
    return current_user.is_authenticated and current_user.role in CONTROL_ROLES


@main_bp.get("/live-inspection")
@login_required
def live_inspection():
    return render_template("live_stream.html", can_control_camera=can_control())


@main_bp.get("/live-inspection/api/status")
@login_required
def live_inspection_status():
    return jsonify(ok=True, camera=live_camera.status(), can_control=can_control())


@main_bp.post("/live-inspection/api/connect")
@login_required
def live_inspection_connect():
    if not can_control():
        abort(403)
    payload = request.get_json(silent=True) or {}
    stream = payload.get("stream", "main")
    if not isinstance(stream, str):
        return jsonify(ok=False, message="Invalid stream type."), 400
    ok, message = live_camera.connect(stream)
    return jsonify(ok=ok, message=message, camera=live_camera.status()), 200 if ok else 409


@main_bp.post("/live-inspection/api/disconnect")
@login_required
def live_inspection_disconnect():
    if not can_control():
        abort(403)
    live_camera.disconnect()
    return jsonify(ok=True, camera=live_camera.status())


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
