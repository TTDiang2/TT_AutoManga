@echo off
REM AutoManga Pake Packaging Script
REM This script packages the frontend as a lightweight WebView app using Pake

echo ========================================
echo AutoManga - Pake Packaging Script
echo ========================================
echo.

REM Check if pake is installed
where pake >nul 2>nul
if %errorlevel% neq 0 (
    echo Pake is not installed. Installing...
    npm install -g pake-cli
    if %errorlevel% neq 0 (
        echo Failed to install Pake. Please install manually: npm install -g pake-cli
        exit /b 1
    )
)

REM Set the app name
set APP_NAME=AutoManga

REM Set the URL (assuming the frontend is served at localhost:8080)
set APP_URL=http://localhost:5180

echo Packaging %APP_NAME% as WebView app...
echo.

REM Run pake with the configuration
pake %APP_URL% --name %APP_NAME% --width 1280 --height 800 --transparent

if %errorlevel% neq 0 (
    echo.
    echo Packaging failed. Please check the error messages above.
    exit /b 1
)

echo.
echo ========================================
echo Packaging completed successfully!
echo ========================================
echo.
echo The executable should be in the current directory.
echo Run: .\AutoManga.exe
echo.

pause
