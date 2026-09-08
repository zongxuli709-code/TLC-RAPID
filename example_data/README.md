# TLC-RAPID example data

This directory contains five anonymized demonstration images supplied by the
TLC-RAPID authors. They let reviewers and users verify the complete workflow
without supplying their own data.

## Files

- `images/example-1.jpg`: visible-light image; standards are 0.03125, 0.0625,
  0.125, 0.25, and 0.5 mg/mL from left to right.
- `images/example-2.jpg`: 366 nm image; standards are 0.125, 0.2, 0.25, 0.5,
  and 1.0 mg/mL from left to right.
- `images/example-3.jpg`: 366 nm image with descending standards: 0.4, 0.3,
  0.2, 0.1, and 0.05 mg/mL from left to right.
- `images/example-4.jpg`: visible/254 nm profile; standards are 0.125, 0.2,
  0.25, 0.5, and 1.0 mg/mL.
- `images/example-5.jpg`: visible/254 nm profile; standards are 0.5, 0.75,
  1.0, 1.5, and 2.0 mg/mL.
- `standard_concentrations.csv`: per-image concentration mapping.
- `analysis_settings.csv`: demonstration settings with quadratic quantification; linear regression is available as an alternative.

## Try the example

The Windows user package places these files in `user_input`, ready to run. For
source use, copy the five JPG files to `user_input/images` and replace the two
CSV templates in `user_input` with the CSV files in this directory.

Double-click `TLC-RAPID.exe` in the Windows user package. Review detected spots
in the manual-marking window, then find results under `runs/predict-seg`.

These images demonstrate workflow only and are not a validation benchmark.
Output may vary with manual corrections, dependency versions, and hardware.
