from datetime import (
    datetime,
    timezone,
)

from app.extensions import db


# =========================================================
# TIME
# =========================================================

def utc_now():
    return datetime.now(
        timezone.utc
    )


# =========================================================
# WORK INFORMATION CHANGE REQUEST
# =========================================================

class WorkInformationChangeRequest(
    db.Model
):
    __tablename__ = (
        "work_information_change_requests"
    )


    # =====================================================
    # ID
    # =====================================================

    id = db.Column(
        db.Integer,
        primary_key=True,
    )


    # =====================================================
    # TARGET USER
    # =====================================================

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )


    # =====================================================
    # REQUESTED BY
    #
    # Usually this is the same user.
    # Kept separately for audit purposes.
    # =====================================================

    requested_by_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )


    # =====================================================
    # EMPLOYEE ID
    # =====================================================

    old_employee_id = db.Column(
        db.String(80),
        nullable=True,
    )


    new_employee_id = db.Column(
        db.String(80),
        nullable=True,
        index=True,
    )


    # =====================================================
    # DEPARTMENT
    # =====================================================

    old_department = db.Column(
        db.String(120),
        nullable=True,
    )


    new_department = db.Column(
        db.String(120),
        nullable=True,
    )


    # =====================================================
    # SHIFT
    # =====================================================

    old_shift = db.Column(
        db.String(120),
        nullable=True,
    )


    new_shift = db.Column(
        db.String(120),
        nullable=True,
    )


    # =====================================================
    # JOB TITLE
    # =====================================================

    old_job_title = db.Column(
        db.String(120),
        nullable=True,
    )


    new_job_title = db.Column(
        db.String(120),
        nullable=True,
    )


    # =====================================================
    # STATUS
    #
    # pending
    # approved
    # rejected
    # cancelled
    # =====================================================

    status = db.Column(
        db.String(20),
        nullable=False,
        default="pending",
        index=True,
    )


    # =====================================================
    # REVIEW
    # =====================================================

    reviewed_by_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )


    reviewed_at = db.Column(
        db.DateTime(
            timezone=True
        ),
        nullable=True,
    )


    rejection_reason = db.Column(
        db.Text,
        nullable=True,
    )


    cancelled_at = db.Column(
        db.DateTime(
            timezone=True
        ),
        nullable=True,
    )


    # =====================================================
    # TIMESTAMPS
    # =====================================================

    created_at = db.Column(
        db.DateTime(
            timezone=True
        ),
        nullable=False,
        default=utc_now,
        index=True,
    )


    updated_at = db.Column(
        db.DateTime(
            timezone=True
        ),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    user = db.relationship(
        "User",
        foreign_keys=[
            user_id
        ],
    )


    requested_by = db.relationship(
        "User",
        foreign_keys=[
            requested_by_id
        ],
    )


    reviewed_by = db.relationship(
        "User",
        foreign_keys=[
            reviewed_by_id
        ],
    )


    # =====================================================
    # DATABASE CONSTRAINTS
    # =====================================================

    __table_args__ = (

        db.CheckConstraint(
            (
                "status IN "
                "('pending', "
                "'approved', "
                "'rejected', "
                "'cancelled')"
            ),
            name=(
                "ck_work_information_"
                "change_requests_status"
            ),
        ),


        # -------------------------------------------------
        # One user can only have ONE pending request.
        # -------------------------------------------------

        db.Index(
            (
                "uq_work_information_"
                "change_pending_user"
            ),
            "user_id",
            unique=True,

            sqlite_where=db.text(
                "status = 'pending'"
            ),

            postgresql_where=db.text(
                "status = 'pending'"
            ),
        ),


        # -------------------------------------------------
        # Reserve Employee ID while a request is pending.
        #
        # This prevents:
        #
        # User A requests BIKA-1001
        # User B requests BIKA-1001
        #
        # at the same time.
        # -------------------------------------------------

        db.Index(
            (
                "uq_work_information_"
                "pending_employee_id"
            ),
            "new_employee_id",
            unique=True,

            sqlite_where=db.text(
                (
                    "status = 'pending' "
                    "AND "
                    "new_employee_id IS NOT NULL"
                )
            ),

            postgresql_where=db.text(
                (
                    "status = 'pending' "
                    "AND "
                    "new_employee_id IS NOT NULL"
                )
            ),
        ),


        db.Index(
            (
                "ix_work_information_"
                "request_status_created"
            ),
            "status",
            "created_at",
        ),

    )


    # =====================================================
    # CHANGED FIELDS
    # =====================================================

    def changed_fields(
        self,
    ):
        """
        Return only fields that actually changed.

        Example:

        [
            (
                "Department",
                "Administration",
                "Management",
            )
        ]
        """

        fields = []


        comparisons = (
            (
                "Employee ID",
                self.old_employee_id,
                self.new_employee_id,
            ),

            (
                "Department",
                self.old_department,
                self.new_department,
            ),

            (
                "Shift",
                self.old_shift,
                self.new_shift,
            ),

            (
                "Job Title",
                self.old_job_title,
                self.new_job_title,
            ),
        )


        for (
            label,
            old_value,
            new_value,
        ) in comparisons:

            if (
                (old_value or "")
                !=
                (new_value or "")
            ):

                fields.append(
                    (
                        label,
                        old_value,
                        new_value,
                    )
                )


        return fields


    @property
    def is_pending(
        self,
    ):

        return (
            self.status
            ==
            "pending"
        )


# =========================================================
# NOTIFICATION
# =========================================================

class Notification(
    db.Model
):
    __tablename__ = (
        "notifications"
    )


    id = db.Column(
        db.Integer,
        primary_key=True,
    )


    # =====================================================
    # RECIPIENT
    # =====================================================

    recipient_user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )


    # =====================================================
    # ACTOR
    #
    # Example:
    # Jia Jun submits work information request.
    #
    # actor = Jia Jun
    # recipient = SuperAdmin
    # =====================================================

    actor_user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )


    # =====================================================
    # TYPE
    # =====================================================

    notification_type = db.Column(
        db.String(80),
        nullable=False,
        index=True,
    )


    # =====================================================
    # CONTENT
    # =====================================================

    title = db.Column(
        db.String(180),
        nullable=False,
    )


    message = db.Column(
        db.Text,
        nullable=False,
    )


    # =====================================================
    # CLICK DESTINATION
    # =====================================================

    link = db.Column(
        db.String(500),
        nullable=True,
    )


    # =====================================================
    # OPTIONAL STRUCTURED PAYLOAD
    # =====================================================

    payload_json = db.Column(
        db.JSON,
        nullable=True,
    )


    # =====================================================
    # READ STATE
    # =====================================================

    is_read = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        index=True,
    )


    read_at = db.Column(
        db.DateTime(
            timezone=True
        ),
        nullable=True,
    )


    # =====================================================
    # TIMESTAMP
    # =====================================================

    created_at = db.Column(
        db.DateTime(
            timezone=True
        ),
        nullable=False,
        default=utc_now,
        index=True,
    )


    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    recipient = db.relationship(
        "User",
        foreign_keys=[
            recipient_user_id
        ],
    )


    actor = db.relationship(
        "User",
        foreign_keys=[
            actor_user_id
        ],
    )


    __table_args__ = (

        db.Index(
            (
                "ix_notifications_"
                "recipient_unread_created"
            ),
            "recipient_user_id",
            "is_read",
            "created_at",
        ),

    )


    def mark_read(
        self,
    ):

        if (
            self.is_read
        ):
            return


        self.is_read = True

        self.read_at = (
            utc_now()
        )


# =========================================================
# USER NOTIFICATION PREFERENCES
# =========================================================

class UserNotificationPreference(
    db.Model
):
    __tablename__ = (
        "user_notification_preferences"
    )


    # =====================================================
    # ONE ROW PER USER
    # =====================================================

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )


    # =====================================================
    # USER-CONTROLLABLE SETTINGS
    # =====================================================

    email_notifications = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )


    in_app_alerts = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )


    # =====================================================
    # TIMESTAMPS
    # =====================================================

    created_at = db.Column(
        db.DateTime(
            timezone=True
        ),
        nullable=False,
        default=utc_now,
    )


    updated_at = db.Column(
        db.DateTime(
            timezone=True
        ),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


    user = db.relationship(
        "User",
    )