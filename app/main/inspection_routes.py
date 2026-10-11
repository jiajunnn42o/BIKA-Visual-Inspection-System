from __future__ import annotations

from threading import (
    Event,
    Lock,
    Thread,
)
import time
import uuid

from flask import (
    current_app,
    jsonify,
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

from app.services.inspection_pipeline_service import (
    InspectionCancelled,
    InspectionPipelineError,
    inspect_image_bytes_with_progress,
)


ALLOWED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}


# =========================================================
# IN-MEMORY INSPECTION JOBS
#
# Suitable for the current single-process development setup.
# For production / multiple workers, move this state to Redis
# or a database-backed job queue.
# =========================================================

_INSPECTION_JOBS = {}
_INSPECTION_JOBS_LOCK = Lock()

_JOB_TTL_SECONDS = 30 * 60


def has_active_inspection_jobs() -> bool:
    """
    Used by Model Management to prevent changing the active
    model while an image inspection is queued or running.
    """

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


def _job_for_user(
    job_id: str,
):

    with _INSPECTION_JOBS_LOCK:

        job = _INSPECTION_JOBS.get(
            job_id
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


def _set_job_progress(
    job_id: str,
    progress: int,
    stage: str,
):

    with _INSPECTION_JOBS_LOCK:

        job = _INSPECTION_JOBS.get(
            job_id
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


def _run_job(
    app,
    job_id: str,
    image_bytes: bytes,
):

    with app.app_context():

        with _INSPECTION_JOBS_LOCK:

            job = _INSPECTION_JOBS.get(
                job_id
            )

            if job is None:
                return

            job[
                "status"
            ] = "running"

            job[
                "stage"
            ] = "Starting inspection"

            job[
                "updated_at"
            ] = time.time()

            cancel_event = job[
                "cancel_event"
            ]


        try:

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


            if cancel_event.is_set():

                raise InspectionCancelled(
                    "Inspection cancelled by user."
                )


            with _INSPECTION_JOBS_LOCK:

                job = _INSPECTION_JOBS.get(
                    job_id
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
                ] = "Inspection complete"

                job[
                    "result"
                ] = result

                job[
                    "updated_at"
                ] = time.time()


        except InspectionCancelled:

            with _INSPECTION_JOBS_LOCK:

                job = _INSPECTION_JOBS.get(
                    job_id
                )

                if job is None:
                    return

                job[
                    "status"
                ] = "cancelled"

                job[
                    "stage"
                ] = "Inspection cancelled"

                job[
                    "message"
                ] = "Inspection cancelled."

                job[
                    "updated_at"
                ] = time.time()


        except InspectionPipelineError as exc:

            current_app.logger.warning(
                "Inspection pipeline error: %s",
                exc,
            )


            with _INSPECTION_JOBS_LOCK:

                job = _INSPECTION_JOBS.get(
                    job_id
                )

                if job is None:
                    return

                job[
                    "status"
                ] = "failed"

                job[
                    "stage"
                ] = "Inspection failed"

                job[
                    "message"
                ] = str(
                    exc
                )

                job[
                    "updated_at"
                ] = time.time()


        except Exception:

            current_app.logger.exception(
                "Unexpected image inspection failure."
            )


            with _INSPECTION_JOBS_LOCK:

                job = _INSPECTION_JOBS.get(
                    job_id
                )

                if job is None:
                    return

                job[
                    "status"
                ] = "failed"

                job[
                    "stage"
                ] = "Inspection failed"

                job[
                    "message"
                ] = (
                    "Inspection failed unexpectedly. "
                    "Check the server log for details."
                )

                job[
                    "updated_at"
                ] = time.time()


@main_bp.route(
    "/inspection/run-image",
    methods=[
        "POST",
    ],
)
@login_required
def run_inspection_image():

    _cleanup_jobs()


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


    image_bytes = (
        uploaded_file.read()
    )


    max_bytes = (
        int(
            current_app.config[
                "INSPECTION_MAX_IMAGE_MB"
            ]
        )
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
                f"{current_app.config['INSPECTION_MAX_IMAGE_MB']} MB."
            ),
        ), 413


    job_id = (
        uuid.uuid4()
        .hex
    )


    cancel_event = Event()


    now = time.time()


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


    job = _job_for_user(
        job_id
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

    job = _job_for_user(
        job_id
    )


    if job is None:

        return jsonify(
            ok=False,
            message=(
                "Inspection job was not found."
            ),
        ), 404


    with _INSPECTION_JOBS_LOCK:

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
                status=job[
                    "status"
                ],
            )


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
