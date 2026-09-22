from datetime import (
    datetime,
    timezone,
)


from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)


from flask_login import (
    current_user,
)


from sqlalchemy.exc import (
    IntegrityError,
    SQLAlchemyError,
)


from app.extensions import db


from app.models import (
    User,
)


from app.workflow_models import (
    WorkInformationChangeRequest,
)


from app.services.notification_service import (
    email_notifications_enabled,
    notify_work_request_result,
)


from app.services.work_request_email_service import (
    send_work_information_result_email,
)


from app.superadmin import (
    superadmin_bp,
)


from app.superadmin.routes import (
    superadmin_required,
)


# =========================================================
# HELPERS
# =========================================================

VALID_REQUEST_STATUSES = {
    "pending",
    "approved",
    "rejected",
}


def _get_work_request_or_404(
    request_id,
):
    work_request = db.session.get(
        WorkInformationChangeRequest,
        request_id,
    )


    if work_request is None:

        abort(
            404
        )


    return work_request


def _employee_id_conflict(
    employee_id,
    target_user_id,
):
    if not employee_id:
        return False


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
                employee_id.upper(),

                User.id
                !=
                target_user_id,
            )
            .limit(1)
        )
    )


    return (
        existing_user_id
        is not None
    )


# =========================================================
# LIST
# =========================================================

@superadmin_bp.route(
    "/work-information-requests",
    methods=[
        "GET",
    ],
)
@superadmin_required
def work_information_requests():

    status = (
        request.args.get(
            "status",
            "pending",
        )
        .strip()
        .lower()
    )


    if (
        status
        not in
        VALID_REQUEST_STATUSES
    ):

        status = (
            "pending"
        )


    requests_list = (
        db.session.execute(
            db.select(
                WorkInformationChangeRequest
            )
            .where(
                WorkInformationChangeRequest.status
                ==
                status
            )
            .order_by(
                WorkInformationChangeRequest
                .created_at
                .desc(),

                WorkInformationChangeRequest
                .id
                .desc(),
            )
        )
        .scalars()
        .all()
    )


    pending_count = (
        db.session.scalar(
            db.select(
                db.func.count(
                    WorkInformationChangeRequest.id
                )
            )
            .where(
                WorkInformationChangeRequest.status
                ==
                "pending"
            )
        )
        or
        0
    )


    approved_count = (
        db.session.scalar(
            db.select(
                db.func.count(
                    WorkInformationChangeRequest.id
                )
            )
            .where(
                WorkInformationChangeRequest.status
                ==
                "approved"
            )
        )
        or
        0
    )


    rejected_count = (
        db.session.scalar(
            db.select(
                db.func.count(
                    WorkInformationChangeRequest.id
                )
            )
            .where(
                WorkInformationChangeRequest.status
                ==
                "rejected"
            )
        )
        or
        0
    )


    return render_template(
        "superadmin/work_information_requests.html",

        requests_list=(
            requests_list
        ),

        current_status=(
            status
        ),

        pending_count=(
            pending_count
        ),

        approved_count=(
            approved_count
        ),

        rejected_count=(
            rejected_count
        ),
    )


# =========================================================
# APPROVE
# =========================================================

@superadmin_bp.route(
    (
        "/work-information-requests/"
        "<int:request_id>/approve"
    ),
    methods=[
        "POST",
    ],
)
@superadmin_required
def approve_work_information_request(
    request_id,
):

    work_request = (
        _get_work_request_or_404(
            request_id
        )
    )


    if (
        work_request.status
        !=
        "pending"
    ):

        flash(
            (
                "This request has already "
                "been processed."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.work_information_requests"
            )
        )


    target_user = (
        db.session.get(
            User,
            work_request.user_id,
        )
    )


    if target_user is None:

        abort(
            404
        )


    # =====================================================
    # OLD PRE-RULE SUPERADMIN SELF REQUEST
    # =====================================================

    if (
        target_user.id
        ==
        current_user.id
    ):

        flash(
            (
                "SuperAdmin self-changes no longer "
                "require approval. Edit your Work "
                "Information directly from My Account."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.work_information_requests"
            )
        )


    # =====================================================
    # RECHECK EMPLOYEE ID
    # =====================================================

    if (
        _employee_id_conflict(
            work_request.new_employee_id,
            target_user.id,
        )
    ):

        flash(
            (
                "This Employee ID is now being "
                "used by another account. "
                "The request cannot be approved."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.work_information_requests",
                review=request_id,
            )
        )


    # =====================================================
    # APPLY
    # =====================================================

    target_user.employee_id = (
        work_request.new_employee_id
    )

    target_user.department = (
        work_request.new_department
    )

    target_user.shift = (
        work_request.new_shift
    )

    target_user.job_title = (
        work_request.new_job_title
    )


    work_request.status = (
        "approved"
    )

    work_request.reviewed_by_id = (
        current_user.id
    )

    work_request.reviewed_at = (
        datetime.now(
            timezone.utc
        )
    )

    work_request.rejection_reason = (
        None
    )


    # =====================================================
    # CREATE APPLICANT NOTIFICATION
    # =====================================================

    notify_work_request_result(
        work_request
    )


    try:

        db.session.commit()


    except IntegrityError:

        db.session.rollback()

        flash(
            (
                "The request could not be approved "
                "because one of the values is now "
                "already in use."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.work_information_requests",
                review=request_id,
            )
        )


    except SQLAlchemyError:

        db.session.rollback()

        current_app.logger.exception(
            (
                "Unable to approve work "
                "information request %s."
            ),
            request_id,
        )

        flash(
            (
                "The request could not "
                "be approved."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.work_information_requests",
                review=request_id,
            )
        )


    # =====================================================
    # EMAIL APPLICANT
    # =====================================================

    if (
        email_notifications_enabled(
            target_user.id
        )
    ):

        try:

            send_work_information_result_email(
                recipient=target_user,
                work_request=work_request,
            )


        except Exception:

            current_app.logger.exception(
                (
                    "Work request %s was approved "
                    "but result email failed."
                ),
                request_id,
            )


    flash(
        (
            f"{target_user.full_name}'s work "
            "information request has been approved."
        ),
        "success",
    )


    return redirect(
        url_for(
            "superadmin.work_information_requests",
            status="pending",
        )
    )


# =========================================================
# REJECT
# =========================================================

@superadmin_bp.route(
    (
        "/work-information-requests/"
        "<int:request_id>/reject"
    ),
    methods=[
        "POST",
    ],
)
@superadmin_required
def reject_work_information_request(
    request_id,
):

    work_request = (
        _get_work_request_or_404(
            request_id
        )
    )


    if (
        work_request.status
        !=
        "pending"
    ):

        flash(
            (
                "This request has already "
                "been processed."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.work_information_requests"
            )
        )


    reason = (
        request.form.get(
            "reason",
            "",
        )
        .strip()
    )


    if (
        len(reason)
        <
        3
    ):

        flash(
            (
                "Please enter a rejection reason."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.work_information_requests",
                review=request_id,
            )
        )


    if (
        len(reason)
        >
        1000
    ):

        flash(
            (
                "The rejection reason is too long."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.work_information_requests",
                review=request_id,
            )
        )


    target_user = (
        db.session.get(
            User,
            work_request.user_id,
        )
    )


    if target_user is None:

        abort(
            404
        )


    work_request.status = (
        "rejected"
    )

    work_request.reviewed_by_id = (
        current_user.id
    )

    work_request.reviewed_at = (
        datetime.now(
            timezone.utc
        )
    )

    work_request.rejection_reason = (
        reason
    )


    # users table is intentionally NOT changed.


    notify_work_request_result(
        work_request
    )


    try:

        db.session.commit()


    except SQLAlchemyError:

        db.session.rollback()

        current_app.logger.exception(
            (
                "Unable to reject work "
                "information request %s."
            ),
            request_id,
        )

        flash(
            (
                "The request could not "
                "be rejected."
            ),
            "error",
        )

        return redirect(
            url_for(
                "superadmin.work_information_requests",
                review=request_id,
            )
        )


    # =====================================================
    # EMAIL APPLICANT
    # =====================================================

    if (
        email_notifications_enabled(
            target_user.id
        )
    ):

        try:

            send_work_information_result_email(
                recipient=target_user,
                work_request=work_request,
            )


        except Exception:

            current_app.logger.exception(
                (
                    "Work request %s was rejected "
                    "but result email failed."
                ),
                request_id,
            )


    flash(
        (
            f"{target_user.full_name}'s work "
            "information request has been rejected."
        ),
        "success",
    )


    return redirect(
        url_for(
            "superadmin.work_information_requests",
            status="pending",
        )
    )