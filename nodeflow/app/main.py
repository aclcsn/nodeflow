"""NodeFlow application entry point.

Kept import-light: importing this module must NOT import Qt. The GUI is imported
lazily inside :func:`main` so that ``import nodeflow.app`` works in headless
environments (CI, tests) where PySide6 may be unavailable.
"""

from __future__ import annotations

import argparse
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nodeflow",
        description="NodeFlow — a visual workflow system for Jupyter notebooks.",
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")
    parser.add_argument(
        "workflow",
        nargs="?",
        default=None,
        help="optional path to a workflow.json to open on launch",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Console-script entry point. Returns a process exit code."""
    args = _build_parser().parse_args(argv)

    from nodeflow import __version__

    if args.version:
        print(f"NodeFlow {__version__}")
        return 0

    try:
        from nodeflow.gui.app import run_gui
    except ImportError as exc:  # GUI deps missing
        print(
            "NodeFlow GUI dependencies are not installed "
            f"(PySide6 / NodeGraphQt). Original error: {exc}",
            file=sys.stderr,
        )
        return 1

    return run_gui(workflow_path=args.workflow)


if __name__ == "__main__":
    raise SystemExit(main())
