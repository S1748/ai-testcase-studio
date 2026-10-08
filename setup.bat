@echo off
setlocal

echo [AITC] Installing backend dependencies...
cd /d "%~dp0backend"

if not exist venv (
    python -m venv venv
    if errorlevel 1 (
        echo Failed to create Python virtual environment.
        pause
        exit /b 1
    )
)

call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install backend dependencies.
    pause
    exit /b 1
)

echo.
echo [AITC] Preparing .env ...
cd /d "%~dp0"
if not exist .env (
    copy .env.example .env >nul
    echo   .env created from .env.example ^(mock mode, no API key needed^)
)

echo.
echo [AITC] Installing frontend dependencies...
cd /d "%~dp0web"
call npm install
if errorlevel 1 (
    echo Failed to install frontend dependencies.
    pause
    exit /b 1
)

echo.
echo Setup completed.
echo Run start.bat to start the application.
pause
