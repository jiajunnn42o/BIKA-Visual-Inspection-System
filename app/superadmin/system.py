from datetime import (
    datetime,
    timedelta,
    timezone,
)


from flask import (
    render_template,
    url_for,
)


from app.extensions import db

from app.models import (
    User,
    UserRole,
    UserStatus,
)

from app.superadmin import (
    superadmin_bp,
)

from app.superadmin.routes import (
    superadmin_required,
)


# =========================================================
# TIME
# =========================================================

def _utc_datetime(
    value,
):

    if value is None:
        return None


    if value.tzinfo is None:

        return value.replace(
            tzinfo=timezone.utc
        )


    return value.astimezone(
        timezone.utc
    )


# =========================================================
# INITIALS
# =========================================================

def _initials(
    user,
):

    first = str(
        user.first_name
        or
        ""
    ).strip()


    last = str(
        user.last_name
        or
        ""
    ).strip()


    result = (
        (
            first[:1]
            +
            last[:1]
        )
        .upper()
    )


    return (
        result
        or
        str(
            user.username
            or
            "U"
        )[:2].upper()
    )


# =========================================================
# ROLE
# =========================================================

def _role_label(
    role,
):

    mapping = {
        "user":
            "User",

        "admin":
            "Admin",

        "superadmin":
            "Superadmin",
    }


    return mapping.get(
        role,
        str(
            role
            or
            ""
        ).title(),
    )


# =========================================================
# INACTIVE
# =========================================================

def _is_inactive(
    user,
    now,
):

    if (
        user.status
        !=
        UserStatus.ACTIVE.value
    ):

        return False


    last_active = (
        _utc_datetime(
            user.last_active_at
        )
    )


    if (
        last_active
        is None
    ):

        return True


    return (
        last_active
        <
        now
        -
        timedelta(
            days=30
        )
    )


# =========================================================
# LAST ACTIVE
# =========================================================

def _last_active_view(
    user,
    now,
):

    if (
        user.status
        ==
        UserStatus.LOCKED.value
    ):

        return {
            "label":
                "Locked",

            "meta":
                "Too many attempts",

            "dot":
                "red",
        }


    value = (
        _utc_datetime(
            user.last_active_at
        )
    )


    if (
        value is None
    ):

        return {
            "label":
                "No activity",

            "meta":
                "Never active",

            "dot":
                "orange",
        }


    delta = (
        now
        -
        value
    )


    seconds = max(
        0,
        int(
            delta.total_seconds()
        )
    )


    if (
        seconds
        <
        300
    ):

        return {
            "label":
                "Online",

            "meta":
                "Just now",

            "dot":
                "green",
        }


    minutes = (
        seconds
        //
        60
    )


    if (
        minutes
        <
        60
    ):

        return {
            "label":
                f"{minutes} min ago",

            "meta":
                "Online"
                if minutes <= 5
                else
                value.strftime(
                    "%Y-%m-%d %H:%M"
                ),

            "dot":
                "green",
        }


    hours = (
        minutes
        //
        60
    )


    if (
        hours
        <
        24
    ):

        return {
            "label":
                f"{hours} hr ago"
                if hours == 1
                else
                f"{hours} hrs ago",

            "meta":
                value.strftime(
                    "%Y-%m-%d %H:%M"
                ),

            "dot":
                "green",
        }


    days = (
        hours
        //
        24
    )


    return {
        "label":
            f"{days} days ago",

        "meta":
            value.strftime(
                "%Y-%m-%d %H:%M"
            ),

        "dot":
            (
                "orange"
                if days > 30
                else
                "green"
            ),
    }


# =========================================================
# SECURITY
# =========================================================

def _security_view(
    user,
    inactive,
):

    if (
        user.status
        ==
        UserStatus.LOCKED.value
    ):

        failed_attempts = (
            getattr(
                user,
                "failed_login_attempts",
                0,
            )
            or
            0
        )


        return {
            "key":
                "locked",

            "label":
                "Locked",

            "meta":
                (
                    f"{failed_attempts} failed login"
                    if failed_attempts == 1
                    else
                    f"{failed_attempts} failed logins"
                ),
        }


    if (
        user.role
        ==
        UserRole.SUPERADMIN.value
    ):

        return {
            "key":
                "protected",

            "label":
                "Protected",

            "meta":
                "High Privilege",
        }


    if (
        inactive
    ):

        return {
            "key":
                "inactive",

            "label":
                "Inactive",

            "meta":
                "No recent activity",
        }


    return {
        "key":
            "normal",

        "label":
            "Normal",

        "meta":
            "No issues",
    }


# =========================================================
# USER VIEW
# =========================================================

def _user_view(
    user,
    index,
    now,
):

    inactive = (
        _is_inactive(
            user,
            now,
        )
    )


    if (
        user.status
        ==
        UserStatus.LOCKED.value
    ):

        display_status = (
            "locked"
        )

        status_label = (
            "Locked"
        )


    elif (
        inactive
    ):

        display_status = (
            "inactive"
        )

        status_label = (
            "Inactive"
        )


    else:

        display_status = (
            "active"
        )

        status_label = (
            "Active"
        )


    last_active = (
        _last_active_view(
            user,
            now,
        )
    )


    security = (
        _security_view(
            user,
            inactive,
        )
    )


    last_login = (
        _utc_datetime(
            user.last_login_at
        )
    )


    profile_photo_url = (
        url_for(
            "static",
            filename=user.profile_photo,
        )
        if user.profile_photo
        else None
    )


    tones = (
        "green",
        "teal",
        "blue",
        "orange",
        "red",
    )


    return {
        "id":
            user.id,

        "name":
            user.full_name,

        "email":
            user.email,

        "initials":
            _initials(
                user
            ),

        "profile_photo_url":
            profile_photo_url,

        "avatar_tone":
            tones[
                index
                %
                len(
                    tones
                )
            ],

        "role":
            user.role,

        "role_label":
            _role_label(
                user.role
            ),

        "display_status":
            display_status,

        "status_label":
            status_label,

        "last_active_label":
            last_active[
                "label"
            ],

        "last_active_meta":
            last_active[
                "meta"
            ],

        "last_active_dot":
            last_active[
                "dot"
            ],

        "last_login_label":
            (
                last_login.strftime(
                    "%Y-%m-%d %H:%M"
                )
                if last_login
                else
                "Never"
            ),

        "last_login_ip":
            (
                getattr(
                    user,
                    "last_login_ip",
                    None,
                )
                or
                "—"
            ),

        "security_key":
            security[
                "key"
            ],

        "security_label":
            security[
                "label"
            ],

        "security_meta":
            security[
                "meta"
            ],
    }


# =========================================================
# SYSTEM PAGE
# =========================================================

@superadmin_bp.route(
    "/system",
    methods=[
        "GET",
    ],
)
@superadmin_required
def system_page():

    now = datetime.now(
        timezone.utc
    )


    # Pending / rejected registration applications are not
    # shown in the normal user management table.
    users = (
        db.session.execute(
            db.select(
                User
            )
            .where(
                User.status.in_(
                    (
                        UserStatus.ACTIVE.value,
                        UserStatus.DISABLED.value,
                        UserStatus.LOCKED.value,
                    )
                )
            )
            .order_by(
                User.first_name.asc(),
                User.last_name.asc(),
                User.id.asc(),
            )
        )
        .scalars()
        .all()
    )


    system_users = [
        _user_view(
            user,
            index,
            now,
        )
        for index, user
        in enumerate(
            users
        )
    ]


    inactive_users = sum(
        1
        for user
        in users
        if _is_inactive(
            user,
            now,
        )
    )


    locked_accounts = sum(
        1
        for user
        in users
        if (
            user.status
            ==
            UserStatus.LOCKED.value
        )
    )


    active_users = sum(
        1
        for user
        in users
        if (
            user.status
            ==
            UserStatus.ACTIVE.value
            and
            not _is_inactive(
                user,
                now,
            )
        )
    )


    superadmins = sum(
        1
        for user
        in users
        if (
            user.role
            ==
            UserRole.SUPERADMIN.value
        )
    )


    system_stats = {
        "total_users":
            len(
                users
            ),

        "active_users":
            active_users,

        "inactive_users":
            inactive_users,

        "locked_accounts":
            locked_accounts,

        "superadmins":
            superadmins,
    }


    system_config = {
        "yield_target":
            85,

        "batch_pass_threshold":
            80,

        "confidence_threshold":
            "0.50",

        "password_hashing":
            "werkzeug.security",
    }


    return render_template(
        "superadmin/system.html",

        system_users=(
            system_users
        ),

        system_stats=(
            system_stats
        ),

        system_config=(
            system_config
        ),
    )