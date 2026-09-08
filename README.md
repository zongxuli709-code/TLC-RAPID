# TLC-RAPID

Automated thin-layer chromatography (TLC) spot detection and quantification from digital plate images.

Chinese instructions: [README_zh.md](README_zh.md)

## Quick start

1. Run `TLC-RAPID.exe` — a simple launcher window opens
2. Click **Open images folder** and add TLC images (`.jpg` / `.png`)
3. Click **Edit concentrations** and fill standard amounts (left to right)
4. Choose **Imaging mode** (use `366nm` for fluorescence plates) and click **Start Analysis**
5. After each image you may **manually mark** missed spots (see below)
6. When finished, open results from the launcher (or `runs/predict-seg/`)

> Console-only mode: `TLC-RAPID.exe --cli`
>
> Version and source commit: `TLC-RAPID.exe --version`
>
> License and source notice: `TLC-RAPID.exe --license`

### Included example

The Windows user package includes one anonymized example image with per-image
standard applied amounts, so a complete workflow can be tried immediately.
It is a workflow demonstration, not a validation benchmark. The source
material and applied-amount mapping are documented in
[`example_data`](example_data/README.md).

The exact standard applied amounts are recorded in
`user_input/standard_concentrations.csv`.

The user package supports 64-bit Windows only. Extract it and double-click
`TLC-RAPID.exe`; Python is not required. Developers can find the source
environment and reproduction procedure in the GitHub repository's
[REPRODUCIBILITY.md](https://github.com/zongxuli709-code/TLC-RAPID/blob/v1.0/REPRODUCIBILITY.md).

## Analysis settings

**Standard applied amounts** (`user_input/standard_concentrations.csv`): enter the amount for each standard band from left to right, normally in μg/band. The `(default)` row applies to all images unless overridden by filename.

The number of standards is **not fixed at five**. The default quadratic workflow requires at least **4 distinct, non-negative standards**. The alternative linear regression requires at least **3**. If a quadratic fit changes direction within the standard range, TLC-RAPID records a calibration failure; it never switches methods silently. Restrict the standards to a validated monotonic range or explicitly select linear regression. TLC-RAPID takes the count of populated `standard_*` columns in this table as *N*: the leftmost *N* spots are treated as standards and all spots to their right as samples. The five columns in the template are only an example—add or remove `standard_*` columns and fill in the corresponding amounts.

The result table also reports `Calibration_Quality`. Fits with R2 below 0.75 are marked `poor_fit`; review the standard assignments, detected spots, response axis, and validated range before interpreting those amounts. Quadratic calibration is rejected if its vertex lies inside the standard range. The program never changes the requested method silently; restrict the standards to a validated monotonic range or explicitly select linear regression.

| image_filename | standard_1 | standard_2 | … | notes |
|----------------|------------|------------|---|-------|
| (default)      | 0.125      | 0.2        | … | Used for all images unless overridden |
| MyPlate.jpg    | …          | …          | … | Optional per-image override |

**Optional parameters** (`user_input/analysis_settings.csv`):

| parameter | typical value | meaning |
|-----------|---------------|---------|
| imaging_mode | 366nm / visible / 254nm | For 366 nm fluorescence plates, use `366nm` (not `auto`) |
| quantification_method | quadratic | Default manuscript-aligned model; `linear` is the alternative |
| confidence_threshold | 0.15 | Detection confidence |

## Manual spot marking

| Action | Effect |
|--------|--------|
| **Left-click** | **ADD** a box |
| **Right-click** | **DELETE** a box |
| **S** | Save and continue to the next image |
| **Esc** | Skip manual marking; keep auto results only |

Click the **image** window first so mouse/keyboard shortcuts apply. After **S**, all spots (including manual ones) are re-ordered **left to right** and re-indexed: the leftmost spots are standards (count = number of standard columns in `standard_concentrations.csv`); the rest are samples. Place manual boxes at the correct horizontal position so standards and samples are not mis-assigned.

In annotated output: **green** = standard, **red** = sample, **yellow** = manual (`Spot_Source = manual` in Excel). On some systems the OpenCV window may fail to open; analysis continues with auto detection only.

## Reading results

Each run writes to `runs/predict-seg/exp*/` (or the latest run folder). Sample quantification is in **`quantitative_analysis_all_images.xlsx`**. Enter standard applied amounts (normally μg/band); **`Calculated_Amount_Per_Band`** gives the corresponding result in the same unit. **`Calculated_Concentration`** is retained as a legacy alias and does not perform sample-preparation or application-volume conversion. The **`Metadata`** sheet records the software version, source commit, model/configuration hashes, dependency versions, and analysis parameters needed to trace the result. If **`Out_of_Range`** is `True`, the response or back-calculated amount lies outside the calibrated range and is not a validated quantitative result.

| Column | Meaning |
|--------|---------|
| `Image` | Image file name |
| `Spot_Index` | Spot index (left to right) |
| `Spot_Type` | `standard`: reference; `sample`: unknown |
| `Known_Concentration` | Known standard amount |
| **`Calculated_Amount_Per_Band`** | **Back-calculated sample amount in the standard-input unit** |
| `Calculated_Concentration` | Legacy alias of `Calculated_Amount_Per_Band` |
| `Out_of_Range` | Outside validated calibration range |
| `Range_Status` | Out-of-range classification |
| `Calibration_Y_Axis` | Calibration response metric (IGI / peak_1d / IOD) |
| `Response_Axis_Source` | 366 nm axis selection (`igi` or `peak_1d_fallback`) |

## Source code and license

Source code is publicly available under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. See [LICENSE](LICENSE).

- Repository: https://github.com/zongxuli709-code/TLC-RAPID
- The packaged Windows executable (`TLC-RAPID.exe`) may be distributed together with a clear link to this repository so that recipients can obtain the corresponding source code, as required by AGPL-3.0.

## Research and reproducibility records

- Citation metadata: [CITATION.cff](CITATION.cff)
- Model scope, checksum, and limitations: [MODEL_CARD.md](MODEL_CARD.md)
- Dataset and split requirements: [DATA.md](DATA.md)
- Exact environment and evaluation workflow: [REPRODUCIBILITY.md](REPRODUCIBILITY.md)
- Resolved Windows build environment: [requirements-freeze.txt](requirements-freeze.txt)
- Release history: [CHANGELOG.md](CHANGELOG.md)
- Submission/release checklist: [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)

Before citing a result, retain the generated workbook's `Metadata` and `Image_Status` sheets together with the input manifest and ground truth used for evaluation.

## License

TLC-RAPID — Copyright (C) 2025-2026 Zongxu Li and contributors. The combined
source, executable, and released YOLO-trained weight are licensed under
**GNU AGPL-3.0-only**. Academic and commercial use are permitted when the AGPL
conditions are followed, including corresponding-source obligations. A
closed-source commercial deployment requires separate upstream rights; this
public package does not grant them. See [LICENSING.md](LICENSING.md),
[MODEL_WEIGHTS.md](MODEL_WEIGHTS.md), [MODIFICATIONS.md](MODIFICATIONS.md),
[THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt), and [LICENSE](LICENSE).
