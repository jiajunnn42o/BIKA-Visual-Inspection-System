from __future__ import annotations

import json

from collections import defaultdict
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from flask import current_app


CLASS_ORDER = (
    "normal",
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
    "normal": "#7DA276",
    "too_dark": "#D6973D",
    "too_short": "#8B6AAB",
    "fractured": "#C65358",
    "bent_snack": "#6287B8",
}


def _dataset_path() -> Path:
    return (
        Path(current_app.root_path).parent
        / "data"
        / "mock"
        / "inspection_batches.json"
    )


@lru_cache(maxsize=4)
def _load_dataset_cached(
    path_string: str,
    modified_ns: int,
) -> dict[str, Any]:
    path = Path(path_string)

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            "Dashboard mock dataset must be a JSON object."
        )

    batches = data.get("batches")

    if not isinstance(batches, list):
        raise ValueError(
            "Dashboard mock dataset is missing the 'batches' list."
        )

    return data


def load_dashboard_dataset() -> dict[str, Any]:
    path = _dataset_path()

    if not path.exists():
        raise FileNotFoundError(
            f"Dashboard mock data was not found at {path}"
        )

    stat = path.stat()

    return _load_dataset_cached(
        str(path),
        stat.st_mtime_ns,
    )


def _parse_datetime(
    value: str,
) -> datetime:
    return datetime.fromisoformat(
        str(value)
    )


def _parse_date_or_none(
    value: str | None,
) -> date | None:
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _dataset_date_bounds(
    batches: list[dict],
) -> tuple[date | None, date | None]:
    if not batches:
        return (None, None)

    dates = [
        _parse_datetime(
            batch["inspection_date"]
        ).date()
        for batch in batches
    ]

    return (
        min(dates),
        max(dates),
    )


def _resolve_filter_dates(
    *,
    range_key: str,
    custom_from: str | None,
    custom_to: str | None,
    batches: list[dict],
) -> tuple[date | None, date | None, str, str]:
    minimum_date, maximum_date = (
        _dataset_date_bounds(batches)
    )

    if (
        minimum_date is None
        or maximum_date is None
    ):
        return (
            None,
            None,
            "No data",
            "all",
        )

    range_key = (
        range_key or "all"
    ).strip().lower()

    if range_key == "7d":
        start_date = max(
            maximum_date - timedelta(days=6),
            minimum_date,
        )

        return (
            start_date,
            maximum_date,
            "Last 7 days",
            "7d",
        )

    if range_key == "30d":
        start_date = max(
            maximum_date - timedelta(days=29),
            minimum_date,
        )

        return (
            start_date,
            maximum_date,
            "Last 30 days",
            "30d",
        )

    if range_key == "custom":
        start_date = (
            _parse_date_or_none(custom_from)
            or minimum_date
        )

        end_date = (
            _parse_date_or_none(custom_to)
            or maximum_date
        )

        if start_date > end_date:
            start_date, end_date = (
                end_date,
                start_date,
            )

        start_date = max(
            start_date,
            minimum_date,
        )

        end_date = min(
            end_date,
            maximum_date,
        )

        label = (
            f"{start_date.strftime('%d %b %Y')}"
            " – "
            f"{end_date.strftime('%d %b %Y')}"
        )

        return (
            start_date,
            end_date,
            label,
            "custom",
        )

    return (
        minimum_date,
        maximum_date,
        "All runs to date",
        "all",
    )


def _filter_batches(
    batches: list[dict],
    *,
    start_date: date | None,
    end_date: date | None,
) -> list[dict]:
    if (
        start_date is None
        or end_date is None
    ):
        return []

    filtered = []

    for batch in batches:
        batch_date = (
            _parse_datetime(
                batch["inspection_date"]
            ).date()
        )

        if (
            start_date
            <= batch_date
            <= end_date
        ):
            filtered.append(batch)

    return filtered


def _safe_divide(
    numerator: float,
    denominator: float,
) -> float:
    if not denominator:
        return 0.0

    return numerator / denominator


def _build_daily_trend(
    batches: list[dict],
) -> list[dict]:
    grouped = defaultdict(
        lambda: {
            "judged": 0,
            "normal": 0,
            "defect": 0,
            "batches": 0,
        }
    )

    for batch in batches:
        batch_date = (
            _parse_datetime(
                batch["inspection_date"]
            ).date()
        )

        summary = batch["summary"]
        bucket = grouped[batch_date]

        bucket["judged"] += int(
            summary.get("judged", 0)
        )
        bucket["normal"] += int(
            summary.get("normal", 0)
        )
        bucket["defect"] += int(
            summary.get("defect", 0)
        )
        bucket["batches"] += 1

    trend = []

    for day in sorted(grouped):
        bucket = grouped[day]
        judged = bucket["judged"]

        yield_percent = (
            _safe_divide(
                bucket["normal"],
                judged,
            )
            * 100
        )

        defect_percent = (
            _safe_divide(
                bucket["defect"],
                judged,
            )
            * 100
        )

        trend.append(
            {
                "date": day.isoformat(),
                "label": day.strftime("%d %b"),
                "batches": bucket["batches"],
                "judged": judged,
                "yield_percent": round(
                    yield_percent,
                    1,
                ),
                "defect_percent": round(
                    defect_percent,
                    1,
                ),
            }
        )

    return trend


def build_dashboard_data(
    *,
    range_key: str = "all",
    custom_from: str | None = None,
    custom_to: str | None = None,
) -> dict[str, Any]:
    dataset = load_dashboard_dataset()

    dataset_info = (
        dataset.get("dataset_info")
        or {}
    )

    all_batches = (
        dataset.get("batches")
        or []
    )

    (
        start_date,
        end_date,
        filter_label,
        resolved_range,
    ) = _resolve_filter_dates(
        range_key=range_key,
        custom_from=custom_from,
        custom_to=custom_to,
        batches=all_batches,
    )

    batches = _filter_batches(
        all_batches,
        start_date=start_date,
        end_date=end_date,
    )

    targets = (
        dataset_info.get("targets")
        or {}
    )

    target_yield = float(
        targets.get(
            "yield_rate_percent",
            85.0,
        )
    )
    target_defect = float(
        targets.get(
            "defect_rate_percent",
            15.0,
        )
    )
    target_batch_pass = float(
        targets.get(
            "batch_pass_rate_percent",
            80.0,
        )
    )

    total_batches = len(batches)

    total_products = sum(
        int(
            batch["summary"].get(
                "judged",
                0,
            )
        )
        for batch in batches
    )

    normal = sum(
        int(
            batch["summary"].get(
                "normal",
                0,
            )
        )
        for batch in batches
    )

    defect = sum(
        int(
            batch["summary"].get(
                "defect",
                0,
            )
        )
        for batch in batches
    )

    total_detected = sum(
        int(
            batch["summary"].get(
                "detected_boxes",
                0,
            )
        )
        for batch in batches
    )

    total_masks = sum(
        int(
            batch["summary"].get(
                "sam2_masks",
                0,
            )
        )
        for batch in batches
    )

    edge_not_judged = sum(
        int(
            batch["summary"].get(
                "edge_not_judged",
                0,
            )
        )
        for batch in batches
    )

    batch_pass_count = sum(
        1
        for batch in batches
        if bool(
            batch["summary"].get(
                "batch_pass",
                False,
            )
        )
    )

    overall_yield = (
        _safe_divide(
            normal,
            total_products,
        )
        * 100
    )

    defect_rate = (
        _safe_divide(
            defect,
            total_products,
        )
        * 100
    )

    batch_pass_rate = (
        _safe_divide(
            batch_pass_count,
            total_batches,
        )
        * 100
    )

    class_totals = {
        class_name: sum(
            int(
                (
                    batch.get("classes")
                    or {}
                ).get(
                    class_name,
                    0,
                )
            )
            for batch in batches
        )
        for class_name in CLASS_ORDER
    }

    composition = []

    for class_name in CLASS_ORDER:
        count = class_totals[class_name]

        percent = (
            _safe_divide(
                count,
                total_products,
            )
            * 100
        )

        composition.append(
            {
                "key": class_name,
                "label":
                    CLASS_LABELS[
                        class_name
                    ],
                "colour":
                    CLASS_COLOURS[
                        class_name
                    ],
                "count": count,
                "percent": round(
                    percent,
                    1,
                ),
            }
        )

    weighted_class_confidence = sum(
        float(
            (
                batch.get("confidence")
                or {}
            ).get(
                "average_class_confidence",
                0.0,
            )
        )
        *
        int(
            (
                batch.get("summary")
                or {}
            ).get(
                "judged",
                0,
            )
        )
        for batch in batches
    )

    weighted_detection_confidence = sum(
        float(
            (
                batch.get("confidence")
                or {}
            ).get(
                "average_detection_confidence",
                0.0,
            )
        )
        *
        int(
            (
                batch.get("summary")
                or {}
            ).get(
                "judged",
                0,
            )
        )
        for batch in batches
    )

    average_class_confidence = (
        _safe_divide(
            weighted_class_confidence,
            total_products,
        )
    )

    average_detection_confidence = (
        _safe_divide(
            weighted_detection_confidence,
            total_products,
        )
    )

    total_runtime_ms = sum(
        int(
            (
                batch.get("timing")
                or {}
            ).get(
                "total_ms",
                0,
            )
        )
        for batch in batches
    )

    average_runtime_ms = (
        _safe_divide(
            total_runtime_ms,
            total_batches,
        )
    )

    average_products_per_batch = (
        _safe_divide(
            total_products,
            total_batches,
        )
    )

    trend = _build_daily_trend(
        batches
    )

    date_bounds = (
        _dataset_date_bounds(
            all_batches
        )
    )

    if total_batches:
        direction = (
            "above"
            if overall_yield
            >= target_yield
            else
            "below"
        )

        status_sentence = (
            f"Across {total_batches:,} batches and "
            f"{total_products:,} products inspected, "
            f"overall yield is {overall_yield:.1f}%, "
            f"{abs(overall_yield - target_yield):.1f}% "
            f"{direction} the {target_yield:.0f}% target."
        )
    else:
        status_sentence = (
            "No inspection batches are available "
            "for the selected period."
        )

    return {
        "source": "mock",
        "is_simulated": bool(
            dataset_info.get(
                "is_simulated",
                True,
            )
        ),
        "filter": {
            "range": resolved_range,
            "label": filter_label,
            "from": (
                start_date.isoformat()
                if start_date
                else ""
            ),
            "to": (
                end_date.isoformat()
                if end_date
                else ""
            ),
            "minimum_date": (
                date_bounds[0].isoformat()
                if date_bounds[0]
                else ""
            ),
            "maximum_date": (
                date_bounds[1].isoformat()
                if date_bounds[1]
                else ""
            ),
        },
        "summary_sentence":
            status_sentence,
        "kpi": {
            "total_batches":
                total_batches,
            "total_products":
                total_products,
            "normal":
                normal,
            "defect":
                defect,
            "yield_percent":
                round(
                    overall_yield,
                    1,
                ),
            "defect_percent":
                round(
                    defect_rate,
                    1,
                ),
            "batch_pass_count":
                batch_pass_count,
            "batch_pass_percent":
                round(
                    batch_pass_rate,
                    1,
                ),
            "yield_gap":
                round(
                    overall_yield
                    -
                    target_yield,
                    1,
                ),
            "defect_gap":
                round(
                    defect_rate
                    -
                    target_defect,
                    1,
                ),
            "batch_pass_gap":
                round(
                    batch_pass_rate
                    -
                    target_batch_pass,
                    1,
                ),
        },
        "targets": {
            "yield_percent":
                round(
                    target_yield,
                    1,
                ),
            "defect_percent":
                round(
                    target_defect,
                    1,
                ),
            "batch_pass_percent":
                round(
                    target_batch_pass,
                    1,
                ),
        },
        "composition":
            composition,
        "processing": {
            "detected_boxes":
                total_detected,
            "sam2_masks":
                total_masks,
            "edge_not_judged":
                edge_not_judged,
            "total_runtime_ms":
                int(
                    total_runtime_ms
                ),
            "average_runtime_ms":
                int(
                    round(
                        average_runtime_ms
                    )
                ),
            "average_class_confidence":
                round(
                    average_class_confidence,
                    3,
                ),
            "average_detection_confidence":
                round(
                    average_detection_confidence,
                    3,
                ),
        },
        "cumulative": {
            "average_products_per_batch":
                round(
                    average_products_per_batch,
                    1,
                ),
            "average_class_confidence":
                round(
                    average_class_confidence,
                    3,
                ),
            "average_detection_confidence":
                round(
                    average_detection_confidence,
                    3,
                ),
        },
        "trend":
            trend,
        "model_versions":
            sorted(
                {
                    str(
                        batch.get(
                            "model_version"
                        )
                        or
                        "—"
                    )
                    for batch in batches
                }
            ),
    }
