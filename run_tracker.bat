@echo off
title Claude Token Tracker
cd /d "%~dp0"

set PYTHON=py -3.12
echo Using Python 3.12
%PYTHON% -c "import webview; print('pywebview OK')"
if errorlevel 1 (
    echo.
    echo Installing dependencies...
    %PYTHON% -m pip install -r requirements.txt
)
echo.
echo Launching Claude Token Tracker...
%PYTHON% app.py
pause
