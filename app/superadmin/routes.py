from datetime import (
    datetime,
    timezone,
)

from functools import wraps


from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from flask_login import (
    current_user,
    login_required,
)

from sqlalchemy import (
    func,
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
    send_registration_approved_email,
    send_registration_rejected_email,
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


VALID_LIST_STATUSES = {
    "pending",
    "approved",
    "rejected",
}


# =========================================================
# SUPERADMIN PERMISSION
# =========================================================

def superadmin_required(view_function):

    @wraps(view_function)
    @login_required
    def wrapped_view(
        *args,
        **kwargs,
    ):

        if (
            current_user.role
            != UserRole.SUPERADMIN.value
        ):
            abort(403)

        return view_function(
            *args,
            **kwargs,
        )

    return wrapped_view


# =========================================================
# HELPERS
# =========================================================

def _get_user_or_404(
    user_id,
):

    user = db.session.get(
        User,
        user_id,
    )

    if user is None:
        abort(404)

    return user


def _get_pending_user_or_404(
    user_id,
):

    user = _get_user_or_404(
        user_id
    )

    if (
        user.status
        != UserStatus.PENDING.value
    ):
        abort(404)

    return user


def _get_registration_user_or_404(
    user_id,
):
    """
    Registration workflow users only.

    Allowed:
    - pending
    - approved through registration workflow
    - rejected
    """

    user = _get_user_or_404(
        user_id
    )


    if (
        user.status
        == UserStatus.PENDING.value
    ):
        return user


    if (
        user.status
        == UserStatus.REJECTED.value
    ):
        return user


    if (
        user.status
        == UserStatus.ACTIVE.value
        and
        user.approved_at
        is not None
    ):
        return user


    abort(404)


def _registration_view_status(
    user,
):

    if (
        user.status
        == UserStatus.PENDING.value
    ):
        return "pending"


    if (
        user.status
        == UserStatus.REJECTED.value
    ):
        return "rejected"


    if (
        user.status
        == UserStatus.ACTIVE.value
        and
        user.approved_at
        is not None
    ):
        return "approved"


    return None


def _user_exists(
    field,
    value,
    exclude_user_id,
):

    if not value:
        return False


    existing_id = db.session.scalar(
        db.select(
            User.id
        )
        .where(
            field == value,
            User.id != exclude_user_id,
        )
        .limit(1)
    )


    return (
        existing_id
        is not None
    )


def _prepare_review_form(
    user,
):

    form = ReviewRegistrationForm(
        obj=user
    )


    if (
        user.role
        in VALID_ROLES
    ):
        form.role.data = user.role

    else:
        form.role.data = (
            UserRole.USER.value
        )


    if (
        user.job_title
        in VALID_JOB_TITLES
    ):
        form.job_title.data = (
            user.job_title
        )

    else:
        form.job_title.data = ""


    if (
        user.department
        in VALID_DEPARTMENTS
    ):
        form.department.data = (
            user.department
        )

    else:
        form.department.data = ""


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


def _return_to_review(
    user_id,
    *,
    saved=False,
):
    """
    Return to registration review.

    When Save Changes succeeds:
    ?saved=1 is added so the frontend can
    display a success toast.
    """

    if (
        request.form.get("_modal")
        == "1"
    ):

        params = {
            "status": "pending",
            "review": user_id,
        }

        if saved:
            params["saved"] = "1"

        return redirect(
            url_for(
                "superadmin.pending_registrations",
                **params,
            )
        )


    params = {
        "user_id": user_id,
    }

    if saved:
        params["saved"] = "1"


    return redirect(
        url_for(
            "superadmin.review_registration",
            **params,
        )
    )


# =========================================================
# REGISTRATION REQUEST LIST
# =========================================================

@superadmin_bp.route(
    "/registrations"
)
@superadmin_required
def pending_registrations():

    current_status = (
        request.args.get(
            "status",
            "pending",
        )
        .strip()
        .lower()
    )


    if (
        current_status
        not in VALID_LIST_STATUSES
    ):
        current_status = "pending"


    # =====================================================
    # PENDING
    # =====================================================

    if (
        current_status
        == "pending"
    ):

        registration_users = (
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


    # =====================================================
    # APPROVED
    # =====================================================

    elif (
        current_status
        == "approved"
    ):

        registration_users = (
            db.session.scalars(
                db.select(
                    User
                )
                .where(
                    User.status
                    == UserStatus.ACTIVE.value,

                    User.approved_at
                    .is_not(None),
                )
                .order_by(
                    User.approved_at.desc(),
                    User.created_at.desc(),
                )
            )
            .all()
        )


    # =====================================================
    # REJECTED
    # =====================================================

    else:

        registration_users = (
            db.session.scalars(
                db.select(
                    User
                )
                .where(
                    User.status
                    == UserStatus.REJECTED.value
                )
                .order_by(
                    User.rejected_at.desc(),
                    User.created_at.desc(),
                )
            )
            .all()
        )


    # =====================================================
    # COUNTS
    # =====================================================

    pending_count = (
        db.session.scalar(
            db.select(
                func.count(
                    User.id
                )
            )
            .where(
                User.status
                == UserStatus.PENDING.value,

                User.email_verified_at
                .is_not(None),

                User.phone_verified_at
                .is_not(None),
            )
        )
        or 0
    )


    approved_count = (
        db.session.scalar(
            db.select(
                func.count(
                    User.id
                )
            )
            .where(
                User.status
                == UserStatus.ACTIVE.value,

                User.approved_at
                .is_not(None),
            )
        )
        or 0
    )


    rejected_count = (
        db.session.scalar(
            db.select(
                func.count(
                    User.id
                )
            )
            .where(
                User.status
                == UserStatus.REJECTED.value
            )
        )
        or 0
    )


    return render_template(
        "superadmin/pending_registrations.html",

        # Keep this name for compatibility
        # with the existing template.
        pending_users=registration_users,

        current_status=current_status,

        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
    )

# =========================================================
# CHECK UNIQUE REGISTRATION VALUE
# =========================================================

@superadmin_bp.route(
    "/registrations/<int:user_id>/check-unique"
)
@superadmin_required
def check_registration_unique(
    user_id,
):
    """
    Real-time availability check for:

    - username
    - employee_id

    The applicant's own existing value does not
    count as a collision.
    """

    user = (
        _get_pending_user_or_404(
            user_id
        )
    )


    field_name = (
        request.args.get(
            "field",
            "",
        )
        .strip()
        .lower()
    )


    raw_value = (
        request.args.get(
            "value",
            "",
        )
        .strip()
    )


    # =====================================================
    # VALID FIELD
    # =====================================================

    if (
        field_name
        not in {
            "username",
            "employee_id",
        }
    ):

        return jsonify(
            {
                "ok": False,
                "available": False,
                "message": "Unsupported field.",
            }
        ), 400


    # =====================================================
    # EMPTY
    # =====================================================

    if not raw_value:

        return jsonify(
            {
                "ok": True,
                "available": False,
                "message": "Required",
            }
        )


    # =====================================================
    # USERNAME
    # =====================================================

    if (
        field_name
        == "username"
    ):

        normalized_value = (
            raw_value.lower()
        )


        existing_user_id = (
            db.session.scalar(
                db.select(
                    User.id
                )
                .where(
                    db.func.lower(
                        User.username
                    )
                    ==
                    normalized_value,

                    User.id
                    !=
                    user.id,
                )
                .limit(1)
            )
        )


    # =====================================================
    # EMPLOYEE ID
    # =====================================================

    else:

        normalized_value = (
            raw_value.upper()
        )


        existing_user_id = (
            db.session.scalar(
                db.select(
                    User.id
                )
                .where(
                    db.func.upper(
                        User.employee_id
                    )
                    ==
                    normalized_value,

                    User.id
                    !=
                    user.id,
                )
                .limit(1)
            )
        )


    # =====================================================
    # COLLISION
    # =====================================================

    if (
        existing_user_id
        is not None
    ):

        return jsonify(
            {
                "ok": True,
                "available": False,
                "message": "Already in use",
            }
        )


    # =====================================================
    # AVAILABLE
    # =====================================================

    return jsonify(
        {
            "ok": True,
            "available": True,
            "message": "Available",
        }
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

    user = (
        _get_registration_user_or_404(
            user_id
        )
    )


    review_status = (
        _registration_view_status(
            user
        )
    )


    if review_status is None:
        abort(404)


    is_read_only = (
        review_status
        != "pending"
    )


    # Pending still needs editable forms.
    form = None
    approve_form = None
    reject_form = None


    if not is_read_only:

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


    # AJAX / modal request
    is_modal_request = (
        request.args.get("modal")
        == "1"
        or
        request.headers.get(
            "X-Requested-With"
        )
        == "XMLHttpRequest"
    )


    template_name = (
        "superadmin/_review_registration_modal.html"
        if is_modal_request
        else
        "superadmin/review_registration.html"
    )


    return render_template(
        template_name,

        user=user,

        form=form,

        approve_form=approve_form,

        reject_form=reject_form,

        review_status=review_status,

        is_read_only=is_read_only,

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


        return _return_to_review(
            user.id
        )


    # =====================================================
    # NORMALIZE
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


    employee_id = (
        form.employee_id.data
        .strip()
        .upper()
    )


    job_title = (
        form.job_title.data.strip()
        if form.job_title.data
        else None
    )


    department = (
        form.department.data.strip()
        if form.department.data
        else None
    )


    shift = (
        form.shift.data.strip()
        if form.shift.data
        else None
    )


    role = (
        form.role.data
        .strip()
        .lower()
    )


    # =====================================================
    # EMAIL + PHONE LOCKED
    # =====================================================

    email = user.email

    phone_number = (
        user.phone_number
    )


    # =====================================================
    # VALIDATION
    # =====================================================

    if (
        job_title
        and
        job_title
        not in VALID_JOB_TITLES
    ):

        flash(
            "Please select a valid Job Title.",
            "error",
        )

        return _return_to_review(
            user.id
        )


    if (
        department
        and
        department
        not in VALID_DEPARTMENTS
    ):

        flash(
            "Please select a valid Department.",
            "error",
        )

        return _return_to_review(
            user.id
        )


    if (
        shift
        and
        shift
        not in VALID_SHIFTS
    ):

        flash(
            "Please select a valid Shift.",
            "error",
        )

        return _return_to_review(
            user.id
        )


    if (
        role
        not in VALID_ROLES
    ):

        flash(
            "Please select a valid Access Role.",
            "error",
        )

        return _return_to_review(
            user.id
        )


    uniqueness_error = (
        _validate_unique_fields(
            user=user,
            username=username,
            email=email,
            phone_number=phone_number,
            employee_id=employee_id,
        )
    )


    if uniqueness_error:

        flash(
            uniqueness_error,
            "error",
        )

        return _return_to_review(
            user.id
        )


    # =====================================================
    # UPDATE
    # =====================================================

    user.first_name = first_name
    user.last_name = last_name

    user.username = username
    user.employee_id = employee_id

    user.job_title = job_title
    user.department = department
    user.shift = shift

    user.role = role


    # =====================================================
    # COMMIT
    # =====================================================

    try:

        db.session.commit()


    except IntegrityError:

        db.session.rollback()

        flash(
            (
                "One of the account values is "
                "already being used by another account."
            ),
            "error",
        )

        return _return_to_review(
            user.id
        )


    except SQLAlchemyError:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to save registration changes."
        )

        flash(
            (
                "The registration changes "
                "could not be saved."
            ),
            "error",
        )

        return _return_to_review(
            user.id
        )


    flash(
        "Registration changes saved successfully.",
        "success",
    )


    return _return_to_review(
        user.id
    )


# =========================================================
# APPROVE
# =========================================================

@superadmin_bp.route(
    "/registrations/<int:user_id>/approve",
    methods=["POST"],
)
@superadmin_required
def approve_registration(
    user_id,
):

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

        return _return_to_review(
            user.id
        )


    if (
        user.email_verified_at
        is None
    ):

        flash(
            (
                "This applicant must verify "
                "their email address first."
            ),
            "error",
        )

        return _return_to_review(
            user.id
        )


    if (
        user.phone_verified_at
        is None
    ):

        flash(
            (
                "This applicant must verify "
                "their phone number first."
            ),
            "error",
        )

        return _return_to_review(
            user.id
        )


    missing_fields = (
        _employment_fields_complete(
            user
        )
    )


    if missing_fields:

        flash(
            (
                "Please complete: "
                +
                ", ".join(
                    missing_fields
                )
                +
                "."
            ),
            "error",
        )

        return _return_to_review(
            user.id
        )


    if (
        user.role
        not in VALID_ROLES
    ):

        flash(
            (
                "Please assign a valid "
                "Access Role."
            ),
            "error",
        )

        return _return_to_review(
            user.id
        )


    now = datetime.now(
        timezone.utc
    )


    user.status = (
        UserStatus.ACTIVE.value
    )

    user.approved_at = now

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
            "Unable to approve registration."
        )

        flash(
            (
                "The registration could "
                "not be approved."
            ),
            "error",
        )

        return _return_to_review(
            user.id
        )


    try:

        send_registration_approved_email(
            user=user
        )

    except Exception:

        current_app.logger.exception(
            (
                "Registration approved but "
                "approval email failed."
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
            "superadmin.pending_registrations",
            status="approved",
        )
    )


# =========================================================
# REJECT
# =========================================================

@superadmin_bp.route(
    "/registrations/<int:user_id>/reject",
    methods=["POST"],
)
@superadmin_required
def reject_registration(
    user_id,
):

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


        return _return_to_review(
            user.id
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

    user.rejected_at = now

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
            "Unable to reject registration."
        )

        flash(
            (
                "The registration could "
                "not be rejected."
            ),
            "error",
        )

        return _return_to_review(
            user.id
        )


    try:

        send_registration_rejected_email(
            user=user,
            rejection_reason=reason,
        )

    except Exception:

        current_app.logger.exception(
            (
                "Registration rejected but "
                "rejection email failed."
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
            "superadmin.pending_registrations",
            status="rejected",
        )
    )