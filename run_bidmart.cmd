@echo off
setlocal
cd /d "%~dp0"

set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo Creating the project Python environment...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv .venv
    ) else (
        where python >nul 2>nul
        if errorlevel 1 goto python_missing
        python -m venv .venv
    )
    if errorlevel 1 goto setup_failed
)

if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" --version >nul 2>nul
    if errorlevel 1 (
        echo Repairing the existing project Python environment...
        where py >nul 2>nul
        if not errorlevel 1 (
            py -3 -m venv --upgrade .venv
        ) else (
            where python >nul 2>nul
            if errorlevel 1 goto python_missing
            python -m venv --upgrade .venv
        )
        if errorlevel 1 goto setup_failed
    )
)

"%VENV_PYTHON%" -c "import flask, dotenv" >nul 2>nul
if errorlevel 1 (
    echo Installing project dependencies...
    "%VENV_PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 goto setup_failed
)

powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>nul
if not errorlevel 1 (
    echo BidMart is already running at http://127.0.0.1:5000
    start "" "http://127.0.0.1:5000"
    exit /b 0
)

echo Starting BidMart...
start "BidMart Server" /D "%CD%" "%VENV_PYTHON%" app.py

for /L %%I in (1,1,20) do (
    powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>nul
    if not errorlevel 1 goto server_ready
    timeout /t 1 /nobreak >nul
)

echo BidMart did not start. Check the BidMart Server window for errors.
pause
exit /b 1

:server_ready
echo BidMart is running at http://127.0.0.1:5000
start "" "http://127.0.0.1:5000"
echo Keep the BidMart Server window open while using the site.
exit /b 0

:python_missing
echo Python 3 is not installed or not available on PATH.
echo Install Python 3, then run this file again.
pause
exit /b 1

:setup_failed
echo Could not prepare the Python environment or install dependencies.
pause
exit /b 1
