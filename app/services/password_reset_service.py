import hashlib
import hmac
import secrets

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from flask import current_app

from app.extensions import db
from app.models import PasswordResetCode


CODE_EXPIRY_MINUTES = 5
MAX_ATTEMPTS = 5

RESEND_COOLDOWN_SECONDS = 60
MAX_SENDS_PER_HOUR = 5


class PasswordResetRateLimitError(Exception):
    pass


def _now():
    return datetime.now(
        timezone.utc
    )


def _generate_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash_code(code):
    secret_key = (
        current_app.config["SECRET_KEY"]
        .encode("utf-8")
    )

    return hmac.new(
        secret_key,
        code.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def issue_password_reset_code(
    user,
    is_resend=False,
):
    now = _now()

    reset = db.session.scalar(
        db.select(
            PasswordResetCode
        ).where(
            PasswordResetCode.user_id
            == user.id
        )
    )

    # First request.
    if reset is None:

        code = _generate_code()

        reset = PasswordResetCode(
            user_id=user.id,
            code_hash=_hash_code(code),
            expires_at=(
                now
                + timedelta(
                    minutes=CODE_EXPIRY_MINUTES
                )
            ),
            attempt_count=0,
            last_sent_at=now,
            resend_count=1,
            window_started_at=now,
            verified_at=None,
            used_at=None,
        )

        db.session.add(
            reset
        )

        return code

    if is_resend:

        seconds_since_last_send = (
            now - reset.last_sent_at
        ).total_seconds()

        if (
            seconds_since_last_send
            < RESEND_COOLDOWN_SECONDS
        ):

            remaining = max(
                1,
                int(
                    RESEND_COOLDOWN_SECONDS
                    - seconds_since_last_send
                ),
            )

            raise PasswordResetRateLimitError(
                (
                    "Please wait "
                    f"{remaining} seconds before "
                    "requesting another code."
                )
            )

        if (
            now - reset.window_started_at
            >= timedelta(hours=1)
        ):

            reset.window_started_at = now
            reset.resend_count = 0

        if (
            reset.resend_count
            >= MAX_SENDS_PER_HOUR
        ):

            raise PasswordResetRateLimitError(
                (
                    "Too many password reset codes "
                    "have been requested. "
                    "Please try again later."
                )
            )

    code = _generate_code()

    reset.code_hash = (
        _hash_code(code)
    )

    reset.expires_at = (
        now
        + timedelta(
            minutes=CODE_EXPIRY_MINUTES
        )
    )

    reset.attempt_count = 0
    reset.last_sent_at = now

    if is_resend:
        reset.resend_count += 1

    else:
        reset.resend_count = 1
        reset.window_started_at = now

    reset.verified_at = None
    reset.used_at = None

    return code


def verify_password_reset_code(
    user,
    submitted_code,
):
    now = _now()

    reset = db.session.scalar(
        db.select(
            PasswordResetCode
        ).where(
            PasswordResetCode.user_id
            == user.id
        )
    )

    if reset is None:
        return (
            False,
            "Invalid or expired verification code.",
        )

    if reset.used_at is not None:
        return (
            False,
            "This password reset request has already been used.",
        )

    if (
        reset.attempt_count
        >= MAX_ATTEMPTS
    ):
        return (
            False,
            (
                "Too many incorrect attempts. "
                "Please request a new code."
            ),
        )

    if now > reset.expires_at:
        return (
            False,
            (
                "This verification code has expired. "
                "Please request a new code."
            ),
        )

    submitted_hash = _hash_code(
        submitted_code.strip()
    )

    if not hmac.compare_digest(
        reset.code_hash,
        submitted_hash,
    ):

        reset.attempt_count += 1

        remaining = (
            MAX_ATTEMPTS
            - reset.attempt_count
        )

        return (
            False,
            (
                "Incorrect verification code. "
                f"{remaining} attempts remaining."
            ),
        )

    reset.verified_at = now

    # Give the user another 10 minutes
    # to choose a new password.
    reset.expires_at = (
        now
        + timedelta(minutes=10)
    )

    return (
        True,
        "Verification successful.",
    )


def get_valid_verified_reset(user):
    now = _now()

    reset = db.session.scalar(
        db.select(
            PasswordResetCode
        ).where(
            PasswordResetCode.user_id
            == user.id
        )
    )

    if reset is None:
        return None

    if reset.used_at is not None:
        return None

    if reset.verified_at is None:
        return None

    if now > reset.expires_at:
        return None

    return reset