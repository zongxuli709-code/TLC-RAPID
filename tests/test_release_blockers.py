from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from utils.load_user_config import _parse_value, validate_user_input


class ReleaseBlockerTests(unittest.TestCase):
    def test_scientific_notation_is_numeric(self) -> None:
        self.assertEqual(_parse_value("1e-3"), 0.001)
        self.assertEqual(_parse_value("2E4"), 20000.0)

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


if __name__ == "__main__":
    unittest.main()
