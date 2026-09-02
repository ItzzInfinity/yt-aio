"""Downloader panel.

Owns:   the Downloader tab.
Reads:  application/config/config.json through AppContext;
        the youtube_video_information cache in yt_aio.db.
Writes: downloads / errors / user_actions rows in yt_aio.db;
        media files under config["default_download_path"].
Runs:   yt-dlp, as a subprocess, through the shared runner in application/jobs.py
        (dev_guide.md 5, Pattern C).

Nothing here blocks or touches the filesystem during construction. The panel builds on
a machine with no yt-dlp, no database and no network; every failure that can happen is
reported when a button is pressed.
"""

from __future__ import annotations

from .... import APP_NAME, APP_VERSION
from ...context import AppContext
from ...jobs import TaskThread
from ...ui.qt import (
    ALIGN_TOP,
    CHECKED,
    HEADER_STRETCH,
    ITEM_FLAGS,
    NO_EDIT,
    ORIENTATION_HORIZONTAL,
    SELECT_ROWS,
    SIZE_EXPANDING,
    UNCHECKED,
    QButtonGroup,
    QDesktopServices,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QUrl,
    QVBoxLayout,
    QWidget,
    pyqtSlot,
)
from ...ui.widgets import ConsoleView
from ...utils.download_manager import record_user_action
from ...utils.shared import CancellationToken, DownloadTarget, VideoItem
from ...utils.video_info_extractor import parse_quick_download_urls


class DownloaderPanel(QWidget):
    """One tab. Constructed once at start-up and never destroyed."""

    def __init__(self, parent: QWidget | None = None, *, context: AppContext) -> None:
        super().__init__(parent)

        # ---- 1. state first, so no slot can ever see a missing attribute
        self._ctx = context
        self._busy = False
        self._worker: TaskThread | None = None
        self._cancel_token: CancellationToken | None = None
        self._items: list[VideoItem] = []
        self._loaded_key: tuple[str, str] | None = None
        self._loaded_source_name = ""

        # ---- 2. create every widget before anything is connected
        self.log_output = ConsoleView()

        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("Channel handle / channel ID / playlist ID / full URL")
        self.channel_radio = QRadioButton("Channel")
        self.playlist_radio = QRadioButton("Playlist")
        self.audio_radio = QRadioButton("Audio")
        self.video_radio = QRadioButton("Video")
        self.channel_radio.setChecked(True)
        self.audio_radio.setChecked(True)

        self.status_label = QLabel()
        self.busy_bar = QProgressBar()
        self.busy_bar.setTextVisible(False)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Select", "ID", "Name", "Duration", "Bitrate", "Channel/Playlist"]
        )
        self.table.setSelectionBehavior(SELECT_ROWS)
        self.table.setEditTriggers(NO_EDIT)
        self.table.setAlternatingRowColors(True)
        self.table.setSizePolicy(SIZE_EXPANDING, SIZE_EXPANDING)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(2, HEADER_STRETCH)
        header.setSectionResizeMode(5, HEADER_STRETCH)

        self.quick_download_box = QTextEdit()
        self.quick_download_box.setPlaceholderText(
            "https://www.youtube.com/watch?v=ID1, https://www.youtube.com/watch?v=ID2"
        )

        self.download_button = QPushButton("Download")
        self.stop_button = QPushButton("Stop")
        self.clear_button = QPushButton("Clear")
        self.config_button = QPushButton("Config")

        # ---- 3. layout
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Log"))
        left_layout.addWidget(self.log_output)

        source_box = QGroupBox("Source")
        source_layout = QGridLayout(source_box)
        source_layout.addWidget(QLabel("Channel or Playlist"), 0, 0)
        source_layout.addWidget(self.source_input, 0, 1, 1, 3)
        source_layout.addWidget(self.channel_radio, 1, 1)
        source_layout.addWidget(self.playlist_radio, 1, 2)
        source_layout.addWidget(self.audio_radio, 1, 3)
        source_layout.addWidget(self.video_radio, 1, 4)

        self._source_group = QButtonGroup(self)
        self._source_group.addButton(self.channel_radio)
        self._source_group.addButton(self.playlist_radio)
        self._media_group = QButtonGroup(self)
        self._media_group.addButton(self.audio_radio)
        self._media_group.addButton(self.video_radio)

        status_box = QGroupBox("Task Status")
        status_layout = QVBoxLayout(status_box)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.busy_bar)

        quick_box = QGroupBox("Quick Download")
        quick_layout = QVBoxLayout(quick_box)
        quick_layout.addWidget(
            QLabel("Comma-separated full links. Use NULL or leave empty to ignore this box.")
        )
        quick_layout.addWidget(self.quick_download_box)

        button_row = QHBoxLayout()
        button_row.addWidget(self.download_button)
        button_row.addWidget(self.stop_button)
        button_row.addWidget(self.clear_button)
        button_row.addWidget(self.config_button)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setAlignment(ALIGN_TOP)
        right_layout.addWidget(source_box)
        right_layout.addWidget(status_box)
        right_layout.addWidget(self.table)
        right_layout.addWidget(quick_box)
        right_layout.addLayout(button_row)

        splitter = QSplitter(ORIENTATION_HORIZONTAL)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([420, 900])

        root_layout = QHBoxLayout(self)
        root_layout.addWidget(splitter)

        # ---- 4. signals, only now that every widget exists
        self.download_button.clicked.connect(self._start)
        self.stop_button.clicked.connect(self._cancel)
        self.clear_button.clicked.connect(self._clear_log)
        self.config_button.clicked.connect(self._open_config)

        # ---- 5. initial UI state
        self._set_busy(False)
        self._log("INFO", f"{APP_NAME} {APP_VERSION} ready. Config: {self._ctx.config_path}")

    # ------------------------------------------------------------------ shell hook
    def shutdown(self) -> None:
        """Called by the shell on close. Safe to call while idle."""
        if self._cancel_token is not None:
            self._cancel_token.cancel()
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(5000)

    # ------------------------------------------------------------------ helpers
    def _log(self, tag: str, text: str) -> None:
        self.log_output.log(tag, text)

    def append_log(self, message: str) -> None:
        """Sink for the worker's log_message signal. Those lines are already tagged."""
        self.log_output.append_raw(message)

    def _set_busy(self, busy: bool, *, status: str = "", button_text: str = "Download") -> None:
        """Single place where enablement is decided. Every terminal path calls this."""
        self._busy = busy
        if status:
            self.status_label.setText(status)
        if busy:
            self.busy_bar.setRange(0, 0)
        else:
            self.busy_bar.setRange(0, 1)
            self.busy_bar.setValue(0)

        self.download_button.setText(button_text)
        self.download_button.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        self.clear_button.setEnabled(not busy)
        self.config_button.setEnabled(not busy)
        self.source_input.setEnabled(not busy)
        self.channel_radio.setEnabled(not busy)
        self.playlist_radio.setEnabled(not busy)
        self.audio_radio.setEnabled(not busy)
        self.video_radio.setEnabled(not busy)
        self.table.setEnabled(not busy)
        self.quick_download_box.setReadOnly(busy)

    def _current_source_kind(self) -> str:
        return "playlist" if self.playlist_radio.isChecked() else "channel"

    def _current_media_type(self) -> str:
        return "video" if self.video_radio.isChecked() else "audio"

    def _selected_items(self) -> list[VideoItem]:
        selected: list[VideoItem] = []
        for row, item in enumerate(self._items):
            checkbox_item = self.table.item(row, 0)
            if checkbox_item and checkbox_item.checkState() == CHECKED:
                selected.append(item)
        return selected

    def _populate_table(self, items: list[VideoItem]) -> None:
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            checkbox = QTableWidgetItem()
            checkbox.setFlags(ITEM_FLAGS)
            checkbox.setCheckState(UNCHECKED)
            self.table.setItem(row, 0, checkbox)
            self.table.setItem(row, 1, QTableWidgetItem(item.video_id))
            self.table.setItem(row, 2, QTableWidgetItem(item.title))
            self.table.setItem(row, 3, QTableWidgetItem(item.duration_label))
            self.table.setItem(row, 4, QTableWidgetItem(item.available_bitrate))
            self.table.setItem(row, 5, QTableWidgetItem(item.channel_name or item.source_name))
        self.table.resizeRowsToContents()
        self._log("INFO", f"Table updated with {len(items)} rows.")

    def _attach_worker(self, worker: TaskThread) -> None:
        worker.log_message.connect(self.append_log)
        worker.load_complete.connect(self._on_load_complete)
        worker.work_complete.connect(self._on_work_complete)
        worker.work_failed.connect(self._on_work_failed)

    # ------------------------------------------------------------------- slots
    @pyqtSlot()
    def _start(self) -> None:
        if self._busy:
            self._log("WARN", "A task is already running.")
            return

        self._ctx.reload_if_changed(self._log)
        record_user_action(self._ctx.db_path, "start")

        quick_urls, invalid_urls = parse_quick_download_urls(self.quick_download_box.toPlainText())
        for invalid_url in invalid_urls:
            self._log("WARN", f"Invalid URL skipped: {invalid_url}")

        if quick_urls:
            self._start_download([DownloadTarget(url=url) for url in quick_urls], "Quick Download")
            return

        source_value = self.source_input.text().strip()
        source_kind = self._current_source_kind()

        if not source_value:
            self._log("WARN", "Enter a channel or playlist value, or provide quick-download URLs.")
            return

        if self._items and self._loaded_key == (source_kind, source_value):
            selected_items = self._selected_items()
            if not selected_items:
                self._log("WARN", "Select at least one loaded item to download.")
                return
            targets = [
                DownloadTarget(
                    url=item.url,
                    title=item.title,
                    video_id=item.video_id,
                    video_info_id=item.video_info_id,
                    source_id=item.source_id,
                )
                for item in selected_items
            ]
            self._start_download(targets, self._loaded_source_name or source_value)
            return

        self._start_load(source_kind, source_value)

    def _start_load(self, source_kind: str, source_value: str) -> None:
        self._cancel_token = CancellationToken()
        self._set_busy(
            True,
            status=f"Loading {source_kind} listing. Please wait...",
            button_text="Loading...",
        )
        self._worker = TaskThread(
            "load",
            self._ctx.config,
            self._ctx.db_path,
            self._cancel_token,
            source_kind=source_kind,
            source_value=source_value,
        )
        self._attach_worker(self._worker)
        self._log("TX", f"Fetching listing for {source_kind}: {source_value}")
        self._worker.start()

    def _start_download(self, targets: list[DownloadTarget], source_name: str) -> None:
        media_type = self._current_media_type()
        self._cancel_token = CancellationToken()
        self._set_busy(
            True,
            status=f"Downloading {len(targets)} item(s).",
            button_text="Downloading...",
        )
        self._worker = TaskThread(
            "download",
            self._ctx.config,
            self._ctx.db_path,
            self._cancel_token,
            media_type=media_type,
            targets=targets,
            source_name=source_name,
        )
        self._attach_worker(self._worker)
        self._log("TX", f"Starting {media_type} download for {len(targets)} item(s).")
        self._worker.start()

    @pyqtSlot(object, str, str, str)
    def _on_load_complete(
        self, items: list[VideoItem], source_name: str, source_kind: str, source_value: str
    ) -> None:
        self._items = items
        self._loaded_key = (source_kind, source_value)
        self._loaded_source_name = source_name
        self._populate_table(items)

    @pyqtSlot(str)
    def _on_work_complete(self, summary: str) -> None:
        self._log("INFO", summary)
        self._set_busy(False, status=summary)
        self._worker = None
        self._cancel_token = None

    @pyqtSlot(str)
    def _on_work_failed(self, message: str) -> None:
        self._log("ERR", f"Task failed: {message}")
        self._set_busy(False, status=f"Failed: {message}")
        self._worker = None
        self._cancel_token = None
        QMessageBox.warning(self, APP_NAME, message)

    @pyqtSlot()
    def _cancel(self) -> None:
        if not self._busy or self._cancel_token is None:
            self._log("WARN", "No running task to stop.")
            return
        record_user_action(self._ctx.db_path, "stop")
        self._cancel_token.cancel()
        self.status_label.setText("Stopping current task...")
        self._log("INFO", "Stop requested.")

    @pyqtSlot()
    def _clear_log(self) -> None:
        if self._busy:
            self._log("WARN", "Cannot clear the log while a task is running.")
            return
        record_user_action(self._ctx.db_path, "clear")
        self.log_output.clear()

    @pyqtSlot()
    def _open_config(self) -> None:
        if self._busy:
            self._log("WARN", "Cannot open the config while a task is running.")
            return

        record_user_action(self._ctx.db_path, "open config")
        self._ctx.reload_if_changed(self._log)

        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._ctx.config_path)))
        if opened:
            self._log("INFO", f"Opened config: {self._ctx.config_path}")
        else:
            self._log("WARN", f"Could not open the config automatically: {self._ctx.config_path}")
