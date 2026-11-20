@echo off
cd /d "%~dp0"
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Python is not installed. Please install Python 3.10 or newer from python.org.
    pause
    exit /b 1
)
python -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo Could not install Python dependencies.
    pause
    exit /b 1
)
python app.py --open
pause
