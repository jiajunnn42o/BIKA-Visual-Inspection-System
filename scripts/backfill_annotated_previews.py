from __future__ import annotations

import argparse
import json
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


from app import create_app
from app.extensions import db
from app.models.inspection_batch import InspectionBatch
from app.services.mask_overlay_service import (
    render_mask_overlay_webp,
)
from app.services.storage_service import (
    object_exists,
    put_bytes,
    read_bytes,
)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Create annotated.webp mask views for existing "
            "BIKA image inspection records."
        )
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild annotated.webp even when it already exists.",
    )

    args = parser.parse_args()

    app = create_app()

    with app.app_context():

        records = list(
            db.session.scalars(
                db.select(
                    InspectionBatch
                ).order_by(
                    InspectionBatch.id.asc()
                )
            ).all()
        )

        created = 0
        skipped = 0
        failed = 0

        for record in records:

            if (
                str(
                    record.source_type
                    or ""
                ).lower()
                !=
                "image"
            ):
                skipped += 1
                continue

            if (
                not record.original_key
                or
                not record.result_key
            ):
                print(
                    f"SKIP {record.batch_id}: "
                    "missing original/result storage key"
                )
                skipped += 1
                continue

            annotated_key = (
                f"inspections/"
                f"{record.batch_id}/"
                "annotated.webp"
            )

            try:

                if (
                    not args.force
                    and
                    object_exists(
                        annotated_key
                    )
                ):
                    print(
                        f"SKIP {record.batch_id}: "
                        "annotated.webp already exists"
                    )
                    skipped += 1
                    continue

                source_bytes = (
                    read_bytes(
                        record.original_key
                    )
                )

                result = json.loads(
                    read_bytes(
                        record.result_key
                    ).decode(
                        "utf-8"
                    )
                )

                annotated_bytes = (
                    render_mask_overlay_webp(
                        source_bytes,
                        result,
                    )
                )

                put_bytes(
                    annotated_key,
                    annotated_bytes,
                    content_type="image/webp",
                    cache_control=(
                        "private, max-age=300"
                    ),
                )

                print(
                    f"OK   {record.batch_id}: "
                    f"{annotated_key}"
                )

                created += 1

            except Exception as exc:

                print(
                    f"FAIL {record.batch_id}: "
                    f"{exc}"
                )

                failed += 1

        print()
        print(
            "Annotated mask backfill complete."
        )
        print(
            f"Created: {created}"
        )
        print(
            f"Skipped: {skipped}"
        )
        print(
            f"Failed:  {failed}"
        )


if __name__ == "__main__":
    main()
