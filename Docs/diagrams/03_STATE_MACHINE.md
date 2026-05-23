# UI State Machine

## Application states and transitions

```mermaid
stateDiagram-v2
    [*] --> Idle
    
    Idle --> Loading: User clicks "Load"
    Idle --> Downloading: User clicks "Download" (items selected)
    Idle --> Configuring: User clicks "Config"
    
    Loading --> Idle: load_complete
    Loading --> Idle: Task cancelled
    Loading --> Idle: Error occurred
    
    Downloading --> Idle: download_complete
    Downloading --> Idle: Task cancelled
    Downloading --> Idle: Error occurred
    
    Configuring --> Idle: Config file closed
    
    Loading --> Loading: Progress update (emit log_message)
    Downloading --> Downloading: Progress update (emit log_message)
    
    note right of Idle
        Inputs enabled
        Table visible
        Log shows results
    end note
    
    note right of Loading
        Inputs disabled
        Progress bar visible
        Real-time logging
        Stop button enabled
    end note
    
    note right of Downloading
        Inputs disabled
        Progress bar visible
        Real-time logging
        Stop button enabled
    end note
