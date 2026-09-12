from app.extensions import db


class EmailVerification(db.Model):
    __tablename__ = "email_verifications"

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

    # Never store the real 6-digit code.
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
            name="ck_email_verification_attempt_count",
        ),
        db.CheckConstraint(
            "resend_count >= 0",
            name="ck_email_verification_resend_count",
        ),
    )

    def __repr__(self):
        return (
            f"<EmailVerification user_id={self.user_id}>"
        )