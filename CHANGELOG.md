# Changelog

## 1.0 — 2026-09-07

- Added traceable Windows release metadata and source-code links.
- Added per-image success/failure reporting and an `Image_Status` worksheet.
- Added a reproducibility `Metadata` worksheet containing software, commit, model, configuration, dependency, and analysis information.
- Standardized the manuscript workflow on quadratic quantification.
- Required at least four distinct non-negative standards for quadratic quantification.
- Removed silent standard-concentration reversal and runtime dependency installation.
- Added input validation, regression tests, automatic detection/quantification metric summaries, model/data documentation, and a locked known-good environment.
- Added two anonymized, licensed example images with correct per-image standard
  concentrations for an immediate trial run.
- The end-user release is a self-contained 64-bit Windows executable package;
  ordinary users do not need to create a Python environment.
