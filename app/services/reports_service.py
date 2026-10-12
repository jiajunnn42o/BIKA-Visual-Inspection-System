from __future__ import annotations

from typing import Any

from flask import url_for
from werkzeug.routing import BuildError

from app.extensions import db
from app.models.inspection_batch import InspectionBatch


DEFECT_CLASS_ORDER = (
    "too_dark",
    "too_short",
    "fractured",
    "bent_snack",
)

CLASS_LABELS = {
    "normal": "Normal",
    "too_dark": "Too Dark",
    "too_short": "Too Short",
    "fractured": "Fractured",
    "bent_snack": "Bent Snack",
}

CLASS_COLOURS = {
    "normal": "#7FA06F",
    "too_dark": "#D69A45",
    "too_short": "#8A69A8",
    "fractured": "#C65358",
    "bent_snack": "#6287B8",
}


def _round_percent(
    numerator: int,
    denominator: int,
) -> float:
    if not denominator:
        return 0.0

    return round(
        (numerator / denominator) * 100,
        1,
    )


def _report_status(
    good_ratio: float,
) -> tuple[str, str]:
    if good_ratio >= 85:
        return (
            "PASS",
            "pass",
        )

    if good_ratio < 50:
        return (
            "FAIL",
            "fail",
        )

    return (
        "REVIEW REQUIRED",
        "review",
    )


def _date_time_string(value) -> str:
    if value is None:
        return ""

    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


def _date_display(value) -> str:
    text = _date_time_string(value)

    return (
        text
        .replace("T", " ")
        [:16]
    )


def _media_url(
    object_key: str | None,
) -> str | None:
    if not object_key:
        return None

    try:
        return url_for(
            "main.inspection_media",
            object_key=object_key,
        )

    except BuildError:
        # media_routes.py has not been registered yet.
        # Reports can still show the real inspection row.
        return None


def _build_batch_row(
    record: InspectionBatch,
) -> dict[str, Any]:
    summary = dict(
        record.summary_json
        or {}
    )

    classes = dict(
        record.classes_json
        or {}
    )

    confidence = dict(
        record.confidence_json
        or {}
    )

    timing = dict(
        record.timing_json
        or {}
    )

    total = int(
        summary.get("judged", 0)
        or 0
    )

    good = int(
        summary.get("normal", 0)
        or 0
    )

    bad = int(
        summary.get("defect", 0)
        or 0
    )

    good_ratio = _round_percent(
        good,
        total,
    )

    status_label, status_key = (
        _report_status(
            good_ratio
        )
    )

    source_type = str(
        record.source_type
        or "image"
    ).lower()

    class_breakdown = [
        {
            "key": class_key,
            "label": CLASS_LABELS[class_key],
            "colour": CLASS_COLOURS[class_key],
            "count": int(
                classes.get(
                    class_key,
                    0,
                )
                or 0
            ),
        }
        for class_key in (
            "normal",
            *DEFECT_CLASS_ORDER,
        )
    ]

    total_ms = float(
        timing.get("total_ms", 0)
        or 0
    )

    return {
        "batch_id":
            record.batch_id,
        "file_name":
            record.original_filename,
        "date_time":
            _date_time_string(
                record.inspection_date
            ),
        "date_display":
            _date_display(
                record.inspection_date
            ),
        "source_type":
            source_type,
        "total":
            total,
        "good":
            good,
        "bad":
            bad,
        "good_ratio":
            good_ratio,
        "status":
            status_label,
        "status_key":
            status_key,
        "model_version":
            str(
                record.model_version
                or "—"
            ),
        "detected_boxes":
            int(
                summary.get(
                    "detected_boxes",
                    0,
                )
                or 0
            ),
        "sam2_masks":
            int(
                summary.get(
                    "sam2_masks",
                    0,
                )
                or 0
            ),
        "edge_not_judged":
            int(
                summary.get(
                    "edge_not_judged",
                    0,
                )
                or 0
            ),
        "average_class_confidence":
            round(
                float(
                    confidence.get(
                        "average_class_confidence",
                        0,
                    )
                    or 0
                )
                * 100,
                1,
            ),
        "average_detection_confidence":
            round(
                float(
                    confidence.get(
                        "average_detection_confidence",
                        0,
                    )
                    or 0
                )
                * 100,
                1,
            ),
        "total_runtime_seconds":
            round(
                total_ms / 1000,
                1,
            ),
        "classes":
            class_breakdown,
        "storage_backend":
            record.storage_backend,
        "preview_url":
            _media_url(
                record.preview_key
            ),
        "original_url":
            _media_url(
                record.original_key
            ),
        "annotated_url":
            _media_url(
                (
                    f"inspections/"
                    f"{record.batch_id}/"
                    "annotated.webp"
                )
                if source_type
                ==
                "image"
                else None
            ),
        "result_url":
            _media_url(
                record.result_key
            ),
    }


def build_reports_data() -> dict[str, Any]:
    records = list(
        db.session.scalars(
            db.select(
                InspectionBatch
            ).order_by(
                InspectionBatch.inspection_date.desc(),
                InspectionBatch.id.desc(),
            )
        ).all()
    )

    batch_rows = [
        _build_batch_row(record)
        for record in records
    ]

    defect_rows = []

    for batch_row in batch_rows:
        class_lookup = {
            item["key"]: item
            for item in batch_row["classes"]
        }

        for class_key in DEFECT_CLASS_ORDER:
            class_item = class_lookup[
                class_key
            ]

            count = int(
                class_item["count"]
            )

            if count <= 0:
                continue

            defect_rows.append(
                {
                    "event_id": (
                        f"{batch_row['batch_id']}"
                        f"-{class_key}"
                    ),
                    "batch_id":
                        batch_row["batch_id"],
                    "file_name":
                        batch_row["file_name"],
                    "date_time":
                        batch_row["date_time"],
                    "date_display":
                        batch_row["date_display"],
                    "source_type":
                        batch_row["source_type"],
                    "preview_url":
                        batch_row["preview_url"],
                    "original_url":
                        batch_row["original_url"],
                    "annotated_url":
                        batch_row["annotated_url"],
                    "class_key":
                        class_key,
                    "class_name":
                        CLASS_LABELS[class_key],
                    "colour":
                        CLASS_COLOURS[class_key],
                    "count":
                        count,
                    "ratio":
                        _round_percent(
                            count,
                            batch_row["total"],
                        ),
                    "batch_total":
                        batch_row["total"],
                    "batch_good":
                        batch_row["good"],
                    "batch_bad":
                        batch_row["bad"],
                    "good_ratio":
                        batch_row["good_ratio"],
                    "batch_status":
                        batch_row["status"],
                    "batch_status_key":
                        batch_row["status_key"],
                    "model_version":
                        batch_row["model_version"],
                    "average_class_confidence":
                        batch_row[
                            "average_class_confidence"
                        ],
                }
            )

    return {
        "source": "database",
        "is_simulated": False,
        "batch_count": len(batch_rows),
        "batches": batch_rows,
        "defect_events": defect_rows,
        "export_fields": [
            {
                "key": "file_name",
                "label": "File Name",
            },
            {
                "key": "date_display",
                "label": "Date / Time",
            },
            {
                "key": "total",
                "label": "Total",
            },
            {
                "key": "good",
                "label": "GOOD",
            },
            {
                "key": "bad",
                "label": "BAD",
            },
            {
                "key": "good_ratio",
                "label": "Good Ratio",
            },
            {
                "key": "status",
                "label": "Status",
            },
            {
                "key": "model_version",
                "label": "Model Version",
            },
            {
                "key": "average_class_confidence",
                "label": "Avg Class Confidence",
            },
            {
                "key": "average_detection_confidence",
                "label": "Avg Detection Confidence",
            },
            {
                "key": "total_runtime_seconds",
                "label": "Runtime (s)",
            },
        ],
    }
