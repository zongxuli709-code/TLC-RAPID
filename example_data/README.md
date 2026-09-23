# TLC-RAPID example data

This directory contains five demonstration images supplied by the TLC-RAPID
authors. Each image has its own recorded standard concentrations.

## Files

The five demonstration images are:

- `images/Arnebiae Radix.jpg`
- `images/Phellodendri Chinensis Cortex.jpg`
- `images/Lonicerae Flos.jpg`
- `images/Lonicerae Japonicae Flos.jpg`
- `images/Gentianae Macrophyllae Radix.jpg`

Their plate-specific standard concentrations are stored in
`standard_concentrations.csv`.
- `standard_concentrations.csv`: per-image applied-amount mapping.
- `analysis_settings.csv`: demonstration settings with quadratic as the
  requested method.

For quadratic analysis, TLC-RAPID first evaluates the non-negative roots inside
the image-specific standard range. If two roots remain, it selects the root
closest to a local estimate from the same-plate standards. If no root can be
selected, it records a linear fallback and, if needed, a same-plate response
interpolation fallback. The exported root, method, reason, and range fields
identify how every numeric estimate was obtained.

## Try the examples

The release contains all five worked images and their image-specific standard
amounts. Release verification produced a numeric result for every detected
sample band in the five image sets. The exported result table identifies
whether each value used a direct quadratic root, a branch-selected quadratic
root, or a labelled fallback estimate. Out-of-range estimates are not
validated quantitative results.

The Windows user package places these files in `user_input`, ready to run. For
source use, copy the JPG files to `user_input/images` and replace the two
CSV templates in `user_input` with the CSV files in this directory.

Double-click `TLC-RAPID.exe` in the Windows user package. Review detected spots
in the manual-marking window, then find results under `runs/predict-seg`.

These images demonstrate the workflow only and are not validation benchmarks.
Output may vary with manual corrections, dependency versions, and hardware.
