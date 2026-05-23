#!/usr/bin/env python3
"""
Generate visual diagrams for YT-AIO documentation using PIL/Pillow.
Outputs modern, color-harmonized dark mode diagrams for developer onboarding.
"""

import os
import sys
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Curated Modern Color Palette (Catppuccin Mocha inspired)
COLOR_BG = '#1e1e2e'          # Deep slate background
COLOR_SURFACE = '#252538'     # Lighter surface for panels
COLOR_BORDER = '#45475a'      # Cool grey border
COLOR_TEXT_PRIMARY = '#cdd6f4'# Crisp light text
COLOR_TEXT_MUTED = '#a6adc8'  # Secondary muted text
COLOR_ACCENT = '#f5c2e7'      # Rose pink accent

# Component colors
COLOR_UI = '#89b4fa'          # Soft blue
COLOR_LOGIC = '#cba6f7'       # Soft lavender
COLOR_DB = '#a6e3a1'          # Soft green
COLOR_EXTERNAL = '#f38ba8'    # Soft red
COLOR_CONFIG = '#fab387'      # Soft orange
COLOR_TOKEN = '#f9e2af'       # Soft yellow

def get_font(size):
    """Attempt to load a clean TTF font, falling back to default."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "DejaVuSans.ttf",
        "Arial.ttf"
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except IOError:
            continue
    return ImageFont.load_default()

def draw_rounded_rect(draw, xy, fill, outline, width=2, radius=8):
    """Draw a rounded rectangle with support for older Pillow runtimes."""
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)
    except AttributeError:
        # Fallback to standard rectangle if rounded is not supported
        draw.rectangle(xy, fill=fill, outline=outline, width=width)

def draw_centered_text(draw, xy, text, font, fill):
    """Draw text centered vertically and horizontally, supporting multiline."""
    x, y = xy
    lines = text.split('\n')
    
    # Measure line metrics safely
    line_metrics = []
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
        except AttributeError:
            # Fallback for old Pillow versions
            w, h = draw.textsize(line, font=font)
        line_metrics.append((w, h))
        
    total_height = sum(h for _, h in line_metrics) + (len(lines) - 1) * 4
    
    current_y = y - total_height / 2
    for line, (w, h) in zip(lines, line_metrics):
        draw.text((x - w / 2, current_y), line, font=font, fill=fill)
        current_y += h + 4

def draw_arrow(draw, start, end, fill=COLOR_BORDER, width=2, label="", font=None):
    """Draw a clean connector line with an arrowhead and optional label."""
    draw.line([start, end], fill=fill, width=width)
    
    # Calculate direction vector
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    length = (dx**2 + dy**2)**0.5
    
    if length > 0:
        # Normalize
        ux, uy = dx / length, dy / length
        # Arrowhead points
        arrow_len = 10
        # Perpendicular vector
        px, py = -uy, ux
        
        ap1 = (x2 - ux * arrow_len + px * (arrow_len / 1.5),
               y2 - uy * arrow_len + py * (arrow_len / 1.5))
        ap2 = (x2 - ux * arrow_len - px * (arrow_len / 1.5),
               y2 - uy * arrow_len - py * (arrow_len / 1.5))
        
        draw.polygon([end, ap1, ap2], fill=fill)
        
    # Draw label if provided
    if label and font:
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2
        # Offset label slightly to avoid overlap with line
        draw_centered_text(draw, (mid_x + 15, mid_y - 10), label, font, COLOR_TEXT_MUTED)

def create_architecture_diagram():
    """Create a structured architecture diagram."""
    width, height = 1200, 850
    img = Image.new('RGB', (width, height), color=COLOR_BG)
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(28)
    font_subtitle = get_font(18)
    font_body = get_font(14)
    font_tiny = get_font(12)
    
    # Title
    draw_centered_text(draw, (width//2, 40), "YT-AIO System Architecture", font_title, COLOR_TEXT_PRIMARY)
    draw_centered_text(draw, (width//2, 75), "Layered Components & Thread Boundary", font_subtitle, COLOR_TEXT_MUTED)
    
    # Outer Panel: Presentation Layer
    draw_rounded_rect(draw, (50, 120, 550, 500), fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=12)
    draw.text((70, 135), "PRESENTATION LAYER (UI)", font=font_subtitle, fill=COLOR_UI)
    
    # Presentation Components
    boxes_ui = [
        ((80, 180, 300, 260), "MainWindow (GUI)\n• PyQt Widget Layout\n• Signal/Slot wiring\n• QTableWidget results", COLOR_UI),
        ((330, 180, 530, 260), "TaskThread (Worker)\n• QThread subclass\n• Background processing\n• Thread-safe signals", COLOR_UI),
        ((80, 300, 300, 360), "UI Stylesheet\n• styles.qss asset\n• Premium dark styling", COLOR_UI),
        ((330, 300, 530, 360), "Terminal Emulator\n• Live stdout log capture\n• Indeterminate progress", COLOR_UI),
    ]
    
    # Outer Panel: Business Logic
    draw_rounded_rect(draw, (600, 120, 1150, 500), fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=12)
    draw.text((620, 135), "BUSINESS LOGIC LAYER (Core Services)", font=font_subtitle, fill=COLOR_LOGIC)
    
    boxes_logic = [
        ((630, 180, 870, 270), "VideoInfoExtractor\n• yt-dlp flat extraction\n• Parallel item metadata\n• Deduplication checks", COLOR_LOGIC),
        ((900, 180, 1120, 270), "DownloadManager\n• ThreadPoolExecutor\n• Media format options\n• Output path resolver", COLOR_LOGIC),
        ((630, 300, 870, 380), "ConfigManager\n• config.json handling\n• Relative path migration\n• Runtime path resolution", COLOR_CONFIG),
        ((900, 300, 1120, 380), "CancellationToken\n• Thread-safe stop state\n• Subprocess process tracker", COLOR_TOKEN),
    ]
    
    # Outer Panel: Data Layer (SQLite)
    draw_rounded_rect(draw, (50, 530, 550, 800), fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=12)
    draw.text((70, 545), "DATA PERSISTENCE LAYER", font=font_subtitle, fill=COLOR_DB)
    
    boxes_db = [
        ((80, 590, 290, 770), "DatabaseManager\n• SQLite CRUD ops\n• WAL write-ahead log\n• Error logging\n• Audit trail hooks\n• Relational tables", COLOR_DB),
        ((320, 590, 520, 770), "SQLite Storage\n• yt_aio.db database\n• sources table\n• downloads history\n• video metadata cache\n• settings_changes", COLOR_DB),
    ]
    
    # Outer Panel: External Integrations
    draw_rounded_rect(draw, (600, 530, 1150, 800), fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=12)
    draw.text((620, 545), "EXTERNAL SERVICES LAYER", font=font_subtitle, fill=COLOR_EXTERNAL)
    
    boxes_external = [
        ((630, 590, 870, 770), "yt-dlp (CLI Subprocess)\n• Command line execution\n• Stream parsing\n• Extends python import", COLOR_EXTERNAL),
        ((900, 590, 1120, 770), "Brave/Firefox/Chrome\n• Browser profile fallback\n• Decrypt session cookies\n• Passes YouTube anti-bot", COLOR_EXTERNAL),
    ]
    
    # Draw all boxes
    all_boxes = boxes_ui + boxes_logic + boxes_db + boxes_external
    for coord, text, color in all_boxes:
        draw_rounded_rect(draw, coord, fill=COLOR_BG, outline=color, width=2, radius=8)
        # Calculate center
        cx = (coord[0] + coord[2]) / 2
        cy = (coord[1] + coord[3]) / 2
        draw_centered_text(draw, (cx, cy), text, font_body, COLOR_TEXT_PRIMARY)
        
    # Draw Inter-layer Connectors
    # UI -> Services calls
    draw_arrow(draw, (250, 260), (330, 300), fill=COLOR_BORDER, width=2, label="", font=font_tiny)
    # TaskThread -> VideoInfoExtractor
    draw_arrow(draw, (530, 220), (630, 220), fill=COLOR_ACCENT, width=2, label="Extracts", font=font_tiny)
    # TaskThread -> DownloadManager
    draw_arrow(draw, (530, 250), (900, 250), fill=COLOR_ACCENT, width=2, label="Downloads", font=font_tiny)
    
    # VideoInfoExtractor -> DB Cache
    draw_arrow(draw, (750, 270), (520, 620), fill=COLOR_DB, width=2, label="Read/Write Cache", font=font_tiny)
    # DownloadManager -> DB Log
    draw_arrow(draw, (1010, 270), (450, 590), fill=COLOR_DB, width=2, label="Log Download", font=font_tiny)
    
    # Services -> Subprocess / Cookies
    draw_arrow(draw, (750, 380), (750, 590), fill=COLOR_EXTERNAL, width=2, label="Spawns CLI", font=font_tiny)
    draw_arrow(draw, (1010, 270), (1010, 590), fill=COLOR_EXTERNAL, width=2, label="Bypasses Challenge", font=font_tiny)
    
    img.save(os.path.join(OUTPUT_DIR, 'architecture.png'))
    print("✓ Created architecture.png")

def create_data_flow_diagram():
    """Create a detailed data flow diagram."""
    width, height = 1100, 750
    img = Image.new('RGB', (width, height), color=COLOR_BG)
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(28)
    font_subtitle = get_font(18)
    font_body = get_font(14)
    font_tiny = get_font(12)
    
    # Title
    draw_centered_text(draw, (width//2, 40), "YT-AIO Core Workflows Data Flow", font_title, COLOR_TEXT_PRIMARY)
    draw_centered_text(draw, (width//2, 75), "Step-by-step metadata extraction & download execution", font_subtitle, COLOR_TEXT_MUTED)
    
    # Steps Flow layout
    # Workflow A: Load Channel/Playlist
    draw_rounded_rect(draw, (40, 130, 1060, 420), fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=12)
    draw.text((60, 145), "A. METADATA LOADING WORKFLOW", font=font_subtitle, fill=COLOR_UI)
    
    a_steps = [
        ((70, 190, 230, 270), "1. Input Entered\n• Handle / URL inputted\n• Select Radio Button\n• Trigger start_load()", COLOR_UI),
        ((270, 190, 430, 270), "2. Flat Playlist\n• Call list_videos()\n• Dump-single-json\n• Extract all video IDs", COLOR_LOGIC),
        ((470, 190, 630, 270), "3. DB Cache Match\n• Scan video_id in DB\n• Fetch existing metadata\n• Bypasses network request", COLOR_DB),
        ((670, 190, 840, 270), "4. Parallel Fetch\n• ThreadPoolExecutor\n• Fetch new metadata\n• Failures isolated", COLOR_LOGIC),
        ((880, 190, 1030, 270), "5. Display Grid\n• Populate QTableWidget\n• Video title, duration\n• Checkbox selections", COLOR_UI),
    ]
    
    # Workflow B: Download Selected
    draw_rounded_rect(draw, (40, 440, 1060, 720), fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=12)
    draw.text((60, 455), "B. DOWNLOAD OPERATIONS WORKFLOW", font=font_subtitle, fill=COLOR_LOGIC)
    
    b_steps = [
        ((70, 500, 230, 580), "1. Selection Checked\n• Read checked checkboxes\n• Create DownloadTarget\n• Trigger download_many()", COLOR_UI),
        ((270, 500, 430, 580), "2. Command Built\n• Select bestaudio/bestvideo\n• Set output directories\n• Prepare subprocess env", COLOR_LOGIC),
        ((470, 500, 630, 580), "3. Download Exec\n• ThreadPool downloads\n• Streaming status lines\n• Live GUI log updates", COLOR_EXTERNAL),
        ((670, 500, 840, 580), "4. Auth Fallback\n• If blocked (HTTP 429)\n• Extract browser cookies\n• Auto-retry download", COLOR_TOKEN),
        ((880, 500, 1030, 580), "5. Results Persisted\n• Log downloads into DB\n• Error log + stack traces\n• Files saved to disk", COLOR_DB),
    ]
    
    # Draw boxes
    for coord, text, color in a_steps + b_steps:
        draw_rounded_rect(draw, coord, fill=COLOR_BG, outline=color, width=2, radius=8)
        cx = (coord[0] + coord[2]) / 2
        cy = (coord[1] + coord[3]) / 2
        draw_centered_text(draw, (cx, cy), text, font_body, COLOR_TEXT_PRIMARY)
        
    # Draw Arrows for Flow A
    draw_arrow(draw, (230, 230), (270, 230), fill=COLOR_BORDER, width=2)
    draw_arrow(draw, (430, 230), (470, 230), fill=COLOR_BORDER, width=2)
    draw_arrow(draw, (630, 230), (670, 230), fill=COLOR_BORDER, width=2)
    draw_arrow(draw, (840, 230), (880, 230), fill=COLOR_BORDER, width=2)
    
    # Write metadata into DB database step
    draw_arrow(draw, (755, 270), (550, 310), fill=COLOR_DB, width=2, label="Write cache", font=font_tiny)
    draw_rounded_rect(draw, (470, 310, 630, 370), fill=COLOR_BG, outline=COLOR_DB, width=2, radius=8)
    draw_centered_text(draw, (550, 340), "DB Cache Table\n(youtube_video_info)", font_body, COLOR_TEXT_PRIMARY)
    draw_arrow(draw, (550, 310), (550, 270), fill=COLOR_DB, width=2, label="Read Cache", font=font_tiny)
    
    # Draw Arrows for Flow B
    draw_arrow(draw, (230, 540), (270, 540), fill=COLOR_BORDER, width=2)
    draw_arrow(draw, (430, 540), (470, 540), fill=COLOR_BORDER, width=2)
    draw_arrow(draw, (630, 540), (670, 540), fill=COLOR_BORDER, width=2)
    draw_arrow(draw, (840, 540), (880, 540), fill=COLOR_BORDER, width=2)
    
    img.save(os.path.join(OUTPUT_DIR, 'data_flow.png'))
    print("✓ Created data_flow.png")

def create_threading_diagram():
    """Create a threading model diagram."""
    width, height = 1200, 750
    img = Image.new('RGB', (width, height), color=COLOR_BG)
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(28)
    font_subtitle = get_font(18)
    font_body = get_font(14)
    font_tiny = get_font(12)
    
    # Title
    draw_centered_text(draw, (width//2, 40), "YT-AIO Threading & Concurrency Model", font_title, COLOR_TEXT_PRIMARY)
    draw_centered_text(draw, (width//2, 75), "Safe inter-thread communication and parallel task runners", font_subtitle, COLOR_TEXT_MUTED)
    
    # Column 1: Main UI Thread
    draw_rounded_rect(draw, (50, 130, 380, 700), fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=12)
    draw.text((70, 150), "MAIN UI THREAD", font=font_subtitle, fill=COLOR_UI)
    draw.text((70, 175), "Qt Event Loop (Non-blocking)", font=font_tiny, fill=COLOR_TEXT_MUTED)
    
    ui_elements = [
        ((70, 220, 360, 280), "GUI Event Listener\n• Mouse clicks, URL entry\n• Keyboard table selections", COLOR_UI),
        ((70, 310, 360, 370), "Signal Dispatcher / Slots\n• Receives worker completions\n• Error alert dialog prompts", COLOR_UI),
        ((70, 400, 360, 460), "UI Widget Renderer\n• Updates status labels\n• Animates active progress bars", COLOR_UI),
        ((70, 490, 360, 670), "Main Window State:\n• config: dict (read-only)\n• db_path: Path\n• cancel_token: CancellationToken\n• worker: TaskThread instance\n• current_items: VideoItem[]", COLOR_UI),
    ]
    
    # Column 2: Task Worker Thread
    draw_rounded_rect(draw, (430, 130, 760, 700), fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=12)
    draw.text((450, 150), "WORKER THREAD (TaskThread)", font=font_subtitle, fill=COLOR_LOGIC)
    draw.text((450, 175), "Spawns 1 thread per action via QThread", font=font_tiny, fill=COLOR_TEXT_MUTED)
    
    worker_elements = [
        ((450, 220, 740, 280), "Thread run() Start\n• Isolates blocking processes\n• Releases Qt GUI UI thread", COLOR_LOGIC),
        ((450, 310, 740, 420), "Operations Dispatcher:\n• action='load': call list_videos()\n• action='download': download_many()\n• Captures stdout / updates", COLOR_LOGIC),
        ((450, 450, 740, 510), "Signal Emitter\n• Emits: progress_updated(int)\n• Emits: log_message(str)", COLOR_LOGIC),
        ((450, 540, 740, 670), "Cancellation Hook:\n• Monitors CancellationToken\n• Clean-kills external Popen\n• Emits final work_failed()", COLOR_TOKEN),
    ]
    
    # Column 3: Parallel Execution ThreadPool
    draw_rounded_rect(draw, (810, 130, 1150, 700), fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=12)
    draw.text((830, 150), "SERVICES THREAD POOL", font=font_subtitle, fill=COLOR_EXTERNAL)
    draw.text((830, 175), "ThreadPoolExecutor (Python)", font=font_tiny, fill=COLOR_TEXT_MUTED)
    
    pool_elements = [
        ((830, 220, 1130, 340), "Metadata Workers (max=4)\n• Parallel fetch_video_metadata()\n• Fetches multiple URLs/IDs\n• Fast cache backfill writes", COLOR_EXTERNAL),
        ((830, 380, 1130, 520), "Download Workers (max=CPU-2)\n• Parallel download_one()\n• Captures subprocess pipes\n• Saves stream files locally", COLOR_EXTERNAL),
        ((830, 560, 1130, 670), "Mutex Lock System:\n• Protects downloads logs\n• Thread-safe sqlite WAL writes", COLOR_DB),
    ]
    
    # Draw all elements
    for coord, text, color in ui_elements + worker_elements + pool_elements:
        draw_rounded_rect(draw, coord, fill=COLOR_BG, outline=color, width=2, radius=8)
        cx = (coord[0] + coord[2]) / 2
        cy = (coord[1] + coord[3]) / 2
        draw_centered_text(draw, (cx, cy), text, font_body, COLOR_TEXT_PRIMARY)
        
    # Draw connector lines
    # UI -> TaskThread start
    draw_arrow(draw, (380, 250), (430, 250), fill=COLOR_ACCENT, width=2, label="Spawn", font=font_tiny)
    # TaskThread -> ThreadPool actions
    draw_arrow(draw, (760, 365), (810, 280), fill=COLOR_ACCENT, width=2, label="Delegate", font=font_tiny)
    draw_arrow(draw, (760, 365), (810, 450), fill=COLOR_ACCENT, width=2, label="Delegate", font=font_tiny)
    
    # Worker signals -> UI Slot dispatcher
    draw_arrow(draw, (450, 480), (360, 340), fill=COLOR_UI, width=2, label="Qt Signals (Thread-Safe)", font=font_tiny)
    # Cancellation Token UI -> Worker
    draw_arrow(draw, (360, 600), (450, 605), fill=COLOR_TOKEN, width=2, label="cancel()", font=font_tiny)
    
    img.save(os.path.join(OUTPUT_DIR, 'threading_model.png'))
    print("✓ Created threading_model.png")

def create_database_schema_visual():
    """Create a database schema visualization."""
    width, height = 1200, 800
    img = Image.new('RGB', (width, height), color=COLOR_BG)
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(28)
    font_subtitle = get_font(18)
    font_body = get_font(14)
    font_tiny = get_font(12)
    
    # Title
    draw_centered_text(draw, (width//2, 40), "YT-AIO SQLite Database Schema", font_title, COLOR_TEXT_PRIMARY)
    draw_centered_text(draw, (width//2, 75), "Relational design tracking sources, cached metadata, and download history", font_subtitle, COLOR_TEXT_MUTED)
    
    # Draw Database Tables
    # Table 1: sources
    t_sources = (50, 140, 330, 340)
    # Table 2: youtube_video_information
    t_videos = (430, 140, 770, 440)
    # Table 3: downloads
    t_downloads = (870, 140, 1150, 490)
    
    # Standalone Tables
    t_errors = (50, 520, 300, 750)
    t_actions = (340, 520, 590, 700)
    t_settings = (630, 520, 880, 700)
    t_version = (920, 520, 1150, 700)
    
    tables_list = [
        (t_sources, "sources", ["id (PK, int)", "source_key (unique, txt)", "source_kind (txt)", "source_name (txt)", "source_value (txt)", "source_url (txt)", "created_at (txt)", "updated_at (txt)"]),
        (t_videos, "youtube_video_information", ["id (PK, int)", "video_id (unique, txt)", "title (txt)", "channel_name (txt)", "playlist_name (txt)", "upload_date (txt)", "duration (int)", "view_count (int)", "like_count (int)", "video_url (txt)", "source_id (FK, int)", "cached_at (txt)"]),
        (t_downloads, "downloads", ["id (PK, int)", "title (txt)", "url (txt)", "status (txt)", "error_message (txt)", "timestamp (txt)", "file_path (txt)", "quality (txt)", "type (txt)", "source_name (txt)", "video_id (txt)", "video_info_id (FK, int)", "source_id (FK, int)"]),
        (t_errors, "errors", ["id (PK, int)", "error_message (txt)", "timestamp (txt)", "stack_trace (txt)", "url (txt)", "action (txt)", "user_input (txt)", "script_version (txt)"]),
        (t_actions, "user_actions", ["id (PK, int)", "action (txt)", "timestamp (txt)"]),
        (t_settings, "settings_changes", ["id (PK, int)", "setting_name (txt)", "old_value (txt)", "new_value (txt)", "timestamp (txt)"]),
        (t_version, "yt_aio_version", ["id (PK, int)", "version_number (txt)", "release_date (txt)", "changelog (txt)"]),
    ]
    
    # Draw tables
    for coords, name, cols in tables_list:
        x1, y1, x2, y2 = coords
        # Header
        draw_rounded_rect(draw, [x1, y1, x2, y2], fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=8)
        draw_rounded_rect(draw, [x1, y1, x2, y1+35], fill=COLOR_DB, outline=COLOR_BORDER, radius=8)
        draw_centered_text(draw, ((x1+x2)/2, y1+17), name, font_body, COLOR_BG)
        
        # Column list
        col_y = y1 + 45
        for col in cols:
            draw.text((x1 + 15, col_y), "• " + col, font=font_tiny, fill=COLOR_TEXT_PRIMARY)
            col_y += 22
            
    # Draw Foreign Keys Connections (Relational lines)
    # sources.id -> youtube_video_information.source_id
    draw_arrow(draw, (330, 240), (430, 240), fill=COLOR_ACCENT, width=2, label="1 : N (source_id)", font=font_tiny)
    
    # youtube_video_information.id -> downloads.video_info_id
    # We will draw a line with segments around
    draw_arrow(draw, (770, 290), (870, 290), fill=COLOR_ACCENT, width=2, label="1 : N (video_info_id)", font=font_tiny)
    
    # sources.id -> downloads.source_id
    # From sources bottom down and right to downloads FK
    draw_arrow(draw, (200, 340), (870, 460), fill=COLOR_ACCENT, width=2, label="1 : N (source_id)", font=font_tiny)
    
    # Extra annotations
    draw_rounded_rect(draw, (50, 760, 1150, 790), fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=4)
    draw.text((65, 768), "Database Characteristics: • WAL (Write-Ahead Logging) Mode enabled  • PRAGMA foreign_keys = ON  • Auto-indices on PKs and UNIQUE constraints", font=font_tiny, fill=COLOR_TEXT_MUTED)
    
    img.save(os.path.join(OUTPUT_DIR, 'database_schema.png'))
    print("✓ Created database_schema.png")

if __name__ == '__main__':
    print("Generating color-harmonized visual diagrams for YT-AIO...")
    print("Output directory: " + OUTPUT_DIR)
    print()
    
    create_architecture_diagram()
    create_data_flow_diagram()
    create_threading_diagram()
    create_database_schema_visual()
    
    print()
    print("✓ All diagrams generated successfully!")
