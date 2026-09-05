#!/usr/bin/env python3
"""
Generate visual diagrams for YT-AIO documentation using PIL/Pillow.
Outputs modern, color-harmonized dark mode diagrams for developer onboarding.
Refined to prevent overlapping text and crossing arrows.
"""

import os
import sys
import shutil
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

def backup_old_diagrams():
    """Rename existing diagrams to _old.png if they exist, preserving history."""
    names = ['architecture.png', 'data_flow.png', 'threading_model.png', 'database_schema.png']
    for name in names:
        path = os.path.join(OUTPUT_DIR, name)
        if os.path.exists(path):
            old_path = os.path.join(OUTPUT_DIR, name.replace('.png', '_old.png'))
            try:
                if os.path.exists(old_path):
                    os.remove(old_path)
                shutil.copy2(path, old_path)
                print(f"Backed up {name} to {name.replace('.png', '_old.png')}")
            except Exception as e:
                print(f"Failed to backup {name}: {e}")

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

def draw_centered_text_with_bg(draw, xy, text, font, fill, bg_color, padding=4):
    """Draw text centered vertically and horizontally with a background masking box."""
    x, y = xy
    lines = text.split('\n')
    
    line_metrics = []
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
        except AttributeError:
            w, h = draw.textsize(line, font=font)
        line_metrics.append((w, h))
        
    total_height = sum(h for _, h in line_metrics) + (len(lines) - 1) * 4
    max_width = max(w for w, _ in line_metrics)
    
    # Draw background box to mask lines/objects behind it
    rx1 = x - max_width / 2 - padding
    ry1 = y - total_height / 2 - padding
    rx2 = x + max_width / 2 + padding
    ry2 = y + total_height / 2 + padding
    draw.rectangle([rx1, ry1, rx2, ry2], fill=bg_color)
    
    current_y = y - total_height / 2
    for line, (w, h) in zip(lines, line_metrics):
        draw.text((x - w / 2, current_y), line, font=font, fill=fill)
        current_y += h + 4

def draw_routed_arrow(draw, points, fill=COLOR_BORDER, width=2, label="", font=None, label_bg=COLOR_BG, label_pos=None):
    """Draw a multi-segment line with an arrowhead at the end and a centered label."""
    if len(points) < 2:
        return
        
    # Draw line segments
    for i in range(len(points) - 1):
        draw.line([points[i], points[i+1]], fill=fill, width=width)
        
    # Draw arrowhead at the last segment
    start = points[-2]
    end = points[-1]
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    length = (dx**2 + dy**2)**0.5
    
    if length > 0:
        ux, uy = dx / length, dy / length
        arrow_len = 10
        px, py = -uy, ux
        ap1 = (x2 - ux * arrow_len + px * (arrow_len / 1.5),
               y2 - uy * arrow_len + py * (arrow_len / 1.5))
        ap2 = (x2 - ux * arrow_len - px * (arrow_len / 1.5),
               y2 - uy * arrow_len - py * (arrow_len / 1.5))
        draw.polygon([end, ap1, ap2], fill=fill)
        
    # Draw label if provided
    if label and font:
        if label_pos is not None:
            mid_x, mid_y = label_pos
        else:
            # Find the middle segment of the path
            mid_seg_idx = len(points) // 2 - 1
            s = points[mid_seg_idx]
            e = points[mid_seg_idx + 1]
            mid_x = (s[0] + e[0]) / 2
            mid_y = (s[1] + e[1]) / 2
        # Use our centered text with background function to mask out lines
        draw_centered_text_with_bg(draw, (mid_x, mid_y), label, font, COLOR_TEXT_MUTED, bg_color=label_bg)

def create_architecture_diagram():
    """Create a structured architecture diagram without overlapping paths."""
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
        ((80, 180, 300, 270), "MainWindow (GUI)\n• PyQt Widget Layout\n• Signal/Slot wiring\n• QTableWidget results", COLOR_UI),
        ((330, 180, 530, 270), "TaskThread (Worker)\n• QThread subclass\n• Background processing\n• Thread-safe signals", COLOR_UI),
        ((80, 310, 300, 390), "UI Stylesheet\n• styles.qss asset\n• Premium dark styling", COLOR_UI),
        ((330, 310, 530, 390), "Terminal Emulator\n• Live stdout log capture\n• Indeterminate progress", COLOR_UI),
    ]
    
    # Outer Panel: Business Logic
    draw_rounded_rect(draw, (600, 120, 1150, 500), fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=12)
    draw.text((620, 135), "BUSINESS LOGIC LAYER (Core Services)", font=font_subtitle, fill=COLOR_LOGIC)
    
    boxes_logic = [
        ((630, 180, 870, 270), "VideoInfoExtractor\n• yt-dlp flat extraction\n• Parallel item metadata\n• Deduplication checks", COLOR_LOGIC),
        ((900, 180, 1120, 270), "DownloadManager\n• ThreadPoolExecutor\n• Media format options\n• Output path resolver", COLOR_LOGIC),
        ((630, 310, 870, 400), "ConfigManager\n• config.json handling\n• Relative path migration\n• Runtime path resolution", COLOR_CONFIG),
        ((900, 310, 1120, 400), "CancellationToken\n• Thread-safe stop state\n• Subprocess process tracker", COLOR_TOKEN),
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
        
    # Draw Inter-layer Connectors (Routed carefully to avoid intersecting boxes)
    
    # MainWindow -> Terminal Emulator (Routed inside Presentation layer)
    draw_routed_arrow(draw, [(190, 270), (190, 290), (430, 290), (430, 310)], fill=COLOR_BORDER, width=2, label_bg=COLOR_SURFACE)
    
    # TaskThread -> VideoInfoExtractor (Direct line, clean)
    draw_routed_arrow(draw, [(530, 225), (630, 225)], fill=COLOR_ACCENT, width=2, label="Extracts", font=font_tiny, label_bg=COLOR_BG, label_pos=(580, 225))
    
    # TaskThread -> DownloadManager (Routed under VideoInfoExtractor at y=280 to avoid intersection)
    draw_routed_arrow(draw, [(530, 245), (560, 245), (560, 280), (890, 280), (890, 225), (900, 225)], 
                      fill=COLOR_ACCENT, width=2, label="Downloads", font=font_tiny, label_bg=COLOR_BG, label_pos=(725, 280))
    
    # VideoInfoExtractor -> SQLite Storage DB Cache (Routed left at y=300 and down through gaps. Label placed in horizontal segment inside panel corridor)
    draw_routed_arrow(draw, [(750, 270), (750, 300), (575, 300), (575, 620), (520, 620)], 
                      fill=COLOR_DB, width=2, label="Read/Write Cache", font=font_tiny, label_bg=COLOR_SURFACE, label_pos=(662.5, 300))
    
    # DownloadManager -> SQLite Storage DB Log (Routed left at y=300 and down through central gaps. Label placed at y=515 corridor on the left)
    draw_routed_arrow(draw, [(1010, 270), (1010, 300), (880, 300), (880, 515), (450, 515), (450, 590)], 
                      fill=COLOR_DB, width=2, label="Log Download", font=font_tiny, label_bg=COLOR_BG, label_pos=(500, 515))
    
    # VideoInfoExtractor -> yt-dlp (Spawns CLI, routed vertically at x=590. Split label vertically to prevent corridor overflow)
    draw_routed_arrow(draw, [(630, 245), (590, 245), (590, 515), (750, 515), (750, 590)], 
                      fill=COLOR_EXTERNAL, width=2, label="Spawns\nCLI", font=font_tiny, label_bg=COLOR_BG, label_pos=(590, 420))
                      
    # DownloadManager -> Browser cookies (Bypasses Challenge, routed vertically at x=1135 and horizontally below CancellationToken. Label centered in horizontal segment)
    draw_routed_arrow(draw, [(1120, 225), (1135, 225), (1135, 525), (1010, 525), (1010, 590)], 
                      fill=COLOR_EXTERNAL, width=2, label="Bypasses Challenge", font=font_tiny, label_bg=COLOR_BG, label_pos=(1072.5, 525))
    
    img.save(os.path.join(OUTPUT_DIR, 'architecture.png'))
    print("✓ Created architecture.png")

def create_data_flow_diagram():
    """Create a detailed data flow diagram with wider blocks and size-adjusted fonts to avoid overflows."""
    width, height = 1200, 750
    img = Image.new('RGB', (width, height), color=COLOR_BG)
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(28)
    font_subtitle = get_font(18)
    font_body = get_font(12)  # Reduced slightly to ensure bullet text fits comfortably inside boxes
    font_tiny = get_font(10)
    
    # Title
    draw_centered_text(draw, (width//2, 40), "YT-AIO Core Workflows Data Flow", font_title, COLOR_TEXT_PRIMARY)
    draw_centered_text(draw, (width//2, 75), "Step-by-step metadata extraction & download execution", font_subtitle, COLOR_TEXT_MUTED)
    
    # Steps Flow layout - Workflow A: Load Channel/Playlist
    draw_rounded_rect(draw, (30, 130, 1170, 420), fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=12)
    draw.text((50, 145), "A. METADATA LOADING WORKFLOW", font=font_subtitle, fill=COLOR_UI)
    
    a_steps = [
        ((50, 190, 240, 310), "1. Input Entered\n• Handle / URL inputted\n• Select Radio Button\n• Trigger start_load()", COLOR_UI),
        ((280, 190, 470, 310), "2. Flat Playlist\n• Call list_videos()\n• Dump-single-json\n• Extract all video IDs", COLOR_LOGIC),
        ((510, 190, 700, 310), "3. DB Cache Match\n• Scan video_id in DB\n• Fetch existing metadata\n• Bypasses network request", COLOR_DB),
        ((740, 190, 930, 310), "4. Parallel Fetch\n• ThreadPoolExecutor\n• Fetch new metadata\n• Failures isolated", COLOR_LOGIC),
        ((970, 190, 1160, 310), "5. Display Grid\n• Populate QTableWidget\n• Video title, duration\n• Checkbox selections", COLOR_UI),
    ]
    
    # Workflow B: Download Selected
    draw_rounded_rect(draw, (30, 450, 1170, 720), fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=12)
    draw.text((50, 455), "B. DOWNLOAD OPERATIONS WORKFLOW", font=font_subtitle, fill=COLOR_LOGIC)
    
    b_steps = [
        ((50, 500, 240, 620), "1. Selection Checked\n• Read checked checkboxes\n• Create DownloadTarget\n• Trigger download_many()", COLOR_UI),
        ((280, 500, 470, 620), "2. Command Built\n• Select bestaudio/bestvideo\n• Set output directories\n• Prepare subprocess env", COLOR_LOGIC),
        ((510, 500, 700, 620), "3. Download Exec\n• ThreadPool downloads\n• Streaming status lines\n• Live GUI log updates", COLOR_EXTERNAL),
        ((740, 500, 930, 620), "4. Auth Fallback\n• If blocked (HTTP 429)\n• Extract browser cookies\n• Auto-retry download", COLOR_TOKEN),
        ((970, 500, 1160, 620), "5. Results Persisted\n• Log downloads into DB\n• Error log + stack traces\n• Files saved to disk", COLOR_DB),
    ]
    
    # Draw boxes
    for coord, text, color in a_steps + b_steps:
        draw_rounded_rect(draw, coord, fill=COLOR_BG, outline=color, width=2, radius=8)
        cx = (coord[0] + coord[2]) / 2
        cy = (coord[1] + coord[3]) / 2
        draw_centered_text(draw, (cx, cy), text, font_body, COLOR_TEXT_PRIMARY)
        
    # Draw Arrows for Flow A
    draw_routed_arrow(draw, [(240, 250), (280, 250)], fill=COLOR_BORDER, width=2)
    draw_routed_arrow(draw, [(470, 250), (510, 250)], fill=COLOR_BORDER, width=2)
    draw_routed_arrow(draw, [(700, 250), (740, 250)], fill=COLOR_BORDER, width=2)
    draw_routed_arrow(draw, [(930, 250), (970, 250)], fill=COLOR_BORDER, width=2)
    
    # Draw Cache table and arrows (clean layout)
    draw_rounded_rect(draw, (510, 340, 700, 400), fill=COLOR_BG, outline=COLOR_DB, width=2, radius=8)
    draw_centered_text(draw, (605, 370), "DB Cache Table\n(youtube_video_info)", font_body, COLOR_TEXT_PRIMARY)
    
    # Read Cache arrow: DB Cache Table -> Step 3
    draw_routed_arrow(draw, [(560, 340), (560, 310)], fill=COLOR_DB, width=2, label="Read Cache", font=font_tiny, label_bg=COLOR_SURFACE, label_pos=(560, 325))
    
    # Write Cache arrow: Step 4 -> DB Cache Table (routed around Step 3)
    draw_routed_arrow(draw, [(835, 310), (835, 370), (700, 370)], fill=COLOR_DB, width=2, label="Write Cache", font=font_tiny, label_bg=COLOR_SURFACE, label_pos=(767.5, 370))
    
    # Draw Arrows for Flow B
    draw_routed_arrow(draw, [(240, 560), (280, 560)], fill=COLOR_BORDER, width=2)
    draw_routed_arrow(draw, [(470, 560), (510, 560)], fill=COLOR_BORDER, width=2)
    draw_routed_arrow(draw, [(700, 560), (740, 560)], fill=COLOR_BORDER, width=2)
    draw_routed_arrow(draw, [(930, 560), (970, 560)], fill=COLOR_BORDER, width=2)
    
    img.save(os.path.join(OUTPUT_DIR, 'data_flow.png'))
    print("✓ Created data_flow.png")

def create_threading_diagram():
    """Create a threading model diagram with custom routed signals and expanded columns."""
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
    
    # Column 1: Main UI Thread (Narrower boxes to make a wider gap)
    draw_rounded_rect(draw, (50, 130, 360, 700), fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=12)
    draw.text((70, 150), "MAIN UI THREAD", font=font_subtitle, fill=COLOR_UI)
    draw.text((70, 175), "Qt Event Loop (Non-blocking)", font=font_tiny, fill=COLOR_TEXT_MUTED)
    
    ui_elements = [
        ((70, 220, 340, 280), "GUI Event Listener\n• Mouse clicks, URL entry\n• Keyboard table selections", COLOR_UI),
        ((70, 310, 340, 370), "Signal Dispatcher / Slots\n• Receives worker completions\n• Error alert dialog prompts", COLOR_UI),
        ((70, 400, 340, 460), "UI Widget Renderer\n• Updates status labels\n• Animates active progress bars", COLOR_UI),
        ((70, 490, 340, 680), "Main Window State:\n• config: dict (read-only)\n• db_path: Path\n• cancel_token: CancellationToken\n• worker: TaskThread instance\n• current_items: VideoItem[]", COLOR_UI),
    ]
    
    # Column 2: Task Worker Thread
    draw_rounded_rect(draw, (460, 130, 770, 700), fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=12)
    draw.text((480, 150), "WORKER THREAD (TaskThread)", font=font_subtitle, fill=COLOR_LOGIC)
    draw.text((480, 175), "Spawns 1 thread per action via QThread", font=font_tiny, fill=COLOR_TEXT_MUTED)
    
    worker_elements = [
        ((480, 220, 750, 280), "Thread run() Start\n• Isolates blocking processes\n• Releases Qt GUI UI thread", COLOR_LOGIC),
        ((480, 310, 750, 420), "Operations Dispatcher:\n• action='load': call list_videos()\n• action='download': download_many()\n• Captures stdout / updates", COLOR_LOGIC),
        ((480, 450, 750, 510), "Signal Emitter\n• Emits: progress_updated(int)\n• Emits: log_message(str)", COLOR_LOGIC),
        ((480, 540, 750, 680), "Cancellation Hook:\n• Monitors CancellationToken\n• Clean-kills external Popen\n• Emits final work_failed()", COLOR_TOKEN),
    ]
    
    # Column 3: Parallel Execution ThreadPool
    draw_rounded_rect(draw, (830, 130, 1150, 700), fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=12)
    draw.text((850, 150), "SERVICES THREAD POOL", font=font_subtitle, fill=COLOR_EXTERNAL)
    draw.text((850, 175), "ThreadPoolExecutor (Python)", font=font_tiny, fill=COLOR_TEXT_MUTED)
    
    pool_elements = [
        ((850, 220, 1130, 340), "Metadata Workers (max=4)\n• Parallel fetch_metadata_batch()\n• One yt-dlp per batch of URLs\n• Fast cache backfill writes", COLOR_EXTERNAL),
        ((850, 380, 1130, 520), "Download Workers (max=CPU-2)\n• Parallel download_one()\n• Captures subprocess pipes\n• Saves stream files locally", COLOR_EXTERNAL),
        ((850, 560, 1130, 680), "Mutex Lock System:\n• Protects downloads logs\n• Thread-safe sqlite WAL writes", COLOR_DB),
    ]
    
    # Draw all elements
    for coord, text, color in ui_elements + worker_elements + pool_elements:
        draw_rounded_rect(draw, coord, fill=COLOR_BG, outline=color, width=2, radius=8)
        cx = (coord[0] + coord[2]) / 2
        cy = (coord[1] + coord[3]) / 2
        draw_centered_text(draw, (cx, cy), text, font_body, COLOR_TEXT_PRIMARY)
        
    # Draw connector lines (Routed cleanly through the expanded vertical gaps)
    
    # UI Event Listener -> TaskThread run() start: "Spawn"
    draw_routed_arrow(draw, [(340, 250), (480, 250)], fill=COLOR_ACCENT, width=2, label="Spawn", font=font_tiny, label_bg=COLOR_BG)
    
    # Operations Dispatcher -> Metadata Workers: "Delegate" (Routed in corridor x=800)
    draw_routed_arrow(draw, [(750, 365), (800, 365), (800, 280), (850, 280)], fill=COLOR_ACCENT, width=2, label="Delegate", font=font_tiny, label_bg=COLOR_BG)
    
    # Operations Dispatcher -> Download Workers: "Delegate" (Routed in corridor x=800)
    draw_routed_arrow(draw, [(750, 365), (800, 365), (800, 450), (850, 450)], fill=COLOR_ACCENT, width=2, label="Delegate", font=font_tiny, label_bg=COLOR_BG)
    
    # Signal Emitter -> UI Signal Dispatcher: "Qt Signals (Thread-Safe)"
    # Routed vertically in corridor x=410 (exactly in the middle of gap 360-460)
    draw_routed_arrow(draw, [(480, 480), (410, 480), (410, 340), (340, 340)], fill=COLOR_UI, width=2, label="Qt Signals\n(Thread-Safe)", font=font_tiny, label_bg=COLOR_BG, label_pos=(410, 410))
    
    # CancellationToken UI State -> Worker Cancellation Hook: "cancel()"
    draw_routed_arrow(draw, [(340, 610), (480, 610)], fill=COLOR_TOKEN, width=2, label="cancel()", font=font_tiny, label_bg=COLOR_BG)
    
    img.save(os.path.join(OUTPUT_DIR, 'threading_model.png'))
    print("✓ Created threading_model.png")

def create_database_schema_visual():
    """Create a database schema visualization with wide margins to avoid boundary overlaps."""
    width, height = 1200, 820
    img = Image.new('RGB', (width, height), color=COLOR_BG)
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(28)
    font_subtitle = get_font(18)
    font_body = get_font(14)
    font_tiny = get_font(12)
    
    # Title
    draw_centered_text(draw, (width//2, 40), "YT-AIO SQLite Database Schema", font_title, COLOR_TEXT_PRIMARY)
    draw_centered_text(draw, (width//2, 75), "Relational design tracking sources, cached metadata, and download history", font_subtitle, COLOR_TEXT_MUTED)
    
    # Table definitions (adjusted widths for wider columns/gaps)
    tables_list = [
        # (x1, y1, width), name, cols
        ((50, 140, 220), "sources", ["id (PK, int)", "source_key (unique, txt)", "source_kind (txt)", "source_name (txt)", "source_value (txt)", "source_url (txt)", "created_at (txt)", "updated_at (txt)"]),
        ((390, 140, 340), "youtube_video_information", ["id (PK, int)", "video_id (unique, txt)", "title (txt)", "channel_name (txt)", "playlist_name (txt)", "upload_date (txt)", "duration (int)", "view_count (int)", "like_count (int)", "video_url (txt)", "source_id (FK, int)", "cached_at (txt)"]),
        ((850, 140, 300), "downloads", ["id (PK, int)", "title (txt)", "url (txt)", "status (txt)", "error_message (txt)", "timestamp (txt)", "file_path (txt)", "quality (txt)", "type (txt)", "source_name (txt)", "video_id (txt)", "video_info_id (FK, int)", "source_id (FK, int)"]),
        ((50, 540, 250), "errors", ["id (PK, int)", "error_message (txt)", "timestamp (txt)", "stack_trace (txt)", "url (txt)", "action (txt)", "user_input (txt)", "script_version (txt)"]),
        ((330, 540, 250), "user_actions", ["id (PK, int)", "action (txt)", "timestamp (txt)"]),
        ((610, 540, 250), "settings_changes", ["id (PK, int)", "setting_name (txt)", "old_value (txt)", "new_value (txt)", "timestamp (txt)"]),
        ((890, 540, 260), "yt_aio_version", ["id (PK, int)", "version_number (txt)", "release_date (txt)", "changelog (txt)"]),
    ]
    
    # Draw tables with dynamic height calculation to avoid text overflow
    for pos, name, cols in tables_list:
        x1, y1, width_box = pos
        x2 = x1 + width_box
        y2 = y1 + 35 + len(cols) * 22 + 10
        
        # Draw background and border
        draw_rounded_rect(draw, [x1, y1, x2, y2], fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=8)
        # Header bar
        draw_rounded_rect(draw, [x1, y1, x2, y1+35], fill=COLOR_DB, outline=COLOR_BORDER, radius=8)
        draw_centered_text(draw, ((x1+x2)/2, y1+17), name, font_body, COLOR_BG)
        
        # Column items
        col_y = y1 + 45
        for col in cols:
            draw.text((x1 + 15, col_y), "• " + col, font=font_tiny, fill=COLOR_TEXT_PRIMARY)
            col_y += 22
            
    # Draw Foreign Keys Connections (Relational lines routed clean around components)
    
    # 1. sources.id -> youtube_video_information.source_id (Direct path: 270 -> 390. Gap is 120px)
    draw_routed_arrow(draw, [(270, 255), (390, 255)], fill=COLOR_ACCENT, width=2, label="source_id", font=font_tiny, label_bg=COLOR_BG)
    
    # 2. youtube_video_information.id -> downloads.video_info_id (Direct path: 730 -> 850. Gap is 120px)
    draw_routed_arrow(draw, [(730, 300), (850, 300)], fill=COLOR_ACCENT, width=2, label="video_info_id", font=font_tiny, label_bg=COLOR_BG)
    
    # 3. sources.id -> downloads.source_id (Routed completely below youtube_video_information to avoid crossings)
    # Starts at center-bottom of sources (x=160), down to y=515 corridor, then right to gap 2 (x=800), up to y=460, right to downloads (x=850)
    draw_routed_arrow(draw, [(160, 361), (160, 515), (800, 515), (800, 460), (850, 460)], 
                      fill=COLOR_ACCENT, width=2, label="source_id", font=font_tiny, label_bg=COLOR_BG)
    
    # Footnote Characteristics Panel
    draw_rounded_rect(draw, (50, 770, 1150, 800), fill=COLOR_SURFACE, outline=COLOR_BORDER, radius=4)
    draw.text((65, 778), "Database Characteristics: • WAL (Write-Ahead Logging) Mode enabled  • PRAGMA foreign_keys = ON  • Auto-indices on PKs and UNIQUE constraints", font=font_tiny, fill=COLOR_TEXT_MUTED)
    
    img.save(os.path.join(OUTPUT_DIR, 'database_schema.png'))
    print("✓ Created database_schema.png")

if __name__ == '__main__':
    print("Generating color-harmonized visual diagrams for YT-AIO...")
    print("Output directory: " + OUTPUT_DIR)
    print()
    
    # Renaming current images to _old.png
    backup_old_diagrams()
    print()
    
    create_architecture_diagram()
    create_data_flow_diagram()
    create_threading_diagram()
    create_database_schema_visual()
    
    print()
    print("✓ All diagrams generated successfully!")
