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
    send_email_verification_code_email,
    send_registration_approved_email,
    send_registration_rejected_email,
    send_registration_updated_email,
)

from app.services.email_verification_service import (
    issue_verification_code,
)

from app.superadmin import superadmin_bp

from app.superadmin.forms import (
    RegistrationReviewForm,
)

from app.utils.phone import (
    InvalidPhoneNumberError,
    normalize_malaysian_mobile,
)

# =========================================================
# SUPERADMIN ACCESS CONTROL
# =========================================================

def superadmin_required(view_function):
    """
    Only authenticated SuperAdmin users
    are allowed to access the protected route.
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
    Save the current editable registration data.

    This is used to detect which fields were
    changed by the SuperAdmin.
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
    Compare old and new registration data.

    Only changed fields are returned.
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
    Check whether another user already uses
    a value that must remain unique.

    Unique fields:
    - Username
    - Email
    - Phone number
    - Employee ID
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
# NEW EMAIL VERIFICATION
# =========================================================

def prepare_new_email_verification(user):
    """
    Prepare verification after a SuperAdmin
    changes the applicant's email address.

    The old email verification becomes invalid.

    A new 6-digit verification code is created.

    No verification URL is sent by email.
    """

    # The new email address must be verified again.
    user.email_verified_at = None

    verification_code = (
        issue_verification_code(
            user=user,
            is_resend=False,
        )
    )

    return verification_code


# =========================================================
# PENDING REGISTRATION LIST
# =========================================================

@superadmin_bp.route(
    "/registrations"
)
@superadmin_required
def pending_registrations():
    """
    Display registration applications that:

    1. Are still pending.
    2. Have already verified their email.
    """

    users = (
        db.session.scalars(
            db.select(User)
            .where(
                User.status
                == UserStatus.PENDING.value,

                User.email_verified_at
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
    Review a pending registration.

    SuperAdmin can:

    - Review submitted information.
    - Correct registration information.
    - Assign a role.
    - Save changes.
    - Approve registration.
    - Reject registration.
    """

    user = db.get_or_404(
        User,
        user_id,
    )

    # -----------------------------------------------------
    # REGISTRATION MUST STILL BE PENDING
    # -----------------------------------------------------

    if (
        user.status
        != UserStatus.PENDING.value
    ):

        flash(
            (
                "This registration is "
                "no longer pending."
            ),
            "warning",
        )

        return redirect(
            url_for(
                "superadmin.pending_registrations"
            )
        )

    # -----------------------------------------------------
    # EMAIL MUST ALREADY BE VERIFIED
    # -----------------------------------------------------

    if (
        user.email_verified_at
        is None
    ):

        flash(
            (
                "This applicant's email address "
                "has not been verified."
            ),
            "warning",
        )

        return redirect(
            url_for(
                "superadmin.pending_registrations"
            )
        )

    # Load existing user data into the form.
    form = RegistrationReviewForm(
        obj=user
    )

    # =====================================================
    # PROCESS FORM
    # =====================================================

    if form.validate_on_submit():

        # -------------------------------------------------
        # NORMALIZE FORM VALUES
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
                "superadmin/review_registration.html",
                user=user,
                form=form,
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

        # -------------------------------------------------
        # CHECK UNIQUE FIELDS
        # -------------------------------------------------

        unique_fields = {
            "username": username,
            "email": email,
            "phone_number": phone_number,
            "employee_id": employee_id,
        }

        has_conflict = False

        for (
            field_name,
            value,
        ) in unique_fields.items():

            conflicting_user = (
                check_unique_conflict(
                    user.id,
                    field_name,
                    value,
                )
            )

            if conflicting_user:

                readable_name = (
                    field_name
                    .replace(
                        "_",
                        " ",
                    )
                    .title()
                )

                flash(
                    (
                        f"{readable_name} "
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

        # -------------------------------------------------
        # SAVE ORIGINAL INFORMATION
        # -------------------------------------------------

        original_data = (
            get_registration_snapshot(
                user
            )
        )

        original_email = (
            user.email
        )

        # -------------------------------------------------
        # APPLY SUPERADMIN CHANGES
        # -------------------------------------------------

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

        user.job_title = (
            job_title
        )

        user.department = (
            department
        )

        user.shift = (
            shift
        )

        user.employee_id = (
            employee_id
        )

        user.role = (
            role
        )

        # -------------------------------------------------
        # DETECT CHANGED FIELDS
        # -------------------------------------------------

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

        email_changed = (
            original_email
            != user.email
        )

        # =================================================
        # SAVE CHANGES ONLY
        # =================================================

        if form.save_changes.data:

            verification_code = None

            # ---------------------------------------------
            # EMAIL WAS CHANGED
            # ---------------------------------------------

            if email_changed:

                try:

                    verification_code = (
                        prepare_new_email_verification(
                            user
                        )
                    )

                except Exception:

                    db.session.rollback()

                    current_app.logger.exception(
                        (
                            "Unable to prepare "
                            "new email verification."
                        )
                    )

                    flash(
                        (
                            "The new email address "
                            "could not be prepared "
                            "for verification."
                        ),
                        "error",
                    )

                    return render_template(
                        "superadmin/review_registration.html",
                        user=user,
                        form=form,
                    )

            # ---------------------------------------------
            # SAVE DATABASE CHANGES
            # ---------------------------------------------

            try:

                db.session.commit()

            except SQLAlchemyError:

                db.session.rollback()

                current_app.logger.exception(
                    (
                        "Database error while "
                        "updating registration."
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
            # SEND CHANGE SUMMARY
            # ---------------------------------------------

            if changes:

                try:

                    send_registration_updated_email(
                        user=user,
                        changes=changes,
                        original_email=(
                            original_email
                        ),
                    )

                except Exception:

                    current_app.logger.exception(
                        (
                            "Unable to send "
                            "registration update email."
                        )
                    )

                    flash(
                        (
                            "The registration information "
                            "was saved, but the update "
                            "notification email could "
                            "not be sent."
                        ),
                        "warning",
                    )

            # ---------------------------------------------
            # NEW EMAIL NEEDS OTP VERIFICATION
            # ---------------------------------------------

            if (
                email_changed
                and
                verification_code
            ):

                try:

                    send_email_verification_code_email(
                        user=user,
                        code=verification_code,
                    )

                except Exception:

                    current_app.logger.exception(
                        (
                            "Unable to send verification "
                            "code to the new email."
                        )
                    )

                    flash(
                        (
                            "The email address was changed, "
                            "but the verification code "
                            "could not be sent."
                        ),
                        "warning",
                    )

                else:

                    flash(
                        (
                            "The email address was changed. "
                            "A new 6-digit verification code "
                            "was sent to the applicant. "
                            "The new email must be verified "
                            "before approval can continue."
                        ),
                        "success",
                    )

                # The user disappears from the pending
                # approval list until the new email
                # is successfully verified.
                return redirect(
                    url_for(
                        "superadmin.pending_registrations"
                    )
                )

            # ---------------------------------------------
            # NORMAL SAVE RESULT
            # ---------------------------------------------

            if changes:

                flash(
                    (
                        "Registration information "
                        "was updated successfully."
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

            # ---------------------------------------------
            # SUPERADMIN CHANGED EMAIL WHILE APPROVING
            #
            # DO NOT APPROVE THE ACCOUNT YET.
            # ---------------------------------------------

            if email_changed:

                try:

                    verification_code = (
                        prepare_new_email_verification(
                            user
                        )
                    )

                    db.session.commit()

                except Exception:

                    db.session.rollback()

                    current_app.logger.exception(
                        (
                            "Unable to save changed "
                            "email before approval."
                        )
                    )

                    flash(
                        (
                            "The email address was changed, "
                            "but the new verification "
                            "process could not be started."
                        ),
                        "error",
                    )

                    return render_template(
                        "superadmin/review_registration.html",
                        user=user,
                        form=form,
                    )

                # -----------------------------------------
                # SEND INFORMATION CHANGE NOTIFICATION
                # -----------------------------------------

                try:

                    send_registration_updated_email(
                        user=user,
                        changes=changes,
                        original_email=(
                            original_email
                        ),
                    )

                except Exception:

                    current_app.logger.exception(
                        (
                            "Unable to send "
                            "registration change "
                            "notification."
                        )
                    )

                # -----------------------------------------
                # SEND NEW OTP TO NEW EMAIL
                # -----------------------------------------

                try:

                    send_email_verification_code_email(
                        user=user,
                        code=verification_code,
                    )

                except Exception:

                    current_app.logger.exception(
                        (
                            "Unable to send verification "
                            "code to changed email."
                        )
                    )

                    flash(
                        (
                            "The new email address "
                            "was saved, but the "
                            "verification code "
                            "could not be sent."
                        ),
                        "warning",
                    )

                else:

                    flash(
                        (
                            "The email address was changed. "
                            "The applicant must verify "
                            "the new email using the "
                            "6-digit code before the "
                            "account can be approved."
                        ),
                        "warning",
                    )

                return redirect(
                    url_for(
                        "superadmin.pending_registrations"
                    )
                )

            # ---------------------------------------------
            # EMAIL IS VERIFIED
            # ACTIVATE ACCOUNT
            # ---------------------------------------------

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

            # Clear any old rejection information.
            user.rejected_at = None
            user.rejected_by_id = None
            user.rejection_reason = None

            # Clear login lock information.
            user.failed_login_attempts = 0
            user.locked_at = None

            # ---------------------------------------------
            # SAVE APPROVAL
            # ---------------------------------------------

            try:

                db.session.commit()

            except SQLAlchemyError:

                db.session.rollback()

                current_app.logger.exception(
                    (
                        "Database error while "
                        "approving registration."
                    )
                )

                flash(
                    (
                        "The registration could "
                        "not be approved."
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

            try:

                send_registration_approved_email(
                    user=user,
                    changes=changes,
                    original_email=(
                        original_email
                    ),
                )

            except Exception:

                current_app.logger.exception(
                    (
                        "Unable to send "
                        "registration approval email."
                    )
                )

                flash(
                    (
                        f"{user.full_name}'s registration "
                        "was approved, but the approval "
                        "email could not be sent."
                    ),
                    "warning",
                )

            else:

                flash(
                    (
                        f"{user.full_name}'s registration "
                        "has been approved successfully."
                    ),
                    "success",
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

            # A rejection must always contain a reason.
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

            # ---------------------------------------------
            # SET REJECTED STATUS
            # ---------------------------------------------

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

            # Remove approval information.
            user.approved_at = None
            user.approved_by_id = None

            # ---------------------------------------------
            # SAVE REJECTION
            # ---------------------------------------------

            try:

                db.session.commit()

            except SQLAlchemyError:

                db.session.rollback()

                current_app.logger.exception(
                    (
                        "Database error while "
                        "rejecting registration."
                    )
                )

                flash(
                    (
                        "The registration could "
                        "not be rejected."
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

            try:

                send_registration_rejected_email(
                    user=user,
                    rejection_reason=(
                        rejection_reason
                    ),
                    changes=changes,
                    original_email=(
                        original_email
                    ),
                )

            except Exception:

                current_app.logger.exception(
                    (
                        "Unable to send "
                        "registration rejection email."
                    )
                )

                flash(
                    (
                        f"{user.full_name}'s registration "
                        "was rejected, but the "
                        "notification email could "
                        "not be sent."
                    ),
                    "warning",
                )

            else:

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

    # =====================================================
    # GET REQUEST / FORM VALIDATION FAILURE
    # =====================================================

    return render_template(
        "superadmin/review_registration.html",
        user=user,
        form=form,
    )