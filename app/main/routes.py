from flask import (
    jsonify,
    render_template,
    request,
)

from flask_login import (
    current_user,
    login_required,
)

from app.main import main_bp

from app.services.dashboard_service import (
    build_dashboard_data,
)


# =========================================================
# DASHBOARD PAGE
# =========================================================

@main_bp.route("/")
@login_required
def index():

    dashboard = build_dashboard_data(
        range_key="all"
    )

    return render_template(
        "index.html",
        user=current_user,
        dashboard=dashboard,
    )


# =========================================================
# DASHBOARD DATA API
# =========================================================

@main_bp.route(
    "/dashboard/data",
    methods=["GET"],
)
@login_required
def dashboard_data():

    dashboard = build_dashboard_data(
        range_key=request.args.get(
            "range",
            "all",
        ),
        custom_from=request.args.get(
            "from"
        ),
        custom_to=request.args.get(
            "to"
        ),
    )

    return jsonify(
        ok=True,
        dashboard=dashboard,
    )