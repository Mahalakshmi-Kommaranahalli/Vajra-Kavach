@echo off
rem ==============================================================================
rem Vajra-Kavach: Install Offline Dependencies (Windows Air-Gapped Phase)
rem Run strictly WITHOUT internet access on the target disconnected machine.
rem ==============================================================================
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "WHEELHOUSE_DIR=%PROJECT_ROOT%\wheelhouse"
if exist "%PROJECT_ROOT%\requirements-offline.txt" (
    set "REQUIREMENTS_FILE=%PROJECT_ROOT%\requirements-offline.txt"
) else (
    set "REQUIREMENTS_FILE=%PROJECT_ROOT%\requirements.txt"
)

echo ======================================================================
echo [Vajra-Kavach] Installing From Local Wheelhouse (100% Offline Windows)
echo ======================================================================

if not exist "%WHEELHOUSE_DIR%" (
    echo [ERROR] Wheelhouse directory not found at %WHEELHOUSE_DIR%!
    echo Please run scripts\build_offline_bundle.bat on an online machine first.
    exit /b 1
)

echo [1/2] Installing pinned dependencies from local wheelhouse...
python -m pip install --no-index --find-links="%WHEELHOUSE_DIR%" -r "%REQUIREMENTS_FILE%"
if %errorlevel% neq 0 (
    echo [ERROR] Offline installation failed. Ensure wheelhouse contains matching wheels.
    exit /b %errorlevel%
)

echo [2/2] Verifying offline module integrity...
python -c "import os; os.environ['OFFLINE_MODE']='true'; from vajra.airgap import enforce_airgap; enforce_airgap(); import cryptography; print('Verified: cryptography ' + cryptography.__version__ + ' operational in OFFLINE_MODE.')"
if %errorlevel% neq 0 (
    echo [ERROR] Integrity verification failed.
    exit /b %errorlevel%
)

echo.
echo [SUCCESS] Vajra-Kavach offline installation complete!
echo Execute pipeline with:
echo set OFFLINE_MODE=true
echo set RAKSHA_SECRET=practice
echo python main.py --input dev\input --output my_output
exit /b 0
