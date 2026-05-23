# ▶️ Running the Application

Guide to running YT-AIO, debugging, and understanding console output.

---

## Basic Execution

### From Command Line

```bash
# Navigate to project directory
cd /home/itzzinfinity/GitHub/yt_aio

# Activate virtual environment (if using one)
source venv/bin/activate

# Run the application
python3 -m yt_aio
```

### Expected Output

```
2026-05-23 10:30:15 - YT-AIO initialized
2026-05-23 10:30:15 - Config loaded from: ./application/config/config.json
2026-05-23 10:30:15 - Database initialized: ./application/db/yt_aio.db
2026-05-23 10:30:15 - UI ready
```

A PyQt window should open with:
- Channel/Playlist input box at top-left
- Video/Audio radio buttons on right
- Empty table in center
- Log output on left
- Control buttons (Download, Stop, Clear, Config) at bottom

---

## Alternative Entry Points

### Using run.py

```bash
python3 yt_aio/run.py
```

### Direct Module Execution

```bash
python3 yt_aio/__main__.py
```

---

## User Workflow Examples

### Example 1: Download a Single Video

```
1. Paste video URL:
   https://www.youtube.com/watch?v=dQw4w9WgXcQ

2. Paste into "Quick Download" textbox (bottom)

3. Click "Download"

4. Log shows:
   → "Downloading 1 item..."
   → "Downloaded: rick_astley.mp4"
   → Files appears in Downloads folder
```

### Example 2: Load and Download from Channel

```
1. Enter channel URL:
   https://www.youtube.com/@vsauce

2. Select "Channel" radio button (should be default)

3. Click "Download" button

4. Log shows:
   → "Loading videos from @vsauce..."
   → "Fetching 142 videos from channel"
   → "Parallel fetching metadata... (4 workers)"
   → "Load complete: 142 videos"

5. Table populates with all 142 videos

6. Select 5 videos (checkboxes)

7. Click "Download" again

8. Log shows:
   → "Downloading 5 videos..."
   → "Downloaded: video1.mp4"
   → "Downloaded: video2.mp4"
   → etc.
```

### Example 3: Download from Playlist

```
1. Enter playlist URL:
   https://www.youtube.com/playlist?list=PLxxx

2. Select "Playlist" radio button

3. Click "Download"

4. Table populates

5. Select videos → Click Download → Files saved
```

---

## Configuration

### Edit Config File

```
1. Click "Config" button (bottom-right)

2. Opens: application/config/config.json

3. Edit settings:
   - default_download_path: where files go
   - default_video_quality: "best" or specific format
   - default_audio_quality: "m4a"
   - max_retries: how many times to retry on failure
   - max_concurrent_downloads: parallelism

4. Save file

5. Next operation uses updated config
```

### Config File Format

```json
{
  "default_download_path": "/home/user/Downloads",
  "default_video_quality": "best",
  "default_audio_quality": "m4a",
  "max_retries": 3,
  "retry_delay": 5,
  "chunk_size": 100,
  "chunk_timeout": 120,
  "proxy": null,
  "user_agent": "Mozilla/5.0...",
  "cookie_fallback_enabled": true,
  "cookie_fallback_browser": "brave",
  "max_concurrent_downloads": 6,
  "download_history": true
}
```

---

## Log Output

### What the Log Shows

```
UI Log (left panel):
├─ User actions: "Loading...", "Downloading..."
├─ Progress: "Fetched 50/142 videos"
├─ Completion: "Download complete: 5/5 ✓"
└─ Errors: "Failed to download video123.mp4"

Database Log (sqlite):
├─ All operations recorded
├─ Timestamps for each action
├─ Success/failure status
├─ Error messages with stack traces
└─ Audit trail of all downloads
```

### Viewing Database Logs

```bash
# Open the database
sqlite3 yt_aio/application/db/yt_aio.db

# View recent downloads
SELECT title, status, timestamp FROM downloads ORDER BY timestamp DESC LIMIT 10;

# View recent errors
SELECT error_message, timestamp FROM errors ORDER BY timestamp DESC LIMIT 5;

# View user actions
SELECT action, timestamp FROM user_actions ORDER BY timestamp DESC LIMIT 20;

# Exit
.quit
```

---

## Cancellation & Stop

### Stop Running Task

```
1. Click "Stop" button while task is running

2. Log shows:
   → "Cancelled by user"

3. Any partial results retained
   - Partial downloads visible in table
   - Files already written stay on disk
```

### Clear Log

```
1. Click "Clear" button

2. Log textbox cleared

3. Note: This doesn't delete database,
   only clears what's displayed in UI
```

---

## Debugging

### Enable Verbose Logging

Set environment variable before running:

```bash
export YT_AIO_DEBUG=1
python3 -m yt_aio
```

### Check Error Log in Database

```bash
# Open SQLite
sqlite3 yt_aio/application/db/yt_aio.db

# View latest errors with stack traces
SELECT error_message, stack_trace, timestamp FROM errors 
ORDER BY timestamp DESC LIMIT 1;
```

### Monitor yt-dlp Calls

```bash
# Uncomment debug prints in video_info_extractor.py
# Then run with:
python3 -m yt_aio 2>&1 | grep "yt-dlp"
```

### Check Config Loading

In MainWindow.__init__():

```python
# Add print statements to see what config was loaded:
print(f"Config loaded: {self.config}")
print(f"DB path resolved to: {self.db_path}")
```

---

## Common Issues & Solutions

### Issue: "yt-dlp not found"

```
Solution:
1. Activate virtual environment
2. pip install --upgrade yt-dlp
3. python3 -m yt_dlp --version  (verify)
4. Restart app
```

### Issue: No Videos Appear After Loading Channel

```
Solution:
1. Check database: Are videos cached?
   sqlite3 yt_aio/application/db/yt_aio.db
   SELECT COUNT(*) FROM youtube_video_information;

2. Check recent errors:
   SELECT * FROM errors ORDER BY timestamp DESC LIMIT 1;

3. Try again with different channel
4. Check internet connection
```

### Issue: Download Fails for Some Videos

```
Solution (normal behavior):
1. Log will show which videos failed
2. Check errors table for reasons
3. Try downloading failed video again
4. Some videos may be age-restricted or unavailable
```

### Issue: App Freezes UI

```
This shouldn't happen. If it does:
1. Task should be running in worker thread
2. If UI freezes, worker thread crashed silently
3. Check logs for exceptions
4. Restart app
5. Report bug (see 12_CONTRIBUTION_GUIDE.md)
```

---

## Performance Tips

### For Large Playlists (1000+ videos)

```
1. Adjust config:
   - Increase max_metadata_workers: 8 (from 4)
   - Increase chunk_size: 200 (from 100)

2. Network:
   - Ensure stable internet
   - Avoid other heavy downloads

3. Monitoring:
   - Use system monitor to watch CPU/RAM
   - Normal: CPU ~40%, RAM ~100-200MB
```

### For Slow Connections

```
1. Adjust config:
   - Decrease max_concurrent_downloads: 2 (from CPU-2)
   - Increase retry_delay: 10 (from 5)
   - Increase chunk_timeout: 180 (from 120)

2. Try:
   - Downloading during off-peak hours
   - Using VPN with better routing
```

---

## Advanced: Direct Python Usage

If you want to use the library programmatically:

```python
# main.py
from yt_aio.application.utils.video_info_extractor import list_videos
from yt_aio.application.utils.download_manager import download_many
from yt_aio.application.utils.config_manager import ensure_config, load_config, resolve_runtime_config
from yt_aio.application.db.database_manager import init_db
from yt_aio.application.utils.shared import CancellationToken

# Setup
config_path = ensure_config("path/to/config.json")
config = load_config(config_path)
config = resolve_runtime_config(config)
db_path = config['log_file_path']
init_db(db_path)
token = CancellationToken()

# Load channel
items = list_videos(
    source_kind="channel",
    source_value="@vsauce",
    config=config,
    db_path=db_path,
    logger=print
)

# Download
result = download_many(
    targets=items[:5],
    media_type="audio",
    config=config,
    db_path=db_path,
    logger=print,
    token=token
)
```

---

## Next Steps

- Explore [05_MODULE_GUIDE.md](05_MODULE_GUIDE.md) to understand code structure
- Check [08_DATABASE_SCHEMA.md](08_DATABASE_SCHEMA.md) to understand data model
- Read [11_ERROR_HANDLING.md](11_ERROR_HANDLING.md) for debugging tips

---

*Next: [05_MODULE_GUIDE.md](05_MODULE_GUIDE.md) — Detailed Code Structure*

