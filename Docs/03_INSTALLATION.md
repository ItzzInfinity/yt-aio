# 🔧 Installation & Setup

This guide covers setting up the development environment for YT-AIO.

---

## Prerequisites

### System Requirements
- **OS:** Linux, macOS, or Windows
- **Python:** 3.8 or later
- **Disk Space:** ~100MB (for dependencies and database)
- **Internet:** Required for YouTube downloads

### Check Your Python Version

```bash
python3 --version
# Should output: Python 3.8.x or higher
```

---

## Step 1: Clone the Repository

```bash
# Navigate to where you want to store the project
cd /home/itzzinfinity/GitHub

# Clone (if not already cloned)
git clone <repository-url>
cd yt_aio
```

---

## Step 2: Create a Virtual Environment (Recommended)

Virtual environments isolate project dependencies from your system Python.

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate      # Linux/macOS
# OR
venv\Scripts\activate          # Windows

# Verify activation (should show "venv" prefix)
which python3
```

---

## Step 3: Install Dependencies

```bash
# Upgrade pip, setuptools, wheel
pip install --upgrade pip setuptools wheel

# Install project dependencies
pip install PyQt5 yt-dlp

# Verify installations
python3 -c "import PyQt5; print('PyQt5 OK')"
python3 -c "import yt_dlp; print('yt-dlp OK')"
```

### Dependency Details

| Package | Purpose | Version |
|---------|---------|---------|
| **PyQt5** | GUI framework | 5.15+ or PyQt6 |
| **yt-dlp** | YouTube downloader | Latest |
| **sqlite3** | Database (built-in) | Built-in |

### Alternative: PyQt6 Instead of PyQt5

If you prefer PyQt6:

```bash
pip install PyQt6 yt-dlp

# The app auto-detects and uses whichever is installed
```

---

## Step 4: Optional Dependencies

### For Cookie-Based Authentication (Brave Browser)

If you encounter YouTube bot challenges, the app can use Brave browser cookies:

```bash
# Install Brave (if not already installed)

# Linux:
sudo apt install brave-browser

# macOS:
brew install brave-browser

# Windows:
# Download from https://brave.com/download/
```

**Why:** YouTube sometimes blocks automated access. Having Brave installed allows the app to extract cookies and retry authentication.

### For Other Browsers

The app can also use Firefox or Chrome:
- **Firefox:** Should work out-of-the-box if installed
- **Chrome/Chromium:** Should work if installed

---

## Step 5: Verify Installation

```bash
# Navigate to project directory
cd /home/itzzinfinity/GitHub/yt_aio

# Run the app
python3 -m yt_aio

# If successful:
# ✅ A PyQt window opens
# ✅ Log shows "YT-AIO initialized"
# ✅ Config file created (if first run)
```

### What Happens on First Run

1. App checks for `application/config/config.json`
2. If missing: Creates default config
3. App checks for `application/db/yt_aio.db`
4. If missing: Creates SQLite database with schema
5. UI window opens, ready to use

---

## Step 6: Test Basic Functionality

```bash
# Inside the app:
1. Enter a YouTube URL (e.g., https://www.youtube.com/watch?v=dQw4w9WgXcQ)
2. Select "Audio" option
3. Click "Download"
4. Check your Downloads folder for the file
```

---

## Troubleshooting Installation

### "ModuleNotFoundError: No module named 'PyQt5'"

```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Reinstall
pip install PyQt5
```

### "ModuleNotFoundError: No module named 'yt_dlp'"

```bash
# Install yt-dlp
pip install yt-dlp

# Or verify it's installed
pip list | grep yt-dlp
```

### "No module named 'yt_aio'"

```bash
# Make sure you're in the correct directory
pwd
# Should output: /home/itzzinfinity/GitHub/yt_aio

# Run from there
python3 -m yt_aio
```

### PyQt5 Installation Fails

Some systems require additional Qt5 libraries:

```bash
# Linux (Ubuntu/Debian)
sudo apt install qt5-qmake libqt5core5a

# Linux (Fedora)
sudo dnf install qt5-qtbase-devel

# macOS
brew install qt5
```

### yt-dlp Gives "Command not found"

```bash
# Ensure it's installed
pip install --upgrade yt-dlp

# Check installation
which yt-dlp
python3 -m yt_dlp --version
```

### "Could not open Brave snap profile"

This is a warning, not a fatal error. The app will:
1. Attempt to use Brave if installed
2. Fall back to other authentication methods
3. Continue anyway if unavailable

---

## Development Setup (Optional)

If you plan to contribute to the codebase:

```bash
# Install development tools
pip install pylint black flake8 pytest

# Format code (optional but recommended)
black yt_aio/

# Run tests
pytest tests/  # (if test directory exists)
```

---

## Project Structure After Install

```
yt_aio/
├── venv/                          # Virtual environment (created by you)
├── yt_aio/
│   ├── application/
│   │   ├── config/
│   │   │   └── config.json       # Created on first run
│   │   ├── db/
│   │   │   └── yt_aio.db         # Created on first run
│   │   ├── logs/
│   │   ├── ui/
│   │   └── utils/
│   ├── __init__.py
│   ├── __main__.py
│   └── run.py
├── Docs/                         # You are here
├── README.md
└── PROGRESS_LOG.md
```

---

## Verify Everything Works

```bash
# 1. Activate venv
source venv/bin/activate

# 2. Navigate to project
cd /home/itzzinfinity/GitHub/yt_aio

# 3. Run the app
python3 -m yt_aio

# 4. Try a quick download
#    - Enter: https://www.youtube.com/watch?v=dQw4w9WgXcQ
#    - Click: Download
#    - Select: Audio
#    - Click: Download again
```

---

## Next Steps

Once installed and verified:
1. Read [04_RUNNING_THE_APP.md](04_RUNNING_THE_APP.md) for usage tips
2. Read [05_MODULE_GUIDE.md](05_MODULE_GUIDE.md) for code structure
3. Explore the config file: `yt_aio/application/config/config.json`

---

## Getting Help

If you encounter issues:

1. Check the error message carefully
2. Check `application/db/yt_aio.db` → `errors` table for detailed logs
3. Look for recent entries in application logs
4. Check [11_ERROR_HANDLING.md](11_ERROR_HANDLING.md) for common errors

---

*Next: [04_RUNNING_THE_APP.md](04_RUNNING_THE_APP.md) — How to Use the App*

