"""BIKA model-path audit (read-only). Run: python check_bika_active_model.py
Place this script in the BIKA_inspectionWebsite root beside config.py.
Does not load GPU models or modify any files.
"""
from pathlib import Path
import hashlib
import json
import os

ROOT = Path(__file__).resolve().parent
MODEL_ROOT = ROOT / 'website_models'
REGISTRY = ROOT / 'instance' / 'model_registry.json'
REQUIRED = ('detector_best.pt', 'detector_settings.json', 'classifier.pt', 'calibration_reference.json')
OPTIONAL = ('02_edge_filter.json',)

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def report(path: Path, hash_it: bool = True) -> None:
    print(' ', path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)
    print('    present:', path.is_file())
    if path.is_file():
        print('    size:', f'{path.stat().st_size / 1024 / 1024:.2f} MiB')
        if hash_it:
            print('    SHA-256:', sha256(path))

def main():
    print('BIKA MODEL LOADING - DISK CONFIG AUDIT (read-only)')
    print('Project root:', ROOT)
    print('Registry path:', REGISTRY)
    registry = {}
    if REGISTRY.is_file():
        try:
            registry = json.loads(REGISTRY.read_text(encoding='utf-8'))
        except Exception as e:
            print('Could not read registry:', e)
    else:
        print('Registry not found; website may fall back to config/default.')
    active = registry.get('active_version')
    default = os.getenv('BIKA_MODEL_VERSION', 'v1_2026-10-10')
    print('Registry active_version:', active)
    print('BIKA_MODEL_VERSION fallback:', default)
    versions = [p for p in sorted(MODEL_ROOT.iterdir()) if p.is_dir() and p.name.startswith('v')] if MODEL_ROOT.is_dir() else []
    complete = [p for p in versions if all((p / name).is_file() for name in REQUIRED)]
    print('Available complete versions:', ', '.join(p.name for p in complete) or '(none)')
    selected = active if active and (MODEL_ROOT / str(active)) in complete else (default if (MODEL_ROOT / default) in complete else (complete[-1].name if complete else None))
    print('Expected active version by registry/fallback:', selected)
    if not selected:
        print('No complete version found in', MODEL_ROOT)
        return
    print('\nACTIVE FILES')
    for name in REQUIRED + OPTIONAL:
        report(MODEL_ROOT / selected / name)
    print('\nWEIGHT COMPARISON ACROSS VERSIONS')
    for name in ('detector_best.pt', 'classifier.pt'):
        print(' ', name)
        for folder in complete:
            p = folder / name
            print('   ', folder.name, sha256(p)[:20], f'({p.stat().st_size / 1024 / 1024:.2f} MiB)')
    print('\nNote: This checks disk configuration and file hashes only.')
    print('It cannot prove which weights are cached in an already-running Flask process.')
    print('Model switching should reset the cached context; restart Flask if uncertain.')
    print('02_edge_filter.json is not loaded by the app(3).zip model pipeline reviewed.')

if __name__ == '__main__':
    main()
