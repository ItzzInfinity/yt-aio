# Download Workflow

## Download process with parallel execution

```mermaid
graph TD
    A["User selects 5 videos<br/>Clicks Download"] --> B["TaskThread spawned<br/>download_many called"]
    B --> C["ThreadPoolExecutor<br/>max_workers=4"]
    C --> D["Submit 5 download_one<br/>tasks to executor"]
    
    D --> E["Worker 1: Start video1"]
    D --> F["Worker 2: Start video2"]
    D --> G["Worker 3: Start video3"]
    D --> H["Worker 4: Start video4"]
    D --> I["video5 waits in queue"]
    
    E --> E1["Build yt-dlp command"]
    E1 --> E2["Execute subprocess"]
    E2 --> E3["Stream to ~/Downloads"]
    E3 --> E4{"Completed?"}
    E4 -->|Yes| E5["Log success<br/>downlaod_count++"]
    E4 -->|No| E6["Log error<br/>failure_count++"]
    E5 --> E7["Worker 1 free"]
    E6 --> E7
    E7 --> I
    I --> J["Worker 1: Start video5"]
    
    F --> F1["Build yt-dlp command"]
    F1 --> F2["Execute subprocess"]
    F2 --> F3["Stream to ~/Downloads"]
    F3 --> F4{"Completed?"}
    F4 -->|429| F5["Retry with auth"]
    F5 --> F6["Log retry attempt"]
    F6 --> F4
    F4 -->|Yes| F7["Log success"]
    F4 -->|No| F8["Log error"]
    
    G --> G1["Execute..."]
    H --> H1["Execute..."]
    
    E5 --> K["All done"]
    F7 --> K
    G1 --> K
    H1 --> K
    J --> K
    
    K --> L["Emit work_complete"]
    L --> M["MainWindow.on_work_complete"]
    M --> N["Show summary:<br/>Success: 4, Failed: 1"]
    
    style E5 fill:#90EE90
    style E6 fill:#FFB6C6
    style F5 fill:#FFE4B5
    style N fill:#87CEEB
