# -*- coding: utf-8 -*-
"""English console messages for TLC-RAPID entry script."""

from __future__ import annotations

from pathlib import Path

from app_metadata import APP_LICENSE, APP_VERSION, SOURCE_URL
from utils.load_user_config import ValidationIssue


def _rel(path: Path | None, root: Path) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def print_banner() -> None:
    print("=" * 60)
    print(f"  TLC-RAPID v{APP_VERSION} - TLC spot detection and quantification")
    print(f"  {APP_LICENSE}; no warranty; source: {SOURCE_URL}")
    print("=" * 60)


def print_checking() -> None:
    print("\n[1/3] Checking setup...")


def print_blocking_issues(issues: list[ValidationIssue], root: Path) -> None:
    print("\n" + "!" * 60)
    print("  Cannot start — please fix the following first")
    print("!" * 60)

    step = 1
    for issue in issues:
        if issue.level != "error":
            continue
        print(f"\n  [{step}] {issue.title}")
        if issue.path:
            print(f"      Location: {_rel(issue.path, root)}")
        for line in issue.next_steps:
            print(f"      -> {line}")
        step += 1

    print("\n" + "-" * 60)
    print("  When done, run TLC-RAPID.exe again.")
    print("-" * 60)


def print_warnings(issues: list[ValidationIssue], root: Path) -> None:
    warnings = [i for i in issues if i.level == "warning"]
    if not warnings:
        return
    print("\n[Note]")
    for issue in warnings:
        print(f"  - {issue.title}")
        if issue.path:
            print(f"    Location: {_rel(issue.path, root)}")
        for line in issue.next_steps:
            print(f"    -> {line}")


def print_config_summary(
    *,
    root: Path,
    source: Path,
    image_count: int,
    weights: Path,
    standard_concentrations: str,
    standard_num: int,
    quantification_method: str,
    imaging_mode: str,
    per_image_conc: dict[str, list[float]],
) -> None:
    qm_label = "isotonic regression" if quantification_method == "isotonic" else "quadratic back-calculation"
    im_label = {
        "auto": "auto-detect",
        "366nm": "366 nm fluorescence (IGI)",
        "visible": "visible light (IOD)",
        "254nm": "254 nm (IOD)",
    }.get(imaging_mode, imaging_mode)

    print("\n[2/3] Current configuration")
    print("-" * 40)
    print(f"  Images folder : {_rel(source, root)}  ({image_count} file(s))")
    print(f"  Model weights : {_rel(weights, root)}")
    print(f"  Standards     : {standard_concentrations}  (n={standard_num})")
    print(f"  Quantification: {quantification_method} ({qm_label})")
    print(f"  Imaging mode  : {imaging_mode} ({im_label})")
    overrides = {k: v for k, v in per_image_conc.items() if k != "_default"}
    if overrides:
        print("  Per-image standards:")
        for name, values in overrides.items():
            print(f"    {name}: {', '.join(str(v) for v in values)}")
    print("-" * 40)


def print_analysis_hint() -> None:
    print("\n[3/3] Ready to analyze")
    print("  - First run may take 1-2 minutes while the model loads")
    print("  - After each image, a Manual Mark window opens:")
    print("      Left-click  = ADD")
    print("      Right-click = DELETE")
    print("      Press S     = save and continue to NEXT image")
    print("      Esc         = skip manual marking for this image")


def confirm_start() -> bool:
    while True:
        answer = input("\nStart analysis now? [Y/n]: ").strip().lower()
        if answer in ("", "y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please enter Y or N.")


def print_done(root: Path) -> None:
    print("\n" + "=" * 60)
    print("  Analysis complete")
    print("=" * 60)
    print("\nResults folder: runs/predict-seg/ (latest exp folder)")
    print("\nNext — read sample predictions:")
    print("  1. Open quantitative_analysis_all_images.xlsx")
    print("  2. Filter rows where Spot_Type = sample")
    print("  3. Read the Calculated_Concentration column")
    print("\nSee README.md for details.")


def pause_before_exit(message: str = "\nPress Enter to exit...") -> None:
    try:
        input(message)
    except Exception:
        pass
