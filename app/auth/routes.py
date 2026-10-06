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

from sqlalchemy import (
    delete,
    or_,
)

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

from app.workflow_models import (
    Notification,
    UserNotificationPreference,
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
    Notify active SuperAdmins only after BOTH email and
    phone verification have completed.

    Channels respect each SuperAdmin's saved preferences:

        email_notifications
        in_app_alerts

    The in-app notification links directly to the exact
    registration request and opens its Review modal.
    """

    superadmins = (
        db.session.scalars(
            db.select(
                User
            )
            .where(
                User.role
                ==
                UserRole.SUPERADMIN.value,

                User.status
                ==
                UserStatus.ACTIVE.value,
            )
            .order_by(
                User.id.asc()
            )
        )
        .all()
    )

    if not superadmins:

        current_app.logger.info(
            (
                "Registration %s completed identity "
                "verification, but there are no active "
                "SuperAdmins to notify."
            ),
            user.id,
        )

        return

    email_recipients = []
    in_app_recipients = []

    # -----------------------------------------------------
    # READ EACH SUPERADMIN'S PREFERENCE
    # -----------------------------------------------------

    for superadmin in superadmins:

        preferences = (
            db.session.get(
                UserNotificationPreference,
                superadmin.id,
            )
        )

        # No preference row means the defaults are ON.
        email_enabled = (
            True
            if preferences is None
            else bool(
                preferences.email_notifications
            )
        )

        in_app_enabled = (
            True
            if preferences is None
            else bool(
                preferences.in_app_alerts
            )
        )

        if email_enabled:
            email_recipients.append(
                superadmin
            )

        if in_app_enabled:
            in_app_recipients.append(
                superadmin
            )

    # -----------------------------------------------------
    # CREATE IN-APP NOTIFICATIONS
    # -----------------------------------------------------

    review_link = (
        url_for(
            "superadmin.pending_registrations",
            status="pending",
            review=user.id,
        )
    )

    now = datetime.now(
        timezone.utc
    )

    for superadmin in in_app_recipients:

        db.session.add(
            Notification(
                recipient_user_id=(
                    superadmin.id
                ),
                actor_user_id=(
                    user.id
                ),
                notification_type=(
                    "registration_request_submitted"
                ),
                title=(
                    "New Registration Request"
                ),
                message=(
                    f"{user.full_name} completed registration "
                    "verification and is waiting for your review."
                ),
                link=(
                    review_link
                ),
                payload_json={
                    "user_id": user.id,
                    "registration_status": "pending",
                },
                is_read=False,
                read_at=None,
                created_at=(
                    now
                ),
            )
        )

    if in_app_recipients:

        try:

            db.session.commit()

        except SQLAlchemyError:

            db.session.rollback()

            current_app.logger.exception(
                (
                    "Unable to create in-app registration "
                    "notifications for applicant %s."
                ),
                user.id,
            )

    # -----------------------------------------------------
    # SEND EMAIL NOTIFICATIONS
    # -----------------------------------------------------

    if email_recipients:

        try:

            result = (
                send_new_registration_to_superadmins(
                    applicant=user,
                    superadmins=(
                        email_recipients
                    ),
                )
            )

            current_app.logger.info(
                (
                    "Registration %s completed identity "
                    "verification. SuperAdmin email: %s sent, "
                    "%s failed. In-app notifications: %s."
                ),
                user.id,
                result["sent"],
                result["failed"],
                len(
                    in_app_recipients
                ),
            )

        except Exception:

            current_app.logger.exception(
                (
                    "Unable to email SuperAdmins about "
                    "verified registration %s."
                ),
                user.id,
            )

    else:

        current_app.logger.info(
            (
                "Registration %s completed verification. "
                "All active SuperAdmins have email "
                "notifications disabled. In-app notifications: %s."
            ),
            user.id,
            len(
                in_app_recipients
            ),
        )


# =========================================================
# LOGIN IDENTIFIER HELPER
# =========================================================

def _find_user_by_login_identifier(raw_identifier):
    """
    Login by:
    1. Email
    2. Username
    3. Verified Malaysian phone number

    Email and username lookup are handled separately
    to avoid ambiguous account matches.
    """

    raw_identifier = str(
        raw_identifier or ""
    ).strip()

    normalized_identifier = (
        raw_identifier.lower()
    )

    # =====================================================
    # EMAIL
    # =====================================================

    if "@" in normalized_identifier:

        return db.session.scalar(
            db.select(User)
            .where(
                db.func.lower(User.email)
                == normalized_identifier
            )
            .limit(1)
        )

    # =====================================================
    # USERNAME
    # =====================================================

    user = db.session.scalar(
        db.select(User)
        .where(
            db.func.lower(User.username)
            == normalized_identifier
        )
        .limit(1)
    )

    if user is not None:
        return user

    # =====================================================
    # PHONE
    # =====================================================

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
        .limit(1)
    )

# =========================================================
# REJECTED REGISTRATION RE-APPLICATION HELPERS
# =========================================================

def _find_rejected_registration_by_email(
    email,
):
    """
    Find the rejected account that owns the submitted email.

    Re-applications reuse the original User row instead of
    inserting another row with duplicate unique values.
    """

    email = (
        str(
            email
            or
            ""
        )
        .strip()
        .lower()
    )

    if not email:
        return None

    return db.session.scalar(
        db.select(
            User
        )
        .where(
            db.func.lower(
                User.email
            )
            ==
            email,

            User.status
            ==
            UserStatus.REJECTED.value,
        )
        .limit(1)
    )


def _registration_unique_conflict(
    *,
    username,
    email,
    phone_number,
    employee_id,
    exclude_user_id=None,
):
    """
    Final server-side uniqueness protection.

    A rejected applicant may reuse values that already belong
    to their own old row, but values belonging to another row
    are still rejected.
    """

    username = (
        str(
            username
            or
            ""
        )
        .strip()
        .lower()
    )

    email = (
        str(
            email
            or
            ""
        )
        .strip()
        .lower()
    )

    phone_number = (
        str(
            phone_number
            or
            ""
        )
        .strip()
    )

    employee_id = (
        str(
            employee_id
            or
            ""
        )
        .strip()
        .upper()
    )


    def another_user_exists(
        condition,
    ):

        query = (
            db.select(
                User.id
            )
            .where(
                condition
            )
        )

        if (
            exclude_user_id
            is not None
        ):

            query = query.where(
                User.id
                !=
                exclude_user_id
            )

        existing_id = (
            db.session.scalar(
                query.limit(1)
            )
        )

        return (
            existing_id
            is not None
        )


    if another_user_exists(
        db.func.lower(
            User.username
        )
        ==
        username
    ):

        return (
            "This username is already in use."
        )


    if another_user_exists(
        db.func.lower(
            User.email
        )
        ==
        email
    ):

        return (
            "This email address is already registered."
        )


    if another_user_exists(
        User.phone_number
        ==
        phone_number
    ):

        return (
            "This phone number is already registered."
        )


    if another_user_exists(
        db.func.upper(
            User.employee_id
        )
        ==
        employee_id
    ):

        return (
            "This employee ID is already registered."
        )


    return None


def _prepare_rejected_registration_for_reapplication(
    *,
    user,
    first_name,
    last_name,
    username,
    email,
    phone_number,
    employee_id,
    password,
):
    """
    Turn one rejected registration back into a fresh pending
    application while keeping the same User primary key.

    Identity verification is intentionally reset so the
    applicant must verify Email -> Phone again.
    """

    user.first_name = (
        first_name
    )

    user.last_name = (
        last_name
    )

    user.username = (
        username
    )

    user.email = (
        email
    )

    user.phone_number = (
        phone_number
    )

    user.employee_id = (
        employee_id
    )

    user.set_password(
        password
    )


    # Employment data is assigned again by SuperAdmin.
    user.job_title = None
    user.department = None
    user.shift = None

    # Public registration always restarts as a normal user.
    user.role = (
        UserRole.USER.value
    )

    user.status = (
        UserStatus.PENDING.value
    )


    # Force both verification stages to run again.
    user.email_verified_at = None
    user.phone_verified_at = None


    # Reset old decision state.
    user.approved_at = None
    user.approved_by = None

    user.rejected_at = None
    user.rejected_by = None
    user.rejection_reason = None


    # Reset failed-login lock state.
    user.failed_login_attempts = 0
    user.locked_at = None


    # A previous phone-verification row may still exist from
    # the rejected attempt. Remove it so the normal Email ->
    # Phone flow creates and sends a genuinely fresh phone OTP.
    db.session.execute(
        delete(
            PhoneVerification
        )
        .where(
            PhoneVerification.user_id
            ==
            user.id
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

    A rejected applicant may register again with the same
    email. In that case the existing rejected User row is
    reused instead of creating a duplicate row.

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
        # NORMALIZE VALUES
        # -------------------------------------------------

        first_name = (
            form.first_name.data
            .strip()
        )

        last_name = (
            form.last_name.data
            .strip()
        )

        username = (
            form.username.data
            .strip()
            .lower()
        )

        email = (
            form.email.data
            .strip()
            .lower()
        )

        employee_id = (
            form.employee_id.data
            .strip()
            .upper()
        )

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
        # CHECK FOR REJECTED APPLICATION USING THIS EMAIL
        # -------------------------------------------------

        rejected_user = (
            _find_rejected_registration_by_email(
                email
            )
        )

        exclude_user_id = (
            rejected_user.id
            if rejected_user
            else None
        )

        # -------------------------------------------------
        # FINAL UNIQUE CHECK
        #
        # Own values from the rejected row are allowed.
        # Values owned by any other account remain blocked.
        # -------------------------------------------------

        uniqueness_error = (
            _registration_unique_conflict(
                username=username,
                email=email,
                phone_number=phone_number,
                employee_id=employee_id,
                exclude_user_id=(
                    exclude_user_id
                ),
            )
        )

        if uniqueness_error:

            flash(
                uniqueness_error,
                "error",
            )

            return render_template(
                "auth/register.html",
                form=form,
            )

        # -------------------------------------------------
        # RE-APPLICATION OR BRAND-NEW USER
        # -------------------------------------------------

        if rejected_user:

            user = (
                rejected_user
            )

            _prepare_rejected_registration_for_reapplication(
                user=user,
                first_name=first_name,
                last_name=last_name,
                username=username,
                email=email,
                phone_number=phone_number,
                employee_id=employee_id,
                password=form.password.data,
            )

        else:

            user = User(
                first_name=(
                    first_name
                ),

                last_name=(
                    last_name
                ),

                username=(
                    username
                ),

                email=(
                    email
                ),

                phone_number=(
                    phone_number
                ),

                employee_id=(
                    employee_id
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

            db.session.add(
                user
            )

        # -------------------------------------------------
        # SAVE ACCOUNT + CREATE FRESH EMAIL OTP
        # -------------------------------------------------

        try:

            # A new user needs an ID before the verification
            # record can reference it. For a rejected user this
            # simply flushes the refreshed account state.
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
                    "creating or resubmitting "
                    "registration."
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

        except Exception:

            db.session.rollback()

            current_app.logger.exception(
                (
                    "Unable to prepare a fresh "
                    "email verification code "
                    "for registration."
                )
            )

            flash(
                (
                    "Your registration could not "
                    "be prepared for email "
                    "verification. Please try again."
                ),
                "error",
            )

            return render_template(
                "auth/register.html",
                form=form,
            )

        # -------------------------------------------------
        # EMAIL VERIFICATION BROWSER TOKEN
        # -------------------------------------------------

        verification_token = (
            _create_verification_token(
                user
            )
        )

        # -------------------------------------------------
        # SEND FRESH EMAIL OTP
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
                    "Your registration was saved, "
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