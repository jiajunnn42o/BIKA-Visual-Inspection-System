BIKA Visual Inspection Model Package
Version: v1_2026-10-10

============================================================
1. MODEL PACKAGE
============================================================

This model package is used by the BIKA Visual Inspection System.

The website inference pipeline must remain consistent with the
validated 09b evaluation pipeline.

Pipeline:

Detection
-> SAM2 Segmentation
-> Deduplication
-> Safe Zone Filtering
-> 320x320 Grayscale Masked Crop
-> Geometry Features
-> Relative Colour Features
-> 5-Class Classification
-> Calibration
-> Final Decision


============================================================
2. FILES
============================================================

detector_best.pt

Purpose:
YOLOv8s biscuit detector.

Original source:
D:\BDS\FYP2\sam2_large_project\
runs\yolov8_detect\np_all_s42\weights\best.pt


detector_settings.json

Purpose:
Detector operating point.

Original source:
D:\BDS\FYP2\sam2_large_project\
outputs\status\combined\
27_detector_new_photos\
03_detector_operating_point.json

Operating settings:

Confidence Threshold: 0.20
NMS IoU Threshold: 0.60
Image Size: 1280

IMPORTANT:
The "weights" field inside this JSON may contain the original
absolute training path.

The website must NOT load the detector using that path.

The website must load:
detector_best.pt

from this model version folder and only use the operating
parameters from detector_settings.json.


classifier.pt

Purpose:
5-class biscuit defect classifier.

Original source:
D:\BDS\FYP2\sam2_large_project\
models\status\combined\
23_classifier_new_photos\
v2_industry\
B_old_new.pt

The classifier package contains the class information and
feature/calibration information required by the validated
classification pipeline.


calibration_reference.json

Purpose:
Image size and colour robustness calibration reference.

Original source:
D:\BDS\FYP2\sam2_large_project\
outputs\status\combined\
16_robustness_calibration\
01_reference.json


============================================================
3. SAM2
============================================================

SAM2 is shared across model versions and is stored separately:

website_models\sam2\sam2.1_hiera_large.pt

Model:
SAM2.1 Hiera Large

Configuration:
configs/sam2.1/sam2.1_hiera_l.yaml


============================================================
4. VALIDATED RESULTS
============================================================

Validated pipeline results:

Macro-F1: 66.6%
Reject-F1: 91.9%

These results correspond to this model combination and the
validated 09b inference pipeline.

Changing or skipping any inference stage may produce results
that are different from the reported evaluation results.


============================================================
5. WEBSITE INTEGRATION
============================================================

Website model version:

v1_2026-10-10

The website should reference this folder through a central
model configuration rather than hard-coded absolute paths.

Example:

MODEL_VERSION = "v1_2026-10-10"

MODEL_DIR =
website_models / MODEL_VERSION


============================================================
6. MODEL REPLACEMENT
============================================================

For a future model version:

1. Create a new folder, for example:

   website_models\v2_2026-11-01\

2. Copy the new model files into the new folder.

3. Update MODEL_VERSION in the website configuration.

4. Do not overwrite this v1 folder.

This allows immediate rollback to the previously validated
model package.


============================================================
7. IMPORTANT NOTES
============================================================

- Original training/evaluation files must only be COPIED.
- Do not move or delete the original files.
- Do not change the validated inference sequence.
- SAM2-L should preferably run on GPU.
- CPU inference may be significantly slower.
- Model files should not be placed inside app/static.
- Large .pt files should not be pushed to normal GitHub
  without an appropriate model-storage strategy.