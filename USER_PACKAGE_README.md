# TLC-RAPID Windows user package

The five included worked example images are ready to run. Results are written
to `runs/predict-seg`. Every detected sample band in the five release examples
produced a numeric result during release verification; the exported table
identifies the applied calculation method and any out-of-range flag.

This package supports 64-bit Windows only. Extract the entire ZIP, then
double-click `TLC-RAPID.exe`. No Python installation or environment setup is
required. Do not move the EXE out of its extracted folder because the
`_internal`, `weights`, and `user_input` folders are required.

To analyze your own data, replace the images in `user_input/images` and update
`user_input/standard_concentrations.csv`. See `README.md` or `README_zh.md` for
the complete instructions.
