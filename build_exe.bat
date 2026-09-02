@echo off
chcp 65001 >nul
cd /d "%~dp0"

where git >nul 2>nul
if errorlevel 1 (
    echo Git is required to create a traceable release.
    exit /b 1
)

set "RELEASE_DIRTY="
for /f "delims=" %%S in ('git status --porcelain') do set "RELEASE_DIRTY=1"
if defined RELEASE_DIRTY (
    echo Release build refused: commit all source changes first.
    echo This prevents an EXE from being published without matching source code.
    exit /b 1
)

set "RELEASE_TAG="
for /f "delims=" %%V in ('git describe --tags --exact-match 2^>nul') do set "RELEASE_TAG=%%V"
if not defined RELEASE_TAG (
    echo Release build refused: HEAD must have an exact version tag, for example v1.0.0.
    exit /b 1
)
for /f "delims=" %%C in ('git rev-parse HEAD') do set "RELEASE_COMMIT=%%C"

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
if exist "release\TLC-RAPID\user_input\images" rmdir /s /q "release\TLC-RAPID\user_input\images"
mkdir "release\TLC-RAPID\user_input\images"
copy /y "user_input\images\PLACE_IMAGES_HERE.txt" "release\TLC-RAPID\user_input\images\PLACE_IMAGES_HERE.txt" >nul
xcopy /e /i /y "weights" "release\TLC-RAPID\weights\" >nul
if not exist "release\TLC-RAPID\runs\predict-seg" mkdir "release\TLC-RAPID\runs\predict-seg"
copy /y "README.md" "release\TLC-RAPID\README.md" >nul
copy /y "README_zh.md" "release\TLC-RAPID\README_zh.md" >nul
copy /y "LICENSE" "release\TLC-RAPID\LICENSE" >nul
copy /y "THIRD_PARTY_NOTICES.txt" "release\TLC-RAPID\THIRD_PARTY_NOTICES.txt" >nul
python -m pip freeze > "release\TLC-RAPID\PACKAGE_VERSIONS.txt"

(
    echo TLC-RAPID %RELEASE_TAG%
    echo.
    echo This executable was built from commit:
    echo %RELEASE_COMMIT%
    echo.
    echo Corresponding source code:
    echo https://github.com/zongxuli709-code/TLC-RAPID/releases/tag/%RELEASE_TAG%
    echo.
    echo Repository:
    echo https://github.com/zongxuli709-code/TLC-RAPID
) > "release\TLC-RAPID\SOURCE_CODE.txt"

echo.
echo ========================================
echo   Done: release\TLC-RAPID
echo ========================================
explorer "release\TLC-RAPID"
pause
