"""Library panel.

Owns:   the Library tab.
Reads:  youtube_video_information joined against downloads and sources, through
        application/db/queries.py.
Writes: deletes the cached rows the operator selected, and clears the download rows'
        link to them. The download history itself is never destroyed.
Runs:   nothing (dev_guide.md 5, Pattern E).

The cache is the large table in this database, so every read is paged and filtered in
SQL. Nothing here loads the whole table into memory.
"""

from __future__ import annotations

from typing import Any

from ...context import AppContext
from ...db.queries import database_stats, delete_videos, fetch_sources, fetch_videos
from ...ui.qt import (
    CHECKED,
    ITEM_FLAGS,
    MB_NO,
    MB_YES,
    NO_EDIT,
    SELECT_ROWS,
    UNCHECKED,
    USER_ROLE,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    pyqtSlot,
)
from ...ui.widgets import RecordTable, muted
from ...utils.video_info_extractor import format_duration

HEADERS = ["", "Video ID", "Title", "Channel", "Duration", "Uploaded", "Cached", "Metadata", "Downloads"]
COMPLETENESS = {
    "Everything": "all",
    "Full metadata only": "full",
    "Partial metadata only": "partial",
    "Downloaded": "downloaded",
    "Never downloaded": "never downloaded",
}


class LibraryPanel(QWidget):
    """One tab. Constructed once at start-up and never destroyed."""

    def __init__(self, parent: QWidget | None = None, *, context: AppContext) -> None:
        super().__init__(parent)

        # ---- 1. state
        self._ctx = context
        self._rows: list[dict[str, Any]] = []
        self._sources: list[dict[str, Any]] = []
        self._offset = 0
        self._total = 0
        self._loaded_once = False

        # ---- 2. widgets
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Title, video ID, channel or playlist")
        self.source_select = QComboBox()
        self.completeness_select = QComboBox()
        self.completeness_select.addItems(list(COMPLETENESS))
        self.page_size = QSpinBox()
        self.page_size.setRange(10, 2000)
        self.page_size.setSingleStep(50)
        self.page_size.setValue(200)
        self.refresh_button = QPushButton("Refresh")

        self.select_all_box = QCheckBox("Select all on this page")
        self.delete_button = QPushButton("Delete selected")
        self.prev_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        self.count_label = muted("Not loaded yet.")
        self.stats_label = muted("")

        self.table = RecordTable(HEADERS)
        self.table.setSelectionBehavior(SELECT_ROWS)
        self.table.setEditTriggers(NO_EDIT)

        # ---- 3. layout
        filter_box = QGroupBox("Filters")
        filter_row = QHBoxLayout(filter_box)
        filter_row.addWidget(QLabel("Search"))
        filter_row.addWidget(self.search_input, 1)
        filter_row.addWidget(QLabel("Source"))
        filter_row.addWidget(self.source_select)
        filter_row.addWidget(QLabel("Show"))
        filter_row.addWidget(self.completeness_select)
        filter_row.addWidget(QLabel("Rows"))
        filter_row.addWidget(self.page_size)
        filter_row.addWidget(self.refresh_button)

        action_row = QHBoxLayout()
        action_row.addWidget(self.select_all_box)
        action_row.addWidget(self.delete_button)
        action_row.addStretch(1)
        action_row.addWidget(self.prev_button)
        action_row.addWidget(self.next_button)
        action_row.addWidget(self.count_label)

        root = QVBoxLayout(self)
        root.addWidget(filter_box)
        root.addWidget(self.table, 1)
        root.addLayout(action_row)
        root.addWidget(self.stats_label)

        # ---- 4. signals
        self.refresh_button.clicked.connect(self._reload)
        self.search_input.returnPressed.connect(self._reset_and_reload)
        self.source_select.currentIndexChanged.connect(self._reset_and_reload)
        self.completeness_select.currentTextChanged.connect(self._reset_and_reload)
        self.page_size.valueChanged.connect(self._reset_and_reload)
        self.select_all_box.toggled.connect(self._toggle_all)
        self.delete_button.clicked.connect(self._delete_selected)
        self.prev_button.clicked.connect(self._previous_page)
        self.next_button.clicked.connect(self._next_page)

        # ---- 5. initial state. The first read waits for the first paint, so the
        # constructor never touches the database.
        self.delete_button.setEnabled(False)
        self._update_page_buttons()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().showEvent(event)
        if not self._loaded_once:
            self._loaded_once = True
            self._load_sources()
            self._reload()

    # ------------------------------------------------------------------ helpers
    def _load_sources(self) -> None:
        try:
            self._sources = fetch_sources(self._ctx.db_path)
        except Exception:
            self._sources = []
        self.source_select.blockSignals(True)
        self.source_select.clear()
        self.source_select.addItem("Any source", None)
        for source in self._sources:
            label = source.get("source_name") or source.get("source_value") or f"#{source['id']}"
            kind = source.get("source_kind") or ""
            self.source_select.addItem(f"{label} [{kind}]" if kind else str(label), source["id"])
        self.source_select.blockSignals(False)

    def _selected_source_id(self) -> int | None:
        return self.source_select.currentData()

    def _update_page_buttons(self) -> None:
        self.prev_button.setEnabled(self._offset > 0)
        self.next_button.setEnabled(self._offset + self.page_size.value() < self._total)

    def _checked_rows(self) -> list[dict[str, Any]]:
        checked = []
        for row_index, record in enumerate(self._rows):
            box = self.table.item(row_index, 0)
            if box is not None and box.checkState() == CHECKED:
                checked.append(record)
        return checked

    def _render(self) -> None:
        self.table.setRowCount(len(self._rows))
        for row_index, record in enumerate(self._rows):
            box = QTableWidgetItem()
            box.setFlags(ITEM_FLAGS)
            box.setCheckState(UNCHECKED)
            box.setData(USER_ROLE, record.get("id"))
            self.table.setItem(row_index, 0, box)

            cells = [
                record.get("video_id") or "",
                record.get("title") or "",
                record.get("channel_name") or record.get("playlist_name") or "",
                format_duration(record.get("duration")),
                record.get("upload_date") or "",
                record.get("cached_at") or "",
                "Full" if record.get("is_full_metadata") else "Partial",
                str(record.get("download_count") or 0),
            ]
            for column_index, text in enumerate(cells, start=1):
                self.table.setItem(row_index, column_index, QTableWidgetItem(str(text)))

        self.table.resizeColumnsToContents()
        first = 0 if not self._rows else self._offset + 1
        last = self._offset + len(self._rows)
        self.count_label.setText(
            f"Showing {first}-{last} of {self._total}" if self._total else "No rows match these filters."
        )
        self.select_all_box.blockSignals(True)
        self.select_all_box.setChecked(False)
        self.select_all_box.blockSignals(False)
        self.delete_button.setEnabled(False)
        self._update_page_buttons()

    def _refresh_stats(self) -> None:
        try:
            stats = database_stats(self._ctx.db_path)
        except Exception as exc:
            self.stats_label.setText(f"Could not read the database summary: {exc}")
            return
        self.stats_label.setText(
            f"Database: {stats['youtube_video_information']} cached videos, "
            f"{stats['downloads']} downloads, {stats['sources']} sources. {self._ctx.db_path}"
        )

    # ------------------------------------------------------------------- slots
    @pyqtSlot()
    def _reload(self) -> None:
        try:
            self._rows, self._total = fetch_videos(
                self._ctx.db_path,
                search=self.search_input.text(),
                source_id=self._selected_source_id(),
                completeness=COMPLETENESS[self.completeness_select.currentText()],
                limit=self.page_size.value(),
                offset=self._offset,
            )
        except Exception as exc:
            self._rows, self._total = [], 0
            self.table.setRowCount(0)
            self.count_label.setText(f"Could not read the library: {exc}")
            return
        self._render()
        self._refresh_stats()

    @pyqtSlot()
    def _reset_and_reload(self) -> None:
        self._offset = 0
        if self._loaded_once:
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

    @pyqtSlot(bool)
    def _toggle_all(self, checked: bool) -> None:
        state = CHECKED if checked else UNCHECKED
        for row_index in range(self.table.rowCount()):
            box = self.table.item(row_index, 0)
            if box is not None:
                box.setCheckState(state)
        self.delete_button.setEnabled(bool(self._checked_rows()))

    @pyqtSlot()
    def _delete_selected(self) -> None:
        selected = self._checked_rows()
        if not selected:
            QMessageBox.information(self, "Nothing selected", "Tick the rows you want to remove.")
            return

        # Confirm with specifics: name the targets, cap the list, state the count and
        # say what cannot be undone (dev_guide.md 12).
        preview = "\n".join(f"  {row.get('video_id')}  {row.get('title') or ''}"[:110] for row in selected[:12])
        if len(selected) > 12:
            preview += f"\n  ... and {len(selected) - 12} more"
        answer = QMessageBox.question(
            self,
            "Delete cached rows",
            f"Remove {len(selected)} cached video row(s) from\n{self._ctx.db_path}\n\n"
            f"{preview}\n\n"
            "The download history is kept, but its link to these rows is cleared.\n"
            "Downloaded files on disk are not touched. This cannot be undone.",
            MB_YES | MB_NO,
            MB_NO,
        )
        if answer != MB_YES:
            self.stats_label.setText("Delete cancelled. Nothing was removed.")
            return

        try:
            removed = delete_videos(self._ctx.db_path, [int(row["id"]) for row in selected])
        except Exception as exc:
            QMessageBox.critical(self, "Delete failed", str(exc))
            self.stats_label.setText(f"Delete failed: {exc}")
            return

        self.stats_label.setText(f"Removed {removed} row(s) from {self._ctx.db_path}")
        # Step back a page if the last page emptied out.
        if self._offset >= self._total - removed and self._offset > 0:
            self._offset = max(0, self._offset - self.page_size.value())
        self._reload()
