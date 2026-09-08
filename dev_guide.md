# Developer Guide

How to add a new panel, open a new window, and change an existing feature without
breaking the rest of the desktop application.

---

## 0. How to read this guide

Every module, class, file and tool name in this document is a **placeholder**. The
guide describes *roles* and *patterns*, not the actual identifiers in the tree. Map a
placeholder onto the real thing by what it does, not by what it is called.

| Placeholder | Role in the real tree |
| --- | --- |
| `suite/` | the top-level Python package that contains the whole application |
| `suite/shell.py` | process entry point; builds the main window and the tab bar |
| `AppShell` | the `QMainWindow` subclass that owns the tab bar |
| `suite/<feature>/` | one subpackage per feature; one feature is one tab |
| `FeaturePanel` | the `QWidget` subclass a feature exposes to the shell |
| `suite/link_channel.py` | shared helper that owns a serial port and its reader thread |
| `LinkChannel` | the class inside that helper |
| `tool_alpha`, `tool_beta` | native executables that ship next to the Python code |
| `worker_module` | a Python package run as a child interpreter process |
| `profiles.json` | a bundled catalog that maps a profile name to numeric parameters |
| `settings.json` | an editable per-run parameter file consumed by a native tool |
| `summary.json` | the machine-readable result document panels write and read |
| `notes.txt` | a human-readable result file emitted by a native tool |
| `chunk-0000` | one element of a numbered series of raw capture files |

When this guide shows code, the code is a **template to copy**, not an excerpt of
anything that already exists. Type it fresh and rename it to fit your feature.

---

## 1. Architecture in one page

The application is a single Qt process. It shows one window. That window contains one
tab bar. Each tab is a self-contained widget that owns its own controls, its own state
and its own background work.

```
                       one OS process, one Qt event loop
   ┌───────────────────────────────────────────────────────────────────┐
   │  AppShell (QMainWindow)                                           │
   │  ┌─────────────────────────────────────────────────────────────┐  │
   │  │  QTabWidget                                                 │  │
   │  │  ┌────────┬────────┬────────┬────────┬────────┬──────────┐  │  │
   │  │  │ Panel1 │ Panel2 │ Panel3 │ Panel4 │ Panel5 │  Panel6  │  │  │
   │  │  └────────┴────────┴────────┴────────┴────────┴──────────┘  │  │
   │  └─────────────────────────────────────────────────────────────┘  │
   └───────────────────────────────────────────────────────────────────┘
        │              │              │              │
        │ QProcess     │ QThread      │ serial fd    │ pure Python
        ▼              ▼              ▼              ▼
   native tool    background      remote device    numpy / pandas
   child proc     worker thread   shell over UART  in-process
```

Three ownership rules hold the design together. Break them and the app gets hard to
change.

1. **The shell knows the panels. Panels never know the shell.** A panel must not walk
   up its parent chain, must not reach for the tab bar, and must not try to switch
   tabs.
2. **Panels never import each other.** No panel holds a Python reference to another
   panel's widget or state.
3. **Panels exchange data through files on disk.** A panel that needs a result another
   panel produced reads the file that panel wrote. That is the only cross-feature
   contract. See [§8](#8-data-contracts-between-panels).

Everything expensive leaves the GUI thread through one of the five patterns in
[§5](#5-the-five-work-patterns). Nothing else is allowed to block.

---

## 2. Repository layout

```
suite/
├── __init__.py
├── shell.py                    # entry point: python -m suite.shell
├── link_channel.py             # shared serial helper used by device-facing panels
│
├── acquire/                    # feature: pull raw data off a device
│   ├── __init__.py
│   └── panel.py                # AcquirePanel
│
├── archive/                    # feature: move data between local volumes
│   ├── __init__.py
│   └── panel.py                # ArchivePanel
│
├── analysis/                   # feature: run native checks over raw data
│   ├── __init__.py
│   ├── panel.py                # AnalysisPanel
│   ├── profiles.json           # bundled catalog
│   ├── reports/                # output, created at run time
│   └── tools/
│       ├── tool_alpha          # native executable, committed as a binary
│       └── tool_beta
│
├── inspect/                    # feature: run a native tool with an editable config
│   ├── __init__.py
│   ├── panel.py                # InspectPanel
│   ├── settings.json           # template config, never overwritten in place
│   └── tools/tool_gamma
│
├── navigate/                   # feature: decode a device log into metrics
│   ├── __init__.py
│   ├── panel.py                # NavigatePanel  (thin GUI)
│   └── worker_module/          # the actual processing, run as a child process
│       ├── __init__.py
│       ├── __main__.py         # argparse entry point
│       ├── reader/             # I/O adapters
│       ├── transform/          # dataframe shaping
│       ├── compute/            # math
│       └── errors/             # typed exceptions
│
└── summarize/                  # feature: merge artifacts into one document
    ├── __init__.py
    └── panel.py                # SummarizePanel
```

Conventions that matter:

- **One feature, one subpackage, one panel class.** Do not put two tabs in one file.
- **Native tools live under the feature that runs them**, in a `tools/` subdirectory.
- **Bundled data files** (`profiles.json`, `settings.json`) sit next to the panel that
  reads them.
- **Generated output** (`reports/`, extracted plaintext, zips) is created at run time
  and is not committed.

---

## 3. The panel contract

For a class to be mountable as a tab it must satisfy all of these:

1. It subclasses `QWidget`. Not `QMainWindow`, not `QDialog`.
2. Its constructor takes no required positional arguments. Optional keyword arguments
   with sensible defaults are fine; the shell may pass one (for example a resolved
   path to a bundled tool).
3. It builds and installs its own layout inside `__init__`.
4. It never calls `show()`, `resize()` or `setWindowTitle()` on itself. The shell owns
   window geometry.
5. It performs **no blocking work** in `__init__`. No device probe that can hang, no
   multi-second file scan, no network call. A cheap local scan (enumerate serial ports,
   list mount points) is acceptable; anything that can stall must be behind a button.
6. **It constructs successfully on a bare laptop.** No device attached, no external
   drive mounted, no tool binary present, no data on disk. A missing prerequisite is
   reported when the user presses the button, not by raising during start-up. One panel
   that throws in its constructor takes down the entire application.

### 3.1 Skeleton

Copy this, rename it, fill it in.

```python
# suite/widget_check/panel.py
"""Widget check panel.

Owns: the Widget Check tab.
Reads:  nothing at construction time.
Writes: <output dir>/summary.json
Runs:   suite/widget_check/tools/tool_delta   (see §5 Pattern A)
"""

import os

from PyQt5.QtCore import pyqtSlot
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QTextEdit, QProgressBar, QFileDialog, QMessageBox,
)


class WidgetCheckPanel(QWidget):
    """One tab. Constructed once at start-up and never destroyed."""

    def __init__(self, parent=None, tool_path: str = ""):
        super().__init__(parent)

        # ---- 1. state first, so no slot can ever see a missing attribute
        self._tool_path = tool_path
        self._busy = False

        # ---- 2. create every widget before anything is connected
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Choose an input folder")
        self.browse_btn = QPushButton("Browse...")
        self.run_btn = QPushButton("Run")
        self.cancel_btn = QPushButton("Cancel")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.console = QTextEdit()
        self.console.setReadOnly(True)

        # ---- 3. layout
        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("Input folder:"))
        input_row.addWidget(self.input_edit, 1)
        input_row.addWidget(self.browse_btn)

        action_row = QHBoxLayout()
        action_row.addWidget(self.run_btn)
        action_row.addWidget(self.cancel_btn)
        action_row.addStretch(1)
        action_row.addWidget(QLabel("Progress:"))
        action_row.addWidget(self.progress)

        inputs_box = QGroupBox("Inputs")
        inputs_v = QVBoxLayout(inputs_box)
        inputs_v.addLayout(input_row)

        root = QVBoxLayout(self)
        root.addWidget(inputs_box)
        root.addLayout(action_row)
        root.addWidget(QLabel("Console:"))
        root.addWidget(self.console, 1)

        # ---- 4. signals, only now that every widget exists
        self.browse_btn.clicked.connect(self._pick_input)
        self.run_btn.clicked.connect(self._start)
        self.cancel_btn.clicked.connect(self._cancel)

        # ---- 5. initial UI state
        self._set_busy(False)

    # ------------------------------------------------------------------ helpers
    def _log(self, tag: str, text: str) -> None:
        """Single place where anything reaches the console."""
        if text:
            self.console.append(f"[{tag}] {text.rstrip()}")

    def _set_busy(self, busy: bool) -> None:
        """Single place where run/cancel enablement is decided."""
        self._busy = busy
        self.run_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        self.input_edit.setEnabled(not busy)
        self.browse_btn.setEnabled(not busy)

    # ------------------------------------------------------------------- slots
    @pyqtSlot()
    def _pick_input(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose input folder", self.input_edit.text().strip() or os.path.expanduser("~")
        )
        if chosen:
            self.input_edit.setText(chosen)

    @pyqtSlot()
    def _start(self) -> None:
        if self._busy:
            return
        folder = self.input_edit.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "No input", "Choose an existing input folder.")
            return
        # ... launch work here, see §5
        self._set_busy(True)

    @pyqtSlot()
    def _cancel(self) -> None:
        if not self._busy:
            return
        self._log("INFO", "Cancel requested.")
        # ... stop the work, then:
        self._set_busy(False)
```

### 3.2 The module docstring is part of the contract

Every panel module starts with a header that answers four questions: what tab it owns,
what it reads, what it writes, and what external programs it runs. A reader who needs
to change the feature should not have to grep the body to find the file contract.

---

## 4. Adding a new tab, step by step

### Step 1 — create the package

```
suite/widget_check/
├── __init__.py        # empty
├── panel.py           # WidgetCheckPanel
└── tools/             # only if the feature ships a native tool
```

`__init__.py` stays empty. Do not re-export the panel from it; the shell imports the
module path directly, and an empty `__init__.py` keeps start-up cheap.

### Step 2 — write the panel

Start from the skeleton in [§3.1](#31-skeleton). Pick a work pattern from
[§5](#5-the-five-work-patterns) before you write the first slot; the pattern decides
how the rest of the class is shaped.

### Step 3 — register it with the shell

The shell does three things and nothing else: import the panel classes, instantiate
them, add each one to the tab bar with a label.

```python
# suite/shell.py
import os
import sys

from PyQt5.QtWidgets import QApplication, QMainWindow, QTabWidget

from .acquire.panel import AcquirePanel
from .archive.panel import ArchivePanel
from .widget_check.panel import WidgetCheckPanel      # <-- new import


TOOLS = os.path.join(os.path.dirname(__file__), "widget_check", "tools")


class AppShell(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Instrument Suite")
        self.resize(1280, 800)

        tabs = QTabWidget()
        tabs.setTabPosition(QTabWidget.North)
        tabs.setDocumentMode(True)

        tabs.addTab(AcquirePanel(), "Acquire")
        tabs.addTab(ArchivePanel(), "Archive")
        tabs.addTab(                                   # <-- new tab
            WidgetCheckPanel(tool_path=os.path.join(TOOLS, "tool_delta")),
            "Widget Check",
        )

        self.setCentralWidget(tabs)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Instrument Suite")
    window = AppShell()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
```

Rules for the tab label:

- Short enough that six or seven tabs fit without eliding. Aim for under 24 characters.
- Says what the operator gets, not what the code does.
- If the feature moves data, name both ends: `Copy: Device to Disk` reads better than
  `Copy Utility`.

**Tab order is workflow order.** Panels are laid left to right in the sequence an
operator uses them during a session. Insert a new tab at the position where it belongs
in the workflow, not at the end.

### Step 4 — declare dependencies

Add any new Python package to the top-level requirements file, pinned. If the new
native tool links a system-provided shared library, record the distribution package
name in the feature's own short `README.md` and in the top-level install notes. A tool
that fails to load at run time with a linker error is a support call, not a bug report.

### Step 5 — add the assets

Native tools are committed as binaries under `suite/<feature>/tools/`. Commit the C or
C++ source too, and record the exact build line in a comment at the top of the source
file:

```c
/* build: cc -O2 -Wall -o ../tools/tool_delta tool_delta.c -lpthread */
```

Mark the binary executable in the commit. A tool that ships without the execute bit
fails with a permission error that reads nothing like the real cause.

### Step 6 — smoke test

Before you open a review, confirm all of the following by hand:

- The app starts with the new tab present and **no device connected**.
- Switching to the tab and back does not stall the UI.
- Pressing the primary action with every field empty produces a clear message box and
  no traceback on the terminal.
- Pressing it with a valid input produces console output that streams while the work
  runs, not all at once at the end.
- Cancel actually stops the work.
- The app exits cleanly with the tab open and idle.

---

## 5. The five work patterns

Pick one before writing the panel. Mixing two in one method is where the bugs live.

### Pattern A — run a bundled native tool

Use when: the work is done by a committed executable that takes positional arguments,
writes progress to stdout and returns a meaningful exit code.

```python
from PyQt5.QtCore import QProcess, pyqtSlot

    def _start(self) -> None:
        if self._busy:
            return
        if not os.path.exists(self._tool_path):
            QMessageBox.critical(self, "Missing tool", f"Not found:\n{self._tool_path}")
            return

        args = [str(a) for a in self._build_args()]     # never pass non-str
        self._log("TX", f"{os.path.basename(self._tool_path)} {' '.join(args)}")

        self._proc = QProcess(self)
        self._proc.setProgram(self._tool_path)
        self._proc.setArguments(args)
        self._proc.setWorkingDirectory(os.path.dirname(self._tool_path))
        self._proc.readyReadStandardOutput.connect(self._on_stdout)
        self._proc.readyReadStandardError.connect(self._on_stderr)
        self._proc.finished.connect(self._on_finished)
        self._proc.errorOccurred.connect(self._on_proc_error)

        self.progress.setRange(0, 0)                    # indeterminate
        self._set_busy(True)
        self._proc.start()

        if not self._proc.waitForStarted(3000):
            self._set_busy(False)
            self.progress.setRange(0, 100)
            QMessageBox.critical(self, "Launch failed", "Could not start the tool.")

    @pyqtSlot()
    def _on_stdout(self) -> None:
        text = bytes(self._proc.readAllStandardOutput()).decode(errors="replace")
        for line in text.splitlines():
            self._log("RX", line)

    @pyqtSlot()
    def _on_stderr(self) -> None:
        text = bytes(self._proc.readAllStandardError()).decode(errors="replace")
        for line in text.splitlines():
            self._log("ERR", line)

    @pyqtSlot(int, QProcess.ExitStatus)
    def _on_finished(self, code: int, _status) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if code == 0 else 0)
        self._set_busy(False)
        if code == 0:
            self._log("INFO", "Completed successfully.")
            QMessageBox.information(self, "Done", "Completed successfully.")
        else:
            self._log("ERR", f"Exited with code {code}.")
            QMessageBox.warning(self, "Failed", f"Tool exited with code {code}.")

    @pyqtSlot()
    def _cancel(self) -> None:
        if not self._busy:
            return
        self._proc.terminate()
        if not self._proc.waitForFinished(2000):
            self._proc.kill()
```

Gotchas:

- **Every argument must be a string.** Passing an integer raises inside Qt with a
  message that does not name the offending argument.
- **Keep a reference to the `QProcess`** on `self`. A local goes out of scope and the
  child is reaped mid-run.
- **`errorOccurred` and `finished` can both fire.** Make `_set_busy(False)` idempotent
  so the panel cannot get stuck in the busy state.
- **Set the working directory explicitly** if the tool resolves anything relative to
  its own location.

#### Determinate progress from a tool that does not report percent

If the tool writes numbered output files, poll the output directory on a `QTimer`
rather than parsing stdout. Compute the expected count up front from the input size,
count the non-empty outputs each tick, and clamp the displayed value at 99 until the
process actually exits.

```python
    self._tick = QTimer(self)
    self._tick.setInterval(500)
    self._tick.timeout.connect(self._refresh_progress)
    self._tick.start()
    # ... and in _on_finished / _cancel / _on_proc_error:
    self._tick.stop()
```

Stop the timer on **every** exit path. A timer that outlives its process keeps
repainting a dead progress bar.

### Pattern B — run a Python module as a child process

Use when: the work is substantial Python that imports heavy libraries, or that you
want to be runnable head-less from a terminal as well as from the GUI.

```python
import pathlib
import sys

MODULE = "suite.navigate.worker_module"

    def _start(self) -> None:
        cmd = [sys.executable, "-m", MODULE, "--data-dir", data_dir, "--out", out_path]
        self._log("TX", " ".join(cmd))
        self._proc.setProgram(cmd[0])
        self._proc.setArguments(cmd[1:])
        # run from the repository root so the package import resolves
        self._proc.setWorkingDirectory(str(pathlib.Path(__file__).resolve().parents[2]))
        self._proc.start()
```

The child module must:

- expose an `argparse` interface in `__main__.py` with long-form flags only;
- write **INFO and below to stdout, WARNING and above to stderr**, so the panel can
  colour them differently;
- never prompt for input;
- exit non-zero on failure.

If the child prints noise from a compatibility layer or a third-party runtime, filter
it in the panel by regular expression and demote it to a warning rather than silencing
stderr wholesale.

### Pattern C — background thread worker

Use when: the work is Python running in-process, is I/O bound, and needs to report
incremental progress. Network transfers are the usual case.

```python
from PyQt5.QtCore import QThread, pyqtSignal


class TransferWorker(QThread):
    """Runs one transfer job. Emits, never touches widgets."""

    progress = pyqtSignal(int, str)     # percent, current item
    log = pyqtSignal(str)
    finished = pyqtSignal(bool, str)    # ok, message

    def __init__(self, host: str, items: list, dest: str):
        super().__init__()
        self._host = host
        self._items = items
        self._dest = dest
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            total = len(self._items)
            for done, item in enumerate(self._items, start=1):
                if self._stop:
                    self.finished.emit(False, "Aborted by user.")
                    return
                self.log.emit(f"Working on {item}")
                # ... the actual transfer ...
                self.progress.emit(int(done / total * 100), item)
            self.finished.emit(True, "Completed successfully.")
        except Exception as exc:
            self.finished.emit(False, f"Failed: {exc}")
```

The panel keeps the worker on `self`, connects the three signals to slots, and calls
`start()`. Hard rules:

- **A worker never touches a widget.** Not a label, not a progress bar, not a message
  box. It emits; the panel renders.
- **Cancellation is cooperative.** Set a flag, check it at the top of every loop
  iteration, and check it again inside inner loops that can run long.
- **The worker owns its own connections and resources** and closes them on every exit
  path, including the aborted one.
- **Keep the reference.** A `QThread` that goes out of scope while running crashes the
  process.

### Pattern D — drive a remote shell over a serial link

Use when: the panel talks to a device that exposes a shell on a serial port.

The shared `LinkChannel` helper owns the port, runs a reader thread, and pushes decoded
lines into a bounded queue. The panel drains that queue on a short `QTimer` and never
reads the port directly.

The core problem is framing: a serial console interleaves your command echo, the
command output, and the shell prompt. Solve it by wrapping every command in sentinel
lines and reading only what lies between them.

```python
import time

from PyQt5.QtWidgets import QApplication

BEGIN = "<<BEGIN:{tag}>>"
END = "<<END:{tag}>>"

    def _send_framed(self, core: str, tag: str) -> None:
        cmd = f"echo {BEGIN.format(tag=tag)}; {core}; echo {END.format(tag=tag)}"
        self._log("TX", cmd)
        self._link.write(cmd + "\n")

    def _collect(self, tag: str, timeout_s: float) -> list:
        """Drain lines between the sentinels. Returns [] on timeout."""
        begin, end = BEGIN.format(tag=tag), END.format(tag=tag)
        lines, inside, deadline = [], False, time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            line = self._link.read_line_nowait()
            if line is None:
                QApplication.processEvents()      # keep the UI alive while waiting
                continue
            if begin in line:
                inside = True
                continue
            if end in line and inside:
                return lines
            if inside:
                lines.append(line.rstrip())
        self._log("WARN", f"Timed out waiting for {tag}.")
        return lines
```

Rules for this pattern:

- **Quote every interpolated path** with `shlex.quote` before it reaches the remote
  shell. Paths from a device listing contain spaces and worse.
- **Long-running remote commands report completion with a return-code sentinel**, not
  by the panel guessing from output. Have the remote emit a single anchored line such
  as `<<RC:0>>` and match it with an anchored regular expression.
- **Normalise carriage returns** when a remote tool paints a progress line in place.
  Pipe its output through a translation step so each update arrives as its own line.
- **Never block the GUI thread in a bare loop.** Either pump the event loop as above,
  or restructure so the drain timer handles the response asynchronously. A collection
  window longer than about two seconds must be asynchronous.
- **A password prompt is not output.** Detect it, raise a masked input dialog, write the
  reply straight to the port, and log a placeholder. See
  [§13](#13-configuration-and-credentials).

### Pattern E — in-process compute

Use when: the work is a few hundred milliseconds of numeric code and produces a plot or
a table.

No process, no thread. Validate inputs, compute, render. Two constraints:

- **Cache expensive reads.** If a routine reads the same large file repeatedly to pull
  different fields out of it, read it once into a module-level cache keyed by path. Add
  a way to evict the cache when the user selects a different input, or a stale buffer
  will silently answer for the new file.
- **Bound the work.** If the input size is user-controlled, either clamp it or move to
  Pattern C. A compute that can grow to seconds belongs on a thread.

---

## 6. Opening a real second window

Most features do not need one. A tab that grows a second surface usually wants a
collapsible group box or a nested `QTabWidget` inside itself. Reach for a real window
only in these three cases.

### 6.1 Modal dialog: ask a question, get an answer, continue

Use the standard dialogs. They are modal, they block only the calling slot, and they
clean themselves up.

```python
from PyQt5.QtWidgets import QInputDialog, QLineEdit

    text, ok = QInputDialog.getText(
        self, "Access required", "Passphrase:", QLineEdit.Password
    )
    if not ok:
        self._log("INFO", "Cancelled by user.")
        return
```

Guard re-entrancy. If the trigger can fire repeatedly while the dialog is open, for
example from a stream of incoming lines, set a flag before showing it and clear it
after:

```python
    if self._prompt_open:
        return
    self._prompt_open = True
    try:
        text, ok = QInputDialog.getText(...)
    finally:
        self._prompt_open = False
```

### 6.2 Modeless tool window: a detail view the user keeps open

```python
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTableWidget


class DetailWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Run detail")
        self.setWindowFlag(Qt.Window)          # own taskbar entry, not always-on-top
        self.setAttribute(Qt.WA_DeleteOnClose) # free it when the user closes it
        self.resize(900, 600)

        self.table = QTableWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self.table)


# in the panel:
    def _open_detail(self) -> None:
        # reuse the open window instead of stacking duplicates
        if getattr(self, "_detail", None) is not None:
            self._detail.raise_()
            self._detail.activateWindow()
            return
        self._detail = DetailWindow(self)
        self._detail.destroyed.connect(lambda *_: setattr(self, "_detail", None))
        self._detail.show()
```

Three things go wrong here and only here:

1. **Garbage collection.** A window created in a slot with no stored reference is
   collected the moment the slot returns, and it vanishes. Store it on `self`, or parent
   it, or both.
2. **Duplicate stacking.** Without the reuse check above, every click opens another
   window and the operator loses track of which one is current.
3. **Dangling reference after close.** With `WA_DeleteOnClose` the C++ object is gone
   but the Python attribute still points at a wrapper. Touching it raises
   `RuntimeError: wrapped C/C++ object has been deleted`. Clearing the attribute on
   `destroyed` is what prevents that.

### 6.3 Plot window from a plotting library

A plotting library that manages its own windows keeps them alive on its own figure
registry. Two rules:

- **Close figures you replace.** A panel that plots on every button press leaks a window
  per press. Close the previous figure, or reuse a single figure and clear its axes.
- **Never plot from a worker thread.** Emit the data, plot in the panel.

### 6.4 What never to do

Do not create a second `QMainWindow`, and do not create a second `QApplication`. There
is one application object and one main window; both belong to the shell.

---

## 7. Modifying an existing panel

### 7.1 Respect the construction order

Panels are built in five phases, in this order:

1. initialise plain state attributes
2. create every widget
3. build the layout
4. connect signals
5. set the initial UI state, then optionally run one cheap local scan

Almost every construction-time crash in a GUI of this shape comes from doing these out
of order: connecting a signal to a slot that reads a widget created two lines later, or
running the initial scan before the widget it populates exists. When you add a control,
add it in phase 2, lay it out in phase 3, and connect it in phase 4. Never inline all
three at the point of use.

A related trap: a slot that fires during construction because you populated a combo box
after connecting its `currentTextChanged` signal. Wrap the population in
`blockSignals(True)` / `blockSignals(False)`, then set the current index deliberately.

### 7.2 Adding a control to an existing row

Find the phase-3 block that builds the row. Add the widget to the same layout with the
same stretch conventions the neighbours use: labels at stretch 0, the field that should
grow at stretch 1 or 2, buttons at stretch 0. If the row is already at five or six
widgets, start a new row instead; a row that wraps is worse than two rows.

### 7.3 Changing the arguments a native tool receives

This is the most dangerous edit in the codebase, because **the argument list is
positional and the contract is not written down anywhere the compiler can see**.

Before you touch it:

1. Find the argument list in the panel and count the positions.
2. Confirm against the tool's source, or against its usage message.
3. **Append, never insert.** Adding a parameter in the middle silently shifts every
   argument after it. The tool will parse garbage and may write garbage.
4. If you must reorder, rebuild and re-commit the tool in the same change, and say so
   in the commit message.
5. Record the full ordered list in the panel's module docstring:

```python
"""...
tool_delta argv:
    1 profile_name        str
    2 input_dir           path
    3 rate_hz             int
    4 first_index         int
    5 last_index          int
    6 write_config        "0" | "1"
    7 report_path         path
    8 hardware_rev        str
    9 mode                str | "None"
   10 catalog_path        path
   11 row_width_bits      int
   12..15 window bounds   int
"""
```

6. Provide a value for **every** position on every code path. When a parameter does not
   apply to the current mode, pass an explicit neutral value such as `"0"`, never an
   empty string and never a missing slot.

### 7.4 Extending the bundled catalog

The catalog maps a profile name to a set of numeric and string parameters. Panels read
it into a dictionary and pull fields out per selection.

- **Read every field with a default**, using `.get(name, default)`. Entries in the
  catalog are not uniform; older entries lack fields that newer ones have, and a direct
  subscript turns a missing optional field into a crash on selection.
- **Coerce at the boundary.** Numeric fields arrive as strings in some entries and as
  numbers in others. Convert once, where you read them, with a fallback:

  ```python
  row_width = int(entry.get("row_width_bits", 0) or 0)
  ```

- **A new field must be optional.** Adding a required field breaks every existing entry.
  Add it with a default that reproduces the previous behaviour, then backfill entries.
- **Keep the file sorted and one entry per profile.** It is edited by hand in the field.
- **Validate after editing**: `python -m json.tool profiles.json > /dev/null`.

### 7.5 Adding a state guard

Any panel that can start work needs exactly one busy flag and exactly one method that
acts on it (`_set_busy` in the skeleton). When you add a second long-running action to a
panel, do not add a second flag. Extend the existing one and have the new action refuse
to start while it is set.

Clear the flag in a `finally`, or in a slot that is guaranteed to run on every exit path
including error and cancel. A busy flag that leaks means the tab is dead until restart,
and that is one of the worst failure modes for a field tool.

### 7.6 Do not extend by copy-paste

If a new variant of an existing action differs only in a path, a label or one argument,
parameterise the existing method. Two near-identical methods drift within a release, and
the second one is where the stale bug survives. When you find an existing pair that has
already drifted, fold them into one as part of your change and say so in the commit.

---

## 8. Data contracts between panels

Panels are decoupled in memory and coupled on disk. The disk contract is real and needs
the same care as an API.

| Artifact | Produced by | Consumed by | Shape |
| --- | --- | --- | --- |
| `summary.json` | the analysis and navigation features | the summarise feature | flat object of scalar metrics |
| `notes.txt` | a native tool | the summarise feature | `Key: value` lines, one per line |
| `report.json` | the summarise feature | operators, downstream tooling | a copy of the merged summary |
| `<run>.csv` | the navigation worker | its own panel, for preview | tabular, header row |
| numbered raw files | the acquire feature | the analysis feature | opaque binary series |

Rules when reading an artifact another feature produced:

1. **Never assume it exists.** Missing is normal; the operator may not have run that step
   yet. Warn in the console, leave the corresponding field showing a placeholder, and
   continue.
2. **Never let one bad artifact abort the whole merge.** Read each source in its own
   `try`, collect successes and failures separately, and report both in the final
   message. Partial results are useful; an aborted merge is not.
3. **Parse `Key: value` text defensively.** Strip units and percent signs, accept both
   integer and decimal forms, and report exactly which expected keys were missing rather
   than failing with a generic parse error.
4. **Never write the consumer's own new fields into the producer's file** without also
   writing a separate merged copy. Keep one file that is the raw producer output and one
   that is the merged document.
5. **Write with an atomic-ish pattern** for anything an operator might read while it is
   being written: write a temporary file next to the target, then rename it into place.

---

## 9. Long-running work and the UI thread

The Qt event loop runs on the main thread. Anything that blocks it freezes the window,
and on some desktops the compositor then grays the whole app out, which operators read
as a crash.

Rules:

- **`waitFor...` calls are allowed only with a short timeout and only for start-up.**
  `waitForStarted(3000)` right after launching a child is fine. `waitForFinished()` on
  the real work is not.
- **No `sleep` in a slot.** If you are waiting for something, you want a timer or a
  thread.
- **No unbounded spin loop waiting for a file to appear.** A loop of the form "while the
  file does not exist, do nothing" pegs a core and never times out. Poll on a timer with
  a deadline and a clear failure message.
- **No fixed sleep as a substitute for readiness.** Waiting a fixed number of seconds for
  a device or a child process to be ready is a race that passes on your machine. Wait for
  an observable condition, with a timeout.
- **`processEvents()` is a last resort**, acceptable only inside a short bounded
  collection loop as in Pattern D. It re-enters the event loop, so a slot that calls it
  can be re-entered; guard the entry with your busy flag.
- **Every long action is cancellable**, and cancel is wired to something that actually
  stops the work: terminate then kill for a process, a cooperative flag for a thread, an
  interrupt byte for a remote shell.

---

## 10. Path resolution

There are two ways a panel finds a bundled file, and only one of them is safe.

```python
# Fragile: depends on where the process was launched from.
tool = os.path.join(os.getcwd(), "suite", "widget_check", "tools", "tool_delta")

# Correct: anchored to the module, works regardless of the working directory.
HERE = os.path.dirname(os.path.abspath(__file__))
tool = os.path.join(HERE, "tools", "tool_delta")
```

Working-directory-relative resolution works only when the app is launched from the
repository root. It breaks under a desktop launcher, under a packaged build, and under a
service manager. **All new code anchors to `__file__`.** When you touch a method that
still resolves against the working directory, convert it as part of the change.

The same applies to output. Resolve an output directory from user input or from an
anchored default, never from the working directory, and create it with
`os.makedirs(path, exist_ok=True)` before writing into it.

---

## 11. Logging and user feedback

One console per panel, one prefix vocabulary across the whole application:

| Prefix | Meaning |
| --- | --- |
| `[TX]` | a command this application sent out, to a child process or a device |
| `[RX]` | a line received back |
| `[INFO]` | normal progress from the application itself |
| `[WARN]` | something was skipped or degraded; the run continues |
| `[ERR]` | the operation failed |

Choose the surface deliberately:

- **Console** — everything. It is the record an operator screenshots when reporting a
  problem. Nothing important happens without a console line.
- **Message box** — only for a decision the operator must make now, or a terminal result
  they must acknowledge. A message box per file processed is unusable.
- **Inline status label or progress bar** — continuous state. Never a message box for
  something that changes every second.
- **Terminal `print`** — debugging only, and it does not survive review. If a value is
  worth printing it is worth a `[INFO]` console line.

When a run finishes, always state where the output went. A panel that says
"Completed successfully" without naming the file it wrote has failed the operator.

---

## 12. Destructive operations

Formatting a volume, deleting files, and overwriting a run all need the same treatment.

1. **Confirm with specifics.** The dialog names the target device or directory, lists up
   to a dozen affected items, states the total count when the list is longer, and says
   the action cannot be undone. Default the focused button to the safe one.
2. **Contain the path.** Before deleting anything under a chosen root, resolve both the
   root and each target with `os.path.realpath` and refuse any target that does not sit
   strictly inside the root. This is what stops a symlink or a stray `..` from walking
   the deletion out of the intended volume.

   ```python
   root = os.path.realpath(chosen_root)
   target = os.path.realpath(os.path.join(chosen_root, name))
   if not target.startswith(root + os.sep):
       QMessageBox.critical(self, "Refused", f"Outside the selected root:\n{target}")
       return
   ```

3. **Do not broaden permissions to make a delete succeed.** Recursively relaxing
   permissions across a whole volume so that a removal will not fail is a change with a
   far wider blast radius than the delete itself. Report the permission error and let the
   operator decide.
4. **Never run an elevated command without saying so** in the console, with the full
   command text, before it runs.
5. **Refresh the view afterwards** so the listing matches reality, and colour the outcome
   so a failure is not mistaken for a success.
6. **Refuse while busy.** A delete during a copy is a corrupted volume.

---

## 13. Configuration and credentials

- **No credentials in source.** Not a default password, not a host key, not a token.
- **A password reaches only the transport.** Read it from a masked dialog, write it
  directly to the process or port, and log a placeholder such as
  `[TX] <credential withheld>`. It never goes through the normal logging helper, because
  that helper echoes what it is given.
- **Never auto-answer a prompt with a literal value.** A hard-coded reply left in place
  after a debugging session both leaks and breaks.
- **Editable configuration is copy-on-write.** Load a template file for display, and save
  the operator's edits to a separate updated file next to it. Prefer the updated file at
  run time when it exists and fall back to the template. The template stays pristine so
  the panel can always offer "reload defaults".
- **Validate before running.** Parse the edited configuration and refuse to launch on a
  parse error, naming the position of the problem.
- **Host and device addresses are fields with defaults, not constants.** Sites differ.

---

## 14. Adding a native tool

A tool the GUI can drive well satisfies all of this:

| Requirement | Why |
| --- | --- |
| positional arguments, fixed order, all required | the panel builds a list; optional positions cause silent misalignment |
| prints a usage line and exits non-zero when the count is wrong | turns a misalignment into a clear message instead of corrupt output |
| line-buffered stdout | otherwise output arrives in one burst at exit and progress is impossible |
| progress on stdout, diagnostics on stderr | the panel colours them differently |
| meaningful exit code: `0` success, non-zero failure | the panel's entire success path keys off this |
| no interactive prompts | there is no terminal attached |
| writes results to a path given on the command line | the panel must know where the output is without guessing |
| creates its own output directories | avoids a whole class of first-run failures |
| terminates promptly on `SIGTERM` | cancel must work |

If the tool cannot report percent complete, have it emit numbered outputs and let the
panel count them (see Pattern A). If it can, emit a bare `NN%` token on its own line and
parse it with an anchored expression.

Commit the source alongside the binary, with the build line in a header comment, and
note any system library dependency in the feature README.

---

## 15. Manual test checklist

Run through this before opening a review on any panel change.

**Start-up**

- App starts with no device attached, no external volume mounted, no data present.
- Every tab can be selected; none stalls or throws on first paint.
- Terminal shows no traceback during start-up.

**Empty and invalid input**

- Primary action with all fields empty gives one clear message box, no traceback.
- A path that does not exist gives a message naming the path.
- A non-numeric value in a numeric field is rejected at entry or at validation.
- An out-of-order range (end before start) is rejected with a message that says which.

**Happy path**

- Console streams while the work runs.
- Progress advances and reaches completion.
- The finish message names the output location.
- The output file exists and parses.

**Cancel and failure**

- Cancel mid-run stops the work within a couple of seconds.
- After cancel, the panel is usable again: run enabled, cancel disabled, progress reset.
- A deliberately missing tool binary produces a clear message, not a traceback.
- A tool that exits non-zero is reported as a failure, not a success.

**Destructive actions**

- The confirmation dialog names the exact target and defaults to the safe button.
- Declining does nothing at all.
- A target outside the selected root is refused.

**Shutdown**

- Closing the window while idle exits cleanly.
- Closing the window with a background thread running does not hang the process.

---

## 16. Review checklist

- [ ] Panel constructs on a machine with no hardware and no data.
- [ ] No blocking call in the constructor.
- [ ] Widgets created before signals are connected; no slot reads a widget that does not
      exist yet.
- [ ] One busy flag, cleared on every exit path including error and cancel.
- [ ] Long work uses one of the five patterns; no `sleep`, no unbounded spin loop, no
      `waitForFinished` on the real work.
- [ ] Cancel is wired and actually stops the work.
- [ ] Paths anchored to `__file__`, not to the working directory.
- [ ] Every argument passed to a child process is a string; the full positional contract
      is documented in the module docstring.
- [ ] Catalog and configuration fields read with defaults.
- [ ] Console lines use the standard prefixes; the completion message names the output.
- [ ] Destructive actions confirm with specifics and contain the path.
- [ ] No credential, host key or token in source; no logged secret.
- [ ] No commented-out previous implementation left in the file.
- [ ] No copy-pasted near-duplicate of an existing method.
- [ ] New dependency pinned in the requirements file; new native tool committed with its
      source, its build line and its execute bit.

---

## 17. Hazards seen in this codebase

These are real failure shapes present in the tree. Do not reproduce them, and fix the
ones you touch.

**A probe whose result is discarded.** A capability check runs, parses its answer, and
then a line below assigns a fixed value over it, usually left over from a debugging
session. The probe still runs, still costs time, and still looks meaningful in review.
If a code path is temporarily forced, force it at the top with a named constant and a
comment saying why, so it is visible.

**A guard flag set and never cleared on the failure path.** A flag is set before
launching work and cleared in the success handler only. Any error path leaves the panel
permanently busy. Clear it in one method that every terminal path calls.

**An attribute referenced after it was renamed.** An error or completion path re-enables
a button using a name that no longer exists. It never runs during normal testing because
the happy path does not reach it, and it raises the first time something fails, replacing
a useful error message with a traceback. Grep for the old name across the whole file when
you rename a widget attribute, and exercise the failure path by hand.

**Commented-out previous implementations.** Several files carry two or three superseded
versions of the same method in comments. They make the current behaviour ambiguous to a
reader and they show up in searches. Version control is the archive; delete them.

**Copy-pasted near-duplicate methods.** Two actions that differ only in a device name and
a script path exist as two full copies. A fix applied to one silently misses the other.
Parameterise.

**Fixed sleeps standing in for readiness.** A wait of a fixed number of seconds after
launching an external extractor, then a bare loop waiting for a file to appear. Both are
races; the second one also has no timeout, so a failure upstream hangs the run forever.
Poll with a deadline and fail loudly.

**Working-directory-relative asset paths.** Several tools are located by joining the
current working directory with a hard-coded relative path. It works only when the app is
launched from the repository root.

**Output written next to the input by convention rather than by contract.** A result file
is written to a location the consumer then reconstructs by walking parent directories
looking for a name prefix. When the directory layout changes, the consumer silently finds
nothing. Pass the path explicitly.
