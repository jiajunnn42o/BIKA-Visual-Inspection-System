from __future__ import annotations

import io
import tempfile
from pathlib import Path

from PIL import Image


PREVIEW_MAX_SIZE = (480, 320)
PREVIEW_WEBP_QUALITY = 82


def image_preview_webp(image_bytes: bytes) -> bytes:
    with Image.open(io.BytesIO(image_bytes)) as image:
        image = image.convert("RGB")
        image.thumbnail(PREVIEW_MAX_SIZE, Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(
            output,
            format="WEBP",
            quality=PREVIEW_WEBP_QUALITY,
            method=6,
        )
        return output.getvalue()


def video_preview_webp(
    video_bytes: bytes,
    *,
    suffix: str = ".mp4",
) -> bytes:
    import cv2

    suffix = suffix if suffix.startswith(".") else f".{suffix}"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
        temporary.write(video_bytes)
        temp_path = Path(temporary.name)

    try:
        capture = cv2.VideoCapture(str(temp_path))
        if not capture.isOpened():
            raise ValueError("Unable to open uploaded video for preview generation.")

        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if frame_count > 1:
            capture.set(
                cv2.CAP_PROP_POS_FRAMES,
                max(0, int(frame_count * 0.10)),
            )

        success, frame = capture.read()
        capture.release()

        if not success:
            raise ValueError("Unable to read a video frame for preview generation.")

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame_rgb)
        image.thumbnail(PREVIEW_MAX_SIZE, Image.Resampling.LANCZOS)

        output = io.BytesIO()
        image.save(
            output,
            format="WEBP",
            quality=PREVIEW_WEBP_QUALITY,
            method=6,
        )
        return output.getvalue()

    finally:
        temp_path.unlink(missing_ok=True)
