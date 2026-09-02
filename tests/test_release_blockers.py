from __future__ import annotations

import csv
import hashlib
import tempfile
import unittest
from pathlib import Path

from app_metadata import APP_VERSION, get_git_commit, sha256_file
from evaluate_quantification import evaluate_quantification_table
from run_testset_eval import summarize_review_sheet
from utils.load_user_config import _parse_value, normalize_quantification_method, validate_user_input


class ReleaseBlockerTests(unittest.TestCase):
    def test_scientific_notation_is_numeric(self) -> None:
        self.assertEqual(_parse_value("1e-3"), 0.001)
        self.assertEqual(_parse_value("2E4"), 20000.0)

    def test_public_version_and_default_method_are_stable(self) -> None:
        self.assertEqual(APP_VERSION, "1.0.0")
        self.assertEqual(normalize_quantification_method(None), "quadratic")
        self.assertEqual(normalize_quantification_method("unknown"), "quadratic")

    def test_provenance_helpers_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = root / "payload.bin"
            payload.write_bytes(b"TLC-RAPID")
            commit = "0123456789abcdef0123456789abcdef01234567"
            (root / "SOURCE_CODE.txt").write_text(
                f"TLC-RAPID v1.0.0\n\nThis executable was built from commit:\n{commit}\n",
                encoding="utf-8",
            )

            self.assertEqual(sha256_file(payload), hashlib.sha256(b"TLC-RAPID").hexdigest().upper())
            self.assertEqual(get_git_commit(root), commit)

    def test_calibration_does_not_silently_reverse_standard_labels(self) -> None:
        from segment.analyze_engine import calculate_calibration_curve_quadratic

        standard_results = [{"Sum_OD": value} for value in (4.0, 3.0, 2.0, 1.0)]
        with self.assertRaisesRegex(ValueError, "will not relabel standards automatically"):
            calculate_calibration_curve_quadratic(
                standard_results,
                [0.1, 0.2, 0.3, 0.4],
                quantification_method="quadratic",
            )

    def test_two_standards_are_rejected_before_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            user_input = Path(temp_dir)
            images = user_input / "images"
            images.mkdir()
            (images / "placeholder.jpg").write_bytes(b"not decoded during validation")
            (user_input / "standard_concentrations.csv").write_text(
                "image_filename,standard_1,standard_2\n"
                "(default),0.1,0.2\n",
                encoding="utf-8",
            )

            issue_codes = {issue.code for issue in validate_user_input(user_input)}

        self.assertIn("too_few_standards", issue_codes)

    def _validate_concentrations(self, values: list[str], method: str = "quadratic") -> set[str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            user_input = Path(temp_dir)
            images = user_input / "images"
            images.mkdir()
            (images / "placeholder.jpg").write_bytes(b"not decoded during validation")
            (user_input / "analysis_settings.csv").write_text(
                "parameter,value\n"
                f"quantification_method,{method}\n",
                encoding="utf-8",
            )
            columns = ",".join(f"standard_{index}" for index in range(1, len(values) + 1))
            (user_input / "standard_concentrations.csv").write_text(
                f"image_filename,{columns}\n"
                f"(default),{','.join(values)}\n",
                encoding="utf-8",
            )
            return {issue.code for issue in validate_user_input(user_input)}

    def test_quadratic_requires_four_standard_levels(self) -> None:
        self.assertIn("too_few_standards", self._validate_concentrations(["0.1", "0.2", "0.3"]))

    def test_isotonic_allows_three_standard_levels(self) -> None:
        self.assertNotIn(
            "too_few_standards",
            self._validate_concentrations(["0.1", "0.2", "0.3"], method="isotonic"),
        )

    def test_duplicate_standard_levels_are_rejected(self) -> None:
        self.assertIn(
            "concentrations_duplicated",
            self._validate_concentrations(["0.1", "0.2", "0.2", "0.4"]),
        )

    def test_negative_standard_levels_are_rejected(self) -> None:
        self.assertIn(
            "concentrations_negative",
            self._validate_concentrations(["-0.1", "0.1", "0.2", "0.4"]),
        )

    def test_review_metrics_are_summarized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sheet = Path(temp_dir) / "review.csv"
            with sheet.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["组别", "图片", "TP对了", "FP多检", "FN漏检"])
                writer.writerow(["visible", "a.jpg", 8, 2, 1])
                writer.writerow(["visible", "b.jpg", 4, 1, 2])
                writer.writerow(["366nm", "c.jpg", 5, 0, 1])
            output = summarize_review_sheet(sheet)
            with output.open("r", encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))

        overall = next(row for row in rows if row["Group"] == "Overall")
        self.assertEqual(overall["TP"], "17")
        self.assertEqual(overall["FP"], "3")
        self.assertEqual(overall["FN"], "4")
        self.assertAlmostEqual(float(overall["Precision"]), 0.85, places=6)

    def test_quantification_error_metrics_are_summarized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pairs = Path(temp_dir) / "pairs.csv"
            pairs.write_text(
                "Plate,Reference_Concentration,Calculated_Concentration\n"
                "visible,1,1.2\n"
                "visible,2,1.8\n"
                "366nm,3,3.1\n",
                encoding="utf-8",
            )
            output = evaluate_quantification_table(pairs, group_column="Plate")
            with output.open("r", encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))

        overall = next(row for row in rows if row["Group"] == "Overall")
        self.assertEqual(overall["N"], "3")
        self.assertAlmostEqual(float(overall["MAE"]), 1 / 6, places=6)
        self.assertAlmostEqual(float(overall["Bias"]), 1 / 30, places=6)


if __name__ == "__main__":
    unittest.main()
