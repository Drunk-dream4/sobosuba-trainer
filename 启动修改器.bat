@echo off
setlocal
cd /d "%~dp0"

where pythonw >nul 2>nul
if not errorlevel 1 (
    start "" pythonw "%~dp0trainer_gui.py"
    exit /b 0
)

where pyw >nul 2>nul
if not errorlevel 1 (
    start "" pyw -3 "%~dp0trainer_gui.py"
    exit /b 0
)

echo Python 3 not found. Please install Python 3 and try again.
pause
