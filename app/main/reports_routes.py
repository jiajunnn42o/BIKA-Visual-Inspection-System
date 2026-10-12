from flask import (
    render_template,
)

from flask_login import (
    current_user,
    login_required,
)

from app.main import main_bp

from app.services.reports_service import (
    build_reports_data,
)


@main_bp.route(
    "/reports",
    methods=[
        "GET",
    ],
)
@login_required
def reports():

    reports_data = (
        build_reports_data()
    )

    return render_template(
        "reports.html",
        user=current_user,
        reports_data=reports_data,
    )
