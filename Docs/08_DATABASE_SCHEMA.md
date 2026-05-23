# 🗄️ Database Schema: SQLite Structure

Complete documentation of the database design and relationships.

---

## Database Overview

**File Location:** `yt_aio/application/db/yt_aio.db`
**Type:** SQLite3 with WAL mode enabled
**Foreign Keys:** Enabled at runtime
**Initialization:** Automatic on first run

---

## Table: `sources`

Tracks channels and playlists.

```
CREATE TABLE sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL UNIQUE,      -- "channel:@user" or "playlist:ID"
    source_kind TEXT NOT NULL,             -- "channel" or "playlist"
    source_name TEXT,                      -- User-friendly name: "MrBeast"
    source_value TEXT NOT NULL,            -- "@username" or "PL..."
    source_url TEXT,                       -- Full YouTube URL
    created_at TEXT,                       -- ISO timestamp
    updated_at TEXT                        -- ISO timestamp
);

CREATE INDEX idx_source_kind ON sources(source_kind);
```

**Example Rows:**
```
id | source_key        | source_kind | source_name | source_value | source_url
---|-------------------|-------------|-------------|--------------|------------------
42 | channel:@vsauce   | channel     | Vsauce      | @vsauce      | https://youtube.com/@vsauce
```

---

## Table: `youtube_video_information`

Video metadata cache.

```
CREATE TABLE youtube_video_information (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL UNIQUE,         -- YouTube video ID
    title TEXT,                            -- Video title
    channel_name TEXT,                     -- Uploader channel name
    playlist_name TEXT,                    -- If part of playlist
    upload_date TEXT,                      -- Upload date (YYYYMMDD format)
    duration INTEGER,                      -- Duration in seconds
    view_count INTEGER,                    -- View count
    like_count INTEGER,                    -- Like count
    dislike_count INTEGER,                 -- Dislike count (if available)
    comment_count INTEGER,                 -- Comment count
    thumbnail_url TEXT,                    -- Thumbnail image URL
    video_url TEXT,                        -- Full YouTube URL
    source_id INTEGER,                     -- Foreign key: sources.id
    cached_at TEXT,                        -- When metadata was cached
    
    FOREIGN KEY(source_id) REFERENCES sources(id)
);

CREATE INDEX idx_video_id ON youtube_video_information(video_id);
CREATE INDEX idx_source_id ON youtube_video_information(source_id);
```

**Example Rows:**
```
id | video_id | title                  | channel_name | duration | source_id
---|----------|------------------------|--------------|----------|----------
1  | abc12345 | Spoons Don't Exist     | Vsauce       | 600      | 42
2  | def67890 | Why We Need Naps       | Vsauce       | 720      | 42
```

---

## Table: `downloads`

Download history with results.

```
CREATE TABLE downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,                            -- Downloaded video title
    url TEXT NOT NULL,                     -- YouTube URL
    status TEXT NOT NULL,                  -- "success" or "failed"
    error_message TEXT,                    -- Error details if failed
    timestamp TEXT NOT NULL,               -- ISO timestamp
    file_path TEXT,                        -- Where file was saved (success only)
    quality TEXT,                          -- Download quality used
    type TEXT NOT NULL,                    -- "audio" or "video"
    source_name TEXT,                      -- Channel/playlist name for context
    video_id TEXT,                         -- Video ID for cross-ref
    video_info_id INTEGER,                 -- Foreign key: youtube_video_information.id
    source_id INTEGER,                     -- Foreign key: sources.id
    
    FOREIGN KEY(video_info_id) REFERENCES youtube_video_information(id),
    FOREIGN KEY(source_id) REFERENCES sources(id)
);

CREATE INDEX idx_downloads_status ON downloads(status);
CREATE INDEX idx_downloads_timestamp ON downloads(timestamp);
```

**Example Rows:**
```
id | title              | status  | file_path                    | type  | timestamp
---|-------------------|---------|------------------------------|-------|------------------
1  | Spoons Don't Exist | success | /home/user/Downloads/spoons.m4a | audio | 2026-05-23 10:30:15
2  | Why We Need Naps   | success | /home/user/Downloads/naps.m4a   | audio | 2026-05-23 10:31:00
3  | Lost Video         | failed  | NULL                         | video | 2026-05-23 10:32:15
```

---

## Table: `errors`

Complete error logging with stack traces.

```
CREATE TABLE errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    error_message TEXT NOT NULL,           -- Error message
    timestamp TEXT NOT NULL,               -- ISO timestamp
    stack_trace TEXT,                      -- Full Python traceback
    url TEXT,                              -- Video/source URL
    action TEXT,                           -- "load", "download", "stop", "clear"
    user_input TEXT,                       -- What user entered (if relevant)
    script_version TEXT,                   -- App version when error occurred
    system_info TEXT                       -- Platform info (optional)
);

CREATE INDEX idx_errors_timestamp ON errors(timestamp);
CREATE INDEX idx_errors_action ON errors(action);
```

**Example Row:**
```
id | error_message              | timestamp           | action   | url
---|----------------------------|---------------------|----------|------------------
1  | HTTP Error 429: Too Many... | 2026-05-23 10:30:15 | load     | https://youtube.com/@channel
```

---

## Table: `user_actions`

Audit trail of user interactions.

```
CREATE TABLE user_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,                  -- "start", "stop", "clear", "open_config"
    timestamp TEXT NOT NULL                -- ISO timestamp
);

CREATE INDEX idx_user_actions_timestamp ON user_actions(timestamp);
```

**Example Rows:**
```
id | action           | timestamp
---|------------------|------------------
1  | start            | 2026-05-23 10:25:00
2  | load             | 2026-05-23 10:25:05
3  | download         | 2026-05-23 10:30:00
4  | stop             | 2026-05-23 10:35:00
```

---

## Table: `settings_changes`

Configuration change history.

```
CREATE TABLE settings_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_name TEXT NOT NULL,            -- Config key that changed
    old_value TEXT,                        -- Previous value
    new_value TEXT,                        -- New value
    timestamp TEXT NOT NULL                -- When changed
);

CREATE INDEX idx_settings_changes_timestamp ON settings_changes(timestamp);
```

---

## Table: `yt_aio_version`

Application version tracking.

```
CREATE TABLE yt_aio_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_number TEXT NOT NULL,          -- "0.3.1"
    release_date TEXT,                     -- Date of release
    changelog TEXT                         -- What changed
);
```

**Example Row:**
```
id | version_number | release_date | changelog
---|----------------|--------------|------------------
1  | 0.3.1          | 2026-04-24   | Fixed modular paths, relational DB
```

---

## Entity-Relationship Diagram

```
┌──────────────┐
│   sources    │
├──────────────┤
│ id (PK)      │
│ source_key   │
│ source_kind  │
│ source_name  │
└──────────────┘
      │ (1)
      │
      │ (source_id FK)
      │
      ├──────────────────────────┐
      │                          │
      ↓ (many)                   ↓ (many)
┌────────────────────────┐  ┌──────────────────┐
│ youtube_video_info     │  │   downloads      │
├────────────────────────┤  ├──────────────────┤
│ id (PK)                │  │ id (PK)          │
│ video_id (UNIQUE)      │  │ title            │
│ title                  │  │ url              │
│ channel_name           │  │ status           │
│ duration               │  │ file_path        │
│ view_count             │  │ type             │
│ source_id (FK) ────────┼──→ source_id (FK)   │
│                        │  │ video_info_id────┼──→ (back to here)
└────────────────────────┘  │ (FK)             │
                            └──────────────────┘

Other tables (no FK):
├─ errors (standalone)
├─ user_actions (standalone)
├─ settings_changes (standalone)
└─ yt_aio_version (standalone)
```

---

## Queries You'll Use

### Find all videos from a channel

```sql
SELECT v.video_id, v.title, v.duration, COUNT(d.id) as download_count
FROM youtube_video_information v
LEFT JOIN downloads d ON v.id = d.video_info_id
WHERE v.source_id = (SELECT id FROM sources WHERE source_value = '@vsauce')
ORDER BY v.title;
```

### Find failed downloads

```sql
SELECT title, url, error_message, timestamp
FROM downloads
WHERE status = 'failed'
ORDER BY timestamp DESC
LIMIT 10;
```

### Get recent errors with stack traces

```sql
SELECT error_message, stack_trace, action, timestamp
FROM errors
ORDER BY timestamp DESC
LIMIT 5;
```

### Find duplicate downloads

```sql
SELECT url, COUNT(*) as count, status
FROM downloads
GROUP BY url
HAVING count > 1
ORDER BY count DESC;
```

---

## Data Integrity Notes

1. **Cascade Deletes:** If a source is deleted, its related videos remain (orphaned)
   - Could implement CASCADE DELETE on source_id if needed
   
2. **Unique Constraints:**
   - video_id is UNIQUE in youtube_video_information
   - source_key is UNIQUE in sources
   - Prevents duplicate metadata
   
3. **Optional Foreign Keys:**
   - video_info_id in downloads can be NULL (for quick downloads)
   - source_id in downloads should never be NULL
   
4. **Indexing Strategy:**
   - video_id is indexed for fast cache lookups
   - source_id is indexed for source-based queries
   - timestamp is indexed for time-based filtering

---

## Typical Data Growth

For a user with normal usage:

```
After 1 month:
├─ sources: 5-10 rows (different channels/playlists)
├─ youtube_video_information: 500-2000 rows (cached videos)
├─ downloads: 50-200 rows (completed downloads)
├─ errors: 5-20 rows (failures, retries)
├─ user_actions: 100-500 rows (all interactions)
└─ Database size: ~2-5 MB

After 1 year (heavy usage):
├─ sources: 50-100 rows
├─ youtube_video_information: 10,000-50,000 rows
├─ downloads: 500-2000 rows
├─ errors: 50-200 rows
├─ user_actions: 1000-5000 rows
└─ Database size: ~20-100 MB
```

---

*Next: [09_CONFIGURATION.md](09_CONFIGURATION.md) — Configuration Management*

