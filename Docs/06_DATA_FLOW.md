# 🔄 Data Flow Through the System

This document traces how data moves from user input through the application.

---

## End-to-End Data Flow: Load Channel Workflow

```
┌─────────────────────────────────────────────────────────┐
│ USER INPUT: Channel URL https://www.youtube.com/@vsauce │
└─────────────────────────────────────────────────────────┘
                        ↓ (UI captures input)
┌─────────────────────────────────────────────────────────┐
│ MainWindow.on_download_clicked()                         │
│ - source_value = "@vsauce" (from textbox)              │
│ - source_kind = "channel" (from radio button)           │
│ - action = "load" (nothing selected yet)                │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ start_load("channel", "@vsauce")                        │
│ - Create TaskThread with these params                   │
│ - Spawn worker thread                                   │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ list_videos(source_kind="channel", source_value="@vsauce")
│ (executes in worker thread)                             │
└─────────────────────────────────────────────────────────┘
                        ↓
    ┌───────────────────┼───────────────────┐
    ↓                   ↓                   ↓
┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│Resolve URL   │ │Check Database│ │Fetch from YouTube│
│              │ │Cache         │ │                  │
└──────────────┘ └──────────────┘ └──────────────────┘

Step 1: Resolve URL
─────────────────────
Input: source_kind="channel", source_value="@vsauce"
Output: source_url="https://www.youtube.com/@vsauce"

Step 2: Create Source Record
──────────────────────────────
INSERT INTO sources (source_kind, source_value, source_url, source_name)
VALUES ("channel", "@vsauce", "https://www.youtube.com/@vsauce", NULL)
→ Returns: source_id = 42

Step 3: Fetch Flat Playlist (All Video IDs)
─────────────────────────────────────────────
Execute: yt-dlp --flat-playlist --dump-single-json <URL>
Returns: 
{
  "id": "UCXuqSBlHAE6Xw-yeJA7Ling",
  "entries": [
    {"id": "video1", "title": "Space..."},
    {"id": "video2", "title": "Why..."},
    ...
    {"id": "video142", "title": "Mind..."}
  ]
}

Step 4: Check Database Cache
──────────────────────────────
SELECT * FROM youtube_video_information 
WHERE video_id IN (video1, video2, ..., video142)
→ Returns: 50 cached videos

Step 5: Parallel Fetch Metadata
────────────────────────────────
For each of 92 uncached videos (parallel, max 4 workers):
  - Run: yt-dlp -j https://www.youtube.com/watch?v=<video_id>
  - Parse: title, duration, uploader, view_count, etc.
  - INSERT INTO youtube_video_information (...) VALUES (...)
  - Emit: log_message("Fetched 50/92...")

Step 6: Convert to VideoItem Objects
──────────────────────────────────────
For each of 142 videos:
  VideoItem(
    video_id="video1",
    title="Space: A Journey...",
    url="https://www.youtube.com/watch?v=video1",
    duration_seconds=600,
    duration_label="10:00",
    available_bitrate="best",
    channel_name="Vsauce",
    source_name="Vsauce",
    view_count=5000000
  )
→ Returns: list of 142 VideoItem objects

Step 7: Emit Signal to UI
──────────────────────────
Emit: load_complete(items=[VideoItem...], source_name="Vsauce")

Step 8: UI Update (Main Thread)
────────────────────────────────
on_load_complete(items, source_name):
  - Store items in self.current_items
  - Store loaded_key = ("channel", "@vsauce")
  - Call populate_table(items)
    - Create 142 rows in QTableWidget
    - Column 0: Checkbox (unchecked)
    - Column 1: video_id
    - Column 2: title
    - Column 3: duration_label
    - Column 4: available_bitrate
  - Emit: set_idle_state()
  - Log: "Load complete: 142 videos"

┌─────────────────────────────────────────────────────────┐
│ UI NOW SHOWS: Table with 142 videos, user can select   │
└─────────────────────────────────────────────────────────┘
```

---

## End-to-End Data Flow: Download Workflow

```
┌─────────────────────────────────────────────────────────┐
│ USER ACTION: Select 3 rows in table, click Download     │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ get_selected_items()                                    │
│ - Loop through table rows                              │
│ - Find checked checkboxes                              │
│ - Return: [VideoItem(video1), VideoItem(video2), ...]  │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ start_download(targets=[VideoItem...], source_name=...)│
│ - Create TaskThread with targets                       │
│ - Spawn worker thread                                  │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ download_many(targets, media_type="audio", ...)         │
│ (executes in worker thread, max_workers = CPU-2)        │
└─────────────────────────────────────────────────────────┘
                        ↓
    For each target in parallel:
    ┌──────────────────────────────────────┐
    │ download_one(target, "audio")        │
    └──────────────────────────────────────┘
                        ↓
    Step A: Resolve Title
    ──────────────────────
    if target.title:
        title = target.title
    else:
        query DB for title (cache hit)
        if not found:
            run yt-dlp -j to fetch
    
    Step B: Build Download Command
    ───────────────────────────────
    For audio: format = "bestaudio[ext=m4a]/best"
    For video: format = "bv*+ba/b"
    
    Command:
    yt-dlp -f "bestaudio[ext=m4a]/best" \
           -o "~/Downloads/%(title)s.%(ext)s" \
           https://www.youtube.com/watch?v=<video_id>
    
    Step C: Execute Download
    ────────────────────────
    Run subprocess.Popen(command)
    Capture output line-by-line:
      - "[download] 5.2% of ~50.00MiB at ..."
      - "[download] 10.4% of ~50.00MiB at ..."
      - ...
      - "[download] 100% of ~50.00MiB in ..."
    
    Step D: Handle Bot Challenge
    ─────────────────────────────
    if output contains "429" or "bot challenge":
        Log: "YouTube blocked us, retrying with auth..."
        Rebuild command with: use_auth=True
        Retry once with browser cookies
    
    Step E: Extract File Path
    ──────────────────────────
    Parse output for: "Final location: /home/user/..."
    → file_path = "/home/user/Downloads/video_title.m4a"
    
    Step F: Log Success
    ───────────────────
    INSERT INTO downloads (
      title, url, status, file_path, timestamp, type, quality
    ) VALUES (
      "Video Title", "https://youtube.com/watch?v=...", 
      "success", "/home/user/Downloads/video_title.m4a",
      "2026-05-23 10:30:15", "audio", "best"
    )
    
    Step G: Emit Progress
    ─────────────────────
    Emit: log_message("✓ Downloaded: Video Title (45.2 MB)")

                        ↓ (All parallel tasks complete)
┌─────────────────────────────────────────────────────────┐
│ Result Summary                                          │
│ "Download complete: 3/3 ✓"                             │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ Emit: work_complete(summary)                            │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ on_work_complete(summary)                               │
│ - Log summary to UI                                     │
│ - Set idle state                                        │
│ - Clear worker reference                               │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ USER SEES: "Download complete: 3/3 ✓"                  │
│ FILES: 3 audio files in ~/Downloads/                    │
│ DATABASE: All operations logged to yt_aio.db            │
└─────────────────────────────────────────────────────────┘
```

---

## Database State Changes

### After Load Operation

```
sources table:
┌────┬──────────────┬─────────────┬──────────────────────────┐
│ id │ source_kind  │ source_value│ source_name              │
├────┼──────────────┼─────────────┼──────────────────────────┤
│ 42 │ channel      │ @vsauce     │ Vsauce                   │
└────┴──────────────┴─────────────┴──────────────────────────┘

youtube_video_information table:
┌────┬──────────┬──────────────────────┬─────────────┬────────────┐
│ id │ video_id │ title                │ channel_name│ source_id  │
├────┼──────────┼──────────────────────┼─────────────┼────────────┤
│ 1  │ abcd1234 │ Spoons Don't Exist   │ Vsauce      │ 42         │
│ 2  │ efgh5678 │ Why We Need Naps     │ Vsauce      │ 42         │
│ 3  │ ijkl9012 │ Philosophy of Mind   │ Vsauce      │ 42         │
│...                                                               │
│142 │ xyz99999 │ Inertia of Thought   │ Vsauce      │ 42         │
└────┴──────────┴──────────────────────┴─────────────┴────────────┘
```

### After Download Operation

```
downloads table (new rows):
┌────┬──────────────────────┬────────────┬──────────┬────────────┐
│ id │ title                │ status     │ type     │ source_id  │
├────┼──────────────────────┼────────────┼──────────┼────────────┤
│ 1  │ Spoons Don't Exist   │ success    │ audio    │ 42         │
│ 2  │ Why We Need Naps     │ success    │ audio    │ 42         │
│ 3  │ Philosophy of Mind   │ success    │ audio    │ 42         │
└────┴──────────────────────┴────────────┴──────────┴────────────┘

user_actions table (new rows):
┌────┬──────────┬────────────────────────┐
│ id │ action   │ timestamp              │
├────┼──────────┼────────────────────────┤
│ 1  │ start    │ 2026-05-23 10:25:00    │
│ 2  │ download │ 2026-05-23 10:30:15    │
└────┴──────────┴────────────────────────┘
```

---

## State Transitions

### MainWindow State Machine

```
IDLE
  ↓ (user clicks Download, no items loaded)
LOADING
  ├─ Disable: input, buttons
  ├─ Show: progress bar, "Loading..." status
  ├─ In background: TaskThread.run() → list_videos()
  ↓
IDLE (on success)
  ├─ Enable: all buttons
  ├─ Hide: progress bar
  ├─ Show: populated table
  ├─ Stored in: self.current_items
  └─ Next action: user can select rows
  
  OR
  
ERROR (on failure)
  ├─ Enable: all buttons
  ├─ Hide: progress bar
  ├─ Show: error message in log
  ├─ Table: unchanged (empty if first load)
  └─ Next action: user can retry

DOWNLOADING
  ├─ Disable: input, radio buttons, select buttons
  ├─ Show: progress bar, "Downloading..." status
  ├─ In background: TaskThread.run() → download_many()
  ↓
IDLE (on completion)
  ├─ Enable: all buttons
  ├─ Hide: progress bar
  ├─ Show: summary "Download complete: X/Y ✓"
  ├─ Files: written to disk
  └─ DB: updated with download records
```

---

## Memory/Reference Flow

### Object Lifecycle

```
┌──────────────────────────────────────┐
│ MainWindow.__init__()                │
│ ├─ Load config → store in self.config
│ ├─ Load db → store db_path in self
│ └─ Create UI widgets → store in self
└──────────────────────────────────────┘
           ↓
     [Running] ← Persists until app closes

During load:
┌──────────────────────────────────────┐
│ Create TaskThread → store in self.worker
│ ThreadSpawned → worker.start()
└──────────────────────────────────────┘
           ↓
     [Running] ← In separate OS thread
           ↓
    [Emits signals]
           ↓
    [Completes]
           ↓
┌──────────────────────────────────────┐
│ MainWindow.on_load_complete()        │
│ ├─ Store items → self.current_items
│ ├─ Update UI → populate_table()
│ └─ Clear worker → self.worker = None
└──────────────────────────────────────┘
           ↓
   [Worker thread terminated, garbage collected]
```

---

## Error Path Example

```
User: clicks Download on invalid URL

                        ↓
        MainWindow.on_download_clicked()
                        ↓
        start_load("channel", "not_a_real_channel")
                        ↓
        TaskThread.run()
                        ↓
        list_videos()
                        ↓
        run_json_command() for yt-dlp call
                        ↓
        yt-dlp returns ERROR (invalid URL)
                        ↓
        Exception raised: "Invalid channel..."
                        ↓
        Caught in TaskThread.run():
        except Exception as e:
            error_msg = str(e)
            self.log_message.emit(error_msg)
            self.work_failed.emit(error_msg)
                        ↓
        Signals propagate to MainWindow (main thread)
                        ↓
        MainWindow.on_work_failed(error_msg):
            append_log(error_msg)
            log_error(db_path, {
                'error_message': error_msg,
                'stack_trace': traceback.format_exc(),
                'url': 'not_a_real_channel',
                'action': 'load'
            })
            show_warning_dialog(error_msg)
            set_idle_state()
                        ↓
        DB: errors table now has new row
        UI: shows error dialog
        User can retry or try different URL
```

---

*Next: [07_KEY_OPERATIONS.md](07_KEY_OPERATIONS.md) — Detailed Workflow Walkthroughs*

