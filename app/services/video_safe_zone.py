"""Video-only normalized inspection zone and independent per-track gating.

This controls when tracked masks are visible, not classifier accuracy or product counts.
The detector only supplies instances on sampled AI keyframes; a mask can first
appear only after its source instance has been observed on such a keyframe.
"""
from __future__ import annotations

import math

DEFAULT_ZONE = (0.05, 0.00, 0.95, 1.00)  # x0,y0,x1,y1; full-height default


def validate_zone(value):
    """Validate normalized bounds, failing explicitly instead of guessing."""
    try:
        bounds = tuple(float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Safe Zone must contain four numeric coordinates.') from exc
    if len(bounds) != 4 or any(not math.isfinite(v) for v in bounds):
        raise ValueError('Safe Zone coordinates must be finite numbers.')
    x0, y0, x1, y1 = bounds
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise ValueError('Safe Zone must be inside the video with positive width and height.')
    if x1 - x0 < 0.05 or y1 - y0 < 0.05:
        raise ValueError('Safe Zone must be at least 5% wide and 5% high.')
    return bounds


def zone_pixels(value, width, height):
    x0, y0, x1, y1 = validate_zone(value)
    return (
        max(0, min(width - 1, round(x0 * width))),
        max(0, min(height - 1, round(y0 * height))),
        max(1, min(width, round(x1 * width))),
        max(1, min(height, round(y1 * height))),
    )
