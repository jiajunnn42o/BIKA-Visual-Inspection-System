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
    RegistrationForm,
    ResendVerificationForm,
    ResetPasswordForm,
)

from app.extensions import db

from app.models import (
    PasswordResetCode,
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

from app.utils.phone import (
    InvalidPhoneNumberError,
    normalize_malaysian_mobile,
)


# =========================================================
# TOKEN SETTINGS
# =========================================================

# Email verification browser token:
# valid for 7 days.
EMAIL_VERIFICATION_TOKEN_MAX_AGE = (
    7 * 24 * 60 * 60
)

# Password reset browser token:
# valid for 30 minutes.
PASSWORD_RESET_TOKEN_MAX_AGE = (
    30 * 60
)


# =========================================================
# EMAIL VERIFICATION TOKEN HELPERS
# =========================================================

def _verification_serializer():
    """
    Create a signed serializer for the
    email verification browser flow.
    """

    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt="bika-email-verification",
    )


def _create_verification_token(user):
    """
    Create a signed browser token for
    email verification.

    The token is not sent by email.

    The email is included so that an old token
    automatically becomes invalid when the
    user's email address changes.
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
    Read and validate an email verification
    browser token.

    Returns:
        User object if valid.
        None if invalid or expired.
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

    # If the user's email changed after the
    # token was created, reject the old token.
    if (
        user.email
        != token_email
    ):
        return None

    return user


# =========================================================
# PASSWORD RESET TOKEN HELPERS
# =========================================================

def _password_reset_serializer():
    """
    Create a signed serializer for the
    password reset browser flow.
    """

    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt="bika-password-reset",
    )


def _create_password_reset_token(email):
    """
    Create a signed password reset browser token.

    The token is never sent by email.

    Only the email address and token purpose
    are stored inside the signed token.
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


def _get_password_reset_email(token):
    """
    Read a password reset browser token.

    Returns:
        Email address if valid.
        None if invalid or expired.
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
# PASSWORD RESET ACCOUNT RULES
# =========================================================

def _password_reset_allowed(user):
    """
    Decide whether an account is allowed
    to request a password reset.

    Allowed:
    - active
    - locked
    - disabled
    - pending with verified email

    Not allowed:
    - pending with unverified email
    - rejected
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
# REGISTER
# =========================================================

@auth_bp.route(
    "/register",
    methods=["GET", "POST"],
)
def register():
    """
    Public account registration.

    Public registration always starts as:
        role = user
        status = pending

    Email verification must be completed
    before SuperAdmin receives the application.
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
        # NORMALIZE MALAYSIAN PHONE NUMBER
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
        # CREATE USER
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

            # Public registration never
            # allows role selection.
            role=UserRole.USER.value,

            # SuperAdmin approval is required.
            status=UserStatus.PENDING.value,
        )

        user.set_password(
            form.password.data
        )

        # -------------------------------------------------
        # CREATE USER + EMAIL OTP
        # -------------------------------------------------

        try:

            db.session.add(
                user
            )

            # Generate the user ID before commit.
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
                    "Database error while creating "
                    "a new registration."
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
        # CREATE BROWSER VERIFICATION TOKEN
        # -------------------------------------------------

        verification_token = (
            _create_verification_token(
                user
            )
        )

        # -------------------------------------------------
        # SEND 6-DIGIT EMAIL OTP
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
# VERIFY REGISTRATION EMAIL
# =========================================================

@auth_bp.route(
    "/verify-email/<token>",
    methods=["GET", "POST"],
)
def verify_email(token):
    """
    Verify a newly registered email address
    using a 6-digit OTP.
    """

    user = (
        _get_verification_user(
            token
        )
    )

    if user is None:

        flash(
            (
                "This email verification session "
                "is invalid or has expired."
            ),
            "error",
        )

        return redirect(
            url_for(
                "auth.register"
            )
        )

    # Already verified.
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

            # Save both failed attempt counters
            # and successful verification.
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

            result = (
                send_new_registration_to_superadmins(
                    applicant=user,
                    superadmins=superadmins,
                )
            )

            current_app.logger.info(
                (
                    f"User {user.id} verified email. "
                    f"SuperAdmin notifications: "
                    f"{result['sent']} sent, "
                    f"{result['failed']} failed."
                )
            )

        except Exception:

            # User verification must remain successful
            # even if notification email fails.
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
# RESEND REGISTRATION EMAIL OTP
# =========================================================

@auth_bp.route(
    "/verify-email/<token>/resend",
    methods=["POST"],
)
def resend_verification_code(token):
    """
    Send a new registration email
    verification code.
    """

    user = (
        _get_verification_user(
            token
        )
    )

    if user is None:

        flash(
            (
                "This email verification session "
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
                "Unable to create a new "
                "email verification code."
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
    Registration has passed email verification
    and is now waiting for SuperAdmin approval.
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
    Start the password reset process.

    Security:
    The response must not reveal whether
    an email address exists in the system.
    """

    if current_user.is_authenticated:

        return redirect(
            url_for(
                "main.index"
            )
        )

    form = ForgotPasswordForm()

    if form.validate_on_submit():

        email = (
            form.email.data
            .strip()
            .lower()
        )

        # -------------------------------------------------
        # LOOK UP ACCOUNT
        # -------------------------------------------------

        user = db.session.scalar(
            db.select(User)
            .where(
                User.email == email
            )
        )

        # The browser token is created even when
        # the account does not exist.
        #
        # This helps prevent account enumeration.
        token = (
            _create_password_reset_token(
                email
            )
        )

        # -------------------------------------------------
        # ONLY SEND OTP FOR ELIGIBLE ACCOUNTS
        # -------------------------------------------------

        if (
            user is not None
            and
            _password_reset_allowed(user)
        ):

            try:

                # Check whether a reset record
                # already exists.
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

                # Repeated Forgot Password requests
                # should also respect resend limits.
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

                # Do not reveal whether this email exists.
                current_app.logger.info(
                    (
                        "Password reset rate limit "
                        f"reached for account {user.id}."
                    )
                )

            except SQLAlchemyError:

                db.session.rollback()

                current_app.logger.exception(
                    (
                        "Database error while creating "
                        "password reset code."
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

        # -------------------------------------------------
        # GENERIC RESPONSE
        # -------------------------------------------------

        flash(
            (
                "If an account exists for this email, "
                "a 6-digit password reset code "
                "has been sent."
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
def verify_password_reset(token):
    """
    Verify the 6-digit password reset code.
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
            User.email == email
        )
    )

    if form.validate_on_submit():

        # -------------------------------------------------
        # GENERIC FAILURE FOR INVALID / INELIGIBLE ACCOUNT
        # -------------------------------------------------

        if (
            user is None
            or
            not _password_reset_allowed(user)
        ):

            flash(
                (
                    "The verification code is "
                    "invalid or has expired."
                ),
                "error",
            )

            return render_template(
                "auth/verify_password_reset.html",
                form=form,
                resend_form=resend_form,
                token=token,
            )

        # -------------------------------------------------
        # VERIFY OTP
        # -------------------------------------------------

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
                    "The verification could not "
                    "be completed. Please try again."
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
                "You can now create a new password."
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
def resend_password_reset_code(token):
    """
    Send another password reset OTP.

    The response avoids exposing whether
    the submitted email exists.
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
            User.email == email
        )
    )

    # -----------------------------------------------------
    # REAL ELIGIBLE ACCOUNT
    # -----------------------------------------------------

    if (
        user is not None
        and
        _password_reset_allowed(user)
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
                    "Database error while resending "
                    "password reset code."
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
                        "reset verification code."
                    )
                )

            else:

                flash(
                    (
                        "A new password reset code "
                        "has been sent to your email."
                    ),
                    "success",
                )

                return redirect(
                    url_for(
                        "auth.verify_password_reset",
                        token=token,
                    )
                )

    # -----------------------------------------------------
    # GENERIC RESPONSE FOR UNKNOWN / INELIGIBLE ACCOUNT
    # -----------------------------------------------------

    flash(
        (
            "If an eligible account exists for "
            "this email, a new verification code "
            "has been sent."
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
def reset_password(token):
    """
    Set a new password after successful
    password reset OTP verification.
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
            User.email == email
        )
    )

    if (
        user is None
        or
        not _password_reset_allowed(user)
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

    # -----------------------------------------------------
    # RESET MUST HAVE PASSED OTP VERIFICATION
    # -----------------------------------------------------

    reset = (
        get_valid_verified_reset(
            user
        )
    )

    if reset is None:

        flash(
            (
                "Your password reset verification "
                "has expired. Please start again."
            ),
            "warning",
        )

        return redirect(
            url_for(
                "auth.forgot_password"
            )
        )

    form = ResetPasswordForm()

    if form.validate_on_submit():

        now = datetime.now(
            timezone.utc
        )

        # -------------------------------------------------
        # SET NEW PASSWORD
        # -------------------------------------------------

        user.set_password(
            form.password.data
        )

        user.password_changed_at = (
            now
        )

        # -------------------------------------------------
        # CLEAR FAILED LOGIN SECURITY STATE
        # -------------------------------------------------

        user.failed_login_attempts = 0
        user.locked_at = None

        # A password reset unlocks accounts locked
        # specifically by failed login attempts.
        if (
            user.status
            == UserStatus.LOCKED.value
        ):

            user.status = (
                UserStatus.ACTIVE.value
            )

        # Disabled accounts remain disabled.
        # Pending accounts remain pending.

        # -------------------------------------------------
        # INVALIDATE RESET REQUEST
        # -------------------------------------------------

        reset.used_at = now

        # -------------------------------------------------
        # SAVE
        # -------------------------------------------------

        try:

            db.session.commit()

        except SQLAlchemyError:

            db.session.rollback()

            current_app.logger.exception(
                (
                    "Database error while resetting "
                    "account password."
                )
            )

            flash(
                (
                    "Your password could not "
                    "be changed. Please try again."
                ),
                "error",
            )

            return render_template(
                "auth/reset_password.html",
                form=form,
                token=token,
            )

        # -------------------------------------------------
        # SECURITY NOTIFICATION EMAIL
        # -------------------------------------------------

        try:

            send_password_changed_email(
                user=user
            )

        except Exception:

            current_app.logger.exception(
                (
                    "Password changed successfully, "
                    "but security notification email "
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
    Authenticate using:

    - Email
    - Username

    Phone number is profile/contact information
    only and is not a login identifier.
    """

    if current_user.is_authenticated:

        return redirect(
            url_for(
                "main.index"
            )
        )

    form = LoginForm()

    if form.validate_on_submit():

        identifier = (
            form.identifier.data
            .strip()
            .lower()
        )

        user = db.session.scalar(
            db.select(User)
            .where(
                or_(
                    User.email
                    == identifier,

                    User.username
                    == identifier,
                )
            )
        )

        # -------------------------------------------------
        # INVALID LOGIN
        # -------------------------------------------------

        if (
            user is None
            or
            not user.check_password(
                form.password.data
            )
        ):

            # Only update failed attempts when
            # the account actually exists.
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
                            "Unable to update failed "
                            "login attempt counter."
                        )
                    )

            # Generic response prevents account
            # enumeration.
            flash(
                "Invalid login credentials.",
                "error",
            )

            return render_template(
                "auth/login.html",
                form=form,
            )

        # -------------------------------------------------
        # PENDING ACCOUNT
        # -------------------------------------------------

        if (
            user.status
            == UserStatus.PENDING.value
        ):

            # Email is not verified yet.
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
        # REJECTED ACCOUNT
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
        # DISABLED ACCOUNT
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
        # LOCKED ACCOUNT
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
        # SUCCESSFUL LOGIN
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