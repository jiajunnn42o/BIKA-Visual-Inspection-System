from flask import abort, redirect, send_file
from flask_login import login_required

from app.main import main_bp
from app.services.storage_service import (
    generate_presigned_get_url,
    local_path_for_serving,
    normalize_object_key,
    storage_backend,
)


@main_bp.route(
    "/inspection-media/<path:object_key>",
    methods=["GET"],
)
@login_required
def inspection_media(object_key):
    key = normalize_object_key(object_key)

    if not key.startswith("inspections/"):
        abort(404)

    if storage_backend() == "b2":
        return redirect(
            generate_presigned_get_url(
                key,
                expires_seconds=900,
            ),
            code=302,
        )

    try:
        path = local_path_for_serving(key)
    except FileNotFoundError:
        abort(404)

    return send_file(
        path,
        conditional=True,
        max_age=300,
    )
