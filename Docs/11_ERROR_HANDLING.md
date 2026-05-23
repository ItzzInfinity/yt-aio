# ⚠️ Error Handling & Logging

How errors are caught, logged, and recovered from.

---

## Error Hierarchy

```
Exception
├─ Network Errors
│  ├─ HTTP 429 (Bot Challenge)
│  ├─ HTTP 403 (Forbidden)
│  ├─ HTTP 5xx (Server Error)
│  └─ Connection Timeout
│
├─ Process Errors
│  ├─ Subprocess Timeout
│  ├─ Non-zero Exit Code
│  └─ Process Killed
│
├─ Data Errors
│  ├─ Invalid URL
│  ├─ Missing Metadata
│  ├─ Null Title
│  └─ Parse JSON Error
│
├─ Auth Errors
│  ├─ "Sign in to confirm..."
│  ├─ Cookie Expired
│  └─ Cookie Not Found
│
└─ File Errors
   ├─ Download Path Invalid
   ├─ No Disk Space
   └─ File Already Exists
```

---

## Error Handling Flow

### Level 1: Subprocess (yt-dlp)

```
yt-dlp command execution
        ↓
return_code = process.wait()
        ↓
if return_code != 0:
    ├─ Capture stderr
    ├─ Check: Is it a known error?
    └─ Decide: Retry? Fallback? Fail?
```

### Level 2: Business Logic (download_manager.py)

```
download_one(target):
    try:
        result = build_and_execute_command()
        
        if return_code != 0:
            raise Exception(f"yt-dlp failed: {stderr}")
        
        return True (success)
        
    except BotChallengeError:
        # Auto-retry with auth
        return download_one_with_auth()
        
    except Exception as e:
        # Log and continue
        log_error(e)
        log_download(status="failed", error=str(e))
        return False
```

### Level 3: Orchestration (TaskThread)

```
TaskThread.run():
    try:
        items = list_videos()
        self.load_complete.emit(items)
        
    except Exception as e:
        error_msg = format_error(e)
        self.log_message.emit(error_msg)
        self.work_failed.emit(error_msg)
        
        # Errors logged to database here
```

### Level 4: UI (MainWindow)

```
MainWindow.on_work_failed(error_msg):
    ├─ Log message
    ├─ Log error to database
    ├─ Show dialog to user
    └─ Return to idle state
```

---

## Common Errors & Responses

### HTTP 429: Bot Challenge

**Cause:** YouTube blocking automated requests

**Detection:**
```python
def _should_retry_with_auth(output):
    return any([
        "429" in output,
        "bot" in output.lower(),
        "challenge" in output.lower(),
        "too many requests" in output.lower()
    ])
```

**Recovery:**
```python
if _should_retry_with_auth(output):
    logger("Retrying with browser cookies...")
    retry_with_auth=True
    result = run_json_command(..., use_auth=True)
    # If success: continue silently
    # If fail: log error, return partial results
```

**User Impact:** None if retry succeeds; retried silently

---

### Command Timeout

**Cause:** Slow network, large playlist, or YouTube throttling

**Detection:**
```python
if (time.time() - start_time) > timeout:
    process.kill()
    raise TimeoutError(f"Timeout after {timeout}s")
```

**Recovery:**
```python
attempt = 1
while attempt <= max_retries:
    try:
        result = run_command(timeout=120)
        return result  # Success
    except TimeoutError:
        attempt += 1
        sleep(retry_delay)
        continue
raise Exception("All retries exhausted")
```

**User Impact:** Slightly slower, but operation succeeds eventually

---

### Invalid URL

**Cause:** User entered malformed YouTube URL

**Detection:**
```python
def validate_youtube_url(url):
    return "youtube.com" in url or "youtu.be" in url
```

**Recovery:**
```python
if not validate_youtube_url(url):
    raise ValueError("Invalid YouTube URL")
    # Caught in TaskThread.run()
    # Emitted to MainWindow
    # User shown error dialog
```

**User Impact:** Error message shown, can retry with different URL

---

### Download Already Exists

**Cause:** File already saved with same name

**Detection:**
```python
if path.exists():
    # Option 1: Overwrite
    # Option 2: Create variant (filename (2).mp4)
    # Current: Overwrite (matches yt-dlp default)
```

**Recovery:** Overwrite file (default yt-dlp behavior)

**User Impact:** Previous file replaced silently

---

## Logging Strategy

### Database Logging

**tables: `errors`, `downloads`, `user_actions`**

```python
log_error(db_path, {
    'error_message': 'HTTP Error 429: Too Many Requests',
    'timestamp': '2026-05-23 10:30:15',
    'stack_trace': traceback.format_exc(),
    'url': 'https://youtube.com/@channel',
    'action': 'load',
    'user_input': '@channel',
    'script_version': '0.3.1',
    'system_info': 'Linux ubuntu 5.10.0'
})
```

### Retrieving Logs

```bash
# View recent errors
sqlite3 yt_aio/application/db/yt_aio.db
SELECT * FROM errors ORDER BY timestamp DESC LIMIT 5;

# View failed downloads
SELECT title, error_message FROM downloads WHERE status='failed';

# Count failures by action
SELECT action, COUNT(*) FROM errors GROUP BY action;
```

---

## Error Recovery Patterns

### Pattern 1: Retry with Backoff

```python
def retry_with_exponential_backoff(func, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries:
                raise
            
            delay = 2 ** attempt  # 2, 4, 8 seconds
            logger(f"Attempt {attempt} failed, retrying in {delay}s...")
            time.sleep(delay)
```

### Pattern 2: Fallback to Cache

```python
def get_video_title(url, db_path):
    try:
        # Fresh fetch
        return fetch_title_via_ytdlp(url)
    except Exception:
        # Fallback to cache
        cached = get_cached_video_by_url(db_path, url)
        if cached:
            return cached['title']
        
        # Final fallback
        return "Unknown"
```

### Pattern 3: Continue on Partial Failure

```python
for target in targets:
    try:
        download_one(target)
        success_count += 1
    except Exception as e:
        logger(f"Failed: {target.title}")
        failure_count += 1
        # Continue to next

logger(f"Complete: {success_count}/{len(targets)} ✓")
```

---

## Best Practices

### ✅ DO

```python
# Catch specific exceptions
try:
    result = yt_dlp_command()
except subprocess.TimeoutExpired:
    logger("Timeout, retrying...")
except subprocess.CalledProcessError:
    logger("Command failed, logging...")

# Log full context
except Exception as e:
    log_error({
        'error_message': str(e),
        'stack_trace': traceback.format_exc(),
        'url': url,
        'context': 'downloading video'
    })

# Continue on expected errors
if download_one fails:
    log_error()
    continue to next
    
# Never swallow exceptions silently
# Always log, always emit signal
```

### ❌ DON'T

```python
# Catching all exceptions silently
try:
    something()
except:
    pass  # BAD!

# Logging incomplete information
log("Error")  # Missing context

# Failing on first error
for target in targets:
    download_one(target)  # One fail = stop all

# Not checking process return codes
process.run(command)
# Use result without checking return_code
```

---

## Debugging Tips

### Enable Verbose Output

**Add to video_info_extractor.py:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# In run_json_command():
logger(f"Command: {' '.join(command)}")
logger(f"Environment: {env}")
```

### Monitor Database

```bash
# Watch errors in real-time
sqlite3 yt_aio/application/db/yt_aio.db
SELECT error_message, timestamp FROM errors 
ORDER BY timestamp DESC;

# Get latest
.mode column
SELECT * FROM errors ORDER BY id DESC LIMIT 1;
```

### Check System Resources

```bash
# Monitor memory/CPU during download
top -u $USER

# Check disk space
df -h ~/Downloads

# Monitor network
iftop -n
```

---

*Next: [12_CONTRIBUTION_GUIDE.md](12_CONTRIBUTION_GUIDE.md) — How to Contribute*

