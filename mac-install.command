#!/usr/bin/env bash
#
# NodeFlow — one-time installer / updater.
#
# Double-click this file in Finder, or run "./mac-install.command" in a terminal.
# It creates a virtual environment, installs NodeFlow and its dependencies, and
# registers the notebook kernel. Running it again after updating the code is
# safe and brings the install up to date.
#
set -e
cd "$(dirname "$0")"

echo "==> Installing NodeFlow into ./.venv"

# Pick a Python 3 interpreter.
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "Error: Python 3 was not found. Install Python 3.11 or newer and try again."
  exit 1
fi

# Create the virtual environment if it does not exist yet.
if [ ! -d ".venv" ]; then
  echo "==> Creating virtual environment (.venv)"
  "$PY" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Upgrading pip"
python -m pip install --upgrade pip

echo "==> Installing NodeFlow and its dependencies (this can take a few minutes)"
pip install -e ".[gui,dev]"

echo "==> Registering the 'nodeflow' notebook kernel"
python -m ipykernel install --sys-prefix --name nodeflow --display-name "NodeFlow (venv)"

echo ""
echo "Installation complete."
echo "Launch NodeFlow with mac-start.command (double-click it in Finder, or run ./mac-start.command)."
