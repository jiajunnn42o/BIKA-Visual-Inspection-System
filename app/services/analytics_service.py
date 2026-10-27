"""Real, inspection-run based quality analytics for the BIKA website.

No synthetic data. Forecasts are conditional on adequate daily history and
are explicitly labelled experimental estimates, not validated predictions.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from math import exp, log, sqrt
from statistics import mean

from flask import url_for

from app.extensions import db
from app.models.inspection_batch import InspectionBatch
from app.models.user import User
from app.services.dashboard_service import _dashboard_targets

CLASS_COLORS = {
    "too_dark": "#cf9458", "too_short": "#8b77b2",
    "fractured": "#c55e64", "bent_snack": "#6686a2",
}
CLASS_NAMES = {
    "too_dark": "Too Dark", "too_short": "Too Short",
    "fractured": "Fractured", "bent_snack": "Bent Snack",
}


def _n(value, default=0):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return default


def _flt(value):
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _record_date(record):
    value = record.inspection_date or record.created_at
    return value.date() if value else date.today()


def _parse_date(text):
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def _window(range_key, date_from, date_to):
    now = datetime.now(timezone.utc).date()
    if range_key == "7d":
        return now - timedelta(days=6), now, "Last 7 days"
    if range_key == "90d":
        return now - timedelta(days=89), now, "Last 90 days"
    if range_key == "all":
        return None, None, "All time"
    if range_key == "custom":
        left, right = _parse_date(date_from), _parse_date(date_to)
        if left and right and left <= right and (right - left).days <= 3650:
            return left, right, f"{left.isoformat()} – {right.isoformat()}"
    return now - timedelta(days=29), now, "Last 30 days"


def _pct(numerator, denominator):
    return round(100 * numerator / denominator, 1) if denominator else None


def _confidence_interval(good, total):
    """Approximate central 95% interval for Beta(1+good, 1+bad)."""
    if not total:
        return None
    a, b = good + 1, total - good + 1
    centre = a / (a + b)
    sigma = sqrt(a * b / (((a + b) ** 2) * (a + b + 1)))
    return {
        "mean": round(centre * 100, 2),
        "lower": round(max(0, centre - 1.96 * sigma) * 100, 2),
        "upper": round(min(1, centre + 1.96 * sigma) * 100, 2),
        "prior": "Beta(1, 1)",
        "method": "Normal approximation to Beta posterior (95%)",
    }


def _weighted_forecast(daily):
    """Conservative experimental trend on logit-rate, weighted by sample size.

    Data gate intentionally strict; the interval is a heuristic uncertainty
    range, not a calibrated statistical prediction interval.
    """
    rows = [r for r in daily if r["judged"] > 0]
    total = sum(r["judged"] for r in rows)
    span = (date.fromisoformat(rows[-1]["date"]) - date.fromisoformat(rows[0]["date"])).days if len(rows) > 1 else 0
    minimum = {"days": 14, "observations": 300, "span_days": 20}
    if len(rows) < 14 or total < 300 or span < 20:
        return {
            "available": False,
            "reason": "Forecasting needs at least 14 days with inspections, 300 judged observations, and 20 calendar days of history.",
            "required": minimum,
            "progress": {"days": len(rows), "observations": total, "span_days": span},
            "method": "Weighted logit-linear time-series regression",
        }
    # Restrict to latest 60 observed calendar days to reflect recent process.
    rows = [r for r in rows if date.fromisoformat(r["date"]) >= date.fromisoformat(rows[-1]["date"]) - timedelta(days=59)]
    start = date.fromisoformat(rows[0]["date"])
    xs = [(date.fromisoformat(r["date"]) - start).days for r in rows]
    ws = [r["judged"] for r in rows]
    ys = [log(((r["defect"] + 0.5) / (r["judged"] + 1)) / (1 - ((r["defect"] + 0.5) / (r["judged"] + 1)))) for r in rows]
    sw = sum(ws)
    mx = sum(w * x for w, x in zip(ws, xs)) / sw
    my = sum(w * y for w, y in zip(ws, ys)) / sw
    denom = sum(w * (x - mx) ** 2 for w, x in zip(ws, xs))
    slope = (sum(w * (x - mx) * (y - my) for w, x, y in zip(ws, xs, ys)) / denom) if denom else 0.0
    intercept = my - slope * mx
    residual = sqrt(sum(w * (y - (intercept + slope * x)) ** 2 for w, x, y in zip(ws, xs, ys)) / sw)
    # Wider uncertainty farther from last data point, with conservative floor.
    residual = max(0.18, residual)
    last = date.fromisoformat(rows[-1]["date"])
    points = []
    for ahead in range(1, 8):
        x = (last - start).days + ahead
        z = max(-15, min(15, intercept + slope * x))
        width = 1.28 * residual * sqrt(1 + ahead / 7)
        transform = lambda val: 100 / (1 + exp(-max(-15, min(15, val))))
        points.append({
            "date": (last + timedelta(days=ahead)).isoformat(),
            "predicted": round(transform(z), 1),
            "lower": round(transform(z - width), 1),
            "upper": round(transform(z + width), 1),
        })
    return {
        "available": True, "points": points,
        "method": "Weighted logit-linear time-series regression",
        "qualification": "Experimental trend only. Shaded range is an uncalibrated residual-based uncertainty band; validate with held-out dates before operational use.",
        "training_days": len(rows), "training_observations": sum(ws),
    }


def _candidate(record):
    summary = record.summary_json or {}
    conf = record.confidence_json or {}
    judged = _n(summary.get("judged"))
    if not judged:
        return []
    reasons = []
    masks = summary.get("sam2_masks")
    if masks is not None and _n(masks) < judged:
        reasons.append("Fewer masks than judged objects")
    detected = summary.get("detected_boxes")
    if detected is not None and _n(detected) < judged:
        reasons.append("Detection count mismatch")
    c = _flt(conf.get("average_class_confidence"))
    if c is not None and 0 < c < 0.75:
        reasons.append("Low average classification confidence")
    edge = _n(summary.get("edge_not_judged"))
    if edge >= 1:
        reasons.append("Edge objects excluded from judgement")
    reviews = summary.get("_human_reviews_v1") or {}
    if any(isinstance(v, dict) and v.get("decision") in ("incorrect_mask", "incorrect_class", "false_positive") for v in reviews.values()):
        reasons.append("Human correction recorded")
    return reasons


def _media(key):
    return url_for("main.inspection_media", object_key=key) if key else None


def build_analytics_data(*, range_key="30d", date_from=None, date_to=None, admin=False):
    start, end, label = _window(range_key, date_from, date_to)
    query = db.select(InspectionBatch).order_by(InspectionBatch.inspection_date.asc(), InspectionBatch.id.asc())
    records = db.session.scalars(query).all()
    records = [r for r in records if (start is None or _record_date(r) >= start) and (end is None or _record_date(r) <= end)]
    targets = _dashboard_targets()
    good, judged, meet = 0, 0, 0
    defect_counts = defaultdict(int)
    daily = defaultdict(lambda: {"normal": 0, "defect": 0, "judged": 0, "inspections": 0})
    shifts = defaultdict(lambda: {"normal": 0, "judged": 0, "inspections": 0})
    author_ids = {str(r.created_by_user_id) for r in records if r.created_by_user_id}
    people = {}
    if author_ids:
        valid_ids = []
        for raw_id in author_ids:
            try:
                valid_ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue
        if valid_ids:
            authors_query = db.select(User).where(User.id.in_(valid_ids))
            for person in db.session.scalars(authors_query).all():
                people[str(person.id)] = (person.shift or "").strip()
    anomalies = []
    review_decisions = {"correct": 0, "false_positive": 0, "incorrect_mask": 0, "incorrect_class": 0}
    for r in records:
        s = r.summary_json or {}
        n = _n(s.get("judged"))
        g = min(n, _n(s.get("normal")))
        good += g
        judged += n
        if n and g / n * 100 >= targets["batch_pass_rate_percent"]:
            meet += 1
        day = _record_date(r).isoformat()
        daily[day]["judged"] += n
        daily[day]["normal"] += g
        daily[day]["defect"] += (n - g)
        daily[day]["inspections"] += 1
        cls = r.classes_json or {}
        for key in CLASS_NAMES:
            defect_counts[key] += _n(cls.get(key))
        shift = people.get(str(r.created_by_user_id), "")
        if shift:
            shifts[shift]["judged"] += n
            shifts[shift]["normal"] += g
            shifts[shift]["inspections"] += 1
        if admin:
            human_reviews = (r.summary_json or {}).get("_human_reviews_v1") or {}
            if isinstance(human_reviews, dict):
                for decision_row in human_reviews.values():
                    if isinstance(decision_row, dict):
                        decision = decision_row.get("decision")
                        if decision in review_decisions:
                            review_decisions[decision] += 1
            reasons = _candidate(r)
            if reasons:
                reviews = (r.summary_json or {}).get("_human_reviews_v1") or {}
                anomalies.append({
                    "batch_id": r.batch_id, "file_name": r.original_filename,
                    "source_type": r.source_type, "date": day,
                    "model_version": r.model_version, "judged": n,
                    "reasons": reasons[:3], "reviewed": sum(1 for v in reviews.values() if isinstance(v, dict)),
                    "preview_url": _media(r.preview_key),
                    "reviewable": bool(r.source_type == "image" and r.result_key and r.original_key),
                })
    points = []
    # Represent zero-data gaps as missing rates. The chart draws gaps rather
    # than interpreting a zero-inspection day as 0% yield.
    for date_key in sorted(daily):
        d = daily[date_key]
        p = (d["normal"] / d["judged"]) if d["judged"] else None
        pbar = good / judged if judged else 0
        limit = 3 * sqrt(max(0, pbar * (1 - pbar) / d["judged"])) if d["judged"] else None
        points.append({
            "date": date_key, **d,
            "yield_rate": _pct(d["normal"], d["judged"]),
            "defect_rate": _pct(d["defect"], d["judged"]),
            "lcl": round(max(0, pbar - limit) * 100, 1) if limit is not None else None,
            "ucl": round(min(1, pbar + limit) * 100, 1) if limit is not None else None,
        })
    # Seven-observed-day rolling ratio, weighted by judged count.
    for index, item in enumerate(points):
        past = points[max(0, index - 6):index + 1]
        denom = sum(v["judged"] for v in past)
        item["rolling_yield"] = _pct(sum(v["normal"] for v in past), denom)
    anomalies.reverse()
    recent_image_runs = []
    if admin:
        for r in reversed(records):
            if r.source_type != "image" or not r.result_key or not r.original_key:
                continue
            human_reviews = (r.summary_json or {}).get("_human_reviews_v1") or {}
            recent_image_runs.append({
                "batch_id": r.batch_id, "file_name": r.original_filename,
                "source_type": r.source_type, "date": _record_date(r).isoformat(),
                "model_version": r.model_version,
                "judged": _n((r.summary_json or {}).get("judged")),
                "reasons": _candidate(r),
                "reviewed": len(human_reviews),
                "preview_url": _media(r.preview_key), "reviewable": True,
            })
            if len(recent_image_runs) >= 40:
                break
    series = points[-90:]
    return {
        "filter": {"range": range_key, "label": label, "from": start.isoformat() if start else None, "to": end.isoformat() if end else None, "time_basis": "Inspection date (UTC)"},
        "kpi": {
            "good_rate": _pct(good, judged), "defect_rate": _pct(judged - good, judged),
            "meeting_standard_rate": _pct(meet, len(records)), "meeting_standard_count": meet,
            "inspections": len(records), "judged": judged, "normal": good, "defects": judged - good,
            "target_good": targets["yield_rate_percent"], "pass_requirement": targets["batch_pass_rate_percent"],
        },
        "trend": series, "trend_truncated": len(points) > len(series),
        "spc": {"pbar": _pct(good, judged), "method": "3σ binomial p-chart; daily sample-size-adjusted limits", "has_data": bool(judged)},
        "defects": [{"key": k, "name": CLASS_NAMES[k], "color": CLASS_COLORS[k], "count": defect_counts[k], "percent": _pct(defect_counts[k], judged - good)} for k in CLASS_NAMES],
        "shifts": [{"name": k, "good_rate": _pct(v["normal"], v["judged"]), **v} for k, v in sorted(shifts.items())],
        "bayesian": _confidence_interval(good, judged),
        "forecast": _weighted_forecast(points),
        "review": {
            "candidates": anomalies[:40], "recent_runs": recent_image_runs,
            "total_candidates": len(anomalies),
            "status": {
                "pending_runs": sum(1 for record in anomalies if record["reviewed"] < record["judged"]),
                "confirmed_objects": review_decisions["correct"],
                "false_positive_objects": review_decisions["false_positive"],
                "corrected_objects": review_decisions["incorrect_mask"] + review_decisions["incorrect_class"],
            },
        } if admin else None,
        "note": "Image inspections saved in Reports are analysed. Video uploads that are not persisted to Reports are not counted.",
    }
