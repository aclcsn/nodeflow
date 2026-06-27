@echo off
REM NodeFlow - launcher for Windows.
REM Double-click this file, or run "win-start.bat" in a terminal.
REM Pass a workflow file to open it directly: win-start.bat my_board.json

cd /d "%~dp0"

if not exist ".venv\" (
    echo NodeFlow is not installed yet. Run win-install.bat first.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
nodeflow %*
