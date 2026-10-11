# 09b_predict_final.py
# ============================================================
# FINAL SYSTEM ON NEW IMAGES  (replaces 09 for demos and new tests)
#
# Runs exactly configuration [4] of 15 (the final system):
#
#   YOLOv8 detector, F2 operating point (07 / 07b)
#     -> original SAM2.1-L masks
#     -> duplicate removal, containment 0.6 (10b)
#     -> classifier 14_final\A_base.pt (13 network, 14 training)
#     -> raw argmax (no priority rule)
#
# Every setting (operating point, dedup threshold, classifier path,
# batch size, colours) is READ FROM 15, not copied, so this script
# cannot drift away from the tested system.
#
# NEW-PHOTO CALIBRATION (16_robustness_calibration.py, no retraining):
#   CALIBRATE_SCALE  length features are relative to the IMAGE size;
#                    biscuit WIDTH is used as a ruler to undo a different
#                    camera distance / field of view.
#   CALIBRATE_COLOUR the image's b* is shifted so that its least-yellow
#                    biscuits match the training frames.
#   Both OFF = exactly the tested system of 15 (use that for any number
#   compared with the report). Output folders differ so both runs can be
#   compared:  09b_predict_final\ (ON)   09b_predict_final_nocalib\ (OFF)
#   02_summary.json -> domain_check -> length_report tells how long this
#   photo's biscuits are compared with a training NORMAL biscuit.
#
# Two ways to use it
# ------------------
# MODE "images" (default): any photo(s) in INPUT_PATH, no labels needed.
#   <name>_overlay.png     prediction overlay; every judged biscuit has an ID
#   <name>_preview.png     left = original, right = overlay
#   01_detections.csv      one row per kept detection (with probabilities)
#   02_summary.json        counts, timing, image size, domain check
#   03_review_sheet.csv    one row per judged biscuit; column true_status
#                          is pre-filled with the prediction -> change only
#                          the wrong ones, then run 09c_score_review.py
#   04_missed_count.csv    one row per image: fill in how many biscuits
#                          got NO coloured mask (missed_normal, missed_defect)
#
# MODE "cvat": the new photo was labelled in CVAT (new task, same labels
#   and attributes as tasks 13 / 4, MASK shapes). Gives the same metrics
#   as 15 for that photo:
#   cvat_<task>\01_metrics.json, 02_gt_objects.csv, previews\
#
# Biscuits whose centre is within the safe margin (60 px, stored in the
# classifier checkpoint) are drawn grey and not judged, exactly as in 15.
# ============================================================

from __future__ import annotations

import csv
import importlib.util
import json
import time
from collections import Counter
from getpass import getpass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(r"D:\BDS\FYP2\sam2_large_project")

MODE = "images"                 # "images" or "cvat"

# MODE "images": one image file or a folder of images.
# Do NOT use train/val frames: the models have already seen them.
INPUT_PATH = PROJECT_ROOT / "demo_inputs"

# MODE "cvat": task id of the NEW task, and which frames (None = all).
CVAT_HOST = "http://localhost:8080"
CVAT_EVAL_TASK_ID = None        # e.g. 15
CVAT_EVAL_FRAMES = None         # e.g. [0]

CALIBRATE_SCALE = True          # also scales the edge margin with biscuit width
CALIBRATE_COLOUR = True

# Resize the photo so its biscuits have the training pixel size (~64 px
# wide) before running the system: detection + SAM2 run once to measure
# the width, then the whole system runs again on the resized photo.
# Upscaling adds no detail, but the classifier then no longer enlarges the
# crops itself (images mode only).
RESIZE_TO_TRAINING_SCALE = False

# Use another classifier checkpoint (same format as 14_final\A_base.pt),
# e.g. the resolution-robust model of 17. None = final classifier of 15.
CLASSIFIER_OVERRIDE = PROJECT_ROOT / "models" / "status" / "combined" / "23_classifier_new_photos" / "v2_industry" / "B_old_new.pt"
# Detector setting: None = 07b f2 point. After 26 + 15c confirm it, point this at
# outputs\status\combined\26c_gap_filter\02_chosen_operating_point.json
DETECTOR_OP_JSON = None
# Other options:
#   None                                                                     -> A_base of 15
#   PROJECT_ROOT / "models" / "status" / "combined" / "17_resolution_robust" / "A_resaug.pt"   -> low-resolution photos
#   PROJECT_ROOT / "models" / "status" / "combined" / "18_classifier_variants" / "A_gray_colour_resaug.pt"
#       -> after 18 run 2, if it passes the decision rule (full AND low resolution)
# A_gray_colour was validated on full-resolution frames only: on a 1080-px
# photo (biscuits ~30 px wide) it calls most long biscuits too_short.

# The 60 px safe margin was set for ~2360x1314 training frames, where a
# biscuit is ~64 px wide (median width, 10b validation frames). With
# CALIBRATE_SCALE on, the margin becomes 60 px x (biscuit width here / 64.3),
# so a small photo does not lose a large share of its biscuits to the border.
TRAIN_MEDIAN_WIDTH_PX = 64.3
LOWRES_WARN_RATIO = 0.75        # preview warning if biscuits are < 75% of the training width

_CALIB_SUFFIX = {(True, True): "", (False, False): "_nocalib",
                 (True, False): "_scaleonly", (False, True): "_colouronly"}
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "status" / "combined" / (
    "09b_predict_final" + _CALIB_SUFFIX[(CALIBRATE_SCALE, CALIBRATE_COLOUR)]
    + ("_resized" if RESIZE_TO_TRAINING_SCALE else "")
    + ("" if CLASSIFIER_OVERRIDE is None else "_" + Path(CLASSIFIER_OVERRIDE).stem)
)

SCRIPTS = PROJECT_ROOT / "scripts" / "status" / "combined"
SCRIPT_16_PATH = SCRIPTS / "16_robustness_calibration" / "16_robustness_calibration.py"
# Needed only for classifiers trained by 18 (greyscale / relative colour features)
SCRIPT_18_PATH = SCRIPTS / "18_classifier_variants_f1" / "18_classifier_variants_f1.py"
_S18 = None


def _s18():
    """Load 18 lazily: its greyscale and relative-colour code is reused, so
    prediction matches training exactly."""
    global _S18
    if _S18 is None:
        _S18 = load_module(SCRIPT_18_PATH, "variants18")
    return _S18
SCRIPT_02_PATH = SCRIPTS / "02_baseline_training" / "02_train_real_only_baseline.py"
SCRIPT_06_PATH = SCRIPTS / "06_final_test" / "06_final_test.py"
SCRIPT_10_PATH = SCRIPTS / "10_error_analysis" / "10_error_analysis.py"
SCRIPT_13_PATH = SCRIPTS / "13_classifier_v2" / "13_train_classifier_v2.py"
SCRIPT_15_PATH = SCRIPTS / "15_final_system_test" / "15_final_system_test.py"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}

SHOW_IDS = True                 # ID number on every judged biscuit
PREVIEW_MAX_WIDTH = 0           # 0 = full resolution; e.g. 2400 to shrink

EDGE_COLOR = (160, 160, 160)    # BGR grey: centre in the safe margin, not judged
EDGE_LABEL = "edge (not judged)"

# Domain check: warn when the mean of a geometry feature on the new image
# is further than this many training standard deviations from the
# training mean (stored in A_base.pt). Large values = different zoom,
# resolution or biscuit size than the training videos.
DOMAIN_Z_WARN = 2.0

# Training frames: landscape, about 2,400 px wide (see 07).
TRAIN_FRAME_WIDTH_APPROX = 2400

REVIEW_CLASSES = ["normal", "too_dark", "too_short", "fractured", "bent_snack", "not_biscuit"]


# ============================================================
# HELPERS
# ============================================================

def load_module(path, name):
    if not path.exists():
        raise FileNotFoundError(f"Script not found:\n{path}")
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def list_images(path):
    path = Path(path)
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(
            p for p in path.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        )
    raise FileNotFoundError(f"INPUT_PATH not found:\n{path}")


def save_csv(path, rows):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def to_full(box, local, height, width):
    full = np.zeros((height, width), dtype=np.uint8)
    x0, y0, x1, y1 = box
    full[y0:y1 + 1, x0:x1 + 1] = local.astype(np.uint8)
    return full


def sync():
    import torch
    if torch.cuda.is_available():
        torch.cuda.synchronize()


# ============================================================
# PIPELINE (same steps and settings as 15, config [4])
# ============================================================

def detect(detector, image, det_cfg):
    r = detector.predict(source=image, imgsz=det_cfg["imgsz"], conf=det_cfg["conf"],
                         iou=det_cfg["nms_iou"], max_det=det_cfg["max_det"],
                         augment=bool(det_cfg.get("augment", False)), verbose=False)[0]   # augment: 26 TTA
    return (r.boxes.xyxy.cpu().numpy().astype(np.float32),
            r.boxes.conf.cpu().numpy().astype(np.float32))


def segment(predictor, image_np, boxes, confs, s10, box_batch):
    """Original SAM2 on detector boxes -> list of preds (same code as 15)."""
    import torch
    preds = []
    if len(boxes) == 0:
        return preds
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        predictor.set_image(image_np)
    for start in range(0, len(boxes), box_batch):
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            masks, _, _ = predictor.predict(point_coords=None, point_labels=None,
                                            box=boxes[start:start + box_batch],
                                            multimask_output=False)
        masks = np.asarray(masks)
        if masks.ndim == 3:
            masks = masks[None]
        for j in range(masks.shape[0]):
            box, local = s10.to_local(masks[j, 0] > 0.5)
            if box is None:
                continue
            ys, xs = np.nonzero(local)
            preds.append({"box": box, "local": local, "area": int(local.sum()),
                          "conf": float(confs[start + j]),
                          "cx": float(xs.mean() + box[0]), "cy": float(ys.mean() + box[1])})
    return preds


def filter_low_conf(preds, det_cfg, s10):
    """Two-tier filter chosen by 26b. Predictions with conf >= det_cfg["conf_high"] are kept as
    they are (= the old operating point); lower-confidence ones are kept only if they are
    biscuit-sized (area >= low_min_area_frac x median area of the confident ones) and not mostly
    inside an already kept mask (overlap < low_containment x own area).
    No-op when det_cfg has no "conf_high" (07b f2 point, 26 points)."""
    hi = det_cfg.get("conf_high")
    if hi is None or not preds:
        return list(preds)
    c_lo = float(det_cfg.get("low_containment", 1.0))
    a_lo = float(det_cfg.get("low_min_area_frac", 0.0))
    high = [p for p in preds if p["conf"] >= hi]
    low = sorted((p for p in preds if p["conf"] < hi), key=lambda q: -q["conf"])
    ref = float(np.median([p["area"] for p in (high if len(high) >= 5 else preds)]))
    kept = list(high)
    for p in low:
        if p["area"] < a_lo * ref:
            continue
        boxes = np.asarray([k["box"] for k in kept]).reshape(-1, 4)
        if any(s10.mask_inter(p, kept[int(i)]) >= c_lo * p["area"] for i in s10.overlapping(p["box"], boxes)):
            continue
        kept.append(p)
    return sorted(kept, key=lambda q: -q["conf"])


def filter_gaps(preds, image_np, det_cfg):
    """Gap filter chosen by 26c: drop masks that are mostly tray background (the bright gaps
    between biscuits that the detector sometimes boxes). Self-calibrating per image, in CIELAB:
      tray colour    = median of the pixels covered by no mask
      biscuit colour = median of the pixels of the confident masks (conf >= 0.5)
    A pixel is tray-like when it is closer to the tray colour than to the biscuit colour;
    a mask with >= det_cfg["gap_fraction"] tray-like pixels is removed.
    No-op unless det_cfg["gap_fraction"] is set."""
    frac = det_cfg.get("gap_fraction")
    if frac is None or len(preds) < 5:
        return list(preds)
    lab = cv2.cvtColor(np.ascontiguousarray(image_np), cv2.COLOR_RGB2LAB).astype(np.float32)
    covered = np.zeros(lab.shape[:2], bool)
    for p in preds:
        x0, y0, x1, y1 = p["box"]
        covered[y0:y1 + 1, x0:x1 + 1] |= p["local"]
    if (~covered).sum() < 500:
        return list(preds)
    tray = np.median(lab[~covered], axis=0)
    ref = [p for p in preds if p["conf"] >= 0.5]
    if len(ref) < 5:
        ref = sorted(preds, key=lambda q: -q["conf"])[:max(5, len(preds) // 2)]
    biscuit = np.median(np.concatenate([lab[p["box"][1]:p["box"][3] + 1, p["box"][0]:p["box"][2] + 1][p["local"]]
                                        for p in ref]), axis=0)
    kept = []
    for p in preds:
        x0, y0, x1, y1 = p["box"]
        px = lab[y0:y1 + 1, x0:x1 + 1][p["local"]]
        tray_like = np.linalg.norm(px - tray, axis=1) < np.linalg.norm(px - biscuit, axis=1)
        if tray_like.mean() < frac:
            kept.append(p)
    return kept


def classify(preds, inside, image, image_np, model, ckpt, s02, s13, s16, reference, device):
    """Same code path as 15.classify_new, plus the new-photo calibration of 16.
    Returns labels, probabilities, raw and calibrated geometry, and the
    calibration applied. Scale and colour are estimated from the biscuits
    in the safe zone only."""
    from torch.utils.data import DataLoader

    H, W = image_np.shape[:2]
    labels = ["normal"] * len(preds)          # empty-mask case = accepted (as 06)
    probs = np.zeros((len(preds), len(s13.CLASSES)), dtype=np.float32)
    probs[:, s13.CLASSES.index("normal")] = 1.0
    calib = {"scale_k": 1.0, "b_shift": 0.0, "scale_on": CALIBRATE_SCALE, "colour_on": CALIBRATE_COLOUR}

    feats, index = [], []
    for i, p in enumerate(preds):
        feat = s02.features_from_full_mask(image, to_full(p["box"], p["local"], H, W))
        if feat is None:
            continue
        feats.append(feat)
        index.append(i)
    if not feats:
        return labels, probs, np.zeros((0, 0), np.float32), np.zeros((0, 0), np.float32), [], calib

    geometry_raw = np.stack([f["geometry_raw"].astype(np.float32) for f in feats])
    zone_rows = [k for k, i in enumerate(index) if inside[i]]

    if CALIBRATE_SCALE:
        calib["scale_k"] = s16.estimate_scale(geometry_raw[zone_rows, s16.MINOR], reference)
    if CALIBRATE_COLOUR:
        calib["b_shift"] = s16.estimate_b_shift(
            s16.biscuit_b_values(image_np, [preds[index[k]] for k in zone_rows]), reference)

    crops = [f["crop"] for f in feats]
    image_c = image_np
    if calib["b_shift"] != 0.0:
        image_c = s16.shift_lab(image_np, 0.0, calib["b_shift"])
        pil_c = Image.fromarray(image_c)
        crops = [s02.features_from_full_mask(pil_c, to_full(preds[i]["box"], preds[i]["local"], H, W))["crop"]
                 for i in index]
    geometry = np.stack([s16.calibrate_geometry(g, calib["scale_k"]) for g in geometry_raw])

    # Classifiers from 18: greyscale crops and / or colour relative to the
    # other biscuits of this image (reference = safe-zone biscuits).
    cfg = ckpt["config"]
    geometry_model = geometry
    if cfg.get("colour_features"):
        s18 = _s18()
        ref = ckpt.get("colour_reference", {})
        s18.L_PERCENTILE = ref.get("L_percentile", s18.L_PERCENTILE)
        s18.B_PERCENTILE = ref.get("b_percentile", s18.B_PERCENTILE)
        lab = s18.biscuit_lab_means(image_np, [preds[i] for i in index])
        zone_lab = lab[zone_rows] if zone_rows else lab
        ref_L = np.nanpercentile(zone_lab[:, 0], s18.L_PERCENTILE)
        ref_b = np.nanpercentile(zone_lab[:, 1], s18.B_PERCENTILE)
        rel = np.stack([lab[:, 0] - ref_L, lab[:, 1] - ref_b], axis=1).astype(np.float32)
        geometry_model = np.concatenate([geometry, rel], axis=1)
        calib["relative_colour_reference"] = {"L": round(float(ref_L), 2), "b": round(float(ref_b), 2)}
    if cfg.get("gray"):
        crops = [c.convert("L").convert("RGB") for c in crops]

    mode = cfg["crop"]
    if mode == "square":
        crop_key, eval_tf = "square_crop", s02.eval_tf
        samples = [{"square_crop": c, "geometry_raw": g, "status": "normal", "occlusion": "none"}
                   for c, g in zip(crops, geometry_model)]
    else:
        _, eval_tf = s13.get_transforms("oriented", s02)
        crop_key = "oriented_crop"
        samples = [{"oriented_crop": s13.oriented_crop(image_c, preds[i]["box"], preds[i]["local"])[0],
                    "geometry_raw": g, "status": "normal", "occlusion": "none"}
                   for i, g in zip(index, geometry_model)]

    loader = DataLoader(
        s13.CropDataset(samples, crop_key, eval_tf,
                        np.asarray(ckpt["geometry_mean"], np.float32),
                        np.asarray(ckpt["geometry_std"], np.float32), False),
        batch_size=32, shuffle=False, num_workers=0,
    )
    p_items, _ = s13.predict(model, loader, device, len(samples))
    for k, i in enumerate(index):
        probs[i] = p_items[k]
        labels[i] = s13.CLASSES[int(p_items[k].argmax())]
    return labels, probs, geometry_raw, geometry, index, calib


def domain_check(geometry_raw, geometry_cal, ckpt, width, height, calib, reference, s16):
    """How far the new image is from the training data (no labels needed)."""
    notes = []
    out = {"width": int(width), "height": int(height),
           "orientation": "portrait" if height > width else "landscape",
           "calibration": {"scale_k": round(calib["scale_k"], 3), "b_shift": round(calib["b_shift"], 2),
                           "safe_margin_px": calib.get("safe_margin_px"),
                           "median_biscuit_width_px": calib.get("median_width_px"),
                           "training_median_width_px": TRAIN_MEDIAN_WIDTH_PX,
                           "scale_on": calib["scale_on"], "colour_on": calib["colour_on"]}}

    if height > width:
        notes.append("Portrait image; all training frames were landscape.")

    mean = np.asarray(ckpt["geometry_mean"], np.float32)[:8]          # 8 shape features
    std = np.maximum(np.asarray(ckpt["geometry_std"], np.float32)[:8], 1e-6)
    for key, g in (("geometry_mean_z_raw", geometry_raw), ("geometry_mean_z_calibrated", geometry_cal)):
        if g.size:
            out[key] = [round(float(v), 2) for v in (g.mean(axis=0) - mean) / std]
    z = out.get("geometry_mean_z_calibrated") or out.get("geometry_mean_z_raw")
    if z:
        far = [k for k, v in enumerate(z) if abs(v) > DOMAIN_Z_WARN]
        out["geometry_features_far_from_training"] = far
        if far:
            notes.append(f"Geometry features {far} (after calibration) are more than {DOMAIN_Z_WARN} "
                         "training std from the training mean: length / shape judgements are unreliable.")

    w = calib.get("median_width_px")
    if w is not None and w < 0.7 * TRAIN_MEDIAN_WIDTH_PX:
        notes.append(
            f"LOW RESOLUTION: biscuits are only {w:.0f} px wide here vs about {TRAIN_MEDIAN_WIDTH_PX:.0f} px "
            "in the training frames. The classifier crops are upscaled and blurry, which it never saw in "
            "training. Use the original full-resolution frame (same export as the CVAT frames).")

    if reference is not None and geometry_cal.size:
        rep = s16.length_report(geometry_cal[:, s16.MAJOR], reference)
        out["length_report"] = rep
        ratio = rep.get("median_length_vs_training_all") if rep else None
        if ratio is not None and ratio < 0.8:
            notes.append(
                f"Biscuits look shorter than in the training frames: median length of all biscuits is "
                f"{100 * ratio:.0f}% of the training median (same measure).")
    if abs(calib["b_shift"]) >= 4:
        notes.append(f"Colour differs from training (b* shift {calib['b_shift']:+.1f} applied"
                     + ("" if calib["colour_on"] else ", but colour calibration is OFF") + ").")
    if abs(calib["scale_k"] - 1) >= 0.15:
        notes.append(f"Biscuits appear at a different size than in training (scale k = {calib['scale_k']:.2f}"
                     + ("" if calib["scale_on"] else ", but scale calibration is OFF") + ").")
    out["warnings"] = notes
    return out


# ============================================================
# DRAWING
# ============================================================

def draw_contour(image, box, local, color, thickness):
    contours, _ = cv2.findContours(local.astype(np.uint8), cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE, offset=(box[0], box[1]))
    cv2.drawContours(image, contours, -1, color, thickness)


def put_id(image, text, x, y, scale):
    thick = max(1, int(round(2 * scale)))
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    org = (int(x - tw / 2), int(y + th / 2))
    cv2.putText(image, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(image, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), thick, cv2.LINE_AA)


def wrap_text(text, max_width, scale=0.6):
    """Split a title line at spaces so it fits max_width pixels."""
    out, cur = [], ""
    for word in text.split(" "):
        trial = word if not cur else cur + " " + word
        if not cur or cv2.getTextSize(trial, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)[0][0] <= max_width:
            cur = trial
        else:
            out.append(cur)
            cur = "    " + word
    out.append(cur)
    return out


def legend_band(width, title_lines, counts, classes, colors):
    """Legend drawn BELOW the image (a dense pile has no free corner)."""
    items = [(f"{c}: {counts.get(c, 0)}", colors[c]) for c in classes]
    items.append((f"{EDGE_LABEL}: {counts.get(EDGE_LABEL, 0)}", EDGE_COLOR))
    col_w = 300
    per_row = max(1, (width - 24) // col_w)
    n_rows = -(-len(items) // per_row)
    lines = []                                  # (text, colour), long lines wrapped
    for line in title_lines:
        colour = (0, 200, 255) if line.startswith("WARNING") else (255, 255, 255)   # BGR orange
        lines += [(part, colour) for part in wrap_text(line, width - 24)]
    height = 16 + 26 * len(lines) + 30 * n_rows + 8
    band = np.zeros((height, width, 3), np.uint8)
    for k, (line, colour) in enumerate(lines):
        cv2.putText(band, line, (12, 30 + 26 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    colour, 1, cv2.LINE_AA)
    y0 = 16 + 26 * len(lines)
    for i, (text, color) in enumerate(items):
        x = 12 + (i % per_row) * col_w
        y = y0 + (i // per_row) * 30
        cv2.rectangle(band, (x, y), (x + 18, y + 18), color, -1)
        cv2.rectangle(band, (x, y), (x + 18, y + 18), (255, 255, 255), 1)
        cv2.putText(band, text, (x + 28, y + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (255, 255, 255), 1, cv2.LINE_AA)
    return band


def draw_panel_label(image, text, align_right=False):
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
    x = image.shape[1] - tw - 32 if align_right else 12
    cv2.rectangle(image, (x, 12), (x + tw + 20, 12 + th + 20), (0, 0, 0), -1)
    cv2.putText(image, text, (x + 10, 12 + th + 10), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)


def draw_result(image_np, preds, shown, ids, counts, classes, colors, alpha, gap, title, stem, out_dir):
    """shown[i] = class name or EDGE_LABEL; ids[i] = review ID or None."""
    base = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
    layer = base.copy()
    for p, lab in zip(preds, shown):
        x0, y0, x1, y1 = p["box"]
        layer[y0:y1 + 1, x0:x1 + 1][p["local"]] = EDGE_COLOR if lab == EDGE_LABEL else colors[lab]
    out = cv2.addWeighted(layer, alpha, base, 1 - alpha, 0)
    for p, lab in zip(preds, shown):
        draw_contour(out, p["box"], p["local"], EDGE_COLOR if lab == EDGE_LABEL else (255, 255, 255), 1)

    if SHOW_IDS:
        scale = max(0.35, min(1.0, min(base.shape[:2]) / 2400))
        for p, pid in zip(preds, ids):
            if pid is not None:
                put_id(out, str(pid), p["cx"], p["cy"], scale)

    band = legend_band(out.shape[1], title, counts, classes, colors)
    overlay_path = Path(out_dir) / f"{stem}_overlay.png"
    cv2.imwrite(str(overlay_path), np.vstack([out, band]))

    left = base.copy()
    draw_panel_label(left, "Original")
    right = out.copy()
    draw_panel_label(right, "Prediction", align_right=True)
    panels = np.hstack([left, np.full((left.shape[0], gap, 3), 255, np.uint8), right])
    # legend across the full width under both panels (no empty block under "Original")
    preview = np.vstack([panels, legend_band(panels.shape[1], title, counts, classes, colors)])
    if PREVIEW_MAX_WIDTH and preview.shape[1] > PREVIEW_MAX_WIDTH:
        s = PREVIEW_MAX_WIDTH / preview.shape[1]
        preview = cv2.resize(preview, (PREVIEW_MAX_WIDTH, int(round(preview.shape[0] * s))),
                             interpolation=cv2.INTER_AREA)
    preview_path = Path(out_dir) / f"{stem}_preview.png"
    cv2.imwrite(str(preview_path), preview)
    return overlay_path, preview_path


# ============================================================
# ONE IMAGE THROUGH THE FINAL SYSTEM
# ============================================================

def median_width_px(kept, s10):
    if not kept:
        return None
    return float(np.median([s10.shape_descriptors(p["local"])[1] for p in kept]))


def adapt_safe_margin(width_px, base_margin, n_kept, s02):
    """Edge margin in pixels, scaled with the biscuit width of this image."""
    if not CALIBRATE_SCALE or n_kept < 8 or width_px is None:
        s02.SAFE_MARGIN_PIXELS = int(base_margin)
        return int(base_margin)
    margin = int(round(base_margin * width_px / TRAIN_MEDIAN_WIDTH_PX))
    s02.SAFE_MARGIN_PIXELS = max(margin, 8)
    return s02.SAFE_MARGIN_PIXELS


def run_system(image, image_np, detector, predictor, model, ckpt, det_cfg,
               s02, s10, s13, s15, s16, reference, device):
    H, W = image_np.shape[:2]
    sync(); t0 = time.perf_counter()
    boxes, confs = detect(detector, image, det_cfg)
    sync(); t1 = time.perf_counter()
    preds = segment(predictor, image_np, boxes, confs, s10, s15.BOX_BATCH)
    kept, n_dropped = s15.suppress_contained(preds, s15.DEDUP_CONTAINMENT, s10)
    n_before = len(kept)
    kept = filter_low_conf(kept, det_cfg, s10)                 # no-op unless a 26b operating point is used
    kept = filter_gaps(kept, image_np, det_cfg)                # no-op unless a 26c operating point is used
    n_dropped += n_before - len(kept)
    width_px = median_width_px(kept, s10)
    margin = adapt_safe_margin(width_px, ckpt["safe_margin_pixels"], len(kept), s02)
    inside = [s02.inside_safe_zone(p["cx"], p["cy"], W, H) for p in kept]
    sync(); t2 = time.perf_counter()
    labels, probs, geometry_raw, geometry, geom_index, calib = classify(
        kept, inside, image, image_np, model, ckpt, s02, s13, s16, reference, device)
    sync(); t3 = time.perf_counter()
    timing = {"detector_ms": round((t1 - t0) * 1000, 1),
              "sam2_and_dedup_ms": round((t2 - t1) * 1000, 1),
              "classifier_ms": round((t3 - t2) * 1000, 1),
              "total_ms": round((t3 - t0) * 1000, 1)}
    return {"n_detected": len(boxes), "n_masks": len(preds), "n_dedup_dropped": n_dropped,
            "preds": kept, "inside": inside, "labels": labels, "probs": probs,
            "geometry_raw": geometry_raw, "geometry": geometry, "geom_index": geom_index,
            "calibration": dict(calib, safe_margin_px=margin,
                                median_width_px=None if width_px is None else round(width_px, 1)),
            "timing": timing}


# ============================================================
# MODE "images"
# ============================================================

def run_images(ctx):
    s02, s13, s15 = ctx["s02"], ctx["s13"], ctx["s15"]
    classes = list(s13.CLASSES)
    images = list_images(INPUT_PATH)
    if not images:
        raise RuntimeError(f"No images found in:\n{INPUT_PATH}")
    print(f"Images: {len(images)} from {INPUT_PATH}")

    det_rows, review_rows, missed_rows = [], [], []
    summary = {"system": ctx["system"], "images": []}

    for n, path in enumerate(images, start=1):
        image = Image.open(path).convert("RGB")
        image_np = np.asarray(image).copy()
        W, H = image.size

        res = run_system(image, image_np, ctx["detector"], ctx["predictor"], ctx["model"],
                         ctx["ckpt"], ctx["det_cfg"], s02, ctx["s10"], s13, s15,
                         ctx["s16"], ctx["reference"], ctx["device"])
        resize_factor = 1.0
        if RESIZE_TO_TRAINING_SCALE and res["calibration"].get("median_width_px"):
            resize_factor = TRAIN_MEDIAN_WIDTH_PX / res["calibration"]["median_width_px"]
            if abs(resize_factor - 1.0) > 0.1:
                image = image.resize((round(W * resize_factor), round(H * resize_factor)), Image.BICUBIC)
                image_np = np.asarray(image).copy()
                W, H = image.size
                print(f"   resized x{resize_factor:.2f} to {W}x{H} (biscuit width -> ~{TRAIN_MEDIAN_WIDTH_PX:.0f} px)")
                res = run_system(image, image_np, ctx["detector"], ctx["predictor"], ctx["model"],
                                 ctx["ckpt"], ctx["det_cfg"], s02, ctx["s10"], s13, s15,
                                 ctx["s16"], ctx["reference"], ctx["device"])
            else:
                resize_factor = 1.0
        preds, labels, probs, inside = res["preds"], res["labels"], res["probs"], res["inside"]
        calib = res["calibration"]
        length_ratio = [""] * len(preds)
        if ctx["reference"] is not None:
            for k, i in enumerate(res["geom_index"]):
                length_ratio[i] = round(float(res["geometry"][k, ctx["s16"].MAJOR])
                                        / ctx["reference"]["median_major_normal"], 3)
        shown = [lab if ok else EDGE_LABEL for lab, ok in zip(labels, inside)]

        # IDs: judged biscuits only, numbered top-to-bottom, left-to-right
        order = sorted([i for i, ok in enumerate(inside) if ok],
                       key=lambda i: (round(preds[i]["cy"] / 80), preds[i]["cx"]))
        ids = [None] * len(preds)
        for k, i in enumerate(order, start=1):
            ids[i] = k

        counts = Counter(shown)
        defects = sum(v for c, v in counts.items() if c not in ("normal", EDGE_LABEL))
        judged = sum(inside)
        keep_rows = [k for k, i in enumerate(res["geom_index"]) if inside[i]]
        empty = np.zeros((0, 0), np.float32)
        domain = domain_check(res["geometry_raw"][keep_rows] if keep_rows else empty,
                              res["geometry"][keep_rows] if keep_rows else empty,
                              ctx["ckpt"], W, H, calib, ctx["reference"], ctx["s16"])

        variant = ctx["ckpt"].get("variant", "A_base")
        title = [f"{path.name} ({W}x{H}{f', resized x{resize_factor:.2f}' if resize_factor != 1.0 else ''}) "
                 f"| judged {judged}, rejected {defects} | classifier {variant}",
                 f"FINAL system: YOLOv8[{s15.OPERATING_POINT}] > SAM2 > dedup {s15.DEDUP_CONTAINMENT} > {variant} (raw) | "
                 f"calibration scale k={calib['scale_k']:.2f}{'' if CALIBRATE_SCALE else ' (off)'}, "
                 f"b* shift {calib['b_shift']:+.1f}{'' if CALIBRATE_COLOUR else ' (off)'}"]
        width_px = calib.get("median_width_px")
        if width_px and width_px < LOWRES_WARN_RATIO * TRAIN_MEDIAN_WIDTH_PX:
            trained_lowres = bool(ctx["ckpt"].get("config", {}).get("resaug")
                                  or ctx["ckpt"].get("config", {}).get("resolution_augmentation"))
            title.append(f"WARNING low resolution: biscuits {width_px:.0f} px wide vs {TRAIN_MEDIAN_WIDTH_PX:.0f} px "
                         f"in training | {variant} "
                         + ("was trained with resolution augmentation"
                            if trained_lowres else "was NOT trained for this - expect too_short errors"))
        _, preview_path = draw_result(image_np, preds, shown, ids, counts, classes,
                                      s15.CLASS_COLORS, s15.OVERLAY_ALPHA, s15.PREVIEW_GAP,
                                      title, path.stem, OUTPUT_DIR)

        for i, p in enumerate(preds):
            row = {"image": path.name, "id": "" if ids[i] is None else ids[i],
                   "detector_conf": round(p["conf"], 4), "cx": round(p["cx"], 1),
                   "cy": round(p["cy"], 1), "mask_area": p["area"],
                   "in_safe_zone": inside[i], "length_vs_training_normal": length_ratio[i],
                   "prediction": labels[i], "shown_as": shown[i]}
            for c, v in zip(classes, probs[i]):
                row[f"p_{c}"] = round(float(v), 4)
            det_rows.append(row)

        for i in order:
            review_rows.append({"image": path.name, "id": ids[i],
                                "cx": round(preds[i]["cx"], 1), "cy": round(preds[i]["cy"], 1),
                                "length_vs_training_normal": length_ratio[i],
                                "prediction": labels[i],
                                "prob": round(float(probs[i].max()), 3),
                                "true_status": labels[i], "note": ""})
        missed_rows.append({"image": path.name, "missed_normal": 0, "missed_defect": 0})

        summary["images"].append({
            "image": path.name, "width": W, "height": H, "resize_factor": round(resize_factor, 3),
            "detected_boxes": res["n_detected"], "masks": res["n_masks"],
            "dedup_dropped": res["n_dedup_dropped"], "kept": len(preds),
            "judged_in_safe_zone": judged, "rejected": defects,
            "counts": {c: counts.get(c, 0) for c in classes + [EDGE_LABEL]},
            "domain_check": domain, "timing": res["timing"], "preview": str(preview_path),
        })

        rep = domain.get("length_report", {})
        ratio = rep.get("median_length_vs_training_all")
        print(f"[{n}/{len(images)}] {path.name} ({W}x{H}): biscuit width {calib['median_width_px']} px "
              f"(training ~{TRAIN_MEDIAN_WIDTH_PX:.0f}) | scale k={calib['scale_k']:.2f} "
              f"b* shift={calib['b_shift']:+.1f} edge margin={calib['safe_margin_px']}px"
              + (f" | median length = {100 * ratio:.0f}% of training (all biscuits)" if ratio else ""))
        print(f"   boxes={res['n_detected']} "
              f"dedup-={res['n_dedup_dropped']} judged={judged} rejected={defects} | "
              + " ".join(f"{c}={counts.get(c, 0)}" for c in classes)
              + f" | {res['timing']['total_ms']:.0f} ms" + (" (warm-up)" if n == 1 else ""))
        for w in domain["warnings"]:
            print("   WARNING:", w)

    save_csv(OUTPUT_DIR / "01_detections.csv", det_rows)
    timed = summary["images"][1:] or summary["images"]
    summary["mean_timing_ms_excluding_first"] = {
        k: round(float(np.mean([im["timing"][k] for im in timed])), 1)
        for k in ("detector_ms", "sam2_and_dedup_ms", "classifier_ms", "total_ms")
    }
    (OUTPUT_DIR / "02_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    review_path = OUTPUT_DIR / "03_review_sheet.csv"
    missed_path = OUTPUT_DIR / "04_missed_count.csv"
    for path, rows in ((review_path, review_rows), (missed_path, missed_rows)):
        if path.exists():
            print(f"Kept your existing {path.name} (delete it to regenerate).")
        else:
            save_csv(path, rows)

    print()
    print("Next (optional, manual check without CVAT):")
    print(f"  1. Open the *_preview.png. In {review_path.name}, change true_status of every")
    print(f"     WRONG biscuit (by ID) to one of: {', '.join(REVIEW_CLASSES)}")
    print("     (not_biscuit = duplicate, fragment or background).")
    print(f"  2. In {missed_path.name}, count biscuits inside the image that have NO coloured mask.")
    print("  3. Run 09c_score_review.py.")
    print("Outputs:", OUTPUT_DIR)


# ============================================================
# MODE "cvat"  (labelled new photo -> same metrics as 15)
# ============================================================

def run_cvat(ctx):
    from cvat_sdk import make_client

    s02, s10, s13, s15 = ctx["s02"], ctx["s10"], ctx["s13"], ctx["s15"]
    if CVAT_EVAL_TASK_ID is None:
        raise RuntimeError('MODE = "cvat" needs CVAT_EVAL_TASK_ID (the new task id).')
    task_id = int(CVAT_EVAL_TASK_ID)
    out_dir = OUTPUT_DIR / f"cvat_task{task_id}"
    (out_dir / "previews").mkdir(parents=True, exist_ok=True)

    username = input("\nCVAT username: ").strip()
    password = getpass("CVAT password: ")
    with make_client(CVAT_HOST, credentials=(username, password)) as client:
        task = client.tasks.retrieve(task_id)
        n_frames = int(task.size)
        frame_ids = list(range(n_frames)) if CVAT_EVAL_FRAMES is None else [int(f) for f in CVAT_EVAL_FRAMES]
        entries = [{"uid": f"task{task_id}_frame{f}", "task_id": task_id, "frame_id": f,
                    "source": f"Task{task_id}"} for f in frame_ids]
        frames = s10.load_frames(client, s02, entries)

    rows = []
    for f in frames:
        if not f["objects"]:
            print(f"WARNING: {f['uid']} has no MASK shapes with the biscuit label. "
                  "Polygons/boxes are ignored by the loader; label with the mask/brush tool.")
        res = run_system(f["image"], f["image_np"], ctx["detector"], ctx["predictor"], ctx["model"],
                         ctx["ckpt"], ctx["det_cfg"], s02, s10, s13, s15,
                         ctx["s16"], ctx["reference"], ctx["device"])
        f["preds_final"], f["labels_final"] = res["preds"], res["labels"]
        f["safe_margin_px"] = res["calibration"]["safe_margin_px"]
        f["domain_check"] = domain_check(res["geometry_raw"], res["geometry"], ctx["ckpt"], f["width"],
                                         f["height"], res["calibration"], ctx["reference"], ctx["s16"])

        p2g, g2p, ious = s10.match_instances(f["preds_final"], f["objects"], s15.MATCH_IOU)
        for j, g in enumerate(f["objects"]):
            i = g2p.get(j)
            rows.append({
                "uid": f["uid"], "image_number": f["image_number"], "object_key": g["object_key"],
                "status": g["status"], "occlusion": g["occlusion"],
                "in_safe_zone": s02.inside_safe_zone(g["cx"], g["cy"], f["width"], f["height"]),
                "detected": i is not None,
                "mask_iou": "" if i is None else round(ious[i], 3),
                "pred_final": "" if i is None else f["labels_final"][i],
            })
        s15.draw_preview(f, f["preds_final"], f["labels_final"], s02.inside_safe_zone,
                         s10.match_instances, s13.CLASSES,
                         out_dir / "previews" / f"task{task_id}_image{f['image_number']:02d}_final_preview.png")

    s02.SAFE_MARGIN_PIXELS = int(np.median([f["safe_margin_px"] for f in frames]))
    result = s15.evaluate_config(frames, "preds_final", "labels_final", s02.inside_safe_zone,
                                 s10.match_instances, s13.status_metrics)
    result["safe_margin_px_used"] = int(s02.SAFE_MARGIN_PIXELS)
    save_csv(out_dir / "02_gt_objects.csv", rows)
    (out_dir / "01_metrics.json").write_text(json.dumps({
        "system": ctx["system"], "task_id": task_id, "frames": frame_ids,
        "domain_check": {f["uid"]: f["domain_check"] for f in frames},
        "result": result,
        "reference_locked_test_final": {"accuracy": 0.850, "defect_recall": 0.879,
                                        "false_reject_rate": 0.109, "extra_rejections": 44,
                                        "n_biscuits": 615},
    }, indent=2, default=float), encoding="utf-8")

    m = result["system"]

    def pct(v):
        return "-" if v is None else f"{100 * v:.1f}%"

    print()
    print(f"NEW TASK {task_id} vs locked test (final system [4])")
    print(f"  detection P/R : {pct(result['detection']['precision'])} / {pct(result['detection']['recall'])}   (test 83.7% / 90.3%)")
    print(f"  accuracy      : {pct(m['accuracy'])}   (test 85.0%)")
    print(f"  defect recall : {pct(m['defect_recall'])}   (test 87.9%)")
    print(f"  false rejects : {pct(m['false_reject_rate'])}   (test 10.9%)")
    print(f"  extra rejects : {result['extra_rejections']}   (test 44 over 3 frames)")
    print("Outputs:", out_dir)


# ============================================================
# MAIN
# ============================================================

def main():
    import torch
    from sam2.build_sam import build_sam2
    from sam2.sam2_image_predictor import SAM2ImagePredictor
    from ultralytics import YOLO

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is required.")
    device = torch.device("cuda")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    s02 = load_module(SCRIPT_02_PATH, "status02")
    s06 = load_module(SCRIPT_06_PATH, "final_test06")
    s10 = load_module(SCRIPT_10_PATH, "error10")
    s13 = load_module(SCRIPT_13_PATH, "classifier13")
    s15 = load_module(SCRIPT_15_PATH, "final15")
    s16 = load_module(SCRIPT_16_PATH, "calibration16")

    reference = None
    if s16.REFERENCE_JSON.exists():
        reference = json.loads(s16.REFERENCE_JSON.read_text(encoding="utf-8"))
    elif CALIBRATE_SCALE or CALIBRATE_COLOUR:
        raise FileNotFoundError(
            f"Calibration reference not found:\n{s16.REFERENCE_JSON}\n"
            "Run 16_robustness_calibration.py first, or set CALIBRATE_SCALE = CALIBRATE_COLOUR = False."
        )

    classifier_path = Path(CLASSIFIER_OVERRIDE) if CLASSIFIER_OVERRIDE else s15.FINAL_CLASSIFIER_PATH
    model, ckpt = s15.load_new_classifier(classifier_path, s13, device)
    s02.SAFE_MARGIN_PIXELS = int(ckpt["safe_margin_pixels"])     # 60 px, as in 15

    op_json = s15.DETECTOR_DIR / (
        "01_detector_operating_point.json" if s15.OPERATING_POINT == "f1"
        else f"01_detector_operating_point_{s15.OPERATING_POINT}.json"
    )
    det_cfg = json.loads(op_json.read_text(encoding="utf-8"))
    if DETECTOR_OP_JSON:
        det_cfg = json.loads(Path(DETECTOR_OP_JSON).read_text(encoding="utf-8"))

    system = {
        "detector_weights": det_cfg["weights"], "operating_point": s15.OPERATING_POINT,
        "conf": det_cfg["conf"], "nms_iou": det_cfg["nms_iou"], "imgsz": det_cfg["imgsz"],
        "sam2_checkpoint": str(s06.SAM2_CHECKPOINT),
        "dedup_containment": s15.DEDUP_CONTAINMENT,
        "classifier": str(classifier_path), "classifier_variant": ckpt.get("variant"),
        "resize_to_training_scale": RESIZE_TO_TRAINING_SCALE,
        "decision": "raw argmax", "safe_margin_px": int(s02.SAFE_MARGIN_PIXELS),
        "calibrate_scale": CALIBRATE_SCALE, "calibrate_colour": CALIBRATE_COLOUR,
        "calibration_reference": str(s16.REFERENCE_JSON) if reference is not None else None,
        "identical_to_15_config_4": not (CALIBRATE_SCALE or CALIBRATE_COLOUR or RESIZE_TO_TRAINING_SCALE
                                         or CLASSIFIER_OVERRIDE),
        "edge_margin": "scaled with biscuit width" if CALIBRATE_SCALE else "fixed 60 px",
    }

    print("=" * 78)
    print(f"09b FINAL SYSTEM: YOLOv8 -> SAM2 -> dedup -> {ckpt.get('variant', 'A_base')}"
          + (" (same as 15 config [4])" if system["identical_to_15_config_4"] else ""))
    print("=" * 78)
    print(f"Detector [{s15.OPERATING_POINT}] conf={det_cfg['conf']} NMS={det_cfg['nms_iou']} | "
          f"dedup={s15.DEDUP_CONTAINMENT} | classifier={ckpt.get('variant')} | "
          f"safe margin={s02.SAFE_MARGIN_PIXELS}px | mode={MODE}")
    print(f"Calibration: scale={'ON' if CALIBRATE_SCALE else 'OFF'} colour={'ON' if CALIBRATE_COLOUR else 'OFF'}"
          + ("" if (CALIBRATE_SCALE or CALIBRATE_COLOUR) else "  (= exactly the tested system of 15)"))

    detector = YOLO(det_cfg["weights"])
    sam_model = build_sam2(s06.SAM2_MODEL_CFG, str(s06.SAM2_CHECKPOINT),
                           device="cuda", mode="eval", apply_postprocessing=False)
    predictor = SAM2ImagePredictor(sam_model)

    ctx = {"s02": s02, "s10": s10, "s13": s13, "s15": s15, "s16": s16, "reference": reference,
           "device": device,
           "detector": detector, "predictor": predictor, "model": model, "ckpt": ckpt,
           "det_cfg": det_cfg, "system": system}

    if MODE == "images":
        run_images(ctx)
    elif MODE == "cvat":
        run_cvat(ctx)
    else:
        raise ValueError('MODE must be "images" or "cvat".')


if __name__ == "__main__":
    main()