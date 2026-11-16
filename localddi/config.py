"""Runtime configuration. Everything is optional; no API key is ever required."""

from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("LOCALDDI_DATA_DIR", "./data")).expanduser()


def db_path() -> Path:
    override = os.environ.get("LOCALDDI_DB")
    return Path(override).expanduser() if override else data_dir() / "localddi.sqlite"


def api_key() -> str | None:
    """If set, API endpoints except /health require this key; the web page stays public."""
    return os.environ.get("LOCALDDI_API_KEY") or None


def cors_origins() -> list[str]:
    raw = os.environ.get("LOCALDDI_CORS_ORIGINS", "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def min_severity() -> str | None:
    """Optional floor applied to every endpoint, e.g. ``minor`` hides rows of unknown severity."""
    value = os.environ.get("LOCALDDI_MIN_SEVERITY", "").strip().lower()
    if not value:
        return None
    if value not in {"minor", "moderate", "major", "contraindicated"}:
        raise ValueError("LOCALDDI_MIN_SEVERITY must be minor, moderate, major or contraindicated")
    return value
