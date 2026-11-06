"""Read-only Live Session -> Reports Batch Summary adapter.

Live rows are explicitly provisional. No artificial GOOD, Total or Good Ratio.
Storage remains in live_session_history.sqlite3; login-owner filtering is preserved.
"""
from __future__ import annotations
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.services.live_session_history import list_sessions

MY = ZoneInfo('Asia/Kuala_Lumpur')
ORDER = [('Fractured','#E6464C'),('Too Dark','#FF00AA'),('Too Short','#48A1E2'),('Bent Snack','#B85DDE')]

def _label(value):
    text = str(value or '').strip().lower().replace('_',' ').replace('-',' ')
    return {'fractured':'Fractured','too dark':'Too Dark','too short':'Too Short','bent snack':'Bent Snack'}.get(text,'Other')

def build_live_report_rows(instance_path, owner_id, limit=60):
    """Most recent max 60 user-owned sessions, no writes, full report-row adapter."""
    sessions = list_sessions(instance_path, owner_id, limit=min(60,max(1,int(limit))))
    from app.services.live_recording_service import recording_manifest
    result = []
    for s in sessions:
        source = str(s.get('camera_source') or 'Camera')[:100]
        recording = recording_manifest(instance_path, owner_id, s['session_id']) or {'status': 'unavailable', 'segments': []}
        when = str(s.get('started_at') or '')
        try:
            dt = datetime.fromisoformat(when.replace('Z','+00:00'))
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            local = dt.astimezone(MY)
            display = local.strftime('%Y-%m-%d %H:%M')
        except (ValueError,TypeError):
            display = when[:16].replace('T',' ')
        counts = {key: 0 for key,_ in ORDER}
        for key, n in (s.get('class_breakdown') or {}).items():
            label = _label(key)
            if label in counts: counts[label] += max(0,int(n or 0))
        total_observations = max(0,int(s.get('event_count') or 0))
        # New Live Sessions persist classified Stable-ID estimates, including normal.
        # Historical sessions with only defect events remain explicitly unknown.
        est_total = s.get('estimated_total')
        est_good = s.get('estimated_good')
        est_bad = s.get('estimated_bad')
        has_estimate = (est_total is not None and est_good is not None and est_bad is not None
                        and int(est_total)>0 and int(est_total)==int(est_good)+int(est_bad))
        classes = [{'key':label.lower().replace(' ','_'),'label':label,'colour':colour,'count':counts[label]} for label,colour in ORDER]
        events=[]
        for event in (s.get('recent_events') or []):
            events.append({'label':_label(event.get('label')), 'detected_at':str(event.get('detected_at') or ''), 'confidence':event.get('confidence')})
        result.append({
            'batch_id': 'live:'+str(s['session_id']),
            'file_name': 'Live · Camo Camera' if 'camo' in source.lower() or 'iphone' in source.lower() else 'Live · Camera',
            'date_time': when, 'date_display': display,
            'source_type':'live', 'is_provisional': True,
            'total':int(est_total) if has_estimate else None, 'good':int(est_good) if has_estimate else None, 'bad':int(est_bad) if has_estimate else total_observations, 'good_ratio':round(100*int(est_good)/int(est_total),1) if has_estimate else None, 'has_estimated_counts':bool(has_estimate),
            'status':'PROVISIONAL', 'status_key':'review',
            'model_version':'Realtime YOLO11n-Seg + v4',
            'average_class_confidence':None, 'average_detection_confidence':None,
            'detected_boxes':None, 'sam2_masks':None, 'edge_not_judged':None,
            'total_runtime_seconds':round(float(s.get('duration_seconds') or 0),1),
            'classes':classes, 'preview_url':None, 'original_url':None, 'annotated_url':None,
            'live_session': {'status':str(s.get('status') or 'unknown'), 'ai_frames':max(0,int(s.get('ai_frames') or 0)),
                'duration_seconds':round(float(s.get('duration_seconds') or 0),1),
                'camera_source':source, 'event_count':total_observations,
                'recent_events':events, 'event_preview_limit':20,
                'recording':recording},
        })
    return result

# BIKA-UNIFIED-FIX-V2

# BIKA-REPORT-COUNTS-V4
