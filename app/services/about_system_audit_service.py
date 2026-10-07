from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, request
from flask_login import current_user


def _audit_path() -> Path:
    """Return the shared About System audit JSON path."""
    instance_dir = Path(current_app.instance_path)
    instance_dir.mkdir(parents=True, exist_ok=True)
    return instance_dir / "about_system_audit.json"


def load_about_system_audit() -> list[dict]:
    """Load audit events from the shared About System audit store."""
    path = _audit_path()

    if not path.exists():
        return []

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return []

    return (
        data
        if isinstance(
            data,
            list,
        )
        else []
    )


def write_about_system_audit(
    *,
    category: str,
    action: str,
    details: str,
) -> None:
    """
    Append one event to the shared About System audit store.

    The current authenticated user is recorded as the actor.
    Passwords and password hashes must never be passed in details.
    """
    events = load_about_system_audit()
    now = datetime.now(timezone.utc)

    forwarded_for = request.headers.get(
        "X-Forwarded-For",
        "",
    )

    ip_address = (
        forwarded_for.split(",")[0].strip()
        if forwarded_for
        else (
            request.remote_addr
            or
            "—"
        )
    )

    actor_name = (
        getattr(
            current_user,
            "full_name",
            None,
        )
        or
        getattr(
            current_user,
            "email",
            None,
        )
        or
        "System"
    )

    actor_role = (
        getattr(
            current_user,
            "role",
            None,
        )
        or
        "system"
    )

    events.insert(
        0,
        {
            "timestamp":
                now.isoformat(),

            "user":
                actor_name,

            "role":
                actor_role,

            "action":
                str(
                    action
                    or
                    ""
                ).strip(),

            "category":
                str(
                    category
                    or
                    "Config"
                ).strip(),

            "details":
                str(
                    details
                    or
                    ""
                ).strip(),

            "ip_address":
                ip_address,
        },
    )

    # Keep the same bounded history used by About System.
    events = events[:500]

    path = _audit_path()
    temporary = path.with_suffix(
        ".tmp"
    )

    temporary.write_text(
        json.dumps(
            events,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temporary.replace(
        path
    )
