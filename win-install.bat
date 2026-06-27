@echo off
REM NodeFlow - one-time installer / updater for Windows.
REM Double-click this file, or run "win-install.bat" in a terminal. It creates a
REM virtual environment, installs NodeFlow and its dependencies, and registers the
REM notebook kernel. Running it again after updating the code is safe.

cd /d "%~dp0"

echo ==^> Installing NodeFlow into .\.venv

REM Pick a Python launcher (prefer the "py" launcher, fall back to "python").
set "PY=py -3"
where py >nul 2>nul || set "PY=python"

REM Create the virtual environment if it does not exist yet.
if not exist ".venv\" (
    echo ==^> Creating virtual environment (.venv)
    %PY% -m venv .venv
)

call ".venv\Scripts\activate.bat"

echo ==^> Upgrading pip
python -m pip install --upgrade pip

echo ==^> Installing NodeFlow and its dependencies (this can take a few minutes)
pip install -e ".[gui,dev]"

echo ==^> Registering the 'nodeflow' notebook kernel
python -m ipykernel install --sys-prefix --name nodeflow --display-name "NodeFlow (venv)"

echo.
echo Installation complete.
echo Launch NodeFlow with win-start.bat (double-click it, or run win-start.bat).
pause
