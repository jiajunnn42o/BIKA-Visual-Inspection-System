from app.extensions import db


class PasswordResetCode(db.Model):
    __tablename__ = "password_reset_codes"

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

    # Never store the real OTP.
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

    # Set after the 6-digit code is correct.
    verified_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    # Set after the password has actually been changed.
    used_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
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
            name="ck_password_reset_attempt_count",
        ),
        db.CheckConstraint(
            "resend_count >= 0",
            name="ck_password_reset_resend_count",
        ),
    )