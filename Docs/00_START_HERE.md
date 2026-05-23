# 🚀 YT-AIO Developer Onboarding Guide

Welcome to **YT-AIO (YouTube All In One)** — a PyQt-based desktop application for downloading YouTube videos and audio with advanced caching, metadata extraction, and concurrent download management.

This guide is designed to get you up to speed on the codebase in the most efficient way possible.

---

## 📋 Reading Order (Recommended Path)

### **Phase 1: Overview & Context (15 minutes)**
1. **START HERE** → This file
2. [01_PROJECT_OVERVIEW.md](01_PROJECT_OVERVIEW.md) — Project goals, key features, tech stack
3. [02_ARCHITECTURE.md](02_ARCHITECTURE.md) — High-level system design and components

### **Phase 2: Setup & Execution (10 minutes)**
4. [03_INSTALLATION.md](03_INSTALLATION.md) — How to set up the development environment
5. [04_RUNNING_THE_APP.md](04_RUNNING_THE_APP.md) — How to run and test locally

### **Phase 3: Code Structure Deep Dive (30 minutes)**
6. [05_MODULE_GUIDE.md](05_MODULE_GUIDE.md) — Detailed breakdown of each module
7. [06_DATA_FLOW.md](06_DATA_FLOW.md) — How data moves through the system
8. [07_KEY_OPERATIONS.md](07_KEY_OPERATIONS.md) — Step-by-step walkthroughs of major workflows

### **Phase 4: Advanced Topics (20 minutes)**
9. [08_DATABASE_SCHEMA.md](08_DATABASE_SCHEMA.md) — SQLite structure and relationships
10. [09_CONFIGURATION.md](09_CONFIGURATION.md) — Config management and runtime path resolution
11. [10_THREADING_AND_CANCELLATION.md](10_THREADING_AND_CANCELLATION.md) — Task execution and cancellation model

### **Phase 5: Development Practices (15 minutes)**
12. [11_ERROR_HANDLING.md](11_ERROR_HANDLING.md) — Error handling patterns and logging
13. [12_CONTRIBUTION_GUIDE.md](12_CONTRIBUTION_GUIDE.md) — How to add features and submit changes

---

## 🎯 Quick Reference by Role

### **If you're working on the UI:**
Start with: [02_ARCHITECTURE.md](02_ARCHITECTURE.md) → [05_MODULE_GUIDE.md](05_MODULE_GUIDE.md) (UI section) → [06_DATA_FLOW.md](06_DATA_FLOW.md)

**Key files:** 
- `application/ui/main_window.py` (950 lines, PyQt orchestration)
- `application/ui/styles.qss` (Qt stylesheet)

### **If you're working on downloads/yt-dlp integration:**
Start with: [05_MODULE_GUIDE.md](05_MODULE_GUIDE.md) (utils section) → [07_KEY_OPERATIONS.md](07_KEY_OPERATIONS.md) → [06_DATA_FLOW.md](06_DATA_FLOW.md)

**Key files:**
- `application/utils/download_manager.py` (download orchestration)
- `application/utils/video_info_extractor.py` (yt-dlp integration)

### **If you're working on the database or caching:**
Start with: [08_DATABASE_SCHEMA.md](08_DATABASE_SCHEMA.md) → [05_MODULE_GUIDE.md](05_MODULE_GUIDE.md) (db section)

**Key files:**
- `application/db/database_manager.py` (SQLite operations)
- `application/config/config.json` (config file)

### **If you're adding configuration features:**
Start with: [09_CONFIGURATION.md](09_CONFIGURATION.md) → [05_MODULE_GUIDE.md](05_MODULE_GUIDE.md) (config section)

---

## 📁 Project Structure at a Glance

```
yt_aio/
├── __init__.py                           # Version and changelog
├── __main__.py                           # Entry point
├── run.py                                # Alternative entry
├── application/
│   ├── ui/
│   │   ├── main_window.py               # PyQt main window, task threads
│   │   └── styles.qss                   # Dark theme stylesheet
│   ├── utils/
│   │   ├── video_info_extractor.py      # yt-dlp metadata fetching
│   │   ├── download_manager.py          # Download orchestration
│   │   ├── config_manager.py            # Config handling
│   │   └── shared.py                    # Shared types, CancellationToken
│   ├── db/
│   │   ├── database_manager.py          # SQLite schema and operations
│   │   └── yt_aio.db                    # Database (created at runtime)
│   ├── config/
│   │   └── config.json                  # User-editable config
│   └── logs/
│       └── (reserved for future use)
└── Docs/                                 # THIS DOCUMENTATION
    ├── 00_START_HERE.md                 # You are here
    ├── 01_PROJECT_OVERVIEW.md           # Goals and features
    ├── 02_ARCHITECTURE.md               # System design
    ├── ... (more guides)
    └── diagrams/                        # Visual diagrams
```

---

## 🔑 Core Concepts

### **1. Layered Architecture**
```
UI Layer (PyQt)           ← User interacts here
    ↓ signals/slots
Business Logic Layer      ← yt-dlp, download orchestration
    ↓ function calls
Data Layer (SQLite)       ← Persistence and caching
```

Each layer is independent and testable in isolation.

### **2. Threading Model**
- **Main Thread:** Qt event loop and UI updates
- **Worker Threads:** TaskThread for long-running operations (load, download)
- **Thread Pool:** Parallel metadata fetches and downloads

### **3. Cancellation & Progress**
- **CancellationToken:** Thread-safe flag to stop tasks
- **Qt Signals:** Emit progress, completion, errors to UI
- **Logger Callbacks:** Real-time log output to textbox

### **4. Caching & Database**
- Check cache before fetching video metadata
- Relational model: sources → videos → downloads
- Relative paths in config resolved at runtime

---

## 🧠 Mental Models

### **"Load Channel" Workflow**
```
User: "I want to load videos from a channel"
  ↓
Click Download (no items loaded yet)
  ↓
start_load() → TaskThread → list_videos()
  ↓
✓ Check DB cache for existing videos from this channel
✓ Run yt-dlp --flat-playlist to get all video IDs
✓ Parallel fetch metadata for new videos (max 4 workers)
✓ Store results in database
  ↓
Emit: "Load complete - 142 videos found"
  ↓
Table shows all videos with checkboxes
```

### **"Download Selected" Workflow**
```
User: "Download the 5 videos I selected"
  ↓
Check selected rows → get_selected_items()
  ↓
start_download() → TaskThread → download_many()
  ↓
For each video in parallel (max CPU-2 workers):
  ✓ Resolve title from DB cache or fresh yt-dlp query
  ✓ Build yt-dlp format command (MP4 for video, M4A for audio)
  ✓ Execute with streaming output
  ✓ Handle bot challenges (retry with auth)
  ✓ Log result: success or error
  ↓
Emit: "Download complete: 5 success, 0 failed"
  ↓
Files saved to download directory
```

---

## ⚡ 5-Minute Quick Start

```bash
# 1. Install dependencies
pip install PyQt5 yt-dlp

# 2. Run the app
cd /home/itzzinfinity/GitHub/yt_aio
python3 -m yt_aio

# 3. Try it:
#    - Enter channel: https://www.youtube.com/@channel_name
#    - Click "Download" to load videos
#    - Select rows
#    - Click "Download" again
```

---

## 📚 Documentation Index

| File | Purpose | Read Time |
|------|---------|-----------|
| 01_PROJECT_OVERVIEW.md | Goals, features, tech stack | 5 min |
| 02_ARCHITECTURE.md | System design with diagrams | 10 min |
| 03_INSTALLATION.md | Setup and dependencies | 10 min |
| 04_RUNNING_THE_APP.md | How to run and debug | 5 min |
| 05_MODULE_GUIDE.md | Each module's functions | 15 min |
| 06_DATA_FLOW.md | Data movement and state | 10 min |
| 07_KEY_OPERATIONS.md | Detailed workflow walkthroughs | 15 min |
| 08_DATABASE_SCHEMA.md | SQLite tables and relationships | 10 min |
| 09_CONFIGURATION.md | Config keys and path resolution | 10 min |
| 10_THREADING_AND_CANCELLATION.md | Threading model | 10 min |
| 11_ERROR_HANDLING.md | Logging and error patterns | 10 min |
| 12_CONTRIBUTION_GUIDE.md | How to add features | 15 min |

**Total: ~2.5 hours for complete understanding**

---

## ❓ Common Questions

**Q: Where do I start?**
A: Read 01_PROJECT_OVERVIEW → 02_ARCHITECTURE → 05_MODULE_GUIDE

**Q: Where is the main UI code?**
A: `application/ui/main_window.py` (~950 lines)

**Q: How do downloads work?**
A: See 07_KEY_OPERATIONS.md → "Download Workflow" section

**Q: How is caching implemented?**
A: See 08_DATABASE_SCHEMA.md and 06_DATA_FLOW.md

**Q: How do I add a new feature?**
A: See 12_CONTRIBUTION_GUIDE.md

---

## 🎓 Learning Paths by Time

### 30 Minutes: Understand What This Does
- Read: 00_START_HERE, 01_PROJECT_OVERVIEW, 02_ARCHITECTURE
- Learn: What the app does and why it's designed this way

### 1 Hour: Set Up & Run Locally
- Add: 03_INSTALLATION, 04_RUNNING_THE_APP
- Result: Can run the app and see it in action

### 2 Hours: Understand the Code
- Add: 05_MODULE_GUIDE, 06_DATA_FLOW, 07_KEY_OPERATIONS
- Result: Can find code and understand execution flow

### 3 Hours: Ready to Modify
- Add: 08_DATABASE_SCHEMA, 09_CONFIGURATION, 10_THREADING, 11_ERROR_HANDLING
- Result: Can add features and debug issues

---

**Next Step:** Read [01_PROJECT_OVERVIEW.md](01_PROJECT_OVERVIEW.md)

---

*Last updated: May 2026*
