from datetime import datetime, timezone

import click
from flask.cli import with_appcontext
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import User, UserRole, UserStatus


@click.command("create-superadmin")
@with_appcontext
def create_superadmin():
    """
    Create the initial SuperAdmin account securely.

    This command is intended for the first system setup.
    The password is entered securely and is never stored as plain text.
    """

    click.echo("\nCreate Initial BIKA SuperAdmin\n")

    first_name = click.prompt("First name").strip()
    last_name = click.prompt("Last name").strip()

    username = click.prompt("Username").strip().lower()
    email = click.prompt("Email").strip().lower()
    phone_number = click.prompt("Phone number").strip()

    job_title = click.prompt(
        "Job title",
        default="System Owner"
    ).strip()

    department = click.prompt(
        "Department",
        default="Administration"
    ).strip()

    shift = click.prompt(
        "Shift",
        default="N/A"
    ).strip()

    employee_id = click.prompt(
        "Employee ID",
        default="BIKA-SA-0001"
    ).strip().upper()

    password = click.prompt(
        "Password",
        hide_input=True,
        confirmation_prompt=True
    )

    if len(password) < 12:
        raise click.ClickException(
            "Password must contain at least 12 characters."
        )

    if db.session.scalar(
        db.select(User).where(User.username == username)
    ):
        raise click.ClickException(
            "This username already exists."
        )

    if db.session.scalar(
        db.select(User).where(User.email == email)
    ):
        raise click.ClickException(
            "This email already exists."
        )

    if db.session.scalar(
        db.select(User).where(
            User.phone_number == phone_number
        )
    ):
        raise click.ClickException(
            "This phone number already exists."
        )

    if db.session.scalar(
        db.select(User).where(
            User.employee_id == employee_id
        )
    ):
        raise click.ClickException(
            "This employee ID already exists."
        )

    user = User(
        first_name=first_name,
        last_name=last_name,
        username=username,
        email=email,
        phone_number=phone_number,
        job_title=job_title,
        department=department,
        shift=shift,
        employee_id=employee_id,

        role=UserRole.SUPERADMIN.value,
        status=UserStatus.ACTIVE.value,

        approved_at=datetime.now(timezone.utc)
    )

    user.set_password(password)

    try:
        db.session.add(user)
        db.session.commit()

    except SQLAlchemyError as exc:
        db.session.rollback()

        raise click.ClickException(
            "Unable to create the SuperAdmin account."
        ) from exc

    click.echo("")
    click.secho(
        "SuperAdmin created successfully.",
        fg="green"
    )

    click.echo(f"Username: {user.username}")
    click.echo(f"Email: {user.email}")
    click.echo(f"Role: {user.role}")
    click.echo(f"Status: {user.status}")