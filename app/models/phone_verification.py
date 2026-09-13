from app.extensions import db


class PhoneVerification(db.Model):
    __tablename__ = "phone_verifications"

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
        unique=True,
        index=True,
    )

    code_hash = db.Column(
        db.String(64),
        nullable=False,
    )

    expires_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
    )

    attempt_count = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    last_sent_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
    )

    resend_count = db.Column(
        db.Integer,
        nullable=False,
        default=1,
        server_default="1",
    )

    window_started_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    __table_args__ = (
        db.CheckConstraint(
            "attempt_count >= 0",
            name="ck_phone_verification_attempt_count",
        ),
        db.CheckConstraint(
            "resend_count >= 0",
            name="ck_phone_verification_resend_count",
        ),
    )