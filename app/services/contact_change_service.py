import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from flask import current_app

from app.account.contact_change_model import AccountContactChange
from app.extensions import db
from app.models import User
from app.services.email_service import send_email_verification_code_email
from app.services.sms_service import send_phone_verification_code_sms


OTP_EXPIRES_SECONDS = 5 * 60
RESEND_COOLDOWN_SECONDS = 60
MAX_FAILED_ATTEMPTS = 5
MAX_RESENDS = 5


class ContactChangeError(Exception):
    pass


class ContactChangeRateLimitError(ContactChangeError):
    def __init__(self, message, retry_after=0):
        super().__init__(message)
        self.retry_after = max(0, int(retry_after))


def _now():
    return datetime.now(timezone.utc)


def _as_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _generate_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def _code_digest(user_id, change_type, pending_value, code):
    secret = str(current_app.config["SECRET_KEY"]).encode("utf-8")
    payload = (
        f"{user_id}|{change_type}|{pending_value}|{code}"
        .encode("utf-8")
    )
    return hmac.new(
        secret,
        payload,
        hashlib.sha256,
    ).hexdigest()


def _seconds_until(value):
    value = _as_utc(value)
    if value is None:
        return 0
    remaining = (value - _now()).total_seconds()
    return max(0, int(remaining + 0.999))


def _other_user_owns_value(user_id, change_type, value):
    if change_type == "email":
        existing_id = db.session.scalar(
            db.select(User.id)
            .where(
                db.func.lower(User.email) == value.lower(),
                User.id != user_id,
            )
            .limit(1)
        )
    else:
        existing_id = db.session.scalar(
            db.select(User.id)
            .where(
                User.phone_number == value,
                User.id != user_id,
            )
            .limit(1)
        )

    return existing_id is not None


def _target_reserved_by_other_change(user_id, change_type, value):
    change = db.session.scalar(
        db.select(AccountContactChange)
        .where(
            AccountContactChange.change_type == change_type,
            AccountContactChange.pending_value == value,
            AccountContactChange.user_id != user_id,
        )
        .limit(1)
    )

    if change is None:
        return False

    expires_at = _as_utc(change.expires_at)

    if expires_at is not None and expires_at <= _now():
        db.session.delete(change)
        db.session.flush()
        return False

    return True


def _get_user_change(user_id, change_type):
    return db.session.scalar(
        db.select(AccountContactChange)
        .where(
            AccountContactChange.user_id == user_id,
            AccountContactChange.change_type == change_type,
        )
        .limit(1)
    )


def _recipient_proxy(user, change_type, pending_value):
    return SimpleNamespace(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        full_name=user.full_name,
        email=(
            pending_value
            if change_type == "email"
            else user.email
        ),
        phone_number=(
            pending_value
            if change_type == "phone"
            else user.phone_number
        ),
    )


def send_contact_change_code(user, change, code):
    """
    Reuse the project's existing email/SMS delivery pipeline,
    but direct the verification code to the *new* contact value.
    """

    recipient = _recipient_proxy(
        user,
        change.change_type,
        change.pending_value,
    )

    if change.change_type == "email":
        send_email_verification_code_email(
            user=recipient,
            code=code,
        )
        return

    send_phone_verification_code_sms(
        user=recipient,
        code=code,
    )


def start_contact_change(user, change_type, pending_value):
    if change_type not in {"email", "phone"}:
        raise ContactChangeError("Invalid contact change type.")

    current_value = (
        user.email
        if change_type == "email"
        else user.phone_number
    )

    if str(current_value or "").strip().lower() == str(pending_value).strip().lower():
        raise ContactChangeError(
            "Please enter a different value from your current one."
        )

    if _other_user_owns_value(
        user.id,
        change_type,
        pending_value,
    ):
        label = "email address" if change_type == "email" else "phone number"
        raise ContactChangeError(
            f"This {label} is already in use by another account."
        )

    if _target_reserved_by_other_change(
        user.id,
        change_type,
        pending_value,
    ):
        label = "email address" if change_type == "email" else "phone number"
        raise ContactChangeError(
            f"This {label} is already waiting for verification on another account."
        )

    now = _now()
    change = _get_user_change(
        user.id,
        change_type,
    )

    if change is not None:
        retry_after = _seconds_until(
            change.resend_available_at
        )

        if retry_after > 0:
            raise ContactChangeRateLimitError(
                f"Please wait {retry_after} seconds before requesting another code.",
                retry_after=retry_after,
            )

        expires_at = _as_utc(change.expires_at)
        expired = (
            expires_at is None
            or expires_at <= now
        )

        if expired:
            change.resend_count = 0
            change.created_at = now

        elif change.resend_count >= MAX_RESENDS:
            raise ContactChangeRateLimitError(
                "Too many verification codes were requested. Please wait until the current verification expires and try again.",
                retry_after=_seconds_until(change.expires_at),
            )

        else:
            change.resend_count += 1

    else:
        change = AccountContactChange(
            user_id=user.id,
            change_type=change_type,
            pending_value=pending_value,
            code_hash="",
            expires_at=now,
            resend_available_at=now,
            failed_attempts=0,
            resend_count=0,
            created_at=now,
            updated_at=now,
        )
        db.session.add(change)

    code = _generate_code()

    change.pending_value = pending_value
    change.code_hash = _code_digest(
        user.id,
        change_type,
        pending_value,
        code,
    )
    change.expires_at = now + timedelta(
        seconds=OTP_EXPIRES_SECONDS
    )
    change.resend_available_at = now + timedelta(
        seconds=RESEND_COOLDOWN_SECONDS
    )
    change.failed_attempts = 0
    change.updated_at = now

    db.session.flush()

    return change, code


def resend_contact_change(user, change_type):
    if change_type not in {"email", "phone"}:
        raise ContactChangeError("Invalid contact change type.")

    change = _get_user_change(
        user.id,
        change_type,
    )

    if change is None:
        raise ContactChangeError(
            "There is no pending verification. Please start the change again."
        )

    if _other_user_owns_value(
        user.id,
        change_type,
        change.pending_value,
    ):
        db.session.delete(change)
        db.session.flush()
        raise ContactChangeError(
            "That contact value is no longer available. Please choose another one."
        )

    retry_after = _seconds_until(
        change.resend_available_at
    )

    if retry_after > 0:
        raise ContactChangeRateLimitError(
            f"Please wait {retry_after} seconds before resending the code.",
            retry_after=retry_after,
        )

    now = _now()
    expires_at = _as_utc(change.expires_at)

    if expires_at is None or expires_at <= now:
        change.resend_count = 0
        change.created_at = now

    elif change.resend_count >= MAX_RESENDS:
        raise ContactChangeRateLimitError(
            "Too many verification codes were requested. Please wait until the current verification expires and try again.",
            retry_after=_seconds_until(change.expires_at),
        )

    else:
        change.resend_count += 1

    code = _generate_code()

    change.code_hash = _code_digest(
        user.id,
        change.change_type,
        change.pending_value,
        code,
    )
    change.expires_at = now + timedelta(
        seconds=OTP_EXPIRES_SECONDS
    )
    change.resend_available_at = now + timedelta(
        seconds=RESEND_COOLDOWN_SECONDS
    )
    change.failed_attempts = 0
    change.updated_at = now

    db.session.flush()

    return change, code


def verify_contact_change(user, change_type, submitted_code):
    if change_type not in {"email", "phone"}:
        return {
            "ok": False,
            "message": "Invalid contact change type.",
        }

    change = _get_user_change(
        user.id,
        change_type,
    )

    if change is None:
        return {
            "ok": False,
            "message": "This verification session no longer exists. Please start again.",
        }

    now = _now()
    expires_at = _as_utc(change.expires_at)

    if expires_at is None or expires_at <= now:
        db.session.delete(change)
        return {
            "ok": False,
            "message": "This verification code has expired. Please start the change again.",
        }

    if change.failed_attempts >= MAX_FAILED_ATTEMPTS:
        db.session.delete(change)
        return {
            "ok": False,
            "message": "Too many incorrect attempts. Please start the change again.",
        }

    expected_hash = _code_digest(
        user.id,
        change.change_type,
        change.pending_value,
        submitted_code,
    )

    if not hmac.compare_digest(
        expected_hash,
        change.code_hash,
    ):
        change.failed_attempts += 1
        change.updated_at = now

        remaining = max(
            0,
            MAX_FAILED_ATTEMPTS - change.failed_attempts,
        )

        if remaining == 0:
            db.session.delete(change)
            return {
                "ok": False,
                "message": "Incorrect code. Too many attempts were made, so the verification was cancelled.",
            }

        return {
            "ok": False,
            "message": f"Incorrect verification code. {remaining} attempt(s) remaining.",
        }

    if _other_user_owns_value(
        user.id,
        change.change_type,
        change.pending_value,
    ):
        db.session.delete(change)
        return {
            "ok": False,
            "message": "That contact value is no longer available. Please choose another one.",
        }

    new_value = change.pending_value

    if change.change_type == "email":
        user.email = new_value
        user.email_verified_at = now
        label = "Email address"
    else:
        user.phone_number = new_value
        user.phone_verified_at = now
        label = "Phone number"

    db.session.delete(change)

    return {
        "ok": True,
        "message": f"{label} updated successfully.",
        "value": new_value,
        "change_type": change_type,
    }


def mask_contact_value(change_type, value):
    value = str(value or "").strip()

    if change_type == "email":
        if "@" not in value:
            return value

        local, domain = value.split("@", 1)
        if len(local) <= 2:
            masked_local = local[:1] + "*"
        else:
            masked_local = local[:1] + ("*" * min(5, len(local) - 2)) + local[-1:]

        return f"{masked_local}@{domain}"

    if len(value) <= 7:
        return value

    return (
        value[:4]
        + ("*" * max(3, len(value) - 8))
        + value[-4:]
    )
