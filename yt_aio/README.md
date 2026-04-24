# YT AIO GUI

PyQt desktop frontend for the existing YouTube automation scripts in this folder.

Current version: `0.2.1`

## What it does

- Loads a channel or playlist through `yt-dlp`
- Fetches per-video metadata and shows a selectable table
- Supports quick downloads from comma-separated YouTube links
- Downloads either audio or video
- Tries raw `yt-dlp` first, then falls back to Brave/browser cookies for YouTube bot checks
- Keeps the `yt_dlp` Python module available even when Brave cookie fallback switches `HOME`
- Writes operational logs to a sqlite database and live text output in the GUI
- Reads defaults from `yt_aio/config.json`

## Project Layout

- `yt_aio/gui.py`: PyQt window and worker-thread wiring
- `yt_aio/services.py`: yt-dlp listing and download logic
- `yt_aio/config.py`: config creation and loading
- `yt_aio/logging_db.py`: sqlite schema and inserts
- `yt_aio/config.json`: user-editable defaults
- `yt_aio/yt_aio.db`: sqlite log database

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
