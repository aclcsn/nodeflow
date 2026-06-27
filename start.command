#!/usr/bin/env bash
#
# NodeFlow — launcher.
#
# Double-click this file in Finder, or run "./start.command" in a terminal.
# Pass a workflow file to open it directly: ./start.command my_board.json
#
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "NodeFlow is not installed yet. Run install.command first."
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
exec nodeflow "$@"
