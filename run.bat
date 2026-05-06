@echo off
title Nova Star Citizen Data Extractor
echo ==========================================
echo  Nova Star Citizen Data Extractor
echo ==========================================
echo.

REM Check for Python
py --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Install requirements if needed
echo [SETUP] Checking dependencies...
py -m pip install -r "%~dp0requirements.txt" --quiet 2>nul
if %errorlevel% neq 0 (
    echo [SETUP] Installing dependencies...
    py -m pip install -r "%~dp0requirements.txt"
)

echo.

REM Run the extractor
cd /d "%~dp0"
py -m nova

echo.
echo ==========================================
echo  Extraction complete! Check the output folder.
echo ==========================================
pause
