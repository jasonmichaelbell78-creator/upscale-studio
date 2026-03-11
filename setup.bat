@echo off
cd /d "%~dp0"
echo ================================================
echo   Upscale Studio - First-Time Setup
echo ================================================
echo.

REM Create virtual environment
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to create virtual environment.
        echo Make sure Python is installed and in your PATH.
        pause
        exit /b 1
    )
)

REM Activate venv
call venv\Scripts\activate.bat

REM Install Python dependencies
echo Installing Python dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install Python packages.
    pause
    exit /b 1
)

REM Download binaries (FFmpeg + Real-ESRGAN)
echo.
python setup_env.py
if errorlevel 1 (
    echo.
    echo WARNING: Setup encountered issues. Check messages above.
    pause
    exit /b 1
)

echo.
echo ================================================
echo   Setup complete!
echo   Double-click  start.bat  to launch.
echo ================================================
pause
