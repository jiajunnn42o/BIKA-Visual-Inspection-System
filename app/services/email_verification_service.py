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

from app.models import (
    EmailVerification,
)


CODE_EXPIRY_MINUTES = 5
MAX_ATTEMPTS = 5

RESEND_COOLDOWN_SECONDS = 60
MAX_SENDS_PER_HOUR = 5


class VerificationRateLimitError(Exception):
    pass


def _now():
    return datetime.now(
        timezone.utc
    )


def _generate_code():
    """
    Generate a secure 6-digit verification code.
    """

    return (
        f"{secrets.randbelow(1_000_000):06d}"
    )


def _hash_code(code):
    """
    Hash the verification code using the
    application secret key.

    The plain code is never stored in PostgreSQL.
    """

    secret_key = (
        current_app.config["SECRET_KEY"]
        .encode("utf-8")
    )

    return hmac.new(
        secret_key,
        code.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def issue_verification_code(
    user,
    is_resend=False,
):
    """
    Create or replace the user's active
    verification code.

    Returns the plain code only once so that it
    can be sent by email.
    """

    now = _now()

    verification = db.session.scalar(
        db.select(
            EmailVerification
        ).where(
            EmailVerification.user_id
            == user.id
        )
    )

    # -----------------------------------------
    # First verification email
    # -----------------------------------------

    if verification is None:

        code = _generate_code()

        verification = EmailVerification(
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
            used_at=None,
        )

        db.session.add(
            verification
        )

        return code

    # -----------------------------------------
    # Resend protection
    # -----------------------------------------

    if is_resend:

        seconds_since_last_send = (
            now
            - verification.last_sent_at
        ).total_seconds()

        if (
            seconds_since_last_send
            < RESEND_COOLDOWN_SECONDS
        ):

            remaining = int(
                RESEND_COOLDOWN_SECONDS
                - seconds_since_last_send
            )

            raise VerificationRateLimitError(
                (
                    "Please wait "
                    f"{remaining} seconds "
                    "before requesting another code."
                )
            )

        # Reset hourly sending window.
        if (
            now
            - verification.window_started_at
            >= timedelta(hours=1)
        ):

            verification.window_started_at = now
            verification.resend_count = 0

        if (
            verification.resend_count
            >= MAX_SENDS_PER_HOUR
        ):

            raise VerificationRateLimitError(
                (
                    "Too many verification codes "
                    "have been requested. "
                    "Please try again later."
                )
            )

    # -----------------------------------------
    # Generate new code
    # -----------------------------------------

    code = _generate_code()

    verification.code_hash = (
        _hash_code(code)
    )

    verification.expires_at = (
        now
        + timedelta(
            minutes=CODE_EXPIRY_MINUTES
        )
    )

    verification.attempt_count = 0
    verification.last_sent_at = now

    if is_resend:
        verification.resend_count += 1

    else:
        verification.resend_count = 1
        verification.window_started_at = now

    verification.used_at = None

    return code


def verify_email_code(
    user,
    submitted_code,
):
    """
    Validate a submitted verification code.

    Returns:
        (success, message)
    """

    now = _now()

    verification = db.session.scalar(
        db.select(
            EmailVerification
        ).where(
            EmailVerification.user_id
            == user.id
        )
    )

    if verification is None:

        return (
            False,
            "No verification request was found.",
        )

    if verification.used_at is not None:

        return (
            False,
            "This verification code has already been used.",
        )

    if (
        verification.attempt_count
        >= MAX_ATTEMPTS
    ):

        return (
            False,
            (
                "Too many incorrect attempts. "
                "Please request a new verification code."
            ),
        )

    if now > verification.expires_at:

        return (
            False,
            (
                "This verification code has expired. "
                "Please request a new code."
            ),
        )

    submitted_hash = (
        _hash_code(
            submitted_code.strip()
        )
    )

    if not hmac.compare_digest(
        verification.code_hash,
        submitted_hash,
    ):

        verification.attempt_count += 1

        remaining_attempts = (
            MAX_ATTEMPTS
            - verification.attempt_count
        )

        return (
            False,
            (
                "Incorrect verification code. "
                f"{remaining_attempts} attempts remaining."
            ),
        )

    # -----------------------------------------
    # Verification successful
    # -----------------------------------------

    user.email_verified_at = now
    verification.used_at = now

    return (
        True,
        "Email verified successfully.",
    )