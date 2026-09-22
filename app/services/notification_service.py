from app.extensions import db

from app.workflow_models import (
    Notification,
    UserNotificationPreference,
)


# =========================================================
# PREFERENCES
# =========================================================

def get_notification_preferences(
    user_id,
    *,
    create=True,
):
    preferences = db.session.get(
        UserNotificationPreference,
        user_id,
    )

    if (
        preferences is None
        and create
    ):
        preferences = UserNotificationPreference(
            user_id=user_id,
            email_notifications=True,
            in_app_alerts=True,
        )

        db.session.add(
            preferences
        )

    return preferences


def email_notifications_enabled(
    user_id,
):
    """
    Existing users without a preference row
    use the default ON behaviour.
    """

    preferences = db.session.get(
        UserNotificationPreference,
        user_id,
    )

    if preferences is None:
        return True

    return bool(
        preferences.email_notifications
    )


# =========================================================
# CREATE NOTIFICATION
# =========================================================

def create_notification(
    *,
    recipient_user_id,
    actor_user_id=None,
    notification_type,
    title,
    message,
    link=None,
    payload_json=None,
    force=False,
):
    """
    Adds a notification to the CURRENT transaction.

    Does not commit.
    """

    preferences = get_notification_preferences(
        recipient_user_id,
        create=True,
    )

    if (
        not force
        and preferences
        and not preferences.in_app_alerts
    ):
        return None

    notification = Notification(
        recipient_user_id=recipient_user_id,
        actor_user_id=actor_user_id,
        notification_type=notification_type,
        title=title,
        message=message,
        link=link,
        payload_json=payload_json,
        is_read=False,
    )

    db.session.add(
        notification
    )

    return notification


# =========================================================
# LATEST
# =========================================================

def get_latest_notifications(
    user_id,
    *,
    limit=8,
):
    return (
        db.session.execute(
            db.select(
                Notification
            )
            .where(
                Notification.recipient_user_id
                == user_id
            )
            .order_by(
                Notification.created_at.desc(),
                Notification.id.desc(),
            )
            .limit(limit)
        )
        .scalars()
        .all()
    )


# =========================================================
# UNREAD COUNT
# =========================================================

def get_unread_notification_count(
    user_id,
):
    count = db.session.scalar(
        db.select(
            db.func.count(
                Notification.id
            )
        )
        .where(
            Notification.recipient_user_id
            == user_id,

            Notification.is_read.is_(
                False
            ),
        )
    )

    return int(
        count or 0
    )


# =========================================================
# MARK ONE READ
# =========================================================

def mark_notification_read(
    notification_id,
    user_id,
):
    notification = db.session.scalar(
        db.select(
            Notification
        )
        .where(
            Notification.id
            == notification_id,

            Notification.recipient_user_id
            == user_id,
        )
    )

    if notification is None:
        return None

    notification.mark_read()

    return notification


# =========================================================
# MARK ALL READ
# =========================================================

def mark_all_notifications_read(
    user_id,
):
    notifications = (
        db.session.execute(
            db.select(
                Notification
            )
            .where(
                Notification.recipient_user_id
                == user_id,

                Notification.is_read.is_(
                    False
                ),
            )
        )
        .scalars()
        .all()
    )

    for notification in notifications:
        notification.mark_read()

    return len(
        notifications
    )


# =========================================================
# WORK INFORMATION REQUEST
# =========================================================

def notify_superadmins_of_work_request(
    work_request,
):
    """
    Create an in-app notification for every
    ACTIVE SuperAdmin.

    SuperAdmins are intentionally included even
    when the requester is also a SuperAdmin.

    This allows a single-SuperAdmin development
    installation to still process requests.
    """

    from app.models import (
        User,
        UserRole,
        UserStatus,
    )

    superadmins = (
        db.session.execute(
            db.select(
                User
            )
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
        .scalars()
        .all()
    )

    requester = work_request.requested_by

    if requester:
        requester_name = (
            requester.full_name
        )
    else:
        requester_name = "A user"

    changed_fields = (
        work_request.changed_fields()
    )

    changed_names = ", ".join(
        row[0]
        for row in changed_fields
    )

    if not changed_names:
        changed_names = (
            "Work Information"
        )

    for superadmin in superadmins:

        create_notification(
            recipient_user_id=superadmin.id,
            actor_user_id=work_request.requested_by_id,
            notification_type=(
                "work_info_request_submitted"
            ),
            title=(
                "New Work Information Request"
            ),
            message=(
                f"{requester_name} requested "
                f"changes to {changed_names}."
            ),
            link=(
                "/superadmin/registrations"
                "?section=work"
                f"&review_work={work_request.id}"
            ),
            payload_json={
                "request_id":
                    work_request.id,

                "user_id":
                    work_request.user_id,
            },
        )

    return superadmins


# =========================================================
# APPROVE / REJECT RESULT
# Used in next stage.
# =========================================================

def notify_work_request_result(
    work_request,
):
    if (
        work_request.status
        ==
        "approved"
    ):
        notification_type = (
            "work_info_request_approved"
        )

        title = (
            "Work Information Request Approved"
        )

        message = (
            "Your work information change "
            "request has been approved."
        )

    elif (
        work_request.status
        ==
        "rejected"
    ):
        notification_type = (
            "work_info_request_rejected"
        )

        title = (
            "Work Information Request Rejected"
        )

        message = (
            "Your work information change "
            "request has been rejected."
        )

        if work_request.rejection_reason:
            message += (
                " Reason: "
                +
                work_request.rejection_reason
            )

    else:
        return None

    return create_notification(
        recipient_user_id=work_request.user_id,
        actor_user_id=work_request.reviewed_by_id,
        notification_type=notification_type,
        title=title,
        message=message,
        link="/account",
        payload_json={
            "request_id":
                work_request.id,
        },
    )