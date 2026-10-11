from flask import (
    current_app,
    render_template,
)

from flask_login import (
    current_user,
    login_required,
)

from app.main import main_bp

from app.services.inspection_model_metadata import (
    get_classifier_ui_metadata,
)


@main_bp.route("/")
@login_required
def index():
    return render_template(
        "index.html",
        user=current_user,
    )


@main_bp.route("/inspection")
@login_required
def inspection():

    inspection_classes = []
    inspection_model_warning = None

    classifier_path = (
        current_app.config[
            "CLASSIFIER_PATH"
        ]
    )


    try:

        model_metadata = (
            get_classifier_ui_metadata(
                str(
                    classifier_path
                )
            )
        )

        inspection_classes = (
            model_metadata[
                "classes"
            ]
        )

    except Exception as exc:

        current_app.logger.exception(
            (
                "Unable to read classifier metadata "
                "for the Inspection page."
            )
        )

        inspection_model_warning = str(
            exc
        )


    return render_template(
        "inspection.html",

        inspection_classes=
            inspection_classes,

        inspection_model_version=
            current_app.config[
                "MODEL_VERSION"
            ],

        inspection_classifier_file=
            classifier_path.name,

        inspection_model_warning=
            inspection_model_warning,
    )
