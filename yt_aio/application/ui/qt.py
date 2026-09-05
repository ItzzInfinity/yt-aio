"""Qt compatibility layer.

Owns:   the single PyQt6-with-PyQt5-fallback import site for the whole application.
Reads:  nothing.
Writes: nothing.
Runs:   nothing.

Every module that needs a Qt name imports it from here. A panel that imports PyQt
directly re-creates this fallback block, and the copies drift (dev_guide.md 7.6).
"""

from __future__ import annotations

try:
    from PyQt6.QtCore import QObject, QThread, QTimer, Qt, QUrl, pyqtSignal, pyqtSlot
    from PyQt6.QtGui import QDesktopServices
    from PyQt6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QButtonGroup,
        QCheckBox,
        QComboBox,
        QCompleter,
        QFileDialog,
        QFormLayout,
        QFrame,
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
        QScrollArea,
        QSizePolicy,
        QSpinBox,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    QT_API = "PyQt6"
except ImportError:
    from PyQt5.QtCore import QObject, QThread, QTimer, Qt, QUrl, pyqtSignal, pyqtSlot
    from PyQt5.QtGui import QDesktopServices
    from PyQt5.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QButtonGroup,
        QCheckBox,
        QComboBox,
        QCompleter,
        QFileDialog,
        QFormLayout,
        QFrame,
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
        QScrollArea,
        QSizePolicy,
        QSpinBox,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    QT_API = "PyQt5"

Signal = pyqtSignal

if QT_API == "PyQt6":
    CHECKED = Qt.CheckState.Checked
    UNCHECKED = Qt.CheckState.Unchecked
    ITEM_FLAGS = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable
    ALIGN_TOP = Qt.AlignmentFlag.AlignTop
    ORIENTATION_HORIZONTAL = Qt.Orientation.Horizontal
    SELECT_ROWS = QAbstractItemView.SelectionBehavior.SelectRows
    NO_EDIT = QAbstractItemView.EditTrigger.NoEditTriggers
    NO_WRAP = QPlainTextEdit.LineWrapMode.NoWrap
    SIZE_EXPANDING = QSizePolicy.Policy.Expanding
    HEADER_STRETCH = QHeaderView.ResizeMode.Stretch
    TAB_NORTH = QTabWidget.TabPosition.North
    USER_ROLE = Qt.ItemDataRole.UserRole
    ECHO_NORMAL = QLineEdit.EchoMode.Normal
    MB_YES = QMessageBox.StandardButton.Yes
    MB_NO = QMessageBox.StandardButton.No
    ELIDE_RIGHT = Qt.TextElideMode.ElideRight
    MATCH_CONTAINS = Qt.MatchFlag.MatchContains
    CASE_INSENSITIVE = Qt.CaseSensitivity.CaseInsensitive
    SORT_ASCENDING = Qt.SortOrder.AscendingOrder
    SORT_DESCENDING = Qt.SortOrder.DescendingOrder
    ALIGN_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
else:
    CHECKED = Qt.Checked
    UNCHECKED = Qt.Unchecked
    ITEM_FLAGS = Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable
    ALIGN_TOP = Qt.AlignTop
    ORIENTATION_HORIZONTAL = Qt.Horizontal
    SELECT_ROWS = QAbstractItemView.SelectRows
    NO_EDIT = QAbstractItemView.NoEditTriggers
    NO_WRAP = QPlainTextEdit.NoWrap
    SIZE_EXPANDING = QSizePolicy.Expanding
    HEADER_STRETCH = QHeaderView.Stretch
    TAB_NORTH = QTabWidget.North
    USER_ROLE = Qt.UserRole
    ECHO_NORMAL = QLineEdit.Normal
    MB_YES = QMessageBox.Yes
    MB_NO = QMessageBox.No
    ELIDE_RIGHT = Qt.ElideRight
    MATCH_CONTAINS = Qt.MatchContains
    CASE_INSENSITIVE = Qt.CaseInsensitive
    SORT_ASCENDING = Qt.AscendingOrder
    SORT_DESCENDING = Qt.DescendingOrder
    ALIGN_RIGHT = Qt.AlignRight | Qt.AlignVCenter


def exec_app(app: QApplication) -> int:
    """Run the event loop under either binding."""
    return app.exec() if QT_API == "PyQt6" else app.exec_()
