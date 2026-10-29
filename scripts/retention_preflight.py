"""Read-only BIKA retention preflight. Run from project root:
python scripts/retention_preflight.py
Does not modify application data, files or database schema.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

from sqlalchemy import inspect, func, select, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.inspection_batch import InspectionBatch  # noqa: E402
from app.services.storage_service import local_storage_root  # noqa: E402


def main():
    app = create_app()
    with app.app_context():
        engine = db.engine
        inspector = inspect(engine)
        print('=== BIKA RETENTION PREFLIGHT (READ ONLY) ===')
        print('Database dialect:', engine.dialect.name)
        print('Inspection table exists:', inspector.has_table('inspection_batches'))
        if inspector.has_table('alembic_version'):
            with engine.connect() as conn:
                print('Alembic revision(s):', conn.execute(text('SELECT version_num FROM alembic_version')).scalars().all())
        else:
            print('Alembic revision: NO alembic_version table')
        if not inspector.has_table('inspection_batches'):
            print('STOP: Inspection table missing. No retention execution possible.')
            return
        cols = {col['name'] for col in inspector.get_columns('inspection_batches')}
        required = {c.name for c in InspectionBatch.__table__.columns}
        print('Missing model columns in DB:', sorted(required - cols) or 'None')
        print('Extra DB columns:', sorted(cols - required) or 'None')
        if required - cols:
            print('STOP: Schema differs from model. Resolve before retention implementation.')
            return
        now = datetime.now(timezone.utc)
        cutoff90 = now - timedelta(days=90)
        cutoff365 = now - timedelta(days=365)
        print('Total inspection rows:', db.session.scalar(select(func.count()).select_from(InspectionBatch)))
        print('90+ days old (archive candidates):', db.session.scalar(select(func.count()).select_from(InspectionBatch).where(InspectionBatch.inspection_date < cutoff90)))
        print('365+ days old (delete candidates):', db.session.scalar(select(func.count()).select_from(InspectionBatch).where(InspectionBatch.inspection_date < cutoff365)))
        print('Oldest inspection:', db.session.scalar(select(func.min(InspectionBatch.inspection_date))))
        root = local_storage_root()
        print('Local storage root:', root)
        records = db.session.scalars(select(InspectionBatch)).all()
        backend_counts = Counter(r.storage_backend for r in records)
        print('Inspection backend counts:', dict(backend_counts))
        checked, missing, total_bytes = 0, 0, 0
        keys = set()
        for rec in records:
            if rec.storage_backend != 'local':
                continue
            for k in (rec.original_key, rec.preview_key, rec.result_key, rec.manifest_key):
                if k:
                    keys.add(k)
            # Additional derived assets (e.g. annotated.webp, crops) may exist.
        for key in sorted(keys):
            parts = [p for p in str(key).replace('\\', '/').split('/') if p not in ('', '.')]
            if '..' in parts:
                print('Unsafe object key found (not accessed):', repr(key))
                continue
            path = (root / Path(*parts)).resolve()
            if not path.is_relative_to(root.resolve()):
                print('Object key outside root (not accessed):', repr(key))
                continue
            checked += 1
            if path.is_file():
                total_bytes += path.stat().st_size
            else:
                missing += 1
        print('Referenced local files checked:', checked)
        print('Referenced local files missing:', missing)
        print('Referenced files total bytes (not total storage):', total_bytes)
        print('Important: Batches may have additional derived files not listed in DB.')
        print('=== END: no changes made ===')


if __name__ == '__main__':
    main()
