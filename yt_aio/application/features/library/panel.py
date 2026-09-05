"""Library panel.

Owns:   the Library tab.
Reads:  youtube_video_information joined against downloads and sources, through
        application/db/queries.py.
Writes: deletes the cached rows the operator selected, and clears the download rows'
        link to them. The download history itself is never destroyed.
Runs:   nothing (dev_guide.md 5, Pattern E).

The cache is the large table in this database, so every read is paged, filtered and
sorted in SQL. Nothing here loads the whole table into memory, and clicking a column
heading re-runs the query rather than reordering the page on screen: sorting one page
out of thousands of rows would look like a sort and behave like a bug.
"""

from __future__ import annotations

from typing import Any

from ...context import AppContext
from ...db.queries import (
    DEFAULT_LIBRARY_SORT,
    database_stats,
    delete_videos,
    fetch_albums,
    fetch_artists,
    fetch_channels,
    fetch_playlists,
    fetch_sources,
    fetch_videos,
)
from ...ui.qt import (
    ALIGN_RIGHT,
    CASE_INSENSITIVE,
    CHECKED,
    ITEM_FLAGS,
    MATCH_CONTAINS,
    MB_NO,
    MB_YES,
    NO_EDIT,
    SELECT_ROWS,
    SORT_ASCENDING,
    SORT_DESCENDING,
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

# Heading, and the sort key queries.py accepts for it. None means the column cannot be
# sorted, which is only ever the tick box.
COLUMNS: list[tuple[str, str | None]] = [
    ("", None),
    ("Video ID", "video_id"),
    ("Title", "title"),
    ("Channel", "channel_name"),
    ("Artists", "artists"),
    ("Album", "album"),
    ("Playlists", "playlists"),
    ("Duration", "duration"),
    ("Uploaded", "upload_date"),
    ("Cached", "cached_at"),
    ("Metadata", "is_full_metadata"),
    ("Downloads", "download_count"),
]
HEADERS = [heading for heading, _ in COLUMNS]
NUMERIC_COLUMNS = {7, 11}

COMPLETENESS = {
    "Everything": "all",
    "Full metadata only": "full",
    "Partial metadata only": "partial",
    "Downloaded": "downloaded",
    "Never downloaded": "never downloaded",
}

# Upper bound in minutes. Zero means no bound, which is why the spin boxes start there.
MAX_FILTER_MINUTES = 600


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
        self._sort_key = DEFAULT_LIBRARY_SORT
        self._sort_descending = True

        # ---- 2. widgets
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Title, video ID, channel or playlist")
        self.source_select = QComboBox()
        self.completeness_select = QComboBox()
        self.completeness_select.addItems(list(COMPLETENESS))

        # Editable so a long channel list can be typed through rather than scrolled.
        self.channel_select = self._lookup_box("Any channel")

        # Artists, album and playlists come from the music tables, so these filter on a
        # relationship rather than on one text column: a song credited to three artists is
        # found by any of the three (Docs/07_MUSIC_SCHEMA_PLAN.md).
        self.artist_select = self._lookup_box("Any artist")
        self.album_select = self._lookup_box("Any album")
        self.playlist_select = self._lookup_box("Any playlist")

        self.min_minutes = QSpinBox()
        self.min_minutes.setRange(0, MAX_FILTER_MINUTES)
        self.min_minutes.setSuffix(" min")
        self.min_minutes.setToolTip("Shortest duration to show. Zero means no lower bound.")
        self.max_minutes = QSpinBox()
        self.max_minutes.setRange(0, MAX_FILTER_MINUTES)
        self.max_minutes.setSuffix(" min")
        self.max_minutes.setToolTip("Longest duration to show. Zero means no upper bound.")

        self.page_size = QSpinBox()
        self.page_size.setRange(10, 2000)
        self.page_size.setSingleStep(50)
        self.page_size.setValue(200)
        self.refresh_button = QPushButton("Refresh")
        self.clear_filters_button = QPushButton("Clear filters")

        self.select_all_box = QCheckBox("Select all on this page")
        self.delete_button = QPushButton("Delete selected")
        self.prev_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        self.count_label = muted("Not loaded yet.")
        self.stats_label = muted("")

        self.table = RecordTable(HEADERS)
        self.table.setSelectionBehavior(SELECT_ROWS)
        self.table.setEditTriggers(NO_EDIT)
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)

        # ---- 3. layout. Two rows: what to match, then how much of it to show.
        filter_box = QGroupBox("Filters")
        filter_column = QVBoxLayout(filter_box)

        first_row = QHBoxLayout()
        first_row.addWidget(QLabel("Search"))
        first_row.addWidget(self.search_input, 1)
        first_row.addWidget(QLabel("Channel"))
        first_row.addWidget(self.channel_select, 1)
        first_row.addWidget(QLabel("Source"))
        first_row.addWidget(self.source_select)

        music_row = QHBoxLayout()
        music_row.addWidget(QLabel("Artist"))
        music_row.addWidget(self.artist_select, 1)
        music_row.addWidget(QLabel("Album"))
        music_row.addWidget(self.album_select, 1)
        music_row.addWidget(QLabel("Playlist"))
        music_row.addWidget(self.playlist_select, 1)

        second_row = QHBoxLayout()
        second_row.addWidget(QLabel("Duration"))
        second_row.addWidget(self.min_minutes)
        second_row.addWidget(QLabel("to"))
        second_row.addWidget(self.max_minutes)
        second_row.addWidget(QLabel("Show"))
        second_row.addWidget(self.completeness_select)
        second_row.addWidget(QLabel("Rows"))
        second_row.addWidget(self.page_size)
        second_row.addStretch(1)
        second_row.addWidget(self.clear_filters_button)
        second_row.addWidget(self.refresh_button)

        filter_column.addLayout(first_row)
        filter_column.addLayout(music_row)
        filter_column.addLayout(second_row)

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
        self.clear_filters_button.clicked.connect(self._clear_filters)
        self.search_input.returnPressed.connect(self._reset_and_reload)
        self.source_select.currentIndexChanged.connect(self._reset_and_reload)
        self.completeness_select.currentTextChanged.connect(self._reset_and_reload)
        self.channel_select.currentTextChanged.connect(self._reset_and_reload)
        self.artist_select.currentTextChanged.connect(self._reset_and_reload)
        self.album_select.currentTextChanged.connect(self._reset_and_reload)
        self.playlist_select.currentTextChanged.connect(self._reset_and_reload)
        self.min_minutes.valueChanged.connect(self._reset_and_reload)
        self.max_minutes.valueChanged.connect(self._reset_and_reload)
        self.page_size.valueChanged.connect(self._reset_and_reload)
        header.sectionClicked.connect(self._sort_by_column)
        self.select_all_box.toggled.connect(self._toggle_all)
        self.delete_button.clicked.connect(self._delete_selected)
        self.prev_button.clicked.connect(self._previous_page)
        self.next_button.clicked.connect(self._next_page)

        # ---- 5. initial state. The first read waits for the first paint, so the
        # constructor never touches the database.
        self.delete_button.setEnabled(False)
        self._update_page_buttons()
        self._show_sort_indicator()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().showEvent(event)
        if not self._loaded_once:
            self._loaded_once = True
            self._load_sources()
            self._load_channels()
            self._load_music_lookups()
            self._reload()

    # ------------------------------------------------------------------ helpers
    def _lookup_box(self, placeholder: str) -> QComboBox:
        """An editable drop-down that offers exact values and accepts a partial one."""
        box = QComboBox()
        box.setEditable(True)
        box.setMinimumWidth(150)
        # A list of two thousand long names would otherwise give the box a size hint wide
        # enough to swallow the whole filter row.
        box.setMaximumWidth(340)
        completer = box.completer()
        if completer is not None:
            completer.setCaseSensitivity(CASE_INSENSITIVE)
            completer.setFilterMode(MATCH_CONTAINS)
        line = box.lineEdit()
        if line is not None:
            line.setPlaceholderText(placeholder)
        return box

    @staticmethod
    def _fill_lookup(box: QComboBox, values: list[str], noun: str) -> None:
        """Refill a drop-down without losing what is typed in it."""
        current = box.currentText()
        box.blockSignals(True)
        box.clear()
        box.addItem("")
        box.addItems(values)
        box.setCurrentText(current)
        box.blockSignals(False)
        line = box.lineEdit()
        if line is not None:
            line.setPlaceholderText(f"Any of {len(values)} {noun}")

    def _load_music_lookups(self) -> None:
        """Fill the artist, album and playlist drop-downs from the music tables."""
        for box, loader, noun in (
            (self.artist_select, fetch_artists, "artist(s)"),
            (self.album_select, fetch_albums, "album(s)"),
            (self.playlist_select, fetch_playlists, "playlist(s)"),
        ):
            try:
                values = loader(self._ctx.db_path)
            except Exception:
                values = []
            self._fill_lookup(box, values, noun)

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

    def _load_channels(self) -> None:
        """Fill the channel drop-down from what the cache actually holds."""
        try:
            channels = fetch_channels(self._ctx.db_path)
        except Exception:
            channels = []
        self._fill_lookup(self.channel_select, channels, "channel(s)")

    def _selected_source_id(self) -> int | None:
        return self.source_select.currentData()

    def _duration_bounds(self) -> tuple[int | None, int | None]:
        """Minutes on screen, seconds in the query. Zero on either end means unbounded."""
        low = self.min_minutes.value() * 60 or None
        high = self.max_minutes.value() * 60 or None
        return low, high

    def _show_sort_indicator(self) -> None:
        for index, (_, key) in enumerate(COLUMNS):
            if key == self._sort_key:
                self.table.horizontalHeader().setSortIndicator(
                    index, SORT_DESCENDING if self._sort_descending else SORT_ASCENDING
                )
                return

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
                record.get("artists") or "",
                record.get("album") or "",
                record.get("playlists") or "",
                format_duration(record.get("duration")),
                record.get("upload_date") or "",
                record.get("cached_at") or "",
                "Full" if record.get("is_full_metadata") else "Partial",
                str(record.get("download_count") or 0),
            ]
            for column_index, text in enumerate(cells, start=1):
                cell = QTableWidgetItem(str(text))
                if column_index in NUMERIC_COLUMNS:
                    cell.setTextAlignment(ALIGN_RIGHT)
                self.table.setItem(row_index, column_index, cell)

        self.table.resizeColumnsToContents()
        self._show_sort_indicator()
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
        low, high = self._duration_bounds()
        if low and high and low > high:
            self.table.setRowCount(0)
            self._rows, self._total = [], 0
            self.count_label.setText("The shortest duration is longer than the longest one.")
            return
        try:
            self._rows, self._total = fetch_videos(
                self._ctx.db_path,
                search=self.search_input.text(),
                source_id=self._selected_source_id(),
                completeness=COMPLETENESS[self.completeness_select.currentText()],
                channel=self.channel_select.currentText(),
                artist=self.artist_select.currentText(),
                album=self.album_select.currentText(),
                playlist=self.playlist_select.currentText(),
                min_duration=low,
                max_duration=high,
                sort_key=self._sort_key,
                descending=self._sort_descending,
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

    @pyqtSlot(int)
    def _sort_by_column(self, column: int) -> None:
        """Clicking a heading re-runs the query. Clicking the same one flips the order."""
        key = COLUMNS[column][1] if 0 <= column < len(COLUMNS) else None
        if key is None:
            return
        if key == self._sort_key:
            self._sort_descending = not self._sort_descending
        else:
            self._sort_key = key
            # Dates and counts are most useful newest and largest first; names are not.
            self._sort_descending = key in {"cached_at", "upload_date", "download_count", "duration", "is_full_metadata"}
        self._offset = 0
        self._reload()

    @pyqtSlot()
    def _clear_filters(self) -> None:
        self.search_input.clear()
        self.channel_select.setCurrentText("")
        for box in (self.artist_select, self.album_select, self.playlist_select):
            box.setCurrentText("")
        for widget in (self.min_minutes, self.max_minutes):
            widget.setValue(0)
        self.source_select.setCurrentIndex(0)
        self.completeness_select.setCurrentIndex(0)
        self._offset = 0
        self._reload()

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
        self._load_channels()
        # Step back a page if the last page emptied out.
        if self._offset >= self._total - removed and self._offset > 0:
            self._offset = max(0, self._offset - self.page_size.value())
        self._reload()
