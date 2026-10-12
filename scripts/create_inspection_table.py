from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

sys.path.insert(
    0,
    str(PROJECT_ROOT),
)

from app import create_app
from app.extensions import db
from app.models.inspection_batch import InspectionBatch


def main():
    app = create_app()

    with app.app_context():
        db.create_all()

        print(
            "Inspection table ready:",
            InspectionBatch.__tablename__,
        )


if __name__ == "__main__":
    main()
