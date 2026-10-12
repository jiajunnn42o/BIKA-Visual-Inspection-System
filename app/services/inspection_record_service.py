from __future__ import annotations

from datetime import datetime, timezone
from statistics import fmean
import uuid

from app.extensions import db
from app.models.inspection_batch import InspectionBatch
from app.services.inspection_artifact_service import save_inspection_artifacts


_CLASS_KEYS = (
    "normal",
    "too_dark",
    "too_short",
    "fractured",
    "bent_snack",
)


def _build_class_counts(result: dict) -> dict[str, int]:
    summary = result.get("summary") or {}

    counts = {
        key: 0
        for key in _CLASS_KEYS
    }

    counts["normal"] = int(
        summary.get("normal", 0)
        or 0
    )

    for item in result.get("defect_counts") or []:
        key = str(
            item.get("class_name", "")
        )

        if key in counts:
            counts[key] = int(
                item.get("count", 0)
                or 0
            )

    return counts


def _build_confidence_summary(result: dict) -> dict[str, float]:
    judged_objects = [
        item
        for item in (result.get("objects") or [])
        if item.get("in_safe_zone")
    ]

    class_values = [
        float(item["class_confidence"])
        for item in judged_objects
        if item.get("class_confidence") is not None
    ]

    detection_values = [
        float(item["detection_confidence"])
        for item in judged_objects
        if item.get("detection_confidence") is not None
    ]

    return {
        "average_class_confidence": (
            round(fmean(class_values), 6)
            if class_values
            else 0.0
        ),
        "average_detection_confidence": (
            round(fmean(detection_values), 6)
            if detection_values
            else 0.0
        ),
    }


def persist_completed_image_inspection(
    *,
    source_bytes: bytes,
    source_filename: str,
    result: dict,
    user_id: str | None,
) -> InspectionBatch:
    """
    Persist one completed real inspection.

    Database stores searchable/reporting metadata.
    Storage backend (local or B2) stores media/result artifacts.
    """

    model = result.get("model") or {}
    summary = dict(result.get("summary") or {})
    timing = dict(result.get("timing") or {})

    record = InspectionBatch(
        batch_id=(
            "PENDING-"
            + uuid.uuid4().hex
        ),
        inspection_date=datetime.now(timezone.utc),
        source_type="image",
        original_filename=source_filename,
        model_version=str(
            model.get(
                "version",
                "Not configured",
            )
        ),
        summary_json=summary,
        classes_json=_build_class_counts(result),
        confidence_json=_build_confidence_summary(result),
        timing_json=timing,
        created_by_user_id=(
            str(user_id)
            if user_id is not None
            else None
        ),
    )

    try:
        db.session.add(record)
        db.session.flush()

        record.batch_id = (
            f"BATCH-{record.id:06d}"
        )

        artifacts = save_inspection_artifacts(
            batch_id=record.batch_id,
            source_bytes=source_bytes,
            source_filename=source_filename,
            source_type="image",
            result=result,
        )

        record.storage_backend = str(
            artifacts.get(
                "storage_backend",
                "local",
            )
        )
        record.original_key = artifacts.get("original_key")
        record.preview_key = artifacts.get("preview_key")
        record.result_key = artifacts.get("result_key")
        record.manifest_key = artifacts.get("manifest_key")

        db.session.commit()

        return record

    except Exception:
        db.session.rollback()
        raise
