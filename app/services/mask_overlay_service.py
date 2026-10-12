from __future__ import annotations

from io import BytesIO

from PIL import (
    Image,
    ImageColor,
    ImageDraw,
)


MASK_ALPHA = 108
OUTLINE_ALPHA = 235
WEBP_QUALITY = 88


def _rgba(
    colour: str,
    alpha: int,
) -> tuple[int, int, int, int]:
    try:
        red, green, blue = (
            ImageColor.getrgb(
                str(colour)
            )
        )

    except Exception:
        red, green, blue = (
            141,
            141,
            141,
        )

    return (
        int(red),
        int(green),
        int(blue),
        int(alpha),
    )


def render_mask_overlay_webp(
    source_bytes: bytes,
    result: dict,
) -> bytes:
    """
    Build the Reports mask-view image from the already-completed
    inspection result.

    No model is re-run. The saved result.json already contains the
    exact mask polygons and mask colours used by the inspection UI.
    """

    with Image.open(
        BytesIO(
            source_bytes
        )
    ) as opened:

        base = opened.convert(
            "RGBA"
        )

    overlay = Image.new(
        "RGBA",
        base.size,
        (
            0,
            0,
            0,
            0,
        ),
    )

    draw = ImageDraw.Draw(
        overlay,
        "RGBA",
    )

    width, height = (
        base.size
    )

    for item in (
        result.get(
            "objects"
        )
        or
        []
    ):
        colour = (
            item.get(
                "mask_colour"
            )
            or
            "#8D8D8D"
        )

        fill = _rgba(
            colour,
            MASK_ALPHA,
        )

        outline = (
            255,
            255,
            255,
            OUTLINE_ALPHA,
        )

        for polygon in (
            item.get(
                "polygons"
            )
            or
            []
        ):
            points = []

            for point in polygon:
                if (
                    not isinstance(
                        point,
                        (
                            list,
                            tuple,
                        ),
                    )
                    or
                    len(point)
                    <
                    2
                ):
                    continue

                x = max(
                    0,
                    min(
                        width - 1,
                        int(
                            round(
                                float(
                                    point[0]
                                )
                            )
                        ),
                    ),
                )

                y = max(
                    0,
                    min(
                        height - 1,
                        int(
                            round(
                                float(
                                    point[1]
                                )
                            )
                        ),
                    ),
                )

                points.append(
                    (
                        x,
                        y,
                    )
                )

            if len(points) < 3:
                continue

            draw.polygon(
                points,
                fill=fill,
            )

            draw.line(
                points
                +
                [
                    points[0]
                ],
                fill=outline,
                width=1,
                joint="curve",
            )

    composed = Image.alpha_composite(
        base,
        overlay,
    ).convert(
        "RGB"
    )

    output = BytesIO()

    composed.save(
        output,
        format="WEBP",
        quality=WEBP_QUALITY,
        method=6,
    )

    return output.getvalue()
