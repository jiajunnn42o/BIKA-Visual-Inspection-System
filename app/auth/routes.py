from datetime import datetime, timezone

from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    url_for,
)

from flask_login import (
    current_user,
    login_user,
    logout_user,
)

from itsdangerous import (
    BadSignature,
    SignatureExpired,
    URLSafeTimedSerializer,
)

from sqlalchemy import or_

from sqlalchemy.exc import (
    IntegrityError,
    SQLAlchemyError,
)

from app.auth import auth_bp

from app.auth.forms import (
    EmailVerificationForm,
    ForgotPasswordForm,
    LoginForm,
    PasswordResetVerificationForm,
    PhoneVerificationForm,
    RegistrationForm,
    ResendVerificationForm,
    ResetPasswordForm,
)

from app.extensions import db

from app.models import (
    PasswordResetCode,
    PhoneVerification,
    User,
    UserRole,
    UserStatus,
)

from app.services.email_service import (
    send_email_verification_code_email,
    send_new_registration_to_superadmins,
    send_password_changed_email,
    send_password_reset_code_email,
)

from app.services.email_verification_service import (
    VerificationRateLimitError,
    issue_verification_code,
    verify_email_code,
)

from app.services.password_reset_service import (
    PasswordResetRateLimitError,
    get_valid_verified_reset,
    issue_password_reset_code,
    verify_password_reset_code,
)

from app.services.phone_verification_service import (
    PhoneVerificationRateLimitError,
    issue_phone_verification_code,
    verify_phone_code,
)

from app.services.sms_service import (
    send_phone_verification_code_sms,
)

from app.utils.phone import (
    InvalidPhoneNumberError,
    normalize_malaysian_mobile,
)


# =========================================================
# TOKEN SETTINGS
# =========================================================

EMAIL_VERIFICATION_TOKEN_MAX_AGE = (
    7 * 24 * 60 * 60
)

PHONE_VERIFICATION_TOKEN_MAX_AGE = (
    7 * 24 * 60 * 60
)

PASSWORD_RESET_TOKEN_MAX_AGE = (
    30 * 60
)


# =========================================================
# EMAIL VERIFICATION TOKEN
# =========================================================

def _verification_serializer():
    """
    Signed serializer used for the
    registration email verification flow.
    """

    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt="bika-email-verification",
    )


def _create_verification_token(user):
    """
    Create a browser-only email verification token.

    The email address is included so that an old
    token becomes invalid automatically if the
    applicant's email address changes.
    """

    return (
        _verification_serializer()
        .dumps(
            {
                "user_id": user.id,
                "email": user.email,
                "purpose": "email-verification",
            }
        )
    )


def _get_verification_user(token):
    """
    Return the user represented by a valid
    email verification browser token.
    """

    try:

        data = (
            _verification_serializer()
            .loads(
                token,
                max_age=(
                    EMAIL_VERIFICATION_TOKEN_MAX_AGE
                ),
            )
        )

    except (
        SignatureExpired,
        BadSignature,
    ):

        return None

    if (
        data.get("purpose")
        != "email-verification"
    ):
        return None

    user_id = data.get(
        "user_id"
    )

    token_email = data.get(
        "email"
    )

    if user_id is None:
        return None

    user = db.session.get(
        User,
        user_id,
    )

    if user is None:
        return None

    if (
        user.email
        != token_email
    ):
        return None

    return user


# =========================================================
# PHONE VERIFICATION TOKEN
# =========================================================

def _phone_verification_serializer():
    """
    Signed serializer for the
    phone verification browser flow.
    """

    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt="bika-phone-verification",
    )


def _create_phone_verification_token(
    user,
):
    """
    Create a browser-only phone verification token.

    The real OTP is sent through SMS.

    Including the phone number inside the signed token
    automatically invalidates old tokens if the number
    is changed later.
    """

    return (
        _phone_verification_serializer()
        .dumps(
            {
                "user_id": user.id,
                "phone_number": (
                    user.phone_number
                ),
                "purpose": (
                    "phone-verification"
                ),
            }
        )
    )


def _get_phone_verification_user(
    token,
):
    """
    Return the user represented by a valid
    phone verification browser token.
    """

    try:

        data = (
            _phone_verification_serializer()
            .loads(
                token,
                max_age=(
                    PHONE_VERIFICATION_TOKEN_MAX_AGE
                ),
            )
        )

    except (
        SignatureExpired,
        BadSignature,
    ):

        return None

    if (
        data.get("purpose")
        != "phone-verification"
    ):
        return None

    user_id = data.get(
        "user_id"
    )

    token_phone = data.get(
        "phone_number"
    )

    if user_id is None:
        return None

    user = db.session.get(
        User,
        user_id,
    )

    if user is None:
        return None

    if (
        user.phone_number
        != token_phone
    ):
        return None

    return user


def _mask_phone_number(
    phone_number,
):
    """
    Mask a phone number before displaying it.

    Example:
        +601121720511
        ->
        +6011 **** 0511
    """

    if not phone_number:
        return ""

    if len(phone_number) <= 8:
        return phone_number

    return (
        f"{phone_number[:5]} "
        f"**** "
        f"{phone_number[-4:]}"
    )


# =========================================================
# PASSWORD RESET TOKEN
# =========================================================

def _password_reset_serializer():
    """
    Signed serializer for the
    password reset browser flow.
    """

    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt="bika-password-reset",
    )


def _create_password_reset_token(
    email,
):
    """
    Create a browser-only password reset token.

    The token is never emailed to the user.
    The email only receives the six-digit OTP.
    """

    return (
        _password_reset_serializer()
        .dumps(
            {
                "email": email,
                "purpose": "password-reset",
            }
        )
    )


def _get_password_reset_email(
    token,
):
    """
    Read a password reset browser token.
    """

    try:

        data = (
            _password_reset_serializer()
            .loads(
                token,
                max_age=(
                    PASSWORD_RESET_TOKEN_MAX_AGE
                ),
            )
        )

    except (
        SignatureExpired,
        BadSignature,
    ):

        return None

    if (
        data.get("purpose")
        != "password-reset"
    ):
        return None

    return data.get(
        "email"
    )


# =========================================================
# PASSWORD RESET RULES
# =========================================================

def _password_reset_allowed(
    user,
):
    """
    Accounts allowed to reset their password:

    - active
    - locked
    - disabled
    - pending with verified email

    Rejected accounts and pending accounts
    without verified email are not eligible.
    """

    if user is None:
        return False

    if (
        user.status
        in {
            UserStatus.ACTIVE.value,
            UserStatus.LOCKED.value,
            UserStatus.DISABLED.value,
        }
    ):
        return True

    if (
        user.status
        == UserStatus.PENDING.value
        and
        user.email_verified_at
        is not None
    ):
        return True

    return False


# =========================================================
# PHONE VERIFICATION START HELPER
# =========================================================

def _ensure_phone_verification_started(
    user,
):
    """
    Ensure that a phone verification record exists.

    Returns:
        (True, "sent")
        (True, "existing")
        (True, "send_failed")
        (False, "database_error")

    This prevents repeatedly regenerating a phone OTP
    every time the user revisits the verification page.
    """

    if (
        user.phone_verified_at
        is not None
    ):
        return (
            True,
            "already_verified",
        )

    existing_verification = (
        db.session.scalar(
            db.select(
                PhoneVerification
            ).where(
                PhoneVerification.user_id
                == user.id
            )
        )
    )

    if (
        existing_verification
        is not None
    ):
        return (
            True,
            "existing",
        )

    try:

        phone_code = (
            issue_phone_verification_code(
                user=user,
                is_resend=False,
            )
        )

        db.session.commit()

    except SQLAlchemyError:

        db.session.rollback()

        current_app.logger.exception(
            (
                "Unable to create initial "
                "phone verification code."
            )
        )

        return (
            False,
            "database_error",
        )

    try:

        send_phone_verification_code_sms(
            user=user,
            code=phone_code,
        )

    except Exception:

        current_app.logger.exception(
            (
                "Initial phone verification "
                "SMS could not be sent."
            )
        )

        return (
            True,
            "send_failed",
        )

    return (
        True,
        "sent",
    )


# =========================================================
# SUPERADMIN NOTIFICATION HELPER
# =========================================================

def _notify_superadmins_of_registration(
    user,
):
    """
    Notify active SuperAdmins only after
    BOTH email and phone verification
    have completed.
    """

    superadmins = (
        db.session.scalars(
            db.select(User)
            .where(
                User.role
                == UserRole.SUPERADMIN.value,

                User.status
                == UserStatus.ACTIVE.value,
            )
            .order_by(
                User.id.asc()
            )
        )
        .all()
    )

    try:

        result = (
            send_new_registration_to_superadmins(
                applicant=user,
                superadmins=superadmins,
            )
        )

        current_app.logger.info(
            (
                f"Registration {user.id} "
                f"completed identity verification. "
                f"SuperAdmin notifications: "
                f"{result['sent']} sent, "
                f"{result['failed']} failed."
            )
        )

    except Exception:

        current_app.logger.exception(
            (
                "Unable to notify SuperAdmins "
                "about verified registration."
            )
        )


# =========================================================
# LOGIN IDENTIFIER HELPER
# =========================================================

def _find_user_by_login_identifier(
    raw_identifier,
):
    """
    Support exactly three login identifiers:

    1. Email
    2. Username
    3. Verified Malaysian phone number

    Phone authentication is only allowed after
    phone_verified_at has been recorded.
    """

    raw_identifier = (
        raw_identifier
        .strip()
    )

    normalized_identifier = (
        raw_identifier
        .lower()
    )

    # -----------------------------------------------------
    # EMAIL / USERNAME
    # -----------------------------------------------------

    user = db.session.scalar(
        db.select(User)
        .where(
            or_(
                User.email
                == normalized_identifier,

                User.username
                == normalized_identifier,
            )
        )
    )

    if user is not None:
        return user

    # -----------------------------------------------------
    # MALAYSIAN PHONE
    # -----------------------------------------------------

    try:

        normalized_phone = (
            normalize_malaysian_mobile(
                raw_identifier
            )
        )

    except InvalidPhoneNumberError:

        return None

    return db.session.scalar(
        db.select(User)
        .where(
            User.phone_number
            == normalized_phone,

            User.phone_verified_at
            .is_not(None),
        )
    )


# =========================================================
# REGISTER
# =========================================================

@auth_bp.route(
    "/register",
    methods=["GET", "POST"],
)
def register():
    """
    Public registration.

    New public registrations always begin as:

        role = user
        status = pending

    Final approval happens only after:

        Email OTP
        ->
        Phone OTP
        ->
        SuperAdmin review
    """

    if current_user.is_authenticated:

        return redirect(
            url_for(
                "main.index"
            )
        )

    form = RegistrationForm()

    if form.validate_on_submit():

        # -------------------------------------------------
        # NORMALIZE MALAYSIAN PHONE
        # -------------------------------------------------

        try:

            phone_number = (
                normalize_malaysian_mobile(
                    form.phone_number.data
                )
            )

        except InvalidPhoneNumberError as exc:

            flash(
                str(exc),
                "error",
            )

            return render_template(
                "auth/register.html",
                form=form,
            )

        # -------------------------------------------------
        # CREATE ACCOUNT
        # -------------------------------------------------

        user = User(
            first_name=(
                form.first_name.data
                .strip()
            ),

            last_name=(
                form.last_name.data
                .strip()
            ),

            username=(
                form.username.data
                .strip()
                .lower()
            ),

            email=(
                form.email.data
                .strip()
                .lower()
            ),

            phone_number=(
                phone_number
            ),

            employee_id=(
                form.employee_id.data
                .strip()
                .upper()
            ),

            role=(
                UserRole.USER.value
            ),

            status=(
                UserStatus.PENDING.value
            ),
        )

        user.set_password(
            form.password.data
        )

        # -------------------------------------------------
        # CREATE ACCOUNT + EMAIL OTP
        # -------------------------------------------------

        try:

            db.session.add(
                user
            )

            # We need an ID before the verification
            # record can reference the new user.
            db.session.flush()

            verification_code = (
                issue_verification_code(
                    user=user,
                    is_resend=False,
                )
            )

            db.session.commit()

        except IntegrityError:

            db.session.rollback()

            flash(
                (
                    "An account with the same "
                    "email, username, phone number, "
                    "or employee ID already exists."
                ),
                "error",
            )

            return render_template(
                "auth/register.html",
                form=form,
            )

        except SQLAlchemyError:

            db.session.rollback()

            current_app.logger.exception(
                (
                    "Database error while "
                    "creating registration."
                )
            )

            flash(
                (
                    "Your registration could not "
                    "be completed. Please try again."
                ),
                "error",
            )

            return render_template(
                "auth/register.html",
                form=form,
            )

        # -------------------------------------------------
        # EMAIL VERIFICATION TOKEN
        # -------------------------------------------------

        verification_token = (
            _create_verification_token(
                user
            )
        )

        # -------------------------------------------------
        # EMAIL OTP
        # -------------------------------------------------

        try:

            send_email_verification_code_email(
                user=user,
                code=verification_code,
            )

        except Exception:

            current_app.logger.exception(
                (
                    "Unable to send registration "
                    "email verification code."
                )
            )

            flash(
                (
                    "Your account was created, "
                    "but the verification email "
                    "could not be sent. "
                    "Please request another code."
                ),
                "warning",
            )

        return redirect(
            url_for(
                "auth.verify_email",
                token=verification_token,
            )
        )

    return render_template(
        "auth/register.html",
        form=form,
    )


# =========================================================
# VERIFY EMAIL
# =========================================================

@auth_bp.route(
    "/verify-email/<token>",
    methods=["GET", "POST"],
)
def verify_email(token):
    """
    First verification stage:

        Email OTP
        ->
        Phone OTP
    """

    user = (
        _get_verification_user(
            token
        )
    )

    if user is None:

        flash(
            (
                "This email verification "
                "session is invalid "
                "or has expired."
            ),
            "error",
        )

        return redirect(
            url_for(
                "auth.register"
            )
        )

    # -----------------------------------------------------
    # EMAIL ALREADY VERIFIED
    # -----------------------------------------------------

    if (
        user.email_verified_at
        is not None
    ):

        if (
            user.phone_verified_at
            is not None
        ):

            return redirect(
                url_for(
                    "auth.registration_submitted"
                )
            )

        phone_ready, phone_state = (
            _ensure_phone_verification_started(
                user
            )
        )

        if not phone_ready:

            flash(
                (
                    "Phone verification could not "
                    "be started. Please try again."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "auth.login"
                )
            )

        if (
            phone_state
            == "send_failed"
        ):

            flash(
                (
                    "Your email is verified, "
                    "but the SMS could not be sent. "
                    "Please use Resend Code."
                ),
                "warning",
            )

        phone_token = (
            _create_phone_verification_token(
                user
            )
        )

        return redirect(
            url_for(
                "auth.verify_phone",
                token=phone_token,
            )
        )

    form = (
        EmailVerificationForm()
    )

    resend_form = (
        ResendVerificationForm()
    )

    if form.validate_on_submit():

        success, message = (
            verify_email_code(
                user=user,
                submitted_code=(
                    form.code.data
                ),
            )
        )

        try:

            db.session.commit()

        except SQLAlchemyError:

            db.session.rollback()

            current_app.logger.exception(
                (
                    "Unable to save email "
                    "verification result."
                )
            )

            flash(
                (
                    "The verification could not "
                    "be completed. Please try again."
                ),
                "error",
            )

            return render_template(
                "auth/verify_email.html",
                user=user,
                form=form,
                resend_form=resend_form,
                token=token,
            )

        if not success:

            flash(
                message,
                "error",
            )

            return render_template(
                "auth/verify_email.html",
                user=user,
                form=form,
                resend_form=resend_form,
                token=token,
            )

        # -------------------------------------------------
        # EMAIL VERIFIED
        # START PHONE VERIFICATION
        # -------------------------------------------------

        phone_ready, phone_state = (
            _ensure_phone_verification_started(
                user
            )
        )

        if not phone_ready:

            flash(
                (
                    "Your email was verified, "
                    "but phone verification could "
                    "not be started. "
                    "Please try signing in again."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "auth.login"
                )
            )

        if (
            phone_state
            == "send_failed"
        ):

            flash(
                (
                    "Your email was verified, "
                    "but the SMS verification code "
                    "could not be sent. "
                    "Please request another code."
                ),
                "warning",
            )

        else:

            flash(
                (
                    "Your email has been verified. "
                    "Please verify your phone number "
                    "to continue."
                ),
                "success",
            )

        phone_token = (
            _create_phone_verification_token(
                user
            )
        )

        return redirect(
            url_for(
                "auth.verify_phone",
                token=phone_token,
            )
        )

    return render_template(
        "auth/verify_email.html",
        user=user,
        form=form,
        resend_form=resend_form,
        token=token,
    )


# =========================================================
# RESEND EMAIL OTP
# =========================================================

@auth_bp.route(
    "/verify-email/<token>/resend",
    methods=["POST"],
)
def resend_verification_code(
    token,
):
    """
    Resend registration email OTP.
    """

    user = (
        _get_verification_user(
            token
        )
    )

    if user is None:

        flash(
            (
                "This email verification "
                "session is invalid "
                "or has expired."
            ),
            "error",
        )

        return redirect(
            url_for(
                "auth.register"
            )
        )

    if (
        user.email_verified_at
        is not None
    ):

        phone_token = (
            _create_phone_verification_token(
                user
            )
        )

        return redirect(
            url_for(
                "auth.verify_phone",
                token=phone_token,
            )
        )

    form = (
        ResendVerificationForm()
    )

    if not form.validate_on_submit():

        flash(
            (
                "Unable to resend the "
                "verification code."
            ),
            "error",
        )

        return redirect(
            url_for(
                "auth.verify_email",
                token=token,
            )
        )

    try:

        verification_code = (
            issue_verification_code(
                user=user,
                is_resend=True,
            )
        )

        db.session.commit()

    except VerificationRateLimitError as exc:

        db.session.rollback()

        flash(
            str(exc),
            "warning",
        )

        return redirect(
            url_for(
                "auth.verify_email",
                token=token,
            )
        )

    except SQLAlchemyError:

        db.session.rollback()

        current_app.logger.exception(
            (
                "Unable to create new "
                "email verification code."
            )
        )

        flash(
            (
                "The verification code "
                "could not be regenerated."
            ),
            "error",
        )

        return redirect(
            url_for(
                "auth.verify_email",
                token=token,
            )
        )

    try:

        send_email_verification_code_email(
            user=user,
            code=verification_code,
        )

    except Exception:

        current_app.logger.exception(
            (
                "Unable to resend email "
                "verification code."
            )
        )

        flash(
            (
                "The verification email "
                "could not be sent."
            ),
            "error",
        )

    else:

        flash(
            (
                "A new verification code "
                "has been sent to your email."
            ),
            "success",
        )

    return redirect(
        url_for(
            "auth.verify_email",
            token=token,
        )
    )


# =========================================================
# VERIFY PHONE
# =========================================================

@auth_bp.route(
    "/verify-phone/<token>",
    methods=["GET", "POST"],
)
def verify_phone(token):
    """
    Second registration verification stage.

    Email must already be verified.

    When phone verification succeeds:
        ->
        Notify SuperAdmins
        ->
        Registration Submitted
    """

    user = (
        _get_phone_verification_user(
            token
        )
    )

    if user is None:

        flash(
            (
                "This phone verification "
                "session is invalid "
                "or has expired."
            ),
            "error",
        )

        return redirect(
            url_for(
                "auth.login"
            )
        )

    # -----------------------------------------------------
    # EMAIL MUST COME FIRST
    # -----------------------------------------------------

    if (
        user.email_verified_at
        is None
    ):

        verification_token = (
            _create_verification_token(
                user
            )
        )

        flash(
            (
                "Please verify your email "
                "before verifying your phone."
            ),
            "warning",
        )

        return redirect(
            url_for(
                "auth.verify_email",
                token=verification_token,
            )
        )

    # -----------------------------------------------------
    # ALREADY VERIFIED
    # -----------------------------------------------------

    if (
        user.phone_verified_at
        is not None
    ):

        return redirect(
            url_for(
                "auth.registration_submitted"
            )
        )

    # Make sure an OTP record exists.
    phone_ready, phone_state = (
        _ensure_phone_verification_started(
            user
        )
    )

    if not phone_ready:

        flash(
            (
                "Phone verification could not "
                "be started. Please try again."
            ),
            "error",
        )

        return redirect(
            url_for(
                "auth.login"
            )
        )

    if (
        phone_state
        == "send_failed"
    ):

        flash(
            (
                "The SMS verification code "
                "could not be sent. "
                "Please use Resend Code."
            ),
            "warning",
        )

    form = (
        PhoneVerificationForm()
    )

    resend_form = (
        ResendVerificationForm()
    )

    masked_phone = (
        _mask_phone_number(
            user.phone_number
        )
    )

    if form.validate_on_submit():

        success, message = (
            verify_phone_code(
                user=user,
                submitted_code=(
                    form.code.data
                ),
            )
        )

        try:

            db.session.commit()

        except SQLAlchemyError:

            db.session.rollback()

            current_app.logger.exception(
                (
                    "Unable to save phone "
                    "verification result."
                )
            )

            flash(
                (
                    "Phone verification could "
                    "not be completed. "
                    "Please try again."
                ),
                "error",
            )

            return render_template(
                "auth/verify_phone.html",
                user=user,
                form=form,
                resend_form=resend_form,
                masked_phone=masked_phone,
                token=token,
            )

        if not success:

            flash(
                message,
                "error",
            )

            return render_template(
                "auth/verify_phone.html",
                user=user,
                form=form,
                resend_form=resend_form,
                masked_phone=masked_phone,
                token=token,
            )

        # -------------------------------------------------
        # EMAIL + PHONE BOTH VERIFIED
        # NOW NOTIFY SUPERADMINS
        # -------------------------------------------------

        _notify_superadmins_of_registration(
            user
        )

        flash(
            (
                "Your phone number has been "
                "verified successfully. "
                "Your registration is now "
                "waiting for SuperAdmin approval."
            ),
            "success",
        )

        return redirect(
            url_for(
                "auth.registration_submitted"
            )
        )

    return render_template(
        "auth/verify_phone.html",
        user=user,
        form=form,
        resend_form=resend_form,
        masked_phone=masked_phone,
        token=token,
    )


# =========================================================
# RESEND PHONE OTP
# =========================================================

@auth_bp.route(
    "/verify-phone/<token>/resend",
    methods=["POST"],
)
def resend_phone_verification_code(
    token,
):
    """
    Resend phone verification SMS OTP.
    """

    user = (
        _get_phone_verification_user(
            token
        )
    )

    if user is None:

        flash(
            (
                "This phone verification "
                "session is invalid "
                "or has expired."
            ),
            "error",
        )

        return redirect(
            url_for(
                "auth.login"
            )
        )

    if (
        user.phone_verified_at
        is not None
    ):

        return redirect(
            url_for(
                "auth.registration_submitted"
            )
        )

    form = (
        ResendVerificationForm()
    )

    if not form.validate_on_submit():

        flash(
            (
                "Unable to resend the "
                "verification code."
            ),
            "error",
        )

        return redirect(
            url_for(
                "auth.verify_phone",
                token=token,
            )
        )

    try:

        phone_code = (
            issue_phone_verification_code(
                user=user,
                is_resend=True,
            )
        )

        db.session.commit()

    except PhoneVerificationRateLimitError as exc:

        db.session.rollback()

        flash(
            str(exc),
            "warning",
        )

        return redirect(
            url_for(
                "auth.verify_phone",
                token=token,
            )
        )

    except SQLAlchemyError:

        db.session.rollback()

        current_app.logger.exception(
            (
                "Database error while "
                "regenerating phone OTP."
            )
        )

        flash(
            (
                "The verification code "
                "could not be regenerated."
            ),
            "error",
        )

        return redirect(
            url_for(
                "auth.verify_phone",
                token=token,
            )
        )

    try:

        send_phone_verification_code_sms(
            user=user,
            code=phone_code,
        )

    except Exception:

        current_app.logger.exception(
            (
                "Unable to resend phone "
                "verification SMS."
            )
        )

        flash(
            (
                "The SMS verification code "
                "could not be sent."
            ),
            "error",
        )

    else:

        flash(
            (
                "A new verification code "
                "has been sent to your phone."
            ),
            "success",
        )

    return redirect(
        url_for(
            "auth.verify_phone",
            token=token,
        )
    )


# =========================================================
# REGISTRATION SUBMITTED
# =========================================================

@auth_bp.route(
    "/registration-submitted"
)
def registration_submitted():
    """
    Registration completed identity verification
    and is waiting for SuperAdmin approval.
    """

    return render_template(
        "auth/registration_submitted.html"
    )


# =========================================================
# FORGOT PASSWORD
# =========================================================

@auth_bp.route(
    "/forgot-password",
    methods=["GET", "POST"],
)
def forgot_password():
    """
    Begin password reset.

    The response intentionally does not reveal
    whether an account exists for the entered email.
    """

    if current_user.is_authenticated:

        return redirect(
            url_for(
                "main.index"
            )
        )

    form = (
        ForgotPasswordForm()
    )

    if form.validate_on_submit():

        email = (
            form.email.data
            .strip()
            .lower()
        )

        user = db.session.scalar(
            db.select(User)
            .where(
                User.email
                == email
            )
        )

        # Always create a browser token,
        # even when no account exists.
        token = (
            _create_password_reset_token(
                email
            )
        )

        if (
            user is not None
            and
            _password_reset_allowed(
                user
            )
        ):

            try:

                existing_reset = (
                    db.session.scalar(
                        db.select(
                            PasswordResetCode
                        ).where(
                            PasswordResetCode.user_id
                            == user.id
                        )
                    )
                )

                reset_code = (
                    issue_password_reset_code(
                        user=user,
                        is_resend=(
                            existing_reset
                            is not None
                        ),
                    )
                )

                db.session.commit()

            except PasswordResetRateLimitError:

                db.session.rollback()

                current_app.logger.info(
                    (
                        "Password reset rate "
                        f"limit reached for "
                        f"user {user.id}."
                    )
                )

            except SQLAlchemyError:

                db.session.rollback()

                current_app.logger.exception(
                    (
                        "Database error while "
                        "creating reset code."
                    )
                )

            else:

                try:

                    send_password_reset_code_email(
                        user=user,
                        code=reset_code,
                    )

                except Exception:

                    current_app.logger.exception(
                        (
                            "Unable to send password "
                            "reset verification email."
                        )
                    )

        flash(
            (
                "If an account exists for this "
                "email, a 6-digit password reset "
                "code has been sent."
            ),
            "info",
        )

        return redirect(
            url_for(
                "auth.verify_password_reset",
                token=token,
            )
        )

    return render_template(
        "auth/forgot_password.html",
        form=form,
    )


# =========================================================
# VERIFY PASSWORD RESET OTP
# =========================================================

@auth_bp.route(
    "/password-reset/verify/<token>",
    methods=["GET", "POST"],
)
def verify_password_reset(
    token,
):
    """
    Verify the password reset email OTP.
    """

    email = (
        _get_password_reset_email(
            token
        )
    )

    if email is None:

        flash(
            (
                "This password reset session "
                "is invalid or has expired."
            ),
            "error",
        )

        return redirect(
            url_for(
                "auth.forgot_password"
            )
        )

    form = (
        PasswordResetVerificationForm()
    )

    resend_form = (
        ResendVerificationForm()
    )

    user = db.session.scalar(
        db.select(User)
        .where(
            User.email
            == email
        )
    )

    if form.validate_on_submit():

        if (
            user is None
            or
            not _password_reset_allowed(
                user
            )
        ):

            flash(
                (
                    "The verification code "
                    "is invalid or has expired."
                ),
                "error",
            )

            return render_template(
                "auth/verify_password_reset.html",
                form=form,
                resend_form=resend_form,
                token=token,
            )

        success, message = (
            verify_password_reset_code(
                user=user,
                submitted_code=(
                    form.code.data
                ),
            )
        )

        try:

            db.session.commit()

        except SQLAlchemyError:

            db.session.rollback()

            current_app.logger.exception(
                (
                    "Unable to save password "
                    "reset verification result."
                )
            )

            flash(
                (
                    "The verification could "
                    "not be completed."
                ),
                "error",
            )

            return render_template(
                "auth/verify_password_reset.html",
                form=form,
                resend_form=resend_form,
                token=token,
            )

        if not success:

            flash(
                message,
                "error",
            )

            return render_template(
                "auth/verify_password_reset.html",
                form=form,
                resend_form=resend_form,
                token=token,
            )

        flash(
            (
                "Verification successful. "
                "You can now create "
                "a new password."
            ),
            "success",
        )

        return redirect(
            url_for(
                "auth.reset_password",
                token=token,
            )
        )

    return render_template(
        "auth/verify_password_reset.html",
        form=form,
        resend_form=resend_form,
        token=token,
    )


# =========================================================
# RESEND PASSWORD RESET OTP
# =========================================================

@auth_bp.route(
    "/password-reset/verify/<token>/resend",
    methods=["POST"],
)
def resend_password_reset_code(
    token,
):
    """
    Resend password reset email OTP.
    """

    email = (
        _get_password_reset_email(
            token
        )
    )

    if email is None:

        flash(
            (
                "This password reset session "
                "is invalid or has expired."
            ),
            "error",
        )

        return redirect(
            url_for(
                "auth.forgot_password"
            )
        )

    form = (
        ResendVerificationForm()
    )

    if not form.validate_on_submit():

        flash(
            (
                "Unable to resend the "
                "verification code."
            ),
            "error",
        )

        return redirect(
            url_for(
                "auth.verify_password_reset",
                token=token,
            )
        )

    user = db.session.scalar(
        db.select(User)
        .where(
            User.email
            == email
        )
    )

    if (
        user is not None
        and
        _password_reset_allowed(
            user
        )
    ):

        try:

            reset_code = (
                issue_password_reset_code(
                    user=user,
                    is_resend=True,
                )
            )

            db.session.commit()

        except PasswordResetRateLimitError as exc:

            db.session.rollback()

            flash(
                str(exc),
                "warning",
            )

            return redirect(
                url_for(
                    "auth.verify_password_reset",
                    token=token,
                )
            )

        except SQLAlchemyError:

            db.session.rollback()

            current_app.logger.exception(
                (
                    "Database error while "
                    "resending password reset OTP."
                )
            )

        else:

            try:

                send_password_reset_code_email(
                    user=user,
                    code=reset_code,
                )

            except Exception:

                current_app.logger.exception(
                    (
                        "Unable to resend password "
                        "reset verification email."
                    )
                )

            else:

                flash(
                    (
                        "A new password reset "
                        "code has been sent."
                    ),
                    "success",
                )

                return redirect(
                    url_for(
                        "auth.verify_password_reset",
                        token=token,
                    )
                )

    flash(
        (
            "If an eligible account exists "
            "for this email, a new verification "
            "code has been sent."
        ),
        "info",
    )

    return redirect(
        url_for(
            "auth.verify_password_reset",
            token=token,
        )
    )


# =========================================================
# RESET PASSWORD
# =========================================================

@auth_bp.route(
    "/password-reset/new/<token>",
    methods=["GET", "POST"],
)
def reset_password(
    token,
):
    """
    Set a new password after successful
    reset-code verification.
    """

    email = (
        _get_password_reset_email(
            token
        )
    )

    if email is None:

        flash(
            (
                "This password reset session "
                "is invalid or has expired."
            ),
            "error",
        )

        return redirect(
            url_for(
                "auth.forgot_password"
            )
        )

    user = db.session.scalar(
        db.select(User)
        .where(
            User.email
            == email
        )
    )

    if (
        user is None
        or
        not _password_reset_allowed(
            user
        )
    ):

        flash(
            (
                "This password reset session "
                "is invalid or has expired."
            ),
            "error",
        )

        return redirect(
            url_for(
                "auth.forgot_password"
            )
        )

    reset = (
        get_valid_verified_reset(
            user
        )
    )

    if reset is None:

        flash(
            (
                "Your password reset "
                "verification has expired. "
                "Please start again."
            ),
            "warning",
        )

        return redirect(
            url_for(
                "auth.forgot_password"
            )
        )

    form = (
        ResetPasswordForm()
    )

    if form.validate_on_submit():

        now = datetime.now(
            timezone.utc
        )

        user.set_password(
            form.password.data
        )

        user.password_changed_at = (
            now
        )

        user.failed_login_attempts = 0
        user.locked_at = None

        # Password reset only automatically
        # unlocks failed-login locks.
        if (
            user.status
            == UserStatus.LOCKED.value
        ):

            user.status = (
                UserStatus.ACTIVE.value
            )

        # Disabled remains disabled.
        # Pending remains pending.

        reset.used_at = now

        try:

            db.session.commit()

        except SQLAlchemyError:

            db.session.rollback()

            current_app.logger.exception(
                (
                    "Database error while "
                    "resetting password."
                )
            )

            flash(
                (
                    "Your password could "
                    "not be changed."
                ),
                "error",
            )

            return render_template(
                "auth/reset_password.html",
                form=form,
                token=token,
            )

        try:

            send_password_changed_email(
                user=user
            )

        except Exception:

            current_app.logger.exception(
                (
                    "Password changed, "
                    "but notification email "
                    "could not be sent."
                )
            )

        flash(
            (
                "Your password has been changed "
                "successfully. You can now sign in "
                "with your new password."
            ),
            "success",
        )

        return redirect(
            url_for(
                "auth.login"
            )
        )

    return render_template(
        "auth/reset_password.html",
        form=form,
        token=token,
    )


# =========================================================
# LOGIN
# =========================================================

@auth_bp.route(
    "/login",
    methods=["GET", "POST"],
)
def login():
    """
    Three supported login identifiers:

    - Email
    - Username
    - Verified Malaysian phone number
    """

    if current_user.is_authenticated:

        return redirect(
            url_for(
                "main.index"
            )
        )

    form = (
        LoginForm()
    )

    if form.validate_on_submit():

        raw_identifier = (
            form.identifier.data
            .strip()
        )

        user = (
            _find_user_by_login_identifier(
                raw_identifier
            )
        )

        # -------------------------------------------------
        # INVALID PASSWORD / ACCOUNT
        # -------------------------------------------------

        if (
            user is None
            or
            not user.check_password(
                form.password.data
            )
        ):

            if user is not None:

                user.failed_login_attempts += 1

                max_attempts = (
                    current_app.config[
                        "MAX_FAILED_LOGIN_ATTEMPTS"
                    ]
                )

                if (
                    user.status
                    == UserStatus.ACTIVE.value
                    and
                    user.failed_login_attempts
                    >= max_attempts
                ):

                    user.status = (
                        UserStatus.LOCKED.value
                    )

                    user.locked_at = (
                        datetime.now(
                            timezone.utc
                        )
                    )

                try:

                    db.session.commit()

                except SQLAlchemyError:

                    db.session.rollback()

                    current_app.logger.exception(
                        (
                            "Unable to update "
                            "failed login counter."
                        )
                    )

            flash(
                "Invalid login credentials.",
                "error",
            )

            return render_template(
                "auth/login.html",
                form=form,
            )

        # -------------------------------------------------
        # PENDING REGISTRATION
        # -------------------------------------------------

        if (
            user.status
            == UserStatus.PENDING.value
        ):

            # Email verification must come first.
            if (
                user.email_verified_at
                is None
            ):

                verification_token = (
                    _create_verification_token(
                        user
                    )
                )

                flash(
                    (
                        "Please verify your email "
                        "address before continuing."
                    ),
                    "warning",
                )

                return redirect(
                    url_for(
                        "auth.verify_email",
                        token=verification_token,
                    )
                )

            # Phone verification comes second.
            if (
                user.phone_verified_at
                is None
            ):

                phone_ready, phone_state = (
                    _ensure_phone_verification_started(
                        user
                    )
                )

                if not phone_ready:

                    flash(
                        (
                            "Phone verification "
                            "could not be started."
                        ),
                        "error",
                    )

                    return render_template(
                        "auth/login.html",
                        form=form,
                    )

                if (
                    phone_state
                    == "send_failed"
                ):

                    flash(
                        (
                            "The SMS could not "
                            "be sent. Please use "
                            "Resend Code."
                        ),
                        "warning",
                    )

                phone_token = (
                    _create_phone_verification_token(
                        user
                    )
                )

                return redirect(
                    url_for(
                        "auth.verify_phone",
                        token=phone_token,
                    )
                )

            # Both verification stages finished.
            flash(
                (
                    "Your account is awaiting "
                    "SuperAdmin approval."
                ),
                "warning",
            )

            return render_template(
                "auth/login.html",
                form=form,
            )

        # -------------------------------------------------
        # REJECTED
        # -------------------------------------------------

        if (
            user.status
            == UserStatus.REJECTED.value
        ):

            flash(
                (
                    "Your registration request "
                    "was not approved."
                ),
                "error",
            )

            return render_template(
                "auth/login.html",
                form=form,
            )

        # -------------------------------------------------
        # DISABLED
        # -------------------------------------------------

        if (
            user.status
            == UserStatus.DISABLED.value
        ):

            flash(
                (
                    "Your account has been disabled. "
                    "Please contact an administrator."
                ),
                "error",
            )

            return render_template(
                "auth/login.html",
                form=form,
            )

        # -------------------------------------------------
        # LOCKED
        # -------------------------------------------------

        if (
            user.status
            == UserStatus.LOCKED.value
        ):

            flash(
                (
                    "Your account is locked due to "
                    "multiple failed login attempts. "
                    "You may reset your password "
                    "to recover your account."
                ),
                "error",
            )

            return render_template(
                "auth/login.html",
                form=form,
            )

        # -------------------------------------------------
        # UNKNOWN STATUS
        # -------------------------------------------------

        if (
            user.status
            != UserStatus.ACTIVE.value
        ):

            flash(
                (
                    "This account is currently "
                    "not available for login."
                ),
                "error",
            )

            return render_template(
                "auth/login.html",
                form=form,
            )

        # -------------------------------------------------
        # SUCCESS
        # -------------------------------------------------

        now = datetime.now(
            timezone.utc
        )

        user.failed_login_attempts = 0
        user.locked_at = None

        user.last_login_at = now
        user.last_active_at = now

        try:

            db.session.commit()

        except SQLAlchemyError:

            db.session.rollback()

            current_app.logger.exception(
                (
                    "Unable to save successful "
                    "login information."
                )
            )

            flash(
                (
                    "The system could not complete "
                    "your login. Please try again."
                ),
                "error",
            )

            return render_template(
                "auth/login.html",
                form=form,
            )

        login_user(
            user,
            remember=(
                form.remember_me.data
            ),
        )

        return redirect(
            url_for(
                "main.index"
            )
        )

    return render_template(
        "auth/login.html",
        form=form,
    )


# =========================================================
# LOGOUT
# =========================================================

@auth_bp.route(
    "/logout",
    methods=["POST"],
)
def logout():
    """
    Sign out the current user.
    """

    if current_user.is_authenticated:

        logout_user()

    flash(
        "You have been signed out.",
        "success",
    )

    return redirect(
        url_for(
            "auth.login"
        )
    )