@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   TLC-RAPID — build Windows executable
echo ========================================
echo.

python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

echo Building (first run may take several minutes)...
pyinstaller --noconfirm TLC-RAPID.spec
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Preparing release\TLC-RAPID ...
if exist "release\TLC-RAPID" rmdir /s /q "release\TLC-RAPID"
mkdir "release\TLC-RAPID"

xcopy /e /i /y "dist\TLC-RAPID\*" "release\TLC-RAPID\" >nul
xcopy /e /i /y "user_input" "release\TLC-RAPID\user_input\" >nul
xcopy /e /i /y "weights" "release\TLC-RAPID\weights\" >nul
if not exist "release\TLC-RAPID\runs\predict-seg" mkdir "release\TLC-RAPID\runs\predict-seg"
copy /y "README.md" "release\TLC-RAPID\README.md" >nul
copy /y "README_zh.md" "release\TLC-RAPID\README_zh.md" >nul

echo.
echo ========================================
echo   Done: release\TLC-RAPID
echo ========================================
explorer "release\TLC-RAPID"
pause
