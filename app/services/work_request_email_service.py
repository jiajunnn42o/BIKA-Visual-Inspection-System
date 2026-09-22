from flask import current_app
from flask_mail import Message

from app.extensions import mail


# =========================================================
# INTERNAL SEND
# =========================================================

def _send_email(
    *,
    subject,
    recipients,
    body,
):
    sender = current_app.config.get(
        "MAIL_DEFAULT_SENDER"
    )

    kwargs = {
        "subject":
            subject,

        "recipients":
            recipients,

        "body":
            body,
    }

    if sender:
        kwargs["sender"] = sender

    message = Message(
        **kwargs
    )

    mail.send(
        message
    )


# =========================================================
# WORK REQUEST → SUPERADMIN
# =========================================================

def send_work_information_request_email(
    *,
    recipient,
    requester,
    work_request,
):
    """
    Sent when a user submits Work Information changes.
    """

    changes = []

    for (
        label,
        old_value,
        new_value,
    ) in work_request.changed_fields():

        old_text = (
            old_value
            if old_value
            else "—"
        )

        new_text = (
            new_value
            if new_value
            else "—"
        )

        changes.append(
            f"{label}: "
            f"{old_text} → {new_text}"
        )

    changes_text = "\n".join(
        changes
    )

    body = (
        f"Hello {recipient.first_name},\n\n"

        f"{requester.full_name} has submitted "
        f"a request to update their work "
        f"information.\n\n"

        f"Requested changes:\n"
        f"{changes_text}\n\n"

        f"Employee ID: "
        f"{requester.employee_id or '—'}\n"

        f"Username: "
        f"{requester.username}\n\n"

        f"Please sign in to the BIKA Visual "
        f"Inspection System to review this "
        f"request.\n\n"

        f"BIKA Visual Inspection System"
    )

    _send_email(
        subject=(
            "New Work Information Change Request"
        ),
        recipients=[
            recipient.email
        ],
        body=body,
    )


# =========================================================
# RESULT → APPLICANT
# Used in the next stage.
# =========================================================

def send_work_information_result_email(
    *,
    recipient,
    work_request,
):
    if (
        work_request.status
        ==
        "approved"
    ):
        subject = (
            "Work Information Request Approved"
        )

        result_text = (
            "Your work information change "
            "request has been approved."
        )

    elif (
        work_request.status
        ==
        "rejected"
    ):
        subject = (
            "Work Information Request Rejected"
        )

        result_text = (
            "Your work information change "
            "request has been rejected."
        )

        if work_request.rejection_reason:
            result_text += (
                "\n\nReason:\n"
                +
                work_request.rejection_reason
            )

    else:
        return

    body = (
        f"Hello {recipient.first_name},\n\n"
        f"{result_text}\n\n"
        f"BIKA Visual Inspection System"
    )

    _send_email(
        subject=subject,
        recipients=[
            recipient.email
        ],
        body=body,
    )