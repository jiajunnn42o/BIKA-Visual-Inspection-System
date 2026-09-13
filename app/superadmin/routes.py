from datetime import (
    datetime,
    timezone,
)

from functools import wraps


from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    url_for,
)

from flask_login import (
    current_user,
    login_required,
)

from sqlalchemy.exc import (
    IntegrityError,
    SQLAlchemyError,
)


from app.extensions import db

from app.models import (
    User,
    UserRole,
    UserStatus,
)

from app.services.email_service import (
    send_email_verification_code_email,
    send_registration_approved_email,
    send_registration_rejected_email,
)

from app.services.email_verification_service import (
    issue_verification_code,
)

from app.services.phone_verification_service import (
    issue_phone_verification_code,
)

from app.services.sms_service import (
    send_phone_verification_code_sms,
)

from app.utils.phone import (
    InvalidPhoneNumberError,
    normalize_malaysian_mobile,
)


from app.superadmin import (
    superadmin_bp,
)

from app.superadmin.forms import (
    ApproveRegistrationForm,
    DEPARTMENT_CHOICES,
    JOB_TITLE_CHOICES,
    RejectRegistrationForm,
    ReviewRegistrationForm,
    ROLE_CHOICES,
    SHIFT_CHOICES,
)


# =========================================================
# VALID VALUES
# =========================================================

VALID_JOB_TITLES = {
    value
    for value, _label
    in JOB_TITLE_CHOICES
    if value
}


VALID_DEPARTMENTS = {
    value
    for value, _label
    in DEPARTMENT_CHOICES
    if value
}


VALID_SHIFTS = {
    value
    for value, _label
    in SHIFT_CHOICES
    if value
}


VALID_ROLES = {
    value
    for value, _label
    in ROLE_CHOICES
    if value
}


# =========================================================
# SUPERADMIN PERMISSION
# =========================================================

def superadmin_required(
    view_function,
):
    """
    Restrict route access to
    authenticated SuperAdmins.
    """

    @wraps(
        view_function
    )
    @login_required
    def wrapped_view(
        *args,
        **kwargs,
    ):

        if (
            current_user.role
            != UserRole.SUPERADMIN.value
        ):

            abort(
                403
            )

        return view_function(
            *args,
            **kwargs,
        )

    return wrapped_view


# =========================================================
# HELPERS
# =========================================================

def _get_pending_user_or_404(
    user_id,
):
    """
    Retrieve a pending applicant.

    Only pending registrations can
    be processed through this workflow.
    """

    user = db.session.get(
        User,
        user_id,
    )

    if user is None:

        abort(
            404
        )

    if (
        user.status
        != UserStatus.PENDING.value
    ):

        abort(
            404
        )

    return user


def _user_exists(
    field,
    value,
    exclude_user_id,
):
    """
    Check whether another user already
    owns a unique value.
    """

    if not value:

        return False

    existing_id = db.session.scalar(
        db.select(
            User.id
        )
        .where(
            field == value,
            User.id
            != exclude_user_id,
        )
        .limit(
            1
        )
    )

    return (
        existing_id
        is not None
    )


def _prepare_review_form(
    user,
):
    """
    Create a ReviewRegistrationForm
    populated using the applicant data.

    Old registrations may contain legacy
    employment values from before the
    fields became SuperAdmin-managed.

    Only valid current choices are loaded.
    """

    form = (
        ReviewRegistrationForm(
            obj=user
        )
    )

    # -----------------------------------------------------
    # ROLE
    # -----------------------------------------------------

    if (
        user.role
        in VALID_ROLES
    ):

        form.role.data = (
            user.role
        )

    else:

        form.role.data = (
            UserRole.USER.value
        )


    # -----------------------------------------------------
    # JOB TITLE
    # -----------------------------------------------------

    if (
        user.job_title
        in VALID_JOB_TITLES
    ):

        form.job_title.data = (
            user.job_title
        )

    else:

        form.job_title.data = ""


    # -----------------------------------------------------
    # DEPARTMENT
    # -----------------------------------------------------

    if (
        user.department
        in VALID_DEPARTMENTS
    ):

        form.department.data = (
            user.department
        )

    else:

        form.department.data = ""


    # -----------------------------------------------------
    # SHIFT
    # -----------------------------------------------------

    if (
        user.shift
        in VALID_SHIFTS
    ):

        form.shift.data = (
            user.shift
        )

    else:

        form.shift.data = ""

    return form


def _validate_unique_fields(
    user,
    username,
    email,
    phone_number,
    employee_id,
):
    """
    Validate applicant unique account values.

    Returns:
        error_message or None
    """

    if _user_exists(
        User.username,
        username,
        user.id,
    ):

        return (
            "This username is already in use."
        )


    if _user_exists(
        User.email,
        email,
        user.id,
    ):

        return (
            "This email address is already in use."
        )


    if _user_exists(
        User.phone_number,
        phone_number,
        user.id,
    ):

        return (
            "This phone number is already in use."
        )


    if _user_exists(
        User.employee_id,
        employee_id,
        user.id,
    ):

        return (
            "This Employee ID is already in use."
        )


    return None


def _employment_fields_complete(
    user,
):
    """
    Return missing or invalid employment fields.

    Approval requires all three fields
    to contain a predefined valid value.
    """

    missing_fields = []


    if (
        not user.job_title
        or
        user.job_title
        not in VALID_JOB_TITLES
    ):

        missing_fields.append(
            "Job Title"
        )


    if (
        not user.department
        or
        user.department
        not in VALID_DEPARTMENTS
    ):

        missing_fields.append(
            "Department"
        )


    if (
        not user.shift
        or
        user.shift
        not in VALID_SHIFTS
    ):

        missing_fields.append(
            "Shift"
        )


    return missing_fields


# =========================================================
# PENDING REGISTRATIONS
# =========================================================

@superadmin_bp.route(
    "/registrations"
)
@superadmin_required
def pending_registrations():
    """
    Show applications that completed BOTH:

        Email verification
        Phone verification

    Accounts that have not completed both
    verification stages are intentionally
    hidden from the SuperAdmin review queue.
    """

    pending_users = (
        db.session.scalars(
            db.select(
                User
            )
            .where(
                User.status
                == UserStatus.PENDING.value,

                User.email_verified_at
                .is_not(None),

                User.phone_verified_at
                .is_not(None),
            )
            .order_by(
                User.created_at.asc()
            )
        )
        .all()
    )


    return render_template(
        "superadmin/pending_registrations.html",
        pending_users=pending_users,
    )


# =========================================================
# REVIEW REGISTRATION
# =========================================================

@superadmin_bp.route(
    "/registrations/<int:user_id>"
)
@superadmin_required
def review_registration(
    user_id,
):
    """
    Display one pending registration.
    """

    user = (
        _get_pending_user_or_404(
            user_id
        )
    )


    form = (
        _prepare_review_form(
            user
        )
    )


    approve_form = (
        ApproveRegistrationForm()
    )


    reject_form = (
        RejectRegistrationForm()
    )


    return render_template(
        "superadmin/review_registration.html",

        user=user,

        form=form,

        approve_form=(
            approve_form
        ),

        reject_form=(
            reject_form
        ),

        # Legacy values are passed only
        # so the UI can tell the SuperAdmin
        # that old invalid data needs replacing.

        legacy_job_title=(
            user.job_title
            if (
                user.job_title
                and
                user.job_title
                not in VALID_JOB_TITLES
            )
            else None
        ),

        legacy_department=(
            user.department
            if (
                user.department
                and
                user.department
                not in VALID_DEPARTMENTS
            )
            else None
        ),

        legacy_shift=(
            user.shift
            if (
                user.shift
                and
                user.shift
                not in VALID_SHIFTS
            )
            else None
        ),
    )


# =========================================================
# SAVE REGISTRATION CHANGES
# =========================================================

@superadmin_bp.route(
    "/registrations/<int:user_id>/save",
    methods=["POST"],
)
@superadmin_required
def save_registration_changes(
    user_id,
):
    """
    Save changes made by the SuperAdmin.

    Employment fields can still be empty
    at this stage.

    Changing email:
        email_verified_at -> None
        new Email OTP

    Changing phone:
        phone_verified_at -> None
        new Phone OTP
    """

    user = (
        _get_pending_user_or_404(
            user_id
        )
    )


    form = (
        ReviewRegistrationForm()
    )


    if not form.validate_on_submit():

        for field_errors in (
            form.errors.values()
        ):

            for error in field_errors:

                flash(
                    error,
                    "error",
                )

        return redirect(
            url_for(
                "superadmin.review_registration",
                user_id=user.id,
            )
        )


    # =====================================================
    # NORMALIZE VALUES
    # =====================================================

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


    job_title = (
        form.job_title.data
        .strip()
        if form.job_title.data
        else None
    )


    department = (
        form.department.data
        .strip()
        if form.department.data
        else None
    )


    shift = (
        form.shift.data
        .strip()
        if form.shift.data
        else None
    )


    role = (
        form.role.data
        .strip()
        .lower()
    )


    # =====================================================
    # NORMALIZE MALAYSIAN PHONE
    # =====================================================

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

        return redirect(
            url_for(
                "superadmin.review_registration",
                user_id=user.id,
            )
        )


    # =====================================================
    # EXTRA WHITELIST PROTECTION
    # =====================================================

    if (
        job_title
        and
        job_title
        not in VALID_JOB_TITLES
    ):

        flash(
            (
                "Please select a valid "
                "Job Title."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.review_registration",
                user_id=user.id,
            )
        )


    if (
        department
        and
        department
        not in VALID_DEPARTMENTS
    ):

        flash(
            (
                "Please select a valid "
                "Department."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.review_registration",
                user_id=user.id,
            )
        )


    if (
        shift
        and
        shift
        not in VALID_SHIFTS
    ):

        flash(
            (
                "Please select a valid Shift."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.review_registration",
                user_id=user.id,
            )
        )


    if (
        role
        not in VALID_ROLES
    ):

        flash(
            (
                "Please select a valid "
                "Access Role."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.review_registration",
                user_id=user.id,
            )
        )


    # =====================================================
    # UNIQUE FIELDS
    # =====================================================

    uniqueness_error = (
        _validate_unique_fields(
            user=user,

            username=username,

            email=email,

            phone_number=(
                phone_number
            ),

            employee_id=(
                employee_id
            ),
        )
    )


    if uniqueness_error:

        flash(
            uniqueness_error,
            "error",
        )

        return redirect(
            url_for(
                "superadmin.review_registration",
                user_id=user.id,
            )
        )


    # =====================================================
    # DETECT EMAIL / PHONE CHANGES
    # =====================================================

    email_changed = (
        email
        != user.email
    )


    phone_changed = (
        phone_number
        != user.phone_number
    )


    # =====================================================
    # UPDATE USER
    # =====================================================

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

    user.job_title = (
        job_title
    )

    user.department = (
        department
    )

    user.shift = (
        shift
    )

    user.role = (
        role
    )


    email_code = None
    phone_code = None


    # =====================================================
    # EMAIL CHANGED
    # =====================================================

    if email_changed:

        user.email_verified_at = None

        try:

            email_code = (
                issue_verification_code(
                    user=user,
                    is_resend=False,
                )
            )

        except Exception:

            current_app.logger.exception(
                (
                    "Unable to generate a new "
                    "email verification OTP "
                    "after SuperAdmin changed "
                    "the applicant email."
                )
            )

            db.session.rollback()

            flash(
                (
                    "The new email address "
                    "could not be prepared "
                    "for verification."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "superadmin.review_registration",
                    user_id=user.id,
                )
            )


    # =====================================================
    # PHONE CHANGED
    # =====================================================

    if phone_changed:

        user.phone_verified_at = None

        try:

            phone_code = (
                issue_phone_verification_code(
                    user=user,
                    is_resend=False,
                )
            )

        except Exception:

            current_app.logger.exception(
                (
                    "Unable to generate a new "
                    "phone verification OTP "
                    "after SuperAdmin changed "
                    "the applicant phone number."
                )
            )

            db.session.rollback()

            flash(
                (
                    "The new phone number "
                    "could not be prepared "
                    "for verification."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "superadmin.review_registration",
                    user_id=user.id,
                )
            )


    # =====================================================
    # SAVE DATABASE
    # =====================================================

    try:

        db.session.commit()

    except IntegrityError:

        db.session.rollback()

        flash(
            (
                "One of the account values "
                "is already being used by "
                "another account."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.review_registration",
                user_id=user.id,
            )
        )


    except SQLAlchemyError:

        db.session.rollback()

        current_app.logger.exception(
            (
                "Unable to save SuperAdmin "
                "registration changes."
            )
        )

        flash(
            (
                "The registration changes "
                "could not be saved."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.review_registration",
                user_id=user.id,
            )
        )


    # =====================================================
    # SEND NEW EMAIL OTP
    # =====================================================

    if (
        email_changed
        and
        email_code
    ):

        try:

            send_email_verification_code_email(
                user=user,
                code=email_code,
            )

        except Exception:

            current_app.logger.exception(
                (
                    "Applicant email was changed, "
                    "but the new verification "
                    "email could not be sent."
                )
            )

            flash(
                (
                    "Changes were saved, but "
                    "the new email verification "
                    "code could not be sent."
                ),
                "warning",
            )


    # =====================================================
    # SEND NEW PHONE OTP
    # =====================================================

    if (
        phone_changed
        and
        phone_code
    ):

        try:

            send_phone_verification_code_sms(
                user=user,
                code=phone_code,
            )

        except Exception:

            current_app.logger.exception(
                (
                    "Applicant phone was changed, "
                    "but the new verification "
                    "code could not be delivered."
                )
            )

            flash(
                (
                    "Changes were saved, but "
                    "the new phone verification "
                    "code could not be delivered."
                ),
                "warning",
            )


    # =====================================================
    # SUCCESS MESSAGE
    # =====================================================

    if (
        email_changed
        or
        phone_changed
    ):

        flash(
            (
                "Changes saved. "
                "Because the email or phone "
                "number was changed, the applicant "
                "must complete verification again "
                "before approval."
            ),
            "warning",
        )

    else:

        flash(
            (
                "Registration changes saved "
                "successfully."
            ),
            "success",
        )


    return redirect(
        url_for(
            "superadmin.review_registration",
            user_id=user.id,
        )
    )


# =========================================================
# APPROVE REGISTRATION
# =========================================================

@superadmin_bp.route(
    "/registrations/<int:user_id>/approve",
    methods=["POST"],
)
@superadmin_required
def approve_registration(
    user_id,
):
    """
    Approve a pending registration.

    Approval requires:

    - Email verified
    - Phone verified
    - Valid Job Title
    - Valid Department
    - Valid Shift
    - Valid Access Role
    """

    user = (
        _get_pending_user_or_404(
            user_id
        )
    )


    form = (
        ApproveRegistrationForm()
    )


    if not form.validate_on_submit():

        flash(
            (
                "The approval request "
                "could not be validated."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.review_registration",
                user_id=user.id,
            )
        )


    # =====================================================
    # EMAIL VERIFICATION
    # =====================================================

    if (
        user.email_verified_at
        is None
    ):

        flash(
            (
                "This applicant must verify "
                "their email address before "
                "the account can be approved."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.review_registration",
                user_id=user.id,
            )
        )


    # =====================================================
    # PHONE VERIFICATION
    # =====================================================

    if (
        user.phone_verified_at
        is None
    ):

        flash(
            (
                "This applicant must verify "
                "their phone number before "
                "the account can be approved."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.review_registration",
                user_id=user.id,
            )
        )


    # =====================================================
    # EMPLOYMENT INFORMATION
    # =====================================================

    missing_fields = (
        _employment_fields_complete(
            user
        )
    )


    if missing_fields:

        flash(
            (
                "Please complete the following "
                "employment information before "
                "approving this registration: "
                + ", ".join(
                    missing_fields
                )
                + "."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.review_registration",
                user_id=user.id,
            )
        )


    # =====================================================
    # ROLE
    # =====================================================

    if (
        user.role
        not in VALID_ROLES
    ):

        flash(
            (
                "Please assign a valid "
                "Access Role before approval."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.review_registration",
                user_id=user.id,
            )
        )


    # =====================================================
    # APPROVE
    # =====================================================

    now = datetime.now(
        timezone.utc
    )


    user.status = (
        UserStatus.ACTIVE.value
    )

    user.approved_at = (
        now
    )

    user.approved_by = (
        current_user.id
    )

    user.rejected_at = None
    user.rejected_by = None
    user.rejection_reason = None


    try:

        db.session.commit()

    except SQLAlchemyError:

        db.session.rollback()

        current_app.logger.exception(
            (
                "Unable to approve "
                "registration."
            )
        )

        flash(
            (
                "The registration could "
                "not be approved."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.review_registration",
                user_id=user.id,
            )
        )


    # =====================================================
    # APPROVAL EMAIL
    # =====================================================

    try:

        send_registration_approved_email(
            user=user
        )

    except Exception:

        current_app.logger.exception(
            (
                "Registration was approved, "
                "but approval email could "
                "not be sent."
            )
        )


    flash(
        (
            f"{user.full_name} has been "
            "approved successfully."
        ),
        "success",
    )


    return redirect(
        url_for(
            "superadmin.pending_registrations"
        )
    )


# =========================================================
# REJECT REGISTRATION
# =========================================================

@superadmin_bp.route(
    "/registrations/<int:user_id>/reject",
    methods=["POST"],
)
@superadmin_required
def reject_registration(
    user_id,
):
    """
    Reject a pending registration.

    A rejection reason is required.
    """

    user = (
        _get_pending_user_or_404(
            user_id
        )
    )


    form = (
        RejectRegistrationForm()
    )


    if not form.validate_on_submit():

        for field_errors in (
            form.errors.values()
        ):

            for error in field_errors:

                flash(
                    error,
                    "error",
                )

        return redirect(
            url_for(
                "superadmin.review_registration",
                user_id=user.id,
            )
        )


    reason = (
        form.reason.data
        .strip()
    )


    now = datetime.now(
        timezone.utc
    )


    user.status = (
        UserStatus.REJECTED.value
    )

    user.rejected_at = (
        now
    )

    user.rejected_by = (
        current_user.id
    )

    user.rejection_reason = (
        reason
    )


    user.approved_at = None
    user.approved_by = None


    try:

        db.session.commit()

    except SQLAlchemyError:

        db.session.rollback()

        current_app.logger.exception(
            (
                "Unable to reject "
                "registration."
            )
        )

        flash(
            (
                "The registration could "
                "not be rejected."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.review_registration",
                user_id=user.id,
            )
        )


    # =====================================================
    # REJECTION EMAIL
    # =====================================================

    try:

        send_registration_rejected_email(
            user=user,
            reason=reason,
        )

    except Exception:

        current_app.logger.exception(
            (
                "Registration was rejected, "
                "but rejection email could "
                "not be sent."
            )
        )


    flash(
        (
            f"{user.full_name}'s registration "
            "has been rejected."
        ),
        "success",
    )


    return redirect(
        url_for(
            "superadmin.pending_registrations"
        )
    )