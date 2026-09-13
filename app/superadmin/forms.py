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
    Optional,
)


# =========================================================
# JOB TITLE OPTIONS
# =========================================================

JOB_TITLE_CHOICES = [
    (
        "",
        "Select Job Title",
    ),

    (
        "Production Operator",
        "Production Operator",
    ),

    (
        "Quality Inspector",
        "Quality Inspector",
    ),

    (
        "Quality Control Executive",
        "Quality Control Executive",
    ),

    (
        "Quality Assurance Executive",
        "Quality Assurance Executive",
    ),

    (
        "Production Supervisor",
        "Production Supervisor",
    ),

    (
        "Maintenance Technician",
        "Maintenance Technician",
    ),

    (
        "Engineer",
        "Engineer",
    ),

    (
        "Warehouse Staff",
        "Warehouse Staff",
    ),

    (
        "Administrative Staff",
        "Administrative Staff",
    ),

    (
        "Manager",
        "Manager",
    ),
]


# =========================================================
# DEPARTMENT OPTIONS
# =========================================================

DEPARTMENT_CHOICES = [
    (
        "",
        "Select Department",
    ),

    (
        "Production",
        "Production",
    ),

    (
        "Quality Assurance",
        "Quality Assurance",
    ),

    (
        "Quality Control",
        "Quality Control",
    ),

    (
        "Engineering",
        "Engineering",
    ),

    (
        "Maintenance",
        "Maintenance",
    ),

    (
        "Warehouse & Logistics",
        "Warehouse & Logistics",
    ),

    (
        "Administration",
        "Administration",
    ),

    (
        "Management",
        "Management",
    ),
]


# =========================================================
# SHIFT OPTIONS
# =========================================================

SHIFT_CHOICES = [
    (
        "",
        "Select Shift",
    ),

    (
        "Day Shift",
        "Day Shift",
    ),

    (
        "Evening Shift",
        "Evening Shift",
    ),

    (
        "Night Shift",
        "Night Shift",
    ),

    (
        "Rotating Shift",
        "Rotating Shift",
    ),

    (
        "Office Hours",
        "Office Hours",
    ),
]


# =========================================================
# ACCESS ROLE OPTIONS
# =========================================================

ROLE_CHOICES = [
    (
        "user",
        "User",
    ),

    (
        "admin",
        "Admin",
    ),

    (
        "superadmin",
        "SuperAdmin",
    ),
]


# =========================================================
# REVIEW REGISTRATION FORM
# =========================================================

class ReviewRegistrationForm(
    FlaskForm
):
    """
    Used by the SuperAdmin when reviewing
    a pending registration.

    Applicant identity fields can be corrected.

    Employment information and access role
    are assigned by the SuperAdmin.
    """

    first_name = StringField(
        "First Name",
        validators=[
            DataRequired(),
            Length(
                min=1,
                max=80,
            ),
        ],
    )

    last_name = StringField(
        "Last Name",
        validators=[
            DataRequired(),
            Length(
                min=1,
                max=80,
            ),
        ],
    )

    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(
                min=3,
                max=80,
            ),
        ],
    )

    email = StringField(
        "Email",
        validators=[
            DataRequired(),
            Email(),
            Length(
                max=255,
            ),
        ],
    )

    phone_number = StringField(
        "Phone Number",
        validators=[
            DataRequired(),
            Length(
                max=30,
            ),
        ],
    )

    employee_id = StringField(
        "Employee ID",
        validators=[
            DataRequired(),
            Length(
                max=80,
            ),
        ],
    )


    # =====================================================
    # EMPLOYMENT ASSIGNMENT
    #
    # Optional during Save Changes.
    # Required later during Approve Registration.
    # =====================================================

    job_title = SelectField(
        "Job Title",
        choices=JOB_TITLE_CHOICES,
        validators=[
            Optional(),
        ],
    )

    department = SelectField(
        "Department",
        choices=DEPARTMENT_CHOICES,
        validators=[
            Optional(),
        ],
    )

    shift = SelectField(
        "Shift",
        choices=SHIFT_CHOICES,
        validators=[
            Optional(),
        ],
    )


    # =====================================================
    # ACCESS CONTROL
    # =====================================================

    role = SelectField(
        "Access Role",
        choices=ROLE_CHOICES,
        validators=[
            DataRequired(),
        ],
    )


    submit = SubmitField(
        "Save Changes"
    )


# =========================================================
# APPROVE FORM
# =========================================================

class ApproveRegistrationForm(
    FlaskForm
):
    """
    Separate CSRF-protected form
    for registration approval.
    """

    submit = SubmitField(
        "Approve Registration"
    )


# =========================================================
# REJECT FORM
# =========================================================

class RejectRegistrationForm(
    FlaskForm
):
    """
    SuperAdmin must provide a reason
    when rejecting an application.
    """

    reason = TextAreaField(
        "Rejection Reason",
        validators=[
            DataRequired(
                message=(
                    "A reason is required "
                    "when rejecting a registration."
                )
            ),

            Length(
                min=3,
                max=1000,
            ),
        ],
    )

    submit = SubmitField(
        "Reject Registration"
    )