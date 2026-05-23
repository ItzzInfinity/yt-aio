# 🏗️ System Architecture

This document explains the high-level design and how components interact.

---

## Overall Architecture Pattern

The application follows a **layered architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────┐
│  PRESENTATION LAYER (UI)                            │
│  - MainWindow (PyQt widget tree)                    │
│  - TaskThread (worker thread orchestration)         │
│  - Signals/Slots (Qt event system)                  │
├─────────────────────────────────────────────────────┤
│  BUSINESS LOGIC LAYER (Utils)                       │
│  - video_info_extractor.py (yt-dlp commands)       │
│  - download_manager.py (orchestration)             │
│  - config_manager.py (settings management)         │
│  - shared.py (common types & utilities)            │
├─────────────────────────────────────────────────────┤
│  DATA ACCESS LAYER (Database)                       │
│  - database_manager.py (SQLite CRUD)               │
│  - yt_aio.db (SQLite file)                         │
├─────────────────────────────────────────────────────┤
│  EXTERNAL SERVICES                                  │
│  - yt-dlp (subprocess calls)                       │
│  - YouTube.com (via yt-dlp)                        │
│  - Browser Cookies (Brave, Firefox)                │
└─────────────────────────────────────────────────────┘
```

---

## Component Dependency Graph

```
┌─────────────────────────────────────────────────────────┐
│ main_window.py (UI Orchestration)                       │
├─────────────────────────────────────────────────────────┤
│ Imports:                                                │
│ ├─ TaskThread (local class)                            │
│ ├─ config_manager.py (config loading)                  │
│ ├─ database_manager.py (DB init, logging)              │
│ ├─ video_info_extractor.py (list_videos)               │
│ ├─ download_manager.py (download_many)                 │
│ └─ shared.py (VideoItem, CancellationToken)            │
└─────────────────────────────────────────────────────────┘
                        ↓
    ┌───────────────────┼───────────────────┐
    ↓                   ↓                   ↓
┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
│config_mgr    │  │video_extractor│ │download_manager  │
│              │  │              │  │                  │
│Responsibilities:
├─ Load JSON  │  ├─ Build yt-dlp │  ├─ Parallel DL    │
│  config     │  │  commands     │  │ execution       │
├─ Resolve   │  ├─ Fetch      │  ├─ Title         │
│  paths     │  │  metadata   │  │  resolution     │
├─ Provide   │  ├─ Cache      │  ├─ Bot challenge │
│  defaults  │  │  lookups    │  │  retry          │
└──────────────┘  ├─ DB logging  │  └──────────────────┘
                  └──────────────┘
                        ↓
                   ┌──────────────────┐
                   │shared.py         │
                   ├──────────────────┤
                   │├─ VideoItem      │
                   │├─ DownloadTarget │
                   │├─ CancellationToken
                   │└─ Utilities      │
                   └──────────────────┘
                        ↓
                   ┌──────────────────────────┐
                   │database_manager.py       │
                   ├──────────────────────────┤
                   │├─ init_db()              │
                   │├─ CRUD operations        │
                   │├─ Cache lookups          │
                   │└─ Error/audit logging    │
                   └──────────────────────────┘
```

---

## Threading Model

The application uses a **main thread + worker thread** model:

```
Main Thread (Qt Event Loop)
├─ Display UI
├─ Handle user clicks
├─ Accept user input
├─ Update widgets from signals
└─ Stay responsive

Worker Thread (TaskThread)
├─ One per task (load or download)
├─ Runs list_videos() or download_many()
├─ Emits signals → Main thread
├─ Respects CancellationToken
└─ Auto-cleanup after completion
```

### Signal Flow

```
User clicks "Download" button
         ↓
MainWindow.on_download_clicked()
         ↓
Emit: "Starting task..."
         ↓
Create TaskThread(action="load" or "download")
         ↓
taskThread.start() (spins up OS thread)
         ↓
TaskThread.run() (executes in worker thread)
│ - Calls list_videos() or download_many()
│ - Emits signals: log_message, progress_updated
│ - Catches exceptions
│ - Emits final: load_complete or work_complete
         ↓
Signals propagate to MainWindow slots (in main thread)
         ↓
MainWindow updates UI: table, log, buttons
         ↓
Worker thread terminates and is garbage collected
```

---

## Task Execution Flow

### Load Workflow

```
┌─────────────────────────────────────────────┐
│ start_load(source_kind, source_value)       │
│ Called by: on_download_clicked() or direct  │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ Create TaskThread(action="load")            │
│ - Config passed in                          │
│ - DB path passed in                         │
│ - CancellationToken passed in               │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ TaskThread.run()                            │
│ (executes in worker thread)                 │
├─────────────────────────────────────────────┤
│ 1. Emit: "Loading videos..."                │
│ 2. Call: list_videos(source_kind, ...)      │
│    → Checks database cache                  │
│    → Runs yt-dlp --flat-playlist            │
│    → Parallel fetch metadata for new IDs    │
│    → Stores results in DB                   │
│    → Returns: [VideoItem, VideoItem, ...]   │
│ 3. Emit: load_complete(items, source_name)  │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ on_load_complete(items, source_name)        │
│ (Signal handler in main thread)             │
├─────────────────────────────────────────────┤
│ 1. Store items in self.current_items        │
│ 2. Call populate_table(items)                │
│ 3. Emit: set_idle_state()                   │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ UI Updated: Table now shows all videos      │
│ User can now select rows and click Download │
└─────────────────────────────────────────────┘
```

### Download Workflow

```
┌─────────────────────────────────────────────┐
│ start_download(targets, source_name)        │
│ Called by: on_download_clicked() or direct  │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ Create TaskThread(action="download")        │
│ - Targets (VideoItems) passed in            │
│ - Media type (audio/video) passed in        │
│ - Config, DB, CancellationToken passed in   │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ TaskThread.run()                            │
│ (executes in worker thread)                 │
├─────────────────────────────────────────────┤
│ 1. Emit: "Downloading 3 videos..."          │
│ 2. Call: download_many(targets, ...)        │
│    → For each target:                       │
│      • Call download_one(target)            │
│      • Resolve title (cache or fresh)       │
│      • Build yt-dlp format command          │
│      • Execute with streaming output        │
│      • Handle bot challenges                │
│      • Log result                           │
│    → Uses ThreadPoolExecutor (max workers = │
│      CPU cores - 2) for parallelism         │
│    → Returns summary string                 │
│ 3. Emit: work_complete(summary)             │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ on_work_complete(summary)                   │
│ (Signal handler in main thread)             │
├─────────────────────────────────────────────┤
│ 1. Append summary to log                    │
│ 2. Call set_idle_state()                    │
│ 3. Clear worker reference                   │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ Downloads complete, files on disk           │
│ User sees: "Download complete: 3/3 ✓"       │
└─────────────────────────────────────────────┘
```

---

## State Management

### MainWindow State

```
MainWindow instance variables:
├─ config: dict                     # Current loaded config
├─ db_path: Path                    # Path to yt_aio.db
├─ cancel_token: CancellationToken  # Current task cancel handle
├─ worker: TaskThread | None        # Currently running task
├─ current_items: [VideoItem]       # Last loaded video list
├─ loaded_key: (str, str) | None    # What source was loaded
├─ loaded_source_name: str          # Channel/playlist name
│
├─ UI Widgets:
│  ├─ source_input_edit              # Text input for URL/ID
│  ├─ channel_radio                  # Channel vs Playlist
│  ├─ playlist_radio
│  ├─ audio_radio                    # Audio vs Video
│  ├─ video_radio
│  ├─ quick_download_edit             # Comma-separated URLs
│  ├─ results_table                   # QTableWidget
│  ├─ log_output                      # QPlainTextEdit
│  ├─ download_button                 # Control buttons
│  ├─ stop_button
│  ├─ clear_button
│  └─ config_button
│
└─ Progress indicators:
   ├─ progress_bar                    # Indeterminate animation
   └─ status_label                    # "Loading...", "Downloading..."
```

---

## Configuration Management

### Config Resolution Chain

```
Start Application
        ↓
ensure_config(CONFIG_PATH)
├─ Check if file exists
├─ If no: call build_default_config(), write file
└─ Return: config Path
        ↓
load_config(config_path)
├─ Read JSON
└─ Return: config dict
        ↓
resolve_runtime_config(raw_config)
├─ For each key in RUNTIME_PATH_KEYS:
│  └─ If value is relative path:
│     └─ Resolve to absolute path from APPLICATION_ROOT
│
├─ Example:
│  "log_file_path": "./db/yt_aio.db"
│  becomes:
│  "/home/user/path/yt_aio/application/db/yt_aio.db"
│
└─ Return: config dict with absolute paths
        ↓
Use config throughout application
```

### Config File Locations

```
RELATIVE (in config.json):
├─ log_file_path: "./db/yt_aio.db"
├─ history_file_path: "./db/yt_aio.db"
├─ logs_directory: "./logs"
└─ cookie_file: "./config/cookies.txt" (optional)

ABSOLUTE (in config.json):
├─ default_download_path: "/home/user/Downloads"
├─ proxy: null
└─ user_agent: "Mozilla/5.0 ..."

AT RUNTIME (resolved from relative):
├─ log_file_path → /full/path/yt_aio/application/db/yt_aio.db
├─ history_file_path → /full/path/yt_aio/application/db/yt_aio.db
└─ logs_directory → /full/path/yt_aio/application/logs
```

---

## Database Architecture

### Schema Overview

```
sources table
├─ id (PK)
├─ source_key (UNIQUE)           ← "channel:@username" or "playlist:ID"
├─ source_kind                   ← "channel" or "playlist"
├─ source_name                   ← "Channel Name" or "Playlist Name"
├─ source_value                  ← "@username" or "PL..."
└─ source_url                    ← Full YouTube URL

        ↓ (via source_id FK)

youtube_video_information table
├─ id (PK)
├─ video_id (UNIQUE)
├─ title
├─ channel_name
├─ duration
├─ view_count
├─ video_url
├─ source_id (FK) → sources
└─ cached_at

        ↓ (via video_info_id FK)

downloads table
├─ id (PK)
├─ title
├─ url
├─ status                       ← "success" or "failed"
├─ file_path
├─ quality                      ← "best" or specific bitrate
├─ type                         ← "audio" or "video"
├─ source_id (FK) → sources
├─ video_info_id (FK) → youtube_video_information
└─ timestamp
```

### Data Relationships

```
A User downloads from a Channel
        ↓
sources (1 row: channel_name="MrBeast")
        ↓
youtube_video_information (100 rows: all videos from channel)
        ↓
downloads (2 rows: user selected and downloaded 2 videos)
        ↓
errors (0 rows if all succeeded, >0 if failures)
```

---

## Error Handling Architecture

### Error Categories

```
Network Errors (HTTP)
├─ 429: YouTube bot challenge
│  └─ Auto-retry with Brave cookies
├─ 403: Forbidden
│  └─ Log error, skip video
└─ 5xx: Server error
   └─ Retry up to max_retries

Auth Errors
├─ "Sign in to confirm..."
│  └─ Retry with browser cookies
└─ Cookie expired
   └─ Log, suggest manual retry

Process Errors
├─ Timeout on yt-dlp execution
│  └─ Kill process, log, continue
├─ Process exit with code != 0
│  └─ Log stderr, continue
└─ Missing output file
   └─ Log, mark as failed

Data Errors
├─ Invalid URL
│  └─ Validate input, show message
├─ Null title
│  └─ Try to fetch again or use fallback
└─ Missing metadata
   └─ Cache fallback or skip
```

### Error Logging Flow

```
Exception occurs in TaskThread.run()
        ↓
Catch exception, emit work_failed(error_msg)
        ↓
MainWindow.on_work_failed(message)
├─ Log message
├─ Call: log_error(db_path, payload)
│  └─ Insert into errors table
├─ Show error dialog
└─ Set idle state
        ↓
User can view errors in database
├─ Query: SELECT * FROM errors WHERE timestamp > ?
└─ Understand what went wrong
```

---

## Concurrency Model

### Thread Safety

```
SAFE (thread-safe):
├─ CancellationToken.cancel()    ← Can call from main or worker
├─ Database writes                ← SQLite WAL mode
└─ Qt signal emissions             ← Qt thread-safe

NOT SAFE (use only in same thread):
├─ Modifying MainWindow widgets
├─ Reading self.current_items     ← Use callback/signal instead
└─ Config dict updates             ← Config is read-only after load
```

### Parallelism Limits

```
list_videos() → Parallel metadata fetch
├─ ThreadPoolExecutor with max_metadata_workers
├─ Default: 4 workers
└─ Prevents overwhelming YouTube API

download_many() → Parallel downloads
├─ ThreadPoolExecutor with max_concurrent_downloads
├─ Default: (CPU cores - 2) workers
└─ Prevents network saturation

Outer TaskThread
├─ Only one TaskThread active at a time
├─ on_download_clicked() checks if is_busy()
└─ Prevents multiple concurrent tasks
```

---

## Cancellation Mechanism

### How Cancellation Works

```
User clicks "Stop" button
        ↓
on_stop_clicked()
├─ self.cancel_token.cancel()
│  └─ Sets cancellation_requested = True
│  └─ Calls kill() on all registered processes
└─ Emit: "Cancelled by user"
        ↓
Worker thread (in list_videos or download_one)
├─ Periodically checks: if token.is_cancelled()
├─ Gracefully exits if true
└─ Emits: work_failed("Cancelled by user")
        ↓
MainWindow receives signal
├─ Sets idle state
├─ Partial results retained if download was mid-batch
└─ User can restart
```

---

*Next: [03_INSTALLATION.md](03_INSTALLATION.md) — How to Set Up*

