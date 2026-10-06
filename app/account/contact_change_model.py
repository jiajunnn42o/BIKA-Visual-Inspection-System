from datetime import datetime, timezone

from app.extensions import db


class AccountContactChange(db.Model):
    """Pending OTP verification for an account email/phone change."""

    __tablename__ = "account_contact_changes"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    change_type = db.Column(
        db.String(16),
        nullable=False,
    )

    pending_value = db.Column(
        db.String(255),
        nullable=False,
    )

    code_hash = db.Column(
        db.String(64),
        nullable=False,
    )

    expires_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
    )

    resend_available_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
    )

    failed_attempts = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    resend_count = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.CheckConstraint(
            "change_type IN ('email', 'phone')",
            name="ck_account_contact_changes_type",
        ),
        db.UniqueConstraint(
            "user_id",
            "change_type",
            name="uq_account_contact_changes_user_type",
        ),
        db.UniqueConstraint(
            "change_type",
            "pending_value",
            name="uq_account_contact_changes_type_value",
        ),
    )
