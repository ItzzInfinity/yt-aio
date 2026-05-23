# 🔄 Threading & Cancellation Model

Understanding how the app handles concurrency and task cancellation.

---

## Threading Model Overview

```
Main Thread (Qt Event Loop)
├─ Runs at startup
├─ Handles: UI events, signals, slots
├─ Stays responsive: Must not block
└─ Draws widgets

Worker Thread(s) (TaskThread)
├─ Spawned on user action
├─ Runs: list_videos() or download_many()
├─ Emits signals: Communicate back to main thread
├─ Terminates: After task complete
└─ Max concurrent: 1 per app instance
```

---

## TaskThread (Worker Thread)

**Class:** `TaskThread(extends QThread)`

**Location:** `application/ui/main_window.py`

### Lifecycle

```
Creation:
  TaskThread(action="load", config=..., db_path=..., token=...)
  → Store in: self.worker
  
Start:
  self.worker.start()
  → Calls: run() in new OS thread
  
Execution:
  run():
    try:
      execute task (list_videos or download_many)
      emit load_complete or work_complete
    except Exception as e:
      emit work_failed(e)
  
Termination:
  → Automatically when run() returns
  → Clean up: Worker reference set to None
  → Garbage collected
```

### Signals (Thread-Safe Communication)

```
TaskThread.log_message(str)
  → Emitted by: list_videos(), download_many()
  → Received by: MainWindow.append_log()
  → Purpose: Real-time log updates

TaskThread.load_complete(items, source_name)
  → Emitted by: list_videos() completion
  → Received by: MainWindow.on_load_complete()
  → Purpose: Signal load done

TaskThread.work_complete(summary)
  → Emitted by: download_many() completion
  → Received by: MainWindow.on_work_complete()
  → Purpose: Signal download done

TaskThread.work_failed(error_msg)
  → Emitted by: Exception handler in run()
  → Received by: MainWindow.on_work_failed()
  → Purpose: Signal task failed
```

---

## CancellationToken (Thread-Safe Cancellation)

**Class:** `CancellationToken`

**Location:** `application/utils/shared.py`

### Purpose

Safely signal a worker thread to stop, even if it's blocked in a subprocess call.

### Design

```
class CancellationToken:
    def __init__(self):
        self._cancelled = False        # Flag
        self._lock = threading.Lock()  # Mutual exclusion
        self._processes = set()        # Registered subprocesses
    
    def cancel(self):
        # Called from: Main thread (UI button)
        # Thread-safe: Yes (uses lock)
        with self._lock:
            self._cancelled = True
            # Kill all registered processes
            for process in self._processes:
                try:
                    process.kill()
                except:
                    pass  # Already terminated
    
    def is_cancelled(self):
        # Called from: Worker thread (in loop)
        # Thread-safe: Yes (uses lock)
        with self._lock:
            return self._cancelled
    
    def register(process):
        # Called from: Worker thread (starting subprocess)
        with self._lock:
            self._processes.add(process)
    
    def unregister(process):
        # Called from: Worker thread (subprocess done)
        with self._lock:
            self._processes.discard(process)
```

### Usage Example

```python
# In list_videos():
token = get_cancellation_token()

# Run subprocess
try:
    token.register(process)
    result = process.communicate(timeout=0.5)
finally:
    token.unregister(process)

# Check if cancelled
if token.is_cancelled():
    raise CancelledError("User stopped")
```

### Scenario: User Clicks Stop

```
User clicks "Stop" button
        ↓
MainWindow.on_stop_clicked()
        ↓
self.cancel_token.cancel()
        ├─ Set _cancelled = True
        ├─ For each registered process:
        │  └─ process.kill()
        └─ Emit: log_message("Cancelled by user")
        ↓
Worker thread (if in subprocess):
├─ Subprocess killed immediately
└─ Return code: -9 (SIGKILL)
        ↓
Worker thread (if checking token):
├─ Check: if token.is_cancelled()
├─ Result: True
└─ Raise: CancelledError("...")
        ↓
TaskThread.run() catches exception:
        ├─ log_message("Cancelled...")
        └─ work_failed("Cancelled by user")
        ↓
MainWindow.on_work_failed():
        ├─ append_log(error_msg)
        ├─ set_idle_state()
        └─ Worker reference set to None
        ↓
Result:
├─ Task stopped cleanly
├─ No zombie processes
├─ Partial results retained
└─ User can retry
```

---

## Parallel Downloads (ThreadPoolExecutor)

**Used In:** `download_many()` in `download_manager.py`

### Design

```python
max_workers = config.get('max_concurrent_downloads', cpu_count() - 2)

with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = {
        executor.submit(download_one, target): target
        for target in targets
    }
    
    for future in as_completed(futures):
        target = futures[future]
        try:
            success = future.result()
            if success:
                success_count += 1
        except Exception as e:
            failure_count += 1
```

### Example with 6 Videos, max_workers=4

```
Timeline:
  T0: Worker 1 starts download video1
      Worker 2 starts download video2
      Worker 3 starts download video3
      Worker 4 starts download video4
      Waiting: video5, video6
  
  T30: Worker 1 finishes video1 (30 sec)
       Worker 1 starts download video5
  
  T45: Worker 3 finishes video3 (45 sec)
       Worker 3 starts download video6
  
  T60: Workers 2,4 finish
       All complete (most videos ~60 sec each)

Result: Total time ~60 sec (vs 6*60=360 sec sequential)
```

---

## Parallel Metadata Fetching

**Used In:** `list_videos()` in `video_info_extractor.py`

### Design

```python
max_workers = 4  # Fixed for metadata (less aggressive than downloads)

with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = {
        executor.submit(fetch_video_metadata, video_id, config, token): video_id
        for video_id in pending_ids
    }
    
    for future in as_completed(futures):
        video_id = futures[future]
        metadata = future.result()
        log_video_info(db_path, metadata)
```

### Rationale for 4 Workers

```
- YouTube API: ~1 req/sec per connection
- Max bandwidth ~4-5 concurrent without throttling
- Default: 4 workers (safe, effective)
- Can increase if needed but risk rate limiting
```

---

## Preventing Concurrent Tasks

### Check Before Starting

```python
def on_download_clicked(self):
    if self.is_busy():
        append_log("ERROR: Task already running")
        return
    
    # Safe to proceed...
```

### is_busy() Implementation

```python
def is_busy(self):
    return self.worker is not None and self.worker.isRunning()
```

### UI Feedback

```python
def set_busy_state(self, message, button_text):
    # Disable inputs to prevent user from starting new task
    source_input.setEnabled(False)
    channel_radio.setEnabled(False)
    playlist_radio.setEnabled(False)
    audio_radio.setEnabled(False)
    video_radio.setEnabled(False)
    
    # Show progress
    progress_bar.setVisible(True)
    download_button.setText(button_text)
    
    # Emit log
    append_log(message)

def set_idle_state(self):
    # Enable inputs
    source_input.setEnabled(True)
    channel_radio.setEnabled(True)
    # ... (re-enable all)
    
    # Hide progress
    progress_bar.setVisible(False)
    download_button.setText("Download")
```

---

## Race Conditions & Solutions

### Potential Issue 1: Modifying current_items while downloading

```
UNSAFE:
  MainWindow.on_download_clicked():
    items = get_selected_items()  # Get reference
    start_download(items)
  
  User clicks "Clear" → clears self.current_items
  
  download_many() tries to use items
    → Items still valid (local copy in download_many)
    → No crash, but items may be stale

SOLUTION: Already safe because:
  - items are copied to download_many() params
  - get_selected_items() returns list copy
  - download_many() never accesses MainWindow.current_items
```

### Potential Issue 2: Config changed during download

```
UNSAFE:
  download_many() uses self.config
  User clicks Config → changes file
  
SOLUTION: Already safe because:
  - Config loaded once at startup
  - Only re-loaded on app restart
  - In-flight downloads use loaded config
  
FUTURE:
  - Watch config file
  - Apply changes only between operations
  - Never change mid-task
```

### Potential Issue 3: Database writes from multiple threads

```
UNSAFE:
  Multiple workers writing to DB simultaneously
  
SOLUTION:
  SQLite WAL mode:
  - Each write gets exclusive lock
  - Readers can still read
  - No corruption
  - Slightly slower than single-threaded
```

---

## Best Practices

### ✅ DO

```python
# Pass config to worker, don't access MainWindow.config
download_many(..., config=self.config, ...)

# Check cancellation regularly
if token.is_cancelled():
    raise CancelledError(...)

# Emit signals, don't directly update UI
self.log_message.emit("Progress update")

# Register long-running processes
token.register(process)
try:
    # ... use process
finally:
    token.unregister(process)
```

### ❌ DON'T

```python
# Don't block main thread
# Don't call UI methods from worker thread directly
# Don't modify MainWindow widgets from worker
# Don't access unprotected shared state
# Don't ignore cancellation checks

# WRONG:
self.window.append_log("message")  # Race condition

# RIGHT:
self.log_message.emit("message")  # Safe signal
```

---

*Next: [11_ERROR_HANDLING.md](11_ERROR_HANDLING.md) — Error Patterns*

