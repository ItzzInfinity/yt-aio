# 📚 Module Guide: Function-by-Function Breakdown

This document describes each module, its purpose, and key functions with pseudo-code.

---

## Module Organization

```
application/
├── ui/              ← User Interface Layer
├── utils/           ← Business Logic
├── db/              ← Data Persistence
└── config/          ← Configuration
```

---

## 🎨 UI Module: `application/ui/main_window.py`

### Purpose
Orchestrate the PyQt GUI, manage user interactions, and coordinate task execution via worker threads.

### Key Classes

#### `MainWindow (extends QMainWindow)`

**Responsibility:** Central orchestrator for the entire application.

**Pseudo-code: __init__() → Application startup**

```
function MainWindow.__init__():
    # 1. Load configuration
    config_path = ensure_config(CONFIG_PATH)
    self.config = load_config(config_path)
    self.config = resolve_runtime_config(self.config)
    
    # 2. Initialize database
    self.db_path = self.config['log_file_path']
    init_db(self.db_path)
    
    # 3. Create UI widgets
    _build_ui():
        create QWidget tree:
            - source input textbox
            - channel/playlist radio buttons
            - audio/video radio buttons
            - results table (QTableWidget)
            - quick download textbox
            - log output (QPlainTextEdit)
            - buttons: Download, Stop, Clear, Config
        
    # 4. Load and apply stylesheet
    _apply_stylesheet()  → Load styles.qss
    
    # 5. Set initial state
    self.current_items = []
    self.worker = None
    self.cancel_token = None
    self.loaded_key = None
    
    # 6. Log startup
    append_log("YT-AIO initialized")
```

**Pseudo-code: on_download_clicked()**

```
function on_download_clicked():
    # Check if already busy
    if is_busy():
        append_log("ERROR: Task already running")
        return
    
    # Get source info
    source_kind = current_source_kind()  # "channel" or "playlist"
    source_value = source_input_edit.text()
    
    # Get quick download URLs
    quick_urls_raw = quick_download_edit.text()
    quick_urls = parse_quick_download_urls(quick_urls_raw)
    
    if quick_urls is not None and len(quick_urls) > 0:
        # QUICK DOWNLOAD PATH
        set_busy_state("Downloading...", "Downloading...")
        media_type = current_media_type()  # "audio" or "video"
        targets = [DownloadTarget(url=url) for url in quick_urls]
        start_download(targets, "Quick Download")
        
    elif loaded_key == (source_kind, source_value):
        # ITEMS ALREADY LOADED - START DOWNLOAD
        selected = get_selected_items()
        if len(selected) == 0:
            append_log("ERROR: Select videos to download")
            return
        
        set_busy_state("Downloading...", "Downloading...")
        media_type = current_media_type()
        source_name = loaded_source_name
        start_download(selected, source_name)
        
    else:
        # NEED TO LOAD FIRST
        if not source_value:
            append_log("ERROR: Enter channel URL or playlist ID")
            return
        
        set_busy_state("Loading...", "Loading...")
        start_load(source_kind, source_value)
```

**Pseudo-code: start_load(source_kind, source_value)**

```
function start_load(source_kind, source_value):
    self.cancel_token = CancellationToken()
    self.worker = TaskThread(
        action="load",
        config=self.config,
        db_path=self.db_path,
        token=self.cancel_token,
        source_kind=source_kind,
        source_value=source_value
    )
    
    attach_worker()  # Connect signals
    self.worker.start()  # Spawn OS thread
```

**Pseudo-code: on_load_complete(items, source_name)**

```
function on_load_complete(items, source_name):
    self.current_items = items
    self.loaded_source_name = source_name
    source_kind = current_source_kind()
    source_value = source_input_edit.text()
    self.loaded_key = (source_kind, source_value)
    
    populate_table(items)  # Show in results table
    
    append_log(f"Load complete: {len(items)} videos")
    set_idle_state("Ready")
```

**Pseudo-code: populate_table(items)**

```
function populate_table(items):
    results_table.setRowCount(len(items))
    
    for row, item in enumerate(items):
        # Checkbox column
        checkbox = QCheckBox()
        results_table.setCellWidget(row, 0, checkbox)
        
        # ID, Name, Duration, Bitrate columns
        results_table.setItem(row, 1, QTableWidgetItem(item.video_id))
        results_table.setItem(row, 2, QTableWidgetItem(item.title))
        results_table.setItem(row, 3, QTableWidgetItem(item.duration_label))
        results_table.setItem(row, 4, QTableWidgetItem(item.available_bitrate))
    
    results_table.resizeColumnsToContents()
```

---

#### `TaskThread (extends QThread)`

**Responsibility:** Execute long-running operations in a separate thread.

**Pseudo-code: run()**

```
function TaskThread.run():
    try:
        if action == "load":
            source_kind = self.kwargs['source_kind']
            source_value = self.kwargs['source_value']
            
            items, source_name = list_videos(
                source_kind=source_kind,
                source_value=source_value,
                config=self.config,
                db_path=self.db_path,
                logger=lambda msg: self.log_message.emit(msg),
                token=self.token
            )
            
            self.load_complete.emit(items, source_name)
            
        elif action == "download":
            targets = self.kwargs['targets']
            media_type = self.kwargs['media_type']
            source_name = self.kwargs['source_name']
            
            summary = download_many(
                targets=targets,
                media_type=media_type,
                config=self.config,
                db_path=self.db_path,
                logger=lambda msg: self.log_message.emit(msg),
                token=self.token,
                source_name=source_name
            )
            
            self.work_complete.emit(summary)
            
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        self.log_message.emit(error_msg)
        self.work_failed.emit(error_msg)
```

---

## ⚙️ Utils Module: Video Info Extraction

### File: `application/utils/video_info_extractor.py`

**Purpose:** Handle all YouTube metadata fetching and yt-dlp integration.

### Key Functions

#### `list_videos(source_kind, source_value, ...)`

**Responsibility:** Fetch all videos from channel/playlist with caching.

**Pseudo-code:**

```
function list_videos(source_kind, source_value, config, db_path, logger, token):
    # 1. Resolve to full YouTube URL
    source_url = resolve_source_url(source_kind, source_value)
    
    # 2. Create source record in DB
    source_id = upsert_source(db_path, {
        source_kind: source_kind,
        source_value: source_value,
        source_url: source_url
    })
    
    # 3. Fetch flat-playlist to get all video IDs
    logger("Fetching video list...")
    command = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-single-json",
        source_url
    ]
    
    json_data = run_json_command(command, config, logger=logger, token=token)
    all_entries = json_data.get('entries', [])
    logger(f"Found {len(all_entries)} videos")
    
    # 4. Check cache for already-fetched videos
    video_ids = [e['id'] for e in all_entries]
    cached = get_cached_videos(db_path, video_ids)
    
    # 5. Parallel fetch metadata for uncached videos
    pending_ids = [v_id for v_id in video_ids if v_id not in cached]
    
    logger(f"Fetching metadata for {len(pending_ids)} new videos...")
    
    metadata_results = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(fetch_video_metadata, v_id, config, token): v_id
            for v_id in pending_ids
        }
        
        for future in as_completed(futures):
            v_id = futures[future]
            try:
                metadata = future.result()
                metadata_results[v_id] = metadata
                
                # Log to DB
                log_video_info(db_path, {
                    'video_id': v_id,
                    'title': metadata['title'],
                    'channel_name': metadata['uploader'],
                    'duration': metadata['duration'],
                    'source_id': source_id
                })
            except Exception as e:
                logger(f"Failed to fetch {v_id}: {e}")
    
    # 6. Build result items from cache + new metadata
    items = []
    for entry in all_entries:
        v_id = entry['id']
        
        if v_id in cached:
            # Use cached data
            item = _cached_row_to_item(cached[v_id])
        elif v_id in metadata_results:
            # Use freshly fetched data
            item = _metadata_to_item(metadata_results[v_id])
        else:
            # Use fallback (flat-playlist data only)
            item = _entry_to_item(entry)
        
        items.append(item)
    
    # 7. Extract source name
    source_name = items[0].channel_name if items else "Unknown"
    
    return items, source_name
```

#### `fetch_video_metadata(video_id, config, token)`

**Responsibility:** Fetch metadata for a single video.

**Pseudo-code:**

```
function fetch_video_metadata(video_id, config, token):
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    command = build_yt_dlp_command(config, [
        "-j",  # JSON output
        "--no-warnings",
        url
    ])
    
    # Run with timeout
    return_code, output_lines = run_json_command(
        command,
        config=config,
        timeout=45,
        token=token
    )
    
    if return_code != 0:
        raise Exception(f"yt-dlp returned {return_code}")
    
    return parse_json_output(output_lines)
```

#### `run_json_command(command_parts, config, ...)`

**Responsibility:** Execute yt-dlp command, handle retries and bot challenges.

**Pseudo-code:**

```
function run_json_command(command_parts, config, retries=3, retry_delay=5, 
                         timeout=None, token=None, logger=None):
    attempt = 0
    attempted_auth = False
    
    while attempt <= retries:
        attempt += 1
        logger(f"Attempt {attempt}/{retries+1}")
        
        # Build full command
        full_cmd = build_yt_dlp_command(config, command_parts, attempted_auth)
        env = build_yt_dlp_env(config, attempted_auth)
        
        # Execute
        process = subprocess.Popen(
            full_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True
        )
        
        token.register(process) if token else None
        
        # Capture output with timeout
        try:
            output_lines = []
            start_time = time.time()
            
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                output_lines.append(line)
                
                # Check timeout
                if timeout and (time.time() - start_time) > timeout:
                    process.kill()
                    raise TimeoutError(f"Command timeout after {timeout}s")
                
                # Check cancellation
                if token and token.is_cancelled():
                    process.kill()
                    raise CancelledError("User cancelled")
            
            return_code = process.wait()
            stderr = process.stderr.read()
            
        finally:
            token.unregister(process) if token else None
        
        combined_output = '\n'.join(output_lines) + stderr
        
        # Check for bot challenge
        if _should_retry_with_auth(combined_output, config, attempted_auth):
            logger("YouTube bot challenge detected, retrying with auth...")
            attempted_auth = True
            time.sleep(retry_delay)
            continue
        
        if return_code == 0:
            return return_code, output_lines
        
        # Retry on failure
        if attempt <= retries:
            logger(f"Failed, retrying in {retry_delay}s...")
            time.sleep(retry_delay)
            continue
        
        raise Exception(f"Command failed: {combined_output}")
    
    raise Exception("All retries exhausted")
```

---

## 📥 Utils Module: Download Manager

### File: `application/utils/download_manager.py`

**Purpose:** Orchestrate concurrent downloads with retry logic and error handling.

#### `download_many(targets, media_type, ...)`

**Pseudo-code:**

```
function download_many(targets, media_type, config, db_path, logger, token, source_name):
    logger(f"Downloading {len(targets)} videos as {media_type}")
    
    success_count = 0
    failure_count = 0
    
    max_workers = config.get('max_concurrent_downloads', cpu_count() - 2)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(download_one, target, media_type, config, 
                          db_path, logger, token, source_name): target
            for target in targets
        }
        
        for future in as_completed(futures):
            target = futures[future]
            
            try:
                success = future.result()
                if success:
                    success_count += 1
                else:
                    failure_count += 1
                    
            except Exception as e:
                logger(f"ERROR downloading {target.title}: {e}")
                failure_count += 1
                
                log_error(db_path, {
                    'error_message': str(e),
                    'url': target.url,
                    'action': 'download'
                })
    
    summary = f"Download complete: {success_count}/{len(targets)} ✓"
    if failure_count > 0:
        summary += f", {failure_count} failed"
    
    logger(summary)
    return summary
```

#### `download_one(target, media_type, ...)`

**Pseudo-code:**

```
function download_one(target, media_type, config, db_path, logger, token, source_name):
    try:
        # 1. Resolve title
        title = target.title
        if not title:
            title = resolve_download_title(db_path, target, config, token)
        
        # 2. Build command
        command = build_download_command(target.url, media_type, config, use_auth=False)
        
        # 3. Execute
        return_code, output_lines = run_streaming_command(command, token, logger)
        
        # 4. Check for bot challenge
        output = '\n'.join(output_lines)
        if _should_retry_with_auth(output, config, attempted_auth=False):
            logger(f"Bot challenge for {title}, retrying with auth...")
            command = build_download_command(target.url, media_type, config, use_auth=True)
            return_code, output_lines = run_streaming_command(command, token, logger)
            output = '\n'.join(output_lines)
        
        # 5. Check result
        if return_code != 0:
            raise Exception(f"yt-dlp returned {return_code}")
        
        # 6. Infer file path
        file_path = infer_output_path(output_lines)
        
        # 7. Log success
        log_download(db_path, {
            'title': title,
            'url': target.url,
            'status': 'success',
            'file_path': file_path,
            'type': media_type,
            'quality': 'best',
            'source_name': source_name
        })
        
        logger(f"✓ Downloaded: {title}")
        return True
        
    except Exception as e:
        logger(f"✗ Failed: {title} - {str(e)}")
        
        log_download(db_path, {
            'title': target.title or 'Unknown',
            'url': target.url,
            'status': 'failed',
            'error_message': str(e),
            'type': media_type,
            'source_name': source_name
        })
        
        log_error(db_path, {
            'error_message': str(e),
            'url': target.url,
            'action': 'download',
            'stack_trace': traceback.format_exc()
        })
        
        return False
```

---

## ⚙️ Utils Module: Configuration

### File: `application/utils/config_manager.py`

**Purpose:** Load, validate, and resolve configuration paths.

#### `ensure_config(config_path)`

**Pseudo-code:**

```
function ensure_config(config_path):
    if config_path.exists():
        return config_path
    
    # Create parent directory
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write default config
    default_config = build_default_config()
    write_json(config_path, default_config)
    
    return config_path
```

#### `resolve_runtime_config(raw_config)`

**Pseudo-code:**

```
function resolve_runtime_config(raw_config):
    resolved = raw_config.copy()
    
    APPLICATION_ROOT = Path(__file__).parent.parent  # yt_aio/application/
    
    RUNTIME_PATH_KEYS = [
        'log_file_path',
        'history_file_path',
        'logs_directory',
        'cookie_file'
    ]
    
    for key in RUNTIME_PATH_KEYS:
        if key in raw_config:
            value = raw_config[key]
            
            if value and not Path(value).is_absolute():
                # Relative path → resolve from APPLICATION_ROOT
                resolved[key] = str(APPLICATION_ROOT / value)
            else:
                resolved[key] = value
    
    return resolved
```

---

## 📊 DB Module

### File: `application/db/database_manager.py`

**Purpose:** SQLite schema management and CRUD operations.

#### `init_db(db_path)`

**Pseudo-code:**

```
function init_db(db_path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    with _connect(db_path) as conn:
        # Create tables
        conn.execute(CREATE TABLE sources ...)
        conn.execute(CREATE TABLE youtube_video_information ...)
        conn.execute(CREATE TABLE downloads ...)
        conn.execute(CREATE TABLE errors ...)
        conn.execute(CREATE TABLE user_actions ...)
        conn.execute(CREATE TABLE settings_changes ...)
        conn.execute(CREATE TABLE yt_aio_version ...)
        
        # Create indices
        conn.execute(CREATE INDEX idx_video_id_on_youtube_video_information ...)
        
        # Insert app version
        conn.execute(INSERT INTO yt_aio_version VALUES (?, ?, ?, ?),
                    (None, APP_VERSION, now_string(), APP_CHANGELOG))
        
        conn.commit()
```

#### `get_cached_videos(db_path, video_ids)`

**Pseudo-code:**

```
function get_cached_videos(db_path, video_ids):
    with _connect(db_path) as conn:
        placeholders = ','.join(['?' for _ in video_ids])
        
        query = f"""
            SELECT id, video_id, title, channel_name, duration, view_count, 
                   available_bitrate, upload_date, source_id
            FROM youtube_video_information
            WHERE video_id IN ({placeholders})
        """
        
        cursor = conn.execute(query, video_ids)
        rows = cursor.fetchall()
        
        result = {}
        for row in rows:
            video_id = row['video_id']
            result[video_id] = dict(row)  # Convert to dict
        
        return result
```

#### `log_download(db_path, payload)`

**Pseudo-code:**

```
function log_download(db_path, payload):
    with _connect(db_path) as conn:
        # Ensure source exists
        source_id = _ensure_source_row(conn, payload)
        
        # Insert download record
        conn.execute("""
            INSERT INTO downloads 
            (title, url, status, error_message, timestamp, file_path, 
             quality, type, source_name, source_id, video_id, video_info_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            payload.get('title'),
            payload.get('url'),
            payload.get('status'),
            payload.get('error_message'),
            payload.get('timestamp', now_string()),
            payload.get('file_path'),
            payload.get('quality'),
            payload.get('type'),
            payload.get('source_name'),
            source_id,
            payload.get('video_id'),
            payload.get('video_info_id')
        ))
        
        conn.commit()
```

---

## 🔧 Shared Module

### File: `application/utils/shared.py`

**Purpose:** Common types and utilities used across modules.

#### `VideoItem` (Dataclass)

```python
@dataclass
class VideoItem:
    video_id: str
    title: str
    url: str
    duration_seconds: int
    duration_label: str  # "MM:SS" format
    available_bitrate: str
    channel_name: str
    source_name: str
    upload_date: str
    view_count: int
    video_info_id: int | None
    source_id: int | None
```

#### `CancellationToken` (Thread-Safe)

**Pseudo-code:**

```
class CancellationToken:
    def __init__(self):
        self._cancelled = False
        self._lock = threading.Lock()
        self._processes = set()
    
    function cancel():
        with self._lock:
            self._cancelled = True
            for process in self._processes:
                try:
                    process.kill()
                except:
                    pass  # Already terminated
    
    function is_cancelled():
        with self._lock:
            return self._cancelled
    
    function register(process):
        with self._lock:
            self._processes.add(process)
    
    function unregister(process):
        with self._lock:
            self._processes.discard(process)
```

---

## 📋 Call Graph (Function Dependencies)

```
User clicks Download (UI)
  ↓
MainWindow.on_download_clicked()
  ├─→ start_load() or start_download()
  │   ├─→ TaskThread.start()
  │   │   ├─→ TaskThread.run()
  │   │   │   ├─→ list_videos()
  │   │   │   │   ├─→ resolve_source_url()
  │   │   │   │   ├─→ upsert_source() [DB]
  │   │   │   │   ├─→ run_json_command()
  │   │   │   │   │   ├─→ build_yt_dlp_command()
  │   │   │   │   │   ├─→ build_yt_dlp_env()
  │   │   │   │   │   └─→ _should_retry_with_auth()
  │   │   │   │   ├─→ get_cached_videos() [DB]
  │   │   │   │   ├─→ fetch_video_metadata() [parallel]
  │   │   │   │   └─→ log_video_info() [DB]
  │   │   │   │
  │   │   │   └─→ download_many()
  │   │   │       ├─→ download_one() [parallel]
  │   │   │       │   ├─→ resolve_download_title()
  │   │   │       │   ├─→ build_download_command()
  │   │   │       │   ├─→ run_streaming_command()
  │   │   │       │   └─→ log_download() [DB]
  │   │   │       └─→ log_error() [DB, on failure]
  │   │   │
  │   │   └─→ Emit: load_complete or work_complete
  │   │
  │   └─→ on_load_complete() or on_work_complete()
  │       └─→ populate_table()
  │
  └─→ set_idle_state()
```

---

*Next: [06_DATA_FLOW.md](06_DATA_FLOW.md) — How Data Moves Through the System*

