@echo off
title Claude Token Tracker
cd /d "%~dp0"

echo Using Python: C:\Python314\python.exe
"C:\Python314\python.exe" -c "import webview; print('pywebview OK')"
if errorlevel 1 (
    echo.
    echo Installing dependencies...
    "C:\Python314\python.exe" -m pip install -r requirements.txt
)
echo.
echo Launching Claude Token Tracker...
"C:\Python314\python.exe" app.py
pause
