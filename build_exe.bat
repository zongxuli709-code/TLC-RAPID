@echo off
chcp 65001 >nul
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_release.ps1"
if errorlevel 1 (
    echo.
    echo Release build failed.
    exit /b 1
)

echo.
echo Release build completed. See the release folder.
