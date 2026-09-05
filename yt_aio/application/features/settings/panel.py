"""Settings panel.

Owns:   the Settings tab.
Reads:  application/config/config.json, through AppContext.
Writes: application/config/config.json, and settings_changes rows by way of
        AppContext.reload_if_changed.
Runs:   nothing (dev_guide.md 5, Pattern E).

Editors are built from the default config, so a key added to build_default_config
appears here with no change to this file. Types come from the default value, which is
also what decides how the edited value is written back.

A key listed in SETTING_SUGGESTIONS gets an editable drop-down of the values known to
work in that field. The list is a shortcut, not a validator: anything typed is still
accepted, because yt-dlp takes far more than can be enumerated here.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ...context import SENSITIVE_KEYS, AppContext
from ...ui.qt import (
    ALIGN_TOP,
    MB_NO,
    MB_YES,
    CASE_INSENSITIVE,
    MATCH_CONTAINS,
    QCheckBox,
    QComboBox,
    QCompleter,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTimer,
    QVBoxLayout,
    QWidget,
    pyqtSlot,
)
from ...ui.widgets import muted
from ...utils.browser_cookies import describe as describe_browser
from ...utils.config_manager import SETTING_RANGES, SETTING_SUGGESTIONS, build_default_config

DIRECTORY_KEYS = {"default_download_path", "logs_directory", "cookie_fallback_home", "info_cache_dir"}
FILE_KEYS = {"log_file_path", "history_file_path", "cookie_file", "download_archive_path"}

HELP = {
    "default_download_path": "Where finished media is written.",
    "log_file_path": "SQLite database. A relative path resolves from yt_aio/application.",
    "history_file_path": "Usually the same database as log_file_path.",
    "logs_directory": "Reserved for file-based logs. Relative paths resolve from yt_aio/application.",
    "max_concurrent_downloads": "How many downloads run at once.",
    "max_metadata_workers": "How many yt-dlp metadata processes run at once.",
    "metadata_batch_size": "How many videos one of those processes is asked for in a single run.",
    "playlist_chunk_size": "How many flat-playlist entries are handled per batch.",
    "fetch_full_metadata": "Off keeps listing fast and stores partial metadata only.",
    "cookie_fallback_enabled": "Retry with browser cookies when YouTube raises a bot check.",
    "cookie_fallback_browser": "Which browser to take cookies from.",
    "cookie_fallback_profile": "Which profile inside that browser. Empty means the default one.",
    "cookie_fallback_home": (
        "Only needed for a confined install. yt-dlp looks under $HOME/.config, which is not where a "
        "snap or a flatpak keeps its profile. Leave it empty and the path is worked out from the browser above."
    ),
    "youtube_visitor_data": "Token used for some YouTube requests. Kept out of the change log.",
    "youtube_player_clients": "Extraction clients to try, comma separated. The current first answer to bot checks.",
    "youtube_po_tokens": "Proof-of-origin tokens, comma separated, each written as context.type+value.",
    "info_cache_enabled": "Reuse stored metadata so a second pass over the same videos runs no yt-dlp at all.",
    "info_cache_dir": "One JSON file per video. Relative paths resolve from yt_aio/application.",
    "info_cache_max_age_hours": "How long a cached file counts as fresh. Zero means it never expires.",
    "enable_download_archive": "Let yt-dlp refuse anything it has already fetched. The database check stays either way.",
    "download_archive_path": "One line per fetched video. A relative path resolves from yt_aio/application.",
    "preferred_audio_codec": "Ranked first when several audio streams exist. Empty means no codec preference.",
    "concurrent_fragments": "Fragments fetched at once for a single file. The main speed-up on large files.",
    "download_retries": "yt-dlp's own retries, separate from max_retries, which re-runs the whole command.",
    "fragment_retries": "yt-dlp's own per-fragment retries.",
    "limit_rate": "Bandwidth cap such as 2M. Empty means no cap.",
    "restrict_filenames": "Write ASCII-only file names with no spaces.",
    "embed_album_from_playlist": "Write the playlist title into the album tag. Off, because a playlist is often a mix, not an album.",
    "socket_timeout": "How long yt-dlp waits on a stalled connection before giving up on an entry.",
    "ui_theme": "dark is Night Mode, light is Day Mode. Applied to the whole window on Save.",
}


class SettingsPanel(QWidget):
    """One tab. Constructed once at start-up and never destroyed."""

    def __init__(self, parent: QWidget | None = None, *, context: AppContext) -> None:
        super().__init__(parent)

        # ---- 1. state
        self._ctx = context
        self._defaults = build_default_config()
        self._editors: dict[str, QWidget] = {}
        self._built = False

        # ---- 2. widgets
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.form_host)

        self.save_button = QPushButton("Save")
        self.reload_button = QPushButton("Reload from file")
        self.defaults_button = QPushButton("Reset to defaults")
        self.path_label = muted("")
        self.status_label = muted("")

        # ---- 3. layout
        button_row = QHBoxLayout()
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.reload_button)
        button_row.addWidget(self.defaults_button)
        button_row.addStretch(1)

        box = QGroupBox("Configuration")
        box_layout = QVBoxLayout(box)
        box_layout.addWidget(self.path_label)
        box_layout.addWidget(self.scroll, 1)

        root = QVBoxLayout(self)
        root.addWidget(box, 1)
        root.addLayout(button_row)
        root.addWidget(self.status_label)

        # ---- 4. signals
        self.save_button.clicked.connect(self._save)
        self.reload_button.clicked.connect(self._reload_from_file)
        self.defaults_button.clicked.connect(self._reset_to_defaults)
        self._ctx.config_changed.connect(self._on_config_changed)

        # ---- 5. initial state. Editors are built on the first paint, not here, so
        # the constructor stays free of file reads.
        self.path_label.setText(str(self._ctx.config_path))

    def _sync_form_height(self) -> None:
        """Let the form be as tall as it needs to be, so the scroll bar appears.

        A QScrollArea in widgetResizable mode sizes its child to the viewport. With 49
        settings the form needs about 1800 pixels and the viewport offers under 750, and
        without an explicit minimum every row was squeezed to eight pixels: labels were
        clipped mid-descender and no scroll bar was ever offered.

        The measurement has to happen after the layout has been laid out. Asking during
        _build_form returns 18 pixels, the margins alone, and setting that as the minimum
        is worse than setting nothing. Hence activate() first, a width of zero treated as
        "not ready yet", and the deferred second pass _build_form schedules.
        """
        layout = self.form
        layout.activate()

        width = self.scroll.viewport().width()
        if width <= 0:
            return

        needed = layout.heightForWidth(width) if layout.hasHeightForWidth() else layout.sizeHint().height()
        # Anything at or below the margins means the layout is not ready. Keep whatever
        # minimum is already in place rather than replacing it with a wrong one.
        if needed <= layout.contentsMargins().top() + layout.contentsMargins().bottom():
            return

        if needed != self.form_host.minimumHeight():
            self.form_host.setMinimumHeight(needed)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """A narrower window wraps more help text, so the needed height changes with it."""
        super().resizeEvent(event)
        if self._built:
            self._sync_form_height()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().showEvent(event)
        if not self._built:
            self._built = True
            self._build_form(self._ctx.raw_config)

    # ------------------------------------------------------------------ helpers
    def _ordered_keys(self, config: dict[str, Any]) -> list[str]:
        """Defaults first, in their declared order, then anything the file adds."""
        keys = [key for key in self._defaults if key in config or key in self._defaults]
        keys += [key for key in config if key not in self._defaults]
        return keys

    def _make_editor(self, key: str, value: Any) -> QWidget:
        default = self._defaults.get(key)
        if isinstance(default, bool) or isinstance(value, bool):
            editor = QCheckBox()
            editor.setChecked(bool(value))
            return editor
        if isinstance(default, int) and not isinstance(default, bool):
            editor = QSpinBox()
            low, high, hint = SETTING_RANGES.get(key, (0, 1_000_000, ""))
            editor.setRange(low, high)
            if hint:
                editor.setToolTip(f"{hint} Allowed: {low} to {high}.")
            try:
                editor.setValue(int(value))
            except (TypeError, ValueError):
                editor.setValue(int(default))
            return editor

        suggestions = self._suggestions_for(key)
        if suggestions:
            return self._make_suggestion_box(key, value, default, suggestions)

        editor = QLineEdit("" if value is None else str(value))
        editor.setPlaceholderText("empty means not set" if default is None else str(default))
        return editor

    def _suggestions_for(self, key: str) -> list[str]:
        """Catalogue values first, then the default and whatever is in the file now.

        The stored value is always offered so an operator never has to retype a working
        setting the catalogue has not heard of.
        """
        listed = list(SETTING_SUGGESTIONS.get(key, ()))
        if not listed:
            return []
        for extra in (self._defaults.get(key), self._ctx.raw_config.get(key)):
            if extra not in (None, "") and str(extra) not in listed:
                listed.append(str(extra))
        return listed

    def _make_suggestion_box(self, key: str, value: Any, default: Any, suggestions: list[str]) -> QComboBox:
        editor = QComboBox()
        editor.setEditable(True)
        editor.setInsertPolicy(QComboBox.InsertPolicy.NoInsert if hasattr(QComboBox, "InsertPolicy") else QComboBox.NoInsert)
        editor.addItems(suggestions)

        completer = editor.completer()
        if completer is not None:
            completer.setCaseSensitivity(CASE_INSENSITIVE)
            completer.setFilterMode(MATCH_CONTAINS)
            completer.setCompletionMode(
                QCompleter.CompletionMode.PopupCompletion
                if hasattr(QCompleter, "CompletionMode")
                else QCompleter.PopupCompletion
            )

        text = "" if value is None else str(value)
        editor.setCurrentText(text)
        line = editor.lineEdit()
        if line is not None:
            line.setPlaceholderText("empty means not set" if default is None else str(default))
        editor.setToolTip(f"{len(suggestions)} suggested value(s). Anything typed is accepted.")
        return editor

    def _help_for(self, key: str, value: Any) -> str:
        """The explanation for one setting, plus anything discovered on this machine."""
        text = HELP.get(key, "")
        if key == "cookie_fallback_browser":
            # What is actually installed, not what could be. Rebuilt on every form build,
            # so plugging in a browser and pressing Reload shows it.
            try:
                found = describe_browser(str(value or ""))
            except Exception:
                found = ""
            if found:
                text = f"{text} {found}".strip()
        return text

    def _field_widget(self, key: str, editor: QWidget, value: Any) -> QWidget:
        """The right-hand half of a row: the editor, a Browse button, and the help under it.

        The help used to be a second line inside the key's own label. Two problems came
        with that. The two texts read as one run-on string, which is what the config key
        is called and what it does jammed together; and a word-wrapped label has a
        height that depends on its width, which collapsed the whole scrolling form.
        """
        host = QWidget()
        column = QVBoxLayout(host)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)

        if key in DIRECTORY_KEYS or key in FILE_KEYS:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(editor, 1)
            browse = QPushButton("Browse...")
            row.addWidget(browse)
            browse.clicked.connect(lambda _=False, k=key, e=editor: self._browse(k, e))
            column.addLayout(row)
        else:
            column.addWidget(editor)

        text = self._help_for(key, value)
        if text:
            caption = muted(text)
            caption.setWordWrap(True)
            column.addWidget(caption)
            editor.setToolTip("\n".join(filter(None, [editor.toolTip(), text])))

        return host

    def _build_form(self, config: dict[str, Any]) -> None:
        while self.form.count():
            item = self.form.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._editors.clear()

        for key in self._ordered_keys(config):
            value = config.get(key, self._defaults.get(key))
            editor = self._make_editor(key, value)
            self._editors[key] = editor

            label = QLabel(key)
            # No wrapping here. A key is one short token, and a wrapped label is what
            # made the form collapse in the first place.
            label.setWordWrap(False)
            label.setAlignment(ALIGN_TOP)
            help_text = self._help_for(key, value)
            if help_text:
                label.setToolTip(help_text)
            self.form.addRow(label, self._field_widget(key, editor, value))

        self.path_label.setText(str(self._ctx.config_path))
        self._sync_form_height()
        # Once more after this event finishes, when the viewport has a real width.
        QTimer.singleShot(0, self._sync_form_height)

    def _collect(self) -> dict[str, Any]:
        """Read the editors back into a config dictionary, keyed by the default's type."""
        collected: dict[str, Any] = {}
        for key, editor in self._editors.items():
            default = self._defaults.get(key)
            if isinstance(editor, QCheckBox):
                collected[key] = editor.isChecked()
            elif isinstance(editor, QSpinBox):
                collected[key] = int(editor.value())
            else:
                text = (
                    editor.currentText() if isinstance(editor, QComboBox) else editor.text()
                ).strip()
                if not text:
                    # A key whose default is a string keeps an empty string; a key whose
                    # default is None becomes null, which is what the utils layer expects.
                    collected[key] = "" if isinstance(default, str) else None
                else:
                    collected[key] = text
        return collected

    def _write_atomically(self, payload: dict[str, Any]) -> None:
        """Write beside the target and rename in, so a reader never sees a half file."""
        target = Path(self._ctx.config_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(json.dumps(payload, indent=4), encoding="utf-8")
        os.replace(temporary, target)

    def _log(self, tag: str, message: str) -> None:
        self.status_label.setText(f"[{tag}] {message}")

    # ------------------------------------------------------------------- slots
    @pyqtSlot()
    def _browse(self, key: str, editor: QWidget) -> None:
        current = self._editor_text(editor).strip() or str(Path.home())
        if key in DIRECTORY_KEYS:
            chosen = QFileDialog.getExistingDirectory(self, f"Choose a directory for {key}", current)
        else:
            chosen, _ = QFileDialog.getOpenFileName(self, f"Choose a file for {key}", current)
        if chosen:
            if isinstance(editor, QComboBox):
                editor.setCurrentText(chosen)
            else:
                editor.setText(chosen)

    @staticmethod
    def _editor_text(editor: QWidget) -> str:
        if isinstance(editor, QComboBox):
            return editor.currentText()
        if isinstance(editor, QLineEdit):
            return editor.text()
        return ""

    @pyqtSlot()
    def _save(self) -> None:
        payload = self._collect()
        try:
            json.dumps(payload)
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Cannot save", f"The settings do not serialise: {exc}")
            return

        changed = [
            key for key, value in payload.items()
            if self._ctx.raw_config.get(key) != value
        ]
        if not changed:
            self._log("INFO", "Nothing changed.")
            return

        try:
            self._write_atomically(payload)
        except OSError as exc:
            QMessageBox.critical(self, "Cannot write the config", str(exc))
            self._log("ERR", f"Could not write {self._ctx.config_path}: {exc}")
            return

        # reload_if_changed records every changed key in settings_changes, re-inits the
        # database if its path moved, and tells the other tabs.
        self._ctx.reload_if_changed(self._log)
        shown = ", ".join(key for key in changed if key not in SENSITIVE_KEYS)
        self._log("INFO", f"Saved {len(changed)} change(s) to {self._ctx.config_path}. {shown}".strip())

    @pyqtSlot()
    def _reload_from_file(self) -> None:
        self._ctx.reload_if_changed(self._log)
        self._build_form(self._ctx.raw_config)
        self._log("INFO", f"Reloaded from {self._ctx.config_path}")

    @pyqtSlot()
    def _reset_to_defaults(self) -> None:
        answer = QMessageBox.question(
            self,
            "Reset to defaults",
            "Fill every field with its built-in default?\n\n"
            "Nothing is written until you press Save, so you can still back out.",
            MB_YES | MB_NO,
            MB_NO,
        )
        if answer != MB_YES:
            return
        self._build_form(dict(self._defaults))
        self._log("INFO", "Fields filled with the built-in defaults. Press Save to keep them.")

    @pyqtSlot()
    def _on_config_changed(self) -> None:
        """Another tab or an external edit changed the file. Show what is on disk now."""
        if self._built:
            self._build_form(self._ctx.raw_config)
