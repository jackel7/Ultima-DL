@echo off
title Ultima-DL Server
color 0C
echo.
echo  ========================================
echo     ⚡ Ultima-DL — Starting Server...
echo  ========================================
echo.

cd /d "%~dp0"

:: Auto-install dependencies (skips if already installed)
echo  [1/2] Checking dependencies...
py -3 -m pip install flask flask-cors yt-dlp --quiet --disable-pip-version-check 2>nul
if errorlevel 1 (
    python -m pip install flask flask-cors yt-dlp --quiet --disable-pip-version-check 2>nul
)
echo  [2/2] Starting server...
echo.

:: Wait 2 seconds then open browser automatically
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:5000"

:: Try py launcher first (handles multiple Python versions), fallback to python
py -3 app.py 2>nul
if errorlevel 1 (
    python app.py
)

:: If server stops, pause so you can see errors
echo.
echo  Server stopped. Press any key to close...
pause >nul
