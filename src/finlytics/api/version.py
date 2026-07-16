"""Version / about endpoint.

GET /api/version  — protected; returns app version + optional build metadata.

Fields
------
version   : str       — from importlib.metadata (installed package) or pyproject.toml fallback.
image_tag : str|null  — injected via FINLYTICS_IMAGE_TAG env var at deploy time (CalVer); null otherwise.
built_at  : str|null  — injected via FINLYTICS_BUILD_DATE env var at deploy time; null otherwise.
"""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/version", tags=["version"])


def _read_version() -> str:
    """Return the package version string.

    1. importlib.metadata  — works when the package is installed (production / editable install).
    2. pyproject.toml parse — fallback for bare source checkouts where the package is not installed.
    """
    try:
        return _pkg_version("finlytics")
    except PackageNotFoundError:
        pass

    # Minimal TOML parse — avoid adding a toml dependency for a single key.
    pyproject = Path(__file__).parent.parent.parent.parent / "pyproject.toml"
    if pyproject.is_file():
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("version") and "=" in stripped:
                _, _, raw = stripped.partition("=")
                return raw.strip().strip('"').strip("'")

    return "0.1.0"


class VersionOut(BaseModel):
    version: str
    image_tag: str | None
    built_at: str | None


@router.get("", response_model=VersionOut)
async def get_version() -> VersionOut:
    """Return app version and optional build metadata (auth-gated)."""
    return VersionOut(
        version=_read_version(),
        image_tag=os.environ.get("FINLYTICS_IMAGE_TAG") or None,
        built_at=os.environ.get("FINLYTICS_BUILD_DATE") or None,
    )
