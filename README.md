# YT AIO GUI

PyQt desktop frontend for the existing YouTube automation scripts in this folder.

Current version: `0.3.1`

## What it does

- Loads a channel or playlist through `yt-dlp`
- Fetches per-video metadata and shows a selectable table
- Supports quick downloads from comma-separated YouTube links
- Downloads either audio or video
- Tries raw `yt-dlp` first, then falls back to Brave/browser cookies for YouTube bot checks
- Keeps the `yt_dlp` Python module available even when Brave cookie fallback switches `HOME`
- Writes operational logs to a sqlite database and live text output in the GUI
- Reads defaults from `yt_aio/application/config/config.json`

## Project Layout

- `yt_aio/application/ui/main_window.py`: PyQt window and worker-thread wiring
- `yt_aio/application/ui/styles.qss`: Qt stylesheet
- `yt_aio/application/utils/video_info_extractor.py`: yt-dlp listing and metadata logic
- `yt_aio/application/utils/download_manager.py`: download orchestration and retries
- `yt_aio/application/utils/config_manager.py`: config creation, loading, and path migration
- `yt_aio/application/db/database_manager.py`: sqlite schema and inserts
- `yt_aio/application/config/config.json`: user-editable defaults
- `yt_aio/application/db/yt_aio.db`: sqlite log database
- `yt_aio/application/logs/`: reserved folder for future file-based logs
- `yt_aio/gui.py`, `yt_aio/services.py`, `yt_aio/config.py`, `yt_aio/logging_db.py`: compatibility wrappers for the old import paths

Path notes:
- `log_file_path`, `history_file_path`, and `logs_directory` are stored as relative paths in `config.json`
- Those paths are resolved at runtime from `yt_aio/application`, so the whole base directory can be moved without rewriting machine-specific paths

## Run

From `/home/itzzinfinity/Downloads/my_music/automation`:

```bash
python3 -m yt_aio
```

If `PyQt6` is not installed, the app falls back to `PyQt5`.

## Notes

- The first `Download` click on a channel or playlist loads the listing into the table.
- After selecting rows, click `Download` again to start the actual download.
- If the quick-download box contains valid URLs, that input takes priority.
- The package now resolves runtime paths relative to `yt_aio/application`, so it can be moved without editing hardcoded project directories.
