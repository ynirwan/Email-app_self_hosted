"""
backend/core/installation.py

Persistent installation identity for ZeniPost Email Marketing Platform.

Generates a UUID on first boot and stores it in a `.installation_id` file
next to license.json (or in cwd as a fallback).  The same ID is included
in every license ping so the dashboard can track unique installations per
license and enforce per-plan seat limits.

The file is intentionally hidden (dot-prefixed) and should be kept in place
— deleting it causes this installation to be counted as a new seat on the
next ping.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level cache so we only hit the filesystem once per process.
_cached_id: Optional[str] = None


def _id_file_path() -> Path:
    """
    Resolve the path for .installation_id.
    Stored next to license.json when possible so it travels with the install.
    Falls back to cwd if no license file has been placed yet.
    """
    # Lazy import to avoid a circular dependency at module load time.
    from core.license import _find_license_file
    license_path = _find_license_file()
    if license_path is not None:
        return license_path.parent / ".installation_id"
    return Path(os.getcwd()) / ".installation_id"


def get_installation_id() -> str:
    """
    Return the persistent installation UUID for this instance.

    On first call the ID is generated and written to disk.  On subsequent
    calls (within the same process) the cached value is returned immediately.
    If the file cannot be written (e.g. read-only filesystem) the ID is still
    returned for this session — it will just regenerate on the next restart.
    """
    global _cached_id
    if _cached_id:
        return _cached_id

    id_path = _id_file_path()

    # Try to read an existing ID first.
    if id_path.exists():
        try:
            existing = id_path.read_text(encoding="utf-8").strip()
            if existing:
                # Basic sanity check — must look like a UUID.
                uuid.UUID(existing)
                _cached_id = existing
                logger.debug("Installation ID loaded from %s: %s", id_path, _cached_id)
                return _cached_id
        except (ValueError, OSError):
            logger.warning("Invalid or unreadable .installation_id at %s — regenerating.", id_path)

    # Generate a new ID.
    new_id = str(uuid.uuid4())
    try:
        id_path.write_text(new_id, encoding="utf-8")
        logger.info("New installation ID generated and saved to %s: %s", id_path, new_id)
    except OSError as exc:
        logger.warning(
            "Could not persist installation ID to %s (%s). "
            "This installation will be counted as a new seat on next restart.",
            id_path, exc,
        )

    _cached_id = new_id
    return _cached_id
