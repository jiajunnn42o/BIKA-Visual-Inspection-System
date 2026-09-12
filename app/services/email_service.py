from flask import current_app
from flask_mail import Message

from app.extensions import mail


FIELD_LABELS = {
    "first_name": "First Name",
    "last_name": "Last Name",
    "username": "Username",
    "email": "Email",
    "phone_number": "Phone Number",
    "job_title": "Job Title",
    "department": "Department",
    "shift": "Shift",
    "employee_id": "Employee ID",
    "role": "Access Role",
}


def _send_email(
    subject,
    recipients,
    body,
):
    recipients = list(
        dict.fromkeys(
            email
            for email in recipients
            if email
        )
    )

    if not recipients:
        return False

    message = Message(
        subject=subject,
        recipients=recipients,
        body=body,
        sender=current_app.config[
            "MAIL_DEFAULT_SENDER"
        ],
    )

    mail.send(message)

    return True


def _format_changes(changes):
    if not changes:
        return ""

    lines = []

    for field_name, values in changes.items():
        label = FIELD_LABELS.get(
            field_name,
            field_name.replace(
                "_",
                " ",
            ).title(),
        )

        old_value = (
            values.get("old")
            or "Not provided"
        )

        new_value = (
            values.get("new")
            or "Not provided"
        )

        lines.extend([
            label,
            f"Previous: {old_value}",
            f"Updated: {new_value}",
            "",
        ])

    return "\n".join(lines)


def send_registration_updated_email(
    user,
    changes,
    original_email=None,
):
    if not changes:
        return False

    body = f"""Hello {user.first_name},

Your BIKA Visual Inspection System registration information has been updated by a SuperAdmin.

The following information was changed:

{_format_changes(changes)}

Your registration is still pending approval.

If you did not expect these changes, please contact the system administrator.

BIKA Visual Inspection System
"""

    recipients = [
        user.email,
    ]

    # If the SuperAdmin changed the email itself,
    # notify both old and new addresses.
    if (
        original_email
        and original_email != user.email
    ):
        recipients.append(
            original_email
        )

    return _send_email(
        subject=(
            "BIKA Registration Information Updated"
        ),
        recipients=recipients,
        body=body,
    )


def send_registration_approved_email(
    user,
    changes=None,
    original_email=None,
):
    change_section = ""

    if changes:
        change_section = f"""
The following registration information was also updated during review:

{_format_changes(changes)}
"""

    body = f"""Hello {user.first_name},

Your registration for the BIKA Visual Inspection System has been approved.

Your account is now active and you may sign in using your registered credentials.

Assigned role:
{user.role}
{change_section}
If you did not expect this approval or any of the changes above, please contact the system administrator.

BIKA Visual Inspection System
"""

    recipients = [
        user.email,
    ]

    if (
        original_email
        and original_email != user.email
    ):
        recipients.append(
            original_email
        )

    return _send_email(
        subject=(
            "BIKA Account Approved"
        ),
        recipients=recipients,
        body=body,
    )


def send_registration_rejected_email(
    user,
    rejection_reason,
    changes=None,
    original_email=None,
):
    change_section = ""

    if changes:
        change_section = f"""
The following information was updated during review:

{_format_changes(changes)}
"""

    body = f"""Hello {user.first_name},

Your registration for the BIKA Visual Inspection System was not approved.

Reason:
{rejection_reason}
{change_section}
If you believe this decision was made in error, please contact the system administrator.

BIKA Visual Inspection System
"""

    recipients = [
        user.email,
    ]

    if (
        original_email
        and original_email != user.email
    ):
        recipients.append(
            original_email
        )

    return _send_email(
        subject=(
            "BIKA Registration Not Approved"
        ),
        recipients=recipients,
        body=body,
    )

def send_new_registration_to_superadmins(
    applicant,
    superadmins,
):
    """
    Notify every active SuperAdmin when a new
    user registration is waiting for review.

    Each SuperAdmin receives an individual email
    so their email addresses are not exposed
    to other administrators.
    """

    result = {
        "sent": 0,
        "failed": 0,
    }

    if not superadmins:
        current_app.logger.warning(
            "A new registration was created, but no active SuperAdmin exists."
        )

        return result

    submitted_at = (
        applicant.created_at.strftime(
            "%d %b %Y, %I:%M %p"
        )
        if applicant.created_at
        else "Just now"
    )

    for superadmin in superadmins:

        body = f"""Hello {superadmin.first_name},

A new user registration is waiting for your review in the BIKA Visual Inspection System.

Applicant:
{applicant.full_name}

Username:
{applicant.username}

Employee ID:
{applicant.employee_id}

Department:
{applicant.department}

Job Title:
{applicant.job_title}

Shift:
{applicant.shift}

Submitted:
{submitted_at}

Please sign in to the BIKA Visual Inspection System to review the registration.

BIKA Visual Inspection System
"""

        try:

            _send_email(
                subject=(
                    "New BIKA Registration Awaiting Approval"
                ),
                recipients=[
                    superadmin.email
                ],
                body=body,
            )

        except Exception:

            result["failed"] += 1

            current_app.logger.exception(
                (
                    "Unable to notify SuperAdmin "
                    f"{superadmin.id} about new registration "
                    f"{applicant.id}."
                )
            )

        else:

            result["sent"] += 1

    return result