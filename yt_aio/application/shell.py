"""Application shell.

Owns:   the one QMainWindow and the tab bar.
Reads:  application/ui/styles.qss
Writes: nothing.
Runs:   nothing. All work belongs to the panels.

The shell knows the panels. Panels never know the shell (dev_guide.md 1). Adding a tab
is an import, a constructor call and an addTab line; nothing else in the tree changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .. import APP_NAME, APP_VERSION
from .context import AppContext
from .db.database_manager import init_db
from .features.downloader.panel import DownloaderPanel
from .features.importer.panel import ImportPanel
from .features.library.panel import LibraryPanel
from .features.logs.panel import LogsPanel
from .features.settings.panel import SettingsPanel
from .ui.qt import TAB_NORTH, QApplication, QMainWindow, QTabWidget, exec_app

STYLESHEET_PATH = Path(__file__).resolve().parent / "ui" / "styles.qss"


class AppShell(QMainWindow):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION} — ItzzInfinity")
        self.resize(1320, 860)

        self._tabs = QTabWidget()
        self._tabs.setTabPosition(TAB_NORTH)
        self._tabs.setDocumentMode(True)

        # Tab order is workflow order: bring links in, fetch them, browse what was
        # kept, check what happened, adjust the settings.
        self._tabs.addTab(ImportPanel(context=context), "Import")
        self._tabs.addTab(DownloaderPanel(context=context), "Downloader")
        self._tabs.addTab(LibraryPanel(context=context), "Library")
        self._tabs.addTab(LogsPanel(context=context), "Logs")
        self._tabs.addTab(SettingsPanel(context=context), "Settings")
        self._tabs.setCurrentIndex(1)

        self.setCentralWidget(self._tabs)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Give every panel a chance to stop its background work before the window goes."""
        for index in range(self._tabs.count()):
            panel = self._tabs.widget(index)
            shutdown = getattr(panel, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception as exc:
                    print(f"Panel shutdown failed: {exc}", file=sys.stderr)
        super().closeEvent(event)


def main() -> int:
    try:
        app = QApplication(sys.argv)
    except Exception as exc:
        print(f"Failed to start Qt application: {exc}", file=sys.stderr)
        return 1

    app.setApplicationName(APP_NAME)

    if STYLESHEET_PATH.exists():
        app.setStyleSheet(STYLESHEET_PATH.read_text(encoding="utf-8"))

    try:
        context = AppContext()
        init_db(context.db_path)
    except Exception as exc:
        print(f"Failed to prepare the configuration or database: {exc}", file=sys.stderr)
        return 1

    window = AppShell(context)
    window.show()
    return exec_app(app)
