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

    # BIKA-UNIFIED-VIEWS-V1: append user-owned Live session rows to the same table.
    from flask import current_app
    from app.services.unified_live_reports import build_live_report_rows
    import sqlite3
    try:
        live_rows = build_live_report_rows(current_app.instance_path, current_user.get_id())
        reports_data['batches'] = sorted(
            [*reports_data.get('batches', []), *live_rows],
            key=lambda row: str(row.get('date_display') or ''), reverse=True,
        )
        reports_data['batch_count'] = len(reports_data['batches'])
        fields = reports_data.get('export_fields', [])
        if not any(field.get('key') == 'source_type' for field in fields):
            fields.insert(0, {'key': 'source_type', 'label': 'Inspection Source'})
        if not any(field.get('key') == 'is_provisional' for field in fields):
            fields.append({'key': 'is_provisional', 'label': 'Provisional Live Observation'})
    except (sqlite3.Error, OSError, ValueError) as exc:
        current_app.logger.warning('Live reports temporarily unavailable: %s', exc)

    return render_template(
        "reports.html",
        user=current_user,
        reports_data=reports_data,
    )


# BIKA-LIVE-SESSION-HISTORY-V1 — separate from judged image/video reports.
@main_bp.get('/reports/api/live-sessions')
@login_required
def reports_live_sessions_api():
    from flask import current_app, jsonify
    from app.services.live_session_history import list_sessions
    rows = list_sessions(current_app.instance_path, current_user.get_id())
    response = jsonify(ok=True, sessions=rows, note='Provisional defect observations; not verified unique products')
    response.headers['Cache-Control'] = 'private, no-store'
    return response


# BIKA_LIVE_RECORDING_V1: authenticated owner-only, safe segmented MP4 playback.
@main_bp.get('/reports/api/live-recordings/<session_id>/manifest')
@login_required
def reports_live_recording_manifest(session_id):
    from flask import current_app, jsonify, abort
    from app.services.live_recording_service import recording_manifest
    data = recording_manifest(current_app.instance_path, current_user.get_id(), session_id)
    if data is None:
        abort(404)
    response = jsonify(ok=True, recording=data)
    response.headers['Cache-Control'] = 'private, no-store'
    return response


@main_bp.get('/reports/api/live-recordings/<session_id>/segments/<int:segment_index>')
@login_required
def reports_live_recording_segment(session_id, segment_index):
    from flask import current_app, send_file, abort
    from app.services.live_recording_service import recording_segment_path
    path = recording_segment_path(current_app.instance_path, current_user.get_id(), session_id, segment_index)
    if path is None:
        abort(404)
    response = send_file(path, mimetype='video/mp4', as_attachment=False, conditional=True)
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response
