# 📖 Project Overview: YT-AIO

## Project Name
**YT-AIO** — **YouTube All In One** Desktop Application

**Current Version:** 0.3.1

---

## 🎯 Goal

Provide a user-friendly PyQt desktop application that enables users to:
- Load and browse videos from YouTube channels or playlists
- Download videos or extract audio with automatic quality selection
- Cache metadata for fast subsequent lookups
- Download multiple items concurrently
- Handle YouTube bot challenges gracefully via browser cookies
- Maintain a complete audit log of all operations

---

## ✨ Key Features

### Core Downloads
- ✅ Download individual videos by URL
- ✅ Download entire channels (all videos from a channel)
- ✅ Download entire playlists
- ✅ Extract audio as M4A (best quality)
- ✅ Download video as MP4 (best quality)
- ✅ Quick download from comma-separated URL list

### Smart Metadata
- ✅ Per-video metadata extraction (title, duration, bitrate)
- ✅ SQLite-backed caching to avoid re-fetching
- ✅ Relational database linking sources → videos → downloads
- ✅ Channel/playlist deduplication

### User Experience
- ✅ PyQt5/PyQt6 GUI with live log output
- ✅ Selectable results table with checkboxes
- ✅ Real-time progress indication
- ✅ Dark theme with hover effects
- ✅ Cancellation support (stop running tasks)

### Robustness
- ✅ Automatic retry on failure (up to 3 times)
- ✅ YouTube bot challenge detection and retry with browser cookies
- ✅ Per-video error isolation (one failure doesn't stop the whole batch)
- ✅ Detailed error logging with stack traces

### Configuration & Customization
- ✅ JSON-based config file (editable from UI)
- ✅ Customizable download path
- ✅ Video/audio quality preferences
- ✅ Proxy support
- ✅ Cookie-based authentication fallback

### Logging & Audit
- ✅ SQLite database logging all operations
- ✅ Download history with success/failure status
- ✅ Error logs with stack traces and URLs
- ✅ User action audit trail (start, stop, clear, config open)
- ✅ Video metadata cache with timestamps

---

## 💻 Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| **Framework** | Python | 3.8+ |
| **GUI** | PyQt5 or PyQt6 | 5.x / 6.x |
| **Download Engine** | yt-dlp | Latest |
| **Database** | SQLite3 | Built-in |
| **Styling** | Qt Stylesheets (QSS) | Native |

### Dependencies
- **yt-dlp** — YouTube downloader (subprocess-based)
- **PyQt5/PyQt6** — Desktop GUI
- **sqlite3** — Built-in database
- **pathlib** — Path handling
- **threading** — Task execution
- **subprocess** — yt-dlp command execution

### Optional Dependencies
- **Brave Browser** — For cookie-based YouTube authentication fallback
- **Firefox/Chrome** — Browser cookie extraction as fallback

---

## 📊 Architecture at a Glance

```
┌─────────────────────────────────────┐
│    PyQt5/PyQt6 Desktop App          │
├─────────────────────────────────────┤
│  UI Layer                            │
│  - Main Window (PyQt)               │
│  - Task Threads (worker threads)    │
│  - Signal/Slot connections          │
├─────────────────────────────────────┤
│  Business Logic Layer                │
│  - Video Info Extractor (yt-dlp)   │
│  - Download Manager (orchestration) │
│  - Config Manager (settings)        │
├─────────────────────────────────────┤
│  Data Layer                          │
│  - SQLite Database                  │
│  - Caching (youtube_video_info)     │
│  - Audit Logging                    │
├─────────────────────────────────────┤
│  External Services                   │
│  - yt-dlp (subprocess)              │
│  - YouTube.com API (via yt-dlp)     │
│  - Browser Cookies (Brave/Firefox)  │
└─────────────────────────────────────┘
```

---

## 📈 User Workflow

### Scenario 1: Load and Download from a Channel

```
1. User opens app
2. Enters channel URL: https://www.youtube.com/@channel_name
3. Clicks "Download"
   → App fetches all 142 videos from channel
   → Shows them in a selectable table
   → Displays: ID, Name, Duration, Bitrate, Channel
4. User selects 5 videos (checkboxes)
5. Clicks "Download" again
   → App downloads 5 selected videos in parallel
   → Shows progress: "Downloaded 3/5 ✓"
   → Logs each result to database
6. Files appear in download folder
```

### Scenario 2: Quick Download from URLs

```
1. User has a list of YouTube links
2. Pastes into "Quick Download" textbox:
   https://www.youtube.com/watch?v=ID1,
   https://www.youtube.com/watch?v=ID2,
   https://www.youtube.com/watch?v=ID3
3. Clicks "Download"
   → App validates all URLs
   → Downloads all 3 videos in parallel
   → Shows progress and logs results
```

### Scenario 3: Retry on Bot Challenge

```
1. User tries to load a large playlist
2. yt-dlp hits YouTube bot challenge (HTTP 429)
3. App automatically retries using Brave browser cookies
4. If successful: continues silently (user doesn't notice)
5. If fails: shows error and suggests re-trying later
6. Logs attempt and outcome to error table
```

---

## 🗂️ Directory Structure

```
yt_aio/
├── __init__.py                        # Version: 0.3.1
├── __main__.py                        # python3 -m yt_aio entry point
├── run.py                             # Alternative entry point
│
├── application/
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py             # 950 lines: MainWindow + TaskThread classes
│   │   └── styles.qss                 # Dark theme stylesheet
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── video_info_extractor.py    # yt-dlp command building, metadata fetching
│   │   ├── download_manager.py        # Download orchestration, parallel execution
│   │   ├── config_manager.py          # Config loading, path resolution
│   │   └── shared.py                  # VideoItem, DownloadTarget, CancellationToken
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database_manager.py        # SQLite schema, CRUD operations
│   │   └── yt_aio.db                  # Database file (created at runtime)
│   │
│   ├── config/
│   │   └── config.json                # User-editable config
│   │
│   └── logs/
│       └── (reserved for future file logging)
│
└── Docs/
    ├── 00_START_HERE.md               # ← You are here
    ├── 01_PROJECT_OVERVIEW.md
    ├── 02_ARCHITECTURE.md
    ├── ... (more guides)
    └── diagrams/
        ├── architecture.md            # Mermaid diagram
        ├── data_flow.md               # Mermaid diagram
        └── workflow.md                # Mermaid diagram
```

---

## 🔄 Data Flow (50,000 Feet)

```
User Input (UI)
      ↓
Input Validation
      ↓
Determine Action (Load or Download)
      ↓
  [LOAD PATH]                    [DOWNLOAD PATH]
  - Call list_videos()           - Get selected items
  - Fetch metadata via yt-dlp    - Resolve titles
  - Cache in DB                  - Build yt-dlp commands
  - Return VideoItems            - Execute in parallel
                                 - Log results
      ↓                               ↓
   Emit: load_complete           Emit: work_complete
      ↓                               ↓
  UI Updates: Populate table      UI Updates: Show summary
      ↓                               ↓
  User can select rows            Files saved to disk
```

---

## 🎯 Key Design Principles

1. **Modularity** — Each component (UI, utils, db) is independent
2. **Threading** — Long operations run in worker threads, UI stays responsive
3. **Caching** — Avoid re-fetching known videos
4. **Graceful Degradation** — One failure doesn't break everything
5. **Logging** — Complete audit trail in database
6. **Configurability** — User can customize paths, quality, retry behavior
7. **Portability** — Relative paths in config, works from any directory

---

## 📋 Success Criteria

✅ Can load and display 100+ videos from a channel  
✅ Can download video and audio concurrently  
✅ Handles bot challenges with cookie fallback  
✅ Maintains complete audit log  
✅ Responsive UI (no freezing)  
✅ Detailed error messages  
✅ Works across different machines  

---

## 🚀 Getting Started

**Fastest way to understand the project:**

1. Read [02_ARCHITECTURE.md](02_ARCHITECTURE.md) (10 min) — understand the design
2. Read [05_MODULE_GUIDE.md](05_MODULE_GUIDE.md) (15 min) — see what each file does
3. Look at [03_INSTALLATION.md](03_INSTALLATION.md) (10 min) — set it up
4. Run it: `python3 -m yt_aio` — see it in action
5. Read [07_KEY_OPERATIONS.md](07_KEY_OPERATIONS.md) — understand execution flow

---

## 📝 Version History

- **v0.3.1** (April 24, 2026) — Modular architecture, relative paths, yt-dlp module fix
- **v0.3.0** (April 24, 2026) — Reorganized into application/ subdirectories
- **v0.2.x** — Database relational model, caching
- **v0.1.x** — Initial UI and download functionality

---

*Next: [02_ARCHITECTURE.md](02_ARCHITECTURE.md) — System Design & Architecture*

