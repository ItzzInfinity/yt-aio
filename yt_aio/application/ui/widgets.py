"""Shared widgets.

Owns:   nothing on screen by itself; panels embed these.
Reads:  nothing.
Writes: nothing.
Runs:   nothing.

Anything more than one panel needs on screen belongs here, so a second tab never
starts by copying a first tab's widget code (dev_guide.md 7.6).
"""

from __future__ import annotations

from .qt import NO_WRAP, ELIDE_RIGHT, QLabel, QPlainTextEdit, QTableWidget, QWidget
from ..utils.shared import now_string


class ConsoleView(QPlainTextEdit):
    """The read-only log surface. One prefix vocabulary across the application.

    TX  a command this application sent out
    RX  a line received back
    INFO  normal progress
    WARN  something was skipped or degraded; the run continues
    ERR   the operation failed
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(NO_WRAP)

    def log(self, tag: str, text: str) -> None:
        """Single place where anything a panel says reaches the console."""
        if text:
            self.append_raw(f"[{now_string()}] [{tag}] {text.rstrip()}")

    def append_raw(self, message: str) -> None:
        """For lines that already carry their own timestamp and tag, such as a worker's."""
        self.appendPlainText(message)
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


class RecordTable(QTableWidget):
    """A read-mostly grid. Rows carry their database id, so sorting cannot desync it."""

    def __init__(self, headers: list[str], parent: QWidget | None = None) -> None:
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(headers)
        self.setAlternatingRowColors(True)
        self.horizontalHeader().setTextElideMode(ELIDE_RIGHT)
        self.verticalHeader().setVisible(False)


def muted(text: str) -> QLabel:
    """A secondary caption. Used for counts, hints and empty states."""
    label = QLabel(text)
    label.setProperty("role", "muted")
    return label
