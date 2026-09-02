"""Shared application state.

Owns:   the resolved configuration and the database path for the whole process.
Reads:  application/config/config.json
Writes: settings_changes rows in yt_aio.db when the file changes on disk.
Runs:   nothing.

Built once by the shell and passed to every panel. This is a shared helper, not the
shell: a panel holding it still cannot reach the tab bar or its sibling panels.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .db.database_manager import init_db, log_setting_change
from .ui.qt import QObject, Signal
from .utils.config_manager import (
    CONFIG_PATH,
    PROJECT_DB_PATH,
    ensure_config,
    load_config,
    resolve_runtime_config,
)
from .utils.shared import now_string

LogFn = Callable[[str, str], None]

# Values that can carry a token or a credential. They are never written into the
# settings_changes table or the console (dev_guide.md 13).
SENSITIVE_KEYS = {"youtube_visitor_data", "proxy"}


def _redact(key: str, value: Any) -> str:
    if key in SENSITIVE_KEYS and value not in (None, ""):
        return '"<redacted>"'
    return json.dumps(value)


class AppContext(QObject):
    """One instance per process."""

    config_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.config_path: Path = ensure_config(CONFIG_PATH)
        self.raw_config: dict[str, Any] = load_config(self.config_path)
        self.config: dict[str, Any] = resolve_runtime_config(self.raw_config)
        self.db_path: str = self._resolved_db_path()

    def _resolved_db_path(self) -> str:
        return self.config.get("log_file_path") or str(PROJECT_DB_PATH)

    def reload_if_changed(self, log: LogFn | None = None) -> None:
        """Re-read config.json, record every changed key, re-init the database if it moved.

        Panels call this before starting work so a hand-edited config takes effect
        without a restart. Emits config_changed only when something actually changed.
        """

        def emit(tag: str, message: str) -> None:
            if log is not None:
                log(tag, message)

        previous = self.raw_config
        try:
            latest = load_config(self.config_path)
        except Exception as exc:
            emit("ERR", f"Failed to reload config: {exc}")
            return

        if json.dumps(previous, sort_keys=True) == json.dumps(latest, sort_keys=True):
            self.raw_config = latest
            self.config = resolve_runtime_config(latest)
            return

        for key in sorted(set(previous) | set(latest)):
            old_value = previous.get(key)
            new_value = latest.get(key)
            if old_value == new_value:
                continue
            recorded_old = _redact(key, old_value)
            recorded_new = _redact(key, new_value)
            try:
                log_setting_change(self.db_path, key, recorded_old, recorded_new, now_string())
            except Exception as exc:
                emit("WARN", f"Could not record the config change for {key}: {exc}")
            emit("INFO", f"Config changed: {key} = {recorded_new}")

        self.raw_config = latest
        self.config = resolve_runtime_config(latest)

        new_db_path = self._resolved_db_path()
        if new_db_path != self.db_path:
            self.db_path = new_db_path
            init_db(self.db_path)
            emit("INFO", f"Database path changed to {self.db_path}")

        self.config_changed.emit()
