from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Regexp,
    ValidationError,
)

from app.extensions import db
from app.models import (
    User,
    UserStatus,
)

from app.utils.phone import (
    InvalidPhoneNumberError,
    normalize_malaysian_mobile,
)

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

    def _rejected_email_owner(self):
        """
        Return the rejected account that currently owns
        the email entered in this registration form.

        A rejected applicant may submit a fresh
        registration using the same account row.
        """

        email = (
            str(
                self.email.data
                or
                ""
            )
            .strip()
            .lower()
        )

        if not email:
            return None

        return db.session.scalar(
            db.select(
                User
            )
            .where(
                db.func.lower(
                    User.email
                )
                ==
                email,

                User.status
                ==
                UserStatus.REJECTED.value,
            )
            .limit(1)
        )

    def _belongs_to_rejected_owner(
        self,
        user,
    ):
        """
        True only when the conflicting value belongs
        to the same rejected account identified by
        the email currently entered in the form.
        """

        if user is None:
            return False

        rejected_owner = (
            self._rejected_email_owner()
        )

        return (
            rejected_owner is not None
            and
            rejected_owner.id
            ==
            user.id
        )

    def validate_email(self, field):
        email = (
            field.data
            .strip()
            .lower()
        )

        user = db.session.scalar(
            db.select(
                User
            )
            .where(
                db.func.lower(
                    User.email
                )
                ==
                email
            )
            .limit(1)
        )

        if (
            user
            and
            user.status
            !=
            UserStatus.REJECTED.value
        ):

            raise ValidationError(
                "This email address is already registered."
            )

    def validate_username(self, field):
        username = (
            field.data
            .strip()
            .lower()
        )

        user = db.session.scalar(
            db.select(
                User
            )
            .where(
                db.func.lower(
                    User.username
                )
                ==
                username
            )
            .limit(1)
        )

        if (
            user
            and
            not self._belongs_to_rejected_owner(
                user
            )
        ):

            raise ValidationError(
                "This username is already in use."
            )

    def validate_phone_number(
        self,
        field,
    ):
        try:

            normalized_phone = (
                normalize_malaysian_mobile(
                    field.data
                )
            )

        except InvalidPhoneNumberError as exc:

            raise ValidationError(
                str(exc)
            )

        user = db.session.scalar(
            db.select(
                User
            )
            .where(
                User.phone_number
                ==
                normalized_phone
            )
            .limit(1)
        )

        if (
            user
            and
            not self._belongs_to_rejected_owner(
                user
            )
        ):

            raise ValidationError(
                "This phone number is already registered."
            )

    def validate_employee_id(
        self,
        field,
    ):
        employee_id = (
            field.data
            .strip()
            .upper()
        )

        user = db.session.scalar(
            db.select(
                User
            )
            .where(
                db.func.upper(
                    User.employee_id
                )
                ==
                employee_id
            )
            .limit(1)
        )

        if (
            user
            and
            not self._belongs_to_rejected_owner(
                user
            )
        ):

            raise ValidationError(
                "This employee ID is already registered."
            )


class LoginForm(FlaskForm):
    identifier = StringField(
        "Email, Username or Phone Number",
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

class EmailVerificationForm(FlaskForm):

    code = StringField(
        "Verification Code",
        validators=[
            DataRequired(),
            Regexp(
                r"^\d{6}$",
                message=(
                    "Please enter the "
                    "6-digit verification code."
                ),
            ),
        ],
    )

    submit = SubmitField(
        "Verify Email"
    )


class ResendVerificationForm(FlaskForm):

    submit = SubmitField(
        "Resend Code"
    )

class ForgotPasswordForm(FlaskForm):

    email = StringField(
        "Email",
        validators=[
            DataRequired(),
            Email(),
            Length(max=255),
        ],
    )

    submit = SubmitField(
        "Continue"
    )


class PasswordResetVerificationForm(FlaskForm):

    code = StringField(
        "Verification Code",
        validators=[
            DataRequired(),
            Regexp(
                r"^\d{6}$",
                message=(
                    "Please enter the "
                    "6-digit verification code."
                ),
            ),
        ],
    )

    submit = SubmitField(
        "Verify Code"
    )


class ResetPasswordForm(FlaskForm):

    password = PasswordField(
        "New Password",
        validators=[
            DataRequired(),
            Length(
                min=12,
                message=(
                    "Password must be at least "
                    "12 characters long."
                ),
            ),
        ],
    )

    confirm_password = PasswordField(
        "Confirm New Password",
        validators=[
            DataRequired(),
            EqualTo(
                "password",
                message=(
                    "Passwords must match."
                ),
            ),
        ],
    )

    submit = SubmitField(
        "Reset Password"
    )

class PhoneVerificationForm(
    FlaskForm
):
    code = StringField(
        "Verification Code",
        validators=[
            DataRequired(),
            Regexp(
                r"^\d{6}$",
                message=(
                    "Please enter the "
                    "6-digit verification code."
                ),
            ),
        ],
    )

    submit = SubmitField(
        "Verify Phone"
    )