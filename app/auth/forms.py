from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    SubmitField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    ValidationError,
)

from app.extensions import db
from app.models import User


class RegistrationForm(FlaskForm):
    first_name = StringField(
        "First Name",
        validators=[
            DataRequired(),
            Length(max=100),
        ],
    )

    last_name = StringField(
        "Last Name",
        validators=[
            DataRequired(),
            Length(max=100),
        ],
    )

    email = StringField(
        "Email",
        validators=[
            DataRequired(),
            Email(),
            Length(max=255),
        ],
    )

    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=100),
        ],
    )

    phone_number = StringField(
        "Phone Number",
        validators=[
            DataRequired(),
            Length(max=30),
        ],
    )

    job_title = StringField(
        "Job Title",
        validators=[
            DataRequired(),
            Length(max=120),
        ],
    )

    department = StringField(
        "Department",
        validators=[
            DataRequired(),
            Length(max=120),
        ],
    )

    shift = StringField(
        "Shift",
        validators=[
            DataRequired(),
            Length(max=80),
        ],
    )

    employee_id = StringField(
        "Employee ID",
        validators=[
            DataRequired(),
            Length(max=80),
        ],
    )

    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
            Length(
                min=12,
                message="Password must contain at least 12 characters.",
            ),
        ],
    )

    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(),
            EqualTo(
                "password",
                message="Passwords do not match.",
            ),
        ],
    )

    submit = SubmitField("Create Account")

    def validate_email(self, field):
        email = field.data.strip().lower()

        user = db.session.scalar(
            db.select(User).where(
                User.email == email
            )
        )

        if user:
            raise ValidationError(
                "This email address is already registered."
            )

    def validate_username(self, field):
        username = field.data.strip().lower()

        user = db.session.scalar(
            db.select(User).where(
                User.username == username
            )
        )

        if user:
            raise ValidationError(
                "This username is already in use."
            )

    def validate_phone_number(self, field):
        phone = field.data.strip()

        user = db.session.scalar(
            db.select(User).where(
                User.phone_number == phone
            )
        )

        if user:
            raise ValidationError(
                "This phone number is already registered."
            )

    def validate_employee_id(self, field):
        employee_id = field.data.strip().upper()

        user = db.session.scalar(
            db.select(User).where(
                User.employee_id == employee_id
            )
        )

        if user:
            raise ValidationError(
                "This employee ID is already registered."
            )

from wtforms import BooleanField


class LoginForm(FlaskForm):
    identifier = StringField(
        "Email, Phone Number or Username",
        validators=[
            DataRequired(),
            Length(max=255),
        ],
    )

    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
        ],
    )

    remember_me = BooleanField(
        "Remember me"
    )

    submit = SubmitField(
        "Login"
    )