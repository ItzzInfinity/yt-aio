"""Application shell.

Owns:   the one QMainWindow and the tab bar.
Reads:  nothing directly; the theme comes from ui/theme.py and the config.
Writes: nothing.
Runs:   nothing. All work belongs to the panels.

The shell knows the panels. Panels never know the shell (dev_guide.md 1). Adding a tab
is an import, a constructor call and an addTab line; nothing else in the tree changes.
"""

from __future__ import annotations

import sys

from .. import APP_NAME, APP_VERSION
from .context import AppContext
from .db.database_manager import init_db
from .features.downloader.panel import DownloaderPanel
from .features.importer.panel import ImportPanel
from .features.library.panel import LibraryPanel
from .features.local_scan.panel import LocalScanPanel
from .features.logs.panel import LogsPanel
from .features.settings.panel import SettingsPanel
from .ui.qt import TAB_NORTH, QApplication, QMainWindow, QTabWidget, exec_app
from .ui.theme import DEFAULT_THEME, apply_theme, resolve_theme_name


class AppShell(QMainWindow):
    def __init__(self, context: AppContext, *, theme: str = DEFAULT_THEME) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION} — ItzzInfinity")
        self.resize(1320, 860)

        self._tabs = QTabWidget()
        self._tabs.setTabPosition(TAB_NORTH)
        self._tabs.setDocumentMode(True)

        # Tab order is workflow order: bring links in, fetch them, browse what was
        # kept, see what is already on disk, check what happened, adjust the settings.
        self._tabs.addTab(ImportPanel(context=context), "Import")
        self._tabs.addTab(DownloaderPanel(context=context), "Downloader")
        self._tabs.addTab(LibraryPanel(context=context), "Library")
        self._tabs.addTab(LocalScanPanel(context=context), "Local Scan")
        self._tabs.addTab(LogsPanel(context=context), "Logs")
        self._tabs.addTab(SettingsPanel(context=context), "Settings")
        self._tabs.setCurrentIndex(1)

        self.setCentralWidget(self._tabs)

        # The theme is a window-wide concern, so the shell owns it rather than the tab
        # that happens to edit the setting. Saving in Settings repaints everything.
        self._context = context
        self._theme = resolve_theme_name(theme)
        context.config_changed.connect(self.refresh_theme)

    def refresh_theme(self) -> None:
        """Repaint if, and only if, ui_theme now names a different palette."""
        wanted = resolve_theme_name(self._context.config.get("ui_theme", DEFAULT_THEME))
        if wanted == self._theme:
            return
        app = QApplication.instance()
        if app is None:
            return
        try:
            self._theme = apply_theme(app, wanted)
        except Exception as exc:
            print(f"Could not apply the {wanted} theme: {exc}", file=sys.stderr)

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

    try:
        context = AppContext()
        init_db(context.db_path)
    except Exception as exc:
        print(f"Failed to prepare the configuration or database: {exc}", file=sys.stderr)
        return 1

    # Painted after the context is built, because the chosen theme lives in the config.
    # A broken palette must not stop the window from opening, so this never raises.
    started_theme = DEFAULT_THEME
    try:
        started_theme = apply_theme(app, context.config.get("ui_theme", DEFAULT_THEME))
    except Exception as exc:
        print(f"Could not apply the theme: {exc}", file=sys.stderr)

    window = AppShell(context, theme=started_theme)
    window.show()
    return exec_app(app)
