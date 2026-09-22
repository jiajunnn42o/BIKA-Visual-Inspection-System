from datetime import (
    datetime,
    timezone,
)

from urllib.parse import (
    urlsplit,
)


from flask import (
    abort,
    jsonify,
    redirect,
    url_for,
)


from flask_login import (
    current_user,
    login_required,
)


from sqlalchemy.exc import (
    SQLAlchemyError,
)


from app.extensions import db

from app.notifications import (
    notifications_bp,
)

from app.workflow_models import (
    Notification,
    WorkInformationChangeRequest,
)


# =========================================================
# GET CURRENT USER NOTIFICATION
# =========================================================

def _notification_for_current_user(
    notification_id,
):

    notification = db.session.scalar(
        db.select(
            Notification
        )
        .where(
            Notification.id
            ==
            notification_id,

            Notification.recipient_user_id
            ==
            current_user.id,
        )
        .limit(1)
    )


    if notification is None:

        abort(
            404
        )


    return notification


# =========================================================
# SAFE FALLBACK LINK
# =========================================================

def _safe_internal_link(
    link,
):

    link = str(
        link
        or
        ""
    ).strip()


    if not link:

        return url_for(
            "account.index"
        )


    parsed = urlsplit(
        link
    )


    # External redirects are never allowed.
    if (
        parsed.scheme
        or
        parsed.netloc
    ):

        return url_for(
            "account.index"
        )


    if (
        not link.startswith(
            "/"
        )
    ):

        return url_for(
            "account.index"
        )


    if (
        link.startswith(
            "//"
        )
    ):

        return url_for(
            "account.index"
        )


    return link


# =========================================================
# PAYLOAD
# =========================================================

def _notification_payload(
    notification,
):

    payload = (
        notification.payload_json
        or
        {}
    )


    if (
        not isinstance(
            payload,
            dict,
        )
    ):

        return {}


    return payload


# =========================================================
# EXACT NOTIFICATION DESTINATION
# =========================================================

def _exact_notification_target(
    notification,
):
    """
    Calculate the most precise page for each
    notification instead of blindly trusting
    notification.link.

    Work Information Request:
        Request Status
        -> correct status tab
        -> exact request
        -> review modal automatically opens
    """

    notification_type = (
        str(
            notification.notification_type
            or
            ""
        )
        .strip()
    )


    payload = (
        _notification_payload(
            notification
        )
    )


    # =====================================================
    # WORK INFORMATION REQUEST
    # =====================================================

    if (
        notification_type
        in {
            "work_info_request_submitted",
            "work_info_request_approved",
            "work_info_request_rejected",
        }
    ):

        request_id = (
            payload.get(
                "request_id"
            )
        )


        try:

            request_id = int(
                request_id
            )


        except (
            TypeError,
            ValueError,
        ):

            request_id = None


        if (
            request_id
            is not None
        ):

            work_request = (
                db.session.get(
                    WorkInformationChangeRequest,
                    request_id,
                )
            )


            if (
                work_request
                is not None
            ):

                request_status = (
                    str(
                        work_request.status
                        or
                        "pending"
                    )
                    .strip()
                    .lower()
                )


                # The Work Information page currently
                # supports these three visible tabs.
                if (
                    request_status
                    not in {
                        "pending",
                        "approved",
                        "rejected",
                    }
                ):

                    request_status = (
                        "pending"
                    )


                # -------------------------------------------------
                # SUPERADMIN:
                # Submitted request notification should open the
                # exact request review modal.
                # -------------------------------------------------

                if (
                    notification_type
                    ==
                    "work_info_request_submitted"
                ):

                    return url_for(
                        "superadmin.work_information_requests",

                        status=(
                            request_status
                        ),

                        review=(
                            work_request.id
                        ),
                    )


                # -------------------------------------------------
                # APPLICANT:
                # Approved / Rejected result takes the user to
                # their exact Work Information section.
                # -------------------------------------------------

                if (
                    notification_type
                    in {
                        "work_info_request_approved",
                        "work_info_request_rejected",
                    }
                ):

                    return (
                        url_for(
                            "account.index"
                        )
                        +
                        "#work-information"
                    )


    # =====================================================
    # FALLBACK
    # =====================================================

    return _safe_internal_link(
        notification.link
    )


# =========================================================
# SERIALIZE
# =========================================================

def _serialize_notification(
    notification,
):

    actor_name = None


    if (
        notification.actor
        is not None
    ):

        actor_name = (
            notification.actor.full_name
        )


    return {

        "id":
            notification.id,

        "type":
            notification.notification_type,

        "title":
            notification.title,

        "message":
            notification.message,

        "is_read":
            bool(
                notification.is_read
            ),

        "created_at":
            (
                notification.created_at.isoformat()
                if notification.created_at
                else None
            ),

        "actor_name":
            actor_name,

        # IMPORTANT:
        # Always pass through open_notification.
        #
        # This marks it read first and then redirects
        # to the exact calculated destination.
        "open_url":
            url_for(
                "notifications.open_notification",

                notification_id=(
                    notification.id
                ),
            ),
    }


# =========================================================
# LATEST NOTIFICATIONS
# =========================================================

@notifications_bp.route(
    "/api/latest",
    methods=[
        "GET",
    ],
)
@login_required
def latest_notifications():

    notifications = (
        db.session.execute(
            db.select(
                Notification
            )
            .where(
                Notification.recipient_user_id
                ==
                current_user.id
            )
            .order_by(
                Notification.created_at.desc(),
                Notification.id.desc(),
            )
            .limit(
                10
            )
        )
        .scalars()
        .all()
    )


    unread_count = (
        db.session.scalar(
            db.select(
                db.func.count(
                    Notification.id
                )
            )
            .where(
                Notification.recipient_user_id
                ==
                current_user.id,

                Notification.is_read.is_(
                    False
                ),
            )
        )
        or
        0
    )


    return jsonify(

        ok=True,

        unread_count=int(
            unread_count
        ),

        notifications=[
            _serialize_notification(
                notification
            )
            for notification
            in notifications
        ],
    )


# =========================================================
# OPEN NOTIFICATION
# =========================================================

@notifications_bp.route(
    "/<int:notification_id>/open",
    methods=[
        "GET",
    ],
)
@login_required
def open_notification(
    notification_id,
):

    notification = (
        _notification_for_current_user(
            notification_id
        )
    )


    # =====================================================
    # MARK READ
    # =====================================================

    if (
        not notification.is_read
    ):

        notification.is_read = (
            True
        )


        notification.read_at = (
            datetime.now(
                timezone.utc
            )
        )


        try:

            db.session.commit()


        except SQLAlchemyError:

            db.session.rollback()


    # =====================================================
    # EXACT DESTINATION
    # =====================================================

    target = (
        _exact_notification_target(
            notification
        )
    )


    return redirect(
        target
    )


# =========================================================
# MARK ONE READ
# =========================================================

@notifications_bp.route(
    "/<int:notification_id>/read",
    methods=[
        "POST",
    ],
)
@login_required
def mark_notification_read(
    notification_id,
):

    notification = (
        _notification_for_current_user(
            notification_id
        )
    )


    if (
        not notification.is_read
    ):

        notification.is_read = (
            True
        )


        notification.read_at = (
            datetime.now(
                timezone.utc
            )
        )


        try:

            db.session.commit()


        except SQLAlchemyError:

            db.session.rollback()


            return jsonify(
                ok=False,

                message=(
                    "Unable to update notification."
                ),
            ), 500


    return jsonify(
        ok=True
    )


# =========================================================
# MARK ALL READ
# =========================================================

@notifications_bp.route(
    "/read-all",
    methods=[
        "POST",
    ],
)
@login_required
def mark_all_notifications_read():

    notifications = (
        db.session.execute(
            db.select(
                Notification
            )
            .where(
                Notification.recipient_user_id
                ==
                current_user.id,

                Notification.is_read.is_(
                    False
                ),
            )
        )
        .scalars()
        .all()
    )


    if (
        not notifications
    ):

        return jsonify(
            ok=True,
            updated=0,
        )


    read_time = (
        datetime.now(
            timezone.utc
        )
    )


    for notification in notifications:

        notification.is_read = (
            True
        )


        notification.read_at = (
            read_time
        )


    try:

        db.session.commit()


    except SQLAlchemyError:

        db.session.rollback()


        return jsonify(

            ok=False,

            message=(
                "Unable to mark notifications as read."
            ),
        ), 500


    return jsonify(

        ok=True,

        updated=len(
            notifications
        ),
    )