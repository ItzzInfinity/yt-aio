from __future__ import annotations

import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable


LogFn = Callable[[str], None]

IS_WINDOWS = sys.platform == "win32"

# Windows gives every child process its own console window unless told not to. yt-dlp is
# launched once per download and once per metadata batch, so without this a black window
# blinks on screen for each one. The flag exists only on Windows; elsewhere it is zero and
# is not passed at all. Nothing is lost by hiding it: stdout and stderr are piped and the
# Downloader tab shows every line.
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def system_info() -> str:
    """A one-line description of the machine, for the errors table.

    `os.uname()` does not exist on Windows. The three call sites each guarded it with a
    hasattr check that fell back to `os.name`, which reports "nt" and tells nobody
    anything. `platform` is in the standard library and works everywhere.
    """
    import platform

    parts = [platform.system() or "unknown", platform.release(), platform.machine()]
    return " ".join(part for part in parts if part) + f" | Python {platform.python_version()}"


def process_kwargs(**extra: Any) -> dict[str, Any]:
    """The keyword arguments every subprocess in this application shares.

    `text=True` alone decodes with `locale.getpreferredencoding()`, which is UTF-8 on
    Linux and macOS and the ANSI code page on Windows, usually cp1252. yt-dlp writes
    UTF-8, so on Windows the first Bengali, Hindi or accented title raises
    UnicodeDecodeError in the middle of a listing and takes the whole run with it. The
    encoding is therefore always stated, and `errors="replace"` makes an unexpected byte
    a replacement character rather than an exception: a mangled character in one title is
    a far better outcome than losing the batch.

    On Windows it also carries CREATE_NO_WINDOW, so launching yt-dlp does not blink a
    console window on screen for every download and every metadata batch.
    """
    kwargs: dict[str, Any] = {"text": True, "encoding": "utf-8", "errors": "replace"}
    if IS_WINDOWS and CREATE_NO_WINDOW:
        kwargs["creationflags"] = CREATE_NO_WINDOW
    kwargs.update(extra)
    return kwargs


@dataclass
class VideoItem:
    video_id: str
    title: str
    url: str
    duration_seconds: int | None = None
    duration_label: str = "Unknown"
    available_bitrate: str = "Unknown"
    channel_name: str = ""
    source_name: str = ""
    upload_date: str = ""
    view_count: int | None = None
    video_info_id: int | None = None
    source_id: int | None = None


@dataclass
class DownloadTarget:
    url: str
    title: str | None = None
    video_id: str | None = None
    video_info_id: int | None = None
    source_id: int | None = None


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._processes: set[subprocess.Popen[str]] = set()
        self._lock = threading.Lock()

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            processes = list(self._processes)
        for process in processes:
            try:
                process.terminate()
            except OSError:
                continue

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def register(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._processes.add(process)

    def unregister(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._processes.discard(process)


def now_string() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_log(logger: LogFn | None, message: str) -> None:
    if logger:
        logger(message)
