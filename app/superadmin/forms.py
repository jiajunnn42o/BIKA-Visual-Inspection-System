from flask_wtf import FlaskForm

from wtforms import (
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)

from wtforms.validators import (
    DataRequired,
    Email,
    Length,
)


class RegistrationReviewForm(FlaskForm):

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

    email = StringField(
        "Email",
        validators=[
            DataRequired(),
            Email(),
            Length(max=255),
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

    role = SelectField(
        "Access Role",
        choices=[
            ("user", "User"),
            ("admin", "Admin"),
            ("superadmin", "SuperAdmin"),
        ],
        validators=[
            DataRequired(),
        ],
    )

    rejection_reason = TextAreaField(
        "Rejection Reason",
        validators=[
            Length(max=1000),
        ],
    )

    save_changes = SubmitField(
        "Save Changes"
    )

    approve = SubmitField(
        "Approve Registration"
    )

    reject = SubmitField(
        "Reject Registration"
    )