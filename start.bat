@echo off
cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found.
    echo Please run setup.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo ================================================
echo   Upscale Studio
echo   http://localhost:8000
echo   Press Ctrl+C to stop the server
echo ================================================
echo.

set OPEN_BROWSER=1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
