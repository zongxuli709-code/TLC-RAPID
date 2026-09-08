# TLC-RAPID example data

This directory contains one release demonstration image and four retained
diagnostic images supplied by the TLC-RAPID authors. Only `example-5.jpg`,
which passes the default quadratic-calibration safety checks, is copied into
the Windows user package. Images 1–4 are retained for investigation because
their recorded standard assignments produce non-invertible quadratic fits;
they are not configured as successful workflow examples.

## Files

- `images/example-5.jpg`: visible-light berberine example. The five working
  concentrations (0.50, 0.75, 1.00, 1.50, and 2.00 mg/mL) were each applied
  at 3 μL. The software input is therefore 1.50, 2.25, 3.00, 4.50, and
  6.00 μg/band from left to right.
- `standard_concentrations.csv`: per-image applied-amount mapping.
- `analysis_settings.csv`: demonstration settings with quadratic quantification; linear regression is available as an alternative.
- `images/example-1.jpg` through `example-4.jpg`: diagnostic images excluded
  from the Windows user package. They require review of standard-band
  assignment and ROI selection and must not be presented as successful
  paper-reproduction examples.

## Try the example

The Windows user package places these files in `user_input`, ready to run. For
source use, copy the JPG file to `user_input/images` and replace the two
CSV templates in `user_input` with the CSV files in this directory.

Double-click `TLC-RAPID.exe` in the Windows user package. Review detected spots
in the manual-marking window, then find results under `runs/predict-seg`.

This image demonstrates workflow only and is not a validation benchmark.
Output may vary with manual corrections, dependency versions, and hardware.
