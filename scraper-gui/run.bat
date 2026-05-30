@echo off
echo Installing dependencies (first time only)...
python -m pip install --quiet -r requirements.txt
echo.
echo Starting Lead Scraper...
python app.py
pause
