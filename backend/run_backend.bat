@echo off
REM GeoIntel Backend Startup Script for Windows

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║        GeoIntel Backend API Server                  ║
echo ║     Real-Time Geopolitical Intelligence             ║
echo ╚══════════════════════════════════════════════════════╝
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

REM Check if virtual environment exists, create if not
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install/update dependencies
echo.
echo Installing dependencies (this may take a minute)...
pip install -q -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies
    echo Try running manually: pip install -r requirements.txt
    pause
    exit /b 1
)

REM Check if database exists, initialize if not
if not exist "geointel.db" (
    echo.
    echo Initializing database...
    python models.py
    if %errorlevel% neq 0 (
        echo ERROR: Failed to initialize database
        pause
        exit /b 1
    )
)

REM Start the Flask server
echo.
echo ════════════════════════════════════════════════════════
echo Backend starting on http://localhost:5000
echo.
echo Press Ctrl+C to stop the server
echo ════════════════════════════════════════════════════════
echo.

python app.py

REM Show error if app crashes
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Backend crashed
    echo Check the error messages above
    pause
)
