from __future__ import annotations

import time
import uuid

from threading import (
    Event,
    Lock,
    Thread,
)

from flask import (
    current_app,
    jsonify,
    render_template,
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

            _INSPECTION_JOBS.pop(
                job_id,
                None,
            )


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

            payload[
                "result"
            ] = job[
                "result"
            ]


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