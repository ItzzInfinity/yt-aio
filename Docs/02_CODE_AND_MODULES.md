# 📚 Code and Modules Guide: Beginner Reference

This guide provides a walk-through of the codebase components, a mapping cheatsheet for key operations, and simplified pseudo-code explaining how primary functions operate behind the scenes.

---

## 1. Directory to Code Mapping Cheatsheet

For a beginner, finding code inside modular folders can be tricky. Use this reference directory:

```
yt_aio/
├── __main__.py                      # Entry point: python3 -m yt_aio
├── run.py                           # Legacy entry script
└── application/                     # Parent directory of all modular logic
    ├── shell.py                      # AppShell: the one window and the tab bar, plus main()
    ├── context.py                    # AppContext: shared config, db path, config_changed signal
    ├── jobs.py                       # TaskThread and CallableThread, shared by every tab
    │
    ├── features/                     # One subpackage per tab
    │   ├── importer/
    │   │   ├── panel.py              # ImportPanel: the Import tab
    │   │   └── parsers.py            # Backup file format detection and parsing
    │   ├── downloader/
    │   │   └── panel.py              # DownloaderPanel: the Downloader tab
    │   ├── library/
    │   │   └── panel.py              # LibraryPanel: browse and delete cached rows
    │   ├── logs/
    │   │   └── panel.py              # LogsPanel: read-only history, errors, actions
    │   └── settings/
    │       └── panel.py              # SettingsPanel: edit config.json from a form
    │
    ├── config/
    │   └── config.json              # Default user settings
    │
    ├── db/
    │   ├── database_manager.py      # SQLite schema and the downloader's write path
    │   └── queries.py               # The read and delete path the viewing tabs share
    │
    ├── ui/
    │   ├── qt.py                    # The single PyQt6/PyQt5 fallback import site
    │   ├── widgets.py               # ConsoleView and RecordTable, shared by the tabs
    │   └── styles.qss               # Application styling stylesheet, applied once by the shell
    │
    └── utils/
        ├── config_manager.py        # Validates config.json, translates relative paths
        ├── download_manager.py      # Spawns parallel yt-dlp download streams
        ├── video_info_extractor.py  # Builds yt-dlp CLI arguments, caches query results
        └── shared.py                # Dataclasses and thread-safe cancellation handles
```

---

## 2. Shell Layer: `application/shell.py`

`AppShell` is the only `QMainWindow` in the process. It does three things and nothing else: import the panel
classes, construct them, and add each one to the `QTabWidget` with a label. It also applies `styles.qss` once at
application level and calls each panel's `shutdown()` on close so no `QThread` is destroyed while running.

`main()` prepares the configuration and the database schema **before** any panel is built, so a panel constructor
never does blocking or failure-prone work. Adding a tab is an import, a constructor call and one `addTab` line.

---

## 3. UI Presentation Layer: `application/features/downloader/panel.py`

File Scheme Link: [panel.py](file:///home/itzzinfinity/GitHub/yt_aio/yt_aio/application/features/downloader/panel.py)

> The window itself lives in [shell.py](file:///home/itzzinfinity/GitHub/yt_aio/yt_aio/application/shell.py). This module is one tab inside it. See [05_TAB_SHELL_MIGRATION.md](05_TAB_SHELL_MIGRATION.md) for the panel contract a new tab must satisfy.

This module handles the PyQt layout and captures button click events. It communicates with the backend files via background **worker threads**.

### Class: `DownloaderPanel`
This is the Downloader tab. It inherits from `QWidget`, never `QMainWindow`: the shell owns the window.

#### Pseudo-code: `_start()`
Triggered when the user clicks the main **Download** button. It determines whether to fetch video list details or begin downloading files.

```python
def _start(self):
    # 1. Stop if a background task is already executing
    if self.is_busy():
        self.log_to_box("Warning: Task already running. Click Stop first.")
        return

    # 2. Check if the "Quick Download" URL box contains data
    quick_text = self.quick_download_edit.text().strip()
    if quick_text:
        urls = parse_comma_separated_urls(quick_text)
        if urls:
            # Bypass table and download direct URLs
            self.set_ui_state(BUSY_DOWNLOADING)
            self.start_download_task(targets=urls, source_name="Quick Download")
            return
            
    # 3. Check if table items are already loaded for the current source
    current_source = self.source_input_edit.text().strip()
    source_kind = "channel" if self.channel_radio.isChecked() else "playlist"
    
    if self.loaded_key == (source_kind, current_source):
        # We already have items displayed in the table grid!
        selected_items = self.get_checked_rows_from_table()
        if not selected_items:
            self.log_to_box("Error: No items selected. Check boxes next to titles.")
            return
            
        self.set_ui_state(BUSY_DOWNLOADING)
        self.start_download_task(targets=selected_items, source_name=self.loaded_source_name)
    else:
        # No items loaded yet for this input. Load metadata first!
        if not current_source:
            self.log_to_box("Error: Please enter a channel or playlist ID/URL.")
            return
            
        self.set_ui_state(BUSY_LOADING)
        self.start_load_task(source_kind, current_source)
```

---

### Class: `TaskThread`
Lives in [jobs.py](file:///home/itzzinfinity/GitHub/yt_aio/yt_aio/application/jobs.py), shared by the Downloader and Import tabs. Inherits from `QThread`. Runs operations on a background OS thread to keep the main GUI window responsive.

#### Pseudo-code: `run()`
Main loop of the worker thread. Runs either metadata fetching or file downloading.

```python
def run(self):
    try:
        if self.action == "load":
            # Extract arguments
            kind = self.args["source_kind"]
            val = self.args["source_value"]
            
            # Fetch listing
            video_items, channel_name = list_videos(
                source_kind=kind,
                source_value=val,
                config=self.config,
                db_path=self.db_path,
                logger=self.emit_log_signal,  # Send log string to UI slot
                token=self.cancel_token        # Check for cancellation
            )
            
            # Emit results back to main thread
            self.load_complete.emit(video_items, channel_name)
            
        elif self.action == "download":
            targets = self.args["targets"]
            media_type = self.args["media_type"]
            source_name = self.args["source_name"]
            
            # Download files
            summary = download_many(
                targets=targets,
                media_type=media_type,
                config=self.config,
                db_path=self.db_path,
                logger=self.emit_log_signal,
                token=self.cancel_token,
                source_name=source_name
            )
            
            self.work_complete.emit(summary)
            
    except Exception as e:
        # Catch errors thread-safely and alert UI
        self.work_failed.emit(str(e))
```

---

## 4. Metadata Extraction Module: `application/utils/video_info_extractor.py`

File Scheme Link: [video_info_extractor.py](file:///home/itzzinfinity/GitHub/yt_aio/yt_aio/application/utils/video_info_extractor.py)

This module builds CLI commands for `yt-dlp` and parses JSON outputs.

#### Pseudo-code: `list_videos()`
Scrapes video indexes from a channel or playlist with cache checking.

```python
def list_videos(source_kind, source_value, config, db_path, logger, token):
    # 1. Resolve source input to standard YouTube URL
    url = resolve_source_url(source_kind, source_value)
    
    # 2. Store source URL in database to get a unique source_id
    source_id = db_upsert_source(db_path, source_kind, source_value, url)
    
    # 3. Perform a fast flat playlist dump (only gets IDs & titles, no detailed streams)
    logger("Fetching flat playlist details via yt-dlp...")
    flat_cmd = ["yt-dlp", "--flat-playlist", "--dump-single-json", url]
    flat_json = run_json_command(flat_cmd, config, token)
    
    entries = flat_json.get("entries", [])
    logger(f"Scraped {len(entries)} video keys. Checking local cache...")
    
    # 4. Search local SQLite cache for already fetched videos
    found_ids = [item["id"] for item in entries]
    cached_map = db_get_cached_videos(db_path, found_ids)
    
    # 5. Extract detailed metadata for uncached videos in parallel
    missing_ids = [vid for vid in found_ids if vid not in cached_map]
    logger(f"Cache miss: Fetching fresh details for {len(missing_ids)} videos...")
    
    fetched_metadata = {}
    # Spawn 4 parallel thread workers
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_video_metadata, vid, config, token): vid for vid in missing_ids}
        
        for fut in as_completed(futures):
            vid = futures[fut]
            try:
                meta = fut.result()
                fetched_metadata[vid] = meta
                
                # Write to DB cache immediately
                db_cache_video_metadata(db_path, source_id, meta)
            except Exception as err:
                logger(f"Warning: Failed to fetch metadata for {vid}: {err}")
                
    # 6. Rebuild final VideoItem list
    final_items = []
    for entry in entries:
        vid = entry["id"]
        if vid in cached_map:
            final_items.append(convert_cache_to_item(cached_map[vid]))
        elif vid in fetched_metadata:
            final_items.append(convert_meta_to_item(fetched_metadata[vid]))
        else:
            final_items.append(convert_flat_to_fallback_item(entry))
            
    source_name = final_items[0].channel_name if final_items else "Unknown"
    return final_items, source_name
```

---

## 5. Download Execution Module: `application/utils/download_manager.py`

File Scheme Link: [download_manager.py](file:///home/itzzinfinity/GitHub/yt_aio/yt_aio/application/utils/download_manager.py)

Manages download execution pools and runs CLI stream download tasks.

#### Pseudo-code: `download_many()`
Takes a list of checked target videos and runs downloads concurrently.

```python
def download_many(targets, media_type, config, db_path, logger, token, source_name):
    # Determine parallel limits (defaults to number of CPU cores minus 2)
    max_workers = config.get("max_concurrent_downloads", max(1, cpu_count() - 2))
    logger(f"Spawning download pool with {max_workers} threads...")
    
    success = 0
    failure = 0
    
    # Executing parallel operations
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(download_one, target, media_type, config, db_path, logger, token, source_name): target 
            for target in targets
        }
        
        for fut in as_completed(futures):
            target = futures[fut]
            try:
                ok = fut.result()
                if ok:
                    success += 1
                else:
                    failure += 1
            except Exception as e:
                logger(f"Fatal error on {target.title}: {e}")
                failure += 1
                
    summary = f"Download finished: {success}/{len(targets)} completed successfully"
    if failure > 0:
        summary += f" ({failure} failed)"
    return summary
```

#### Pseudo-code: `download_one()`
Downloads a single stream and logs results. It implements the anti-bot cookie fallback block.

```python
def download_one(target, media_type, config, db_path, logger, token, source_name):
    title = target.title or "Unknown Video"
    logger(f"Start download: {title}")
    
    # 1. Build CLI arguments (no cookies first)
    cmd = build_yt_dlp_download_args(target.url, media_type, config, use_cookies=False)
    
    # 2. Run stream subprocess
    ret_code, stdout_lines = run_streaming_subprocess(cmd, token, logger)
    
    # 3. Check for bot challenge HTTP 429 errors
    output_log = "\n".join(stdout_lines)
    if "429" in output_log or "Too Many Requests" in output_log or "Sign in" in output_log:
        logger(f"Anti-bot block detected for '{title}'. Fetching browser cookies...")
        
        # Re-build command with browser cookies path parameters
        auth_cmd = build_yt_dlp_download_args(target.url, media_type, config, use_cookies=True)
        ret_code, stdout_lines = run_streaming_subprocess(auth_cmd, token, logger)
        output_log = "\n".join(stdout_lines)
        
    # 4. Check status code
    if ret_code == 0:
        saved_file = parse_saved_filepath(output_log)
        db_log_download_success(db_path, target, saved_file, media_type, source_name)
        logger(f"Completed: {title} saved successfully")
        return True
    else:
        err_msg = parse_stderr_error(output_log)
        db_log_download_failure(db_path, target, err_msg, media_type, source_name)
        logger(f"Failed download: {title} - {err_msg}")
        return False
```

---

## 6. Configuration Resolution: `application/utils/config_manager.py`

File Scheme Link: [config_manager.py](file:///home/itzzinfinity/GitHub/yt_aio/yt_aio/application/utils/config_manager.py)

#### Pseudo-code: `resolve_runtime_config()`
Ensures setting paths inside `config.json` resolve correctly relative to the project root directory.

```python
def resolve_runtime_config(raw_config):
    resolved = raw_config.copy()
    
    # Locate the absolute system path of the application base folder
    app_root = Path(__file__).parent.parent.absolute()
    
    # Specify keys that represent files or directories
    path_keys = ["log_file_path", "history_file_path", "logs_directory", "cookie_file"]
    
    for key in path_keys:
        if key in raw_config and raw_config[key]:
            path_val = Path(raw_config[key])
            
            # If the path is not absolute (starts with ./ or relative structure)
            if not path_val.is_absolute():
                # Merge relative path with the app base path
                resolved[key] = str((app_root / path_val).resolve())
                
    return resolved
```

**Next Guide:** Read **[03_DATABASE_AND_CONFIG.md](03_DATABASE_AND_CONFIG.md)**
