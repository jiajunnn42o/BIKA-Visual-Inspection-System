import os

from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


BASE_DIR = Path(
    __file__
).resolve().parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAX_FAILED_LOGIN_ATTEMPTS = 3

    MAIL_SERVER = os.getenv("MAIL_SERVER")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "false").lower() == "true"

    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv(
        "MAIL_DEFAULT_SENDER",
        MAIL_USERNAME,
    )

    MAIL_SUPPRESS_SEND = False

    # =====================================================
    # BIKA MODEL PACKAGE
    # =====================================================

    MODEL_VERSION = os.getenv(
        "BIKA_MODEL_VERSION",
        "v1_2026-10-10",
    )

    WEBSITE_MODELS_DIR = (
        BASE_DIR
        /
        "website_models"
    )

    MODEL_DIR = (
        WEBSITE_MODELS_DIR
        /
        MODEL_VERSION
    )

    DETECTOR_PATH = (
        MODEL_DIR
        /
        "detector_best.pt"
    )

    DETECTOR_SETTINGS_PATH = (
        MODEL_DIR
        /
        "detector_settings.json"
    )

    CLASSIFIER_PATH = (
        MODEL_DIR
        /
        "classifier.pt"
    )

    CALIBRATION_PATH = (
        MODEL_DIR
        /
        "calibration_reference.json"
    )

    SAM2_CHECKPOINT_PATH = (
        WEBSITE_MODELS_DIR
        /
        "sam2"
        /
        "sam2.1_hiera_large.pt"
    )

    SAM2_MODEL_CONFIG = os.getenv(
        "BIKA_SAM2_MODEL_CONFIG",
        "configs/sam2.1/sam2.1_hiera_l.yaml",
    )

    # =====================================================
    # VALIDATED 09b PIPELINE SOURCE
    #
    # The website reuses the feature / dedup / classifier /
    # calibration functions from the original FYP scripts so
    # website inference stays aligned with 09b.
    #
    # Later, before Linux/VPS deployment, these dependencies
    # can be vendored into the website repository and this
    # path can be changed through .env.
    # =====================================================

    PIPELINE_SOURCE_ROOT = Path(
        os.getenv(
            "BIKA_PIPELINE_SOURCE_ROOT",
            r"D:\BDS\FYP2\sam2_large_project",
        )
    )

    INSPECTION_MAX_IMAGE_MB = int(
        os.getenv(
            "BIKA_INSPECTION_MAX_IMAGE_MB",
            "10",
        )
    )

    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is not configured."
        )

    if not SQLALCHEMY_DATABASE_URI:
        raise RuntimeError(
            "DATABASE_URL is not configured."
        )


TWILIO_ACCOUNT_SID = os.getenv(
    "TWILIO_ACCOUNT_SID"
)

TWILIO_AUTH_TOKEN = os.getenv(
    "TWILIO_AUTH_TOKEN"
)

TWILIO_FROM_NUMBER = os.getenv(
    "TWILIO_FROM_NUMBER"
)

SMS_MODE = os.getenv(
    "SMS_MODE",
    "console",
)
