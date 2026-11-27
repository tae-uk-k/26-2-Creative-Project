@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 goto :error
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :error
)

echo.
echo Hanoon MVP: http://127.0.0.1:5000
echo Press Ctrl+C to stop the server.
echo.
".venv\Scripts\python.exe" app.py
goto :eof

:error
echo.
echo Setup failed. Check that Python 3 is installed and try again.
pause
exit /b 1
