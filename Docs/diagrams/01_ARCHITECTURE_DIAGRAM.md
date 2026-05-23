# Architecture Diagram

## System Components & Relationships

```mermaid
graph TB
    User["👤 User"]
    UI["🖥️ MainWindow UI<br/>(PyQt5)"]
    TaskThread["⚙️ TaskThread<br/>(Worker)"]
    
    Shared["📦 Shared Types<br/>(VideoItem, CancellationToken)"]
    ConfigMgr["⚙️ ConfigManager<br/>(Load, Validate, Resolve)"]
    
    Extractor["🔍 VideoInfoExtractor<br/>(yt-dlp command builder)"]
    Downloader["⬇️ DownloadManager<br/>(ThreadPoolExecutor)"]
    
    YTDLP["📺 yt-dlp<br/>(Subprocess)"]
    YT["🌐 YouTube API"]
    
    DB["🗄️ SQLite Database<br/>(WAL mode)"]
    Config["📄 config.json<br/>(User settings)"]
    Cache["💾 Video Cache<br/>(youtube_video_information)"]
    DLHistory["📋 Download History<br/>(downloads table)"]
    Errors["⚠️ Error Log<br/>(errors table)"]
    
    User -->|1. Load Channel| UI
    UI -->|2. Create TaskThread| TaskThread
    TaskThread -->|3. Use config| ConfigMgr
    ConfigMgr -->|Resolve paths| Config
    
    TaskThread -->|"4. Call list_videos()"| Extractor
    Extractor -->|Check cache| Cache
    Extractor -->|5. Build yt-dlp cmd| YTDLP
    YTDLP -->|6. HTTP requests| YT
    YT -->|JSON response| YTDLP
    YTDLP -->|Parse JSON| Extractor
    
    Extractor -->|7. Parallel metadata fetch| Extractor
    Extractor -->|8. Cache results| Cache
    Extractor -->|9. Emit load_complete| TaskThread
    
    TaskThread -->|Signal back to| UI
    UI -->|Display items| User
    
    User -->|10. Select & Download| UI
    UI -->|11. Spawn TaskThread| TaskThread
    TaskThread -->|"12. Call download_many()"| Downloader
    
    Downloader -->|13. ThreadPoolExecutor| Downloader
    Downloader -->|Per-video command| YTDLP
    YTDLP -->|Download stream| YT
    
    Downloader -->|14. Log result| DB
    Extractor -->|Log to cache| DB
    TaskThread -->|Log errors| DB
    
    DB -->|Store| Cache
    DB -->|Store| DLHistory
    DB -->|Store| Errors
    
    CancelToken["🛑 CancellationToken<br/>(Thread-safe flag)"]
    UI -->|User clicks Stop| CancelToken
    CancelToken -->|Kill processes| YTDLP
    
    style User fill:#fff3cd
    style UI fill:#cfe2ff
    style TaskThread fill:#e7d4f5
    style YTDLP fill:#f8d7da
    style YT fill:#fff
    style DB fill:#d1e7dd
    style Config fill:#e2e3e5
