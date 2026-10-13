from __future__ import annotations

import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.media_preview_service import (
    image_preview_webp,
    video_preview_webp,
)
from app.services.mask_overlay_service import (
    render_mask_overlay_webp,
)
from app.services.image_storage_optimizer import (
    image_storage_optimization_enabled,
    optimize_image_for_storage,
)
from app.services.storage_service import (
    put_bytes,
    put_json,
    storage_backend,
)


_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_component(value: str) -> str:
    cleaned = _SAFE_ID.sub("-", str(value)).strip(".-_")
    return cleaned or "inspection"


def _source_extension(filename: str, source_type: str) -> str:
    suffix = Path(filename).suffix.lower()
    image_ext = {".jpg", ".jpeg", ".png", ".webp"}
    video_ext = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

    if source_type == "video":
        return suffix if suffix in video_ext else ".mp4"
    return suffix if suffix in image_ext else ".jpg"


def save_inspection_artifacts(
    *,
    batch_id: str,
    source_bytes: bytes,
    source_filename: str,
    source_type: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    normalized_type = (
        "video" if str(source_type).lower() == "video" else "image"
    )

    safe_batch_id = _safe_component(batch_id)
    safe_source_name = _safe_component(Path(source_filename).stem)
    extension = _source_extension(source_filename, normalized_type)

    base_key = f"inspections/{safe_batch_id}"

    storage_optimization = {
        "enabled":
            False,

        "original_upload_bytes":
            len(
                source_bytes
            ),

        "stored_source_bytes":
            len(
                source_bytes
            ),

        "saved_bytes":
            0,

        "reduction_percent":
            0.0,
    }

    # -----------------------------------------------------
    # IMPORTANT:
    # Inference has already completed before this function
    # is called. Compression only changes the stored copy.
    # -----------------------------------------------------
    if (
        normalized_type
        ==
        "image"
        and
        image_storage_optimization_enabled()
    ):

        optimized = (
            optimize_image_for_storage(
                source_bytes
            )
        )

        stored_source_bytes = (
            optimized.data
        )

        source_content_type = (
            optimized.content_type
        )

        original_key = (
            f"{base_key}/"
            f"source_{safe_source_name}"
            f"{optimized.extension}"
        )

        storage_optimization = {
            "enabled":
                True,

            "format":
                optimized.format,

            "quality":
                optimized.quality,

            "original_upload_bytes":
                optimized.original_bytes,

            "stored_source_bytes":
                optimized.stored_bytes,

            "saved_bytes":
                optimized.saved_bytes,

            "reduction_percent":
                optimized.reduction_percent,

            "original_dimensions": {
                "width":
                    optimized.original_width,

                "height":
                    optimized.original_height,
            },

            "stored_dimensions": {
                "width":
                    optimized.stored_width,

                "height":
                    optimized.stored_height,
            },
        }

    else:

        stored_source_bytes = (
            source_bytes
        )

        original_key = (
            f"{base_key}/"
            f"original_{safe_source_name}"
            f"{extension}"
        )

        source_content_type = (
            mimetypes.guess_type(
                original_key
            )[0]
            or
            (
                "video/mp4"
                if normalized_type
                ==
                "video"
                else
                "image/jpeg"
            )
        )

    preview_key = f"{base_key}/preview.webp"
    annotated_key = f"{base_key}/annotated.webp"
    result_key = f"{base_key}/result.json"
    manifest_key = f"{base_key}/manifest.json"

    put_bytes(
        original_key,
        stored_source_bytes,
        content_type=source_content_type,
    )

    if normalized_type == "video":
        preview_bytes = video_preview_webp(
            source_bytes,
            suffix=extension,
        )
    else:
        preview_bytes = image_preview_webp(source_bytes)

    put_bytes(
        preview_key,
        preview_bytes,
        content_type="image/webp",
        cache_control="private, max-age=300",
    )

    if normalized_type == "image":
        annotated_bytes = (
            render_mask_overlay_webp(
                source_bytes,
                result,
            )
        )

        if (
            image_storage_optimization_enabled()
        ):
            annotated_bytes = (
                optimize_image_for_storage(
                    annotated_bytes
                ).data
            )

        put_bytes(
            annotated_key,
            annotated_bytes,
            content_type="image/webp",
            cache_control="private, max-age=300",
        )

    put_json(result_key, result)

    manifest = {
        "schema_version": 2,
        "batch_id": batch_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "storage_backend": storage_backend(),
        "source_type": normalized_type,
        "source_filename": source_filename,
        "storage_optimization": storage_optimization,
        "original_key": original_key,
        "preview_key": preview_key,
        "annotated_key": (
            annotated_key
            if normalized_type == "image"
            else None
        ),
        "result_key": result_key,
        "manifest_key": manifest_key,
    }

    put_json(manifest_key, manifest)
    return manifest
