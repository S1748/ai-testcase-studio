@echo off
setlocal

cd /d "%~dp0"

if not exist backend\venv (
    echo Backend virtual environment not found.
    echo Please run setup.bat first.
    pause
    exit /b 1
)

if not exist web\node_modules (
    echo Frontend dependencies not found.
    echo Please run setup.bat first.
    pause
    exit /b 1
)

echo [AITC] Starting backend on http://localhost:8000 ...
start "AITC Backend" /D "%~dp0backend" cmd /k "call venv\Scripts\activate && uvicorn app.main:app --reload --port 8000"

echo [AITC] Starting frontend on http://localhost:5173 ...
start "AITC Frontend" /D "%~dp0web" cmd /k "npm run dev"

echo.
echo Backend:  http://localhost:8000
echo Frontend: http://localhost:5173
echo Swagger:  http://localhost:8000/docs
echo.
pause
