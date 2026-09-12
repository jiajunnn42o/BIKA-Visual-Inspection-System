from datetime import datetime, timezone

from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
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
    LoginForm,
    RegistrationForm,
    ResendVerificationForm,
)

from app.extensions import db

from app.models import (
    User,
    UserRole,
    UserStatus,
)

from app.services.email_service import (
    send_email_verification_code_email,
    send_new_registration_to_superadmins,
)

from app.services.email_verification_service import (
    VerificationRateLimitError,
    issue_verification_code,
    verify_email_code,
)

from app.utils.phone import (
    normalize_malaysian_mobile,
)

# =========================================================
# EMAIL VERIFICATION TOKEN SETTINGS
# =========================================================

EMAIL_VERIFICATION_TOKEN_MAX_AGE = (
    7 * 24 * 60 * 60
)


def _verification_serializer():
    """
    Create a signed serializer used for email
    verification URLs.
    """

    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt="bika-email-verification",
    )


def _create_verification_token(user):
    """
    Create a signed verification token.

    The token contains:
    - User ID
    - Current email address

    If the user's email changes, the old token
    automatically becomes invalid.
    """

    return (
        _verification_serializer()
        .dumps(
            {
                "user_id": user.id,
                "email": user.email,
            }
        )
    )


def _get_verification_user(token):
    """
    Read and validate a verification token.

    Returns:
        User object
        or None if invalid / expired.
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

    user_id = data.get(
        "user_id"
    )

    email = data.get(
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

    # If the account email was changed after
    # this token was generated, invalidate it.
    if user.email != email:
        return None

    return user


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

    New users:
    - Always receive role = user
    - Always receive status = pending
    - Must verify their email
    - Cannot log in until SuperAdmin approval
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
        # CREATE USER OBJECT
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
                normalize_malaysian_mobile(
                    form.phone_number.data
                )
            ),

            job_title=(
                form.job_title.data
                .strip()
            ),

            department=(
                form.department.data
                .strip()
            ),

            shift=(
                form.shift.data
                .strip()
            ),

            employee_id=(
                form.employee_id.data
                .strip()
                .upper()
            ),

            # Public users cannot select their role.
            role=UserRole.USER.value,

            # Registration requires SuperAdmin approval.
            status=UserStatus.PENDING.value,
        )

        # Password is hashed before being stored.
        user.set_password(
            form.password.data
        )

        # -------------------------------------------------
        # CREATE USER + VERIFICATION CODE
        # IN ONE DATABASE TRANSACTION
        # -------------------------------------------------

        try:

            db.session.add(
                user
            )

            # Assign an ID without committing yet.
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
                    "An account with the same email, "
                    "username, phone number, or "
                    "employee ID already exists."
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
                    "Database error while creating "
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

        # -------------------------------------------------
        # CREATE VERIFICATION URL
        # -------------------------------------------------

        verification_token = (
            _create_verification_token(
                user
            )
        )

        # -------------------------------------------------
        # SEND VERIFICATION EMAIL
        # -------------------------------------------------

        try:

            send_email_verification_code_email(
                user=user,
                code=verification_code,
            )

        except Exception:

            # Account remains created.
            # User may request another verification code.
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
    Verify ownership of the registered email
    using a 6-digit verification code.
    """

    user = (
        _get_verification_user(
            token
        )
    )

    if user is None:

        flash(
            (
                "This email verification link "
                "is invalid or has expired."
            ),
            "error",
        )

        return redirect(
            url_for(
                "auth.register"
            )
        )

    # -----------------------------------------------------
    # ALREADY VERIFIED
    # -----------------------------------------------------

    if (
        user.email_verified_at
        is not None
    ):

        return redirect(
            url_for(
                "auth.registration_submitted"
            )
        )

    form = (
        EmailVerificationForm()
    )

    resend_form = (
        ResendVerificationForm()
    )

    # -----------------------------------------------------
    # VERIFY SUBMITTED CODE
    # -----------------------------------------------------

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
        # NOW NOTIFY ACTIVE SUPERADMINS
        # -------------------------------------------------

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

            notification_result = (
                send_new_registration_to_superadmins(
                    applicant=user,
                    superadmins=superadmins,
                )
            )

            current_app.logger.info(
                (
                    "Registration email verified. "
                    f"User ID {user.id}. "
                    f"SuperAdmin notifications: "
                    f"{notification_result['sent']} sent, "
                    f"{notification_result['failed']} failed."
                )
            )

        except Exception:

            # Email verification remains successful
            # even if SuperAdmin notification fails.
            current_app.logger.exception(
                (
                    "Unable to notify SuperAdmins "
                    "after email verification."
                )
            )

        flash(
            (
                "Your email has been verified "
                "successfully. Your registration "
                "is now waiting for SuperAdmin "
                "approval."
            ),
            "success",
        )

        return redirect(
            url_for(
                "auth.registration_submitted"
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
# RESEND EMAIL VERIFICATION CODE
# =========================================================

@auth_bp.route(
    "/verify-email/<token>/resend",
    methods=["POST"],
)
def resend_verification_code(token):
    """
    Send a new 6-digit verification code.

    Security limits are handled by
    email_verification_service.py.
    """

    user = (
        _get_verification_user(
            token
        )
    )

    if user is None:

        flash(
            (
                "This email verification link "
                "is invalid or has expired."
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
                "auth.verify_email",
                token=token,
            )
        )

    # -----------------------------------------------------
    # CREATE NEW VERIFICATION CODE
    # -----------------------------------------------------

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
                "verification code."
            )
        )

        flash(
            (
                "The verification code could "
                "not be regenerated."
            ),
            "error",
        )

        return redirect(
            url_for(
                "auth.verify_email",
                token=token,
            )
        )

    # -----------------------------------------------------
    # SEND NEW CODE
    # -----------------------------------------------------

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
# REGISTRATION SUBMITTED
# =========================================================

@auth_bp.route(
    "/registration-submitted"
)
def registration_submitted():
    """
    Displayed after the user's email
    has been verified.
    """

    return render_template(
        "auth/registration_submitted.html"
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
    Authenticate using:
    - Email
    - Username
    - Phone Number
    """

    if current_user.is_authenticated:

        return redirect(
            url_for(
                "main.index"
            )
        )

    form = LoginForm()

    if form.validate_on_submit():

        raw_identifier = (
            form.identifier.data
            .strip()
        )

        normalized_identifier = (
            raw_identifier.lower()
        )

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

        # -------------------------------------------------
        # INVALID CREDENTIALS
        # -------------------------------------------------

        if (
            user is None
            or not user.check_password(
                form.password.data
            )
        ):

            if user is not None:

                user.failed_login_attempts += 1

                if (
                    user.status
                    == UserStatus.ACTIVE.value
                    and
                    user.failed_login_attempts
                    >= current_app.config[
                        "MAX_FAILED_LOGIN_ATTEMPTS"
                    ]
                ):

                    user.status = (
                        UserStatus.LOCKED.value
                    )

                    user.locked_at = (
                        datetime.now(
                            timezone.utc
                        )
                    )

                db.session.commit()

            # Do not reveal whether the
            # account exists.
            flash(
                "Invalid login credentials.",
                "error",
            )

            return render_template(
                "auth/login.html",
                form=form,
            )

        # -------------------------------------------------
        # PENDING
        # -------------------------------------------------

        if (
            user.status
            == UserStatus.PENDING.value
        ):

            # Email has not been verified yet.
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

            # Email already verified.
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
                    "Your account is locked due "
                    "to multiple failed login attempts."
                ),
                "error",
            )

            return render_template(
                "auth/login.html",
                form=form,
            )

        # -------------------------------------------------
        # UNKNOWN ACCOUNT STATUS
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

        user.failed_login_attempts = 0
        user.locked_at = None

        now = datetime.now(
            timezone.utc
        )

        user.last_login_at = now
        user.last_active_at = now

        db.session.commit()

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