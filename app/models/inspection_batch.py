from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


class InspectionBatch(db.Model):
    __tablename__ = "inspection_batches"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    batch_id = db.Column(
        db.String(40),
        unique=True,
        nullable=False,
        index=True,
    )

    inspection_date = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        index=True,
        default=lambda: datetime.now(timezone.utc),
    )

    source_type = db.Column(
        db.String(16),
        nullable=False,
        default="image",
    )

    original_filename = db.Column(
        db.String(255),
        nullable=False,
    )

    model_version = db.Column(
        db.String(128),
        nullable=False,
        default="Not configured",
    )

    summary_json = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
    )

    classes_json = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
    )

    confidence_json = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
    )

    timing_json = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
    )

    storage_backend = db.Column(
        db.String(16),
        nullable=False,
        default="local",
    )

    original_key = db.Column(
        db.String(700),
        nullable=True,
    )

    preview_key = db.Column(
        db.String(700),
        nullable=True,
    )

    result_key = db.Column(
        db.String(700),
        nullable=True,
    )

    manifest_key = db.Column(
        db.String(700),
        nullable=True,
    )

    created_by_user_id = db.Column(
        db.String(64),
        nullable=True,
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            "<InspectionBatch "
            f"{self.batch_id} "
            f"{self.original_filename}>"
        )
