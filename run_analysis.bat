@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting TLC-RAPID...
python run_analysis.py
if errorlevel 1 (
    echo.
    echo Run failed. Install dependencies: pip install -r requirements.txt
    pause
)
