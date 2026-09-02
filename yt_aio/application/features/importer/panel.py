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
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

from ...context import AppContext
from ...db.queries import import_video_rows
from ...jobs import CallableThread, TaskThread
from ...ui.qt import (
    CHECKED,
    ITEM_FLAGS,
    NO_EDIT,
    ORIENTATION_HORIZONTAL,
    SELECT_ROWS,
    UNCHECKED,
    USER_ROLE,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
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
from .parsers import ImportedItem, parse_backup_file

HEADERS = ["", "Video ID", "Title", "Channel", "Duration", "URL"]
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

        self.table = RecordTable(HEADERS)
        self.table.setSelectionBehavior(SELECT_ROWS)
        self.table.setEditTriggers(NO_EDIT)

        self.select_all_box = QCheckBox("Select all")
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

        self._media_group = QButtonGroup(self)
        self._media_group.addButton(self.audio_radio)
        self._media_group.addButton(self.video_radio)

        action_row = QHBoxLayout()
        action_row.addWidget(self.select_all_box)
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

        # ---- 5. initial state
        self._set_busy(False)
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
        has_items = bool(self._items)
        self.file_input.setEnabled(not busy)
        self.browse_button.setEnabled(not busy)
        self.parse_button.setEnabled(not busy)
        self.table.setEnabled(not busy)
        self.select_all_box.setEnabled(not busy and has_items)
        self.audio_radio.setEnabled(not busy)
        self.video_radio.setEnabled(not busy)
        self.merge_button.setEnabled(not busy and has_items)
        self.download_button.setEnabled(not busy and has_items)
        self.stop_button.setEnabled(busy)

    def _checked_items(self) -> list[ImportedItem]:
        checked = []
        for row_index, item in enumerate(self._items):
            box = self.table.item(row_index, 0)
            if box is not None and box.checkState() == CHECKED:
                checked.append(item)
        return checked

    def _render(self) -> None:
        self.table.setRowCount(len(self._items))
        for row_index, item in enumerate(self._items):
            box = QTableWidgetItem()
            box.setFlags(ITEM_FLAGS)
            box.setCheckState(CHECKED)
            box.setData(USER_ROLE, item.video_id)
            self.table.setItem(row_index, 0, box)
            cells = [
                item.video_id,
                item.display_title,
                item.channel_name,
                format_duration(item.duration_seconds),
                item.url,
            ]
            for column_index, text in enumerate(cells, start=1):
                self.table.setItem(row_index, column_index, QTableWidgetItem(str(text)))
        self.table.resizeColumnsToContents()
        self.select_all_box.blockSignals(True)
        self.select_all_box.setChecked(bool(self._items))
        self.select_all_box.blockSignals(False)

    def _attach(self, worker) -> None:
        worker.log_message.connect(self.append_log)
        worker.work_complete.connect(self._on_work_complete)
        worker.work_failed.connect(self._on_work_failed)

    # ------------------------------------------------------------------- slots
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
        self.format_label.setText(
            f"Detected {label}. {len(self._items)} unique video(s) from {self._source_label}."
        )
        self._render()
        self._log("INFO", f"Detected {label}: {len(self._items)} unique video(s).")

    @pyqtSlot(bool)
    def _toggle_all(self, checked: bool) -> None:
        state = CHECKED if checked else UNCHECKED
        for row_index in range(self.table.rowCount()):
            box = self.table.item(row_index, 0)
            if box is not None:
                box.setCheckState(state)

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
