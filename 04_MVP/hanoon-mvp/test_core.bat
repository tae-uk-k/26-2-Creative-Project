@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Python virtual environment...
    python -m venv .venv || goto :error
)

echo [2/3] Installing test dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q || goto :error

echo [3/3] Running Hanoon core technology tests...
".venv\Scripts\python.exe" -m pytest tests\test_visibility_engine.py -v
if errorlevel 1 goto :error

echo.
echo All core technology tests passed.
pause
exit /b 0

:error
echo.
echo Core technology tests failed.
pause
exit /b 1
