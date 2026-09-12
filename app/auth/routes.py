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

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.auth import auth_bp

from app.auth.forms import (
    LoginForm,
    RegistrationForm,
)

from app.extensions import db

from app.models import (
    User,
    UserRole,
    UserStatus,
)

from app.services.email_service import (
    send_new_registration_to_superadmins,
)


# =========================================================
# REGISTER
# =========================================================

@auth_bp.route(
    "/register",
    methods=["GET", "POST"],
)
def register():

    # A logged-in user does not need to register again.
    if current_user.is_authenticated:

        return redirect(
            url_for("main.index")
        )

    form = RegistrationForm()

    if form.validate_on_submit():

        # -------------------------------------------------
        # CREATE NEW USER
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

            email=(
                form.email.data
                .strip()
                .lower()
            ),

            username=(
                form.username.data
                .strip()
                .lower()
            ),

            phone_number=(
                form.phone_number.data
                .strip()
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

            # Public registration is always User.
            role=UserRole.USER.value,

            # Every public registration requires
            # SuperAdmin approval.
            status=UserStatus.PENDING.value,
        )

        # Password is hashed before storing.
        user.set_password(
            form.password.data
        )

        # -------------------------------------------------
        # SAVE REGISTRATION
        # -------------------------------------------------

        try:

            db.session.add(user)
            db.session.commit()

        except IntegrityError:

            db.session.rollback()

            flash(
                (
                    "An account with the same email, "
                    "username, phone number, or employee ID "
                    "already exists."
                ),
                "error",
            )

            return render_template(
                "auth/register.html",
                form=form,
            )

        # -------------------------------------------------
        # FIND ACTIVE SUPERADMINS
        # -------------------------------------------------

        superadmins = db.session.scalars(
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
        ).all()

        # -------------------------------------------------
        # NOTIFY SUPERADMINS
        # -------------------------------------------------

        try:

            notification_result = (
                send_new_registration_to_superadmins(
                    applicant=user,
                    superadmins=superadmins,
                )
            )

            current_app.logger.info(
                (
                    "New registration notification result "
                    f"for user {user.id}: "
                    f"{notification_result['sent']} sent, "
                    f"{notification_result['failed']} failed."
                )
            )

        except Exception:

            # Registration remains valid even if
            # notification sending unexpectedly fails.
            current_app.logger.exception(
                (
                    "Unexpected error while sending "
                    "new registration notifications."
                )
            )

        # -------------------------------------------------
        # REGISTRATION COMPLETE
        # -------------------------------------------------

        return redirect(
            url_for(
                "auth.registration_submitted"
            )
        )

    return render_template(
        "auth/register.html",
        form=form,
    )


# =========================================================
# REGISTRATION SUBMITTED
# =========================================================

@auth_bp.route(
    "/registration-submitted"
)
def registration_submitted():

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

    if current_user.is_authenticated:

        return redirect(
            url_for("main.index")
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

        # Login supports:
        # - Email
        # - Username
        # - Phone Number
        user = db.session.scalar(
            db.select(User)
            .where(
                or_(
                    User.email
                    == normalized_identifier,

                    User.username
                    == normalized_identifier,

                    User.phone_number
                    == raw_identifier,
                )
            )
        )

        # -------------------------------------------------
        # INVALID ACCOUNT / PASSWORD
        # -------------------------------------------------

        if (
            user is None
            or not user.check_password(
                form.password.data
            )
        ):

            # Only increment the counter if
            # the account actually exists.
            if user is not None:

                user.failed_login_attempts += 1

                # Automatically lock an active account
                # after too many failed login attempts.
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

            # Do not reveal whether the account exists.
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
                    "multiple failed login attempts."
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
            remember=form.remember_me.data,
        )

        return redirect(
            url_for("main.index")
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
        url_for("auth.login")
    )