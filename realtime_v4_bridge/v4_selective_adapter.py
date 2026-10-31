"""Selective BIKA v4 adapter: all-object frame-colour references, selected-track CNN.

Experimental-only. Scale reference uses cached geometry from previous frames for
unselected objects, so it is an APPROXIMATION to original all-object same-frame
v4 geometry calibration. Compare against original v4 on labeled video before use.
"""
from __future__ import annotations
import numpy as np
import cv2
from pathlib import Path
from PIL import Image
from torch.utils.data import DataLoader
from v4_adapter import V4Adapter, polygon_to_pred, CLASSES


def masked_crop(rgb, pred):
    x0, y0, x1, y1 = pred['box']
    patch = rgb[y0:y1 + 1, x0:x1 + 1].copy()
    mask = pred['local']
    if patch.shape[:2] != mask.shape:
        raise ValueError('Mask/crop shape mismatch')
    patch[~mask] = 0
    return Image.fromarray(patch)


class SelectiveV4Adapter(V4Adapter):
    def __init__(self, root: Path, device='0'):
        super().__init__(root, device)
        self.raw_geometry = {}  # stable id -> last computed raw geometry (for scale reference)

    def prune(self, active_sids):
        active = set(active_sids)
        self.raw_geometry = {sid: g for sid, g in self.raw_geometry.items() if sid in active}

    def predict_selected(self, frame_bgr, polygons, stable_ids, selected_indices):
        """Return {original_index: (class, probability, 5-array)} for selected instances.

        Relative colour and b* calibration are estimated from ALL valid visible
        polygons, including those not being classified. ResNet runs only for
        selected indices. Geometry-scale reference uses last geometry saved for
        other stable IDs (unlike full original v4, which recalculates each frame).
        """
        selected = set(selected_indices)
        if not selected:
            return {}
        h, w = frame_bgr.shape[:2]
        all_preds, orig_idx = [], []
        for i, poly in enumerate(polygons):
            p = polygon_to_pred(poly, h, w)
            if p is not None:
                all_preds.append(p)
                orig_idx.append(i)
        if not all_preds:
            return {}
        selected_entries = [(i, p) for i, p in zip(orig_idx, all_preds) if i in selected]
        if not selected_entries:
            return {}

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        pipe, s02, s13, s16, ckpt = self.pipeline, self.s02, self.s13, self.s16, self.ckpt

        # Expensive geometry extraction ONLY for selected objects.
        feats = []
        indices = []
        for i, p in selected_entries:
            feat = s02.features_from_full_mask(image, pipe.to_full(p['box'], p['local'], h, w))
            if feat is not None:
                indices.append(i)
                feats.append(feat)
                self.raw_geometry[stable_ids[i]] = np.asarray(feat['geometry_raw'], np.float32)
        if not feats:
            return {}

        zone = [s02.inside_safe_zone(p['cx'], p['cy'], w, h) for p in all_preds]
        zone_preds = [p for p, safe in zip(all_preds, zone) if safe]
        if pipe.CALIBRATE_SCALE:
            # Current geometries from selected targets, cached geometries for
            # remaining stable tracks. Missing geometry is ignored. It follows
            # original v4 formula but is NOT necessarily same-frame equivalent.
            widths = [self.raw_geometry[stable_ids[i]][s16.MINOR]
                      for i, safe in zip(orig_idx, zone)
                      if safe and stable_ids[i] in self.raw_geometry]
            scale_k = s16.estimate_scale(np.asarray(widths, np.float32), self.ref)
        else:
            scale_k = 1.0

        if pipe.CALIBRATE_COLOUR:
            b_values = s16.biscuit_b_values(rgb, zone_preds)
            b_shift = s16.estimate_b_shift(b_values, self.ref)
        else:
            b_shift = 0.0
        image_c = s16.shift_lab(rgb, 0., b_shift) if b_shift else rgb
        # Exactly masked crops, avoiding a second geometry pass.
        crops = [masked_crop(image_c, p) if b_shift else f['crop']
                 for (i, p), f in zip([(i,p) for i,p in selected_entries if i in indices], feats)]
        raw_geo = [np.asarray(f['geometry_raw'], np.float32) for f in feats]
        calibrated_geo = [s16.calibrate_geometry(g, scale_k) for g in raw_geo]

        cfg = ckpt['config']
        geometry_model = np.stack(calibrated_geo).astype(np.float32)
        if cfg.get('colour_features'):
            # Important: reference from ALL visible objects, not only selected.
            s18 = pipe._s18()
            cref = ckpt.get('colour_reference', {})
            s18.L_PERCENTILE = cref.get('L_percentile', s18.L_PERCENTILE)
            s18.B_PERCENTILE = cref.get('b_percentile', s18.B_PERCENTILE)
            lab = s18.biscuit_lab_means(rgb, all_preds)
            zone_lab = lab[np.asarray(zone, dtype=bool)] if any(zone) else lab
            ref_l = float(np.nanpercentile(zone_lab[:, 0], s18.L_PERCENTILE))
            ref_b = float(np.nanpercentile(zone_lab[:, 1], s18.B_PERCENTILE))
            by_idx = {i: lab[k] for k,i in enumerate(orig_idx)}
            rel = np.asarray([[by_idx[i][0]-ref_l, by_idx[i][1]-ref_b]
                              for i in indices], np.float32)
            geometry_model = np.concatenate([geometry_model, rel], axis=1)
        if cfg.get('gray'):
            crops = [c.convert('L').convert('RGB') for c in crops]

        mode = cfg['crop']
        if mode == 'square':
            crop_key, eval_tf = 'square_crop', s02.eval_tf
            samples = [{'square_crop': c, 'geometry_raw': g,
                        'status': 'normal', 'occlusion': 'none'}
                       for c, g in zip(crops, geometry_model)]
        else:
            _, eval_tf = s13.get_transforms('oriented', s02)
            crop_key = 'oriented_crop'
            by_idx_p = dict(zip(orig_idx, all_preds))
            samples = [{'oriented_crop': s13.oriented_crop(image_c, by_idx_p[i]['box'], by_idx_p[i]['local'])[0],
                        'geometry_raw': g, 'status': 'normal', 'occlusion': 'none'}
                       for i, g in zip(indices, geometry_model)]
        loader = DataLoader(
            s13.CropDataset(samples, crop_key, eval_tf,
                            np.asarray(ckpt['geometry_mean'], np.float32),
                            np.asarray(ckpt['geometry_std'], np.float32), False),
            batch_size=32, shuffle=False, num_workers=0)
        probs, _ = s13.predict(self.model, loader, self.device, len(samples))
        return {i: (CLASSES[int(v.argmax())], float(v.max()), v.copy())
                for i, v in zip(indices, probs)}
