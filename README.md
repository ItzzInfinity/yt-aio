# YT AIO GUI

PyQt desktop frontend for the existing YouTube automation scripts in this folder.

The window is a tab shell with six tabs: Import, Downloader, Library, Local Scan, Logs and Settings. Each one
is a self-contained package under `yt_aio/application/features/`.

Current version: `0.6.0`

## What it does

- Loads a channel or playlist through `yt-dlp`
- Fetches per-video metadata and shows a selectable table
- Supports quick downloads from comma-separated YouTube links
- Downloads either audio or video
- Tries raw `yt-dlp` first, then falls back to Brave/browser cookies for YouTube bot checks
- Keeps the `yt_dlp` Python module available even when Brave cookie fallback switches `HOME`
- Writes operational logs to a sqlite database and live text output in the GUI, tagged `[TX]`, `[RX]`, `[INFO]`, `[WARN]` and `[ERR]`
- Reads a folder of audio files already on disk and grades each one against the database
- Reads defaults from `yt_aio/application/config/config.json`

## Project Layout

- `yt_aio/application/shell.py`: `AppShell`, the only window, owns the tab bar and `main()`
- `yt_aio/application/context.py`: `AppContext`, the shared config and database handle passed to every panel
- `yt_aio/application/jobs.py`: the shared `QThread` runners every tab uses for background work
- `yt_aio/application/features/importer/`: the Import tab, its backup-file parsers and the OpenTune reader
- `yt_aio/application/features/downloader/panel.py`: the Downloader tab
- `yt_aio/application/features/library/panel.py`: the Library tab
- `yt_aio/application/features/local_scan/panel.py`: the Local Scan tab
- `yt_aio/application/features/logs/panel.py`: the Logs tab
- `yt_aio/application/features/settings/panel.py`: the Settings tab
- `yt_aio/application/db/queries.py`: the read and delete path the viewing tabs share
- `yt_aio/application/ui/qt.py`: the single PyQt6/PyQt5 fallback import site
- `yt_aio/application/ui/widgets.py`: the shared console and grid widgets
- `yt_aio/application/ui/styles.qss`: Qt stylesheet
- `yt_aio/application/utils/video_info_extractor.py`: yt-dlp listing and metadata logic
- `yt_aio/application/utils/download_manager.py`: download orchestration and retries
- `yt_aio/application/utils/config_manager.py`: config creation, loading, and path migration
- `yt_aio/application/db/database_manager.py`: sqlite schema and inserts
- `yt_aio/application/config/config.json`: user-editable defaults
- `yt_aio/application/db/yt_aio.db`: sqlite log database
- `yt_aio/application/logs/`: reserved folder for future file-based logs

Path notes:
- `log_file_path`, `history_file_path`, and `logs_directory` are stored as relative paths in `config.json`
- Those paths are resolved at runtime from `yt_aio/application`, so the whole base directory can be moved without rewriting machine-specific paths

## Run

From the directory that contains the `yt_aio` package:

```bash
python3 -m yt_aio
```

If `PyQt6` is not installed, the app falls back to `PyQt5`. That fallback lives in one place,
`yt_aio/application/ui/qt.py`, and every module imports its Qt names from there.

## Adding a tab

1. Create `yt_aio/application/features/<feature>/` with an empty `__init__.py` and a `panel.py`.
2. Write a `QWidget` subclass whose constructor takes no required positional argument, does no blocking work,
   and accepts the shared `AppContext` as a keyword argument.
3. Register it in `AppShell.__init__` with one `addTab` call, placed in workflow order.

The full contract, including the optional `shutdown()` hook the shell calls on close, is in
[Docs/05_TAB_SHELL_MIGRATION.md](Docs/05_TAB_SHELL_MIGRATION.md).

## The tabs

- **Import** reads a backup file exported by a phone app and turns it into a list of videos. Format is detected from
  the file's own bytes, so SQLite databases, ZIP archives, JSON, CSV and plain lists of links all work. From there the
  items can be merged into the database or downloaded directly.
- **Downloader** is the original interface: load a channel or playlist, tick rows, download.
- **Library** browses the cached video rows with search, source and status filters, and deletes the rows you tick.
  Deleting metadata never touches the download history or the files on disk.
- **Logs** is a read-only view of the download history, the errors with their stack traces, your button presses, the
  settings changes and the version history.
- **Settings** edits `config.json` from a form built out of the defaults, so a new setting appears here on its own.
  Saving records every change in the database, with credential-shaped values redacted.

## Notes

- The first `Download` click on a channel or playlist loads the listing into the table.
- After selecting rows, click `Download` again to start the actual download.
- If the quick-download box contains valid URLs, that input takes priority.
- The package now resolves runtime paths relative to `yt_aio/application`, so it can be moved without editing hardcoded project directories.
