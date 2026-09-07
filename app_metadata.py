"""Version and provenance helpers for reproducible TLC-RAPID results."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

APP_NAME = "TLC-RAPID"
APP_VERSION = "1.0"
APP_LICENSE = "GNU AGPL-3.0-only"
SOURCE_URL = "https://github.com/zongxuli709-code/TLC-RAPID"
COPYRIGHT_NOTICE = "Copyright (C) 2025-2026 Zongxu Li and TLC-RAPID contributors"

CORE_PACKAGES = (
    "numpy",
    "opencv-python",
    "openpyxl",
    "packaging",
    "pandas",
    "scikit-learn",
    "scipy",
    "torch",
    "torchvision",
    "ultralytics",
)


def sha256_file(path: str | Path | None) -> str:
    """Return a file SHA-256, or ``unavailable`` when the file cannot be read."""
    if path is None:
        return "unavailable"
    file_path = Path(path)
    if not file_path.is_file():
        return "unavailable"
    digest = hashlib.sha256()
    try:
        with file_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return "unavailable"
    return digest.hexdigest().upper()


def _commit_from_source_code(root: Path) -> str | None:
    source_code = root / "SOURCE_CODE.txt"
    if not source_code.is_file():
        return None
    try:
        text = source_code.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    match = re.search(r"(?im)^[0-9a-f]{40}$", text)
    return match.group(0).lower() if match else None


def get_git_commit(root: str | Path) -> str:
    """Resolve the source commit without exposing an absolute local path."""
    root_path = Path(root)
    embedded = _commit_from_source_code(root_path)
    if embedded:
        return embedded

    configured = os.getenv("TLC_RAPID_COMMIT", "").strip()
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", configured):
        return configured.lower()

    if getattr(sys, "frozen", False):
        return "unknown"
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root_path,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        commit = completed.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return commit.lower() if re.fullmatch(r"[0-9a-fA-F]{40}", commit) else "unknown"


def runtime_versions() -> dict[str, str]:
    versions = {
        "Python_Version": platform.python_version(),
        "Platform": platform.platform(),
    }
    for package in CORE_PACKAGES:
        key = "Dependency_" + package.replace("-", "_")
        try:
            versions[key] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[key] = "not installed"
    return versions


def build_provenance(
    *,
    root: str | Path,
    weights: str | Path | None,
    data_config: str | Path | None,
) -> dict[str, str]:
    weight_path = Path(weights) if weights is not None else None
    data_path = Path(data_config) if data_config is not None else None
    provenance = {
        "Software_Name": APP_NAME,
        "Software_Version": APP_VERSION,
        "Git_Commit": get_git_commit(root),
        "Model_Weights_File": weight_path.name if weight_path else "unavailable",
        "Model_Weights_SHA256": sha256_file(weight_path),
        "Dataset_Config_File": data_path.name if data_path else "unavailable",
        "Dataset_Config_SHA256": sha256_file(data_path),
    }
    provenance.update(runtime_versions())
    return provenance
