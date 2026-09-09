# Reproducing TLC-RAPID v1.0

## Source environment

The known-good release environment is Windows, Python 3.12.4, and the pinned
direct dependencies in `requirements-lock.txt`.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-lock.txt
python -m unittest discover -s tests -v
```

`requirements-freeze.txt` records the fully resolved Windows/Python 3.12 build
environment, including transitive and build dependencies. Use it to recreate
the exact Windows release environment; use `requirements-lock.txt` as the
portable direct-dependency specification.

Place the published model at `weights/best.pt` and verify its SHA-256:

```powershell
Get-FileHash weights\best.pt -Algorithm SHA256
```

Expected v1.0 hash:

```text
E507240E8C7BB8E8C3C57ABB20ADEE6FEBA78670F2EDF6E06BCF1AE12A4440A5
```

## Running an analysis

1. Put TLC images in `user_input/images/`.
2. Fill `user_input/standard_concentrations.csv` with standard applied amounts
   from left to right, normally in μg/band.
3. Confirm `user_input/analysis_settings.csv` matches the manuscript method.
4. Run `python run_analysis.py --run` for a non-interactive run or `python run_analysis.py` for the launcher.
5. Inspect `quantitative_analysis_all_images.xlsx`, including `Metadata` and `Image_Status`.

The v1.0 default requests quadratic regression and requires at least four distinct non-negative standard amounts. Linear regression is the explicit alternative and requires at least three standards. For quadratic analysis, each sample is inverted independently: non-real, negative, and out-of-range roots are rejected; a sole remaining root is used; and two remaining roots are resolved by proximity to a local response-based estimate from the same-plate standards. When no quadratic root can be selected, the result records a linear fallback and its reason. If linear inversion is unavailable, a same-plate response interpolation is returned and explicitly identified. TLC-RAPID never silently reverses standard labels, and all fallback and range states remain visible in the exported fields.

The image-analysis output ends at applied amount per band. Reproducing the
manuscript's precision, accuracy, stability, herbal-content, MRE, and paired
t-test results additionally requires the individual raw response values,
replicate and batch identifiers, sample masses, extraction volumes, dilution
factors, application volumes, and paired HPLC results. Summary tables alone are
not sufficient for independent recalculation.

## Detection evaluation

Run the frozen test groups without manual correction:

```powershell
python run_testset_eval.py C:\path\to\test-set
```

After an assessor fills TP, FP, and FN in `人工核对表.csv`, calculate the summary automatically:

```powershell
python run_testset_eval.py --summarize-review runs\predict-seg\testset-核对图\人工核对表.csv
```

The manuscript should additionally archive the final input manifests, ground truth, generated metric CSV, quantitative reference measurements, and the script or notebook that creates every reported table and figure.

## Quantification evaluation

Prepare a CSV or XLSX containing one row per independently measured sample with `Reference_Concentration` and `Calculated_Concentration`. An optional grouping column can identify plate type, batch, or imaging mode.

```powershell
python evaluate_quantification.py paired_concentrations.csv --group-column Plate_Type
```

The generated `quantification_metrics.csv` reports N, MAE, RMSE, mean bias, and R² for each group and overall. Preserve the paired input table alongside the metric output so every reported value can be audited.
