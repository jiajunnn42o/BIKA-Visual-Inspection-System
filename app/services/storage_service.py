from __future__ import annotations

import json
import mimetypes
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from flask import current_app


class StorageConfigurationError(RuntimeError):
    pass


def storage_backend() -> str:
    value = (
        current_app.config.get("STORAGE_BACKEND")
        or os.getenv("STORAGE_BACKEND")
        or "local"
    )
    backend = str(value).strip().lower()
    if backend not in {"local", "b2"}:
        raise StorageConfigurationError(
            "STORAGE_BACKEND must be 'local' or 'b2'."
        )
    return backend


def _project_root() -> Path:
    return Path(current_app.root_path).parent


def local_storage_root() -> Path:
    configured = (
        current_app.config.get("LOCAL_INSPECTION_STORAGE")
        or os.getenv("LOCAL_INSPECTION_STORAGE")
    )
    if configured:
        root = Path(configured).expanduser()
        if not root.is_absolute():
            root = _project_root() / root
    else:
        root = _project_root() / "data" / "inspections"

    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def normalize_object_key(object_key: str) -> str:
    value = str(object_key).replace("\\", "/").strip().lstrip("/")
    parts = [
        part
        for part in value.split("/")
        if part not in {"", ".", ".."}
    ]
    if not parts:
        raise ValueError("Object key cannot be empty.")
    return "/".join(parts)


def _local_path(object_key: str) -> Path:
    key = normalize_object_key(object_key)
    root = local_storage_root()
    candidate = (root / Path(*key.split("/"))).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Invalid storage object key.") from exc
    return candidate


def _env_or_config(key: str) -> str | None:
    value = current_app.config.get(key) or os.getenv(key)
    if value is None:
        return None
    return str(value).strip()


@lru_cache(maxsize=4)
def _build_b2_client(
    endpoint_url: str,
    key_id: str,
    application_key: str,
    region: str,
):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=key_id,
        aws_secret_access_key=application_key,
        region_name=region,
    )


def _b2_settings() -> dict[str, str]:
    values = {
        "bucket": _env_or_config("B2_BUCKET_NAME"),
        "endpoint_url": _env_or_config("B2_ENDPOINT_URL"),
        "key_id": _env_or_config("B2_KEY_ID"),
        "application_key": _env_or_config("B2_APPLICATION_KEY"),
        "region": _env_or_config("B2_REGION"),
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise StorageConfigurationError(
            "Missing Backblaze B2 settings: " + ", ".join(missing)
        )
    return {key: str(value) for key, value in values.items()}


def _b2_client_and_bucket():
    settings = _b2_settings()
    client = _build_b2_client(
        settings["endpoint_url"],
        settings["key_id"],
        settings["application_key"],
        settings["region"],
    )
    return client, settings["bucket"]


def put_bytes(
    object_key: str,
    data: bytes,
    *,
    content_type: str | None = None,
    cache_control: str | None = None,
) -> str:
    key = normalize_object_key(object_key)
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("Storage payload must be bytes.")

    guessed_type = (
        content_type
        or mimetypes.guess_type(key)[0]
        or "application/octet-stream"
    )

    if storage_backend() == "local":
        path = _local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(data))
        return key

    client, bucket = _b2_client_and_bucket()
    arguments: dict[str, Any] = {
        "Bucket": bucket,
        "Key": key,
        "Body": bytes(data),
        "ContentType": guessed_type,
    }
    if cache_control:
        arguments["CacheControl"] = cache_control
    client.put_object(**arguments)
    return key


def put_json(object_key: str, payload: Any) -> str:
    data = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        default=str,
    ).encode("utf-8")
    return put_bytes(
        object_key,
        data,
        content_type="application/json; charset=utf-8",
    )


def read_bytes(object_key: str) -> bytes:
    key = normalize_object_key(object_key)
    if storage_backend() == "local":
        return _local_path(key).read_bytes()

    client, bucket = _b2_client_and_bucket()
    response = client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def object_exists(object_key: str) -> bool:
    key = normalize_object_key(object_key)
    if storage_backend() == "local":
        return _local_path(key).is_file()

    client, bucket = _b2_client_and_bucket()
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception as exc:
        response = getattr(exc, "response", {})
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        code = response.get("Error", {}).get("Code")
        if status == 404 or str(code) in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def delete_object(object_key: str) -> None:
    key = normalize_object_key(object_key)
    if storage_backend() == "local":
        path = _local_path(key)
        if path.exists():
            path.unlink()
        return

    client, bucket = _b2_client_and_bucket()
    client.delete_object(Bucket=bucket, Key=key)


def generate_presigned_get_url(
    object_key: str,
    *,
    expires_seconds: int = 900,
) -> str:
    if storage_backend() != "b2":
        raise StorageConfigurationError(
            "Presigned URLs are only used by the B2 backend."
        )

    key = normalize_object_key(object_key)
    client, bucket = _b2_client_and_bucket()
    return client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=max(60, min(int(expires_seconds), 3600)),
    )


def local_path_for_serving(object_key: str) -> Path:
    if storage_backend() != "local":
        raise StorageConfigurationError(
            "Local path requested while storage backend is not local."
        )
    path = _local_path(object_key)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return path
