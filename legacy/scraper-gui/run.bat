@echo off
cd /d "%~dp0"
echo ============================================
echo    Lead Scraper
echo ============================================
echo.
echo Installing dependencies (first run only, ~30 seconds)...
python -m pip install --quiet -r requirements.txt
echo.
echo Starting the app - your browser will open in a few seconds.
echo.
echo  *  Keep THIS black window open while you use the app.
echo  *  To STOP the app, just close this window.
echo.
rem Open the browser a few seconds after the server starts (gives Flask time to boot)
start "" /b powershell -WindowStyle Hidden -Command "Start-Sleep 4; Start-Process 'http://localhost:5000'"
python app.py
pause
