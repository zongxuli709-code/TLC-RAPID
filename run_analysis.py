# -*- coding: utf-8 -*-
"""
TLC-RAPID entry point — automated TLC spot detection and quantification.

Default: open the launcher GUI.
  python run_analysis.py
  python run_analysis.py --run     # headless analysis (used by GUI)
  python run_analysis.py --cli     # console-only workflow
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import traceback
from datetime import datetime
from pathlib import Path

from app_metadata import (
    APP_LICENSE,
    APP_NAME,
    APP_VERSION,
    COPYRIGHT_NOTICE,
    SOURCE_URL,
    get_git_commit,
)
from app_paths import app_root

ROOT = app_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from utils.console_ui import (
    confirm_start,
    pause_before_exit,
    print_analysis_hint,
    print_banner,
    print_blocking_issues,
    print_checking,
    print_config_summary,
    print_done,
    print_warnings,
)
from utils.load_user_config import (
    count_images,
    is_blocking_issue,
    load_concentrations,
    load_settings,
    validate_user_input,
)

ENGINE_PATH = ROOT / "segment" / "analyze_engine.py"
ERROR_LOG = ROOT / "error_log.txt"


def _log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _load_engine():
    if getattr(sys, "frozen", False):
        return importlib.import_module("segment.analyze_engine")

    spec = importlib.util.spec_from_file_location("analyze_engine", ENGINE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load analysis engine: {ENGINE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_analysis(*, interactive: bool = True) -> int:
    """Run quantification. Returns process exit code."""
    print_banner()
    _log(
        f"Start version={APP_VERSION} commit={get_git_commit(ROOT)} "
        f"ROOT={ROOT} frozen={getattr(sys, 'frozen', False)}"
    )

    print_checking()
    issues = validate_user_input()
    errors = [i for i in issues if is_blocking_issue(i)]

    if errors:
        print_blocking_issues(errors, ROOT)
        if interactive:
            pause_before_exit()
        return 1

    print_warnings(issues, ROOT)

    settings = load_settings()
    concentrations_by_image = load_concentrations()

    default_conc = concentrations_by_image.get("_default", [])
    if default_conc:
        settings["standard_concentrations"] = ",".join(str(c) for c in default_conc)
        settings["standard_num"] = len(default_conc)

    settings.pop("images_subdir", None)
    settings["view_img"] = False
    settings["manual_mark"] = True

    source = Path(settings["source"])
    print_config_summary(
        root=ROOT,
        source=source,
        image_count=count_images(source),
        weights=Path(settings["weights"]),
        standard_concentrations=settings.get("standard_concentrations", ""),
        standard_num=int(settings.get("standard_num", 0)),
        quantification_method=settings.get("quantification_method", "isotonic"),
        imaging_mode=settings.get("imaging_mode", "auto"),
        per_image_conc=concentrations_by_image,
    )

    print_analysis_hint()

    if interactive and not confirm_start():
        print("\nCancelled.")
        pause_before_exit()
        return 0

    _log("Loading engine and model...")
    print("\nLoading model, please wait...")
    engine = _load_engine()
    _log("Analysis started.")
    print("Analysis in progress...\n")
    summary = engine.run(concentrations_by_image=concentrations_by_image, **settings)
    if not isinstance(summary, dict):
        raise RuntimeError("Analysis engine did not return a run summary")

    exit_code = int(summary.get("exit_code", 1))
    successful = int(summary.get("successful_images", 0))
    failed = int(summary.get("failed_images", 0))
    excel_path = summary.get("excel_path", "")

    if exit_code == 0:
        print_done(ROOT)
        _log(f"Analysis finished successfully: {successful} image(s). Results={excel_path}")
    elif exit_code == 2:
        print(
            f"\n[Warning] Analysis partially completed: {successful} image(s) succeeded, "
            f"{failed} image(s) failed."
        )
        print(f"Review the Image_Status sheet in: {excel_path}")
        _log(f"Analysis partially completed: successful={successful}, failed={failed}, results={excel_path}")
    else:
        print(f"\n[Analysis failed] No image was quantified successfully ({failed} failed).")
        print(f"Review the Image_Status sheet in: {excel_path}")
        _log(f"Analysis failed: successful={successful}, failed={failed}, results={excel_path}")

    if interactive:
        pause_before_exit()
    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if "--version" in args:
        print(f"{APP_NAME} {APP_VERSION} ({get_git_commit(ROOT)})")
        return 0

    if "--license" in args:
        print(f"{APP_NAME} {APP_VERSION}")
        print(COPYRIGHT_NOTICE)
        print(f"License: {APP_LICENSE}")
        print("This program comes with ABSOLUTELY NO WARRANTY.")
        print(f"Source: {SOURCE_URL}")
        print(f"Full license: {ROOT / 'LICENSE'}")
        return 0

    if "--cli" in args:
        return run_analysis(interactive=True)

    if "--run" in args:
        return run_analysis(interactive=False)

    # Default: GUI launcher
    try:
        from utils.launcher_gui import run_gui
    except Exception as e:
        print(f"[Warning] GUI unavailable ({e}); falling back to console mode.")
        return run_analysis(interactive=True)

    run_gui()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        err = traceback.format_exc()
        print("\n[Fatal error] The program stopped unexpectedly.")
        print(err)
        try:
            with open(ERROR_LOG, "a", encoding="utf-8") as f:
                f.write("\n===== CRASH =====\n")
                f.write(err)
                f.write("\n")
        except Exception:
            pass
        print(f"\nDetails written to: {ERROR_LOG}")
        print("Please keep the message above for troubleshooting.")
        pause_before_exit()
        raise SystemExit(1)
