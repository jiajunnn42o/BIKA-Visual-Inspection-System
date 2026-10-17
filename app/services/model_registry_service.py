from __future__ import annotations

import json
import re
import shutil
import uuid
import zipfile

from datetime import (
    date,
    datetime,
    timezone,
)

from pathlib import Path
from threading import Lock

from flask import current_app


MODEL_REQUIRED_FILES = (
    "detector_best.pt",
    "detector_settings.json",
    "classifier.pt",
    "calibration_reference.json",
)

MODEL_OPTIONAL_FILES = (
    "README.txt",
    "manifest.json",
    "02_edge_filter.json",
)

MODEL_MANIFEST_FILENAME = "manifest.json"

DEFAULT_MODEL_NAME = (
    "BIKA Biscuit Inspection Model"
)

MODEL_STAGE_OPTIONS = (
    {
        "value": "production_candidate",
        "label": "Production Candidate",
        "description": (
            "Ready for final verification before production use."
        ),
    },
    {
        "value": "validation",
        "label": "Validation",
        "description": (
            "Under controlled evaluation and comparison."
        ),
    },
    {
        "value": "experimental",
        "label": "Experimental",
        "description": (
            "Research or trial model; not yet validated."
        ),
    },
    {
        "value": "production",
        "label": "Production",
        "description": (
            "Approved model intended for operational use."
        ),
    },
)

MODEL_STAGE_LABELS = {
    item["value"]: item["label"]
    for item in MODEL_STAGE_OPTIONS
}


CALVER_PATTERN = re.compile(
    (
        r"^v"
        r"(?P<year>\d{4})"
        r"\."
        r"(?P<month>\d{2})"
        r"\."
        r"(?P<day>\d{2})"
        r"-r"
        r"(?P<revision>\d{2,4})"
        r"$"
    )
)

LEGACY_VERSION_PATTERN = re.compile(
    r"^v[A-Za-z0-9._-]{1,79}$"
)

LEGACY_DATE_PATTERN = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})"
)


MODEL_UPLOAD_MAX_BYTES = (
    1024 * 1024 * 1024
)

MODEL_UPLOAD_MAX_UNCOMPRESSED_BYTES = (
    2 * 1024 * 1024 * 1024
)

MODEL_UPLOAD_MAX_MEMBERS = 40

_MODEL_UPLOAD_LOCK = Lock()


class ModelRegistryError(RuntimeError):
    pass


def _models_root() -> Path:
    root = Path(
        current_app.config["WEBSITE_MODELS_DIR"]
    )

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    return root


def _registry_path() -> Path:
    instance_dir = Path(
        current_app.instance_path
    )

    instance_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    return (
        instance_dir
        /
        "model_registry.json"
    )


def _load_registry() -> dict:
    path = _registry_path()

    if not path.exists():
        return {
            "active_version": None,
        }

    try:
        raw = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError,
    ):
        raw = {}

    return {
        "active_version":
            raw.get("active_version"),
    }


def _save_registry(
    data: dict,
) -> None:
    path = _registry_path()

    temporary = path.with_suffix(
        ".tmp"
    )

    temporary.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temporary.replace(path)


def model_dir(
    version: str,
) -> Path:
    return (
        _models_root()
        /
        version
    )


def missing_model_files(
    version: str,
) -> list[str]:
    folder = model_dir(version)

    if not folder.is_dir():
        return list(
            MODEL_REQUIRED_FILES
        )

    return [
        filename
        for filename in MODEL_REQUIRED_FILES
        if not (
            folder
            /
            filename
        ).is_file()
    ]


def is_complete_model_version(
    version: str,
) -> bool:
    if (
        not version
        or
        not LEGACY_VERSION_PATTERN.fullmatch(
            version
        )
    ):
        return False

    return not missing_model_files(
        version
    )


def _parse_release_date(
    value: str,
) -> date:
    text = str(
        value
        or
        ""
    ).strip()

    try:
        parsed = date.fromisoformat(
            text
        )

    except ValueError as exc:
        raise ModelRegistryError(
            "Release date must be a valid date."
        ) from exc

    if (
        parsed.year < 2000
        or
        parsed.year > 2100
    ):
        raise ModelRegistryError(
            "Release date must be between 2000 and 2100."
        )

    return parsed


def _normalise_model_name(
    value: str,
) -> str:
    name = " ".join(
        str(
            value
            or
            ""
        )
        .strip()
        .split()
    )

    if not name:
        raise ModelRegistryError(
            "Model name is required."
        )

    if (
        len(name) < 3
        or
        len(name) > 80
    ):
        raise ModelRegistryError(
            "Model name must contain 3 to 80 characters."
        )

    if any(
        ord(character) < 32
        for character in name
    ):
        raise ModelRegistryError(
            "Model name contains invalid characters."
        )

    return name


def _normalise_description(
    value: str,
) -> str:
    description = str(
        value
        or
        ""
    ).strip()

    if len(description) > 500:
        raise ModelRegistryError(
            "Description must not exceed 500 characters."
        )

    return description


def _normalise_stage(
    value: str,
) -> str:
    stage = str(
        value
        or
        ""
    ).strip()

    if stage not in MODEL_STAGE_LABELS:
        raise ModelRegistryError(
            "Please select a valid model lifecycle stage."
        )

    return stage


def _calver_revision(
    version: str,
    release_date: date,
) -> int | None:
    match = CALVER_PATTERN.fullmatch(
        version
    )

    if not match:
        return None

    try:
        version_date = date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )

    except ValueError:
        return None

    if version_date != release_date:
        return None

    return int(
        match.group("revision")
    )


def generate_next_version(
    release_date: str,
) -> str:
    parsed = _parse_release_date(
        release_date
    )

    revisions = []

    for folder in _models_root().iterdir():
        if not folder.is_dir():
            continue

        revision = _calver_revision(
            folder.name,
            parsed,
        )

        if revision is not None:
            revisions.append(
                revision
            )

    next_revision = (
        max(
            revisions,
            default=0,
        )
        +
        1
    )

    return (
        "v"
        f"{parsed.year:04d}"
        "."
        f"{parsed.month:02d}"
        "."
        f"{parsed.day:02d}"
        "-r"
        f"{next_revision:02d}"
    )


def _manifest_path(
    folder: Path,
) -> Path:
    return (
        folder
        /
        MODEL_MANIFEST_FILENAME
    )


def _legacy_release_date(
    version: str,
    folder: Path,
) -> str:
    match = LEGACY_DATE_PATTERN.search(
        version
    )

    if match:
        try:
            return date.fromisoformat(
                match.group("date")
            ).isoformat()
        except ValueError:
            pass

    try:
        return datetime.fromtimestamp(
            folder.stat().st_mtime
        ).date().isoformat()

    except OSError:
        return "—"


def _legacy_manifest(
    version: str,
    folder: Path,
) -> dict:
    return {
        "schema_version": 0,
        "model_name":
            DEFAULT_MODEL_NAME,
        "version":
            version,
        "release_date":
            _legacy_release_date(
                version,
                folder,
            ),
        "revision":
            None,
        "stage":
            "legacy",
        "stage_label":
            "Legacy Package",
        "description":
            (
                "Model package created before "
                "manifest-based registry metadata."
            ),
        "created_at":
            None,
        "uploaded_by":
            None,
    }


def read_model_manifest(
    version: str,
) -> dict:
    folder = model_dir(
        version
    )

    path = _manifest_path(
        folder
    )

    if not path.exists():
        return _legacy_manifest(
            version,
            folder,
        )

    try:
        manifest = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return _legacy_manifest(
            version,
            folder,
        )

    stage = str(
        manifest.get("stage")
        or
        "legacy"
    )

    return {
        "schema_version":
            manifest.get(
                "schema_version",
                1,
            ),
        "model_name":
            str(
                manifest.get("model_name")
                or
                DEFAULT_MODEL_NAME
            ).strip(),
        "version":
            str(
                manifest.get("version")
                or
                version
            ).strip(),
        "release_date":
            str(
                manifest.get("release_date")
                or
                _legacy_release_date(
                    version,
                    folder,
                )
            ).strip(),
        "revision":
            manifest.get("revision"),
        "stage":
            stage,
        "stage_label":
            (
                MODEL_STAGE_LABELS.get(stage)
                or
                str(
                    manifest.get("stage_label")
                    or
                    "Legacy Package"
                )
            ),
        "description":
            str(
                manifest.get("description")
                or
                ""
            ).strip(),
        "created_at":
            manifest.get("created_at"),
        "uploaded_by":
            manifest.get("uploaded_by"),
    }


def _write_model_manifest(
    folder: Path,
    manifest: dict,
) -> None:
    _manifest_path(folder).write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _version_sort_key(
    version: str,
) -> tuple:
    folder = model_dir(version)

    manifest = read_model_manifest(
        version
    )

    release_text = str(
        manifest.get("release_date")
        or
        ""
    )

    try:
        release = date.fromisoformat(
            release_text
        )

    except ValueError:
        release = date(
            1970,
            1,
            1,
        )

    revision = manifest.get(
        "revision"
    )

    try:
        revision_value = int(
            revision
        )

    except (
        TypeError,
        ValueError,
    ):
        revision_value = 0

    try:
        modified = folder.stat().st_mtime

    except OSError:
        modified = 0

    return (
        release,
        revision_value,
        modified,
        version,
    )


def available_model_versions() -> list[str]:
    versions = []

    for folder in _models_root().iterdir():
        if (
            not folder.is_dir()
            or
            folder.name == "sam2"
            or
            folder.name.startswith(".")
        ):
            continue

        if is_complete_model_version(
            folder.name
        ):
            versions.append(
                folder.name
            )

    return sorted(
        versions,
        key=_version_sort_key,
        reverse=True,
    )


def _apply_version_to_config(
    version: str,
) -> None:
    folder = model_dir(
        version
    )

    current_app.config[
        "MODEL_VERSION"
    ] = version

    current_app.config[
        "MODEL_DIR"
    ] = folder

    current_app.config[
        "DETECTOR_PATH"
    ] = (
        folder
        /
        "detector_best.pt"
    )

    current_app.config[
        "DETECTOR_SETTINGS_PATH"
    ] = (
        folder
        /
        "detector_settings.json"
    )

    current_app.config[
        "CLASSIFIER_PATH"
    ] = (
        folder
        /
        "classifier.pt"
    )

    current_app.config[
        "CALIBRATION_PATH"
    ] = (
        folder
        /
        "calibration_reference.json"
    )


def resolve_active_version() -> str | None:
    registry = _load_registry()

    persisted = str(
        registry.get("active_version")
        or
        ""
    ).strip()

    if is_complete_model_version(
        persisted
    ):
        return persisted

    configured = str(
        current_app.config.get(
            "MODEL_VERSION"
        )
        or
        ""
    ).strip()

    if is_complete_model_version(
        configured
    ):
        return configured

    versions = available_model_versions()

    return (
        versions[0]
        if versions
        else None
    )


def synchronise_runtime_model() -> str | None:
    version = resolve_active_version()

    if version is None:
        return None

    _apply_version_to_config(
        version
    )

    registry = _load_registry()

    if (
        registry.get("active_version")
        !=
        version
    ):
        registry[
            "active_version"
        ] = version

        _save_registry(
            registry
        )

    return version


def set_active_version(
    version: str,
) -> None:
    if not is_complete_model_version(
        version
    ):
        missing = missing_model_files(
            version
        )

        raise ModelRegistryError(
            "This is not a complete model package"
            +
            (
                ": "
                +
                ", ".join(missing)
                if missing
                else
                "."
            )
        )

    _save_registry(
        {
            "active_version":
                version,
        }
    )

    _apply_version_to_config(
        version
    )


def _normalise_percent(
    value: float,
) -> float:
    value = float(value)

    if 0 <= value <= 1:
        value *= 100

    return value


def _read_performance(
    folder: Path,
) -> str:
    readme = (
        folder
        /
        "README.txt"
    )

    if not readme.exists():
        return "—"

    try:
        text = readme.read_text(
            encoding="utf-8",
            errors="ignore",
        )

    except OSError:
        return "—"

    patterns = (
        (
            "Macro-F1",
            r"macro[\s_-]*f1\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*%?",
        ),
        (
            "Reject-F1",
            r"reject[\s_-]*f1\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*%?",
        ),
        (
            "mAP",
            r"\bmap(?:50(?:-95)?)?\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*%?",
        ),
        (
            "Accuracy",
            r"\baccuracy\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*%?",
        ),
    )

    values = []

    for label, pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        try:
            percent = _normalise_percent(
                float(
                    match.group(1)
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

        values.append(
            f"{label} {percent:.1f}%"
        )

        if len(values) >= 2:
            break

    return (
        " · ".join(values)
        if values
        else "—"
    )


def _last_updated(
    folder: Path,
) -> str:
    manifest_path = _manifest_path(
        folder
    )

    if manifest_path.exists():
        try:
            data = json.loads(
                manifest_path.read_text(
                    encoding="utf-8"
                )
            )

            created_at = data.get(
                "created_at"
            )

            if created_at:
                parsed = datetime.fromisoformat(
                    str(created_at).replace(
                        "Z",
                        "+00:00",
                    )
                )

                return parsed.date().isoformat()

        except (
            OSError,
            ValueError,
            json.JSONDecodeError,
        ):
            pass

    timestamps = []

    for filename in (
        *MODEL_REQUIRED_FILES,
        *MODEL_OPTIONAL_FILES,
    ):
        path = (
            folder
            /
            filename
        )

        if not path.exists():
            continue

        try:
            timestamps.append(
                path.stat().st_mtime
            )

        except OSError:
            pass

    if not timestamps:
        return "—"

    return datetime.fromtimestamp(
        max(timestamps)
    ).strftime(
        "%Y-%m-%d"
    )


def model_info(
    version: str,
    *,
    active_version: str | None = None,
) -> dict:
    folder = model_dir(version)

    complete = is_complete_model_version(
        version
    )

    manifest = read_model_manifest(
        version
    )

    class_count = "—"
    class_names = []

    if complete:
        try:
            from app.services.inspection_model_metadata import (
                get_classifier_ui_metadata,
            )

            metadata = (
                get_classifier_ui_metadata(
                    str(
                        folder
                        /
                        "classifier.pt"
                    )
                )
            )

            class_count = metadata[
                "class_count"
            ]

            class_names = [
                item["display_name"]
                for item
                in metadata["classes"]
            ]

        except Exception:
            class_count = "—"

    is_active = (
        active_version == version
    )

    return {
        "name":
            manifest["model_name"],
        "version":
            version,
        "status":
            (
                "Active"
                if is_active
                else
                "Available"
            )
            if complete
            else
            "Invalid",
        "stage":
            manifest["stage"],
        "stage_label":
            manifest["stage_label"],
        "release_date":
            manifest["release_date"],
        "revision":
            manifest["revision"],
        "description":
            manifest["description"],
        "uploaded_by":
            manifest["uploaded_by"],
        "classes":
            class_count,
        "class_names":
            class_names,
        "performance":
            (
                _read_performance(folder)
                if complete
                else
                "—"
            ),
        "last_updated":
            (
                _last_updated(folder)
                if complete
                else
                "—"
            ),
        "is_active":
            is_active,
        "complete":
            complete,
        "missing_files":
            missing_model_files(
                version
            ),
    }


def live_model_context() -> dict:
    active = synchronise_runtime_model()

    if active is None:
        return {
            "live_model": {
                "name":
                    "Not configured",
                "version":
                    "—",
                "status":
                    "Not configured",
                "stage":
                    "none",
                "stage_label":
                    "—",
                "release_date":
                    "—",
                "revision":
                    None,
                "description":
                    "",
                "uploaded_by":
                    None,
                "classes":
                    "—",
                "class_names":
                    [],
                "performance":
                    "—",
                "last_updated":
                    "—",
                "is_active":
                    False,
                "complete":
                    False,
            },
            "model_versions":
                [],
            "model_stage_options":
                MODEL_STAGE_OPTIONS,
            "default_model_name":
                DEFAULT_MODEL_NAME,
        }

    return {
        "live_model":
            model_info(
                active,
                active_version=
                    active,
            ),
        "model_versions": [
            model_info(
                version,
                active_version=
                    active,
            )
            for version
            in available_model_versions()
        ],
        "model_stage_options":
            MODEL_STAGE_OPTIONS,
        "default_model_name":
            DEFAULT_MODEL_NAME,
    }


def _validate_detector_settings(
    path: Path,
) -> None:
    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise ModelRegistryError(
            "detector_settings.json is not valid JSON."
        ) from exc

    required = {
        "conf",
        "nms_iou",
        "imgsz",
        "max_det",
    }

    missing = sorted(
        required
        -
        set(data)
    )

    if missing:
        raise ModelRegistryError(
            "detector_settings.json is missing: "
            +
            ", ".join(missing)
        )


def validate_model_folder(
    folder: Path,
) -> dict:
    missing = [
        filename
        for filename
        in MODEL_REQUIRED_FILES
        if not (
            folder
            /
            filename
        ).is_file()
    ]

    if missing:
        raise ModelRegistryError(
            "Model package is missing: "
            +
            ", ".join(missing)
        )

    _validate_detector_settings(
        folder
        /
        "detector_settings.json"
    )

    from app.services.inspection_model_metadata import (
        get_classifier_ui_metadata,
    )

    metadata = (
        get_classifier_ui_metadata(
            str(
                folder
                /
                "classifier.pt"
            )
        )
    )

    if not metadata.get(
        "classes"
    ):
        raise ModelRegistryError(
            "classifier.pt does not contain class metadata."
        )

    return metadata


def _zip_entry_is_symlink(
    info: zipfile.ZipInfo,
) -> bool:
    mode = (
        info.external_attr
        >>
        16
    )

    return (
        mode
        &
        0o170000
    ) == 0o120000


def install_uploaded_model(
    *,
    model_name: str,
    release_date: str,
    stage: str,
    description: str,
    uploaded_by: str | None,
    uploaded_file,
) -> dict:
    normalised_name = (
        _normalise_model_name(
            model_name
        )
    )

    parsed_release_date = (
        _parse_release_date(
            release_date
        )
    )

    normalised_stage = (
        _normalise_stage(
            stage
        )
    )

    normalised_description = (
        _normalise_description(
            description
        )
    )

    with _MODEL_UPLOAD_LOCK:
        version = generate_next_version(
            parsed_release_date.isoformat()
        )

        target = (
            _models_root()
            /
            version
        )

        if target.exists():
            raise ModelRegistryError(
                "The generated model version already exists. "
                "Refresh the page and try again."
            )

        token = uuid.uuid4().hex

        temporary_zip = (
            _models_root()
            /
            f".upload_{token}.zip"
        )

        staging = (
            _models_root()
            /
            f".upload_{token}"
        )

        try:
            uploaded_file.save(
                temporary_zip
            )

            if (
                temporary_zip.stat().st_size
                >
                MODEL_UPLOAD_MAX_BYTES
            ):
                raise ModelRegistryError(
                    "Model package ZIP is too large."
                )

            with zipfile.ZipFile(
                temporary_zip,
                "r",
            ) as archive:
                members = [
                    info
                    for info
                    in archive.infolist()
                    if not info.is_dir()
                ]

                if (
                    not members
                    or
                    len(members)
                    >
                    MODEL_UPLOAD_MAX_MEMBERS
                ):
                    raise ModelRegistryError(
                        "Model package contains an invalid number of files."
                    )

                total_size = sum(
                    max(
                        0,
                        int(info.file_size),
                    )
                    for info
                    in members
                )

                if (
                    total_size
                    >
                    MODEL_UPLOAD_MAX_UNCOMPRESSED_BYTES
                ):
                    raise ModelRegistryError(
                        "Uncompressed model package is too large."
                    )

                for info in members:
                    normalised = (
                        info.filename
                        .replace(
                            "\\",
                            "/",
                        )
                    )

                    parts = [
                        part
                        for part
                        in normalised.split(
                            "/"
                        )
                        if part not in {
                            "",
                            ".",
                        }
                    ]

                    if (
                        normalised.startswith("/")
                        or
                        ".." in parts
                        or
                        _zip_entry_is_symlink(
                            info
                        )
                    ):
                        raise ModelRegistryError(
                            "Model ZIP contains an unsafe path."
                        )

                by_basename = {}

                for info in members:
                    basename = Path(
                        info.filename
                        .replace(
                            "\\",
                            "/",
                        )
                    ).name

                    by_basename.setdefault(
                        basename,
                        []
                    ).append(
                        info
                    )

                selected = {}

                for filename in MODEL_REQUIRED_FILES:
                    candidates = (
                        by_basename.get(
                            filename,
                            []
                        )
                    )

                    if len(candidates) != 1:
                        raise ModelRegistryError(
                            "Model ZIP must contain exactly one "
                            f"{filename}."
                        )

                    selected[
                        filename
                    ] = candidates[0]

                required_parents = {
                    str(
                        Path(
                            info.filename
                            .replace(
                                "\\",
                                "/",
                            )
                        ).parent
                    )
                    for info
                    in selected.values()
                }

                if len(required_parents) != 1:
                    raise ModelRegistryError(
                        "All required model files must be in the same ZIP folder."
                    )

                package_parent = next(
                    iter(
                        required_parents
                    )
                )

                staging.mkdir(
                    parents=True,
                    exist_ok=False,
                )

                for filename, info in selected.items():
                    with (
                        archive.open(
                            info,
                            "r",
                        )
                        as source,
                        (
                            staging
                            /
                            filename
                        ).open(
                            "wb"
                        )
                        as destination,
                    ):
                        shutil.copyfileobj(
                            source,
                            destination,
                        )

                for info in by_basename.get(
                    "README.txt",
                    []
                ):
                    parent = str(
                        Path(
                            info.filename
                            .replace(
                                "\\",
                                "/",
                            )
                        ).parent
                    )

                    if parent != package_parent:
                        continue

                    with (
                        archive.open(
                            info,
                            "r",
                        )
                        as source,
                        (
                            staging
                            /
                            "README.txt"
                        ).open(
                            "wb"
                        )
                        as destination,
                    ):
                        shutil.copyfileobj(
                            source,
                            destination,
                        )

                    break

                # Preserve experimental edge filter when included beside the
                # required weights; never take a file from another ZIP folder.
                edge_candidates = [
                    info for info in by_basename.get("02_edge_filter.json", [])
                    if str(Path(info.filename.replace("\\", "/")).parent) == package_parent
                ]
                if len(edge_candidates) > 1:
                    raise ModelRegistryError(
                        "Model ZIP contains duplicate 02_edge_filter.json files."
                    )
                if edge_candidates:
                    with archive.open(edge_candidates[0], "r") as source, (
                        staging / "02_edge_filter.json"
                    ).open("wb") as destination:
                        shutil.copyfileobj(source, destination)

            from app.services.inspection_model_metadata import (
                get_classifier_ui_metadata,
            )

            get_classifier_ui_metadata.cache_clear()

            metadata = validate_model_folder(
                staging
            )

            match = CALVER_PATTERN.fullmatch(
                version
            )

            revision = (
                int(
                    match.group("revision")
                )
                if match
                else None
            )

            manifest = {
                "schema_version":
                    1,
                "model_name":
                    normalised_name,
                "version":
                    version,
                "release_date":
                    parsed_release_date.isoformat(),
                "revision":
                    revision,
                "stage":
                    normalised_stage,
                "stage_label":
                    MODEL_STAGE_LABELS[
                        normalised_stage
                    ],
                "description":
                    normalised_description,
                "class_count":
                    metadata[
                        "class_count"
                    ],
                "classes": [
                    item["name"]
                    for item
                    in metadata["classes"]
                ],
                "created_at":
                    (
                        datetime.now(
                            timezone.utc
                        )
                        .isoformat()
                        .replace(
                            "+00:00",
                            "Z",
                        )
                    ),
                "uploaded_by":
                    (
                        str(uploaded_by).strip()
                        if uploaded_by
                        else None
                    ),
                "source_filename":
                    str(
                        uploaded_file.filename
                        or
                        ""
                    ),
                "package_files":
                    (
                        list(
                            MODEL_REQUIRED_FILES
                        )
                        +
                        (
                            ["README.txt"]
                            if (
                                staging
                                /
                                "README.txt"
                            ).exists()
                            else []
                        )
                    ),
            }

            _write_model_manifest(
                staging,
                manifest,
            )

            staging.replace(
                target
            )

            get_classifier_ui_metadata.cache_clear()

            return model_info(
                version,
                active_version=
                    resolve_active_version(),
            )

        except zipfile.BadZipFile as exc:
            raise ModelRegistryError(
                "The uploaded file is not a valid ZIP package."
            ) from exc

        finally:
            try:
                temporary_zip.unlink(
                    missing_ok=True
                )

            except OSError:
                pass

            if staging.exists():
                shutil.rmtree(
                    staging,
                    ignore_errors=True,
                )
