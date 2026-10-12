from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.extensions import db
from app.models.inspection_batch import InspectionBatch


def main():
    app = create_app()

    with app.app_context():
        records = list(
            db.session.scalars(
                db.select(InspectionBatch)
                .order_by(InspectionBatch.id.desc())
                .limit(10)
            ).all()
        )

        print("Inspection records:", len(records))

        for record in records:
            print(
                record.batch_id,
                "|",
                record.original_filename,
                "|",
                record.inspection_date,
                "|",
                record.storage_backend,
            )


if __name__ == "__main__":
    main()
