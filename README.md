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

The Windows user package includes two anonymized example images with per-image
standard concentrations, so a complete workflow can be tried immediately.
They are workflow demonstrations, not a validation benchmark. The source
materials and concentration mapping are documented in
[`example_data`](example_data/README.md).

- `example-visible.jpg`: 0.03125, 0.0625, 0.125, 0.25, and 0.5 mg/mL.
- `example-uv366.jpg`: 0.125, 0.2, 0.25, 0.5, and 1.0 mg/mL.

The user package supports 64-bit Windows only. Extract it and double-click
`TLC-RAPID.exe`; Python is not required. Developers can find the source
environment and reproduction procedure in [REPRODUCIBILITY.md](REPRODUCIBILITY.md).

## Analysis settings

**Standard concentrations** (`user_input/standard_concentrations.csv`): enter the amount for each standard spot from left to right; the `(default)` row applies to all images unless overridden by filename.

The number of standards is **not fixed at five**. The default quadratic paper workflow requires at least **4 distinct, non-negative standards**; isotonic mode requires at least **3**. TLC-RAPID takes the count of populated `standard_*` columns in this table as *N*: the leftmost *N* spots are treated as standards and all spots to their right as samples. The five columns in the template are only an example—add or remove `standard_*` columns and fill in the corresponding amounts.

| image_filename | standard_1 | standard_2 | … | notes |
|----------------|------------|------------|---|-------|
| (default)      | 0.125      | 0.2        | … | Used for all images unless overridden |
| MyPlate.jpg    | …          | …          | … | Optional per-image override |

**Optional parameters** (`user_input/analysis_settings.csv`):

| parameter | typical value | meaning |
|-----------|---------------|---------|
| imaging_mode | 366nm / visible / 254nm | For 366 nm fluorescence plates, use `366nm` (not `auto`) |
| quantification_method | quadratic | Paper/default workflow; `isotonic` is the monotonic alternative |
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

Each run writes to `runs/predict-seg/exp*/` (or the latest run folder). Sample quantification is in **`quantitative_analysis_all_images.xlsx`**; the **`Calculated_Concentration`** column gives the predicted amount for each unknown spot, in the same units as the standards in `standard_concentrations.csv`. The **`Metadata`** sheet records the software version, source commit, model/configuration hashes, dependency versions, and analysis parameters needed to trace the result. If **`Out_of_Range`** is `True`, the response or back-calculated amount lies outside the validated calibration range and should be interpreted with caution.

| Column | Meaning |
|--------|---------|
| `Image` | Image file name |
| `Spot_Index` | Spot index (left to right) |
| `Spot_Type` | `standard`: reference; `sample`: unknown |
| `Known_Concentration` | Known standard amount |
| **`Calculated_Concentration`** | **Predicted sample amount** |
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
