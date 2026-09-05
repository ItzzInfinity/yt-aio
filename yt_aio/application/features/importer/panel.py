"""Import panel.

Owns:   the Import tab.
Reads:  a backup file the operator chose, through features/importer/parsers.py.
Writes: youtube_video_information and sources rows when the operator merges an import;
        downloads rows and media files when the operator downloads from one.
Runs:   yt-dlp, through the shared runner in application/jobs.py, for downloads only.
        Parsing runs on a worker thread too, because a backup database can be large
        (dev_guide.md 5, Pattern C).

The tab never hands items to the Downloader tab. Panels do not know each other; this
one runs its own job through the same shared runner.

A parsed file is held whole in memory, so filtering and sorting happen here rather than
in SQL. The tick boxes are keyed by video id instead of by row, which is what lets a
selection survive a change of filter or sort order.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import Any, Callable

from ...context import AppContext
from ...db.queries import import_video_rows
from ...jobs import CallableThread, TaskThread
from ...ui.qt import (
    ALIGN_RIGHT,
    CASE_INSENSITIVE,
    CHECKED,
    ITEM_FLAGS,
    MATCH_CONTAINS,
    NO_EDIT,
    ORIENTATION_HORIZONTAL,
    SELECT_ROWS,
    SORT_ASCENDING,
    SORT_DESCENDING,
    UNCHECKED,
    USER_ROLE,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QSplitter,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    pyqtSlot,
)
from ...ui.widgets import ConsoleView, RecordTable, muted
from ...utils.download_manager import record_user_action
from ...utils.shared import CancellationToken, DownloadTarget, now_string as _stamp
from ...utils.video_info_extractor import format_duration
from .models import (
    COLLECTION_CACHED,
    COLLECTION_DOWNLOADED,
    COLLECTION_HISTORY,
    COLLECTION_LIBRARY,
    COLLECTION_LIKED,
    COLLECTION_PLAYLIST,
    ImportedItem,
)
from .parsers import parse_backup_file

# Heading, and how a row is read for sorting. None is the tick box, which never sorts.
COLUMNS: list[tuple[str, Callable[[ImportedItem], Any] | None]] = [
    ("", None),
    ("Video ID", lambda item: item.video_id),
    ("Title", lambda item: item.display_title.casefold()),
    # Sorts on what the cell shows, not on the primary artist alone.
    ("Artist", lambda item: (item.artists or item.channel_name).casefold()),
    ("Album", lambda item: item.album.casefold()),
    ("Duration", lambda item: item.duration_seconds if item.duration_seconds is not None else -1),
    ("Collection", lambda item: item.collection_label),
    ("Playlists", lambda item: item.playlists.casefold()),
    ("Plays", lambda item: item.play_count),
    ("URL", lambda item: item.url),
]
HEADERS = [heading for heading, _ in COLUMNS]
NUMERIC_COLUMNS = {5, 8}
DEFAULT_SORT_COLUMN = 2

# Filter name -> what an item must carry to pass it. None means everything passes.
COLLECTION_FILTERS: dict[str, Callable[[ImportedItem], bool] | None] = {
    "Everything": None,
    "Saved, liked or downloaded": lambda item: item.collection_label != COLLECTION_CACHED,
    "Downloaded on the phone": lambda item: COLLECTION_DOWNLOADED in item.collections,
    "Liked": lambda item: COLLECTION_LIKED in item.collections,
    "In the library": lambda item: COLLECTION_LIBRARY in item.collections,
    "In a playlist": lambda item: COLLECTION_PLAYLIST in item.collections,
    "Played at least once": lambda item: COLLECTION_HISTORY in item.collections,
    "Cache only": lambda item: item.collection_label == COLLECTION_CACHED,
}
NON_CACHE_FILTER = "Saved, liked or downloaded"

MAX_FILTER_MINUTES = 600

FILE_FILTER = (
    "Backup files (*.db *.sqlite *.sqlite3 *.zip *.json *.csv *.txt);;All files (*)"
)


class ImportPanel(QWidget):
    """One tab. Constructed once at start-up and never destroyed."""

    def __init__(self, parent: QWidget | None = None, *, context: AppContext) -> None:
        super().__init__(parent)

        # ---- 1. state
        self._ctx = context
        self._busy = False
        self._items: list[ImportedItem] = []
        self._visible: list[ImportedItem] = []
        self._checked: set[str] = set()
        self._sort_column = DEFAULT_SORT_COLUMN
        self._sort_descending = False
        self._source_label = ""
        self._parse_worker: CallableThread | None = None
        self._download_worker: TaskThread | None = None
        self._cancel_token: CancellationToken | None = None

        # ---- 2. widgets
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("Backup exported by a phone app: SQLite, ZIP, JSON, CSV or a text file of links")
        self.browse_button = QPushButton("Browse...")
        self.parse_button = QPushButton("Parse file")
        self.format_label = muted("No file parsed yet.")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Title, artist, album or video ID")
        self.collection_select = QComboBox()
        self.collection_select.addItems(list(COLLECTION_FILTERS))
        self.channel_select = QComboBox()
        self.channel_select.setEditable(True)
        self.channel_select.setMinimumWidth(170)
        completer = self.channel_select.completer()
        if completer is not None:
            completer.setCaseSensitivity(CASE_INSENSITIVE)
            completer.setFilterMode(MATCH_CONTAINS)
        self.min_minutes = QSpinBox()
        self.min_minutes.setRange(0, MAX_FILTER_MINUTES)
        self.min_minutes.setSuffix(" min")
        self.min_minutes.setToolTip("Shortest duration to show. Zero means no lower bound.")
        self.max_minutes = QSpinBox()
        self.max_minutes.setRange(0, MAX_FILTER_MINUTES)
        self.max_minutes.setSuffix(" min")
        self.max_minutes.setToolTip("Longest duration to show. Zero means no upper bound.")
        self.clear_filters_button = QPushButton("Clear filters")

        self.table = RecordTable(HEADERS)
        self.table.setSelectionBehavior(SELECT_ROWS)
        self.table.setEditTriggers(NO_EDIT)
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)

        self.select_all_box = QCheckBox("Select all shown")
        self.selection_label = muted("")
        self.audio_radio = QRadioButton("Audio")
        self.video_radio = QRadioButton("Video")
        self.audio_radio.setChecked(True)
        self.merge_button = QPushButton("Add to database")
        self.download_button = QPushButton("Download selected")
        self.stop_button = QPushButton("Stop")

        self.log_output = ConsoleView()

        # ---- 3. layout
        file_box = QGroupBox("Backup file")
        file_row = QHBoxLayout(file_box)
        file_row.addWidget(QLabel("File"))
        file_row.addWidget(self.file_input, 1)
        file_row.addWidget(self.browse_button)
        file_row.addWidget(self.parse_button)

        filter_box = QGroupBox("Filters")
        filter_column = QVBoxLayout(filter_box)
        first_row = QHBoxLayout()
        first_row.addWidget(QLabel("Search"))
        first_row.addWidget(self.search_input, 1)
        first_row.addWidget(QLabel("Artist"))
        first_row.addWidget(self.channel_select)
        second_row = QHBoxLayout()
        second_row.addWidget(QLabel("Show"))
        second_row.addWidget(self.collection_select)
        second_row.addWidget(QLabel("Duration"))
        second_row.addWidget(self.min_minutes)
        second_row.addWidget(QLabel("to"))
        second_row.addWidget(self.max_minutes)
        second_row.addStretch(1)
        second_row.addWidget(self.clear_filters_button)
        filter_column.addLayout(first_row)
        filter_column.addLayout(second_row)

        self._media_group = QButtonGroup(self)
        self._media_group.addButton(self.audio_radio)
        self._media_group.addButton(self.video_radio)

        action_row = QHBoxLayout()
        action_row.addWidget(self.select_all_box)
        action_row.addWidget(self.selection_label)
        action_row.addStretch(1)
        action_row.addWidget(self.audio_radio)
        action_row.addWidget(self.video_radio)
        action_row.addWidget(self.merge_button)
        action_row.addWidget(self.download_button)
        action_row.addWidget(self.stop_button)

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.addWidget(file_box)
        top_layout.addWidget(self.format_label)
        top_layout.addWidget(filter_box)
        top_layout.addWidget(self.table, 1)
        top_layout.addLayout(action_row)

        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.addWidget(QLabel("Log"))
        bottom_layout.addWidget(self.log_output)

        split = QSplitter(ORIENTATION_HORIZONTAL)
        split.addWidget(top)
        split.addWidget(bottom)
        split.setSizes([900, 420])

        root = QVBoxLayout(self)
        root.addWidget(split)

        # ---- 4. signals
        self.browse_button.clicked.connect(self._browse)
        self.parse_button.clicked.connect(self._parse)
        self.select_all_box.toggled.connect(self._toggle_all)
        self.merge_button.clicked.connect(self._merge)
        self.download_button.clicked.connect(self._download)
        self.stop_button.clicked.connect(self._cancel)
        self.search_input.textChanged.connect(self._apply_filters)
        self.collection_select.currentTextChanged.connect(self._apply_filters)
        self.channel_select.currentTextChanged.connect(self._apply_filters)
        self.min_minutes.valueChanged.connect(self._apply_filters)
        self.max_minutes.valueChanged.connect(self._apply_filters)
        self.clear_filters_button.clicked.connect(self._clear_filters)
        self.table.itemChanged.connect(self._on_item_changed)
        header.sectionClicked.connect(self._sort_by_column)

        # ---- 5. initial state
        self._set_busy(False)
        self._show_sort_indicator()
        self._update_selection_label()
        self.log_output.log("INFO", "Choose a backup file, then press Parse file.")

    # ------------------------------------------------------------------ shell hook
    def shutdown(self) -> None:
        """Called by the shell on close. Safe to call while idle."""
        if self._cancel_token is not None:
            self._cancel_token.cancel()
        for worker in (self._parse_worker, self._download_worker):
            if worker is not None and worker.isRunning():
                worker.wait(5000)

    # ------------------------------------------------------------------ helpers
    def _log(self, tag: str, text: str) -> None:
        self.log_output.log(tag, text)

    def append_log(self, message: str) -> None:
        """Sink for a worker's log_message signal."""
        self.log_output.append_raw(message)

    def _set_busy(self, busy: bool) -> None:
        """Single place where enablement is decided. Every terminal path calls this."""
        self._busy = busy
        has_selection = bool(self._checked)
        self.file_input.setEnabled(not busy)
        self.browse_button.setEnabled(not busy)
        self.parse_button.setEnabled(not busy)
        self.table.setEnabled(not busy)
        for widget in (
            self.search_input,
            self.collection_select,
            self.channel_select,
            self.min_minutes,
            self.max_minutes,
            self.clear_filters_button,
        ):
            widget.setEnabled(not busy and bool(self._items))
        self.select_all_box.setEnabled(not busy and bool(self._visible))
        self.audio_radio.setEnabled(not busy)
        self.video_radio.setEnabled(not busy)
        self.merge_button.setEnabled(not busy and has_selection)
        self.download_button.setEnabled(not busy and has_selection)
        self.stop_button.setEnabled(busy)

    def _checked_items(self) -> list[ImportedItem]:
        """Everything ticked, whether or not the current filter shows it."""
        return [item for item in self._items if item.video_id in self._checked]

    def _duration_bounds(self) -> tuple[int | None, int | None]:
        return self.min_minutes.value() * 60 or None, self.max_minutes.value() * 60 or None

    def _passes(self, item: ImportedItem) -> bool:
        needle = self.search_input.text().strip().casefold()
        if needle:
            haystack = " ".join(
                (item.video_id, item.title, item.channel_name, item.artists, item.album, item.playlists)
            ).casefold()
            if needle not in haystack:
                return False

        artist = self.channel_select.currentText().strip().casefold()
        if artist and artist not in f"{item.channel_name} {item.artists}".casefold():
            return False

        low, high = self._duration_bounds()
        if low or high:
            # Nothing is known about an item with no duration, so a duration filter
            # cannot claim it matches.
            if item.duration_seconds is None:
                return False
            if low and item.duration_seconds < low:
                return False
            if high and item.duration_seconds > high:
                return False

        predicate = COLLECTION_FILTERS.get(self.collection_select.currentText())
        return predicate is None or predicate(item)

    def _load_artist_options(self) -> None:
        names = sorted(
            {item.channel_name for item in self._items if item.channel_name},
            key=str.casefold,
        )
        self.channel_select.blockSignals(True)
        self.channel_select.clear()
        self.channel_select.addItem("")
        self.channel_select.addItems(names)
        self.channel_select.setCurrentText("")
        self.channel_select.blockSignals(False)
        line = self.channel_select.lineEdit()
        if line is not None:
            line.setPlaceholderText(f"Any of {len(names)} artist(s)")

    def _show_sort_indicator(self) -> None:
        self.table.horizontalHeader().setSortIndicator(
            self._sort_column, SORT_DESCENDING if self._sort_descending else SORT_ASCENDING
        )

    def _update_selection_label(self) -> None:
        self.selection_label.setText(
            f"{len(self._checked)} selected of {len(self._visible)} shown, {len(self._items)} parsed."
        )

    def _render(self) -> None:
        # The tick boxes write back through itemChanged, so that has to stay quiet
        # while the grid is being filled.
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._visible))
        for row_index, item in enumerate(self._visible):
            box = QTableWidgetItem()
            box.setFlags(ITEM_FLAGS)
            box.setCheckState(CHECKED if item.video_id in self._checked else UNCHECKED)
            box.setData(USER_ROLE, item.video_id)
            self.table.setItem(row_index, 0, box)
            cells = [
                item.video_id,
                item.display_title,
                item.artists or item.channel_name,
                item.album,
                format_duration(item.duration_seconds),
                item.collection_label,
                item.playlists,
                str(item.play_count or ""),
                item.url,
            ]
            for column_index, text in enumerate(cells, start=1):
                cell = QTableWidgetItem(str(text))
                if column_index in NUMERIC_COLUMNS:
                    cell.setTextAlignment(ALIGN_RIGHT)
                self.table.setItem(row_index, column_index, cell)
        self.table.blockSignals(False)

        self.table.resizeColumnsToContents()
        self._show_sort_indicator()

        shown_ids = {item.video_id for item in self._visible}
        self.select_all_box.blockSignals(True)
        self.select_all_box.setChecked(bool(shown_ids) and shown_ids <= self._checked)
        self.select_all_box.blockSignals(False)
        self._update_selection_label()
        self._set_busy(self._busy)

    def _attach(self, worker) -> None:
        worker.log_message.connect(self.append_log)
        worker.work_complete.connect(self._on_work_complete)
        worker.work_failed.connect(self._on_work_failed)

    # ------------------------------------------------------------------- slots
    @pyqtSlot()
    def _apply_filters(self) -> None:
        self._visible = [item for item in self._items if self._passes(item)]
        key = COLUMNS[self._sort_column][1]
        if key is not None:
            self._visible.sort(key=key, reverse=self._sort_descending)
        self._render()

    @pyqtSlot(int)
    def _sort_by_column(self, column: int) -> None:
        if not 0 <= column < len(COLUMNS) or COLUMNS[column][1] is None:
            return
        if column == self._sort_column:
            self._sort_descending = not self._sort_descending
        else:
            self._sort_column = column
            self._sort_descending = column in NUMERIC_COLUMNS
        self._apply_filters()

    @pyqtSlot()
    def _clear_filters(self) -> None:
        self.search_input.clear()
        self.channel_select.setCurrentText("")
        for widget in (self.min_minutes, self.max_minutes):
            widget.setValue(0)
        self.collection_select.setCurrentIndex(0)
        self._apply_filters()

    @pyqtSlot(QTableWidgetItem)
    def _on_item_changed(self, changed: QTableWidgetItem) -> None:
        """One tick box moved. The video id is the key, not the row number."""
        if changed.column() != 0:
            return
        video_id = changed.data(USER_ROLE)
        if not video_id:
            return
        if changed.checkState() == CHECKED:
            self._checked.add(str(video_id))
        else:
            self._checked.discard(str(video_id))
        self._update_selection_label()
        self._set_busy(self._busy)

    @pyqtSlot()
    def _browse(self) -> None:
        start = self.file_input.text().strip() or str(Path.home())
        chosen, _ = QFileDialog.getOpenFileName(self, "Choose a backup file", start, FILE_FILTER)
        if chosen:
            self.file_input.setText(chosen)

    @pyqtSlot()
    def _parse(self) -> None:
        if self._busy:
            self._log("WARN", "A task is already running.")
            return

        path = self.file_input.text().strip()
        if not path or not os.path.isfile(os.path.expanduser(path)):
            QMessageBox.warning(self, "No file", f"Choose an existing file.\n{path or '(nothing entered)'}")
            self._log("WARN", f"Not a readable file: {path or '(nothing entered)'}")
            return

        self._cancel_token = CancellationToken()
        self._items = []
        self._visible = []
        self._checked = set()
        self.table.setRowCount(0)
        self._set_busy(True)
        self._log("TX", f"Parsing {path}")

        def job(log, _token):
            # The parser writes plain sentences; tag them as they cross into the console.
            return parse_backup_file(path, lambda message: log(f"[{_stamp()}] [INFO] {message}"))

        self._parse_worker = CallableThread(job, self._cancel_token, done_message="Parse finished.")
        self._attach(self._parse_worker)
        self._parse_worker.result_ready.connect(self._on_parsed)
        self._parse_worker.start()

    @pyqtSlot(object)
    def _on_parsed(self, result) -> None:
        items, label = result
        self._items = list(items)
        self._source_label = os.path.basename(self.file_input.text().strip())
        self._load_artist_options()

        # A music-app backup caches far more than the operator ever saved. When the
        # file says which is which, start on the saved music rather than on the cache.
        saved = sum(1 for item in self._items if item.collection_label != COLLECTION_CACHED)
        self.collection_select.blockSignals(True)
        self.collection_select.setCurrentText(
            NON_CACHE_FILTER if 0 < saved < len(self._items) else "Everything"
        )
        self.collection_select.blockSignals(False)

        self._apply_filters()
        # Ticking only what is on screen keeps the default action honest: what the
        # buttons act on is what the grid shows.
        self._checked = {item.video_id for item in self._visible}
        self._render()

        self.format_label.setText(
            f"Detected {label}. {len(self._items)} unique video(s) from {self._source_label}; "
            f"{len(self._visible)} shown by the current filter."
        )
        self._log("INFO", f"Detected {label}: {len(self._items)} unique video(s).")
        if 0 < saved < len(self._items):
            self._log(
                "INFO",
                f"{saved} of them are saved, liked, downloaded, played or in a playlist. "
                f"The other {len(self._items) - saved} are cache only; switch Show to "
                "Everything to see them.",
            )

    @pyqtSlot(bool)
    def _toggle_all(self, checked: bool) -> None:
        """Applies to the rows on screen, never to rows a filter is hiding."""
        shown = {item.video_id for item in self._visible}
        if checked:
            self._checked |= shown
        else:
            self._checked -= shown
        self._render()

    @pyqtSlot()
    def _merge(self) -> None:
        if self._busy:
            self._log("WARN", "A task is already running.")
            return
        selected = self._checked_items()
        if not selected:
            QMessageBox.information(self, "Nothing selected", "Tick the rows you want to add.")
            return

        record_user_action(self._ctx.db_path, "import merge")
        rows = [dataclasses.asdict(item) for item in selected]
        label = self._source_label or "backup"
        db_path = self._ctx.db_path

        self._cancel_token = CancellationToken()
        self._set_busy(True)
        self._log("INFO", f"Adding {len(rows)} item(s) to {db_path}")

        def job(log, _token):
            written, skipped = import_video_rows(db_path, rows, label)
            log(f"[{_stamp()}] [INFO] {written} row(s) written, {skipped} skipped.")
            return written, skipped

        self._parse_worker = CallableThread(job, self._cancel_token, done_message="Import finished.")
        self._attach(self._parse_worker)
        self._parse_worker.result_ready.connect(self._on_merged)
        self._parse_worker.start()

    @pyqtSlot(object)
    def _on_merged(self, result) -> None:
        written, skipped = result
        self._log(
            "INFO",
            f"Added {written} row(s) to the database under the source '{self._source_label or 'backup'}'. "
            f"{skipped} row(s) had no video id. Open the Library tab to see them.",
        )

    @pyqtSlot()
    def _download(self) -> None:
        if self._busy:
            self._log("WARN", "A task is already running.")
            return
        selected = self._checked_items()
        if not selected:
            QMessageBox.information(self, "Nothing selected", "Tick the rows you want to download.")
            return

        record_user_action(self._ctx.db_path, "import download")
        media_type = "video" if self.video_radio.isChecked() else "audio"
        targets = [
            DownloadTarget(url=item.url, title=item.title or None, video_id=item.video_id)
            for item in selected
        ]

        self._cancel_token = CancellationToken()
        self._set_busy(True)
        self._log("TX", f"Starting {media_type} download for {len(targets)} imported item(s).")
        self._download_worker = TaskThread(
            "download",
            self._ctx.config,
            self._ctx.db_path,
            self._cancel_token,
            media_type=media_type,
            targets=targets,
            source_name=self._source_label or "Import",
        )
        self._attach(self._download_worker)
        self._download_worker.start()

    @pyqtSlot()
    def _cancel(self) -> None:
        if not self._busy or self._cancel_token is None:
            self._log("WARN", "No running task to stop.")
            return
        self._cancel_token.cancel()
        self._log("INFO", "Stop requested.")

    @pyqtSlot(str)
    def _on_work_complete(self, summary: str) -> None:
        self._log("INFO", summary)
        self._set_busy(False)
        self._parse_worker = None
        self._download_worker = None
        self._cancel_token = None

    @pyqtSlot(str)
    def _on_work_failed(self, message: str) -> None:
        self._log("ERR", message)
        self._set_busy(False)
        self._parse_worker = None
        self._download_worker = None
        self._cancel_token = None
        QMessageBox.warning(self, "Import failed", message)
