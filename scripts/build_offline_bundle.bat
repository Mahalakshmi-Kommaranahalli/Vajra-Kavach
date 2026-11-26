@echo off
rem ==============================================================================
rem Vajra-Kavach: Build Offline Bundle & Wheelhouse (Windows Online Phase)
rem Run this on an internet-connected machine before air-gap deployment.
rem ==============================================================================
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "WHEELHOUSE_DIR=%PROJECT_ROOT%\wheelhouse"
set "REQUIREMENTS_FILE=%PROJECT_ROOT%\requirements.txt"

echo ======================================================================
echo [Vajra-Kavach] Building Offline Dependencies Wheelhouse (Windows)
echo ======================================================================

if not exist "%WHEELHOUSE_DIR%" mkdir "%WHEELHOUSE_DIR%"

echo [1/2] Downloading binary wheels into %WHEELHOUSE_DIR%...
python -m pip download -r "%REQUIREMENTS_FILE%" -d "%WHEELHOUSE_DIR%" --prefer-binary
if %errorlevel% neq 0 (
    echo [ERROR] Failed to download wheels. Check your internet connection.
    exit /b %errorlevel%
)

echo [2/2] Verifying downloaded files in wheelhouse...
dir /b "%WHEELHOUSE_DIR%\*.whl"

echo.
echo [SUCCESS] Offline bundle created successfully in %WHEELHOUSE_DIR%!
echo Transfer this repository and wheelhouse folder to your disconnected host.
exit /b 0
