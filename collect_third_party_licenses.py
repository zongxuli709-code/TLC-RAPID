"""Collect exact release dependency versions and their installed license texts."""

from __future__ import annotations

import shutil
import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "THIRD_PARTY_LICENSES"
OVERRIDES = ROOT / "third_party_license_overrides"
LOCK = ROOT / "requirements-freeze.txt"

ROOT_PACKAGES = (
    "matplotlib", "numpy", "opencv-python", "openpyxl", "packaging",
    "pandas", "Pillow", "psutil", "PyYAML", "requests", "scikit-learn",
    "scipy", "seaborn", "setuptools", "torch", "torchvision", "tqdm",
    "ultralytics", "pyinstaller",
)


def _safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in name.upper()).strip("-")


def _dependency_closure() -> dict[str, object]:
    environment = default_environment()
    environment["extra"] = ""
    queue = list(ROOT_PACKAGES)
    found: dict[str, object] = {}
    while queue:
        requested_name = queue.pop(0)
        canonical = canonicalize_name(requested_name)
        if canonical in found:
            continue
        try:
            dist = distribution(requested_name)
        except PackageNotFoundError as exc:
            raise RuntimeError(f"Required package is not installed: {requested_name}") from exc
        found[canonical] = dist
        for raw_requirement in dist.requires or ():
            requirement = Requirement(raw_requirement)
            if requirement.marker is None or requirement.marker.evaluate(environment):
                queue.append(requirement.name)
    return found


def _license_files(dist: object) -> list[Path]:
    matches: list[Path] = []
    for item in dist.files or ():
        relative = str(item).replace("\\", "/")
        lower = relative.lower()
        basename = Path(relative).name.lower()
        is_metadata = ".dist-info/" in lower or ".egg-info/" in lower
        is_notice = basename.startswith(("license", "licence", "copying", "notice", "copyright"))
        if is_metadata and is_notice:
            path = Path(dist.locate_file(item)).resolve()
            if path.is_file() and path not in matches:
                matches.append(path)
    return matches


def collect() -> list[Path]:
    dependencies = _dependency_closure()
    OUTPUT.mkdir(exist_ok=True)
    for old in OUTPUT.iterdir():
        if old.is_file():
            old.unlink()

    created: list[Path] = []
    inventory: list[str] = [
        "TLC-RAPID v1.0 dependency and license inventory",
        "Generated from the locked Windows release environment.",
        "",
    ]
    lock_lines = [
        "# Fully resolved Windows/Python 3.12 environment used for TLC-RAPID v1.0.",
        "# Fully resolved Windows build lock; direct dependency pins are in requirements-lock.txt.",
    ]
    missing: list[str] = []

    for canonical, dist in sorted(dependencies.items()):
        name = dist.metadata.get("Name") or canonical
        version = dist.version
        lock_lines.append(f"{name}=={version}")
        sources = _license_files(dist)
        if not sources:
            override = OVERRIDES / f"{canonical}-{version}.txt"
            if override.is_file():
                sources = [override]
            else:
                missing.append(f"{name} {version}: license file unavailable")
                continue
        target_names: list[str] = []
        for index, source in enumerate(sources, start=1):
            suffix = _safe_name(source.name)
            if len(sources) > 1 and any(path.name == source.name for path in sources[: index - 1]):
                suffix = f"{index}-{suffix}"
            target = OUTPUT / f"{_safe_name(name)}-{version}-{suffix}.txt"
            shutil.copyfile(source, target)
            created.append(target)
            target_names.append(target.name)
        license_metadata = (dist.metadata.get("License") or "not declared").splitlines()[0]
        home = dist.metadata.get("Home-page") or "not declared"
        inventory.extend(
            [
                f"{name} {version}",
                f"  License metadata: {license_metadata}",
                f"  Homepage: {home}",
                f"  License files: {', '.join(target_names)}",
                "",
            ]
        )

    runtime_files = (
        (
            (Path(sys.base_prefix) / "LICENSE_PYTHON.txt", Path(sys.base_prefix) / "LICENSE.txt"),
            f"PYTHON-{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}.txt",
            "Python runtime",
        ),
        (
            (
                Path(sys.base_prefix) / "Library" / "lib" / "tk8.6" / "license.terms",
                Path(sys.base_prefix) / "tcl" / "tk8.6" / "license.terms",
            ),
            "TCL-TK-8.6-LICENSE-TERMS.txt",
            "Tcl/Tk runtime",
        ),
    )
    for candidates, target_name, label in runtime_files:
        source = next((candidate for candidate in candidates if candidate.is_file()), None)
        if source is None:
            missing.append(f"{label}: license file not found")
            continue
        target = OUTPUT / target_name
        shutil.copyfile(source, target)
        created.append(target)
        inventory.extend([label, f"  License files: {target.name}", ""])

    upstream_target = OUTPUT / "ULTRALYTICS-YOLOV5-AGPL-3.0.txt"
    shutil.copyfile(ROOT / "LICENSE", upstream_target)
    created.append(upstream_target)
    inventory.extend(
        [
            "Ultralytics YOLOv5 (modified source; exact starting revision not recorded)",
            "  License metadata: GNU AGPL v3",
            f"  License files: {upstream_target.name}",
            "",
        ]
    )

    if missing:
        raise RuntimeError("License collection incomplete:\n- " + "\n- ".join(missing))

    (OUTPUT / "INVENTORY.txt").write_text("\n".join(inventory), encoding="utf-8")
    LOCK.write_text("\n".join(lock_lines) + "\n", encoding="utf-8")
    created.extend((OUTPUT / "INVENTORY.txt", LOCK))
    return created


if __name__ == "__main__":
    files = collect()
    print(f"Generated {len(files)} release records and license files.")
    print(f"License directory: {OUTPUT}")
    print(f"Resolved environment: {LOCK}")
