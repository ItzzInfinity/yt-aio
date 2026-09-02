# 🧩 Tab Shell Migration Plan (FSD 1.7.2)

Answers FSD section `1.7.2`: read [`dev_guide.md`](file:///home/itzzinfinity/GitHub/yt_aio/dev_guide.md),
list every change needed to bring this codebase to the documented structure, and state the
expected output once those changes are made.

> **Status: implemented on 2026-09-02, shipped as version `0.4.0`.** Every change below is in the tree. The
> sections stay written as a plan because that is what FSD 1.7.2 asked for, and because sections 3 to 7 are the
> contract a new tab has to satisfy. One thing landed wider than planned: the console tags in item B6 were applied
> at their source in the utils layer as well, so the worker's own lines carry severity and not just the panel's.
> The tab roster in section 8 is now fully built: FSD 1.8.2 shipped Import, Library, Logs and Settings in `0.5.0`,
> and `features/downloader/worker.py` moved to `application/jobs.py` once a second tab needed the same runner.

The centre of the plan is one move: **the current single-window app becomes exactly one tab**,
mounted in a shell that owns the tab bar. Every feature in FSD `1.8.2` then arrives as another
tab package, with no edit to the downloader beyond one import line in the shell.

---

## 1. Mapping the guide's placeholders onto this repository

`dev_guide.md` §0 states that every name in it is a placeholder for a role. This is the binding
map for this project. Use it whenever the guide names something.

| Guide placeholder | This repository | Status today |
|---|---|---|
| `suite/` | `yt_aio/application/` | exists |
| `suite/shell.py` | `yt_aio/application/shell.py` | **missing** — `main()` lives inside `main_window.py` |
| `AppShell` | `AppShell(QMainWindow)` in `shell.py` | **missing** — `MainWindow` is both shell and feature |
| `suite/<feature>/` | `yt_aio/application/features/<feature>/` | **missing** — one flat UI module |
| `FeaturePanel` | `DownloaderPanel(QWidget)` | **missing** — `MainWindow(QMainWindow)` |
| `suite/link_channel.py` (shared helper owning a resource) | `yt_aio/application/context.py` owning config + database path | **missing** — that state sits on `MainWindow` |
| `profiles.json` (bundled catalog) | `application/config/config.json` | exists, already relative-path based |
| `summary.json` (cross-feature artifact) | `application/db/yt_aio.db` | exists — the database *is* the disk contract here |
| `tool_alpha` (bundled native tool) | `yt-dlp`, resolved from `PATH` or `python3 -m yt_dlp` | exists, not bundled — see §9 |
| `worker_module` (child interpreter process) | not used; work runs on `QThread` + `ThreadPoolExecutor` | Pattern C, see §6 |

Two deliberate deviations from the guide, both recorded here so a reviewer does not read them as
oversights:

1. **Feature packages sit under `application/features/`, not directly under `application/`.**
   FSD `1.7` fixes `ui/`, `utils/`, `db/`, `config/` and `logs/` as the top level of
   `application/`. Dropping five feature packages beside those five layer packages makes the
   listing ambiguous. The guide's rule that matters, one feature is one subpackage with one panel
   class, is fully preserved.
2. **Panels talk to SQLite, not to loose files.** Guide §8 makes files on disk the only
   cross-feature contract. Here the equivalent single writer-many readers artifact is
   `yt_aio.db`. The intent, no panel holding a reference to another panel, is preserved exactly.

---

## 2. Target layout

```
yt_aio/
├── __init__.py                      # metadata only: APP_NAME, APP_VERSION, APP_CHANGELOG
├── __main__.py                      # python3 -m yt_aio  ->  application.shell.main()
│
└── application/
    ├── __init__.py                  # empty
    ├── shell.py                     # AppShell(QMainWindow) + main(); the only window
    ├── context.py                   # AppContext: config, db path, reload, config_changed signal
    │
    ├── features/
    │   ├── __init__.py              # empty
    │   └── downloader/
    │       ├── __init__.py          # empty
    │       ├── panel.py             # DownloaderPanel(QWidget)   <- today's MainWindow body
    │       └── worker.py            # TaskThread(QThread)
    │
    ├── ui/
    │   ├── __init__.py              # empty
    │   ├── qt.py                    # the PyQt6/PyQt5 compatibility layer, imported everywhere
    │   └── styles.qss               # applied once by the shell, now with QTabWidget rules
    │
    ├── utils/                       # unchanged: shared.py, config_manager.py,
    │                                # video_info_extractor.py, download_manager.py
    ├── db/                          # unchanged: database_manager.py, yt_aio.db
    ├── config/config.json           # unchanged
    └── logs/                        # unchanged
```

Deleted: `yt_aio/gui.py`, `yt_aio/services.py`, `yt_aio/config.py`, `yt_aio/logging_db.py`,
`yt_aio/run.py`, `yt_aio/application/ui/main_window.py`.

---

## 3. The change list

Each item is independently reviewable. `[G §n]` cites the section of `dev_guide.md` that requires
it. Items are ordered so the tree stays importable after every one of them.

### Group A — new files

**A1. `application/ui/qt.py` — extract the Qt compatibility layer.** `[G §7.6]`
Lines 14 to 91 of `main_window.py` are a 78-line PyQt6-with-PyQt5-fallback import block plus the
enum aliases `CHECKED`, `UNCHECKED`, `ITEM_FLAGS`, `ALIGN_TOP`, `ORIENTATION_HORIZONTAL`,
`SELECT_ROWS`, `NO_EDIT`. With five tabs this block gets copied five times and the copies drift.
Move it once into `ui/qt.py`, export `QT_API` and every widget name, and have panels do
`from ...ui.qt import QWidget, QVBoxLayout, CHECKED`. This is the single highest-value change in
the list: it is what makes tab number two cheap.

**A2. `application/context.py` — the shared application state helper.** `[G §1, §8]`
Today `MainWindow` owns `config_path`, `raw_config`, `config`, `db_path` and
`reload_config_if_changed()`. None of that is downloader-specific. The Settings tab and the
Database tab from FSD `1.8.2` need the same four values and the same reload path. Give it a home:

```python
# yt_aio/application/context.py
"""Shared application state.

Owns:   the resolved configuration and the database path.
Reads:  application/config/config.json
Writes: settings_changes rows in yt_aio.db when the file changes on disk.
Runs:   nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

from .db.database_manager import init_db, log_setting_change
from .ui.qt import QObject, Signal
from .utils.config_manager import CONFIG_PATH, ensure_config, load_config, resolve_runtime_config
from .utils.shared import now_string


class AppContext(QObject):
    """One instance per process. Built by the shell, passed to every panel."""

    config_changed = Signal()          # panels connect; panels never call each other

    def __init__(self) -> None:
        super().__init__()
        self.config_path: Path = ensure_config(CONFIG_PATH)
        self.raw_config: dict = load_config(self.config_path)
        self.config: dict = resolve_runtime_config(self.raw_config)
        self.db_path: str = self.config["log_file_path"]

    def reload_if_changed(self, log=None) -> None:
        """Re-read config.json, record every changed key, re-init the database if it moved."""
        ...   # the body of today's MainWindow.reload_config_if_changed, verbatim
```

`AppContext` is a shared helper, not the shell. Passing it to a panel does **not** break guide §1
rule 1: the panel still cannot reach the tab bar, cannot switch tabs, and cannot see its siblings.
It is the same role `link_channel.py` plays in the guide.

**A3. `application/features/downloader/worker.py`.** `[G §5 Pattern C]`
*(Landed here first, then moved to the shared `application/jobs.py` when the Import tab of FSD 1.8.2 became a
second caller. A shared runner beats two copies of the same worker.)*
Move `TaskThread` (lines 94 to 163 of `main_window.py`) here unchanged in behaviour, with two
fixes:

- Replace the two `assert` statements in `run()` with real validation. `assert` is stripped under
  `python3 -O`, which turns a programming error into a confusing `NoneType` crash inside
  `list_videos`. Raise `ValueError` with the missing field named.
- Widen `load_complete` to `Signal(object, str, str, str)` so it carries the `source_kind` and
  `source_value` the job actually ran with. See B4 for why.

The class already satisfies the hard rules of Pattern C: it never touches a widget, it emits, it
keeps its reference on the panel, and cancellation is cooperative through `CancellationToken`.

**A4. `application/features/downloader/panel.py`.** The subject of §4 below.

**A5. `application/shell.py`.** The subject of §5 below.

**A6. `application/features/__init__.py` and `.../downloader/__init__.py`, both empty.** `[G §4 Step 1]`
Do not re-export the panel from `__init__.py`. The shell imports the module path directly and an
empty init keeps start-up cheap.

### Group B — changes inside the code being moved

These are edits to logic that is moving anyway, so they cost nothing extra now and get expensive
later.

**B1. `MainWindow(QMainWindow)` becomes `DownloaderPanel(QWidget)`.** `[G §3 rules 1 and 4]`
Drop `setWindowTitle()` and `resize(1320, 860)` from the constructor. The shell owns geometry.
Drop `setCentralWidget`; the panel installs its own `QVBoxLayout` on itself.

**B2. `_apply_stylesheet()` is deleted from the panel.** `[G §6.4]`
`self.setStyleSheet(...)` on a panel styles that panel's subtree only, so tab two would render
unstyled. The shell calls `app.setStyleSheet(...)` once, before any panel is constructed.

**B3. No blocking work in the constructor.** `[G §3 rules 5 and 6]`
`MainWindow.__init__` currently calls `ensure_config()` and `init_db()`. Both are heavy and both
can fail: `ensure_config` migrates legacy files and rewrites `config.json`, and `init_db` creates
seven tables, adds missing columns, drops the retired count columns and runs
`_backfill_relations()` over every existing row. One panel that raises in its constructor takes
down the whole application, and with five tabs that is five times the exposure. Both calls move
into `main()` before `AppShell` is built. The panel receives a ready `AppContext`.

**B4. Fix the stale-key bug while it is being moved.** `[G §17, "an attribute referenced after it
was renamed" family]`
`on_load_complete` recomputes the cache key from the widgets:

```python
source_kind = self.current_source_kind()          # read at completion time
source_value = self.source_input.text().strip()   # read at completion time
self.loaded_key = (source_kind, source_value)
```

Edit the source box or flip the Channel/Playlist radio while a listing runs, and the finished
listing is filed under the new key. The next Download click then downloads the previous channel's
rows believing they belong to the new source. Take both values from the `load_complete` signal
(A3) instead of from the widgets.

**B5. Fold `set_busy_state` and `set_idle_state` into one `_set_busy(bool)`.** `[G §7.5]`
The two methods enable and disable the same nine widgets in mirror image. They are already one
edit away from drifting, and a widget added to one but not the other is a permanently dead
control. One method, one flag, called from every terminal path. While folding, add
`self.table.setEnabled(not busy)`: today the checkboxes stay live during a download, so the
selection can be changed out from under a running job.

**B6. Adopt the console prefix vocabulary.** `[G §11]`
Every log line today is `[timestamp] message` with no severity. Introduce
`_log(tag, text)` writing `[HH:MM:SS] [TAG] text` with `TX`, `RX`, `INFO`, `WARN`, `ERR`, and
route every existing `append_log` call through it. This matters more than it looks: it is the
vocabulary the Logs tab in FSD `1.8.2` will filter on, and retrofitting tags across five panels
later is far worse than tagging one panel now. Keep `append_log` as the sink the worker's
`log_message` signal connects to.

**B7. Rename slots to the guide's convention and decorate them.** `[G §3.1]`
`on_download_clicked` to `_start`, `on_stop_clicked` to `_cancel`, `on_clear_clicked` to
`_clear_log`, `on_config_clicked` to `_open_config`, `on_load_complete` to `_on_load_complete`,
`on_work_complete` to `_on_work_complete`, `on_work_failed` to `_on_work_failed`,
`get_selected_items` to `_selected_items`, `populate_table` to `_populate_table`. Add
`@pyqtSlot()` to each. Public surface of the panel becomes: the constructor and `shutdown()`.

**B8. Reorder the constructor into the five phases.** `[G §7.1]`
State, then every widget, then layout, then connections, then initial UI state. `_build_ui`
currently interleaves creation and layout and ends with the connections, which is close but not
the documented order, and the phases are what stop a slot from firing against a widget that does
not exist yet.

**B9. Add a `shutdown()` hook and honour it in the shell.** `[G §15 "Shutdown"]`
There is no `closeEvent` anywhere today. Close the window mid-download and Qt destroys a running
`QThread`, which prints `QThread: Destroyed while thread is still running` and can abort the
process. `shutdown()` cancels the token, calls `wait(5000)` on the worker, and returns. This is a
documented extension to the guide's panel contract: **optional `shutdown()`, called by the shell
on close, must be safe to call when idle and must not block for more than a few seconds.**

**B10. Module docstring as contract.** `[G §3.2]`
Every panel module opens with what tab it owns, what it reads, what it writes, and what external
programs it runs. For the downloader: owns the Downloader tab; reads `config.json` and the
`youtube_video_information` cache; writes `downloads`, `errors`, `user_actions` rows and the media
files themselves; runs `yt-dlp` as a subprocess.

### Group C — the shell and the entry point

**C1. `main()` moves out of `main_window.py` into `shell.py`,** and becomes the only place that
constructs `QApplication`. `[G §6.4]`

**C2. `yt_aio/__main__.py` imports from the new location:**
`from .application.shell import main`. The documented run command `python3 -m yt_aio` does not
change.

**C3. Delete the compatibility shims:** `yt_aio/gui.py`, `yt_aio/services.py`, `yt_aio/config.py`,
`yt_aio/logging_db.py`, `yt_aio/run.py`. `[G §16, §17]`
They were the transition aid recorded in the 2026-04-24 progress entry, and the transition is
over. Nothing in the tree imports them except `run.py` importing `gui.py`. Leaving them means a
reader grepping for `download_many` finds three answers, and a new tab can import a stale path
that silently star-imports a whole module.

**C4. Reduce `yt_aio/__init__.py` to metadata only.** It currently re-exports five config
functions, so `main_window.py` doing `from ... import APP_NAME` drags the config layer into the
outermost package import. Keep `APP_NAME`, `APP_VERSION`, `APP_CHANGELOG` and nothing else. Bump
`APP_VERSION` to `0.4.0` and set `APP_CHANGELOG` to the tab-shell migration.

**C5. Add `QTabWidget` and `QTabBar` rules to `styles.qss`.**
The stylesheet has no tab rules at all, so a tab bar added today renders in the default light
palette above a `#12161c` panel. Needed: `QTabWidget::pane` border and background, `QTabBar::tab`
padding and radius, and `:selected` and `:hover` states drawn from the existing accent `#1f6feb`
and surface `#1e2630`.

### Group D — documentation, done in the same change

**D1.** `README.md` — replace the compatibility-wrapper bullet with the shell and features layout.
**D2.** `Docs/02_CODE_AND_MODULES.md` — the directory cheatsheet at §1 and the `main_window.py`
walk-through both name files that no longer exist.
**D3.** `Docs/01_ARCHITECTURE_AND_THREADING.md` and `Docs/README.md` — the three-layer diagram
gains a shell row above the UI layer.
**D4.** `PROGRESS_LOG.md` — one entry, matching the existing format.

---

## 4. The panel, in full shape

```python
# yt_aio/application/features/downloader/panel.py
"""Downloader panel.

Owns:   the Downloader tab.
Reads:  application/config/config.json (through AppContext);
        the youtube_video_information cache in yt_aio.db.
Writes: downloads / errors / user_actions rows in yt_aio.db;
        media files under config["default_download_path"].
Runs:   yt-dlp, as a subprocess, from a background QThread (guide §5 Pattern C).
"""

from ...context import AppContext
from ...ui.qt import (CHECKED, NO_EDIT, SELECT_ROWS, QGroupBox, QPushButton,
                      QTableWidget, QVBoxLayout, QWidget, pyqtSlot)
from ...utils.shared import CancellationToken, DownloadTarget, VideoItem, now_string
from .worker import TaskThread


class DownloaderPanel(QWidget):
    """One tab. Constructed once at start-up and never destroyed."""

    def __init__(self, parent=None, *, context: AppContext) -> None:
        super().__init__(parent)

        # ---- 1. state
        self._ctx = context
        self._busy = False
        self._worker: TaskThread | None = None
        self._cancel_token: CancellationToken | None = None
        self._items: list[VideoItem] = []
        self._loaded_key: tuple[str, str] | None = None
        self._loaded_source_name = ""

        # ---- 2. widgets   (source_input, radios, table, quick box, four buttons, log view)
        # ---- 3. layout    (today's QSplitter, unchanged)
        # ---- 4. connections
        # ---- 5. initial state
        self._set_busy(False)
        self._log("INFO", f"{APP_NAME} {APP_VERSION} ready. Config: {self._ctx.config_path}")

    def shutdown(self) -> None:
        """Called by the shell on close. Safe when idle."""
        if self._cancel_token is not None:
            self._cancel_token.cancel()
        if self._worker is not None:
            self._worker.wait(5000)
```

Constructor cost after B3: building widgets and reading `self._ctx`. No file write, no schema
migration, no subprocess. It satisfies guide §3 rule 6 on a machine with no `yt-dlp`, no database
and no config, because the only thing that can now fail, launching `yt-dlp`, happens behind the
Download button.

---

## 5. The shell

```python
# yt_aio/application/shell.py
"""Application shell.

Owns:   the one QMainWindow and the tab bar.
Reads:  application/ui/styles.qss
Writes: nothing.
Runs:   nothing. All work belongs to the panels.
"""

import sys
from pathlib import Path

from .. import APP_NAME, APP_VERSION
from .context import AppContext
from .db.database_manager import init_db
from .features.downloader.panel import DownloaderPanel
from .ui.qt import QT_API, QApplication, QMainWindow, QTabWidget

STYLESHEET_PATH = Path(__file__).resolve().parent / "ui" / "styles.qss"


class AppShell(QMainWindow):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION} — ItzzInfinity")
        self.resize(1320, 860)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(DownloaderPanel(context=context), "Downloader")
        self.setCentralWidget(self._tabs)

    def closeEvent(self, event) -> None:
        for index in range(self._tabs.count()):
            panel = self._tabs.widget(index)
            shutdown = getattr(panel, "shutdown", None)
            if callable(shutdown):
                shutdown()
        super().closeEvent(event)


def main() -> int:
    try:
        app = QApplication(sys.argv)
    except Exception as exc:
        print(f"Failed to start Qt application: {exc}", file=sys.stderr)
        return 1

    if STYLESHEET_PATH.exists():
        app.setStyleSheet(STYLESHEET_PATH.read_text(encoding="utf-8"))

    context = AppContext()          # ensure_config + load + resolve  (was in the panel)
    init_db(context.db_path)        # schema + migration              (was in the panel)

    window = AppShell(context)
    window.show()
    return app.exec() if QT_API == "PyQt6" else app.exec_()
```

Adding tab two is then three lines: an import, a constructor call, an `addTab`. That is the whole
point of the exercise.

Every path here is anchored to `__file__`, never to the working directory, which the codebase
already gets right through `PACKAGE_ROOT` in `config_manager.py`. `[G §10]`

---

## 6. Which work pattern the downloader uses

Guide §5 offers five. The downloader is **Pattern C, background thread worker**, and stays there:
`TaskThread` is a `QThread` that emits `log_message`, `load_complete`, `work_complete` and
`work_failed`, and never touches a widget. Inside it, `download_many` and the metadata fetch fan
out over a `ThreadPoolExecutor`, and `yt-dlp` itself runs as a `subprocess.Popen` whose handle is
registered with the `CancellationToken` so Stop terminates it.

Pattern A, a bundled native tool driven by `QProcess`, does not apply: `yt-dlp` is resolved from
the environment, not committed under a `tools/` directory, and the retry, cookie-fallback and
`HOME`-override logic in `video_info_extractor.py` needs Python around each launch.

Future tabs should pick deliberately. The Logs, Settings and Database tabs from FSD `1.8.2` are
all **Pattern E, in-process compute**: a SQLite read of a few hundred milliseconds, rendered
straight into a table. The phone-backup import tab is Pattern E if it parses one file, Pattern C
if it then downloads.

---

## 7. The cross-panel contract

Guide §8, translated to this project. The database is the contract.

| Artifact | Written by | Read by | Shape |
|---|---|---|---|
| `sources`, `youtube_video_information` | Downloader listing | Downloader cache lookup, future Database tab | relational rows keyed by `video_id` |
| `downloads` | Downloader | future Logs and Database tabs | one row per attempted download |
| `errors` | every layer | future Logs tab | message plus stack trace |
| `user_actions` | Downloader buttons | future Logs tab | action plus timestamp |
| `settings_changes` | `AppContext.reload_if_changed` | future Logs and Settings tabs | key, old value, new value |
| `config.json` | future Settings tab | every panel, through `AppContext` | flat JSON object |

Three rules apply to every future reader, taken from guide §8:

1. **Never assume a row exists.** An empty table is the normal first-run state. Show a placeholder,
   do not raise.
2. **Read every config key with a default.** `config.get(key, fallback)`, never a bare subscript.
   `ensure_config` backfills missing keys, but a panel must survive a hand-edited file.
3. **One bad row must not abort a view.** Read defensively per row, count the failures, report
   both counts.

When the Settings tab writes `config.json`, it calls `AppContext.reload_if_changed()`, which emits
`config_changed`. Panels connect to that signal. No panel imports another panel. `[G §1 rule 2]`

---

## 8. Tab roster and order

Guide §4 Step 3: tab order is workflow order, labels under 24 characters, named for what the
operator gets. The roster for FSD `1.8.2`, left to right:

| Position | Label | Feature package | Status |
|---|---|---|---|
| 1 | `Import` | `features/importer/` | **built in 0.5.0** — parse a phone-backup file into targets or rows |
| 2 | `Downloader` | `features/downloader/` | **built in 0.4.0** |
| 3 | `Library` | `features/library/` | **built in 0.5.0** — browse and delete cached rows, with search and filters |
| 4 | `Logs` | `features/logs/` | **built in 0.5.0** — downloads, errors and stack traces |
| 5 | `Settings` | `features/settings/` | **built in 0.5.0** — edit `config.json` from the UI |

All five are mounted. The shell opens on `Downloader`, because that is the tab an operator reaches for most.

---

## 9. Risks and things that will bite

- **The stylesheet is the visible half of this change.** Without C5 the app looks broken on first
  run even though every behaviour is correct. Do C5 in the same commit, not after.
- **`ui/qt.py` must export every name the panels use.** A missing export surfaces as a
  `NameError` at construction, which under guide §3 rule 6 takes down the whole window. Import the
  module and diff its `dir()` against the old import block before deleting `main_window.py`.
- **Deleting the shims is the only breaking change here.** Any personal script outside this repo
  doing `from yt_aio.services import download_many` stops working. In-repo, nothing does.
- **`init_db` moving to `main()` changes failure timing.** A corrupt or locked database now fails
  before the window appears, with a traceback on the terminal instead of a message box. That is
  the correct trade: guide §3 rule 6 is about panels, and a database the app cannot open is not a
  condition to start up into. Wrap it and print a clear line naming the path.
- **`QMessageBox` from a background tab.** Once tab two exists, an error box raised by the
  downloader while the user is on another tab is disorienting. Guide §11 already says the console
  is the record and the box is only for a decision; keep boxes for terminal failures only.

---

## 10. Expected output after the changes

### 10.1 The tree

```
$ find yt_aio -name '*.py' | sort
yt_aio/__init__.py
yt_aio/__main__.py
yt_aio/application/__init__.py
yt_aio/application/context.py
yt_aio/application/db/__init__.py
yt_aio/application/db/database_manager.py
yt_aio/application/features/__init__.py
yt_aio/application/features/downloader/__init__.py
yt_aio/application/features/downloader/panel.py
yt_aio/application/jobs.py
yt_aio/application/shell.py
yt_aio/application/ui/__init__.py
yt_aio/application/ui/qt.py
yt_aio/application/utils/__init__.py
yt_aio/application/utils/config_manager.py
yt_aio/application/utils/download_manager.py
yt_aio/application/utils/shared.py
yt_aio/application/utils/video_info_extractor.py
```

Five files gone, five files added, one 560-line module split into three.

### 10.2 The window

```
┌──────────────────────────────────────────────────────────────────────┐
│ YT AIO 0.4.0 — ItzzInfinity                                    _ □ ✕ │
├──────────────┬───────────────────────────────────────────────────────┤
│ ▎Downloader  │                                                       │  <- tab bar, one tab,
├──────────────┴───────────────────────────────────────────────────────┤     styled dark
│  Log                    ║  ┌─ Source ─────────────────────────────┐  │
│  ┌───────────────────┐  ║  │ Channel or Playlist [______________] │  │
│  │[10:02:11] [INFO]  │  ║  │  ( )Channel ( )Playlist (•)Audio ... │  │
│  │ YT AIO 0.4.0 ready│  ║  └──────────────────────────────────────┘  │
│  │[10:02:40] [TX]    │  ║  ┌─ Task Status ────────────────────────┐  │
│  │ yt-dlp --flat-... │  ║  │ Idle. First click loads...           │  │
│  │[10:02:44] [RX]    │  ║  └──────────────────────────────────────┘  │
│  │ 412 entries       │  ║  ┌──────────────────────────────────────┐  │
│  └───────────────────┘  ║  │ Select │ ID │ Name │ Duration │ ...  │  │
│                         ║  └──────────────────────────────────────┘  │
│                         ║  [Download] [Stop] [Clear] [Config]        │
└──────────────────────────────────────────────────────────────────────┘
```

Identical to today apart from the tab strip and the severity tags in the log. The splitter, the
table, the quick-download box and the four buttons all keep their positions.

### 10.3 Behaviour that must not change

Every one of these is the acceptance bar for the migration. Nothing in Groups A to D touches the
download or extraction logic.

- `python3 -m yt_aio` starts the app and prints nothing on a healthy run.
- First Download click on a source loads the listing into the table; second click downloads the
  checked rows.
- A non-empty quick-download box still takes priority over the source field.
- Audio and video selection, the Brave cookie fallback, the `HOME` and `PYTHONPATH` handling, the
  flat-playlist streaming from FSD `1.8.1` and the parallel download pool are untouched.
- Stop still cancels within a couple of seconds by terminating the registered subprocesses.
- Config still opens in the system editor, and edits are still diffed into `settings_changes` on
  the next Download click.
- `config.json` keeps its relative `./db/yt_aio.db` and `./logs` values, still resolved from
  `application/`, so the base directory is still movable. FSD `1.7.1` is not regressed.

### 10.4 New behaviour

- Closing the window during a download cancels the job and waits for the thread instead of
  destroying a running `QThread`.
- A failure inside `ensure_config` or `init_db` is reported before the window opens, naming the
  path, rather than half-building a window.
- Log lines carry `[TX]`, `[RX]`, `[INFO]`, `[WARN]` or `[ERR]`.
- Adding tab two requires no edit to any existing panel.

### 10.5 Verification

```bash
python3 -c "import yt_aio.application.shell as s; print(s.AppShell, s.main)"
python3 -c "from yt_aio.application.features.downloader.panel import DownloaderPanel as P; \
            from PyQt6.QtWidgets import QWidget; print(issubclass(P, QWidget))"
python3 -m json.tool yt_aio/application/config/config.json > /dev/null && echo "config OK"
grep -rn "from .gui\|yt_aio.services\|main_window" --include='*.py' yt_aio/   # expect no output
python3 -m yt_aio
```

Expected: the class and function objects print, `True`, `config OK`, an empty grep, and a window
with one `Downloader` tab.

### 10.6 Smoke test, from guide §15

- [ ] App starts with no network, no `yt-dlp` on `PATH`, and no `yt_aio.db` present.
- [ ] The `Downloader` tab paints; no traceback on the terminal.
- [ ] Download with every field empty gives one console line, no traceback, no crash.
- [ ] A listing streams into the table while it runs, not all at once at the end.
- [ ] Stop mid-listing and mid-download returns the panel to a usable state within a few seconds.
- [ ] After a failure, Download is enabled again and Stop is disabled.
- [ ] The completion message names where the files went.
- [ ] Closing the window while idle exits cleanly; closing mid-download does not hang.

---

## 11. Out of scope

Not part of this migration, listed so they are not mistaken for omissions:

- Building the Import, Library, Logs or Settings panels. Those are FSD `1.8.2`; this plan only
  makes them cheap.
- Any change to `video_info_extractor.py`, `download_manager.py` or `database_manager.py` beyond
  imports and the console tags of item B6. The extraction, download and schema layers are already the
  correct shape, and no logic in them was touched.
- Bundling `yt-dlp` under a `tools/` directory as guide §14 describes for native tools.
- Replacing the `QThread` worker with a child-process worker, guide §5 Pattern B.
