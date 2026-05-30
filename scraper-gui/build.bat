@echo off
setlocal
cd /d "%~dp0"
echo ========================================
echo  Lead Scraper - Build Standalone .exe
echo ========================================
echo.
echo This will take 2-5 minutes the first time.
echo.

echo [1/3] Installing build dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
python -m pip install --quiet pyinstaller
if errorlevel 1 (
    echo.
    echo ERROR: pip install failed. Make sure Python is installed and on PATH.
    pause
    exit /b 1
)

echo.
echo [2/3] Compiling LeadScraper.exe (this is the slow part)...
python -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name LeadScraper ^
    --hidden-import openpyxl.cell._writer ^
    --collect-all webview ^
    --collect-all flask ^
    desktop_app.py
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller failed. See messages above.
    pause
    exit /b 1
)

echo.
echo [3/3] Cleaning up build artifacts...
if exist build rmdir /s /q build
if exist LeadScraper.spec del LeadScraper.spec

echo.
echo ========================================
echo  DONE
echo ========================================
echo.
echo Your app is at:  dist\LeadScraper.exe
echo.
echo You can copy that .exe anywhere (other folders, other Windows
echo machines, USB drive, etc.) and double-click to run it.
echo No Python needed on the destination machine.
echo.
pause
