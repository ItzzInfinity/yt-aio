"""Background job runners.

Owns:   the QThread wrappers every panel uses for work that must not block the UI.
Reads:  nothing directly.
Writes: nothing directly.
Runs:   whatever the utils layer runs, on a worker thread (dev_guide.md 5, Pattern C).

A worker never touches a widget. It emits; the panel renders. Panels share these
runners rather than importing each other's worker modules.
"""

from __future__ import annotations

from typing import Any, Callable

from .ui.qt import QThread, Signal
from .utils.download_manager import download_many
from .utils.shared import CancellationToken, DownloadTarget
from .utils.video_info_extractor import list_videos


class TaskThread(QThread):
    """Listing and downloading. One job per instance."""

    log_message = Signal(str)
    load_complete = Signal(object, str, str, str)  # items, source_name, source_kind, source_value
    work_complete = Signal(str)
    work_failed = Signal(str)

    def __init__(
        self,
        action: str,
        config: dict,
        db_path: str,
        token: CancellationToken,
        *,
        source_kind: str | None = None,
        source_value: str | None = None,
        media_type: str | None = None,
        targets: list[DownloadTarget] | None = None,
        source_name: str = "",
    ) -> None:
        super().__init__()
        self.action = action
        self.config = config
        self.db_path = db_path
        self.token = token
        self.source_kind = source_kind
        self.source_value = source_value
        self.media_type = media_type
        self.targets = targets or []
        self.source_name = source_name

    def _emit(self, message: str) -> None:
        self.log_message.emit(message)

    def run(self) -> None:
        try:
            if self.action == "load":
                if self.source_kind is None or self.source_value is None:
                    raise ValueError("A load task needs both source_kind and source_value.")
                items, source_name = list_videos(
                    self.source_kind,
                    self.source_value,
                    self.config,
                    self.db_path,
                    self._emit,
                    self.token,
                )
                # The kind and value travel with the result so the panel files it under
                # the source it actually ran against, not under whatever the widgets
                # happen to hold once the job finishes.
                self.load_complete.emit(items, source_name, self.source_kind, self.source_value)
                self.work_complete.emit(f"Loaded {len(items)} items.")
                return

            if self.action == "download":
                if self.media_type is None:
                    raise ValueError("A download task needs a media_type.")
                summary = download_many(
                    self.targets,
                    self.media_type,
                    self.config,
                    self.db_path,
                    self._emit,
                    self.token,
                    self.source_name,
                )
                self.work_complete.emit(summary)
                return

            raise RuntimeError(f"Unknown task action: {self.action}")
        except Exception as exc:
            if str(exc) == "Cancelled by user":
                self.work_complete.emit("Task cancelled.")
                return
            self.work_failed.emit(str(exc))


class CallableThread(QThread):
    """Runs one plain function off the GUI thread.

    The function is called as fn(log, token), where log takes a single already
    formatted string and token is a CancellationToken it should check in long loops.
    """

    log_message = Signal(str)
    result_ready = Signal(object)
    work_complete = Signal(str)
    work_failed = Signal(str)

    def __init__(
        self,
        fn: Callable[[Callable[[str], None], CancellationToken], Any],
        token: CancellationToken,
        *,
        done_message: str = "Finished.",
    ) -> None:
        super().__init__()
        self._fn = fn
        self._token = token
        self._done_message = done_message

    def _emit(self, message: str) -> None:
        self.log_message.emit(message)

    def run(self) -> None:
        try:
            result = self._fn(self._emit, self._token)
            self.result_ready.emit(result)
            self.work_complete.emit(self._done_message)
        except Exception as exc:
            if str(exc) == "Cancelled by user":
                self.work_complete.emit("Task cancelled.")
                return
            self.work_failed.emit(str(exc))
