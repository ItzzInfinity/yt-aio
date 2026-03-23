from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable


LogFn = Callable[[str], None]


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
