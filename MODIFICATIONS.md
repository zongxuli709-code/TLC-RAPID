# Modification statement

TLC-RAPID is a modified work that incorporates source from Ultralytics YOLOv5.
This file provides the prominent modification notice required by GNU AGPL v3
section 5(a).

## Upstream work

- Project: Ultralytics YOLOv5
- Upstream repository: https://github.com/ultralytics/yolov5
- Upstream license: GNU AGPL v3
- Starting revision: **not recoverable from the current repository history**

The local source strongly resembles the YOLOv5 v7-era segmentation code, but a
tag or commit is not inferred from resemblance. The original clone and training
records available for this release do not identify the starting commit, and the
stripped `best.pt` checkpoint contains no upstream Git commit metadata.

## TLC-RAPID modifications

Modification period: 2025-04-29 through 2026-09-02.

The authors modified and extended the upstream work to:

- load a custom TLC spot instance-segmentation checkpoint;
- support visible-light, 254 nm, and 366 nm TLC image response extraction;
- add plate-specific standard assignment, quadratic and isotonic calibration,
  range flags, and concentration back-calculation;
- add manual add/delete review of detected spots;
- generate annotated images, CSV files, plots, and multi-sheet Excel reports;
- add a Windows launcher, frozen executable configuration, input validation,
  result provenance, checksums, evaluation utilities, and release packaging;
- remove runtime dependency installation and make the release environment
  versioned and reproducible.

The most substantially modified upstream-derived areas are `models/`, `utils/`,
and `segment/analyze_engine.py`. Project-specific entry points and release
materials include `run_analysis.py`, `app_metadata.py`,
`evaluate_quantification.py`, `run_testset_eval.py`, the `user_input/`
templates, documentation, tests, and build scripts.

## Downstream changes

Anyone conveying a modified TLC-RAPID version must keep applicable upstream
notices and add a dated description of their own changes. A convenient format
is a new section in this file containing the modifier, date, source revision,
and affected files.
