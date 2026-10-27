"""BIKA Data Analytics and restricted image-mask verification endpoints."""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone

from flask import abort, jsonify, render_template, request, url_for, current_app
from flask_login import current_user, login_required

from app.extensions import db
from app.main import main_bp
from app.models.inspection_batch import InspectionBatch
from app.services.analytics_service import build_analytics_data
from app.services.storage_service import read_bytes


def _is_reviewer():
    return str(getattr(current_user, "role", "")) in ("admin", "superadmin")


def _lookup_record(batch_id):
    return db.session.scalar(db.select(InspectionBatch).where(InspectionBatch.batch_id == batch_id))


@main_bp.route("/analytics", methods=["GET"])
@login_required
def analytics():
    return render_template("analytics.html", user=current_user, can_review=_is_reviewer())


@main_bp.route("/analytics/api/data", methods=["GET"])
@login_required
def analytics_data():
    return jsonify(ok=True, analytics=build_analytics_data(
        range_key=request.args.get("range", "30d"),
        date_from=request.args.get("from"),
        date_to=request.args.get("to"),
        admin=_is_reviewer(),
    ))


@main_bp.route("/analytics/api/review/<batch_id>", methods=["GET"])
@login_required
def analytics_review_detail(batch_id):
    if not _is_reviewer():
        abort(403)
    record = _lookup_record(batch_id)
    if not record:
        abort(404)
    if record.source_type != "image" or not record.result_key or not record.original_key:
        return jsonify(ok=False, message="Mask selection is currently supported for stored image inspections only."), 409
    try:
        result = json.loads(read_bytes(record.result_key).decode("utf-8"))
    except (OSError, ValueError, UnicodeError, KeyError):
        current_app.logger.warning("Inspection result unavailable for review: %s", batch_id)
        return jsonify(ok=False, message="The stored inspection result is unavailable."), 404
    # Do not return arbitrary inference artifacts or source filesystem paths.
    objects = []
    for obj in (result.get("objects") or [])[:2000]:
        if not isinstance(obj, dict):
            continue
        objects.append({
            "object_id": str(obj.get("object_id", ""))[:80],
            "class_name": str(obj.get("display_name") or obj.get("class_name") or "Unknown")[:100],
            "decision": str(obj.get("decision") or "Unknown")[:80],
            "confidence": obj.get("class_confidence"),
            "detection_confidence": obj.get("detection_confidence"),
            "in_safe_zone": bool(obj.get("in_safe_zone")),
            "polygons": obj.get("polygons") or [],
            "bbox": obj.get("bbox") or {},
            "colour": str(obj.get("mask_colour") or "#8b2940")[:30],
        })
    image = result.get("image") or {}
    summary = record.summary_json or {}
    return jsonify(ok=True, detail={
        "batch_id": record.batch_id,
        "file_name": record.original_filename,
        "model_version": record.model_version,
        "image_url": url_for("main.inspection_media", object_key=record.original_key),
        "annotated_url": url_for("main.inspection_media", object_key=f"inspections/{record.batch_id}/annotated.webp"),
        "image": {"width": image.get("width"), "height": image.get("height")},
        "objects": objects,
        "reviews": summary.get("_human_reviews_v1") or {},
    })


@main_bp.route("/analytics/api/review/<batch_id>", methods=["POST"])
@login_required
def analytics_review_save(batch_id):
    if not _is_reviewer():
        abort(403)
    record = _lookup_record(batch_id)
    if not record:
        abort(404)
    if record.source_type != "image" or not record.result_key:
        return jsonify(ok=False, message="This inspection cannot be reviewed here."), 409
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(ok=False, message="Invalid request."), 400
    object_id = str(data.get("object_id") or "").strip()
    decision = str(data.get("decision") or "").strip()
    note = str(data.get("note") or "").strip()
    if not object_id or len(object_id) > 80 or len(note) > 400:
        return jsonify(ok=False, message="Invalid object ID or note (maximum 400 characters)."), 400
    if decision not in {"correct", "incorrect_mask", "incorrect_class", "false_positive"}:
        return jsonify(ok=False, message="Invalid review decision."), 400
    try:
        result = json.loads(read_bytes(record.result_key).decode("utf-8"))
    except (OSError, ValueError, UnicodeError):
        return jsonify(ok=False, message="Saved detection results are unavailable."), 409
    valid_ids = {str(obj.get("object_id", "")) for obj in (result.get("objects") or []) if isinstance(obj, dict)}
    if object_id not in valid_ids:
        return jsonify(ok=False, message="Object not found in the original prediction."), 400
    # Namespaced human feedback on a persisted inspection record. No schema
    # migration and original result.json / model output remain unchanged.
    summary = deepcopy(record.summary_json or {})
    reviews = dict(summary.get("_human_reviews_v1") or {})
    previous = reviews.get(object_id) if isinstance(reviews.get(object_id), dict) else {}
    event = {
        "decision": decision, "note": note,
        "reviewed_by": str(current_user.id),
        "reviewer_name": str(getattr(current_user, "username", "Reviewer"))[:100],
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    history = list(previous.get("history") or []) if previous else []
    if previous:
        history.append({key: previous.get(key) for key in ("decision", "note", "reviewed_by", "reviewed_at")})
    event["history"] = history[-50:]
    reviews[object_id] = event
    summary["_human_reviews_v1"] = reviews
    record.summary_json = summary
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to save review")
        return jsonify(ok=False, message="Could not save review. Please retry."), 500
    return jsonify(ok=True, review=event)
