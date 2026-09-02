# -*- coding: utf-8 -*-
"""批量跑测试集（不弹窗、不手动补框），保存带框结果供人工核对。"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

from app_paths import app_root

ROOT = app_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_ROOT = ROOT / "runs" / "predict-seg"
REVIEW_ROOT = OUT_ROOT / "testset-核对图"

# 沿用你之前测这批图时的参数：白板/蓝板更敏感，绿板用软件默认
GROUPS = [
    {
        "folder": "1-白板（可见光）",
        "name": "testset-白板",
        "conf_thres": 0.04,
        "iou_thres": 0.3,
        "y_tolerance": 80,
        "fixed_width": 130,
        "fixed_height": 35,
        "imaging_mode": "visible",
    },
    {
        "folder": "2-蓝板（366nm）",
        "name": "testset-蓝板",
        "conf_thres": 0.05,
        "iou_thres": 0.45,
        "y_tolerance": 100,
        "fixed_width": 140,
        "fixed_height": 30,
        "imaging_mode": "366nm",
    },
    {
        "folder": "3-绿板（254nm）",
        "name": "testset-绿板",
        "conf_thres": 0.15,
        "iou_thres": 0.3,
        "y_tolerance": 60,
        "fixed_width": 130,
        "fixed_height": 35,
        "imaging_mode": "254nm",
    },
]


def _copy_review_images(src_dir: Path, dst_dir: Path) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    for ext in (".jpg", ".jpeg", ".png", ".bmp"):
        for img in src_dir.glob(f"*{ext}"):
            stem = img.stem
            if stem.endswith("_masked") or "calibration_curve" in stem:
                continue
            shutil.copy2(img, dst_dir / img.name)


def _write_review_sheet(group_dirs: list[tuple[str, Path]]) -> Path:
    import csv

    sheet = REVIEW_ROOT / "人工核对表.csv"
    rows = [
        [
            "组别",
            "图片",
            "模型检出斑点数",
            "TP对了",
            "FP多检",
            "FN漏检",
            "备注",
        ]
    ]
    for group_name, out_dir in group_dirs:
        excel = out_dir / "quantitative_analysis_all_images.xlsx"
        counts: dict[str, int] = {}
        if excel.exists():
            import pandas as pd

            df = pd.read_excel(excel)
            if "Image" in df.columns:
                counts = df.groupby("Image").size().to_dict()
        images = sorted(
            [
                p
                for p in out_dir.iterdir()
                if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}
                and not p.stem.endswith("_masked")
                and "calibration_curve" not in p.stem
            ],
            key=lambda p: p.name,
        )
        for img in images:
            n = counts.get(img.name, "")
            rows.append([group_name, img.name, n, "", "", "", ""])

    with open(sheet, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)
    return sheet


def summarize_review_sheet(sheet: Path, output: Path | None = None) -> Path:
    """Calculate reproducible detection metrics from a completed review sheet."""
    import pandas as pd

    sheet = Path(sheet)
    if not sheet.is_file():
        raise FileNotFoundError(f"找不到人工核对表: {sheet}")

    df = pd.read_csv(sheet, encoding="utf-8-sig")
    required = ("组别", "TP对了", "FP多检", "FN漏检")
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"人工核对表缺少列: {', '.join(missing)}")

    numeric_columns = ("TP对了", "FP多检", "FN漏检")
    numeric = df.loc[:, numeric_columns].apply(pd.to_numeric, errors="coerce")
    completed = numeric.notna().all(axis=1)
    if not completed.any():
        raise ValueError("人工核对表尚无完整的 TP / FP / FN 记录")

    reviewed = df.loc[completed, ["组别"]].copy()
    reviewed.loc[:, numeric_columns] = numeric.loc[completed, numeric_columns]
    values = reviewed.loc[:, numeric_columns].to_numpy(dtype=float)
    if (values < 0).any() or not (values == values.astype(int)).all():
        raise ValueError("TP / FP / FN 必须是非负整数")
    reviewed.loc[:, numeric_columns] = values.astype(int)

    def metric_row(group_name: str, group_df: pd.DataFrame) -> dict[str, float | int | str]:
        tp = int(group_df["TP对了"].sum())
        fp = int(group_df["FP多检"].sum())
        fn = int(group_df["FN漏检"].sum())
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {
            "Group": group_name,
            "Reviewed_Images": int(len(group_df)),
            "TP": tp,
            "FP": fp,
            "FN": fn,
            "Precision": precision,
            "Recall": recall,
            "F1": f1,
        }

    rows = [metric_row(str(group), group_df) for group, group_df in reviewed.groupby("组别", sort=True)]
    rows.append(metric_row("Overall", reviewed))
    summary = pd.DataFrame(rows)
    output = Path(output) if output else sheet.with_name("metrics_summary.csv")
    summary.to_csv(output, index=False, encoding="utf-8-sig", float_format="%.6f")
    return output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the TLC-RAPID test-set review workflow")
    parser.add_argument("test_root", type=Path, nargs="?", help="test-set root containing the configured group folders")
    parser.add_argument("--weights", type=Path, default=ROOT / "weights" / "best.pt")
    parser.add_argument("--data", type=Path, default=ROOT / "weights" / "boCenColor.yaml")
    parser.add_argument(
        "--summarize-review",
        type=Path,
        help="calculate Precision, Recall, and F1 from a completed manual review CSV without running inference",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.summarize_review:
        summary = summarize_review_sheet(args.summarize_review.expanduser().resolve())
        print(f"指标汇总已保存: {summary}")
        return
    if args.test_root is None:
        raise SystemExit("test_root is required unless --summarize-review is used")

    import matplotlib

    matplotlib.use("Agg")

    from segment import analyze_engine as engine

    test_root = args.test_root.expanduser().resolve()
    weights = args.weights.expanduser().resolve()
    data = args.data.expanduser().resolve()

    if not test_root.exists():
        raise FileNotFoundError(f"找不到测试集目录: {test_root}")
    if not weights.exists():
        raise FileNotFoundError(f"找不到模型权重: {weights}")
    if not data.exists():
        raise FileNotFoundError(f"找不到数据配置: {data}")

    print("=" * 60)
    print("测试集批量检测（关闭手动补框，结果供人工核对）")
    print(f"测试集: {test_root}")
    print(f"权重: {weights}")
    print("=" * 60)

    group_dirs: list[tuple[str, Path]] = []
    for group in GROUPS:
        source = test_root / group["folder"]
        if not source.exists():
            print(f"[跳过] 不存在: {source}")
            continue
        n_img = len(
            [
                p
                for p in source.iterdir()
                if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
            ]
        )
        print(f"\n>>> {group['folder']}  {n_img} 张  conf={group['conf_thres']}")
        engine.run(
            weights=str(weights),
            source=str(source),
            data=str(data),
            conf_thres=group["conf_thres"],
            iou_thres=group["iou_thres"],
            y_tolerance=group["y_tolerance"],
            fixed_width=group["fixed_width"],
            fixed_height=group["fixed_height"],
            imaging_mode=group.get("imaging_mode", "auto"),
            quantification_method="quadratic",
            view_img=False,
            manual_mark=False,
            save_txt=True,
            save_conf=True,
            nosave=False,
            project=str(OUT_ROOT),
            name=group["name"],
            exist_ok=True,
        )
        out_dir = OUT_ROOT / group["name"]
        group_dirs.append((group["folder"], out_dir))
        review_dir = REVIEW_ROOT / group["folder"]
        _copy_review_images(out_dir, review_dir)
        print(f"已复制核对图到: {review_dir}")

    sheet = _write_review_sheet(group_dirs)
    print("\n" + "=" * 60)
    print("全部跑完。请打开核对图文件夹：")
    print(f"  {REVIEW_ROOT}")
    print(f"核对表: {sheet}")
    print("在表里填 TP / FP / FN 后发给我，即可算 Precision、Recall、F1。")
    print("=" * 60)


if __name__ == "__main__":
    main()
