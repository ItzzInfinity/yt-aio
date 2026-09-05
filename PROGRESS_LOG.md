
# Progress Log

## 2026-09-04 22:53 IST — version 0.6.0

Worked the batch of five items at the end of FSD 1.8.2.

- Added the `Local Scan` tab (`features/local_scan/panel.py`). It walks a chosen folder and its
  subfolders, reads tags through mutagen with ffprobe as the fallback and the file name as the last
  resort, and grades every file against the database as `In database`, `Probable match`, `Title clash`
  or `New`. Grading rather than a yes/no is deliberate: a wrong "already have it" would stop a
  download the operator wanted.
- Added `utils/local_library.py` for the scanning and tag reading, and `db/local_files.py` for the
  matching and the `local_files` table. A rescan reports the files that were not there last time and
  forgets the ones that have gone. No file on disk is ever modified.
- Fixed two defects in title normalisation found while testing: Python's `\w` excludes combining
  marks, which split every Bengali title into single letters, and "song" and "full" were being
  stripped as noise, which collapsed "Full Moon" and "Moon" into the same title.
- Added `features/importer/opentune.py`, a schema-aware reader for OpenTune / InnerTune backups,
  after reading the schema in `Docs/song_db_erd.html`. The generic table scan was importing
  `related_song_map`, which is the recommendation graph rather than saved music, and could not
  attach an artist to anything because artist names are only reachable through `song_artist_map`.
  Split `ImportedItem` out into `features/importer/models.py` so both readers share one row type.
- Added duration and channel filters plus per-column sorting to the Library, Import and Local Scan
  viewers. Library and Local Scan sort in SQL because they are paged; Import sorts in memory. Import's
  tick boxes are now keyed by video id, so a selection survives a change of filter or sort.
- Added `SETTING_SUGGESTIONS` and `SETTING_RANGES` to `utils/config_manager.py`. The Settings tab
  turns 20 text fields into editable drop-downs and gives 5 numeric fields a real range and a
  typical-value tool tip. Anything typed is still accepted.
- Wrote `Docs/06_YTDLNIS_APPROACH.md` after reading `YTDLPUtil.kt` in `~/Downloads/ytdlnis` 1.8.9.1:
  the commands it builds, the eight changes worth making to our code with the file and function for
  each, and the four things not worth copying. Nothing from it was implemented; the item asked what
  to change.
- Verified against the real 3462-row database and a generated fixture set: all six tabs construct and
  paint, every sortable column sorts, all seven local-scan match cases classify correctly, and the
  settings round trip reports no spurious changes.

## 2026-03-28 17:40 IST

- Created the `yt_aio` package as a dedicated GUI project area under `my_music/automation`.
- Added config bootstrap logic that creates `config.json` and merges in any missing defaults.
- Added sqlite logging tables for downloads, video metadata, user actions, errors, and app version.
- Implemented yt-dlp service helpers for channel/playlist listing, quick-link validation, streaming downloads, and cancellation.
- Implemented a PyQt5/PyQt6-compatible GUI with live log output, source controls, a selectable results table, quick-download input, and control buttons.

## 2026-03-28 20:55 IST

- Investigated FSD section 1.6 against `yt_aio.db` and confirmed two active issues: repeated `list_videos` timeout errors and `downloads.title` being stored as `NULL`.
- Fixed the listing path so yt-dlp JSON subprocesses are drained with `communicate()` instead of blocking on full pipes until timeout.
- Added flat-playlist fallback rows so a channel or playlist can still populate the selectable table even when per-video metadata fails.
- Fixed download logging so titles are resolved and written into the `downloads` table instead of `NULL`.
- Backfilled the existing null `downloads.title` row in `yt_aio.db` using the saved file path.

## 2026-03-31 19:35 IST

- Resolved FSD issue 1.6.3 by adding visible task-state feedback in the GUI: status text, an indeterminate progress bar, and explicit `Loading...` / `Downloading...` button states while work is running.
- Resolved FSD issue 1.6.4 by migrating the sqlite layer toward a relational model with a `sources` table plus relational `source_id`, `video_id`, and `video_info_id` links on existing tables.
- Added relational backfill for the existing `yt_aio.db` so legacy cached video rows and download rows are connected where the source and video could be inferred safely.
- Resolved FSD issue 1.6.5 by adding DB-backed cache reads before per-video metadata fetches, so already-known videos are loaded from `youtube_video_information` instead of being fetched again.

## 2026-04-24 16:25 IST

- Read the latest `errors` rows from `yt_aio.db` and confirmed the active recurring failure was `ModuleNotFoundError: No module named 'yt_dlp'` during both `list_videos` and `download`.
- Reproduced the failure path and traced it to the Brave cookie fallback changing `HOME`, which broke the `/home/itzzinfinity/.local/bin/yt-dlp` wrapper's access to the user-site `yt_dlp` install.
- Hardened the launcher to prefer `/usr/bin/python3 -m yt_dlp` when the module is available in the running app environment.
- Preserved the active `yt_dlp` import path in `PYTHONPATH` whenever the auth fallback overrides `HOME`, so browser-cookie retries keep working.
- Verified the fix locally with a Brave-cookie-backed live `-F` request for `https://www.youtube.com/watch?v=7V64PG7SnOE`, which now completes successfully and returns the format list.

## 2026-04-24 16:55 IST

- Implemented FSD section `1.7 Modularity` by reorganizing the package into `yt_aio/application/ui`, `yt_aio/application/utils`, `yt_aio/application/db`, `yt_aio/application/config`, and `yt_aio/application/logs`.
- Split the old monolithic modules into focused files: UI in `main_window.py`, config handling in `config_manager.py`, metadata extraction in `video_info_extractor.py`, download orchestration in `download_manager.py`, and sqlite access in `database_manager.py`.
- Moved runtime assets to portable package-relative locations: `application/config/config.json` and `application/db/yt_aio.db`.
- Added compatibility wrappers at the old module paths so `run_yt_aio_gui.py` and existing imports still work during the transition.
- Updated the stylesheet handling to load from `application/ui/styles.qss` and bumped the package version to `0.3.0`.

## 2026-04-24 17:10 IST

- Implemented FSD section `1.7.1` by changing `config.json` to store `log_file_path`, `history_file_path`, and `logs_directory` as relative paths instead of machine-specific absolute paths.
- Added runtime path resolution in `config_manager.py` so relative config paths are resolved from the `yt_aio/application` base directory.
- Updated the UI/runtime flow to keep raw config values for comparison and display while using resolved absolute paths internally for DB and filesystem operations.
- Updated the download and yt-dlp helpers so relative path values like `cookie_file` or a relative download directory also resolve correctly.
- Bumped the package version to `0.3.1`.

## 2026-05-23 20:30 IST

- Implemented FSD point 1.8.1 (Strategy B) for scalable channel and playlist fetching.
- Switched listing to a single streaming subprocess `yt-dlp --flat-playlist -j` that processes JSON lines as they arrive for instant visual feedback.
- Completely removed `like_count`, `dislike_count`, `comment_count`, and `view_count` columns from the sqlite database schema to minimize database insertion and query overhead.
- Added a safe automatic schema migration in `init_db` that drops these columns from existing user databases.
- Updated metadata logging functions to batch write streamed records in a single database transaction.
- Added the `is_full_metadata` column to track partial vs full metadata fetches, verifying caching states with boolean logic instead of checking if numerical columns are `None`.
- Bumped package version to `0.3.2`.

## 2026-09-02 21:10 IST

- Implemented FSD point `1.7.2` by reading `dev_guide.md` and writing `Docs/05_TAB_SHELL_MIGRATION.md`.
- Mapped every placeholder in `dev_guide.md` onto this tree: `suite/` is `yt_aio/application`, the missing `shell.py`
  is the `AppShell` plus tab bar, and the guide's file-based cross-panel contract is `yt_aio.db` here.
- Listed the changes needed to move the current window into one `Downloader` tab: extract the PyQt6/PyQt5
  compatibility block into `ui/qt.py`, lift config and database state out of the window into an `AppContext` helper,
  split `main_window.py` into `features/downloader/panel.py` and `features/downloader/worker.py`, and add
  `application/shell.py` as the only `QMainWindow`.
- Recorded the panel-contract violations to fix while moving: `QMainWindow` subclassing, `setStyleSheet` on the panel,
  `ensure_config` and `init_db` running inside the constructor, `assert` used for validation in the worker, the mirrored
  `set_busy_state` and `set_idle_state` pair, and the absent `closeEvent` that destroys a running `QThread`.
- Recorded one correctness bug found in the code being moved: `on_load_complete` rebuilds the cache key by re-reading
  the source widgets at completion time, so editing the source field during a listing files the result under the wrong key.
- Documented the expected output after the migration: the new tree, the window with a single styled tab, the behaviour
  that must stay identical, the four new behaviours, verification commands, and the guide's smoke-test checklist.
- Fixed the roster and left-to-right order for the FSD `1.8.2` tabs: Import, Downloader, Library, Logs, Settings.
- No application code changed, so the version stays `0.3.2`. The bump to `0.4.0` belongs to the migration commit itself.

## 2026-09-02 21:30 IST

- Executed the FSD `1.7.2` plan in `Docs/05_TAB_SHELL_MIGRATION.md`: the app is now a tab shell and the existing UI is
  the `Downloader` tab. Version bumped to `0.4.0` and recorded in the `yt_aio_version` table.
- Added `application/shell.py` with `AppShell`, the only `QMainWindow` in the process, owning a `QTabWidget` and `main()`.
- Added `application/context.py` with `AppContext`, holding the config path, raw config, resolved config and database
  path for the whole process, plus a `config_changed` signal so future tabs never call each other.
- Added `application/ui/qt.py` as the single PyQt6-with-PyQt5-fallback import site, so a new panel does not re-create
  the fallback block.
- Split `application/ui/main_window.py` into `features/downloader/panel.py` and `features/downloader/worker.py`, and
  deleted the old module.
- `MainWindow(QMainWindow)` became `DownloaderPanel(QWidget)`: no window title, no resize, no `setStyleSheet` on
  itself, and no `ensure_config` or `init_db` in the constructor. Both now run in `main()` before any panel is built.
- Folded `set_busy_state` and `set_idle_state` into one `_set_busy`, and added the table to what it disables so the
  selection cannot change during a running download.
- Fixed a real bug found while moving the code: `on_load_complete` rebuilt the cache key by re-reading the source
  widgets at completion time, so editing the source field during a listing filed the result under the wrong key and
  the next click could download the previous source. The kind and value now travel on the `load_complete` signal.
- Added `shutdown()` on the panel and a `closeEvent` on the shell, so closing the window during a download cancels the
  job and waits for the thread instead of destroying a running `QThread`.
- Adopted the `[TX]` `[RX]` `[INFO]` `[WARN]` `[ERR]` console vocabulary, tagged at the source in the panel and in the
  utils layer. `run_streaming_command` now logs one `[TX]` line per launched subprocess with the program name and the
  target only, never the full argument list, so cookie and visitor-data values are not written to the log.
- Deleted the transitional compatibility wrappers `yt_aio/gui.py`, `services.py`, `config.py`, `logging_db.py` and
  `run.py`, and reduced `yt_aio/__init__.py` to metadata. `python3 -m yt_aio` is unchanged.
- Added `QTabWidget` and `QTabBar` rules to `styles.qss`, since the sheet had none and a tab bar would otherwise have
  rendered in the default light palette.
- Verified headless with the offscreen Qt platform: the panel constructs against a context pointing at non-existent
  paths, the shell shows one `Downloader` tab, the busy and idle transitions are correct on both the completion and
  failure paths, an empty Download gives one warning line and no traceback, a real `QThread` job populates the table
  through the widened `load_complete` signal, and the window closes cleanly.

## 2026-09-02 22:05 IST

- Implemented FSD point `1.8.2` (Tabs as Containers). Version bumped to `0.5.0`. The window now carries five tabs in
  workflow order: Import, Downloader, Library, Logs and Settings, opening on Downloader.
- Added `application/features/importer/` with `parsers.py` and `panel.py`. The parser detects the format from the
  file's own bytes rather than its extension, and handles SQLite databases, ZIP archives, JSON, CSV and plain text.
  A NewPipe-shaped export, millisecond durations and `mm:ss` durations all parse correctly.
- The Import tab either merges parsed items into `youtube_video_information` under an `import:<file>` source, or
  downloads them directly. The merge never overwrites a richer stored record with a sparser backup entry.
- Added `application/features/library/panel.py`: paged browsing of the cached rows with search, source and status
  filters, and deletion of ticked rows behind a confirmation that names the targets and states what is kept.
  Deleting metadata clears the download rows' link to it rather than destroying the download history.
- Added `application/features/logs/panel.py`: a read-only view over the download history, errors with their stack
  traces, user actions, settings changes and the version table, with search, paging and a record detail pane.
- Added `application/features/settings/panel.py`: `config.json` edited from a form generated out of
  `build_default_config`, so a new setting appears with no change to the panel. Saving writes atomically, records
  every change through `AppContext.reload_if_changed`, and tells the other tabs through `config_changed`.
- Added `application/db/queries.py` for the read and delete path, keeping `database_manager.py` to the schema and the
  downloader's write path. Table and column names come only from the view specs, never from user input.
- Moved `TaskThread` from `features/downloader/worker.py` to the shared `application/jobs.py` once the Import tab
  became a second caller, and added `CallableThread` there for the parse and merge jobs. Panels share the runner
  rather than importing each other.
- Added `application/ui/widgets.py` with `ConsoleView` and `RecordTable`, so a new tab does not copy a first tab's
  widget code. The Downloader now uses `ConsoleView` too.
- Redacted credential-shaped config values, `youtube_visitor_data` and `proxy`, from the `settings_changes` table and
  the console. The real value is still written to `config.json`; only the audit record is masked.
- Every read is paged in SQL. The 3462-row cache is never loaded whole, and the panels defer their first database read
  to their first paint so no constructor touches the disk.
- Verified headless under both bindings: all five tabs build under PyQt6 and under PyQt5, the Logs views page and
  filter, the Library filters and paging are correct, deletion is refused with nothing ticked and confirmed with
  specifics otherwise, the Settings form has 32 editors and its save round-trips through the config file and the
  change log with the token redacted, and the Import tab parses a ZIP fixture and merges 7 videos.
- The destructive tests ran against a copied config and a copied database. One earlier test run leaked 7 fixture rows
  into the real database, because saving settings correctly makes AppContext re-derive its database path from the
  config; those rows, their source row and the stray user action were removed and the counts verified back at 3462.
