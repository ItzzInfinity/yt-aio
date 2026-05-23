# Load Channel Workflow

## Step-by-step execution flow

```mermaid
sequenceDiagram
    participant U as User
    participant UI as MainWindow
    participant TT as TaskThread
    participant Ex as VideoInfoExtractor
    participant YTDLP as yt-dlp
    participant YT as YouTube
    participant DB as Database
    
    U->>UI: Enter "https://youtube.com/@channelname"
    U->>UI: Click "Load" button
    
    UI->>UI: Validate URL
    UI->>UI: set_busy_state()
    UI->>TT: Create TaskThread
    TT->>TT: start() - runs in background thread
    
    TT->>Ex: list_videos(url, config, db_path)
    
    Ex->>DB: get_cached_videos(video_ids=None)
    DB-->>Ex: Empty list (first load)
    
    Ex->>Ex: build_yt_dlp_command("--flat-playlist", "--dump-single-json")
    Ex->>YTDLP: subprocess.run(command, timeout=None)
    
    YTDLP->>YT: GET /api/... (fetch full playlist JSON)
    YT-->>YTDLP: Large JSON response (~100KB for 1000 videos)
    
    YTDLP-->>Ex: return_code=0, stdout=JSON
    
    Ex->>Ex: Parse JSON -> video_id list
    Ex->>Ex: Identify missing from cache
    
    Ex->>Ex: ThreadPoolExecutor(max_workers=4)
    
    par Parallel Metadata Fetch
        Ex->>YTDLP: fetch_video_metadata(video_id_1)
        YTDLP->>YT: GET /watch?v=...
        YT-->>YTDLP: JSON
        Ex->>DB: log_video_info(metadata)
        
        Ex->>YTDLP: fetch_video_metadata(video_id_2)
        YTDLP->>YT: GET /watch?v=...
        YT-->>YTDLP: JSON
        Ex->>DB: log_video_info(metadata)
    end
    
    Ex->>Ex: Collect all VideoItem objects
    Ex-->>TT: return items[]
    
    TT->>UI: load_complete.emit(items, source_name)
    
    UI->>UI: on_load_complete(items)
    UI->>UI: populate_table(items)
    UI->>UI: set_idle_state()
    
    UI-->>U: Display 1000 items in table
    
    rect rgb(220, 240, 255)
        Note over DB: Database State<br/>- sources table: +1 row<br/>- youtube_video_information: +1000 rows<br/>- Committed within transaction
    end
