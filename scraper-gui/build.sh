#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
echo "========================================"
echo "  Lead Scraper - Build Standalone App"
echo "========================================"
echo

echo "[1/3] Installing build dependencies..."
python3 -m pip install --quiet --upgrade pip
python3 -m pip install --quiet -r requirements.txt pyinstaller || \
    python3 -m pip install --quiet --break-system-packages -r requirements.txt pyinstaller

echo
echo "[2/3] Compiling LeadScraper (this is the slow part)..."
python3 -m PyInstaller \
    --noconfirm \
    --onefile \
    --windowed \
    --name LeadScraper \
    --hidden-import openpyxl.cell._writer \
    --collect-all webview \
    --collect-all flask \
    desktop_app.py

echo
echo "[3/3] Cleaning up build artifacts..."
rm -rf build LeadScraper.spec

echo
echo "========================================"
echo "  DONE"
echo "========================================"
echo
echo "Your app is at:  dist/LeadScraper  (Mac) or dist/LeadScraper.app"
echo
echo "Copy it anywhere and run by double-clicking."
