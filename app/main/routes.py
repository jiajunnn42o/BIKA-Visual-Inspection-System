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


# BIKA-DASH-LIVE-RUNTIME-V1 — independent read-only telemetry endpoint.
@main_bp.route('/dashboard/api/live-runtime', methods=['GET'])
@login_required
def dashboard_api_live_runtime():
    from app.services.dashboard_runtime_service import current_live_runtime
    return jsonify(ok=True, camera=current_live_runtime())


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

# BIKA-COMBINED-TOTALS-V1-1 -- present a single summed Image / Video / Live dataset.
_original_bika_dashboard_builder = build_dashboard_data

def build_dashboard_data(*args, **kwargs):
    from app.services.unified_totals_service import merge_dashboard_data
    result = _original_bika_dashboard_builder(*args, **kwargs)
    return merge_dashboard_data(result, current_user.get_id(),
                                range_key=kwargs.get('range_key','all'),
                                custom_from=kwargs.get('custom_from'),
                                custom_to=kwargs.get('custom_to'))
