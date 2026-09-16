@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please create .venv and install requirements-web.txt first.
    pause
    exit /b 1
)
echo LMU Data Analysis: http://127.0.0.1:8765
echo Keep this window open while using the app. Press Ctrl+C to stop.
".venv\Scripts\python.exe" scripts\serve_web.py
if errorlevel 1 pause
