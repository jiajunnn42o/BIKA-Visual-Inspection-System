from functools import wraps

from flask import (
    abort,
    jsonify,
    request,
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

from app.models import (
    User,
)

from app.superadmin import (
    superadmin_bp,
)


from app.services.about_system_audit_service import (
    write_about_system_audit,
)


VALID_ROLES = {
    "user",
    "admin",
    "superadmin",
}


MANAGEABLE_STATUSES = {
    "active",
    "disabled",
    "locked",
}


# =========================================================
# SUPERADMIN PERMISSION
# =========================================================

def superadmin_required(
    view_function,
):

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
            !=
            "superadmin"
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

def _get_user_or_404(
    user_id,
):

    user = db.session.get(
        User,
        user_id,
    )

    if user is None:

        abort(
            404
        )

    return user


def _role_label(
    role,
):

    labels = {
        "user":
            "User",

        "admin":
            "Admin",

        "superadmin":
            "SuperAdmin",
    }

    return labels.get(
        role,
        str(
            role
            or
            ""
        ).title(),
    )


def _status_label(
    status,
):

    labels = {
        "active":
            "Active",

        "disabled":
            "Disabled",

        "locked":
            "Locked",

        "pending":
            "Pending",

        "rejected":
            "Rejected",
    }

    return labels.get(
        status,
        str(
            status
            or
            ""
        ).title(),
    )


def _user_initials(
    user,
):

    parts = [
        str(
            user.first_name
            or
            ""
        ).strip(),

        str(
            user.last_name
            or
            ""
        ).strip(),
    ]

    initials = "".join(
        (
            part[0].upper()
            if part
            else ""
        )
        for part
        in parts
    )

    return (
        initials
        or
        "U"
    )


def _profile_photo_url(
    user,
):

    if not user.profile_photo:
        return None

    value = str(
        user.profile_photo
    ).strip()

    if not value:
        return None

    if value.startswith(
        "/static/"
    ):

        return value

    return url_for(
        "static",
        filename=value,
    )


def _status_action_config(
    status,
):

    if status == "active":

        return {
            "action":
                "disable",

            "label":
                "Disable Account",

            "help":
                (
                    "Disables login access while "
                    "keeping the account and history."
                ),
        }

    if status == "disabled":

        return {
            "action":
                "reactivate",

            "label":
                "Reactivate Account",

            "help":
                (
                    "Restores login access "
                    "for this account."
                ),
        }

    if status == "locked":

        return {
            "action":
                "unlock",

            "label":
                "Unlock Account",

            "help":
                (
                    "Clears the security lock "
                    "and restores login access."
                ),
        }

    return {
        "action":
            "none",

        "label":
            "Managed elsewhere",

        "help":
            (
                "This status is controlled by "
                "the registration workflow."
            ),
    }


def _has_other_active_superadmin(
    exclude_user_id,
):

    other_id = db.session.scalar(
        db.select(
            User.id
        )
        .where(
            User.id
            !=
            exclude_user_id,

            User.role
            ==
            "superadmin",

            User.status
            ==
            "active",
        )
        .limit(
            1
        )
    )

    return (
        other_id
        is not None
    )


def _serialize_user(
    user,
):

    is_self = (
        user.id
        ==
        current_user.id
    )

    manageable_status = (
        user.status
        in
        MANAGEABLE_STATUSES
    )

    status_config = (
        _status_action_config(
            user.status
        )
    )

    return {
        "id":
            user.id,

        "name":
            user.full_name,

        "first_name":
            user.first_name,

        "last_name":
            user.last_name,

        "username":
            user.username,

        "email":
            user.email,

        "phone_number":
            user.phone_number,

        "employee_id":
            user.employee_id,

        "job_title":
            user.job_title,

        "department":
            user.department,

        "shift":
            user.shift,

        "role":
            user.role,

        "role_label":
            _role_label(
                user.role
            ),

        "status":
            user.status,

        "status_label":
            _status_label(
                user.status
            ),

        "profile_photo_url":
            _profile_photo_url(
                user
            ),

        "initials":
            _user_initials(
                user
            ),

        "is_self":
            is_self,

        "can_edit_role":
            (
                not is_self
                and
                manageable_status
            ),

        "can_change_status":
            (
                not is_self
                and
                manageable_status
                and
                status_config[
                    "action"
                ]
                !=
                "none"
            ),

        "status_action":
            status_config[
                "action"
            ],

        "status_action_label":
            status_config[
                "label"
            ],

        "status_help":
            (
                (
                    "You cannot change your own "
                    "account status."
                )
                if is_self
                else
                status_config[
                    "help"
                ]
            ),
    }


# =========================================================
# GET USER FOR SYSTEM EDIT MODAL
# =========================================================

@superadmin_bp.route(
    "/system/users/<int:user_id>/edit",
    methods=[
        "GET",
    ],
)
@superadmin_required
def system_user_detail(
    user_id,
):

    user = (
        _get_user_or_404(
            user_id
        )
    )

    return jsonify({
        "ok":
            True,

        "user":
            _serialize_user(
                user
            ),
    })


# =========================================================
# UPDATE USER ACCESS
# =========================================================

@superadmin_bp.route(
    "/system/users/<int:user_id>/access",
    methods=[
        "POST",
    ],
)
@superadmin_required
def system_update_user_access(
    user_id,
):

    user = (
        _get_user_or_404(
            user_id
        )
    )

    data = (
        request.get_json(
            silent=True
        )
        or
        {}
    )

    requested_role = str(
        data.get(
            "role",
            user.role,
        )
        or
        ""
    ).strip().lower()

    status_action = str(
        data.get(
            "status_action",
            "none",
        )
        or
        "none"
    ).strip().lower()

    superadmin_password = str(
        data.get(
            "superadmin_password",
            "",
        )
        or
        ""
    )


    original_role = (
        user.role
    )

    original_status = (
        user.status
    )


    # =====================================================
    # WORKFLOW-OWNED STATUS
    # =====================================================

    if (
        user.status
        not in
        MANAGEABLE_STATUSES
    ):

        return jsonify({
            "ok":
                False,

            "message":
                (
                    "Pending or rejected accounts "
                    "must be managed through "
                    "Request Status."
                ),
        }), 409


    # =====================================================
    # VALID ROLE
    # =====================================================

    if (
        requested_role
        not in
        VALID_ROLES
    ):

        return jsonify({
            "ok":
                False,

            "message":
                "Please select a valid access role.",
        }), 400


    # =====================================================
    # VALID STATUS ACTION
    # =====================================================

    valid_status_actions = {
        "none",
        "disable",
        "reactivate",
        "unlock",
    }

    if (
        status_action
        not in
        valid_status_actions
    ):

        return jsonify({
            "ok":
                False,

            "message":
                "Invalid account status action.",
        }), 400


    # =====================================================
    # SELF PROTECTION
    # =====================================================

    if (
        user.id
        ==
        current_user.id
    ):

        if (
            requested_role
            !=
            user.role
        ):

            return jsonify({
                "ok":
                    False,

                "message":
                    (
                        "You cannot change your own "
                        "SuperAdmin role."
                    ),
            }), 400

        if (
            status_action
            !=
            "none"
        ):

            return jsonify({
                "ok":
                    False,

                "message":
                    (
                        "You cannot change your own "
                        "account status."
                    ),
            }), 400


    # =====================================================
    # SECURITY-SENSITIVE CHANGE DETECTION
    #
    # SuperAdmin password is required for every
    # user-access change:
    # 1. Changing a user's access role
    # 2. Disabling an account
    # 3. Reactivating an account
    # 4. Unlocking an account
    # =====================================================

    role_changed = (
        requested_role
        !=
        original_role
    )

    requires_superadmin_password = (
        role_changed
        or
        status_action
        !=
        "none"
    )


    # =====================================================
    # SUPERADMIN PASSWORD VERIFICATION
    # =====================================================

    if (
        requires_superadmin_password
    ):

        if (
            not superadmin_password
        ):

            return jsonify({
                "ok":
                    False,

                "code":
                    "superadmin_password_required",

                "message":
                    (
                        "Enter your SuperAdmin password "
                        "to confirm this access change."
                    ),
            }), 400

        if (
            not current_user.check_password(
                superadmin_password
            )
        ):

            return jsonify({
                "ok":
                    False,

                "code":
                    "invalid_superadmin_password",

                "message":
                    "Incorrect SuperAdmin password.",
            }), 403


    # =====================================================
    # VALIDATE STATUS TRANSITION
    # =====================================================

    new_status = (
        user.status
    )

    if (
        status_action
        ==
        "disable"
    ):

        if (
            user.status
            !=
            "active"
        ):

            return jsonify({
                "ok":
                    False,

                "message":
                    (
                        "Only an active account "
                        "can be disabled."
                    ),
            }), 400

        new_status = (
            "disabled"
        )


    elif (
        status_action
        ==
        "reactivate"
    ):

        if (
            user.status
            !=
            "disabled"
        ):

            return jsonify({
                "ok":
                    False,

                "message":
                    (
                        "Only a disabled account "
                        "can be reactivated."
                    ),
            }), 400

        new_status = (
            "active"
        )


    elif (
        status_action
        ==
        "unlock"
    ):

        if (
            user.status
            !=
            "locked"
        ):

            return jsonify({
                "ok":
                    False,

                "message":
                    (
                        "Only a locked account "
                        "can be unlocked."
                    ),
            }), 400

        new_status = (
            "active"
        )


    # =====================================================
    # KEEP AT LEAST ONE ACTIVE SUPERADMIN
    # =====================================================

    removes_active_superadmin = (
        user.role
        ==
        "superadmin"
        and
        user.status
        ==
        "active"
        and
        (
            requested_role
            !=
            "superadmin"
            or
            new_status
            !=
            "active"
        )
    )

    if (
        removes_active_superadmin
        and
        not _has_other_active_superadmin(
            user.id
        )
    ):

        return jsonify({
            "ok":
                False,

            "message":
                (
                    "This change would leave the "
                    "system without an active "
                    "SuperAdmin."
                ),
        }), 400


    # =====================================================
    # NO CHANGES
    # =====================================================

    if (
        requested_role
        ==
        user.role
        and
        new_status
        ==
        user.status
    ):

        return jsonify({
            "ok":
                False,

            "message":
                "No changes were selected.",
        }), 400


    # =====================================================
    # APPLY
    # =====================================================

    user.role = (
        requested_role
    )

    user.status = (
        new_status
    )


    # Reset security lock state whenever an admin-managed
    # transition leaves the account active/disabled.

    if (
        status_action
        in {
            "disable",
            "reactivate",
            "unlock",
        }
    ):

        user.failed_login_attempts = (
            0
        )

        user.locked_at = (
            None
        )


    try:

        db.session.commit()

    except SQLAlchemyError:

        db.session.rollback()

        return jsonify({
            "ok":
                False,

            "message":
                (
                    "The user changes could not "
                    "be saved. Please try again."
                ),
        }), 500


    # =====================================================
    # ABOUT SYSTEM AUDIT LOG
    # =====================================================

    if (
        original_role
        !=
        user.role
    ):

        write_about_system_audit(
            category="Security",
            action="Changed user role",
            details=(
                f"{user.full_name}: "
                f"{_role_label(original_role)} "
                f"→ {_role_label(user.role)}"
            ),
        )


    if (
        original_status
        !=
        user.status
    ):

        action_labels = {
            "disable":
                "Deactivated user account",

            "reactivate":
                "Reactivated user account",

            "unlock":
                "Unlocked user account",
        }

        write_about_system_audit(
            category="Security",
            action=(
                action_labels.get(
                    status_action,
                    "Changed user account status",
                )
            ),
            details=(
                f"{user.full_name}: "
                f"{_status_label(original_status)} "
                f"→ {_status_label(user.status)}"
            ),
        )


    return jsonify({
        "ok":
            True,

        "message":
            (
                f"{user.full_name}'s account "
                "access was updated successfully."
            ),

        "user":
            _serialize_user(
                user
            ),
    })
