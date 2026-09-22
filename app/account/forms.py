from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, EqualTo, Length, ValidationError

from app.extensions import db
from app.models import User


class PersonalInformationForm(FlaskForm):
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

    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=100),
        ],
    )

    def __init__(
        self,
        *args,
        current_user_id=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.current_user_id = current_user_id

    def validate_username(self, field):
        username = field.data.strip().lower()

        query = db.select(User.id).where(
            db.func.lower(User.username) == username
        )

        if self.current_user_id is not None:
            query = query.where(
                User.id != self.current_user_id
            )

        existing_id = db.session.scalar(
            query.limit(1)
        )

        if existing_id is not None:
            raise ValidationError(
                "This username is already in use."
            )


class PasswordChangeForm(FlaskForm):
    current_password = PasswordField(
        "Current Password",
        validators=[
            DataRequired(),
        ],
    )

    new_password = PasswordField(
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
        "Confirm Password",
        validators=[
            DataRequired(),
            EqualTo(
                "new_password",
                message="Passwords do not match.",
            ),
        ],
    )
