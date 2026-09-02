"""Logs panel.

Owns:   the Logs tab.
Reads:  downloads, errors, user_actions, settings_changes and yt_aio_version, through
        application/db/queries.py.
Writes: nothing. This tab is read-only by design; deleting belongs to the Library tab.
Runs:   nothing (dev_guide.md 5, Pattern E).
"""

from __future__ import annotations

from typing import Any

from ...context import AppContext
from ...db.queries import LOG_VIEWS, fetch_view
from ...ui.qt import (
    ALIGN_TOP,
    NO_EDIT,
    ORIENTATION_HORIZONTAL,
    SELECT_ROWS,
    USER_ROLE,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    pyqtSlot,
)
from ...ui.widgets import RecordTable, muted

DETAIL_PLACEHOLDER = "Select a row to see the whole record, including the stack trace."


class LogsPanel(QWidget):
    """One tab. Constructed once at start-up and never destroyed."""

    def __init__(self, parent: QWidget | None = None, *, context: AppContext) -> None:
        super().__init__(parent)

        # ---- 1. state
        self._ctx = context
        self._rows: list[dict[str, Any]] = []
        self._columns: list[str] = []
        self._offset = 0
        self._total = 0
        self._loaded_once = False

        # ---- 2. widgets
        self.view_select = QComboBox()
        self.view_select.addItems(list(LOG_VIEWS))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by any text in the record")
        self.page_size = QSpinBox()
        self.page_size.setRange(10, 2000)
        self.page_size.setSingleStep(50)
        self.page_size.setValue(200)
        self.refresh_button = QPushButton("Refresh")
        self.prev_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        self.count_label = muted("Not loaded yet.")

        self.table = RecordTable(["ID"])
        self.table.setSelectionBehavior(SELECT_ROWS)
        self.table.setEditTriggers(NO_EDIT)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlainText(DETAIL_PLACEHOLDER)

        # ---- 3. layout
        filter_box = QGroupBox("View")
        filter_row = QHBoxLayout(filter_box)
        filter_row.addWidget(QLabel("Table"))
        filter_row.addWidget(self.view_select)
        filter_row.addWidget(QLabel("Search"))
        filter_row.addWidget(self.search_input, 1)
        filter_row.addWidget(QLabel("Rows"))
        filter_row.addWidget(self.page_size)
        filter_row.addWidget(self.refresh_button)

        page_row = QHBoxLayout()
        page_row.addWidget(self.prev_button)
        page_row.addWidget(self.next_button)
        page_row.addStretch(1)
        page_row.addWidget(self.count_label)

        split = QSplitter(ORIENTATION_HORIZONTAL)
        table_side = QWidget()
        table_layout = QVBoxLayout(table_side)
        table_layout.addWidget(self.table)
        detail_side = QWidget()
        detail_layout = QVBoxLayout(detail_side)
        detail_layout.setAlignment(ALIGN_TOP)
        detail_layout.addWidget(QLabel("Record detail"))
        detail_layout.addWidget(self.detail)
        split.addWidget(table_side)
        split.addWidget(detail_side)
        split.setSizes([880, 440])

        root = QVBoxLayout(self)
        root.addWidget(filter_box)
        root.addWidget(split, 1)
        root.addLayout(page_row)

        # ---- 4. signals
        self.refresh_button.clicked.connect(self._reload)
        self.search_input.returnPressed.connect(self._reload)
        self.view_select.currentTextChanged.connect(self._on_view_changed)
        self.page_size.valueChanged.connect(self._on_view_changed)
        self.prev_button.clicked.connect(self._previous_page)
        self.next_button.clicked.connect(self._next_page)
        self.table.itemSelectionChanged.connect(self._show_detail)

        # ---- 5. initial state. The first read is deferred to the first paint so the
        # constructor stays free of work that touches the disk.
        self._update_page_buttons()

    # ------------------------------------------------------------------ shell hook
    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().showEvent(event)
        if not self._loaded_once:
            self._loaded_once = True
            self._reload()

    # ------------------------------------------------------------------ helpers
    def _current_view(self) -> str:
        return self.view_select.currentText() or next(iter(LOG_VIEWS))

    def _update_page_buttons(self) -> None:
        self.prev_button.setEnabled(self._offset > 0)
        self.next_button.setEnabled(self._offset + self.page_size.value() < self._total)

    def _render(self) -> None:
        spec = LOG_VIEWS[self._current_view()]
        headers = [spec.headers[spec.columns.index(name)] for name in self._columns]
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(self._rows))

        for row_index, record in enumerate(self._rows):
            for column_index, name in enumerate(self._columns):
                value = record.get(name)
                text = "" if value is None else str(value)
                # A stack trace is many lines; the grid shows the first, the detail
                # pane shows all of it.
                cell = QTableWidgetItem(text.splitlines()[0] if "\n" in text else text)
                cell.setData(USER_ROLE, record.get("id"))
                self.table.setItem(row_index, column_index, cell)

        self.table.resizeColumnsToContents()
        first = 0 if not self._rows else self._offset + 1
        last = self._offset + len(self._rows)
        self.count_label.setText(
            f"Showing {first}-{last} of {self._total}" if self._total else "No rows match."
        )
        self.detail.setPlainText(DETAIL_PLACEHOLDER)
        self._update_page_buttons()

    # ------------------------------------------------------------------- slots
    @pyqtSlot()
    def _reload(self) -> None:
        view = self._current_view()
        try:
            self._columns, self._rows, self._total = fetch_view(
                self._ctx.db_path,
                view,
                search=self.search_input.text(),
                limit=self.page_size.value(),
                offset=self._offset,
            )
        except Exception as exc:
            self._rows, self._columns, self._total = [], [], 0
            self.count_label.setText(f"Could not read {view}: {exc}")
            self.table.setRowCount(0)
            return
        self._render()

    @pyqtSlot()
    def _on_view_changed(self) -> None:
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

    @pyqtSlot()
    def _show_detail(self) -> None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return
        record = self._rows[rows[0].row()] if rows[0].row() < len(self._rows) else None
        if record is None:
            return

        spec = LOG_VIEWS[self._current_view()]
        # Long fields last, so the short identifying ones stay visible at the top.
        ordered = [name for name in self._columns if name not in spec.detail_columns]
        ordered += [name for name in spec.detail_columns if name in self._columns]

        lines = []
        for name in ordered:
            value = record.get(name)
            if value in (None, ""):
                continue
            text = str(value)
            lines.append(f"{name}:\n{text}\n" if "\n" in text else f"{name}: {text}")
        self.detail.setPlainText("\n".join(lines) or "This record is empty.")
