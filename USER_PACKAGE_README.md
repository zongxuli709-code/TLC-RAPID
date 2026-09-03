# TLC-RAPID user package

The included example is ready to run. Results are written to
`runs/predict-seg`.

## Windows executable package

Double-click `TLC-RAPID.exe`. No separate Python installation is required.

## Cross-platform Python package (Windows and macOS)

Install Python 3.12, open a terminal in this folder, and create an isolated
environment:

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run_analysis.py
```

### macOS Terminal

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
bash run_analysis.sh
```

On Apple Silicon, installation availability depends on Python and PyTorch
wheels for the macOS version in use. This is a Python package, not a signed
native `.app`. The Windows `.exe` cannot run on macOS.

To analyze your own data, replace the images in `user_input/images` and update
`user_input/standard_concentrations.csv`. See `README.md` or `README_zh.md` for
the complete instructions.

