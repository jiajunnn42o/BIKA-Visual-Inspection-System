"""Local Windows-only native folder picker for the About System Backup Destination.

It selects a directory ON THE FLASK HOST, not a folder on a remote visitor's PC.
No files or backups are written by this endpoint.
"""
from __future__ import annotations

import ipaddress
import os
from pathlib import Path
from threading import Lock

from flask import jsonify, request

from app.main import main_bp
from app.main.about_system import superadmin_only

_picker_lock = Lock()


def _is_loopback(address: str | None) -> bool:
    try:
        return ipaddress.ip_address(str(address or "").split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _pick_windows_folder() -> str:
    """Run a Windows folder-selection dialog in the interactive Flask process."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    try:
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
        return str(
            filedialog.askdirectory(
                parent=root,
                mustexist=True,
                title="Select a BIKA Backup Folder",
            )
            or ""
        )
    finally:
        root.destroy()


@main_bp.route("/about-system/backup-destination/select-folder", methods=["POST"])
@superadmin_only
def pick_about_backup_folder():
    # Guard against remote visitors opening a dialog on the host computer.
    if not _is_loopback(request.remote_addr):
        return jsonify(ok=False, message="Folder browsing is only available on the local Windows computer."), 403
    if os.name != "nt":
        return jsonify(ok=False, message="The Windows folder picker is unavailable on this server."), 409
    if not _picker_lock.acquire(blocking=False):
        return jsonify(ok=False, message="A folder selection window is already open."), 409

    try:
        try:
            selected = _pick_windows_folder()
        except Exception:
            # Do not expose OS exception details or sensitive local paths.
            return jsonify(ok=False, message="Could not open the Windows folder selector. Run Flask in an interactive desktop session."), 500

        if not selected:
            return jsonify(ok=True, cancelled=True)

        path = Path(selected)
        if not path.is_absolute() or not path.is_dir():
            return jsonify(ok=False, message="Please select an existing folder."), 400
        if len(str(path)) > 260:
            return jsonify(ok=False, message="Selected folder path is too long (maximum 260 characters)."), 400
        return jsonify(ok=True, path=str(path))
    finally:
        _picker_lock.release()
