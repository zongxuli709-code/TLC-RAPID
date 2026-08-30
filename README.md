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

## Analysis settings

**Standard concentrations** (`user_input/standard_concentrations.csv`): enter the amount for each standard spot from left to right; the `(default)` row applies to all images unless overridden by filename.

The number of standards is **not fixed at five**. TLC-RAPID takes the count of populated `standard_*` columns in this table as *N*: the leftmost *N* spots are treated as standards and all spots to their right as samples. The five columns in the template are only an example—for 2, 3, 4, 6, or more standards, add or remove `standard_*` columns and fill in the corresponding amounts.

| image_filename | standard_1 | standard_2 | … | notes |
|----------------|------------|------------|---|-------|
| (default)      | 0.125      | 0.2        | … | Used for all images unless overridden |
| MyPlate.jpg    | …          | …          | … | Optional per-image override |

**Optional parameters** (`user_input/analysis_settings.csv`):

| parameter | typical value | meaning |
|-----------|---------------|---------|
| imaging_mode | 366nm / visible / 254nm | For 366 nm fluorescence plates, use `366nm` (not `auto`) |
| quantification_method | isotonic | Daily use; `quadratic` reproduces the paper workflow |
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

Each run writes to `runs/predict-seg/exp*/` (or the latest run folder). Sample quantification is in **`quantitative_analysis_all_images.xlsx`**; the **`Calculated_Concentration`** column gives the predicted amount for each unknown spot, in the same units as the standards in `standard_concentrations.csv`. If **`Out_of_Range`** is `True`, the response or back-calculated amount lies outside the validated calibration range and should be interpreted with caution.

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

- Repository: `https://github.com/<YOUR_USERNAME>/TLC-RAPID` *(replace with your public URL after publishing)*
- The packaged Windows executable (`TLC-RAPID.exe`) may be distributed together with a clear link to this repository so that recipients can obtain the corresponding source code, as required by AGPL-3.0.

## License

TLC-RAPID — Copyright (c) 2026. Licensed under GNU AGPL-3.0. See [LICENSE](LICENSE).
