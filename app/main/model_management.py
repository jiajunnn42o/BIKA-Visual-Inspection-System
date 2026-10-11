from __future__ import annotations

from functools import wraps

from flask import (
    abort,
    current_app,
    jsonify,
    request,
)

from flask_login import (
    current_user,
    login_required,
)

from app.main import main_bp
from app.models import UserRole

from app.services.about_system_audit_service import (
    write_about_system_audit,
)

from app.services.model_registry_service import (
    DEFAULT_MODEL_NAME,
    MODEL_STAGE_OPTIONS,
    ModelRegistryError,
    generate_next_version,
    install_uploaded_model,
    live_model_context,
    model_info,
    resolve_active_version,
    set_active_version,
    synchronise_runtime_model,
)


MODEL_MANAGEMENT_ROLES = {
    UserRole.ADMIN.value,
    UserRole.SUPERADMIN.value,
}


def model_management_required(
    view_function,
):
    @wraps(view_function)
    @login_required
    def wrapped(
        *args,
        **kwargs,
    ):
        if (
            current_user.role
            not in
            MODEL_MANAGEMENT_ROLES
        ):
            abort(403)

        return view_function(
            *args,
            **kwargs,
        )

    return wrapped


@main_bp.before_app_request
def synchronise_active_model_before_request():
    try:
        synchronise_runtime_model()

    except Exception:
        current_app.logger.exception(
            "Unable to synchronise active model version."
        )


@main_bp.app_context_processor
def inject_model_management_context():
    try:
        return live_model_context()

    except Exception:
        current_app.logger.exception(
            "Unable to build model-management template context."
        )

        return {
            "live_model": {
                "name":
                    "Not configured",
                "version":
                    "—",
                "status":
                    "Not configured",
                "stage":
                    "none",
                "stage_label":
                    "—",
                "release_date":
                    "—",
                "revision":
                    None,
                "description":
                    "",
                "uploaded_by":
                    None,
                "classes":
                    "—",
                "class_names":
                    [],
                "performance":
                    "—",
                "last_updated":
                    "—",
                "is_active":
                    False,
                "complete":
                    False,
            },
            "model_versions":
                [],
            "model_stage_options":
                MODEL_STAGE_OPTIONS,
            "default_model_name":
                DEFAULT_MODEL_NAME,
        }


def _inspection_is_active() -> bool:
    try:
        from app.main.inspection_routes import (
            has_active_inspection_jobs,
        )

        return has_active_inspection_jobs()

    except Exception:
        return False


def _reset_inspection_runtime() -> None:
    from app.services.inspection_pipeline_service import (
        reset_inspection_model_context,
    )

    reset_inspection_model_context()


def _current_user_display_name() -> str:
    for attribute in (
        "full_name",
        "name",
        "username",
        "email",
    ):
        value = getattr(
            current_user,
            attribute,
            None,
        )

        if value:
            return str(
                value
            ).strip()

    return str(
        current_user.get_id()
    )


@main_bp.route(
    "/about-system/model/next-version",
    methods=["GET"],
)
@model_management_required
def preview_model_version():
    release_date = str(
        request.args.get(
            "release_date"
        )
        or
        ""
    ).strip()

    try:
        version = generate_next_version(
            release_date
        )

    except ModelRegistryError as exc:
        return jsonify(
            ok=False,
            message=str(exc),
        ), 400

    return jsonify(
        ok=True,
        version=version,
    )


@main_bp.route(
    "/about-system/model/switch",
    methods=["POST"],
)
@model_management_required
def switch_model_version():
    data = (
        request.get_json(
            silent=True
        )
        or
        {}
    )

    version = str(
        data.get("version")
        or
        ""
    ).strip()

    if not version:
        return jsonify(
            ok=False,
            message=(
                "Please select a model version."
            ),
        ), 400

    current_version = (
        resolve_active_version()
    )

    if current_version == version:
        return jsonify(
            ok=True,
            message=(
                f"{version} is already active."
            ),
            model=(
                model_info(
                    version,
                    active_version=
                        version,
                )
            ),
        )

    if _inspection_is_active():
        return jsonify(
            ok=False,
            message=(
                "An inspection is currently running. "
                "Wait for it to finish or cancel it before switching models."
            ),
        ), 409

    try:
        _reset_inspection_runtime()

        set_active_version(
            version
        )

    except ModelRegistryError as exc:
        return jsonify(
            ok=False,
            message=str(exc),
        ), 400

    except Exception as exc:
        return jsonify(
            ok=False,
            message=str(exc),
        ), 409

    try:
        write_about_system_audit(
            category="Config",
            action="Switched active model version",
            details=(
                f"{current_version or 'Not configured'} "
                f"→ {version}"
            ),
        )

    except Exception:
        current_app.logger.exception(
            "Unable to write model-switch audit event."
        )

    return jsonify(
        ok=True,
        message=(
            f"Active model switched to {version}."
        ),
        model=(
            model_info(
                version,
                active_version=
                    version,
            )
        ),
    )


@main_bp.route(
    "/about-system/model/upload",
    methods=["POST"],
)
@model_management_required
def upload_model_version():
    model_name = str(
        request.form.get("model_name")
        or
        ""
    ).strip()

    release_date = str(
        request.form.get("release_date")
        or
        ""
    ).strip()

    stage = str(
        request.form.get("stage")
        or
        ""
    ).strip()

    description = str(
        request.form.get("description")
        or
        ""
    ).strip()

    uploaded = request.files.get(
        "package"
    )

    if (
        uploaded is None
        or
        not uploaded.filename
    ):
        return jsonify(
            ok=False,
            message=(
                "Please choose a model package ZIP."
            ),
        ), 400

    if (
        not uploaded.filename
        .lower()
        .endswith(".zip")
    ):
        return jsonify(
            ok=False,
            message=(
                "Model package must be a ZIP file."
            ),
        ), 400

    try:
        installed = install_uploaded_model(
            model_name=
                model_name,
            release_date=
                release_date,
            stage=
                stage,
            description=
                description,
            uploaded_by=
                _current_user_display_name(),
            uploaded_file=
                uploaded,
        )

    except FileExistsError as exc:
        return jsonify(
            ok=False,
            message=str(exc),
        ), 409

    except ModelRegistryError as exc:
        return jsonify(
            ok=False,
            message=str(exc),
        ), 400

    except Exception:
        current_app.logger.exception(
            "Unable to install uploaded model package."
        )

        return jsonify(
            ok=False,
            message=(
                "The model package could not be installed."
            ),
        ), 500

    try:
        write_about_system_audit(
            category="Config",
            action="Uploaded model package",
            details=(
                f"{installed['name']} · "
                f"{installed['version']} · "
                f"{installed['stage_label']} · "
                f"{installed['classes']} classes"
            ),
        )

    except Exception:
        current_app.logger.exception(
            "Unable to write model-upload audit event."
        )

    return jsonify(
        ok=True,
        message=(
            f"{installed['version']} uploaded successfully. "
            "Use Switch Version to activate it."
        ),
        model=installed,
    ), 201
