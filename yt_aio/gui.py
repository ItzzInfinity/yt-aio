from __future__ import annotations

import json
import sys
from pathlib import Path

from . import APP_NAME, APP_VERSION
from .config import CONFIG_PATH, ensure_config, load_config
from .logging_db import init_db, log_setting_change
from .services import (
    CancellationToken,
    DownloadTarget,
    VideoItem,
    download_many,
    list_videos,
    now_string,
    parse_quick_download_urls,
    record_user_action,
)

try:
    from PyQt6.QtCore import QThread, Qt, QUrl, pyqtSignal as Signal
    from PyQt6.QtGui import QDesktopServices
    from PyQt6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QButtonGroup,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QRadioButton,
        QSizePolicy,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    QT_API = "PyQt6"
except ImportError:
    from PyQt5.QtCore import QThread, Qt, QUrl, pyqtSignal as Signal
    from PyQt5.QtGui import QDesktopServices
    from PyQt5.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QButtonGroup,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QRadioButton,
        QSizePolicy,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    QT_API = "PyQt5"


if QT_API == "PyQt6":
    CHECKED = Qt.CheckState.Checked
    UNCHECKED = Qt.CheckState.Unchecked
    ITEM_FLAGS = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable
    ALIGN_TOP = Qt.AlignmentFlag.AlignTop
    ORIENTATION_HORIZONTAL = Qt.Orientation.Horizontal
    SELECT_ROWS = QAbstractItemView.SelectionBehavior.SelectRows
    NO_EDIT = QAbstractItemView.EditTrigger.NoEditTriggers
else:
    CHECKED = Qt.Checked
    UNCHECKED = Qt.Unchecked
    ITEM_FLAGS = Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable
    ALIGN_TOP = Qt.AlignTop
    ORIENTATION_HORIZONTAL = Qt.Horizontal
    SELECT_ROWS = QAbstractItemView.SelectRows
    NO_EDIT = QAbstractItemView.NoEditTriggers


class TaskThread(QThread):
    log_message = Signal(str)
    load_complete = Signal(object, str)
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
                assert self.source_kind is not None
                assert self.source_value is not None
                items, source_name = list_videos(
                    self.source_kind,
                    self.source_value,
                    self.config,
                    self.db_path,
                    self._emit,
                    self.token,
                )
                self.load_complete.emit(items, source_name)
                self.work_complete.emit(f"Loaded {len(items)} items.")
                return

            if self.action == "download":
                assert self.media_type is not None
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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config_path = ensure_config(CONFIG_PATH)
        self.config = load_config(self.config_path)
        self.db_path = str(Path(self.config["log_file_path"]).expanduser())
        init_db(self.db_path)

        self.worker: TaskThread | None = None
        self.cancel_token: CancellationToken | None = None
        self.current_items: list[VideoItem] = []
        self.loaded_key: tuple[str, str] | None = None
        self.loaded_source_name = ""

        # self.setWindowTitle(f"{APP_NAME} GUI ({QT_API})")
        self.setWindowTitle(f"{APP_NAME} — ItzzInfinity")
        self.resize(1320, 860)
        self._build_ui()
        self.append_log(f"[{now_string()}] {APP_NAME} {APP_VERSION} ready. Config: {self.config_path}")

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        splitter = QSplitter(ORIENTATION_HORIZONTAL)
        root_layout.addWidget(splitter)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Log"))

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap if QT_API == "PyQt6" else QPlainTextEdit.NoWrap)
        left_layout.addWidget(self.log_output)
        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setAlignment(ALIGN_TOP)

        input_group = QGroupBox("Source")
        input_layout = QGridLayout(input_group)
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("Channel handle / channel ID / playlist ID / full URL")
        input_layout.addWidget(QLabel("Channel or Playlist"), 0, 0)
        input_layout.addWidget(self.source_input, 0, 1, 1, 3)

        self.channel_radio = QRadioButton("Channel")
        self.playlist_radio = QRadioButton("Playlist")
        self.channel_radio.setChecked(True)
        source_group = QButtonGroup(self)
        source_group.addButton(self.channel_radio)
        source_group.addButton(self.playlist_radio)
        input_layout.addWidget(self.channel_radio, 1, 1)
        input_layout.addWidget(self.playlist_radio, 1, 2)

        self.audio_radio = QRadioButton("Audio")
        self.video_radio = QRadioButton("Video")
        self.audio_radio.setChecked(True)
        media_group = QButtonGroup(self)
        media_group.addButton(self.audio_radio)
        media_group.addButton(self.video_radio)
        input_layout.addWidget(self.audio_radio, 1, 3)
        input_layout.addWidget(self.video_radio, 1, 4)

        right_layout.addWidget(input_group)

        status_group = QGroupBox("Task Status")
        status_layout = QVBoxLayout(status_group)
        self.status_label = QLabel()
        self.busy_bar = QProgressBar()
        self.busy_bar.setTextVisible(False)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.busy_bar)
        right_layout.addWidget(status_group)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Select", "ID", "Name", "Duration", "Bitrate", "Channel/Playlist"]
        )
        self.table.setSelectionBehavior(SELECT_ROWS)
        self.table.setEditTriggers(NO_EDIT)
        self.table.setAlternatingRowColors(True)
        if QT_API == "PyQt6":
            self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        else:
            self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        header = self.table.horizontalHeader()
        try:
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        except AttributeError:
            header.setSectionResizeMode(2, QHeaderView.Stretch)
            header.setSectionResizeMode(5, QHeaderView.Stretch)
        right_layout.addWidget(self.table)

        quick_group = QGroupBox("Quick Download")
        quick_layout = QVBoxLayout(quick_group)
        quick_layout.addWidget(QLabel("Comma-separated full links. Use NULL or leave empty to ignore this box."))
        self.quick_download_box = QTextEdit()
        self.quick_download_box.setPlaceholderText(
            "https://www.youtube.com/watch?v=ID1, https://www.youtube.com/watch?v=ID2"
        )
        quick_layout.addWidget(self.quick_download_box)
        right_layout.addWidget(quick_group)

        button_row = QHBoxLayout()
        self.download_button = QPushButton("Download")
        self.stop_button = QPushButton("Stop")
        self.clear_button = QPushButton("Clear")
        self.config_button = QPushButton("Config")
        button_row.addWidget(self.download_button)
        button_row.addWidget(self.stop_button)
        button_row.addWidget(self.clear_button)
        button_row.addWidget(self.config_button)
        right_layout.addLayout(button_row)

        splitter.addWidget(right_panel)
        splitter.setSizes([420, 900])

        self.download_button.clicked.connect(self.on_download_clicked)
        self.stop_button.clicked.connect(self.on_stop_clicked)
        self.clear_button.clicked.connect(self.on_clear_clicked)
        self.config_button.clicked.connect(self.on_config_clicked)
        self.set_idle_state("Idle. First click loads a channel or playlist; next click downloads selected rows.")

    def append_log(self, message: str) -> None:
        self.log_output.appendPlainText(message)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def is_busy(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def set_busy_state(self, message: str, button_text: str) -> None:
        self.status_label.setText(message)
        self.busy_bar.setRange(0, 0)
        self.download_button.setText(button_text)
        self.download_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.clear_button.setEnabled(False)
        self.config_button.setEnabled(False)
        self.source_input.setEnabled(False)
        self.channel_radio.setEnabled(False)
        self.playlist_radio.setEnabled(False)
        self.audio_radio.setEnabled(False)
        self.video_radio.setEnabled(False)
        self.quick_download_box.setReadOnly(True)

    def set_idle_state(self, message: str) -> None:
        self.status_label.setText(message)
        self.busy_bar.setRange(0, 1)
        self.busy_bar.setValue(0)
        self.download_button.setText("Download")
        self.download_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.clear_button.setEnabled(True)
        self.config_button.setEnabled(True)
        self.source_input.setEnabled(True)
        self.channel_radio.setEnabled(True)
        self.playlist_radio.setEnabled(True)
        self.audio_radio.setEnabled(True)
        self.video_radio.setEnabled(True)
        self.quick_download_box.setReadOnly(False)

    def current_source_kind(self) -> str:
        return "playlist" if self.playlist_radio.isChecked() else "channel"

    def current_media_type(self) -> str:
        return "video" if self.video_radio.isChecked() else "audio"

    def on_download_clicked(self) -> None:
        if self.is_busy():
            self.append_log(f"[{now_string()}] A task is already running.")
            return

        self.reload_config_if_changed()
        record_user_action(self.db_path, "start")
        quick_urls, invalid_urls = parse_quick_download_urls(self.quick_download_box.toPlainText())
        for invalid_url in invalid_urls:
            self.append_log(f"[{now_string()}] Invalid URL skipped: {invalid_url}")

        if quick_urls:
            quick_targets = [DownloadTarget(url=url) for url in quick_urls]
            self.start_download(quick_targets, "Quick Download")
            return

        source_value = self.source_input.text().strip()
        source_kind = self.current_source_kind()
        current_key = (source_kind, source_value)

        if not source_value:
            self.append_log(
                f"[{now_string()}] Enter a channel/playlist value or provide quick-download URLs."
            )
            return

        if self.current_items and self.loaded_key == current_key:
            selected_items = self.get_selected_items()
            if not selected_items:
                self.append_log(f"[{now_string()}] Select at least one loaded item to download.")
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
            self.start_download(targets, self.loaded_source_name or source_value)
            return

        self.start_load(source_kind, source_value)

    def start_load(self, source_kind: str, source_value: str) -> None:
        self.cancel_token = CancellationToken()
        self.set_busy_state(
            f"Loading {source_kind} listing. Please wait...",
            "Loading...",
        )
        self.worker = TaskThread(
            "load",
            self.config,
            self.db_path,
            self.cancel_token,
            source_kind=source_kind,
            source_value=source_value,
        )
        self.attach_worker()
        self.append_log(f"[{now_string()}] Fetching listing for {source_kind}: {source_value}")
        self.worker.start()

    def start_download(self, targets: list[DownloadTarget], source_name: str) -> None:
        self.cancel_token = CancellationToken()
        self.set_busy_state(
            f"Downloading {len(targets)} item(s).",
            "Downloading...",
        )
        self.worker = TaskThread(
            "download",
            self.config,
            self.db_path,
            self.cancel_token,
            media_type=self.current_media_type(),
            targets=targets,
            source_name=source_name,
        )
        self.attach_worker()
        self.append_log(
            f"[{now_string()}] Starting {self.current_media_type()} download for {len(targets)} item(s)."
        )
        self.worker.start()

    def attach_worker(self) -> None:
        assert self.worker is not None
        self.worker.log_message.connect(self.append_log)
        self.worker.load_complete.connect(self.on_load_complete)
        self.worker.work_complete.connect(self.on_work_complete)
        self.worker.work_failed.connect(self.on_work_failed)

    def on_load_complete(self, items: list[VideoItem], source_name: str) -> None:
        source_kind = self.current_source_kind()
        source_value = self.source_input.text().strip()
        self.current_items = items
        self.loaded_key = (source_kind, source_value)
        self.loaded_source_name = source_name
        self.populate_table(items)

    def on_work_complete(self, summary: str) -> None:
        self.append_log(f"[{now_string()}] {summary}")
        self.set_idle_state(summary)
        self.worker = None
        self.cancel_token = None

    def on_work_failed(self, message: str) -> None:
        self.append_log(f"[{now_string()}] Task failed: {message}")
        self.set_idle_state(f"Failed: {message}")
        QMessageBox.warning(self, APP_NAME, message)
        self.worker = None
        self.cancel_token = None

    def get_selected_items(self) -> list[VideoItem]:
        selected: list[VideoItem] = []
        for row, item in enumerate(self.current_items):
            checkbox_item = self.table.item(row, 0)
            if checkbox_item and checkbox_item.checkState() == CHECKED:
                selected.append(item)
        return selected

    def populate_table(self, items: list[VideoItem]) -> None:
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
        self.append_log(f"[{now_string()}] Table updated with {len(items)} rows.")

    def on_stop_clicked(self) -> None:
        if not self.is_busy() or self.cancel_token is None:
            self.append_log(f"[{now_string()}] No running task to stop.")
            return
        record_user_action(self.db_path, "stop")
        self.cancel_token.cancel()
        self.status_label.setText("Stopping current task...")
        self.append_log(f"[{now_string()}] Stop requested.")

    def on_clear_clicked(self) -> None:
        if self.is_busy():
            self.append_log(f"[{now_string()}] Cannot clear the log while a task is running.")
            return
        record_user_action(self.db_path, "clear")
        self.log_output.clear()

    def on_config_clicked(self) -> None:
        if self.is_busy():
            self.append_log(f"[{now_string()}] Cannot open the config while a task is running.")
            return

        record_user_action(self.db_path, "open config")
        self.reload_config_if_changed()

        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.config_path)))
        if opened:
            self.append_log(f"[{now_string()}] Opened config: {self.config_path}")
        else:
            self.append_log(f"[{now_string()}] Could not open config automatically: {self.config_path}")

    def reload_config_if_changed(self) -> None:
        try:
            previous_config = self.config
            latest_config = load_config(self.config_path)
        except Exception as exc:
            self.append_log(f"[{now_string()}] Failed to reload config: {exc}")
            return

        if json.dumps(previous_config, sort_keys=True) == json.dumps(latest_config, sort_keys=True):
            self.config = latest_config
            return

        changed_keys = sorted(set(previous_config) | set(latest_config))
        for key in changed_keys:
            old_value = previous_config.get(key)
            new_value = latest_config.get(key)
            if old_value == new_value:
                continue
            log_setting_change(
                self.db_path,
                key,
                json.dumps(old_value),
                json.dumps(new_value),
                now_string(),
            )
            self.append_log(
                f"[{now_string()}] Config changed: {key} = {json.dumps(new_value)}"
            )

        self.config = latest_config
        self.db_path = str(Path(self.config["log_file_path"]).expanduser())
        init_db(self.db_path)


def main() -> int:
    ensure_config(CONFIG_PATH)

    try:
        app = QApplication(sys.argv)
    except Exception as exc:
        print(f"Failed to start Qt application: {exc}", file=sys.stderr)
        return 1

    window = MainWindow()
    window.show()

    if QT_API == "PyQt6":
        return app.exec()
    return app.exec_()
