from __future__ import annotations

import io
import os

from dataclasses import dataclass

from PIL import Image


try:
    from flask import current_app
except ImportError:
    current_app = None


DEFAULT_MAX_EDGE = 1920
DEFAULT_WEBP_QUALITY = 82


@dataclass(frozen=True)
class OptimizedImage:
    data: bytes

    extension: str
    content_type: str

    original_bytes: int
    stored_bytes: int

    original_width: int
    original_height: int

    stored_width: int
    stored_height: int

    format: str
    quality: int

    @property
    def saved_bytes(self) -> int:
        return max(
            0,
            self.original_bytes
            -
            self.stored_bytes,
        )

    @property
    def reduction_percent(self) -> float:
        if self.original_bytes <= 0:
            return 0.0

        return round(
            (
                self.saved_bytes
                /
                self.original_bytes
            )
            *
            100.0,
            2,
        )


def _setting(
    name: str,
    default,
):
    value = None

    if current_app is not None:
        try:
            value = (
                current_app.config.get(
                    name
                )
            )
        except RuntimeError:
            value = None

    if value is None:
        value = os.getenv(
            name
        )

    if value is None:
        return default

    return value


def _bool_setting(
    name: str,
    default: bool,
) -> bool:
    value = _setting(
        name,
        default,
    )

    if isinstance(
        value,
        bool,
    ):
        return value

    return str(
        value
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def image_storage_optimization_enabled() -> bool:
    return _bool_setting(
        "STORAGE_OPTIMIZE_IMAGES",
        True,
    )


def image_storage_max_edge() -> int:
    try:
        value = int(
            _setting(
                "STORAGE_IMAGE_MAX_EDGE",
                DEFAULT_MAX_EDGE,
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        value = DEFAULT_MAX_EDGE

    return max(
        640,
        min(
            value,
            4096,
        ),
    )


def image_storage_quality() -> int:
    try:
        value = int(
            _setting(
                "STORAGE_IMAGE_WEBP_QUALITY",
                DEFAULT_WEBP_QUALITY,
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        value = DEFAULT_WEBP_QUALITY

    return max(
        50,
        min(
            value,
            95,
        ),
    )


def optimize_image_for_storage(
    image_bytes: bytes,
) -> OptimizedImage:
    """
    Create the long-term storage copy AFTER inference.

    Important:
    - The inspection model has already consumed the original upload.
    - This function only changes the copy written to Local/B2 storage.
    - EXIF orientation is intentionally not transformed because the
      inference pipeline reads the same raw PIL pixel orientation.
    """

    original_size = len(
        image_bytes
    )

    max_edge = (
        image_storage_max_edge()
    )

    quality = (
        image_storage_quality()
    )

    with Image.open(
        io.BytesIO(
            image_bytes
        )
    ) as opened:

        image = opened.convert(
            "RGB"
        )

        original_width, original_height = (
            image.size
        )

        largest_edge = max(
            original_width,
            original_height,
        )

        if largest_edge > max_edge:

            scale = (
                max_edge
                /
                float(
                    largest_edge
                )
            )

            stored_width = max(
                1,
                int(
                    round(
                        original_width
                        *
                        scale
                    )
                ),
            )

            stored_height = max(
                1,
                int(
                    round(
                        original_height
                        *
                        scale
                    )
                ),
            )

            image = image.resize(
                (
                    stored_width,
                    stored_height,
                ),
                Image.Resampling.LANCZOS,
            )

        else:
            stored_width, stored_height = (
                image.size
            )

        output = io.BytesIO()

        image.save(
            output,
            format="WEBP",
            quality=quality,
            method=6,
        )

        stored_data = (
            output.getvalue()
        )

    return OptimizedImage(
        data=stored_data,

        extension=".webp",
        content_type="image/webp",

        original_bytes=(
            original_size
        ),
        stored_bytes=(
            len(
                stored_data
            )
        ),

        original_width=(
            original_width
        ),
        original_height=(
            original_height
        ),

        stored_width=(
            stored_width
        ),
        stored_height=(
            stored_height
        ),

        format="webp",
        quality=quality,
    )
