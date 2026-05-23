# ⚙️ Configuration Management

Understanding and customizing the application configuration.

---

## Configuration File

**Location:** `yt_aio/application/config/config.json`

**Access:** Click "Config" button in UI to edit

**Format:** JSON with comments (comments are stripped during load)

---

## Default Configuration

```json
{
  "default_download_path": "/home/user/Downloads",
  "default_video_quality": "best",
  "default_audio_quality": "m4a",
  "max_retries": 3,
  "retry_delay": 5,
  
  "log_file_path": "./db/yt_aio.db",
  "history_file_path": "./db/yt_aio.db",
  "logs_directory": "./logs",
  
  "log_level": "INFO",
  "proxy": null,
  "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
  
  "cookie_fallback_enabled": true,
  "cookie_fallback_browser": "brave",
  
  "download_subtitles": false,
  "subtitle_language": "en",
  "download_thumbnail": false,
  "thumbnail_quality": "best",
  "download_description": false,
  "description_format": "txt",
  
  "max_concurrent_downloads": 6,
  "max_metadata_workers": 4,
  "download_history": true,
  
  "chunk_size": 100,
  "chunk_timeout": 120,
  "enable_progressive_fetching": true
}
```

---

## Configuration Keys Explained

### Download Settings

| Key | Type | Default | Purpose |
|-----|------|---------|---------|
| `default_download_path` | string (absolute path) | `/home/user/Downloads` | Where to save files |
| `default_video_quality` | string | `"best"` | yt-dlp format for video |
| `default_audio_quality` | string | `"m4a"` | yt-dlp format for audio |

### Retry & Resilience

| Key | Type | Default | Purpose |
|-----|------|---------|---------|
| `max_retries` | int | `3` | How many times to retry on failure |
| `retry_delay` | int | `5` | Seconds to wait between retries |
| `log_level` | string | `"INFO"` | Logging verbosity (INFO, DEBUG, ERROR) |

### Paths (Relative → Resolved at Runtime)

| Key | Type | Default | Purpose | Resolution |
|-----|------|---------|---------|-----------|
| `log_file_path` | string (relative) | `"./db/yt_aio.db"` | SQLite database | `APPLICATION_ROOT/db/yt_aio.db` |
| `history_file_path` | string (relative) | `"./db/yt_aio.db"` | Download history DB | Same as log_file_path |
| `logs_directory` | string (relative) | `"./logs"` | File logs (future) | `APPLICATION_ROOT/logs` |

### YouTube Authentication

| Key | Type | Default | Purpose |
|-----|------|---------|---------|
| `proxy` | string | `null` | HTTP proxy (if needed) |
| `user_agent` | string | Mozilla UA | User agent for requests |
| `cookie_fallback_enabled` | bool | `true` | Use browser cookies on bot challenge |
| `cookie_fallback_browser` | string | `"brave"` | Which browser: "brave", "firefox", "chrome" |

### Optional Downloads

| Key | Type | Default | Purpose |
|-----|------|---------|---------|
| `download_subtitles` | bool | `false` | Include subtitle files |
| `subtitle_language` | string | `"en"` | Subtitle language |
| `download_thumbnail` | bool | `false` | Include thumbnail image |
| `thumbnail_quality` | string | `"best"` | Thumbnail resolution |
| `download_description` | bool | `false` | Save video description |
| `description_format` | string | `"txt"` | Format: "txt", "json", "html" |

### Concurrency

| Key | Type | Default | Purpose |
|-----|------|---------|---------|
| `max_concurrent_downloads` | int | `6` (CPU-2) | Parallel download workers |
| `max_metadata_workers` | int | `4` | Parallel metadata fetch workers |

### Future Features (Point 1.8.1)

| Key | Type | Default | Purpose |
|-----|------|---------|---------|
| `chunk_size` | int | `100` | Videos per playlist chunk |
| `chunk_timeout` | int | `120` | Timeout per chunk (seconds) |
| `enable_progressive_fetching` | bool | `true` | Stream results as chunks complete |

---

## Path Resolution

### How Relative Paths Are Resolved

```
Config file contains:
  "log_file_path": "./db/yt_aio.db"

At runtime:
  1. Load config JSON
  2. Call: resolve_runtime_config(config)
  3. For each key in RUNTIME_PATH_KEYS:
     ├─ If value is relative (starts with "./" or no "/"):
     │  └─ Resolve to: APPLICATION_ROOT / value
     │
     └─ APPLICATION_ROOT = yt_aio/application/
     
  4. Result:
     "/full/path/yt_aio/application/db/yt_aio.db"

Effect:
  ✓ Config file is portable
  ✓ Works from any directory
  ✓ No hardcoded paths
```

---

## Editing Configuration

### Method 1: Through UI

```
1. Click "Config" button
2. Opens config.json in default text editor
3. Edit values
4. Save file (Ctrl+S)
5. Next operation uses updated config
```

### Method 2: Direct File Edit

```
1. Open: yt_aio/application/config/config.json
2. Edit with any text editor
3. Save
4. Restart app
```

### Validation

App validates config keys on load:

```
✓ Paths must exist or be creatable
✓ Integers must be > 0
✓ Booleans must be true/false
✓ Strings can be anything

If validation fails:
├─ Log warning
├─ Use default value
└─ Continue (failsafe)
```

---

## Common Customizations

### Change Download Folder

```json
{
  "default_download_path": "/mnt/external_drive/videos"
}
```

### Use Faster Download (Less Quality)

```json
{
  "default_video_quality": "best[height<=720]",
  "max_concurrent_downloads": 8
}
```

### Use VPN/Proxy

```json
{
  "proxy": "socks5://127.0.0.1:9050"
}
```

### Conservative Retry (Slow Network)

```json
{
  "max_retries": 5,
  "retry_delay": 10,
  "chunk_timeout": 180
}
```

### Aggressive Download (Fast Network)

```json
{
  "max_retries": 2,
  "retry_delay": 2,
  "max_concurrent_downloads": 10,
  "max_metadata_workers": 8
}
```

---

## Configuration Reload

**Current Behavior:**
- Config loaded once at app startup
- Changes require app restart

**Future Improvement:**
- Watch config file for changes
- Reload on detect
- Update active settings (backlog item)

---

*Next: [10_THREADING_AND_CANCELLATION.md](10_THREADING_AND_CANCELLATION.md)*

