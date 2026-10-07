from __future__ import annotations

import json
import os

import os
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (
    abort,
    current_app,
    jsonify,
    render_template,
    request,
)
from flask_login import current_user, login_required
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.main import main_bp
from app.models import User, UserRole
from app.services.about_system_audit_service import (
    load_about_system_audit,
    write_about_system_audit,
)


ABOUT_SYSTEM_ROLES = {
    UserRole.ADMIN.value,
    UserRole.SUPERADMIN.value,
}

RETENTION_POLICIES = {
    "keep_all": {
        "label": "Keep all records",
        "description": "No automatic deletion",
    },
    "archive_90": {
        "label": "Archive after 90 days",
        "description": "Move old records to archive",
    },
    "delete_1y": {
        "label": "Delete after 1 year",
        "description": "Permanently delete records",
    },
}

BACKUP_TYPES = {
    "database": "Database Only",
    "full": "Full Backup",
}

DEFAULT_STATE = {
    "model": {
        "name": "Not configured",
        "version": "—",
        "status": "Not configured",
        "classes": "—",
        "accuracy": None,
        "last_updated": None,
    },
    "retention_policy": "keep_all",
    "backup": {
        "type": "database",
        "auto_enabled": True,
        "destination": "Local Storage (Default)",
        "schedule": "Weekly, Sunday 02:00",
        "last_backup_at": None,
    },
}


def about_system_required(view_function):
    """Allow Admin and SuperAdmin only."""

    @wraps(view_function)
    @login_required
    def wrapped_view(*args, **kwargs):
        if current_user.role not in ABOUT_SYSTEM_ROLES:
            abort(403)
        return view_function(*args, **kwargs)

    return wrapped_view


def superadmin_only(view_function):
    """Extra guard for high-risk About System operations."""

    @wraps(view_function)
    @login_required
    def wrapped_view(*args, **kwargs):
        if current_user.role != UserRole.SUPERADMIN.value:
            abort(403)
        return view_function(*args, **kwargs)

    return wrapped_view


def _state_path() -> Path:
    instance_dir = Path(current_app.instance_path)
    instance_dir.mkdir(parents=True, exist_ok=True)
    return instance_dir / "about_system_state.json"


def _deep_merge(base: dict, incoming: dict) -> dict:
    result = dict(base)
    for key, value in incoming.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_state() -> dict:
    path = _state_path()
    if not path.exists():
        return _deep_merge({}, DEFAULT_STATE)

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}

    return _deep_merge(DEFAULT_STATE, raw)


def _save_state(state: dict) -> None:
    path = _state_path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_audit() -> list[dict]:
    """Compatibility wrapper around the shared audit service."""
    return load_about_system_audit()


def _write_audit(
    *,
    category: str,
    action: str,
    details: str,
) -> None:
    """Compatibility wrapper around the shared audit service."""
    write_about_system_audit(
        category=category,
        action=action,
        details=details,
    )


def _database_size_bytes() -> int | None:
    try:
        bind = db.session.get_bind()
        dialect = bind.dialect.name

        if dialect == "postgresql":
            value = db.session.execute(
                text("SELECT pg_database_size(current_database())")
            ).scalar_one_or_none()
            return int(value) if value is not None else None

        if dialect == "sqlite":
            database = bind.url.database
            if database and os.path.exists(database):
                return os.path.getsize(database)

    except (SQLAlchemyError, OSError, ValueError, TypeError):
        return None

    return None


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "Unavailable"

    units = ("B", "KB", "MB", "GB", "TB")
    size = float(value)
    unit_index = 0

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"

    return f"{size:.1f} {units[unit_index]}"


def _oldest_record_label() -> str:
    try:
        value = db.session.scalar(db.select(func.min(User.created_at)))
    except SQLAlchemyError:
        value = None

    if value is None:
        return "—"

    return value.strftime("%Y-%m-%d")


def _normalise_audit(events: list[dict]) -> list[dict]:
    output = []

    for event in events:
        category = str(event.get("category") or "Config")

        # Admin can use the operational audit, but Security is intentionally
        # SuperAdmin-only even if someone manually calls this page endpoint.
        if (
            current_user.role != UserRole.SUPERADMIN.value
            and category.lower() == "security"
        ):
            continue

        raw_timestamp = event.get("timestamp")
        try:
            parsed = datetime.fromisoformat(str(raw_timestamp))
            timestamp = parsed.strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            timestamp = str(raw_timestamp or "—")

        output.append(
            {
                **event,
                "timestamp_label": timestamp,
                "role_label": str(event.get("role") or "System").title(),
            }
        )

    return output


def _page_context() -> dict:
    state = _load_state()

    if state.get("retention_policy") not in RETENTION_POLICIES:
        state["retention_policy"] = "keep_all"

    if state.get("backup", {}).get("type") not in BACKUP_TYPES:
        state.setdefault("backup", {})["type"] = "database"

    audit_events = _normalise_audit(_load_audit())
    database_size = _database_size_bytes()

    today_utc = datetime.now(timezone.utc).date()
    audit_today = 0

    for event in audit_events:
        try:
            event_date = datetime.fromisoformat(
                str(event.get("timestamp"))
            ).date()
        except (TypeError, ValueError):
            continue

        if event_date == today_utc:
            audit_today += 1

    last_backup_at = state["backup"].get("last_backup_at")
    backup_healthy = bool(last_backup_at)

    model = state["model"]
    accuracy = model.get("accuracy")
    accuracy_label = "—"
    if isinstance(accuracy, (int, float)):
        accuracy_label = f"{accuracy:.3f} ({accuracy * 100:.1f}%)"

    quota_bytes = 1024 * 1024 * 1024
    usage_percent = (
        min(100.0, (database_size / quota_bytes) * 100)
        if database_size is not None
        else 0.0
    )

    return {
        "about_state": state,
        "about_model_accuracy": accuracy_label,
        "about_retention_options": RETENTION_POLICIES,
        "about_backup_types": BACKUP_TYPES,
        "about_audit_events": audit_events[:80],
        "about_stats": {
            "database_size": _format_bytes(database_size),
            "database_size_bytes": database_size,
            "audit_today": audit_today,
            "backup_status": "Healthy" if backup_healthy else "No backup yet",
            "backup_status_key": "healthy" if backup_healthy else "pending",
            "oldest_record": _oldest_record_label(),
            "storage_usage": _format_bytes(database_size),
            "storage_quota": "1 GB",
            "storage_percent": round(usage_percent, 2),
        },
        "about_permissions": {
            "is_admin": current_user.role == UserRole.ADMIN.value,
            "is_superadmin": current_user.role == UserRole.SUPERADMIN.value,
            "can_manage_operations": current_user.role in ABOUT_SYSTEM_ROLES,
            "can_restore_backup": current_user.role == UserRole.SUPERADMIN.value,
            "can_upload_backup": current_user.role == UserRole.SUPERADMIN.value,
            "can_view_security_audit": current_user.role == UserRole.SUPERADMIN.value,
        },
    }


@main_bp.route("/about-system", methods=["GET"])
@about_system_required
def about_system():
    return render_template(
        "about_system.html",
        **_page_context(),
    )


@main_bp.route("/about-system/retention", methods=["POST"])
@about_system_required
def update_about_system_retention():
    data = request.get_json(silent=True) or {}
    policy = str(data.get("policy") or "").strip()

    if policy not in RETENTION_POLICIES:
        return jsonify(
            ok=False,
            message="Please select a valid retention policy.",
        ), 400

    state = _load_state()
    previous = state.get("retention_policy", "keep_all")
    state["retention_policy"] = policy
    _save_state(state)

    _write_audit(
        category="Config",
        action="Updated data retention policy",
        details=(
            f"{RETENTION_POLICIES.get(previous, {}).get('label', previous)} "
            f"→ {RETENTION_POLICIES[policy]['label']}"
        ),
    )

    return jsonify(
        ok=True,
        message="Retention policy saved.",
        policy=policy,
    )


@main_bp.route("/about-system/backup-settings", methods=["POST"])
@about_system_required
def update_about_system_backup_settings():
    data = request.get_json(silent=True) or {}

    backup_type = str(data.get("backup_type") or "").strip()
    auto_enabled = bool(data.get("auto_enabled"))
    schedule = str(data.get("schedule") or "").strip()

    if backup_type not in BACKUP_TYPES:
        return jsonify(
            ok=False,
            message="Please select a valid backup type.",
        ), 400

    if not schedule:
        return jsonify(
            ok=False,
            message="Backup schedule cannot be empty.",
        ), 400

    if len(schedule) > 120:
        return jsonify(
            ok=False,
            message="Backup schedule is too long.",
        ), 400

    state = _load_state()
    state["backup"]["type"] = backup_type
    state["backup"]["auto_enabled"] = auto_enabled
    state["backup"]["schedule"] = schedule
    _save_state(state)

    _write_audit(
        category="Backup",
        action="Updated backup schedule",
        details=(
            f"{BACKUP_TYPES[backup_type]}; "
            f"auto backup {'enabled' if auto_enabled else 'disabled'}; "
            f"{schedule}"
        ),
    )

    return jsonify(
        ok=True,
        message="Backup settings saved.",
    )


@main_bp.route("/about-system/security-audit", methods=["GET"])
@superadmin_only
def about_system_security_audit():
    events = [
        event
        for event in _normalise_audit(_load_audit())
        if str(event.get("category") or "").lower() == "security"
    ]

    return jsonify(
        ok=True,
        events=events,
    )
