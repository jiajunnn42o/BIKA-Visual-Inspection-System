"""Save new Video Inspection runs through the SAME InspectionBatch and storage as Image.

Important: totals are sampled/track observations, NOT verified unique snacks.
Official Good Rate and SPC therefore use zero judged observations for these rows.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import uuid

from app.extensions import db
from app.models.inspection_batch import InspectionBatch
from app.services.inspection_artifact_service import save_inspection_artifacts
from app.services.storage_service import put_bytes, storage_backend

NAMES = ('normal', 'too_dark', 'too_short', 'fractured', 'bent_snack')


def persist_completed_video_inspection(*, source_bytes, source_filename,
                                        annotated_path, result, user_id):
    path = Path(annotated_path)
    if not path.is_file() or not path.stat().st_size:
        raise FileNotFoundError('Annotated video must exist before saving Report.')
    observed = result.get('summary') or {}
    obs_counts = {name: 0 for name in NAMES}
    obs_counts['normal'] = max(0, int(observed.get('normal') or 0))
    for defect in result.get('defect_counts') or []:
        name = str(defect.get('class_name') or '')
        if name in obs_counts:
            obs_counts[name] += max(0, int(defect.get('count') or 0))
    provisional = {
        'judged': 0, 'normal': 0, 'defect': 0,
        '_bika_provisional_video': True,
        'observation_counts': obs_counts,
        'observation_total': max(0, int(observed.get('judged') or sum(obs_counts.values()))),
        'observation_defects': max(0, int(observed.get('defect') or sum(obs_counts[k] for k in NAMES[1:]))),
        'ai_inspection_frames': max(0, int((result.get('video') or {}).get('ai_inspection_frames') or 0)),
        'video_duration_seconds': float((result.get('video') or {}).get('duration_seconds') or 0),
        'source_note': 'Video observations may repeat physical objects; NOT production yield.',
    }
    record = InspectionBatch(
        batch_id='PENDING-'+uuid.uuid4().hex,
        inspection_date=datetime.now(timezone.utc),
        source_type='video',
        original_filename=str(source_filename)[:255],
        model_version=str((result.get('model') or {}).get('version') or 'YOLO + v4')[:128],
        summary_json=provisional,
        classes_json={name:0 for name in NAMES},
        confidence_json={},
        timing_json={'total_ms': 0},
        created_by_user_id=str(user_id) if user_id is not None else None,
    )
    try:
        db.session.add(record)
        db.session.flush()
        record.batch_id=f'BATCH-{record.id:06d}'
        # Store a compact JSON summary, not potentially huge data-URL preview frames.
        result_to_store = {
            'kind':'video', 'model': result.get('model') or {},
            'video':result.get('video') or {}, 'summary':observed,
            'defect_counts':result.get('defect_counts') or [],
            'counting_note':result.get('counting_note') or provisional['source_note'],
            'provisional':True,
        }
        artifacts=save_inspection_artifacts(
            batch_id=record.batch_id, source_bytes=source_bytes,
            source_filename=source_filename, source_type='video', result=result_to_store,
        )
        annotated_key=f'inspections/{record.batch_id}/annotated.mp4'
        put_bytes(annotated_key,path.read_bytes(),content_type='video/mp4')
        provisional['_annotated_video_key']=annotated_key
        record.summary_json=provisional
        record.storage_backend=str(artifacts.get('storage_backend') or storage_backend())
        record.original_key=artifacts.get('original_key')
        record.preview_key=artifacts.get('preview_key')
        record.result_key=artifacts.get('result_key')
        record.manifest_key=artifacts.get('manifest_key')
        db.session.commit()
        return record
    except Exception:
        db.session.rollback()
        raise
