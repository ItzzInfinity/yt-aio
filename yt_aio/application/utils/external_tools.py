"""Finding ffmpeg and ffprobe.

Owns:   locating the two external binaries the application cannot do without.
Reads:  PATH, a configured location, and the well-known install directories.
Writes: nothing.
Runs:   nothing. It only looks for files.

yt-dlp needs ffmpeg to merge a video stream with an audio one and to convert audio, and
the Local Scan tab needs ffprobe for containers mutagen will not open. Neither ships with
Python, and on Windows neither is installed by anything else: the usual outcome is a
folder of extracted binaries that was never added to PATH.

So four places are tried, in order:

1.  `ffmpeg_location` from the config, which may name the directory or the executable.
2.  PATH. On Windows `shutil.which` applies PATHEXT, so "ffmpeg" finds "ffmpeg.exe".
3.  A `bin` directory beside the project, so dropping the executables next to the code is
    enough and no environment variable has to be edited.
4.  The directories winget, Chocolatey, Scoop and the common manual extractions use.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

IS_WINDOWS = sys.platform == "win32"

# Beside the installed package: yt_aio/bin/ffmpeg.exe and friends.
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
BUNDLED_BIN = PACKAGE_ROOT / "bin"

TOOL_NAMES = ("ffmpeg", "ffprobe")


def _executable_names(tool: str) -> tuple[str, ...]:
    return (f"{tool}.exe", tool) if IS_WINDOWS else (tool,)


def _in_directory(directory: Path, tool: str) -> Path | None:
    for name in _executable_names(tool):
        candidate = directory / name
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def _windows_candidates() -> list[Path]:
    """Where the Windows package managers and the usual manual unzip put it."""
    directories: list[Path] = []
    for variable, relative in (
        ("LOCALAPPDATA", "Microsoft/WinGet/Links"),
        ("ProgramData", "chocolatey/bin"),
        ("USERPROFILE", "scoop/shims"),
        ("ProgramFiles", "ffmpeg/bin"),
        ("ProgramFiles(x86)", "ffmpeg/bin"),
    ):
        base = os.environ.get(variable)
        if base:
            directories.append(Path(base).joinpath(*relative.split("/")))
    directories.append(Path("C:/ffmpeg/bin"))
    return directories


def _unix_candidates() -> list[Path]:
    """Homebrew on both architectures, and the standard prefixes."""
    return [
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
        Path("/usr/bin"),
        Path("/snap/bin"),
    ]


def find_tool(tool: str, config: dict[str, Any] | None = None) -> str | None:
    """The full path to ffmpeg or ffprobe, or None when it is genuinely not installed."""
    configured = str((config or {}).get("ffmpeg_location") or "").strip()
    if configured:
        location = Path(configured).expanduser()
        # The setting may name the directory or one of the executables in it.
        if location.is_file():
            found = location if location.stem.lower().startswith(tool) else _in_directory(location.parent, tool)
            if found is not None:
                return str(found)
        elif location.is_dir():
            found = _in_directory(location, tool)
            if found is not None:
                return str(found)

    on_path = shutil.which(tool)
    if on_path:
        return on_path

    found = _in_directory(BUNDLED_BIN, tool)
    if found is not None:
        return str(found)

    for directory in (_windows_candidates() if IS_WINDOWS else _unix_candidates()):
        found = _in_directory(directory, tool)
        if found is not None:
            return str(found)

    return None


def ffmpeg_location(config: dict[str, Any] | None = None) -> str | None:
    """The directory holding ffmpeg, which is the form yt-dlp's option wants."""
    found = find_tool("ffmpeg", config)
    return str(Path(found).parent) if found else None


def missing_tools(config: dict[str, Any] | None = None) -> list[str]:
    """Which of ffmpeg and ffprobe could not be found anywhere."""
    return [tool for tool in TOOL_NAMES if find_tool(tool, config) is None]


def install_hint() -> str:
    """What to tell someone whose machine has no ffmpeg, for their platform."""
    if IS_WINDOWS:
        return (
            "Install it with `winget install Gyan.FFmpeg`, or download a build from "
            "https://www.gyan.dev/ffmpeg/builds/ and either add its bin folder to PATH, "
            "put ffmpeg.exe and ffprobe.exe in the yt_aio/bin folder, or set "
            "ffmpeg_location in the Settings tab."
        )
    if sys.platform == "darwin":
        return "Install it with `brew install ffmpeg`."
    return "Install it with your package manager, for example `sudo apt install ffmpeg`."
