# TLC-RAPID example data

This directory contains two anonymized demonstration images supplied by the
TLC-RAPID authors. They are provided so that reviewers and users can verify the
complete analysis workflow without supplying their own data.

## Files

- `images/example-visible.jpg`: visible-light TLC image. Standards 1-5 are
  0.03125, 0.0625, 0.125, 0.25, and 0.5 mg/mL from left to right.
- `images/example-uv366.jpg`: 366 nm image. Standards 1-5 are 0.125, 0.2,
  0.25, 0.5, and 1.0 mg/mL from left to right.
- `standard_concentrations.csv`: per-image concentration mapping used by the
  software.
- `analysis_settings.csv`: demonstration analysis settings.

## Try the example

The end-user packages already copy these files into `user_input`, so they can
be run immediately. When running from the GitHub source package, copy the two
JPG files to `user_input/images`, then replace the two CSV files in
`user_input` with the CSV files in this directory.

In the Windows user package, double-click `TLC-RAPID.exe`. Review and correct
detected spots in the manual-marking window, then find the results under
`runs/predict-seg`.

These images are demonstration data, not a validation benchmark. Output may
vary with manual corrections, dependency versions, and hardware.
