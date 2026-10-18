from __future__ import annotations

import time
import uuid
from pathlib import Path

from threading import (
    Event,
    Lock,
    Thread,
)

from flask import (
    current_app,
    jsonify,
    render_template,
    send_file,
    request,
    url_for,
)

from flask_login import (
    current_user,
    login_required,
)

from app.main import (
    main_bp,
)

from app.services.inspection_model_metadata import (
    get_classifier_ui_metadata,
)

from app.services.inspection_pipeline_service import (
    InspectionCancelled,
    InspectionPipelineError,
    inspect_image_bytes_with_progress,
)

from app.services.video_inspection_service import (
    inspect_video_bytes_with_progress,
)
from app.services.video_safe_zone import validate_zone

from app.services.inspection_record_service import (
    persist_completed_image_inspection,
)


# =========================================================
# ALLOWED IMAGE TYPES
# =========================================================

ALLOWED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}


# =========================================================
# IN-MEMORY INSPECTION JOBS
#
# Current development implementation.
#
# Suitable for:
# - Local Flask development
# - Single-process server
#
# Future production:
# Move job state to Redis / database-backed queue when
# multiple workers or cloud GPU workers are introduced.
# =========================================================

_INSPECTION_JOBS = {}

_INSPECTION_JOBS_LOCK = Lock()

_JOB_TTL_SECONDS = (
    30
    *
    60
)


# =========================================================
# ACTIVE JOB CHECK
#
# Used by Model Management.
# Prevents switching the active model while an inspection
# is currently queued or running.
# =========================================================

def has_active_inspection_jobs() -> bool:

    with _INSPECTION_JOBS_LOCK:

        return any(

            job.get(
                "status"
            )
            in {
                "queued",
                "running",
            }

            for job
            in _INSPECTION_JOBS.values()
        )


# =========================================================
# JOB CLEANUP
# =========================================================

def _cleanup_jobs():

    now = time.time()


    with _INSPECTION_JOBS_LOCK:

        expired = [

            job_id

            for job_id, job
            in _INSPECTION_JOBS.items()

            if (
                now
                -
                job[
                    "updated_at"
                ]
                >
                _JOB_TTL_SECONDS
            )
        ]


        for job_id in expired:

            expired_job = _INSPECTION_JOBS.pop(job_id, None)
            if expired_job is not None:
                output = expired_job.get("annotated_video_path")
                if output:
                    # Output paths are generated inside app.instance_path;
                    # users cannot supply a filesystem path.
                    Path(output).unlink(missing_ok=True)
                    Path(output).with_suffix(".tracks.json").unlink(missing_ok=True)


# =========================================================
# GET JOB FOR CURRENT USER
# =========================================================

def _job_for_user(
    job_id: str,
):

    with _INSPECTION_JOBS_LOCK:

        job = (
            _INSPECTION_JOBS.get(
                job_id
            )
        )


        if (
            job is None
            or
            str(
                job[
                    "user_id"
                ]
            )
            !=
            str(
                current_user.get_id()
            )
        ):

            return None


        return job


# =========================================================
# UPDATE JOB PROGRESS
# =========================================================

def _set_job_progress(
    job_id: str,
    progress: int,
    stage: str,
):

    with _INSPECTION_JOBS_LOCK:

        job = (
            _INSPECTION_JOBS.get(
                job_id
            )
        )


        if job is None:

            return


        job[
            "progress"
        ] = max(
            0,
            min(
                100,
                int(
                    progress
                ),
            ),
        )


        job[
            "stage"
        ] = str(
            stage
        )


        job[
            "updated_at"
        ] = time.time()


# =========================================================
# BACKGROUND INSPECTION WORKER
# =========================================================

def _run_job(
    app,
    job_id: str,
    image_bytes: bytes,
    source_filename: str,
    user_id: str,
):

    with app.app_context():

        # -------------------------------------------------
        # Mark job as running
        # -------------------------------------------------

        with _INSPECTION_JOBS_LOCK:

            job = (
                _INSPECTION_JOBS.get(
                    job_id
                )
            )


            if job is None:

                return


            job[
                "status"
            ] = "running"


            job[
                "stage"
            ] = (
                "Starting inspection"
            )


            job[
                "updated_at"
            ] = time.time()


            cancel_event = (
                job[
                    "cancel_event"
                ]
            )


        try:

            # -------------------------------------------------
            # Run exact BIKA inspection pipeline
            #
            # YOLO
            # → SAM2
            # → Dedup
            # → Safe Zone
            # → Crop + Geometry + Relative Colour
            # → Classifier
            # → Calibration
            # -------------------------------------------------

            result = (
                inspect_image_bytes_with_progress(
                    image_bytes,

                    progress_callback=(
                        lambda progress, stage:
                            _set_job_progress(
                                job_id,
                                progress,
                                stage,
                            )
                    ),

                    cancel_check=(
                        cancel_event.is_set
                    ),
                )
            )


            # -------------------------------------------------
            # Cancellation may be requested during a GPU stage.
            # It becomes effective once the current stage ends.
            # -------------------------------------------------

            if cancel_event.is_set():

                raise InspectionCancelled(
                    "Inspection cancelled by user."
                )


            # -------------------------------------------------
            # Persist real inspection record + media artifacts
            # -------------------------------------------------

            _set_job_progress(
                job_id,
                100,
                "Saving inspection record",
            )

            persistence_message = ""

            try:

                record = persist_completed_image_inspection(
                    source_bytes=image_bytes,
                    source_filename=source_filename,
                    result=result,
                    user_id=user_id,
                )

                result["record"] = {
                    "saved": True,
                    "batch_id": record.batch_id,
                    "storage_backend": record.storage_backend,
                    "original_key": record.original_key,
                    "preview_key": record.preview_key,
                    "result_key": record.result_key,
                }

            except Exception:

                current_app.logger.exception(
                    "Inspection completed but persistence failed."
                )

                persistence_message = (
                    "Inspection completed, but the report record "
                    "could not be saved. Check the server log."
                )

                result["record"] = {
                    "saved": False,
                }


            # -------------------------------------------------
            # Complete
            # -------------------------------------------------

            with _INSPECTION_JOBS_LOCK:

                job = (
                    _INSPECTION_JOBS.get(
                        job_id
                    )
                )


                if job is None:

                    return


                job[
                    "status"
                ] = "complete"


                job[
                    "progress"
                ] = 100


                job[
                    "stage"
                ] = (
                    "Inspection complete"
                )


                job[
                    "result"
                ] = result


                job[
                    "message"
                ] = persistence_message


                job[
                    "updated_at"
                ] = time.time()


        # =================================================
        # CANCELLED
        # =================================================

        except InspectionCancelled:

            with _INSPECTION_JOBS_LOCK:

                job = (
                    _INSPECTION_JOBS.get(
                        job_id
                    )
                )


                if job is None:

                    return


                job[
                    "status"
                ] = "cancelled"


                job[
                    "stage"
                ] = (
                    "Inspection cancelled"
                )


                job[
                    "message"
                ] = (
                    "Inspection cancelled."
                )


                job[
                    "updated_at"
                ] = time.time()


        # =================================================
        # EXPECTED PIPELINE ERROR
        # =================================================

        except InspectionPipelineError as exc:

            current_app.logger.warning(
                "Inspection pipeline error: %s",
                exc,
            )


            with _INSPECTION_JOBS_LOCK:

                job = (
                    _INSPECTION_JOBS.get(
                        job_id
                    )
                )


                if job is None:

                    return


                job[
                    "status"
                ] = "failed"


                job[
                    "stage"
                ] = (
                    "Inspection failed"
                )


                job[
                    "message"
                ] = str(
                    exc
                )


                job[
                    "updated_at"
                ] = time.time()


        # =================================================
        # UNEXPECTED ERROR
        # =================================================

        except Exception:

            current_app.logger.exception(
                "Unexpected image inspection failure."
            )


            with _INSPECTION_JOBS_LOCK:

                job = (
                    _INSPECTION_JOBS.get(
                        job_id
                    )
                )


                if job is None:

                    return


                job[
                    "status"
                ] = "failed"


                job[
                    "stage"
                ] = (
                    "Inspection failed"
                )


                job[
                    "message"
                ] = (
                    "Inspection failed unexpectedly. "
                    "Check the server log for details."
                )


                job[
                    "updated_at"
                ] = time.time()


# =========================================================
# INSPECTION PAGE
#
# GET /inspection
#
# This route was previously lost when routes.py was replaced
# by the Dashboard implementation.
# =========================================================

@main_bp.route(
    "/inspection",
    methods=[
        "GET",
    ],
)
@login_required
def inspection():

    # -----------------------------------------------------
    # Read class metadata from the CURRENT active
    # classifier instead of hard-coding class names.
    # -----------------------------------------------------

    model_metadata = (
        get_classifier_ui_metadata(
            str(
                current_app.config[
                    "CLASSIFIER_PATH"
                ]
            )
        )
    )


    return render_template(
        "inspection.html",

        user=current_user,

        inspection_classes=(
            model_metadata[
                "classes"
            ]
        ),

        inspection_model_version=(
            current_app.config.get(
                "MODEL_VERSION",
                "Not configured",
            )
        ),

        inspection_classifier_file=(
            model_metadata[
                "classifier_file"
            ]
        ),
    )


# =========================================================
# START IMAGE INSPECTION
#
# POST /inspection/run-image
# =========================================================

@main_bp.route(
    "/inspection/run-image",
    methods=[
        "POST",
    ],
)
@login_required
def run_inspection_image():

    _cleanup_jobs()


    # -----------------------------------------------------
    # Uploaded file
    # -----------------------------------------------------

    uploaded_file = (
        request.files.get(
            "file"
        )
    )


    if (
        uploaded_file is None
        or
        not uploaded_file.filename
    ):

        return jsonify(
            ok=False,

            message=(
                "Please select an image first."
            ),
        ), 400


    filename = (
        uploaded_file.filename
        .strip()
    )


    # -----------------------------------------------------
    # File extension
    # -----------------------------------------------------

    extension = (

        (
            "."
            +
            filename
            .rsplit(
                ".",
                1,
            )[
                -1
            ]
            .lower()
        )

        if "." in filename

        else ""
    )


    if (
        extension
        not in
        ALLOWED_IMAGE_EXTENSIONS
    ):

        return jsonify(
            ok=False,

            message=(
                "Supported image formats are "
                "JPG, JPEG, PNG and WEBP."
            ),
        ), 400


    # -----------------------------------------------------
    # Read bytes
    # -----------------------------------------------------

    image_bytes = (
        uploaded_file.read()
    )


    if not image_bytes:

        return jsonify(
            ok=False,

            message=(
                "The uploaded image is empty."
            ),
        ), 400


    # -----------------------------------------------------
    # File size limit
    # -----------------------------------------------------

    max_image_mb = int(
        current_app.config.get(
            "INSPECTION_MAX_IMAGE_MB",
            10,
        )
    )


    max_bytes = (
        max_image_mb
        *
        1024
        *
        1024
    )


    if (
        len(
            image_bytes
        )
        >
        max_bytes
    ):

        return jsonify(
            ok=False,

            message=(
                "Image size must not exceed "
                f"{max_image_mb} MB."
            ),
        ), 413


    # -----------------------------------------------------
    # Create job
    # -----------------------------------------------------

    job_id = (
        uuid.uuid4()
        .hex
    )


    cancel_event = (
        Event()
    )


    now = (
        time.time()
    )


    with _INSPECTION_JOBS_LOCK:

        _INSPECTION_JOBS[
            job_id
        ] = {

            "job_id":
                job_id,

            "user_id":
                str(
                    current_user.get_id()
                ),

            "status":
                "queued",

            "progress":
                0,

            "stage":
                "Queued",

            "message":
                "",

            "result":
                None,

            "source_filename":
                filename,

            "cancel_event":
                cancel_event,

            "created_at":
                now,

            "updated_at":
                now,
        }


    # -----------------------------------------------------
    # Obtain real Flask app object for background thread
    # -----------------------------------------------------

    app = (
        current_app
        ._get_current_object()
    )


    worker = Thread(
        target=_run_job,

        args=(
            app,
            job_id,
            image_bytes,
            filename,
            str(
                current_user.get_id()
            ),
        ),

        daemon=True,

        name=(
            f"inspection-{job_id[:8]}"
        ),
    )


    worker.start()


    # -----------------------------------------------------
    # Return job endpoints
    # -----------------------------------------------------

    return jsonify(
        ok=True,

        job_id=job_id,

        status_url=url_for(
            "main.inspection_job_status",

            job_id=job_id,
        ),

        cancel_url=url_for(
            "main.cancel_inspection_job",

            job_id=job_id,
        ),
    ), 202


# =========================================================
# INSPECTION JOB STATUS
#
# GET /inspection/job/<job_id>
# =========================================================

@main_bp.route(
    "/inspection/job/<job_id>",
    methods=[
        "GET",
    ],
)
@login_required
def inspection_job_status(
    job_id,
):

    _cleanup_jobs()


    job = (
        _job_for_user(
            job_id
        )
    )


    if job is None:

        return jsonify(
            ok=False,

            message=(
                "Inspection job was not found."
            ),
        ), 404


    with _INSPECTION_JOBS_LOCK:

        payload = {

            "ok":
                True,

            "job_id":
                job[
                    "job_id"
                ],

            "status":
                job[
                    "status"
                ],

            "progress":
                job[
                    "progress"
                ],

            "stage":
                job[
                    "stage"
                ],

            "message":
                job[
                    "message"
                ],
        }


        # -------------------------------------------------
        # Only send full inference result once completed
        # -------------------------------------------------

        if (
            job[
                "status"
            ]
            ==
            "complete"
        ):

            result = job["result"]
            # URL generation needs the CURRENT request context, not the
            # background inference thread's application context.
            if result and result.get("kind") == "video" and result.get("annotated_video"):
                annotated_meta = dict(result["annotated_video"])
                annotated_meta["url"] = url_for(
                    "main.inspection_annotated_video", job_id=job_id
                )
                annotated_meta["download_url"] = url_for(
                    "main.inspection_annotated_video", job_id=job_id, download=1
                )
                annotated_meta["tracks_url"] = url_for(
                    "main.inspection_video_tracks", job_id=job_id
                )
                payload["result"] = dict(result, annotated_video=annotated_meta)
            else:
                payload["result"] = result


    return jsonify(
        payload
    )


# =========================================================
# CANCEL INSPECTION
#
# POST /inspection/job/<job_id>/cancel
# =========================================================

@main_bp.route(
    "/inspection/job/<job_id>/cancel",
    methods=[
        "POST",
    ],
)
@login_required
def cancel_inspection_job(
    job_id,
):

    job = (
        _job_for_user(
            job_id
        )
    )


    if job is None:

        return jsonify(
            ok=False,

            message=(
                "Inspection job was not found."
            ),
        ), 404


    with _INSPECTION_JOBS_LOCK:

        # -------------------------------------------------
        # Already finished
        # -------------------------------------------------

        if (
            job[
                "status"
            ]
            in {
                "complete",
                "failed",
                "cancelled",
            }
        ):

            return jsonify(
                ok=True,

                status=(
                    job[
                        "status"
                    ]
                ),
            )


        # -------------------------------------------------
        # Signal cancellation
        #
        # GPU work cannot necessarily stop in the middle of
        # one stage. Pipeline checks cancellation between
        # stages.
        # -------------------------------------------------

        job[
            "cancel_event"
        ].set()


        job[
            "stage"
        ] = (
            "Cancelling after current stage"
        )


        job[
            "updated_at"
        ] = time.time()


    return jsonify(
        ok=True,

        status="cancelling",
    ), 202

# =========================================================
# BOUNDED SAMPLED VIDEO INSPECTION
# Reuses the exact 09b image model for sampled video frames.
# Do not treat summed detections as unique biscuits.
# =========================================================

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm"}
MAX_VIDEO_UPLOAD_BYTES = 80 * 1024 * 1024

def _run_video_job(app, job_id: str, video_bytes: bytes, filename: str, safe_zone):
    with app.app_context():
        with _INSPECTION_JOBS_LOCK:
            job = _INSPECTION_JOBS.get(job_id)
            if job is None:
                return
            job["status"] = "running"
            job["stage"] = "Preparing video frames"
            job["updated_at"] = time.time()
            cancel_event = job["cancel_event"]

        # A generated, opaque job identifier is the only filename component.
        # Output is not in /static and is accessible ONLY through the
        # login-protected, per-user inspection video route.
        output_path = Path(app.instance_path) / "video_inspections" / f"{job_id}.mp4"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        completed = False
        try:
            result = inspect_video_bytes_with_progress(
                video_bytes, filename=filename, output_path=output_path,
                safe_zone=safe_zone,
                progress_callback=lambda p, stage: _set_job_progress(job_id, p, stage),
                cancel_check=cancel_event.is_set,
            )
            if cancel_event.is_set():
                raise InspectionCancelled("Video inspection cancelled by user.")
            with _INSPECTION_JOBS_LOCK:
                job = _INSPECTION_JOBS.get(job_id)
                if job is not None:
                    job.update(status="complete", progress=100,
                               stage="Annotated MP4 export complete", result=result,
                               annotated_video_path=str(output_path),
                               message="Annotated MP4 ready. New biscuit entries trigger AI and full colour masks follow tracked objects.",
                               updated_at=time.time())
                    completed = True
        except InspectionCancelled:
            with _INSPECTION_JOBS_LOCK:
                job = _INSPECTION_JOBS.get(job_id)
                if job is not None:
                    job.update(status="cancelled", stage="Inspection cancelled",
                               message="Inspection cancelled.", updated_at=time.time())
        except InspectionPipelineError as exc:
            current_app.logger.warning("Video inspection error: %s", exc)
            with _INSPECTION_JOBS_LOCK:
                job = _INSPECTION_JOBS.get(job_id)
                if job is not None:
                    job.update(status="failed", stage="Video inspection failed",
                               message=str(exc), updated_at=time.time())
        except Exception:
            current_app.logger.exception("Unexpected video inspection failure.")
            with _INSPECTION_JOBS_LOCK:
                job = _INSPECTION_JOBS.get(job_id)
                if job is not None:
                    job.update(status="failed", stage="Video inspection failed",
                               message="Video inspection failed unexpectedly. Check the server log.",
                               updated_at=time.time())
        finally:
            if not completed:
                output_path.unlink(missing_ok=True)
                output_path.with_suffix(".tracks.json").unlink(missing_ok=True)


@main_bp.route("/inspection/video/<job_id>/annotated.mp4", methods=["GET"])
@login_required
def inspection_annotated_video(job_id):
    _cleanup_jobs()
    job = _job_for_user(job_id)
    if job is None or job.get("status") != "complete":
        return jsonify(ok=False, message="Annotated video is not available."), 404
    path = job.get("annotated_video_path")
    if not path or not Path(path).is_file():
        return jsonify(ok=False, message="Annotated video has expired."), 404
    download = request.args.get("download") == "1"
    response = send_file(
        path, mimetype="video/mp4", conditional=True,
        as_attachment=download, download_name=f"BIKA_annotated_{job_id[:8]}.mp4",
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@main_bp.route("/inspection/video/<job_id>/tracks.json", methods=["GET"])
@login_required
def inspection_video_tracks(job_id):
    """Only the originating user may read this video's clickable track data."""
    _cleanup_jobs()
    job = _job_for_user(job_id)
    if job is None or job.get("status") != "complete":
        return jsonify(ok=False, message="Tracking data is not available."), 404
    output_path = job.get("annotated_video_path")
    if not output_path:
        return jsonify(ok=False, message="Tracking data has expired."), 404
    path = Path(output_path).with_suffix(".tracks.json")
    if not path.is_file():
        return jsonify(ok=False, message="Tracking data has expired."), 404
    response = send_file(path, mimetype="application/json", conditional=True)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@main_bp.route("/inspection/run-video", methods=["POST"])
@login_required
def run_inspection_video():
    _cleanup_jobs()
    with _INSPECTION_JOBS_LOCK:
        if any(str(job.get("user_id")) == str(current_user.get_id())
               and job.get("status") in {"queued", "running"}
               for job in _INSPECTION_JOBS.values()):
            return jsonify(ok=False, message="Another inspection is already running. Wait for it to finish or cancel it."), 409
    uploaded_file = request.files.get("file")
    if not uploaded_file or not uploaded_file.filename:
        return jsonify(ok=False, message="Please select a video first."), 400
    filename = uploaded_file.filename.strip()
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_VIDEO_EXTENSIONS:
        return jsonify(ok=False, message="Supported videos: MP4, MOV, AVI, WEBM."), 400
    if request.content_length and request.content_length > MAX_VIDEO_UPLOAD_BYTES + 1024 * 1024:
        return jsonify(ok=False, message="Video size must not exceed 80 MB."), 413
    video_bytes = uploaded_file.read(MAX_VIDEO_UPLOAD_BYTES + 1)
    if len(video_bytes) > MAX_VIDEO_UPLOAD_BYTES:
        return jsonify(ok=False, message="Video size must not exceed 80 MB."), 413
    if not video_bytes:
        return jsonify(ok=False, message="Video file is empty."), 400

    try:
        # Only horizontal position is user-configurable. The activation
        # region always spans the complete video height, regardless of older
        # browser forms that may still submit top/height coordinates.
        safe_zone = validate_zone([
            float(request.form.get("zone_left", "5")) / 100,
            0.0,
            (float(request.form.get("zone_left", "5")) + float(request.form.get("zone_width", "90"))) / 100,
            1.0,
        ])
    except (ValueError, TypeError) as exc:
        return jsonify(ok=False, message=f"Invalid Safe Zone: {exc}"), 400

    job_id = uuid.uuid4().hex
    now = time.time()
    with _INSPECTION_JOBS_LOCK:
        _INSPECTION_JOBS[job_id] = {
            "job_id": job_id, "user_id": str(current_user.get_id()),
            "status": "queued", "progress": 0, "stage": "Queued",
            "message": "", "result": None, "source_filename": filename,
            "cancel_event": Event(), "created_at": now, "updated_at": now,
        }
    app = current_app._get_current_object()
    Thread(target=_run_video_job, args=(app, job_id, video_bytes, filename, safe_zone),
           daemon=True, name=f"video-inspection-{job_id[:8]}").start()
    return jsonify(
        ok=True, job_id=job_id,
        status_url=url_for("main.inspection_job_status", job_id=job_id),
        cancel_url=url_for("main.cancel_inspection_job", job_id=job_id),
    ), 202
