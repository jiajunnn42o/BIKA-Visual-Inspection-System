from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from app import create_app
from app.services.storage_service import (
    object_exists,
    put_bytes,
    read_bytes,
    storage_backend,
)


def main():
    app = create_app()

    with app.app_context():
        key = "system-test/storage_service_test.txt"
        payload = b"BIKA storage service OK"

        print("Backend:", storage_backend())

        put_bytes(
            key,
            payload,
            content_type="text/plain",
        )

        if not object_exists(key):
            raise RuntimeError("Uploaded object cannot be found.")

        downloaded = read_bytes(key)
        if downloaded != payload:
            raise RuntimeError("Downloaded object content does not match.")

        print("Storage test PASS:", key)


if __name__ == "__main__":
    main()
