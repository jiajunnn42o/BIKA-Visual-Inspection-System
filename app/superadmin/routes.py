from datetime import datetime, timezone
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

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db

from app.models import (
    User,
    UserRole,
    UserStatus,
)

from app.services.email_service import (
    send_registration_approved_email,
    send_registration_rejected_email,
    send_registration_updated_email,
)

from app.superadmin import superadmin_bp

from app.superadmin.forms import (
    RegistrationReviewForm,
)


# =========================================================
# SUPERADMIN ACCESS CONTROL
# =========================================================

def superadmin_required(view_function):
    """
    Allow only authenticated SuperAdmin users
    to access the protected route.
    """

    @wraps(view_function)
    @login_required
    def wrapped_view(*args, **kwargs):

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
# REGISTRATION DATA HELPERS
# =========================================================

def get_registration_snapshot(user):
    """
    Capture registration information before
    SuperAdmin makes any changes.

    This information is used to determine
    exactly which fields were changed.
    """

    return {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
        "email": user.email,
        "phone_number": user.phone_number,
        "job_title": user.job_title,
        "department": user.department,
        "shift": user.shift,
        "employee_id": user.employee_id,
        "role": user.role,
    }


def get_changed_fields(before, after):
    """
    Compare original registration information
    with the updated information.

    Returns only fields that were actually changed.
    """

    changes = {}

    for field_name, old_value in before.items():

        new_value = after.get(
            field_name
        )

        if old_value != new_value:

            changes[field_name] = {
                "old": old_value,
                "new": new_value,
            }

    return changes


def check_unique_conflict(
    user_id,
    field_name,
    value,
):
    """
    Check whether another user already owns
    a value that must remain unique.

    Unique fields currently include:
    - username
    - email
    - phone number
    - employee ID
    """

    column = getattr(
        User,
        field_name,
    )

    return db.session.scalar(
        db.select(User).where(
            column == value,
            User.id != user_id,
        )
    )


# =========================================================
# PENDING REGISTRATIONS LIST
# =========================================================

@superadmin_bp.route(
    "/registrations"
)
@superadmin_required
def pending_registrations():
    """
    Display all registration applications
    waiting for SuperAdmin approval.
    """

    users = db.session.scalars(
        db.select(User)
        .where(
            User.status
            == UserStatus.PENDING.value
        )
        .order_by(
            User.created_at.asc()
        )
    ).all()

    return render_template(
        "superadmin/pending_registrations.html",
        users=users,
    )


# =========================================================
# REVIEW REGISTRATION
# =========================================================

@superadmin_bp.route(
    "/registrations/<int:user_id>",
    methods=["GET", "POST"],
)
@superadmin_required
def review_registration(user_id):
    """
    Allow SuperAdmin to:

    - Review registration
    - Modify submitted information
    - Assign role
    - Save changes
    - Approve registration
    - Reject registration
    """

    user = db.get_or_404(
        User,
        user_id,
    )

    # -----------------------------------------------------
    # Only pending applications can be reviewed here.
    # -----------------------------------------------------

    if (
        user.status
        != UserStatus.PENDING.value
    ):

        flash(
            "This registration is no longer pending.",
            "warning",
        )

        return redirect(
            url_for(
                "superadmin.pending_registrations"
            )
        )

    # Populate form using current database values.
    form = RegistrationReviewForm(
        obj=user
    )

    # -----------------------------------------------------
    # PROCESS FORM
    # -----------------------------------------------------

    if form.validate_on_submit():

        # =================================================
        # NORMALIZE FORM VALUES
        # =================================================

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

        phone_number = (
            form.phone_number.data
            .strip()
        )

        job_title = (
            form.job_title.data
            .strip()
        )

        department = (
            form.department.data
            .strip()
        )

        shift = (
            form.shift.data
            .strip()
        )

        employee_id = (
            form.employee_id.data
            .strip()
            .upper()
        )

        role = (
            form.role.data
        )

        # =================================================
        # UNIQUE FIELD VALIDATION
        # =================================================

        unique_fields = {
            "username": username,
            "email": email,
            "phone_number": phone_number,
            "employee_id": employee_id,
        }

        has_conflict = False

        for field_name, value in unique_fields.items():

            conflicting_user = (
                check_unique_conflict(
                    user.id,
                    field_name,
                    value,
                )
            )

            if conflicting_user:

                readable_field_name = (
                    field_name
                    .replace("_", " ")
                    .title()
                )

                flash(
                    (
                        f"{readable_field_name} "
                        "is already being used "
                        "by another account."
                    ),
                    "error",
                )

                has_conflict = True

        if has_conflict:

            return render_template(
                "superadmin/review_registration.html",
                user=user,
                form=form,
            )

        # =================================================
        # CAPTURE ORIGINAL DATA
        # =================================================

        original_data = (
            get_registration_snapshot(
                user
            )
        )

        # Keep original email separately.
        #
        # If SuperAdmin changes the user's email,
        # both old and new addresses can be notified.
        original_email = user.email

        # =================================================
        # APPLY SUPERADMIN CHANGES
        # =================================================

        user.first_name = first_name
        user.last_name = last_name

        user.username = username
        user.email = email
        user.phone_number = phone_number

        user.job_title = job_title
        user.department = department
        user.shift = shift
        user.employee_id = employee_id

        user.role = role

        # Capture information after changes.
        updated_data = (
            get_registration_snapshot(
                user
            )
        )

        changes = (
            get_changed_fields(
                original_data,
                updated_data,
            )
        )

        # =================================================
        # SAVE CHANGES ONLY
        # =================================================

        if form.save_changes.data:

            try:
                db.session.commit()

            except SQLAlchemyError:

                db.session.rollback()

                current_app.logger.exception(
                    (
                        "Database error while updating "
                        "registration information."
                    )
                )

                flash(
                    (
                        "The registration information "
                        "could not be saved."
                    ),
                    "error",
                )

                return render_template(
                    "superadmin/review_registration.html",
                    user=user,
                    form=form,
                )

            # ---------------------------------------------
            # SEND MODIFICATION EMAIL
            # ---------------------------------------------

            if changes:

                try:

                    send_registration_updated_email(
                        user=user,
                        changes=changes,
                        original_email=original_email,
                    )

                except Exception:

                    current_app.logger.exception(
                        (
                            "Unable to send registration "
                            "update email."
                        )
                    )

                    flash(
                        (
                            "The registration information "
                            "was saved, but the notification "
                            "email could not be sent."
                        ),
                        "warning",
                    )

                else:

                    flash(
                        (
                            "Registration information "
                            "was updated and the user "
                            "was notified by email."
                        ),
                        "success",
                    )

            else:

                flash(
                    (
                        "No registration information "
                        "was changed."
                    ),
                    "info",
                )

            return redirect(
                url_for(
                    "superadmin.review_registration",
                    user_id=user.id,
                )
            )

        # =================================================
        # APPROVE REGISTRATION
        # =================================================

        if form.approve.data:

            user.status = (
                UserStatus.ACTIVE.value
            )

            user.approved_at = (
                datetime.now(
                    timezone.utc
                )
            )

            user.approved_by_id = (
                current_user.id
            )

            # Remove any previous rejection information.
            user.rejected_at = None
            user.rejected_by_id = None
            user.rejection_reason = None

            # Ensure the newly-approved user is not
            # carrying failed login state.
            user.failed_login_attempts = 0
            user.locked_at = None

            try:

                db.session.commit()

            except SQLAlchemyError:

                db.session.rollback()

                current_app.logger.exception(
                    (
                        "Database error while approving "
                        "registration."
                    )
                )

                flash(
                    (
                        "The registration could not "
                        "be approved."
                    ),
                    "error",
                )

                return render_template(
                    "superadmin/review_registration.html",
                    user=user,
                    form=form,
                )

            # ---------------------------------------------
            # SEND APPROVAL EMAIL
            # ---------------------------------------------

            email_sent = True

            try:

                send_registration_approved_email(
                    user=user,
                    changes=changes,
                    original_email=original_email,
                )

            except Exception:

                email_sent = False

                current_app.logger.exception(
                    (
                        "Unable to send registration "
                        "approval email."
                    )
                )

            if email_sent:

                flash(
                    (
                        f"{user.full_name}'s registration "
                        "has been approved and an email "
                        "notification was sent."
                    ),
                    "success",
                )

            else:

                flash(
                    (
                        f"{user.full_name}'s registration "
                        "has been approved, but the "
                        "notification email could not "
                        "be sent."
                    ),
                    "warning",
                )

            return redirect(
                url_for(
                    "superadmin.pending_registrations"
                )
            )

        # =================================================
        # REJECT REGISTRATION
        # =================================================

        if form.reject.data:

            rejection_reason = (
                form.rejection_reason.data
                or ""
            ).strip()

            # Rejection reason is mandatory.
            if not rejection_reason:

                flash(
                    (
                        "A rejection reason is required "
                        "before rejecting the registration."
                    ),
                    "error",
                )

                return render_template(
                    "superadmin/review_registration.html",
                    user=user,
                    form=form,
                )

            user.status = (
                UserStatus.REJECTED.value
            )

            user.rejected_at = (
                datetime.now(
                    timezone.utc
                )
            )

            user.rejected_by_id = (
                current_user.id
            )

            user.rejection_reason = (
                rejection_reason
            )

            # Remove any approval information.
            user.approved_at = None
            user.approved_by_id = None

            try:

                db.session.commit()

            except SQLAlchemyError:

                db.session.rollback()

                current_app.logger.exception(
                    (
                        "Database error while rejecting "
                        "registration."
                    )
                )

                flash(
                    (
                        "The registration could not "
                        "be rejected."
                    ),
                    "error",
                )

                return render_template(
                    "superadmin/review_registration.html",
                    user=user,
                    form=form,
                )

            # ---------------------------------------------
            # SEND REJECTION EMAIL
            # ---------------------------------------------

            email_sent = True

            try:

                send_registration_rejected_email(
                    user=user,
                    rejection_reason=rejection_reason,
                    changes=changes,
                    original_email=original_email,
                )

            except Exception:

                email_sent = False

                current_app.logger.exception(
                    (
                        "Unable to send registration "
                        "rejection email."
                    )
                )

            if email_sent:

                flash(
                    (
                        f"{user.full_name}'s registration "
                        "has been rejected and an email "
                        "notification was sent."
                    ),
                    "success",
                )

            else:

                flash(
                    (
                        f"{user.full_name}'s registration "
                        "has been rejected, but the "
                        "notification email could not "
                        "be sent."
                    ),
                    "warning",
                )

            return redirect(
                url_for(
                    "superadmin.pending_registrations"
                )
            )

    # =====================================================
    # GET REQUEST / FORM VALIDATION FAILED
    # =====================================================

    return render_template(
        "superadmin/review_registration.html",
        user=user,
        form=form,
    )