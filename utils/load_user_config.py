# -*- coding: utf-8 -*-
"""Load analysis settings and standard concentrations from user_input/."""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from app_paths import app_root

ROOT = app_root()
USER_INPUT_DIR = ROOT / "user_input"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SETTINGS_NAMES = (
    "analysis_settings.csv",
    "analysis_settings.xlsx",
    "分析设置.csv",
    "分析设置.xlsx",
)
CONCENTRATIONS_NAMES = (
    "standard_concentrations.csv",
    "standard_concentrations.xlsx",
    "标准品浓度.csv",
    "标准品浓度.xlsx",
)

DEFAULT_SETTINGS: dict[str, Any] = {
    "model_weights": "weights/best.pt",
    "dataset_config": "weights/boCenColor.yaml",
    "standard_count": 5,
    "y_axis_type": "sum_od",
    "transform_type": "auto",
    "roi_width": 130,
    "roi_height": 35,
    "confidence_threshold": 0.15,
    "y_tolerance": 60,
    "images_folder": "images",
    "quantification_method": "isotonic",
    "imaging_mode": "auto",
}

DEFAULT_CONCENTRATIONS = [0.125, 0.2, 0.25, 0.5, 1]

# Maps config parameter names (English or legacy Chinese) to run() kwargs.
SETTING_KEY_MAP = {
    "model_weights": "weights",
    "weights_file": "weights",
    "模型权重": "weights",
    "dataset_config": "data",
    "数据集配置": "data",
    "standard_count": "standard_num",
    "标准品数量": "standard_num",
    "y_axis_type": "y_axis_type",
    "纵坐标类型": "y_axis_type",
    "transform_type": "transform_type",
    "数据变换": "transform_type",
    "roi_width": "fixed_width",
    "矩形宽度": "fixed_width",
    "roi_height": "fixed_height",
    "矩形高度": "fixed_height",
    "confidence_threshold": "conf_thres",
    "置信度阈值": "conf_thres",
    "y_tolerance": "y_tolerance",
    "水平带容忍": "y_tolerance",
    "images_folder": "images_subdir",
    "图片文件夹": "images_subdir",
    "quantification_method": "quantification_method",
    "定量方法": "quantification_method",
    "imaging_mode": "imaging_mode",
    "成像模式": "imaging_mode",
}

SETTINGS_PARAM_COLUMNS = ("parameter", "param", "参数名", "key", "name")
SETTINGS_VALUE_COLUMNS = ("value", "值", "val")

CONC_IMAGE_COLUMNS = ("image_filename", "image", "filename", "图片文件名")
CONC_DEFAULT_MARKERS = {
    "(default)",
    "default",
    "_default",
    "（默认）",
    "(默认)",
    "默认",
}
STANDARD_COL_PREFIXES = ("standard_", "std_", "标准品")


@dataclass(frozen=True)
class ValidationIssue:
    level: str  # "error" | "warning"
    code: str
    title: str
    next_steps: tuple[str, ...]
    path: Path | None = None


def normalize_quantification_method(value: Any) -> str:
    if value is None:
        return "isotonic"
    text = str(value).strip().lower().replace(" ", "")
    aliases = {
        "isotonic": "isotonic",
        "iso": "isotonic",
        "等单调": "isotonic",
        "等单调回归": "isotonic",
        "quadratic": "quadratic",
        "quad": "quadratic",
        "poly2": "quadratic",
        "二次": "quadratic",
        "二次反算": "quadratic",
        "二次方程": "quadratic",
        "二次方程反算": "quadratic",
    }
    if text in aliases:
        return aliases[text]
    if "二次" in text or "quadratic" in text or "poly" in text:
        return "quadratic"
    if "单调" in text or "isotonic" in text or "iso" in text:
        return "isotonic"
    return "isotonic"


def minimum_standard_count(quantification_method: Any) -> int:
    """Return the minimum defensible number of standards for the selected fit."""
    return 4 if normalize_quantification_method(quantification_method) == "quadratic" else 3


def normalize_imaging_mode(value: Any) -> str:
    if value is None:
        return "auto"
    text = str(value).strip().lower().replace(" ", "")
    aliases = {
        "auto": "auto",
        "自动": "auto",
        "visible": "visible",
        "可见光": "visible",
        "白光": "visible",
        "white": "visible",
        "366": "366nm",
        "366nm": "366nm",
        "荧光": "366nm",
        "blue": "366nm",
        "254": "254nm",
        "254nm": "254nm",
        "紫外": "254nm",
        "uv": "254nm",
        "绿板": "254nm",
    }
    if text in aliases:
        return aliases[text]
    if "366" in text or "荧光" in text:
        return "366nm"
    if "254" in text or "紫外" in text:
        return "254nm"
    if "可见" in text or "visible" in text:
        return "visible"
    return "auto"


def _find_config_file(directory: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        path = directory / name
        if path.exists():
            return path
    return None


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".xlsx":
        return pd.read_excel(path, dtype=str)

    encodings = ("utf-8-sig", "utf-8", "gbk", "gb18030", "cp936")
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            return pd.read_csv(path, dtype=str, encoding=encoding)
        except UnicodeDecodeError as e:
            last_error = e
            continue
    raise UnicodeDecodeError(
        "read_table",
        b"",
        0,
        1,
        f"Cannot read {path.name}; tried: {', '.join(encodings)}. {last_error}",
    )


def _parse_value(raw: Any) -> Any:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def _pick_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    lower_map = {str(c).strip().lower(): str(c) for c in columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def _is_standard_column(name: str) -> bool:
    text = str(name).strip().lower()
    if text in ("notes", "remark", "remarks", "备注"):
        return False
    return any(text.startswith(prefix) for prefix in STANDARD_COL_PREFIXES)


def update_settings_values(
    updates: dict[str, Any],
    user_input_dir: Path | None = None,
) -> Path:
    """Update parameter values in analysis_settings.csv (create file if missing)."""
    user_input_dir = Path(user_input_dir or USER_INPUT_DIR)
    user_input_dir.mkdir(parents=True, exist_ok=True)
    config_path = _find_config_file(user_input_dir, SETTINGS_NAMES)
    if config_path is None:
        config_path = user_input_dir / "analysis_settings.csv"
        rows = [
            {"parameter": key, "value": value, "description": ""}
            for key, value in DEFAULT_SETTINGS.items()
        ]
        pd.DataFrame(rows).to_csv(config_path, index=False, encoding="utf-8-sig")

    df = _read_table(config_path)
    param_col = _pick_column(list(df.columns), SETTINGS_PARAM_COLUMNS)
    value_col = _pick_column(list(df.columns), SETTINGS_VALUE_COLUMNS)
    if not param_col or not value_col:
        raise ValueError(f"Cannot parse settings file: {config_path}")

    keys_lower = {str(k).strip().lower(): i for i, k in enumerate(df[param_col].tolist())}
    for key, value in updates.items():
        key_l = str(key).strip().lower()
        if key_l in keys_lower:
            df.at[keys_lower[key_l], value_col] = value
        else:
            new_row = {col: "" for col in df.columns}
            new_row[param_col] = key
            new_row[value_col] = value
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    if config_path.suffix.lower() == ".xlsx":
        df.to_excel(config_path, index=False)
    else:
        df.to_csv(config_path, index=False, encoding="utf-8-sig")
    return config_path


def load_settings(user_input_dir: Path | None = None) -> dict[str, Any]:
    user_input_dir = Path(user_input_dir or USER_INPUT_DIR)
    settings = dict(DEFAULT_SETTINGS)

    config_path = _find_config_file(user_input_dir, SETTINGS_NAMES)
    if config_path:
        df = _read_table(config_path)
        param_col = _pick_column(list(df.columns), SETTINGS_PARAM_COLUMNS)
        value_col = _pick_column(list(df.columns), SETTINGS_VALUE_COLUMNS)
        if param_col and value_col:
            for _, row in df.iterrows():
                key = str(row[param_col]).strip()
                value = _parse_value(row[value_col])
                if key and value is not None:
                    settings[key] = value

    run_kwargs: dict[str, Any] = {}
    for cfg_key, en_key in SETTING_KEY_MAP.items():
        if cfg_key in settings:
            run_kwargs[en_key] = settings[cfg_key]

    images_subdir = str(
        settings.get("images_folder", settings.get("图片文件夹", "images"))
    )
    run_kwargs["source"] = user_input_dir / images_subdir

    for path_key in ("weights", "data"):
        if path_key in run_kwargs:
            p = Path(str(run_kwargs[path_key]))
            if not p.is_absolute():
                run_kwargs[path_key] = ROOT / p

    qm_raw = settings.get("quantification_method", settings.get("定量方法", "isotonic"))
    im_raw = settings.get("imaging_mode", settings.get("成像模式", "auto"))
    run_kwargs["standard_concentrations"] = ",".join(str(x) for x in DEFAULT_CONCENTRATIONS)
    run_kwargs["quantification_method"] = normalize_quantification_method(qm_raw)
    run_kwargs["imaging_mode"] = normalize_imaging_mode(im_raw)
    return run_kwargs


def _normalize_image_key(name: str) -> str:
    return Path(str(name).strip()).name.lower()


def load_concentrations(user_input_dir: Path | None = None) -> dict[str, list[float]]:
    user_input_dir = Path(user_input_dir or USER_INPUT_DIR)
    result: dict[str, list[float]] = {"_default": list(DEFAULT_CONCENTRATIONS)}

    config_path = _find_config_file(user_input_dir, CONCENTRATIONS_NAMES)
    if not config_path:
        return result

    df = _read_table(config_path)
    if df.empty:
        return result

    conc_cols = [c for c in df.columns if _is_standard_column(c)]
    if not conc_cols:
        skip = set(CONC_IMAGE_COLUMNS) | {"notes", "remark", "remarks", "备注"}
        conc_cols = [c for c in df.columns if c not in skip]

    image_col = _pick_column(list(df.columns), CONC_IMAGE_COLUMNS) or df.columns[0]

    for _, row in df.iterrows():
        image_name = str(row.get(image_col, "")).strip()
        if image_name.lower() in ("nan", "none"):
            image_name = ""
        concentrations: list[float] = []
        for col in conc_cols:
            val = _parse_value(row.get(col))
            if val is not None and isinstance(val, (int, float)):
                concentrations.append(float(val))

        if not concentrations:
            continue

        marker = image_name.lower().replace(" ", "")
        if (
            not image_name
            or marker in CONC_DEFAULT_MARKERS
            or "default" in marker
            or "默认" in image_name
        ):
            result["_default"] = concentrations
        else:
            result[image_name] = concentrations

    return result


def get_concentrations_for_image(concentrations_by_image: dict[str, list[float]], image_name: str) -> list[float]:
    if not concentrations_by_image:
        return list(DEFAULT_CONCENTRATIONS)

    if image_name in concentrations_by_image:
        return concentrations_by_image[image_name]

    norm_name = _normalize_image_key(image_name)
    stem_name = Path(norm_name).stem

    norm_index: dict[str, list[float]] = {}
    stem_index: dict[str, list[float]] = {}
    for key, values in concentrations_by_image.items():
        if key == "_default":
            continue
        norm_index[_normalize_image_key(key)] = values
        stem_index[Path(_normalize_image_key(key)).stem] = values

    if norm_name in norm_index:
        return norm_index[norm_name]
    if stem_name in stem_index:
        return stem_index[stem_name]

    return concentrations_by_image.get("_default", list(DEFAULT_CONCENTRATIONS))


def count_images(source: Path) -> int:
    if not source.is_dir():
        return 0
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
    return sum(1 for f in source.iterdir() if f.suffix.lower() in exts)


def validate_user_input(user_input_dir: Path | None = None) -> list[ValidationIssue]:
    user_input_dir = Path(user_input_dir or USER_INPUT_DIR)
    issues: list[ValidationIssue] = []

    if not user_input_dir.exists():
        issues.append(
            ValidationIssue(
                level="error",
                code="missing_user_input",
                title="user_input folder is missing",
                path=user_input_dir,
                next_steps=(
                    "Make sure the program folder is complete and not quarantined by antivirus",
                    "If you downloaded a zip, extract all files before running",
                ),
            )
        )
        return issues

    settings = load_settings(user_input_dir)
    source = Path(settings["source"])
    if not source.exists():
        issues.append(
            ValidationIssue(
                level="error",
                code="images_folder_missing",
                title="Images folder not found",
                path=source,
                next_steps=(
                    "Create user_input/images/",
                    "Copy your TLC images (.jpg / .png) into that folder",
                ),
            )
        )
    elif source.is_dir() and count_images(source) == 0:
        issues.append(
            ValidationIssue(
                level="error",
                code="images_empty",
                title="Images folder is empty",
                path=source,
                next_steps=(
                    "Copy TLC images (.jpg / .png / .bmp) into the folder above",
                    "Check file extensions — not hidden names like image.jpg.txt",
                ),
            )
        )

    weights = Path(settings.get("weights", ROOT / "weights/best.pt"))
    if not weights.exists():
        issues.append(
            ValidationIssue(
                level="error",
                code="weights_missing",
                title="Model weights file not found",
                path=weights,
                next_steps=(
                    "Make sure weights/best.pt exists and is not quarantined",
                    "If the package is incomplete, re-extract or contact the distributor",
                ),
            )
        )

    data_yaml = Path(settings.get("data", ROOT / "weights/boCenColor.yaml"))
    if not data_yaml.exists():
        issues.append(
            ValidationIssue(
                level="error",
                code="dataset_config_missing",
                title="Dataset config file not found",
                path=data_yaml,
                next_steps=("Make sure weights/boCenColor.yaml exists",),
            )
        )

    conc_path = _find_config_file(user_input_dir, CONCENTRATIONS_NAMES)
    if conc_path is None:
        issues.append(
            ValidationIssue(
                level="warning",
                code="concentrations_default",
                title="standard_concentrations.csv not found; using built-in defaults",
                path=user_input_dir / "standard_concentrations.csv",
                next_steps=(
                    "Open user_input/standard_concentrations.csv in Excel",
                    "Enter standard amounts left to right for each standard spot",
                ),
            )
        )
    else:
        try:
            concentrations_by_image = load_concentrations(user_input_dir)
        except Exception as e:
            issues.append(
                ValidationIssue(
                    level="error",
                    code="concentrations_invalid",
                    title=f"Cannot read standard concentrations: {e}",
                    path=conc_path,
                    next_steps=("Correct the concentration table and try again",),
                )
            )
        else:
            quantification_method = settings.get("quantification_method", "quadratic")
            minimum_count = minimum_standard_count(quantification_method)
            for image_name, concentrations in concentrations_by_image.items():
                label = "(default)" if image_name == "_default" else image_name
                if len(concentrations) < minimum_count:
                    issues.append(
                        ValidationIssue(
                            level="error",
                            code="too_few_standards",
                            title=(
                                f"{label} has fewer than {minimum_count} standard concentrations "
                                f"for {quantification_method} quantification"
                            ),
                            path=conc_path,
                            next_steps=(
                                f"Enter at least {minimum_count} standard concentrations from left to right",
                                "Remove incomplete rows that are not used",
                            ),
                        )
                    )
                if not all(math.isfinite(value) for value in concentrations):
                    issues.append(
                        ValidationIssue(
                            level="error",
                            code="concentrations_not_finite",
                            title=f"{label} contains NaN or an infinite concentration",
                            path=conc_path,
                            next_steps=("Replace every concentration with a finite number",),
                        )
                    )
                    continue
                if any(value < 0 for value in concentrations):
                    issues.append(
                        ValidationIssue(
                            level="error",
                            code="concentrations_negative",
                            title=f"{label} contains a negative concentration",
                            path=conc_path,
                            next_steps=("Use zero for a blank standard and non-negative values for all other standards",),
                        )
                    )
                if len(set(concentrations)) != len(concentrations):
                    issues.append(
                        ValidationIssue(
                            level="error",
                            code="concentrations_duplicated",
                            title=f"{label} contains duplicate standard concentrations",
                            path=conc_path,
                            next_steps=(
                                "Use distinct calibration levels",
                                "Put technical replicates in separate lanes or images and summarize them explicitly",
                            ),
                        )
                    )

    return issues


def is_blocking_issue(issue: ValidationIssue) -> bool:
    return issue.level == "error"


def is_blocking_error(message: str) -> bool:
    """Legacy helper — kept for compatibility."""
    blocking_prefixes = (
        "Missing folder",
        "Images folder not found",
        "Images folder is empty",
        "Model weights not found",
        "Dataset config not found",
    )
    return message.startswith(blocking_prefixes)
