"""Local Scan panel.

Owns:   the Local Scan tab.
Reads:  a folder of audio files the operator chose, through utils/local_library.py,
        and the cache it compares them against, through db/local_files.py.
Writes: local_files rows. Never modifies, moves or deletes a file on disk.
Runs:   nothing external except ffprobe, and only for a file mutagen declined
        (dev_guide.md 5, Pattern C: the scan itself runs on a worker thread).

The tab answers one question: which of these files do I already have, and which are new.
A wrong "already have" is the expensive answer, because it would stop a download the
operator wanted, so the four verdicts are shown as they are rather than collapsed into
a yes or no. The detail pane puts the file and the database row side by side for the
clashes, which are exactly the rows a person has to decide about.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...context import AppContext
from ...db.local_files import (
    DEFAULT_LOCAL_SORT,
    STATUS_CLASH,
    STATUS_IN_DATABASE,
    STATUS_NEW,
    STATUS_PROBABLE,
    add_local_files_to_library,
    fetch_local_artists,
    fetch_local_files,
    fetch_local_roots,
    forget_root,
    record_scan,
)
from ...jobs import CallableThread
from ...ui.qt import (
    ALIGN_RIGHT,
    CASE_INSENSITIVE,
    MATCH_CONTAINS,
    MB_NO,
    MB_YES,
    NO_EDIT,
    ORIENTATION_HORIZONTAL,
    SELECT_ROWS,
    SORT_ASCENDING,
    SORT_DESCENDING,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    pyqtSlot,
)
from ...ui.widgets import ConsoleView, RecordTable, muted
from ...utils.download_manager import record_user_action
from ...utils.local_library import scan_directory
from ...utils.shared import CancellationToken, now_string as _stamp
from ...utils.video_info_extractor import format_duration

# Heading, and the sort key db/local_files.py accepts for it.
COLUMNS: list[tuple[str, str]] = [
    ("Status", "match_status"),
    ("File", "file_name"),
    ("Title", "title"),
    ("Artist", "artist"),
    ("Album", "album"),
    ("Duration", "duration"),
    ("Bitrate", "bitrate"),
    ("Video ID", "video_id"),
    ("Modified", "modified_at"),
    ("First seen", "first_seen_at"),
]
HEADERS = [heading for heading, _ in COLUMNS]
NUMERIC_COLUMNS = {5, 6}

STATUS_FILTERS = [
    "Everything",
    STATUS_NEW,
    STATUS_CLASH,
    STATUS_PROBABLE,
    STATUS_IN_DATABASE,
]

MAX_FILTER_MINUTES = 600


class LocalScanPanel(QWidget):
    """One tab. Constructed once at start-up and never destroyed."""

    def __init__(self, parent: QWidget | None = None, *, context: AppContext) -> None:
        super().__init__(parent)

        # ---- 1. state
        self._ctx = context
        self._busy = False
        self._rows: list[dict[str, Any]] = []
        self._offset = 0
        self._total = 0
        self._sort_key = DEFAULT_LOCAL_SORT
        self._sort_descending = False
        self._loaded_once = False
        self._scan_worker: CallableThread | None = None
        self._add_worker: CallableThread | None = None
        self._cancel_token: CancellationToken | None = None

        # ---- 2. widgets
        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText("A folder of audio files, for example ~/Music")
        self.browse_button = QPushButton("Browse...")
        self.recursive_box = QCheckBox("Include subfolders")
        self.recursive_box.setChecked(True)
        self.scan_button = QPushButton("Scan folder")
        self.stop_button = QPushButton("Stop")
        self.forget_button = QPushButton("Forget this folder")
        self.add_button = QPushButton("ADD TO DATABASE")
        self.add_button.setToolTip(
            "Write every file the filters currently match into the library.\n"
            "A file that names a video becomes a song and is flagged as downloaded.\n"
            "A file that names none is recorded separately, out of the way of the song queries."
        )

        self.root_select = QComboBox()
        self.root_select.setMinimumWidth(240)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("File name, title, artist, album or video ID")
        self.status_select = QComboBox()
        self.status_select.addItems(STATUS_FILTERS)
        self.artist_select = QComboBox()
        self.artist_select.setEditable(True)
        self.artist_select.setMinimumWidth(170)
        completer = self.artist_select.completer()
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
        self.untagged_box = QCheckBox("Untagged only")
        self.untagged_box.setToolTip("Files with no title tag, where only the name identifies them.")
        self.page_size = QSpinBox()
        self.page_size.setRange(10, 2000)
        self.page_size.setSingleStep(50)
        self.page_size.setValue(200)
        self.clear_filters_button = QPushButton("Clear filters")
        self.refresh_button = QPushButton("Refresh")

        self.table = RecordTable(HEADERS)
        self.table.setSelectionBehavior(SELECT_ROWS)
        self.table.setEditTriggers(NO_EDIT)
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)

        self.detail_view = QPlainTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setPlainText("Select a row to compare the file against the database.")

        self.prev_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        self.count_label = muted("No folder scanned yet.")
        self.summary_label = muted("")

        self.log_output = ConsoleView()

        # ---- 3. layout
        folder_box = QGroupBox("Folder")
        folder_row = QHBoxLayout(folder_box)
        folder_row.addWidget(QLabel("Path"))
        folder_row.addWidget(self.folder_input, 1)
        folder_row.addWidget(self.browse_button)
        folder_row.addWidget(self.recursive_box)
        folder_row.addWidget(self.scan_button)
        folder_row.addWidget(self.stop_button)

        filter_box = QGroupBox("Filters")
        filter_column = QVBoxLayout(filter_box)
        first_row = QHBoxLayout()
        first_row.addWidget(QLabel("Scanned folder"))
        first_row.addWidget(self.root_select)
        first_row.addWidget(QLabel("Search"))
        first_row.addWidget(self.search_input, 1)
        first_row.addWidget(QLabel("Artist"))
        first_row.addWidget(self.artist_select)
        second_row = QHBoxLayout()
        second_row.addWidget(QLabel("Show"))
        second_row.addWidget(self.status_select)
        second_row.addWidget(QLabel("Duration"))
        second_row.addWidget(self.min_minutes)
        second_row.addWidget(QLabel("to"))
        second_row.addWidget(self.max_minutes)
        second_row.addWidget(self.untagged_box)
        second_row.addWidget(QLabel("Rows"))
        second_row.addWidget(self.page_size)
        second_row.addStretch(1)
        second_row.addWidget(self.clear_filters_button)
        second_row.addWidget(self.refresh_button)
        filter_column.addLayout(first_row)
        filter_column.addLayout(second_row)

        action_row = QHBoxLayout()
        action_row.addWidget(self.add_button)
        action_row.addWidget(self.forget_button)
        action_row.addStretch(1)
        action_row.addWidget(self.prev_button)
        action_row.addWidget(self.next_button)
        action_row.addWidget(self.count_label)

        grid_host = QWidget()
        grid_layout = QVBoxLayout(grid_host)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.addWidget(self.table, 1)
        grid_layout.addLayout(action_row)

        detail_host = QWidget()
        detail_layout = QVBoxLayout(detail_host)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.addWidget(QLabel("File against database"))
        detail_layout.addWidget(self.detail_view, 1)
        detail_layout.addWidget(QLabel("Log"))
        detail_layout.addWidget(self.log_output, 1)

        split = QSplitter(ORIENTATION_HORIZONTAL)
        split.addWidget(grid_host)
        split.addWidget(detail_host)
        split.setSizes([900, 420])

        root = QVBoxLayout(self)
        root.addWidget(folder_box)
        root.addWidget(filter_box)
        root.addWidget(split, 1)
        root.addWidget(self.summary_label)

        # ---- 4. signals
        self.browse_button.clicked.connect(self._browse)
        self.scan_button.clicked.connect(self._scan)
        self.stop_button.clicked.connect(self._cancel)
        self.add_button.clicked.connect(self._add_to_database)
        self.forget_button.clicked.connect(self._forget)
        self.refresh_button.clicked.connect(self._reload)
        self.clear_filters_button.clicked.connect(self._clear_filters)
        self.root_select.currentIndexChanged.connect(self._on_root_changed)
        self.search_input.returnPressed.connect(self._reset_and_reload)
        self.status_select.currentTextChanged.connect(self._reset_and_reload)
        self.artist_select.currentTextChanged.connect(self._reset_and_reload)
        self.min_minutes.valueChanged.connect(self._reset_and_reload)
        self.max_minutes.valueChanged.connect(self._reset_and_reload)
        self.untagged_box.toggled.connect(self._reset_and_reload)
        self.page_size.valueChanged.connect(self._reset_and_reload)
        self.prev_button.clicked.connect(self._previous_page)
        self.next_button.clicked.connect(self._next_page)
        self.table.itemSelectionChanged.connect(self._show_detail)
        header.sectionClicked.connect(self._sort_by_column)

        # ---- 5. initial state. The first read waits for the first paint, so the
        # constructor never touches the database.
        self._set_busy(False)
        self._show_sort_indicator()
        self._update_page_buttons()
        self.log_output.log("INFO", "Choose a folder, then press Scan folder.")

    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().showEvent(event)
        if not self._loaded_once:
            self._loaded_once = True
            self._load_roots()
            self._load_artists()
            self._reload()

    # ------------------------------------------------------------------ shell hook
    def shutdown(self) -> None:
        """Called by the shell on close. Safe to call while idle."""
        if self._cancel_token is not None:
            self._cancel_token.cancel()
        if self._scan_worker is not None and self._scan_worker.isRunning():
            self._scan_worker.wait(5000)

    # ------------------------------------------------------------------ helpers
    def _log(self, tag: str, text: str) -> None:
        self.log_output.log(tag, text)

    def append_log(self, message: str) -> None:
        """Sink for a worker's log_message signal."""
        self.log_output.append_raw(message)

    def _set_busy(self, busy: bool) -> None:
        """Single place where enablement is decided. Every terminal path calls this."""
        self._busy = busy
        self.folder_input.setEnabled(not busy)
        self.browse_button.setEnabled(not busy)
        self.recursive_box.setEnabled(not busy)
        self.scan_button.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        self.forget_button.setEnabled(not busy and bool(self._selected_root()))
        self.add_button.setEnabled(not busy and bool(self._rows))
        for widget in (
            self.root_select, self.search_input, self.status_select, self.artist_select,
            self.min_minutes, self.max_minutes, self.untagged_box, self.page_size,
            self.clear_filters_button, self.refresh_button, self.table,
        ):
            widget.setEnabled(not busy)
        if not busy:
            self._update_page_buttons()
        else:
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)

    def _selected_root(self) -> str:
        return self.root_select.currentData() or ""

    def _duration_bounds(self) -> tuple[int | None, int | None]:
        """Minutes on screen, seconds in the query. Zero on either end means unbounded."""
        return self.min_minutes.value() * 60 or None, self.max_minutes.value() * 60 or None

    def _update_page_buttons(self) -> None:
        self.prev_button.setEnabled(not self._busy and self._offset > 0)
        self.next_button.setEnabled(
            not self._busy and self._offset + self.page_size.value() < self._total
        )

    def _show_sort_indicator(self) -> None:
        for index, (_, key) in enumerate(COLUMNS):
            if key == self._sort_key:
                self.table.horizontalHeader().setSortIndicator(
                    index, SORT_DESCENDING if self._sort_descending else SORT_ASCENDING
                )
                return

    def _load_roots(self, prefer: str = "") -> None:
        try:
            roots = fetch_local_roots(self._ctx.db_path)
        except Exception as exc:
            roots = []
            self._log("WARN", f"Could not read the scanned folders: {exc}")

        current = prefer or self._selected_root()
        self.root_select.blockSignals(True)
        self.root_select.clear()
        self.root_select.addItem("Every scanned folder", "")
        for entry in roots:
            path = str(entry["root_path"])
            self.root_select.addItem(
                f"{path}  ({entry['total']} files, {entry['new_files']} new)", path
            )
        if current:
            index = self.root_select.findData(current)
            if index >= 0:
                self.root_select.setCurrentIndex(index)
        self.root_select.blockSignals(False)

        if roots:
            newest = max(roots, key=lambda entry: str(entry.get("last_scanned") or ""))
            self.summary_label.setText(
                f"{len(roots)} folder(s) scanned. Most recent: {newest['root_path']} "
                f"at {newest.get('last_scanned') or 'an unknown time'}."
            )
        else:
            self.summary_label.setText("No folder has been scanned yet.")

    def _load_artists(self) -> None:
        try:
            artists = fetch_local_artists(self._ctx.db_path, self._selected_root())
        except Exception:
            artists = []
        current = self.artist_select.currentText()
        self.artist_select.blockSignals(True)
        self.artist_select.clear()
        self.artist_select.addItem("")
        self.artist_select.addItems(artists)
        self.artist_select.setCurrentText(current)
        self.artist_select.blockSignals(False)
        line = self.artist_select.lineEdit()
        if line is not None:
            line.setPlaceholderText(f"Any of {len(artists)} artist(s)")

    def _render(self) -> None:
        self.table.setRowCount(len(self._rows))
        for row_index, record in enumerate(self._rows):
            cells = [
                record.get("match_status") or "",
                record.get("file_name") or "",
                record.get("title") or "",
                record.get("artist") or "",
                record.get("album") or "",
                format_duration(record.get("duration")),
                f"{record['bitrate']}k" if record.get("bitrate") else "",
                record.get("video_id") or "",
                record.get("modified_at") or "",
                record.get("first_seen_at") or "",
            ]
            for column_index, text in enumerate(cells):
                cell = QTableWidgetItem(str(text))
                if column_index in NUMERIC_COLUMNS:
                    cell.setTextAlignment(ALIGN_RIGHT)
                self.table.setItem(row_index, column_index, cell)

        self.table.resizeColumnsToContents()
        self._show_sort_indicator()
        first = 0 if not self._rows else self._offset + 1
        last = self._offset + len(self._rows)
        self.count_label.setText(
            f"Showing {first}-{last} of {self._total}" if self._total else "No files match these filters."
        )
        self._update_page_buttons()
        # Whether there is anything to add depends on what the filters just returned, so
        # enablement is recomputed here rather than only when a task starts or ends.
        self._set_busy(self._busy)

    def _describe(self, record: dict[str, Any]) -> str:
        """The file on the left, what the database holds on the right."""
        local_duration = format_duration(record.get("duration"))
        matched_duration = format_duration(record.get("matched_duration"))
        lines = [
            f"Status      {record.get('match_status') or 'unknown'}",
            f"Why         {record.get('match_detail') or 'No explanation was recorded.'}",
            "",
            "ON DISK",
            f"  Path      {record.get('file_path') or ''}",
            f"  Title     {record.get('title') or '(no title tag)'}",
            f"  Artist    {record.get('artist') or '(none)'}",
            f"  Album     {record.get('album') or '(none)'}",
            f"  Duration  {local_duration}",
            f"  Bitrate   {str(record['bitrate']) + 'k' if record.get('bitrate') else '(unknown)'}",
            f"  Video ID  {record.get('video_id') or '(none found in tags or file name)'}",
            f"  Tags read {record.get('tag_source') or 'unknown'}",
            f"  Modified  {record.get('modified_at') or ''}",
            f"  Size      {record.get('size_bytes') or 0} bytes",
        ]

        if record.get("matched_video_info_id"):
            lines += [
                "",
                "IN THE DATABASE",
                f"  Title     {record.get('matched_title') or '(untitled)'}",
                f"  Channel   {record.get('matched_channel') or '(none)'}",
                f"  Duration  {matched_duration}",
                f"  Video ID  {record.get('matched_video_id') or '(none)'}",
            ]
            gap = None
            if record.get("duration") is not None and record.get("matched_duration") is not None:
                gap = abs(int(record["duration"]) - int(record["matched_duration"]))
            if gap is not None:
                lines.append(f"  Durations differ by {gap}s.")
        else:
            lines += ["", "IN THE DATABASE", "  Nothing is linked to this file."]

        if record.get("match_status") == STATUS_CLASH:
            lines += [
                "",
                "The titles agree but the recordings do not. Compare the two durations "
                "above and decide whether this is the same track under a different "
                "master, or a different track that happens to share a name.",
            ]
        elif record.get("match_status") == STATUS_NEW:
            lines += ["", "Nothing in the database resembles this file. It is safe to treat as new."]
        return "\n".join(lines)

    # ------------------------------------------------------------------- slots
    @pyqtSlot()
    def _browse(self) -> None:
        start = self.folder_input.text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Choose a folder of audio files", start)
        if chosen:
            self.folder_input.setText(chosen)

    @pyqtSlot()
    def _add_to_database(self) -> None:
        """Write what the filters match into the library (FSD 1.8.3).

        Acts on the whole filtered set, not the page on screen, because this grid filters
        rather than selects. The count is stated in the confirmation so what is about to
        happen is never a surprise.
        """
        if self._busy:
            self._log("WARN", "A task is already running.")
            return
        if not self._total:
            QMessageBox.information(self, "Nothing to add", "No scanned file matches the current filters.")
            return

        answer = QMessageBox.question(
            self,
            "Add to database",
            f"Write {self._total} scanned file(s) into the library?\n\n"
            "Files that name a video become songs and are flagged as downloaded.\n"
            "Files that name none are recorded separately, so they never answer a\n"
            "duplicate check for a video they are not.\n\n"
            "Nothing on disk is touched.",
            MB_YES | MB_NO,
            MB_NO,
        )
        if answer != MB_YES:
            return

        record_user_action(self._ctx.db_path, "local scan add to database")
        db_path = self._ctx.db_path
        low, high = self._duration_bounds()
        filters = {
            "root_path": self._selected_root(),
            "search": self.search_input.text(),
            "status": self.status_select.currentText(),
            "artist": self.artist_select.currentText(),
            "min_duration": low,
            "max_duration": high,
            "only_untagged": self.untagged_box.isChecked(),
        }

        self._cancel_token = CancellationToken()
        self._set_busy(True)
        self._log("TX", f"Adding {self._total} file(s) to the library.")

        def job(log, _token):
            def emit(message: str) -> None:
                log(f"[{_stamp()}] [INFO] {message}")

            return add_local_files_to_library(db_path, emit, **filters)

        self._add_worker = CallableThread(job, self._cancel_token, done_message="Add finished.")
        self._add_worker.log_message.connect(self.append_log)
        self._add_worker.result_ready.connect(self._on_added)
        self._add_worker.work_complete.connect(self._on_work_complete)
        self._add_worker.work_failed.connect(self._on_work_failed)
        self._add_worker.start()

    @pyqtSlot(object)
    def _on_added(self, summary: dict[str, Any]) -> None:
        self._reload()
        self._log(
            "INFO",
            f"{summary['considered']} file(s) written. Songs: {summary['songs_added']} added, "
            f"{summary['songs_updated']} already present, {summary['flagged_downloaded']} newly "
            f"flagged as downloaded. Without a video id: {summary['local_only_added']} added and "
            f"{summary['local_only_updated']} refreshed, kept out of the song tables.",
        )

    @pyqtSlot()
    def _scan(self) -> None:
        if self._busy:
            self._log("WARN", "A scan is already running.")
            return

        raw = self.folder_input.text().strip()
        folder = Path(raw).expanduser() if raw else None
        if folder is None or not folder.is_dir():
            QMessageBox.warning(
                self, "No folder", f"Choose an existing folder.\n{raw or '(nothing entered)'}"
            )
            self._log("WARN", f"Not a readable folder: {raw or '(nothing entered)'}")
            return

        record_user_action(self._ctx.db_path, "local scan")
        db_path = self._ctx.db_path
        root = str(folder)
        recursive = self.recursive_box.isChecked()

        self._cancel_token = CancellationToken()
        self._set_busy(True)
        self._log("TX", f"Scanning {root}")

        def job(log, token):
            # The scanner writes plain sentences; tag them as they cross into the console.
            def emit(message: str) -> None:
                log(f"[{_stamp()}] [INFO] {message}")

            tracks = scan_directory(root, emit, recursive=recursive, is_cancelled=token.is_cancelled)
            summary = record_scan(db_path, root, tracks, emit, forget_missing=not token.is_cancelled())
            return summary

        self._scan_worker = CallableThread(job, self._cancel_token, done_message="Scan finished.")
        self._scan_worker.log_message.connect(self.append_log)
        self._scan_worker.result_ready.connect(self._on_scanned)
        self._scan_worker.work_complete.connect(self._on_work_complete)
        self._scan_worker.work_failed.connect(self._on_work_failed)
        self._scan_worker.start()

    @pyqtSlot(object)
    def _on_scanned(self, summary: dict[str, Any]) -> None:
        counts = summary["counts"]
        self._load_roots(prefer=summary["root_path"])
        self._load_artists()
        self._offset = 0
        self._reload()
        self._log(
            "INFO",
            f"{summary['total']} file(s) in {summary['root_path']}: "
            f"{counts[STATUS_NEW]} new, {counts[STATUS_CLASH]} title clash(es), "
            f"{counts[STATUS_PROBABLE]} probable match(es), "
            f"{counts[STATUS_IN_DATABASE]} already in the database.",
        )
        if counts[STATUS_NEW]:
            self._log(
                "INFO",
                f"Set Show to New to list the {counts[STATUS_NEW]} file(s) the database "
                "has never seen.",
            )
        if counts[STATUS_CLASH]:
            self._log(
                "WARN",
                f"{counts[STATUS_CLASH]} file(s) share a title with a cached row but not a "
                "duration. Set Show to Title clash and read the comparison on the right.",
            )

    @pyqtSlot()
    def _reload(self) -> None:
        low, high = self._duration_bounds()
        if low and high and low > high:
            self.table.setRowCount(0)
            self._rows, self._total = [], 0
            self.count_label.setText("The shortest duration is longer than the longest one.")
            return
        try:
            self._rows, self._total = fetch_local_files(
                self._ctx.db_path,
                root_path=self._selected_root(),
                search=self.search_input.text(),
                status=self.status_select.currentText(),
                artist=self.artist_select.currentText(),
                min_duration=low,
                max_duration=high,
                only_untagged=self.untagged_box.isChecked(),
                sort_key=self._sort_key,
                descending=self._sort_descending,
                limit=self.page_size.value(),
                offset=self._offset,
            )
        except Exception as exc:
            self._rows, self._total = [], 0
            self.table.setRowCount(0)
            self.count_label.setText(f"Could not read the scan results: {exc}")
            return
        self._render()

    @pyqtSlot()
    def _reset_and_reload(self) -> None:
        self._offset = 0
        if self._loaded_once:
            self._reload()

    @pyqtSlot()
    def _on_root_changed(self) -> None:
        self._load_artists()
        self._reset_and_reload()
        self.forget_button.setEnabled(not self._busy and bool(self._selected_root()))

    @pyqtSlot(int)
    def _sort_by_column(self, column: int) -> None:
        """Clicking a heading re-runs the query. Clicking the same one flips the order."""
        if not 0 <= column < len(COLUMNS):
            return
        key = COLUMNS[column][1]
        if key == self._sort_key:
            self._sort_descending = not self._sort_descending
        else:
            self._sort_key = key
            # Sizes and times read best largest and newest first; names do not.
            self._sort_descending = key in {"duration", "bitrate", "modified_at", "first_seen_at"}
        self._offset = 0
        self._reload()

    @pyqtSlot()
    def _clear_filters(self) -> None:
        self.search_input.clear()
        self.artist_select.setCurrentText("")
        for widget in (self.min_minutes, self.max_minutes):
            widget.setValue(0)
        self.status_select.setCurrentIndex(0)
        self.untagged_box.setChecked(False)
        self._offset = 0
        self._reload()

    @pyqtSlot()
    def _previous_page(self) -> None:
        self._offset = max(0, self._offset - self.page_size.value())
        self._reload()

    @pyqtSlot()
    def _next_page(self) -> None:
        if self._offset + self.page_size.value() < self._total:
            self._offset += self.page_size.value()
            self._reload()

    @pyqtSlot()
    def _show_detail(self) -> None:
        rows = {index.row() for index in self.table.selectedIndexes()}
        if len(rows) != 1:
            return
        row_index = rows.pop()
        if 0 <= row_index < len(self._rows):
            self.detail_view.setPlainText(self._describe(self._rows[row_index]))

    @pyqtSlot()
    def _forget(self) -> None:
        root = self._selected_root()
        if not root:
            QMessageBox.information(
                self, "No folder chosen", "Pick one scanned folder before forgetting it."
            )
            return

        answer = QMessageBox.question(
            self,
            "Forget this folder",
            f"Remove the scan results for\n{root}\n\nfrom {self._ctx.db_path}.\n\n"
            "Only the scan record goes. No audio file is moved, changed or deleted, and "
            "nothing else in the database is touched. Scanning the folder again rebuilds it.",
            MB_YES | MB_NO,
            MB_NO,
        )
        if answer != MB_YES:
            self._log("INFO", "Forget cancelled. Nothing was removed.")
            return

        try:
            removed = forget_root(self._ctx.db_path, root)
        except Exception as exc:
            QMessageBox.critical(self, "Could not forget the folder", str(exc))
            self._log("ERR", f"Forget failed: {exc}")
            return

        self._log("INFO", f"Forgot {removed} scan row(s) for {root}. No file on disk was touched.")
        self._offset = 0
        self._load_roots()
        self._load_artists()
        self._reload()

    @pyqtSlot()
    def _cancel(self) -> None:
        if not self._busy or self._cancel_token is None:
            self._log("WARN", "No running scan to stop.")
            return
        self._cancel_token.cancel()
        self._log("INFO", "Stop requested. The files already read are still recorded.")

    @pyqtSlot(str)
    def _on_work_complete(self, summary: str) -> None:
        self._log("INFO", summary)
        self._set_busy(False)
        self._scan_worker = None
        self._cancel_token = None

    @pyqtSlot(str)
    def _on_work_failed(self, message: str) -> None:
        self._log("ERR", message)
        self._set_busy(False)
        self._scan_worker = None
        self._cancel_token = None
        QMessageBox.warning(self, "Scan failed", message)
