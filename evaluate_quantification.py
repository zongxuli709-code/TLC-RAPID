"""Calculate manuscript-ready concentration error metrics from paired reference data."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import r2_score


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    return pd.read_csv(path, encoding="utf-8-sig")


def evaluate_quantification_table(
    input_path: Path,
    *,
    reference_column: str = "Reference_Concentration",
    predicted_column: str = "Calculated_Concentration",
    group_column: str | None = None,
    output_path: Path | None = None,
) -> Path:
    """Write N, MAE, RMSE, bias, and R2 for complete finite reference/prediction pairs."""
    input_path = Path(input_path)
    if not input_path.is_file():
        raise FileNotFoundError(f"Quantification table not found: {input_path}")

    df = _read_table(input_path)
    required = [reference_column, predicted_column]
    if group_column:
        required.append(group_column)
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")

    numeric = df.loc[:, [reference_column, predicted_column]].apply(pd.to_numeric, errors="coerce")
    complete = numeric.notna().all(axis=1)
    finite = np.isfinite(numeric[reference_column]) & np.isfinite(numeric[predicted_column])
    valid = complete & finite
    if not valid.any():
        raise ValueError("No complete finite reference/prediction pairs were found")

    working = df.loc[valid, [group_column] if group_column else []].copy()
    working[reference_column] = numeric.loc[valid, reference_column].astype(float)
    working[predicted_column] = numeric.loc[valid, predicted_column].astype(float)

    def metric_row(group: str, group_df: pd.DataFrame) -> dict[str, float | int | str]:
        reference = group_df[reference_column].to_numpy(dtype=float)
        predicted = group_df[predicted_column].to_numpy(dtype=float)
        errors = predicted - reference
        r2 = float(r2_score(reference, predicted)) if len(reference) >= 2 and np.ptp(reference) > 0 else np.nan
        return {
            "Group": group,
            "N": int(len(reference)),
            "MAE": float(np.mean(np.abs(errors))),
            "RMSE": float(np.sqrt(np.mean(errors**2))),
            "Bias": float(np.mean(errors)),
            "R2": r2,
        }

    rows: list[dict[str, float | int | str]] = []
    if group_column:
        rows.extend(
            metric_row(str(group), group_df)
            for group, group_df in working.groupby(group_column, sort=True)
        )
    rows.append(metric_row("Overall", working))

    output_path = Path(output_path) if output_path else input_path.with_name("quantification_metrics.csv")
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig", float_format="%.10g")
    return output_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="CSV/XLSX containing paired reference and predicted concentrations")
    parser.add_argument("--reference-column", default="Reference_Concentration")
    parser.add_argument("--predicted-column", default="Calculated_Concentration")
    parser.add_argument("--group-column", default=None)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    output = evaluate_quantification_table(
        args.input,
        reference_column=args.reference_column,
        predicted_column=args.predicted_column,
        group_column=args.group_column,
        output_path=args.output,
    )
    print(f"Quantification metrics saved: {output}")


if __name__ == "__main__":
    main()
