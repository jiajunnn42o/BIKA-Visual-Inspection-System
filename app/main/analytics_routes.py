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


# BIKA_TEAM_PIPELINE_REVIEW_V3
# Team members may submit *human review feedback*; this does not give them
# account administration, settings or permission to alter original AI outputs.
def _can_quality_review():
    return str(getattr(current_user, "role", "")).strip().lower() in (
        "user", "admin", "superadmin"
    )


def _lookup_record(batch_id):
    return db.session.scalar(db.select(InspectionBatch).where(InspectionBatch.batch_id == batch_id))


@main_bp.route("/analytics", methods=["GET"])
@login_required
def analytics():
    return render_template("analytics.html", user=current_user, can_review=_can_quality_review())


@main_bp.route("/analytics/api/data", methods=["GET"])
@login_required
def analytics_data():
    # BIKA-UNIFIED-VIEWS-V1: same API and same Analytics cards, no second dashboard.
    from app.services.live_analytics_service import build_live_analytics
    from flask import current_app
    import sqlite3
    period = request.args.get("range", "30d")
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    summary = build_analytics_data(range_key=period, date_from=date_from,
                                   date_to=date_to, admin=_can_quality_review())
    try:
        summary['live'] = build_live_analytics(current_app.instance_path,
            current_user.get_id(), range_key=period,
            date_from=date_from, date_to=date_to)
    except (sqlite3.Error, OSError, ValueError) as exc:
        current_app.logger.warning('Live analytics unavailable: %s', exc)
        summary['live'] = {'sessions':0,'defect_observations':0,'classes':{},
                           'daily':[],'unavailable':True}
    return jsonify(ok=True, analytics=summary)


@main_bp.route("/analytics/api/review/<batch_id>", methods=["GET"])
@login_required
def analytics_review_detail(batch_id):
    if not _can_quality_review():
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
    if not _can_quality_review():
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
    corrected_class = str(data.get("corrected_class") or "").strip().lower()
    if not object_id or len(object_id) > 80 or len(note) > 400:
        return jsonify(ok=False, message="Invalid object ID or note (maximum 400 characters)."), 400
    if decision not in {"correct", "incorrect_mask", "incorrect_class", "false_positive"}:
        return jsonify(ok=False, message="Invalid review decision."), 400
    valid_classes = {"normal", "fractured", "too_short", "too_dark", "bent_snack"}
    if decision == "incorrect_class" and corrected_class not in valid_classes:
        return jsonify(ok=False, message="Select a valid corrected class."), 400
    if decision != "incorrect_class" and corrected_class:
        return jsonify(ok=False, message="Corrected class is only valid for incorrect classification."), 400
    try:
        result = json.loads(read_bytes(record.result_key).decode("utf-8"))
    except (OSError, ValueError, UnicodeError):
        return jsonify(ok=False, message="Saved detection results are unavailable."), 409
    valid_ids = {str(obj.get("object_id", "")) for obj in (result.get("objects") or []) if isinstance(obj, dict)}
    if object_id not in valid_ids:
        return jsonify(ok=False, message="Object not found in the original prediction."), 400
    if decision == "incorrect_class":
        original_obj = next((obj for obj in (result.get("objects") or [])
                             if isinstance(obj, dict) and str(obj.get("object_id", "")) == object_id), {})
        original_class = str(original_obj.get("class_name") or original_obj.get("display_name") or "").strip().lower().replace(" ", "_").replace("-", "_")
        if corrected_class == original_class:
            return jsonify(ok=False, message="Corrected class must differ from the predicted class."), 400
    # Namespaced human feedback on a persisted inspection record. No schema
    # migration and original result.json / model output remain unchanged.
    summary = deepcopy(record.summary_json or {})
    reviews = dict(summary.get("_human_reviews_v1") or {})
    previous = reviews.get(object_id) if isinstance(reviews.get(object_id), dict) else {}
    event = {
        "decision": decision, "note": note, "corrected_class": corrected_class if decision == "incorrect_class" else None,
        "reviewed_by": str(current_user.id),
        "reviewer_name": str(getattr(current_user, "username", "Reviewer"))[:100],
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    history = list(previous.get("history") or []) if previous else []
    if previous:
        history.append({key: previous.get(key) for key in ("decision", "note", "corrected_class", "reviewed_by", "reviewed_at")})
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


# BIKA_BULK_REVIEW_V1: save multiple human review decisions in a single commit.
# BIKA_BULK_REVIEW_CORRECTION_V1_7: allow deliberate corrections to saved reviews,
# preserving history and rejecting stale client versions.
@main_bp.route('/analytics/api/review/<batch_id>/bulk', methods=['POST'])
@login_required
def analytics_review_bulk_save(batch_id):
    # This endpoint intentionally reuses the team-review permission from v3.
    if not _can_quality_review():
        abort(403)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(ok=False, message='Invalid JSON request.'), 400
    ids = payload.get('object_ids')
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 500 or
            any(not isinstance(v, str) or not v.strip() or len(v) > 80 for v in ids) or
            len(ids) != len(set(ids))):
        return jsonify(ok=False, message='Choose 1–500 unique object IDs.'), 400
    review_mode=payload.get('review_mode','new')
    if review_mode not in ('new','correct_reviewed'):
        return jsonify(ok=False, message='Invalid bulk review mode.'), 400
    correction=review_mode=='correct_reviewed'
    expected_versions=payload.get('expected_reviewed_at') if correction else None
    if correction and (not isinstance(expected_versions,dict) or set(expected_versions)!=set(ids)
            or any(not isinstance(t,str) or not t or len(t)>80 for t in expected_versions.values())):
        return jsonify(ok=False, message='Saved review versions are required to make corrections. Refresh first.'), 400
    decision = payload.get('decision')
    if decision not in ('correct', 'incorrect_mask', 'incorrect_class', 'false_positive'):
        return jsonify(ok=False, message='Invalid review decision.'), 400
    note = payload.get('note', '')
    corrected_class = payload.get('corrected_class') or ''
    if not isinstance(note, str) or len(note) > 400 or not isinstance(corrected_class, str):
        return jsonify(ok=False, message='Invalid note or corrected class.'), 400
    corrected_class = corrected_class.strip().lower()
    allowed_classes = {'normal', 'fractured', 'too_short', 'too_dark', 'bent_snack'}
    if decision == 'incorrect_class':
        if corrected_class not in allowed_classes:
            return jsonify(ok=False, message='Select a corrected class.'), 400
    elif corrected_class:
        return jsonify(ok=False, message='Corrected class is only allowed for incorrect classification.'), 400
    record = _lookup_record(batch_id)
    if not record:
        abort(404)
    if record.source_type != 'image' or not record.result_key or not record.original_key:
        return jsonify(ok=False, message='Bulk review supports stored image inspections only.'), 409
    try:
        original = json.loads(read_bytes(record.result_key).decode('utf-8'))
    except (OSError, ValueError, UnicodeError, KeyError):
        current_app.logger.warning('Bulk review source unavailable for %s', batch_id)
        return jsonify(ok=False, message='Saved detection results are unavailable.'), 409
    objects = original.get('objects') or []
    if not isinstance(objects, list):
        return jsonify(ok=False, message='Malformed stored detection objects.'), 409
    objects_by_id = {
        str(o.get('object_id')): o
        for o in objects[:2000] if isinstance(o, dict) and o.get('object_id') is not None
    }
    invalid = [oid for oid in ids if oid not in objects_by_id]
    if invalid:
        return jsonify(ok=False, message='One or more objects no longer match saved predictions.'), 400
    if decision == 'incorrect_class':
        for oid in ids:
            source = objects_by_id[oid]
            source_class = str(source.get('class_name') or source.get('display_name') or '').strip().lower().replace(' ', '_').replace('-', '_')
            if source_class == corrected_class:
                return jsonify(ok=False, message=f'{oid}: corrected class must differ from original prediction.'), 400
    # Preserve first-time review behavior; correcting previously reviewed
    # objects requires the explicit mode and the versions shown to the user.
    summary = deepcopy(record.summary_json or {})
    reviews = dict(summary.get('_human_reviews_v1') or {})
    if correction:
        stale = [oid for oid in ids if not isinstance(reviews.get(oid),dict)
                 or str(reviews[oid].get('reviewed_at') or '') != expected_versions[oid]]
        if stale:
            return jsonify(ok=False, message='Some reviews were updated or removed since you opened this image. Reopen it and try again.'), 409
        accepted=list(ids)
        skipped=[]
    else:
        accepted = [oid for oid in ids if not isinstance(reviews.get(oid),dict)]
        skipped = [oid for oid in ids if oid not in accepted]
    if not accepted:
        response = jsonify(ok=True, count=0, skipped=skipped, reviews={})
        response.headers['Cache-Control'] = 'no-store'
        return response
    now = datetime.now(timezone.utc).isoformat()
    reviewed_by = str(current_user.id)
    reviewer_name = str(getattr(current_user, 'username', 'Reviewer'))[:100]
    new_entries = {}
    for oid in accepted:
        previous=reviews.get(oid) if correction else None
        history=list(previous.get('history') or []) if isinstance(previous,dict) and isinstance(previous.get('history') or [],list) else []
        if isinstance(previous,dict):
            history.append({key:previous.get(key) for key in ('decision','note','corrected_class','reviewed_by','reviewer_name','reviewed_at')})
        event = {
            'decision': decision,
            'note': note.strip(),
            'corrected_class': corrected_class if decision == 'incorrect_class' else None,
            'reviewed_by': reviewed_by,
            'reviewer_name': reviewer_name,
            'reviewed_at': now,
            'history': history[-50:],
        }
        reviews[oid] = event
        new_entries[oid] = event
    summary['_human_reviews_v1'] = reviews
    record.summary_json = summary
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Unable to save bulk review for %s', batch_id)
        return jsonify(ok=False, message='Unable to save bulk review. No review decisions committed.'), 500
    response = jsonify(ok=True, count=len(new_entries), skipped=skipped, reviews=new_entries)
    response.headers['Cache-Control'] = 'no-store'
    return response


# BIKA_ANALYTICS_PERIOD_MEMORY_V1: user-specific server-side date-range preference.
@main_bp.route("/analytics/api/period-preference", methods=["GET", "POST"])
@login_required
def analytics_period_preference():
    from app.services.analytics_period_preference_service import (
        get_period_preference, save_period_preference,
    )
    from sqlite3 import Error as SqliteError

    try:
        if request.method == "GET":
            pref = get_period_preference(current_user.id)
            response = jsonify(ok=True, preference=pref)
        else:
            payload = request.get_json(silent=True)
            try:
                pref = save_period_preference(current_user.id, payload)
            except ValueError as exc:
                return jsonify(ok=False, message=str(exc)), 400
            response = jsonify(ok=True, preference=pref)
        response.headers["Cache-Control"] = "no-store"
        return response
    except (SqliteError, OSError):
        current_app.logger.exception("Analytics date preference storage is unavailable")
        return jsonify(ok=False, message="Unable to save or load date preference"), 503


# BIKA-LIVE-ANALYTICS-V1: read-only, per-user, provisional Live Session insights.
@main_bp.get('/analytics/api/live-sessions')
@login_required
def analytics_live_sessions():
    from app.services.live_analytics_service import build_live_analytics
    import sqlite3
    try:
        summary = build_live_analytics(
            current_app.instance_path, current_user.get_id(),
            range_key=request.args.get('range', '30d'),
            date_from=request.args.get('from'),
            date_to=request.args.get('to'),
        )
        response = jsonify(ok=True, live=summary)
        response.headers['Cache-Control'] = 'private, no-store'
        return response
    except ValueError as exc:
        return jsonify(ok=False, message=str(exc)), 400
    except (sqlite3.Error, OSError):
        current_app.logger.exception('Unable to read Live session analytics')
        return jsonify(ok=False, message='Live session history temporarily unavailable'), 503


# BIKA-TREND-REVIEW-MASK-V1 Read-only per-account provisional history overlay.
@main_bp.get('/analytics/api/provisional')
@login_required
def analytics_provisional_data():
    from app.services.provisional_trend_service import build_provisional_views
    from flask import current_app
    import sqlite3
    try:
        output = build_provisional_views(
            current_app.instance_path, current_user.get_id(),
            range_key=request.args.get('range','30d'),
            date_from=request.args.get('from'),date_to=request.args.get('to'),
            include_review=_can_quality_review())
    except (sqlite3.Error, OSError, ValueError) as exc:
        current_app.logger.warning('Provisional Analytics unavailable: %s', exc)
        return jsonify(ok=False,message='Live/Video activity temporarily unavailable'),503
    return jsonify(ok=True, provisional=output)


# BIKA-COMBINED-TOTALS-V1-1 -- maintain official SPC separately; combine display totals.
_original_bika_analytics_builder = build_analytics_data

def build_analytics_data(*args, **kwargs):
    from app.services.unified_totals_service import merge_analytics_data
    result = _original_bika_analytics_builder(*args, **kwargs)
    return merge_analytics_data(result, current_user.get_id())

# BIKA-REVIEW-CORRECT-CLASS-V1_1
