# 🤝 Contribution Guide

How to add features, fix bugs, and contribute to YT-AIO.

---

## Development Workflow

### Step 1: Understand the Codebase

1. Read [00_START_HERE.md](00_START_HERE.md) (5 min)
2. Read [02_ARCHITECTURE.md](02_ARCHITECTURE.md) (10 min)
3. Read [05_MODULE_GUIDE.md](05_MODULE_GUIDE.md) (15 min)
4. Identify: Which module needs change?

### Step 2: Set Up Development Environment

```bash
# Clone and enter directory
cd /home/itzzinfinity/GitHub/yt_aio

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install PyQt5 yt-dlp pytest black pylint

# Run the app to verify setup
python3 -m yt_aio
```

### Step 3: Create a Feature Branch

```bash
git checkout -b feature/my-feature
# or
git checkout -b bugfix/issue-name
```

### Step 4: Implement Your Change

#### Before Coding

- Write a design comment in the code
- Identify affected modules
- Consider error cases
- Plan database changes (if any)

#### During Coding

- Follow existing style
- Add docstrings
- Handle errors gracefully
- Log important operations

#### After Coding

- Test locally
- Check for side effects
- Verify logging works
- Update documentation

### Step 5: Testing

```bash
# Run locally
python3 -m yt_aio

# Test your feature manually

# Check for errors
sqlite3 yt_aio/application/db/yt_aio.db
SELECT * FROM errors ORDER BY timestamp DESC;

# Check logs
SELECT * FROM downloads ORDER BY timestamp DESC;
```

### Step 6: Code Style

```bash
# Format code
black yt_aio/

# Check style
pylint yt_aio/application/utils/your_file.py
```

### Step 7: Commit & Push

```bash
git add .
git commit -m "Feature: Add my feature (#issue_number)"
git push origin feature/my-feature
```

### Step 8: Create Pull Request

- Title: Clear description
- Description: What, Why, How
- Link issues: "Closes #42"
- Request review

---

## Common Feature Types

### Feature Type 1: Add Configuration Option

**Example:** Custom output path for thumbnails

**Files to Modify:**
1. `application/config/config.json` — Add default value
2. `application/utils/config_manager.py` — Validate if needed
3. `application/utils/download_manager.py` — Use the config
4. `Docs/09_CONFIGURATION.md` — Document it

**Testing:**
```bash
1. Edit config.json
2. Set: "thumbnail_output_path": "./thumbnails"
3. Click Config button (verify edit)
4. Download a video
5. Check: Thumbnail saved to ./thumbnails/
```

---

### Feature Type 2: Add UI Button

**Example:** Export download history to CSV

**Files to Modify:**
1. `application/ui/main_window.py` — Add button, handler
2. `application/utils/download_manager.py` — Add export logic
3. `Docs/04_RUNNING_THE_APP.md` — Document new button
4. `README.md` — List new feature

**Code Template:**
```python
# In main_window.py, add to _build_ui():
export_csv_button = QPushButton("Export CSV")
export_csv_button.clicked.connect(self.on_export_csv_clicked)
button_layout.addWidget(export_csv_button)

# Add signal handler:
def on_export_csv_clicked(self):
    self.append_log("Exporting history...")
    
    from application.utils.download_manager import export_history_csv
    try:
        export_history_csv(self.db_path)
        self.append_log("✓ Exported to downloads_history.csv")
    except Exception as e:
        self.append_log(f"✗ Export failed: {e}")
```

---

### Feature Type 3: Database Enhancement

**Example:** Add video view count to cache

**Files to Modify:**
1. `application/db/database_manager.py` — Add column
2. `application/utils/video_info_extractor.py` — Populate it
3. `Docs/08_DATABASE_SCHEMA.md` — Document schema change
4. `PROGRESS_LOG.md` — Log the change

**Migration Pattern:**
```python
# In database_manager.py, in init_db():

# Ensure column exists
_ensure_column(conn, 'youtube_video_information', 
               'view_count INTEGER', 'Add view count tracking')

def _ensure_column(conn, table, column_def, reason):
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
        print(f"Added column: {reason}")
    except sqlite3.OperationalError:
        pass  # Column already exists
```

---

### Feature Type 4: Error Handling Improvement

**Example:** Better timeout detection

**Files to Modify:**
1. `application/utils/video_info_extractor.py` — Improve detection
2. `Docs/11_ERROR_HANDLING.md` — Document the error
3. `application/db/database_manager.py` — Log if needed

**Code Template:**
```python
def _should_retry_with_auth(output, config, attempted_auth):
    # Existing patterns
    patterns = [
        "429",
        "bot",
        "challenge"
    ]
    
    # Add new pattern
    patterns.append("rate limit")
    
    for pattern in patterns:
        if pattern.lower() in output.lower():
            return True
    
    return False
```

---

## Testing Checklist

### Unit Tests (If Applicable)

```python
# test_video_info_extractor.py
def test_parse_quick_download_urls():
    urls = "https://youtube.com/watch?v=abc, https://youtube.com/watch?v=def"
    result = parse_quick_download_urls(urls)
    assert len(result) == 2
    assert result[0] == "https://youtube.com/watch?v=abc"
```

### Integration Tests

```bash
1. Load channel
   - Verify: Table populated
   - Verify: DB has sources + videos
   
2. Download single video
   - Verify: File downloaded
   - Verify: DB has downloads row (status=success)
   
3. Handle error gracefully
   - Try invalid URL
   - Verify: Error shown, app doesn't crash
   - Verify: error table updated
   
4. Cancellation works
   - Start load
   - Click Stop immediately
   - Verify: Task stops, partial results kept
```

### Edge Cases

```
1. Empty playlist
2. Very large playlist (1000+ videos)
3. Network interruption (simulate with proxy)
4. Disk full (can't write file)
5. Permission denied (read-only directory)
6. Concurrent operations (multiple users?)
```

---

## Code Style Guidelines

### Python Style (PEP 8)

```python
# ✅ Good
def load_videos_from_channel(channel_id: str, max_workers: int = 4) -> list[VideoItem]:
    """Load all videos from a YouTube channel.
    
    Args:
        channel_id: YouTube channel ID or @handle
        max_workers: Number of parallel metadata workers
        
    Returns:
        List of VideoItem objects
        
    Raises:
        ValueError: If channel_id is invalid
    """
    if not channel_id:
        raise ValueError("channel_id cannot be empty")
    
    # Implementation...

# ❌ Avoid
def LoadVideos(id,workers=4):
    return FetchVids(id,workers)
```

### Comments & Docstrings

```python
# ❌ Unhelpful
x = get_data()  # Get data

# ✅ Clear
videos = list_videos_from_channel(channel_url)  # Fetch from YouTube

# ❌ Obvious
counter = 0  # Counter
counter += 1  # Increment counter

# ✅ Meaningful
successful_downloads = 0
successful_downloads += 1  # Track completed downloads
```

### Error Messages

```python
# ❌ Vague
raise Exception("Error")

# ✅ Specific
raise ValueError(f"Invalid YouTube URL: {url}. Expected format: https://youtube.com/...")
```

---

## Common Mistakes to Avoid

### ❌ Blocking the Main Thread

```python
# WRONG:
def on_download_clicked(self):
    items = list_videos()  # Blocks UI!
    self.populate_table(items)

# RIGHT:
def on_download_clicked(self):
    self.start_load()  # Spawns worker thread
    # UI stays responsive
```

### ❌ Hardcoded Paths

```python
# WRONG:
db_path = "/home/itzzinfinity/GitHub/yt_aio/db/yt_aio.db"

# RIGHT:
db_path = config['log_file_path']  # From config
```

### ❌ Unhandled Exceptions

```python
# WRONG:
process.run(command)

# RIGHT:
try:
    process.run(command)
except Exception as e:
    logger(f"Command failed: {e}")
    log_error(db_path, {'error': str(e)})
```

### ❌ Silent Failures

```python
# WRONG:
try:
    something_might_fail()
except:
    pass  # Fails silently!

# RIGHT:
try:
    something_might_fail()
except Exception as e:
    logger(f"Operation failed: {e}")
    raise  # Or handle specifically
```

---

## Documentation Updates

### When to Document

| Scenario | Document | Where |
|----------|----------|-------|
| New config key | Yes | 09_CONFIGURATION.md |
| New function | Yes | 05_MODULE_GUIDE.md |
| New database table | Yes | 08_DATABASE_SCHEMA.md |
| Bug fix | Maybe | PROGRESS_LOG.md |
| New feature | Yes | 01_PROJECT_OVERVIEW.md |

### Update PROGRESS_LOG.md

```markdown
## 2026-05-24 15:30 IST

- Implemented CSV export feature (issue #42)
  - Added: ExportButton to MainWindow
  - Added: export_history_csv() in download_manager
  - Saves to: downloads_history_CSV in current directory
  - Includes: All download records with timestamps
  - Tested with: 100+ record history

- Bug fix: Timeout detection improved
  - Now catches "rate limit" pattern
  - Retries with auth fallback
  - Prevents false failures on large playlists
```

---

## Asking for Help

### Where to Ask

1. **Code Questions:** Comment in relevant file
2. **Design Questions:** Create GitHub issue
3. **Bug Reports:** Include:
   - What happened
   - What you expected
   - Steps to reproduce
   - Error from database (SELECT * FROM errors LIMIT 1)
4. **Feature Requests:** Describe use case and benefit

---

## Release Checklist

Before bumping version:

- [ ] All tests pass
- [ ] Documentation updated
- [ ] No hardcoded paths
- [ ] Error handling complete
- [ ] Database schema migration tested
- [ ] Config keys documented
- [ ] PROGRESS_LOG.md updated
- [ ] README.md reflects new features
- [ ] Version number bumped in `__init__.py`

---

*Thank you for contributing to YT-AIO! 🙏*

