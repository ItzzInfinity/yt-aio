"""What has to be present before the application can start.

Owns:   the check that runs before anything else, and the message it prints.
Reads:  the installed distributions, PATH, and the Python version.
Writes: nothing, except to the console.
Runs:   nothing.

Imports nothing from `application`, and must keep it that way. The whole point is to say
"PyQt is not installed" without needing PyQt to say it, and the moment this file reaches
into the package it starts importing the very things it is checking for.

Without this, a clone with no dependencies installed greets the user with a traceback
ending in `ModuleNotFoundError: No module named 'PyQt5'`, which names the fallback rather
than the thing to install and says nothing about how.
"""

from __future__ import annotations

import shutil
import sys
from importlib.util import find_spec

MINIMUM_PYTHON = (3, 10)

# The Qt binding is special: either one works, so neither alone is a missing requirement.
QT_BINDINGS = ("PyQt6", "PyQt5")

# (import name, install name, what stops working without it)
REQUIRED = [
    ("yt_dlp", "yt-dlp", "fetching and downloading, which is the whole application"),
]
OPTIONAL = [
    ("mutagen", "mutagen", "reading tags in the Local Scan tab; ffprobe is used instead, more slowly"),
]

INSTALL_COMMAND = "python -m pip install -r requirements.txt"


def _python_problem() -> str | None:
    if sys.version_info >= MINIMUM_PYTHON:
        return None
    running = ".".join(str(part) for part in sys.version_info[:3])
    wanted = ".".join(str(part) for part in MINIMUM_PYTHON)
    return f"Python {wanted} or newer is required. This is Python {running}."


def _missing_qt() -> str | None:
    if any(find_spec(name) is not None for name in QT_BINDINGS):
        return None
    return (
        "No Qt binding is installed. PyQt6 is the one to get:\n"
        "    python -m pip install PyQt6\n"
        "  PyQt5 also works if PyQt6 will not build on this machine."
    )


def _missing_packages() -> list[str]:
    problems: list[str] = []
    for import_name, install_name, consequence in REQUIRED:
        if find_spec(import_name) is None:
            problems.append(
                f"{install_name} is not installed, which stops {consequence}.\n"
                f"    python -m pip install {install_name}"
            )
    return problems


def _missing_optional() -> list[str]:
    warnings: list[str] = []
    for import_name, install_name, consequence in OPTIONAL:
        if find_spec(import_name) is None:
            warnings.append(f"{install_name} is not installed, which limits {consequence}.")
    return warnings


def _missing_media_tools() -> list[str]:
    """ffmpeg and ffprobe. A warning, never a blocker: plenty of work needs neither.

    Uses the full search from `application.utils.external_tools` when that import is safe,
    and falls back to PATH alone when it is not, so a broken tree still gets an answer.
    """
    try:
        from .application.utils.external_tools import install_hint, missing_tools

        missing = missing_tools()
        hint = install_hint()
    except Exception:
        missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
        hint = "Install ffmpeg and make sure it is on PATH."

    if not missing:
        return []
    return [
        f"{' and '.join(missing)} could not be found. Merging video with audio and "
        f"converting audio both need it, so downloads will fail without it.\n    {hint}"
    ]


def problems() -> tuple[list[str], list[str]]:
    """(what stops the application, what merely limits it)."""
    blocking: list[str] = []
    warnings: list[str] = []

    version = _python_problem()
    if version:
        blocking.append(version)

    qt = _missing_qt()
    if qt:
        blocking.append(qt)

    blocking.extend(_missing_packages())
    warnings.extend(_missing_optional())
    warnings.extend(_missing_media_tools())
    return blocking, warnings


def run(stream=None) -> int:
    """Print what is wrong. Returns 0 when the application can start, 1 when it cannot."""
    out = stream if stream is not None else sys.stderr
    blocking, warnings = problems()

    for warning in warnings:
        print(f"Warning: {warning}", file=out)

    if not blocking:
        return 0

    print("\nYT AIO cannot start yet.\n", file=out)
    for problem in blocking:
        print(f"  - {problem}", file=out)
    print(f"\nInstalling everything at once:\n    {INSTALL_COMMAND}\n", file=out)
    return 1
