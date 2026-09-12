from enum import Enum

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


class UserStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    DISABLED = "disabled"
    LOCKED = "locked"
    REJECTED = "rejected"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    # Basic identity
    id = db.Column(
        db.Integer,
        primary_key=True
    )

    first_name = db.Column(
        db.String(100),
        nullable=False
    )

    last_name = db.Column(
        db.String(100),
        nullable=False
    )

    username = db.Column(
        db.String(100),
        nullable=False,
        unique=True,
        index=True
    )

    email = db.Column(
        db.String(255),
        nullable=False,
        unique=True,
        index=True
    )

    email_verified_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    phone_number = db.Column(
        db.String(30),
        nullable=False,
        unique=True,
        index=True
    )

    # Password is never stored directly.
    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    # Employment information entered during registration.
    job_title = db.Column(
        db.String(120),
        nullable=False
    )

    department = db.Column(
        db.String(120),
        nullable=False
    )

    shift = db.Column(
        db.String(80),
        nullable=False
    )

    employee_id = db.Column(
        db.String(80),
        nullable=False,
        unique=True,
        index=True
    )

    # Only store the image path / filename, not the image itself.
    profile_photo = db.Column(
        db.String(500),
        nullable=True
    )

    # Role is controlled by SuperAdmin.
    role = db.Column(
        db.String(20),
        nullable=False,
        default=UserRole.USER.value,
        server_default=UserRole.USER.value,
        index=True
    )

    # New public registrations always begin as pending.
    status = db.Column(
        db.String(20),
        nullable=False,
        default=UserStatus.PENDING.value,
        server_default=UserStatus.PENDING.value,
        index=True
    )

    # Login security
    failed_login_attempts = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0"
    )

    locked_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    password_changed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    # Registration approval information
    approved_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    approved_by_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="SET NULL"
        ),
        nullable=True
    )

    rejected_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    rejected_by_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="SET NULL"
        ),
        nullable=True
    )

    rejection_reason = db.Column(
        db.Text,
        nullable=True
    )

    # Activity / audit timestamps
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now()
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now()
    )

    last_login_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    last_active_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    __table_args__ = (
        db.CheckConstraint(
            "role IN ('user', 'admin', 'superadmin')",
            name="ck_users_role"
        ),
        db.CheckConstraint(
            """
            status IN (
                'pending',
                'active',
                'disabled',
                'locked',
                'rejected'
            )
            """,
            name="ck_users_status"
        ),
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(
            self.password_hash,
            password
        )

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_active(self):
        """
        Flask-Login only treats approved, active accounts
        as valid active users.
        """
        return self.status == UserStatus.ACTIVE.value

    @property
    def is_superadmin(self):
        return self.role == UserRole.SUPERADMIN.value

    @property
    def is_admin(self):
        return self.role in {
            UserRole.ADMIN.value,
            UserRole.SUPERADMIN.value,
        }

    @property
    def is_email_verified(self):
        return self.email_verified_at is not None

    def __repr__(self):
        return f"<User {self.username}>"