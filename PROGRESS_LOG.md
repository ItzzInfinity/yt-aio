
# Progress Log

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
