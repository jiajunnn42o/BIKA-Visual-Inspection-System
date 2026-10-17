from __future__ import annotations

from collections import Counter
import gc
from io import BytesIO
import json
from pathlib import Path
from threading import Lock
import time

import cv2
import numpy as np
from PIL import Image
import torch
from ultralytics import YOLO

from flask import current_app

from app.inference.legacy import (
    predict_final_09b as pipeline09b,
)

from app.services.inspection_model_metadata import (
    get_classifier_ui_metadata,
)


EDGE_LABEL = "edge (not judged)"
EDGE_COLOUR = "#8D8D8D"


class InspectionPipelineError(
    RuntimeError
):
    pass


class InspectionCancelled(
    InspectionPipelineError
):
    """Raised when the user requests cancellation."""
    pass


_context = None
_context_signature = None

_context_lock = Lock()
_inference_lock = Lock()


# =========================================================
# PATH / CONFIG HELPERS
# =========================================================

def _required_file(
    path: Path,
    label: str,
) -> Path:

    if not path.exists():

        raise InspectionPipelineError(
            f"{label} not found: {path}"
        )

    return path


def _pipeline_script_paths(
    project_root: Path,
) -> dict[str, Path]:

    scripts = (
        project_root
        /
        "scripts"
        /
        "status"
        /
        "combined"
    )


    paths = {
        "s02":
            scripts
            /
            "02_baseline_training"
            /
            "02_train_real_only_baseline.py",

        "s10":
            scripts
            /
            "10_error_analysis"
            /
            "10_error_analysis.py",

        "s13":
            scripts
            /
            "13_classifier_v2"
            /
            "13_train_classifier_v2.py",

        "s15":
            scripts
            /
            "15_final_system_test"
            /
            "15_final_system_test.py",

        "s16":
            scripts
            /
            "16_robustness_calibration"
            /
            "16_robustness_calibration.py",

        "s18":
            scripts
            /
            "18_classifier_variants_f1"
            /
            "18_classifier_variants_f1.py",
    }


    missing = [
        f"{name}: {path}"

        for name, path
        in paths.items()

        if not path.exists()
    ]


    if missing:

        raise InspectionPipelineError(
            "Validated 09b dependency scripts are missing:\n"
            +
            "\n".join(
                missing
            )
        )


    return paths


def _context_config() -> dict:

    config = current_app.config


    return {
        "model_version":
            str(
                config[
                    "MODEL_VERSION"
                ]
            ),

        "pipeline_source_root":
            Path(
                config[
                    "PIPELINE_SOURCE_ROOT"
                ]
            ),

        "detector_path":
            Path(
                config[
                    "DETECTOR_PATH"
                ]
            ),

        "detector_settings_path":
            Path(
                config[
                    "DETECTOR_SETTINGS_PATH"
                ]
            ),

        "classifier_path":
            Path(
                config[
                    "CLASSIFIER_PATH"
                ]
            ),

        "calibration_path":
            Path(
                config[
                    "CALIBRATION_PATH"
                ]
            ),

        "sam2_checkpoint_path":
            Path(
                config[
                    "SAM2_CHECKPOINT_PATH"
                ]
            ),

        "sam2_model_config":
            str(
                config[
                    "SAM2_MODEL_CONFIG"
                ]
            ),
    }


def _signature(
    cfg: dict,
) -> tuple:

    return (
        cfg[
            "model_version"
        ],

        str(
            cfg[
                "pipeline_source_root"
            ]
        ),

        str(
            cfg[
                "detector_path"
            ]
        ),

        str(
            cfg[
                "detector_settings_path"
            ]
        ),

        str(
            cfg[
                "classifier_path"
            ]
        ),

        str(
            cfg[
                "calibration_path"
            ]
        ),

        str(
            cfg[
                "sam2_checkpoint_path"
            ]
        ),

        cfg[
            "sam2_model_config"
        ],
    )


# =========================================================
# MODEL CONTEXT
# =========================================================

def _build_context(
    cfg: dict,
) -> dict:

    if not torch.cuda.is_available():

        raise InspectionPipelineError(
            "CUDA GPU is required for the validated "
            "SAM2.1-L inspection pipeline."
        )


    detector_path = _required_file(
        cfg[
            "detector_path"
        ],
        "Detector checkpoint",
    )

    detector_settings_path = (
        _required_file(
            cfg[
                "detector_settings_path"
            ],
            "Detector settings",
        )
    )

    classifier_path = _required_file(
        cfg[
            "classifier_path"
        ],
        "Classifier checkpoint",
    )

    calibration_path = _required_file(
        cfg[
            "calibration_path"
        ],
        "Calibration reference",
    )

    sam2_checkpoint_path = (
        _required_file(
            cfg[
                "sam2_checkpoint_path"
            ],
            "SAM2 checkpoint",
        )
    )


    script_paths = (
        _pipeline_script_paths(
            cfg[
                "pipeline_source_root"
            ]
        )
    )


    # -----------------------------------------------------
    # Patch 09b's dependency script locations.
    #
    # We use the actual functions from the supplied 09b,
    # while its supporting feature / classifier / calibration
    # code continues to come from the original validated FYP
    # scripts.
    # -----------------------------------------------------

    pipeline09b.PROJECT_ROOT = (
        cfg[
            "pipeline_source_root"
        ]
    )

    pipeline09b.SCRIPT_02_PATH = (
        script_paths[
            "s02"
        ]
    )

    pipeline09b.SCRIPT_10_PATH = (
        script_paths[
            "s10"
        ]
    )

    pipeline09b.SCRIPT_13_PATH = (
        script_paths[
            "s13"
        ]
    )

    pipeline09b.SCRIPT_15_PATH = (
        script_paths[
            "s15"
        ]
    )

    pipeline09b.SCRIPT_16_PATH = (
        script_paths[
            "s16"
        ]
    )

    pipeline09b.SCRIPT_18_PATH = (
        script_paths[
            "s18"
        ]
    )

    pipeline09b._S18 = None

    # These match the validated 09b new-photo setup.
    pipeline09b.CALIBRATE_SCALE = True
    pipeline09b.CALIBRATE_COLOUR = True
    pipeline09b.RESIZE_TO_TRAINING_SCALE = False


    # -----------------------------------------------------
    # Load exact supporting modules reused by 09b.
    # -----------------------------------------------------

    s02 = pipeline09b.load_module(
        script_paths[
            "s02"
        ],
        "bika_status02_web",
    )

    s10 = pipeline09b.load_module(
        script_paths[
            "s10"
        ],
        "bika_status10_web",
    )

    s13 = pipeline09b.load_module(
        script_paths[
            "s13"
        ],
        "bika_status13_web",
    )

    s15 = pipeline09b.load_module(
        script_paths[
            "s15"
        ],
        "bika_status15_web",
    )

    s16 = pipeline09b.load_module(
        script_paths[
            "s16"
        ],
        "bika_status16_web",
    )


    # -----------------------------------------------------
    # Detector operating point.
    #
    # IMPORTANT:
    # detector_settings.json may still contain the original
    # absolute "weights" field. The website intentionally
    # ignores that path and uses detector_best.pt from the
    # active website model package.
    # -----------------------------------------------------

    det_cfg = json.loads(
        detector_settings_path
        .read_text(
            encoding="utf-8"
        )
    )


    required_detector_keys = (
        "conf",
        "nms_iou",
        "imgsz",
        "max_det",
    )


    missing_keys = [
        key

        for key
        in required_detector_keys

        if key not in det_cfg
    ]


    if missing_keys:

        raise InspectionPipelineError(
            "detector_settings.json is missing "
            "required 09b setting(s): "
            +
            ", ".join(
                missing_keys
            )
        )


    det_cfg[
        "weights"
    ] = str(
        detector_path
    )

    # Optional experiment-34 edge filter, scoped strictly to the ACTIVE model.
    # V1 without 02_edge_filter.json remains unchanged. Do not use the global
    # research-project path from the standalone 09b script.
    edge_filter_path = detector_path.parent / "02_edge_filter.json"
    if edge_filter_path.is_file():
        try:
            edge_cfg = json.loads(edge_filter_path.read_text(encoding="utf-8"))
            if not isinstance(edge_cfg, dict) or not isinstance(edge_cfg.get("adopt"), bool):
                raise ValueError("'adopt' must be a boolean")
            if edge_cfg["adopt"]:
                yellow = float(edge_cfg["edge_min_yellow"])
                border = int(edge_cfg.get("edge_border_px", 2))
                if not (0.0 <= yellow <= 1.0 and 0 <= border <= 64):
                    raise ValueError("invalid edge_min_yellow or edge_border_px")
                det_cfg["edge_min_yellow"] = yellow
                det_cfg["edge_border_px"] = border
        except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
            raise InspectionPipelineError(
                f"Invalid edge filter settings for model {cfg['model_version']}: "
                f"{edge_filter_path} ({exc})"
            ) from exc

    current_app.logger.info(
        "BIKA model %s | edge filter: %s | config: %s",
        cfg["model_version"],
        (f"ON (min_yellow={det_cfg['edge_min_yellow']}, border_px={det_cfg['edge_border_px']})"
         if det_cfg.get("edge_min_yellow") is not None else "OFF"),
        str(edge_filter_path) if edge_filter_path.is_file() else "none",
    )


    # -----------------------------------------------------
    # Calibration reference from active website model package.
    # -----------------------------------------------------

    reference = json.loads(
        calibration_path
        .read_text(
            encoding="utf-8"
        )
    )


    # -----------------------------------------------------
    # GPU models.
    # -----------------------------------------------------

    device = torch.device(
        "cuda"
    )


    detector = YOLO(
        str(
            detector_path
        )
    )

    try:
        detector.to(
            device
        )
    except Exception:
        # Ultralytics will still select CUDA during predict
        # when available; do not fail only because .to() is
        # unsupported by a particular wrapper version.
        pass


    model, ckpt = (
        s15.load_new_classifier(
            classifier_path,
            s13,
            device,
        )
    )


    s02.SAFE_MARGIN_PIXELS = int(
        ckpt[
            "safe_margin_pixels"
        ]
    )


    from sam2.build_sam import (
        build_sam2,
    )

    from sam2.sam2_image_predictor import (
        SAM2ImagePredictor,
    )


    sam_model = build_sam2(
        cfg[
            "sam2_model_config"
        ],
        str(
            sam2_checkpoint_path
        ),
        device="cuda",
        mode="eval",
        apply_postprocessing=False,
    )


    predictor = (
        SAM2ImagePredictor(
            sam_model
        )
    )


    class_meta = (
        get_classifier_ui_metadata(
            str(
                classifier_path
            )
        )
    )


    return {
        "model_version":
            cfg[
                "model_version"
            ],

        "s02":
            s02,

        "s10":
            s10,

        "s13":
            s13,

        "s15":
            s15,

        "s16":
            s16,

        "reference":
            reference,

        "device":
            device,

        "detector":
            detector,

        "predictor":
            predictor,

        "model":
            model,

        "ckpt":
            ckpt,

        "det_cfg":
            det_cfg,

        "class_meta":
            class_meta,

        "paths": {
            "detector":
                str(
                    detector_path
                ),

            "classifier":
                str(
                    classifier_path
                ),

            "sam2":
                str(
                    sam2_checkpoint_path
                ),

            "calibration":
                str(
                    calibration_path
                ),
        },
    }


def get_inspection_context() -> dict:

    global _context
    global _context_signature


    cfg = _context_config()

    signature = _signature(
        cfg
    )


    if (
        _context is not None
        and
        _context_signature
        ==
        signature
    ):

        return _context


    with _context_lock:

        if (
            _context is not None
            and
            _context_signature
            ==
            signature
        ):

            return _context


        _context = _build_context(
            cfg
        )

        _context_signature = (
            signature
        )


        return _context


# =========================================================
# RUNTIME MODEL CACHE CONTROL
# =========================================================

def reset_inspection_model_context() -> None:
    """
    Release the current cached detector / SAM2 / classifier
    context. The next inspection will load the active version.
    """

    global _context
    global _context_signature

    acquired = (
        _inference_lock.acquire(
            blocking=False
        )
    )

    if not acquired:
        raise InspectionPipelineError(
            "An inspection is currently using the model. "
            "Wait for it to finish before switching versions."
        )

    try:
        with _context_lock:
            old_context = _context

            _context = None
            _context_signature = None

        pipeline09b._S18 = None

        get_classifier_ui_metadata.cache_clear()

        if old_context is not None:
            del old_context

        gc.collect()

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    finally:
        _inference_lock.release()


# =========================================================
# RESULT SERIALISATION
# =========================================================

def _mask_polygons(
    pred: dict,
) -> list[list[list[int]]]:

    local = (
        pred[
            "local"
        ]
        .astype(
            np.uint8
        )
    )


    contours, _ = (
        cv2.findContours(
            local,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
    )


    x0, y0, _, _ = (
        pred[
            "box"
        ]
    )


    polygons = []


    for contour in contours:

        if (
            contour is None
            or
            len(contour)
            < 3
        ):

            continue


        perimeter = (
            cv2.arcLength(
                contour,
                True,
            )
        )


        epsilon = max(
            0.8,
            0.0025
            *
            perimeter,
        )


        approx = (
            cv2.approxPolyDP(
                contour,
                epsilon,
                True,
            )
        )


        points = (
            approx
            .reshape(
                -1,
                2,
            )
        )


        if len(points) < 3:
            continue


        polygons.append(
            [
                [
                    int(
                        point[0]
                        +
                        x0
                    ),
                    int(
                        point[1]
                        +
                        y0
                    ),
                ]

                for point
                in points
            ]
        )


    if not polygons:

        x0, y0, x1, y1 = (
            map(
                int,
                pred[
                    "box"
                ],
            )
        )

        polygons = [
            [
                [x0, y0],
                [x1, y0],
                [x1, y1],
                [x0, y1],
            ]
        ]


    return polygons


def _round_probability(
    value,
) -> float:

    return round(
        float(
            value
        ),
        5,
    )


def _serialise_result(
    image_np: np.ndarray,
    result: dict,
    ctx: dict,
) -> dict:

    height, width = (
        image_np.shape[
            :2
        ]
    )


    preds = result[
        "preds"
    ]

    labels = result[
        "labels"
    ]

    probs = result[
        "probs"
    ]

    inside = result[
        "inside"
    ]


    classes = list(
        ctx[
            "s13"
        ].CLASSES
    )


    meta_items = (
        ctx[
            "class_meta"
        ][
            "classes"
        ]
    )


    class_meta = {
        item[
            "name"
        ]:
            item

        for item
        in meta_items
    }


    # -----------------------------------------------------
    # Use the same judged-object ordering as 09b:
    # top-to-bottom, then left-to-right.
    # -----------------------------------------------------

    judged_order = sorted(
        [
            index

            for index, is_inside
            in enumerate(
                inside
            )

            if is_inside
        ],
        key=lambda index:
            (
                round(
                    preds[
                        index
                    ][
                        "cy"
                    ]
                    /
                    80
                ),
                preds[
                    index
                ][
                    "cx"
                ],
            ),
    )


    judged_ids = {
        index:
            number

        for number, index
        in enumerate(
            judged_order,
            start=1,
        )
    }


    edge_order = sorted(
        [
            index

            for index, is_inside
            in enumerate(
                inside
            )

            if not is_inside
        ],
        key=lambda index:
            (
                round(
                    preds[
                        index
                    ][
                        "cy"
                    ]
                    /
                    80
                ),
                preds[
                    index
                ][
                    "cx"
                ],
            ),
    )


    edge_ids = {
        index:
            number

        for number, index
        in enumerate(
            edge_order,
            start=1,
        )
    }


    # -----------------------------------------------------
    # Length vs training normal, same calculation as 09b.
    # -----------------------------------------------------

    length_ratio = [
        None
    ] * len(
        preds
    )


    reference = ctx[
        "reference"
    ]


    if reference is not None:

        for geometry_row, pred_index in enumerate(
            result[
                "geom_index"
            ]
        ):

            length_ratio[
                pred_index
            ] = round(
                float(
                    result[
                        "geometry"
                    ][
                        geometry_row,
                        ctx[
                            "s16"
                        ].MAJOR,
                    ]
                    /
                    reference[
                        "median_major_normal"
                    ]
                ),
                4,
            )


    objects = []


    for index, pred in enumerate(
        preds
    ):

        raw_label = (
            labels[
                index
            ]
        )


        is_inside = bool(
            inside[
                index
            ]
        )


        meta = class_meta.get(
            raw_label,
            {
                "display_name":
                    raw_label
                    .replace(
                        "_",
                        " ",
                    )
                    .title(),

                "colour":
                    "#7A7A7A",

                "decision":
                    (
                        "NORMAL"
                        if raw_label
                        ==
                        "normal"
                        else
                        "DEFECT"
                    ),
            },
        )


        probability_row = {
            class_name:
                _round_probability(
                    probability
                )

            for class_name, probability
            in zip(
                classes,
                probs[
                    index
                ],
            )
        }


        if is_inside:

            review_id = (
                judged_ids[
                    index
                ]
            )

            object_id = (
                f"BSC-{review_id:03d}"
            )

            display_name = (
                meta[
                    "display_name"
                ]
            )

            mask_colour = (
                meta[
                    "colour"
                ]
            )

            decision = (
                "Normal"
                if raw_label
                ==
                "normal"
                else
                "Defect"
            )

            shown_as = (
                raw_label
            )

        else:

            review_id = None

            object_id = (
                "EDGE-"
                f"{edge_ids[index]:03d}"
            )

            display_name = (
                "Edge (Not Judged)"
            )

            mask_colour = (
                EDGE_COLOUR
            )

            decision = (
                "Not Judged"
            )

            shown_as = (
                EDGE_LABEL
            )


        objects.append(
            {
                "object_id":
                    object_id,

                "review_id":
                    review_id,

                "class_name":
                    raw_label,

                "display_name":
                    display_name,

                "shown_as":
                    shown_as,

                "decision":
                    decision,

                "in_safe_zone":
                    is_inside,

                "class_confidence":
                    _round_probability(
                        probs[
                            index
                        ].max()
                    ),

                "detection_confidence":
                    _round_probability(
                        pred[
                            "conf"
                        ]
                    ),

                "probabilities":
                    probability_row,

                "mask_colour":
                    mask_colour,

                "mask_area":
                    int(
                        pred[
                            "area"
                        ]
                    ),

                # Full kept-mask bounding box in original
                # backend image coordinates. The Selected Mask
                # crop uses this instead of deriving a tight box
                # from the simplified SVG polygon.
                "bbox": {
                    "x0":
                        int(
                            pred[
                                "box"
                            ][
                                0
                            ]
                        ),

                    "y0":
                        int(
                            pred[
                                "box"
                            ][
                                1
                            ]
                        ),

                    "x1":
                        int(
                            pred[
                                "box"
                            ][
                                2
                            ]
                        ),

                    "y1":
                        int(
                            pred[
                                "box"
                            ][
                                3
                            ]
                        ),
                },

                "centre": {
                    "x":
                        round(
                            float(
                                pred[
                                    "cx"
                                ]
                            ),
                            2,
                        ),

                    "y":
                        round(
                            float(
                                pred[
                                    "cy"
                                ]
                            ),
                            2,
                        ),
                },

                "length_vs_training_normal":
                    length_ratio[
                        index
                    ],

                "polygons":
                    _mask_polygons(
                        pred
                    ),
            }
        )


    judged_labels = [
        labels[index]

        for index, is_inside
        in enumerate(
            inside
        )

        if is_inside
    ]


    counts = Counter(
        judged_labels
    )


    judged = len(
        judged_labels
    )


    normal = int(
        counts.get(
            "normal",
            0,
        )
    )


    defect = (
        judged
        -
        normal
    )


    yield_percent = (
        None

        if judged
        ==
        0

        else

        round(
            100.0
            *
            normal
            /
            judged,
            2,
        )
    )


    defect_counts = []


    for item in meta_items:

        class_name = (
            item[
                "name"
            ]
        )


        if item[
            "is_normal"
        ]:

            continue


        count = int(
            counts.get(
                class_name,
                0,
            )
        )


        defect_counts.append(
            {
                "class_name":
                    class_name,

                "display_name":
                    item[
                        "display_name"
                    ],

                "colour":
                    item[
                        "colour"
                    ],

                "count":
                    count,
            }
        )


    keep_rows = [
        geometry_row

        for geometry_row, pred_index
        in enumerate(
            result[
                "geom_index"
            ]
        )

        if inside[
            pred_index
        ]
    ]


    empty = np.zeros(
        (
            0,
            0,
        ),
        dtype=np.float32,
    )


    domain = (
        pipeline09b.domain_check(
            (
                result[
                    "geometry_raw"
                ][
                    keep_rows
                ]
                if keep_rows
                else empty
            ),
            (
                result[
                    "geometry"
                ][
                    keep_rows
                ]
                if keep_rows
                else empty
            ),
            ctx[
                "ckpt"
            ],
            width,
            height,
            result[
                "calibration"
            ],
            reference,
            ctx[
                "s16"
            ],
        )
    )


    return {
        "ok":
            True,

        "image": {
            "width":
                int(
                    width
                ),

            "height":
                int(
                    height
                ),
        },

        "model": {
            "version":
                ctx[
                    "model_version"
                ],

            "classifier":
                Path(
                    ctx[
                        "paths"
                    ][
                        "classifier"
                    ]
                ).name,

            "detector":
                Path(
                    ctx[
                        "paths"
                    ][
                        "detector"
                    ]
                ).name,

            "sam2":
                Path(
                    ctx[
                        "paths"
                    ][
                        "sam2"
                    ]
                ).name,
        },

        "operating_point": {
            "conf":
                float(
                    ctx[
                        "det_cfg"
                    ][
                        "conf"
                    ]
                ),

            "nms_iou":
                float(
                    ctx[
                        "det_cfg"
                    ][
                        "nms_iou"
                    ]
                ),

            "imgsz":
                int(
                    ctx[
                        "det_cfg"
                    ][
                        "imgsz"
                    ]
                ),
        },

        "summary": {
            "detected_boxes":
                int(
                    result[
                        "n_detected"
                    ]
                ),

            "sam2_masks":
                int(
                    result[
                        "n_masks"
                    ]
                ),

            "dedup_dropped":
                int(
                    result[
                        "n_dedup_dropped"
                    ]
                ),

            "kept":
                len(
                    preds
                ),

            "judged":
                judged,

            "edge_not_judged":
                int(
                    len(
                        preds
                    )
                    -
                    judged
                ),

            "normal":
                normal,

            "defect":
                defect,

            "yield_percent":
                yield_percent,
        },

        "defect_counts":
            defect_counts,

        "objects":
            objects,

        "calibration":
            result[
                "calibration"
            ],

        "domain_check":
            domain,

        "timing":
            result[
                "timing"
            ],
    }


# =========================================================
# PUBLIC IMAGE INFERENCE
# =========================================================

def _report_progress(
    callback,
    progress: int,
    stage: str,
):
    if callback is not None:
        callback(
            int(progress),
            str(stage),
        )


def _check_cancel(
    cancel_check,
):
    if (
        cancel_check is not None
        and
        cancel_check()
    ):
        raise InspectionCancelled(
            "Inspection cancelled by user."
        )


def _run_system_with_progress(
    image,
    image_np,
    ctx,
    progress_callback=None,
    cancel_check=None,
):
    """
    Same execution order as 09b.run_system(), with only two
    additions:
      1. stage progress callbacks for the web UI
      2. cooperative cancellation checks between heavy stages

    Cancellation cannot interrupt a CUDA kernel in the middle
    of YOLO / SAM2 / classifier execution. It takes effect as
    soon as the current stage returns.
    """

    H, W = image_np.shape[:2]

    s02 = ctx["s02"]
    s10 = ctx["s10"]
    s13 = ctx["s13"]
    s15 = ctx["s15"]
    s16 = ctx["s16"]

    _check_cancel(
        cancel_check
    )

    _report_progress(
        progress_callback,
        18,
        "Running YOLO detector",
    )

    pipeline09b.sync()
    t0 = time.perf_counter()

    boxes, confs = pipeline09b.detect(
        ctx["detector"],
        image,
        ctx["det_cfg"],
    )

    pipeline09b.sync()
    t1 = time.perf_counter()

    _check_cancel(
        cancel_check
    )

    _report_progress(
        progress_callback,
        35,
        "Generating SAM2 masks",
    )

    preds = pipeline09b.segment(
        ctx["predictor"],
        image_np,
        boxes,
        confs,
        s10,
        s15.BOX_BATCH,
    )

    _check_cancel(
        cancel_check
    )

    _report_progress(
        progress_callback,
        61,
        "Removing duplicates",
    )

    kept, n_dropped = (
        s15.suppress_contained(
            preds,
            s15.DEDUP_CONTAINMENT,
            s10,
        )
    )

    n_before = len(
        kept
    )

    kept = pipeline09b.filter_low_conf(
        kept,
        ctx["det_cfg"],
        s10,
    )

    kept = pipeline09b.filter_gaps(
        kept,
        image_np,
        ctx["det_cfg"],
    )

    # After mask deduplication and gap filtering, before safe-zone / classifier.
    # When edge_min_yellow is absent (V1), the function is a no-op.
    kept = pipeline09b.filter_edge_objects(
        kept,
        image_np,
        ctx["det_cfg"],
    )

    n_dropped += (
        n_before
        -
        len(
            kept
        )
    )

    width_px = (
        pipeline09b.median_width_px(
            kept,
            s10,
        )
    )

    margin = (
        pipeline09b.adapt_safe_margin(
            width_px,
            ctx["ckpt"][
                "safe_margin_pixels"
            ],
            len(
                kept
            ),
            s02,
        )
    )

    inside = [
        s02.inside_safe_zone(
            pred["cx"],
            pred["cy"],
            W,
            H,
        )
        for pred
        in kept
    ]

    pipeline09b.sync()
    t2 = time.perf_counter()

    _check_cancel(
        cancel_check
    )

    _report_progress(
        progress_callback,
        72,
        "Classifying and calibrating",
    )

    (
        labels,
        probs,
        geometry_raw,
        geometry,
        geom_index,
        calib,
    ) = pipeline09b.classify(
        kept,
        inside,
        image,
        image_np,
        ctx["model"],
        ctx["ckpt"],
        s02,
        s13,
        s16,
        ctx["reference"],
        ctx["device"],
    )

    pipeline09b.sync()
    t3 = time.perf_counter()

    _check_cancel(
        cancel_check
    )

    _report_progress(
        progress_callback,
        91,
        "Preparing inspection result",
    )

    timing = {
        "detector_ms":
            round(
                (t1 - t0)
                *
                1000,
                1,
            ),

        "sam2_and_dedup_ms":
            round(
                (t2 - t1)
                *
                1000,
                1,
            ),

        "classifier_ms":
            round(
                (t3 - t2)
                *
                1000,
                1,
            ),

        "total_ms":
            round(
                (t3 - t0)
                *
                1000,
                1,
            ),
    }

    return {
        "n_detected":
            len(
                boxes
            ),

        "n_masks":
            len(
                preds
            ),

        "n_dedup_dropped":
            n_dropped,

        "preds":
            kept,

        "inside":
            inside,

        "labels":
            labels,

        "probs":
            probs,

        "geometry_raw":
            geometry_raw,

        "geometry":
            geometry,

        "geom_index":
            geom_index,

        "calibration":
            dict(
                calib,
                safe_margin_px=
                    margin,
                median_width_px=(
                    None
                    if width_px is None
                    else
                    round(
                        width_px,
                        1,
                    )
                ),
            ),

        "timing":
            timing,
    }


def inspect_image_bytes_with_progress(
    image_bytes: bytes,
    progress_callback=None,
    cancel_check=None,
) -> dict:

    _report_progress(
        progress_callback,
        2,
        "Reading uploaded image",
    )

    _check_cancel(
        cancel_check
    )

    try:

        image = (
            Image.open(
                BytesIO(
                    image_bytes
                )
            )
            .convert(
                "RGB"
            )
        )

    except Exception as exc:

        raise InspectionPipelineError(
            "The uploaded file is not a valid image."
        ) from exc


    image_np = (
        np.asarray(
            image
        )
        .copy()
    )


    _report_progress(
        progress_callback,
        5,
        "Loading inspection models",
    )

    ctx = get_inspection_context()

    _check_cancel(
        cancel_check
    )


    # -----------------------------------------------------
    # One CUDA inference at a time.
    #
    # Acquire with a timeout loop so a job waiting for the
    # GPU can still be cancelled.
    # -----------------------------------------------------

    _report_progress(
        progress_callback,
        12,
        "Waiting for GPU",
    )

    acquired = False

    try:

        while not acquired:

            _check_cancel(
                cancel_check
            )

            acquired = (
                _inference_lock.acquire(
                    timeout=0.2
                )
            )


        _check_cancel(
            cancel_check
        )


        try:

            result = (
                _run_system_with_progress(
                    image,
                    image_np,
                    ctx,
                    progress_callback=
                        progress_callback,
                    cancel_check=
                        cancel_check,
                )
            )

        except torch.cuda.OutOfMemoryError as exc:

            torch.cuda.empty_cache()

            raise InspectionPipelineError(
                "CUDA ran out of memory. Close other GPU "
                "training/inference processes and try again."
            ) from exc

    finally:

        if acquired:
            _inference_lock.release()


    _check_cancel(
        cancel_check
    )

    _report_progress(
        progress_callback,
        95,
        "Building mask data",
    )

    serialised = _serialise_result(
        image_np,
        result,
        ctx,
    )

    _check_cancel(
        cancel_check
    )

    _report_progress(
        progress_callback,
        100,
        "Inspection complete",
    )

    return serialised


def inspect_image_bytes(
    image_bytes: bytes,
) -> dict:
    """
    Backward-compatible synchronous wrapper.
    """

    return inspect_image_bytes_with_progress(
        image_bytes,
    )
