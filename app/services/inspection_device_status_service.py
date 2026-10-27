"""Read-only, non-initialising device diagnostics for BIKA Inspection.

IMPORTANT: Never call get_inspection_context() here. That would load 09b
weights and SAM2 just because a browser opened a page.
"""
from __future__ import annotations

from typing import Any


def _parameters_device(model: Any) -> str | None:
    """Return actual PyTorch parameter device, not an intended device."""
    if model is None:
        return None
    try:
        parameters = model.parameters()
        parameter = next(parameters, None)
        if parameter is not None:
            return str(parameter.device)
    except (AttributeError, StopIteration, TypeError, RuntimeError):
        pass
    try:
        for buffer in model.buffers():
            return str(buffer.device)
    except (AttributeError, TypeError, RuntimeError):
        pass
    return None


def runtime_model_device_snapshot() -> dict:
    """Inspect already cached model weights. Does not allocate models."""
    # These modules are already part of the validated inspection pipeline.
    # Failure to load an optional diagnostic must never break the web page.
    try:
        import torch
        from app.services import inspection_pipeline_service as pipeline
    except (ImportError, RuntimeError) as exc:
        return {
            "cuda_available": False,
            "cuda_name": None,
            "loaded": False,
            "device": "unknown",
            "label": "Unable to check",
            "model_version": None,
            "components": {},
            "note": f"Device diagnostics unavailable ({type(exc).__name__}).",
        }

    try:
        cuda_available = bool(torch.cuda.is_available())
    except Exception:
        cuda_available = False
    cuda_name = None
    if cuda_available:
        try:
            cuda_name = str(torch.cuda.get_device_name(torch.cuda.current_device()))
        except Exception:
            cuda_name = None

    # A completed prior run can leave the cached 09b context available.
    # It is NOT evidence that inference is running at this instant.
    context = getattr(pipeline, "_context", None)
    if not isinstance(context, dict):
        return {
            "cuda_available": cuda_available,
            "cuda_name": cuda_name,
            "loaded": False,
            "device": "not_loaded",
            "label": "Not loaded",
            "model_version": None,
            "components": {},
            "note": "Run an inspection to verify the actual model devices.",
        }

    detector = getattr(context.get("detector"), "model", None)
    sam2 = getattr(context.get("predictor"), "model", None)
    classifier = context.get("model")
    components = {
        "YOLO": _parameters_device(detector),
        "SAM2": _parameters_device(sam2),
        "Classifier": _parameters_device(classifier),
    }
    known = [device for device in components.values() if device is not None]
    if len(known) == 3 and all(dev.startswith("cuda") for dev in known):
        device = "gpu"
        label = "GPU (CUDA)"
    elif len(known) == 3 and all(dev.startswith("cpu") for dev in known):
        device = "cpu"
        label = "CPU"
    elif len(known) == 3:
        device = "mixed"
        label = "Mixed CPU / GPU"
    else:
        device = "unverified"
        label = "Not fully verified"

    return {
        "cuda_available": cuda_available,
        "cuda_name": cuda_name,
        "loaded": True,
        "device": device,
        "label": label,
        "model_version": str(context.get("model_version") or "") or None,
        "components": components,
        "note": (
            "Reports where the loaded YOLO, SAM2 and Classifier parameters reside; "
            "video decoding, optical flow, and MP4 encoding may still use CPU."
        ),
    }
