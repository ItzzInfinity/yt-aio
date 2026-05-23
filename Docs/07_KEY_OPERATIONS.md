# 🔑 Key Operations: Detailed Walkthroughs

Step-by-step breakdowns of the most important workflows.

---

## Operation 1: Load Channel/Playlist

### What happens when user clicks "Download" without items loaded

```
PRECONDITION:
├─ User entered: "https://www.youtube.com/@vsauce"
├─ Selected: "Channel" radio button
├─ Table is empty (first time loading this source)
└─ No items selected

TRIGGER: User clicks "Download" button

EXECUTION:
1. MainWindow.on_download_clicked()
   └─ Detect: No items loaded for this source
      └─ Call: start_load("channel", "https://www.youtube.com/@vsauce")

2. start_load()
   ├─ Create: TaskThread(action="load", source_kind, source_value, ...)
   ├─ Create: CancellationToken (for stopping)
   ├─ Connect signals:
   │  ├─ TaskThread.log_message → MainWindow.append_log()
   │  └─ TaskThread.load_complete → MainWindow.on_load_complete()
   └─ Start: self.worker.start() (spawn OS thread)

3. TaskThread.run() (in worker thread)
   ├─ Call: list_videos(source_kind, source_value, ...)
   └─ Return: (items, source_name)

4. list_videos() Details:
   ├─ Resolve URL: "@vsauce" → "https://www.youtube.com/@vsauce"
   ├─ Create source: INSERT sources row, get source_id=42
   ├─ Fetch flat-playlist:
   │  ├─ Run: yt-dlp --flat-playlist --dump-single-json <URL>
   │  └─ Parse: {entries: [{id: vid1, title: ...}, ...]}
   │  └─ Emit: log_message("Found 142 videos")
   ├─ Check cache:
   │  ├─ Query: youtube_video_information WHERE video_id IN (vid1, vid2, ...)
   │  └─ Emit: log_message("50 cached, 92 new")
   ├─ Parallel metadata fetch:
   │  ├─ For each of 92 new videos:
   │  │  ├─ Run: yt-dlp -j https://youtube.com/watch?v=<video_id>
   │  │  ├─ Parse title, duration, uploader
   │  │  └─ INSERT INTO youtube_video_information
   │  ├─ ThreadPoolExecutor(max_workers=4)
   │  ├─ Emit: log_message("Fetched 50/92...")
   │  └─ Emit: log_message("Fetched 92/92 ✓")
   ├─ Convert to VideoItem:
   │  ├─ Merge cached + fresh data
   │  └─ Create: [VideoItem(...), VideoItem(...), ...]
   └─ Return: (items, "Vsauce")

5. TaskThread emits: load_complete(items, "Vsauce")
   └─ Signal → MainWindow (main thread)

6. MainWindow.on_load_complete(items, "Vsauce")
   ├─ Store: self.current_items = items
   ├─ Store: self.loaded_source_name = "Vsauce"
   ├─ Store: self.loaded_key = ("channel", "@vsauce")
   ├─ Call: populate_table(items)
   │  ├─ Set table row count: 142
   │  └─ For each item:
   │     ├─ Row[0]: QCheckBox (unchecked)
   │     ├─ Row[1]: video_id
   │     ├─ Row[2]: title
   │     ├─ Row[3]: duration_label ("10:00")
   │     └─ Row[4]: available_bitrate ("best")
   ├─ Call: set_idle_state()
   │  ├─ Hide progress bar
   │  ├─ Enable buttons
   │  └─ Change button text: "Download"
   └─ Emit: append_log("Load complete: 142 videos")

7. User sees: Table populated with 142 rows

POSTCONDITION:
├─ self.current_items has 142 VideoItems
├─ self.loaded_key is ("channel", "@vsauce")
├─ Table has 142 rows (all unchecked)
├─ Database: sources + youtube_video_information updated
└─ User can select rows and download
```

---

## Operation 2: Download Selected Videos

### What happens when user selects rows and clicks "Download"

```
PRECONDITION:
├─ Items already loaded
├─ User selected: rows 0, 5, 12 (3 videos)
├─ Selected media type: "audio"
└─ Download config ready

TRIGGER: User clicks "Download" button

EXECUTION:
1. MainWindow.on_download_clicked()
   ├─ Detect: Items loaded, some selected
   ├─ Call: get_selected_items()
   │  ├─ Loop through table rows
   │  ├─ Check if checkbox checked
   │  └─ Return: [VideoItem(vid1), VideoItem(vid5), VideoItem(vid12)]
   ├─ Get: media_type = "audio"
   ├─ Get: source_name = "Vsauce"
   └─ Call: start_download([VideoItem...], "Vsauce")

2. start_download()
   ├─ Create: TaskThread(action="download", targets, media_type, ...)
   ├─ Create: CancellationToken
   ├─ Connect signals
   └─ Start: self.worker.start()

3. TaskThread.run() (in worker thread)
   ├─ Call: download_many(targets, "audio", ...)
   └─ Return: summary = "Download complete: 3/3 ✓"

4. download_many() Details:
   ├─ Log: "Downloading 3 videos..."
   ├─ Create ThreadPoolExecutor(max_workers = CPU_COUNT - 2)
   ├─ For each of 3 targets (parallel):
   │  └─ submit: download_one(target, "audio")
   │
   ├─ PARALLEL EXECUTION:
   │  ├─ download_one(vid1):
   │  │  ├─ Resolve title: "Spoons Don't Exist"
   │  │  ├─ Build command: yt-dlp -f "bestaudio[ext=m4a]/best" ...
   │  │  ├─ Execute: run_streaming_command()
   │  │  ├─ Capture: "[download] 5.2%", "[download] 10.4%", ...
   │  │  ├─ Check: No bot challenge
   │  │  ├─ Extract file path: "spoons_dont_exist.m4a"
   │  │  ├─ Log: INSERT downloads (success)
   │  │  └─ Emit: log_message("✓ Downloaded: Spoons Don't Exist")
   │  │
   │  ├─ download_one(vid5):
   │  │  ├─ (same steps)
   │  │  └─ Emit: log_message("✓ Downloaded: Why We Need Naps")
   │  │
   │  └─ download_one(vid12):
   │     ├─ (same steps)
   │     └─ Emit: log_message("✓ Downloaded: Philosophy of Mind")
   │
   └─ Collect results: success=3, failure=0

5. Return: "Download complete: 3/3 ✓"

6. TaskThread emits: work_complete("Download complete: 3/3 ✓")
   └─ Signal → MainWindow (main thread)

7. MainWindow.on_work_complete(summary)
   ├─ Call: append_log(summary)
   ├─ Call: set_idle_state()
   ├─ Clear: self.worker = None
   └─ User sees: "Download complete: 3/3 ✓" in log

POSTCONDITION:
├─ Files: 3 .m4a files in Downloads folder
├─ Database: 3 rows in downloads table (status="success")
├─ UI: Ready for next action
└─ User can close or download again
```

---

## Operation 3: Handling YouTube Bot Challenge

### What happens if YouTube blocks our requests

```
SCENARIO: User tries to load large playlist

                ↓
        TaskThread.run()
                ↓
        list_videos() calls run_json_command()
                ↓
        yt-dlp executes and hits YouTube 429 (bot check)
                ↓
        Process returns output:
        "ERROR: HTTP Error 429: Too Many Requests"
                ↓
        Check: _should_retry_with_auth(output, config, False)
        Result: True (matches "429" pattern)
                ↓
        Emit: log_message("YouTube blocked us, retrying with auth...")
                ↓
        Set: attempted_auth = True
                ↓
        Rebuild command with:
        ├─ HOME → Brave profile directory (snap)
        ├─ PYTHONPATH → preserve yt_dlp module path
        └─ Cookie browser → brave
                ↓
        Execute: yt-dlp with Brave browser cookies
                ↓
        YouTube accepts (recognizes legitimate browser)
                ↓
        Success: flat-playlist fetched, metadata continues
                ↓
        User doesn't notice → Works silently
```

---

## Operation 4: Cancellation (User Stops Task)

### What happens when user clicks "Stop"

```
SCENARIO: User loading 1000-video playlist, gets impatient

                ↓
        User clicks "Stop" button
                ↓
        MainWindow.on_stop_clicked()
        ├─ Call: self.cancel_token.cancel()
        │  ├─ Set: _cancelled = True (thread-safe)
        │  ├─ For each registered process:
        │  │  └─ process.kill()
        │  └─ Emit: log_message("Cancelled by user")
        └─ Call: set_idle_state()
                ↓
        Worker thread (in list_videos):
        ├─ Check: if token.is_cancelled()
        ├─ Result: True
        ├─ Gracefully exit
        └─ Catch exception: CancelledError
                ↓
        TaskThread.run():
        ├─ except CancelledError:
        ├─ Emit: work_failed("Cancelled by user")
        └─ Return
                ↓
        MainWindow.on_work_failed("Cancelled by user")
        ├─ Log message
        ├─ Show error dialog
        └─ Set idle state
                ↓
        RESULT:
        ├─ Partial results retained
        ├─ Some metadata may be cached
        ├─ User can re-click to continue
        └─ All processes killed (no zombie processes)
```

---

## Operation 5: Retry on Network Failure

### What happens if yt-dlp times out

```
SCENARIO: Slow network or large playlist

                ↓
        run_json_command(command, timeout=45)
                ↓
        Subprocess starts
                ↓
        Output: "Fetching video 50 of 1000..."
                ↓
        45 seconds elapsed
                ↓
        Check: time.time() - start_time > 45
        Result: True
                ↓
        Action: process.kill()
                ↓
        Raise: TimeoutError("Command timeout after 45s")
                ↓
        Check: attempt < retries
        Result: True (attempt=1, retries=3)
                ↓
        Sleep: retry_delay (5 seconds)
                ↓
        Increment: attempt = 2
                ↓
        Retry: run command again
                ↓
        [Success this time]
                ↓
        Continue: with results
                OR
        [Fails again]
                ↓
        Repeat: up to max_retries (3)
                ↓
        If all fail: Raise exception
                ↓
        TaskThread catches: Emit work_failed()
```

---

## Operation 6: Error Logging

### Complete error path

```
SCENARIO: Download fails for a video

                ↓
        download_one(target):
        ├─ Try: build_command(), run_streaming_command(), ...
        └─ except Exception as e:
                ↓
        Catch exception:
        ├─ Log: append_log(f"✗ Failed: {title} - {e}")
        ├─ Call: log_download(db_path, {
        │         'title': 'Video Name',
        │         'url': 'https://...',
        │         'status': 'failed',
        │         'error_message': str(e)
        │       })
        │         └─ INSERT downloads (status="failed")
        │
        ├─ Call: log_error(db_path, {
        │         'error_message': str(e),
        │         'url': 'https://...',
        │         'action': 'download',
        │         'stack_trace': traceback.format_exc(),
        │         'user_input': 'title of video',
        │         'script_version': '0.3.1',
        │         'system_info': 'platform info'
        │       })
        │         └─ INSERT errors (with full stack trace)
        │
        └─ return False
                ↓
        download_many() continues:
        ├─ Mark failure_count++
        ├─ Emit: log_message("Failed: 1/3 ✗")
        └─ Move to next target
                ↓
        All downloads complete
        ├─ Return: "Download complete: 2/3 ✓, 1 failed"
        └─ Emit: work_complete(summary)
                ↓
        Database state:
        ├─ downloads table: 3 rows
        │  ├─ Row 1: status="success"
        │  ├─ Row 2: status="success"
        │  └─ Row 3: status="failed"
        │
        ├─ errors table: 1 new row
        │  ├─ error_message: detailed error
        │  ├─ stack_trace: full Python traceback
        │  ├─ url: video URL
        │  └─ timestamp: when it failed
        │
        └─ User can inspect database for details
```

---

*Next: [08_DATABASE_SCHEMA.md](08_DATABASE_SCHEMA.md) — Database Design*

