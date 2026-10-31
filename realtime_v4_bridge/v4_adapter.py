"""Read-only inference adapter for the EXACT v4 feature path; no SAM3 loaded.

Reuses the existing training_handover source modules and 09b.classify().
No trained weights or Website production files are changed.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import cv2
import numpy as np
import torch
from torch import nn
from torchvision import models
from PIL import Image

CLASSES = ("normal", "too_dark", "too_short", "fractured", "bent_snack")


def _load_module(path: Path, name: str):
    if not path.is_file():
        raise FileNotFoundError(f"Required validated feature source missing: {path}")
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ResnetGeometryV4(nn.Module):
    """Architecture matching s13.build_model, without downloading any pretrained weights."""
    def __init__(self, geo_dim: int, num_classes: int = 5, occ_head: bool = False):
        super().__init__()
        backbone = models.resnet18(weights=None)
        dim = backbone.fc.in_features
        backbone.fc = nn.Identity()
        self.backbone = backbone
        self.geometry_branch = nn.Sequential(
            nn.Linear(geo_dim, 48), nn.ReLU(), nn.Dropout(.10),
            nn.Linear(48, 32), nn.ReLU(),
        )
        self.status_head = nn.Sequential(
            nn.Linear(dim + 32, 128), nn.ReLU(), nn.Dropout(.20),
            nn.Linear(128, num_classes),
        )
        self.occ_head = (
            nn.Sequential(nn.Linear(dim + 32, 64), nn.ReLU(), nn.Dropout(.20),
                          nn.Linear(64, 3)) if occ_head else None
        )

    def forward(self, image, geometry):
        z = torch.cat([self.backbone(image), self.geometry_branch(geometry)], dim=1)
        occ = self.occ_head(z) if self.occ_head is not None else None
        return self.status_head(z), occ


def polygon_to_pred(poly, height: int, width: int):
    """Convert original-frame polygon to the inclusive bbox/local mask layout used by 09b."""
    p = np.asarray(poly, np.float32)
    if p.ndim != 2 or p.shape[1] != 2 or len(p) < 3 or not np.isfinite(p).all():
        return None
    x0 = max(0, int(np.floor(p[:, 0].min())))
    y0 = max(0, int(np.floor(p[:, 1].min())))
    x1 = min(width - 1, int(np.ceil(p[:, 0].max())))
    y1 = min(height - 1, int(np.ceil(p[:, 1].max())))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    local = np.zeros((y1 - y0 + 1, x1 - x0 + 1), np.uint8)
    cv2.fillPoly(local, [np.rint(p - np.array([x0, y0])).astype(np.int32)], 1)
    ys, xs = np.nonzero(local)
    if xs.size < 25:
        return None
    # Trim the rasterized mask bbox to mask pixels (09b expects exact bbox dimensions).
    tx0, ty0, tx1, ty1 = int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())
    return {
        "box": (x0 + tx0, y0 + ty0, x0 + tx1, y0 + ty1),
        "local": local[ty0:ty1 + 1, tx0:tx1 + 1].astype(bool),
        "cx": float(x0 + xs.mean()),
        "cy": float(y0 + ys.mean()),
        "area": int(len(xs)),
    }


class V4Adapter:
    def __init__(self, root: Path, device: str = 'cuda'):
        root = Path(root).resolve()
        src = root / 'training_handover' / 'source' / 'scripts' / 'status' / 'combined'
        legacy = root / 'app' / 'inference' / 'legacy' / 'predict_final_09b.py'
        self.pipeline = _load_module(legacy, 'bika_v4_bridge_09b')
        self.s02 = _load_module(src / '02_baseline_training' / '02_train_real_only_baseline.py', 'bika_v4_bridge_s02')
        self.s13 = _load_module(src / '13_classifier_v2' / '13_train_classifier_v2.py', 'bika_v4_bridge_s13')
        self.s16 = _load_module(src / '16_robustness_calibration' / '16_robustness_calibration.py', 'bika_v4_bridge_s16')
        self.pipeline.SCRIPT_18_PATH = src / '18_classifier_variants_f1' / '18_classifier_variants_f1.py'
        self.pipeline._S18 = None
        self.pipeline.CALIBRATE_SCALE = True
        self.pipeline.CALIBRATE_COLOUR = True
        checkpoint = root / 'website_models' / 'v4_2026-10-27' / 'classifier.pt'
        ref_path = root / 'website_models' / 'v4_2026-10-27' / 'calibration_reference.json'
        self.ref = json.loads(ref_path.read_text(encoding='utf-8'))
        # v4 is a plain dict / state_dict; safe loading prevents pickle object execution.
        self.ckpt = torch.load(checkpoint, map_location='cpu', weights_only=True)
        if list(self.ckpt['classes']) != list(CLASSES) or list(self.s13.CLASSES) != list(CLASSES):
            raise ValueError('v4 class order mismatch; refusing to guess class indices')
        if self.ckpt['geometry_dim'] != 10 or self.ckpt['config']['crop'] != 'square':
            raise ValueError('Unexpected v4 model config; inspect before running')
        self.s02.SAFE_MARGIN_PIXELS = int(self.ckpt['safe_margin_pixels'])
        self.pipeline.TRAIN_MEDIAN_WIDTH_PX = float(self.ckpt['train_median_width_px'])
        self.device = torch.device('cuda' if str(device).startswith('0') or str(device)=='cuda' else 'cpu')
        if self.device.type == 'cuda' and not torch.cuda.is_available():
            raise RuntimeError('CUDA requested but unavailable (use --device cpu)')
        self.model = ResnetGeometryV4(self.ckpt['geometry_dim'], len(CLASSES), self.ckpt['config']['occ_head'])
        self.model.load_state_dict(self.ckpt['model_state_dict'], strict=True)
        self.model.to(self.device).eval()

    @torch.inference_mode()
    def predict_polygons(self, frame_bgr: np.ndarray, polygons):
        """Return list of (label, probability, probability_vector), or None for invalid masks.

        Full *same-frame* list is required to preserve v4 frame-level relative-colour
        calibration. Runs v4 on every detected instance; measure actual FPS on your PC.
        """
        h, w = frame_bgr.shape[:2]
        preds = []
        idx = []
        for i, p in enumerate(polygons):
            pr = polygon_to_pred(p, h, w)
            if pr is not None:
                preds.append(pr)
                idx.append(i)
        result = [None] * len(polygons)
        if not preds:
            return result
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        # Same v4 safe-zone convention for *calibration* reference.
        # For video preview, the actual raw predictions are shown even near edges;
        # only confirmed line-crossing tracks generate demo event rows.
        inside = [self.s02.inside_safe_zone(p['cx'], p['cy'], w, h) for p in preds]
        labels, probabilities, _, _, geom_indices, calib = self.pipeline.classify(
            preds, inside, image, rgb, self.model, self.ckpt,
            self.s02, self.s13, self.s16, self.ref, self.device
        )
        good = set(geom_indices)
        for i, real_idx in enumerate(idx):
            if i not in good: continue
            prob = probabilities[i]
            result[real_idx] = (labels[i], float(prob.max()), prob.copy())
        return result
