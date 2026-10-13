from __future__ import annotations

import argparse
import sys

from pathlib import Path


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )


from app.services.image_storage_optimizer import (
    optimize_image_for_storage,
)


def human_size(
    value: int,
) -> str:
    size = float(
        value
    )

    for unit in (
        "B",
        "KB",
        "MB",
        "GB",
    ):
        if size < 1024.0:
            return (
                f"{size:.2f} {unit}"
            )

        size /= 1024.0

    return (
        f"{size:.2f} TB"
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Preview how much a BIKA inspection image "
            "will shrink before it is saved to storage."
        )
    )

    parser.add_argument(
        "image",
        type=Path,
    )

    args = parser.parse_args()

    data = (
        args.image
        .read_bytes()
    )

    result = (
        optimize_image_for_storage(
            data
        )
    )

    print(
        "Original:",
        human_size(
            result.original_bytes
        ),
        (
            f"({result.original_width}"
            f"x{result.original_height})"
        ),
    )

    print(
        "Stored:",
        human_size(
            result.stored_bytes
        ),
        (
            f"({result.stored_width}"
            f"x{result.stored_height})"
        ),
    )

    print(
        "Format:",
        result.format.upper(),
    )

    print(
        "Quality:",
        result.quality,
    )

    print(
        "Reduction:",
        (
            f"{result.reduction_percent:.2f}%"
        ),
    )


if __name__ == "__main__":
    main()
