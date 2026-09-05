# YT AIO

A desktop front end for `yt-dlp`. Load a channel or playlist, pick what you want, download
it, and keep a searchable library of what you have.

Runs on Windows, macOS and Linux. Current version `0.6.0`.

The window is a tab shell with six tabs: Import, Downloader, Library, Local Scan, Logs and
Settings. Each is a self-contained package under `yt_aio/application/features/`.

---

## Install and run

You need **Python 3.10 or newer** and **ffmpeg**. Everything else comes from pip.

### Windows

```powershell
git clone https://github.com/ItzzInfinity/yt_aio.git
cd yt_aio
python -m pip install -r requirements.txt
winget install Gyan.FFmpeg
python -m yt_aio
```

If `winget` is not available, download a build from
[gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) and do any one of these:

- add its `bin` folder to `PATH`, or
- put `ffmpeg.exe` and `ffprobe.exe` in a `bin` folder inside `yt_aio`, or
- set `ffmpeg_location` in the Settings tab to the folder holding them.

`python3` is not usually a command on Windows. Use `python`, or `py -3` if you have
several versions installed.

### macOS

```bash
git clone https://github.com/ItzzInfinity/yt_aio.git
cd yt_aio
python3 -m pip install -r requirements.txt
brew install ffmpeg
python3 -m yt_aio
```

### Linux

```bash
git clone https://github.com/ItzzInfinity/yt_aio.git
cd yt_aio
python3 -m pip install -r requirements.txt
sudo apt install ffmpeg          # or your distribution's equivalent
python3 -m yt_aio
```

### Installing it as a command

```bash
python -m pip install .
yt-aio
```

### If something is missing

Start-up checks before it opens a window and tells you what to install rather than
showing a traceback:

```
YT AIO cannot start yet.

  - No Qt binding is installed. PyQt6 is the one to get:
    python -m pip install PyQt6
  - yt-dlp is not installed, which stops fetching and downloading.
    python -m pip install yt-dlp

Installing everything at once:
    python -m pip install -r requirements.txt
```

`ffmpeg` and `mutagen` produce a warning rather than a refusal: the application starts
without them, but downloads that need merging or converting will fail.

---

## What it does

- Loads a channel or playlist through `yt-dlp`, streaming entries as they arrive rather
  than waiting for the whole list
- Fetches metadata in batches, one process per batch instead of one per video, and caches
  the result so a second pass runs no `yt-dlp` at all
- Downloads audio or video, with format sorting, a download archive and tag rewriting that
  strips YouTube's ` - Topic` suffix off the artist
- Keeps a music library of songs, artists, albums and playlists, so a song credited to
  three artists is found by any of them
- Imports a backup from a phone music app. OpenTune, InnerTune, ViTune and ViMusic are
  read by their own schema; anything else is scanned for links
- Scans a folder of audio already on disk and grades each file against the library
- Falls back to browser cookies when YouTube raises a bot check, including for Brave
  installed as a snap or a flatpak, which `yt-dlp` cannot find on its own
- Writes every download, error, setting change and button press to SQLite

---

## First run

Nothing is configured in advance. On first start the application writes
`yt_aio/application/config/config.json` with sensible defaults, creates
`yt_aio/application/db/yt_aio.db`, and picks your own `Downloads` folder as the download
path. None of those files are in the repository, so a clone starts clean.

Everything is editable from the Settings tab, which builds its form from the defaults, so
a new setting appears there on its own with a drop-down of the values known to work.

Paths in the config may be relative. They resolve from `yt_aio/application`, so the whole
directory can be moved without rewriting anything.

---

## The tabs

- **Import** reads a backup file exported by a phone app. The format is detected from the
  file's own bytes, so SQLite databases, ZIP archives, JSON, CSV and plain lists of links
  all work. OpenTune and ViTune backups are read by their real schema, which is what keeps
  their recommendation and playback tables out of your library. Parsed items can be merged
  into the database or downloaded directly.
- **Downloader** loads a channel or playlist, then downloads the rows you tick. The first
  `Download` click loads the listing; the second starts the download. A valid URL in the
  quick-download box takes priority over the channel field.
- **Library** browses everything cached, with search and filters for channel, artist,
  album, playlist, duration, source and status. Every column sorts, all of it in SQL.
  Deleting metadata never touches the download history or the files on disk.
- **Local Scan** reads a folder of audio and grades each file against the database:
  already have it, probable match, title clash, or new. Tags come from mutagen, then
  ffprobe, then the file name, and the row says which answered.
- **Logs** is a read-only view of the download history, the errors with their stack
  traces, your button presses, the settings changes and the version history.
- **Settings** edits the config from a generated form. Saving records every change in the
  database, with credential-shaped values redacted, and applies the theme immediately.

---

## Project layout

| Path | What lives there |
|---|---|
| `yt_aio/__main__.py` | `python -m yt_aio`: preflight, then the shell |
| `yt_aio/preflight.py` | the dependency check, which imports nothing from `application` |
| `yt_aio/application/shell.py` | `AppShell`, the only window, and the tab bar |
| `yt_aio/application/context.py` | `AppContext`, the shared config and database handle |
| `yt_aio/application/jobs.py` | the shared `QThread` runners every tab uses |
| `yt_aio/application/features/` | one package per tab |
| `yt_aio/application/db/database_manager.py` | schema and the write path |
| `yt_aio/application/db/queries.py` | the read and delete path the viewing tabs share |
| `yt_aio/application/ui/qt.py` | the single PyQt6-with-PyQt5-fallback import site |
| `yt_aio/application/ui/theme.py` | the dark and light palettes |
| `yt_aio/application/utils/video_info_extractor.py` | listing and metadata |
| `yt_aio/application/utils/download_manager.py` | download orchestration and retries |
| `yt_aio/application/utils/browser_cookies.py` | where each platform keeps browser profiles |
| `yt_aio/application/utils/external_tools.py` | finding ffmpeg and ffprobe |

Generated at runtime and never committed: `config/config.json`, `db/*.db`,
`db/downloaded.txt`, `db/info_cache/` and `logs/`.

---

## Adding a tab

1. Create `yt_aio/application/features/<feature>/` with an empty `__init__.py` and a
   `panel.py`.
2. Write a `QWidget` subclass whose constructor takes no required positional argument,
   does no blocking work, and accepts the shared `AppContext` as a keyword argument.
3. Register it in `AppShell.__init__` with one `addTab` call, in workflow order.

The full contract, including the optional `shutdown()` hook the shell calls on close, is
in [Docs/05_TAB_SHELL_MIGRATION.md](Docs/05_TAB_SHELL_MIGRATION.md).

---

## Documentation

| Document | What it covers |
|---|---|
| [Docs/01_ARCHITECTURE_AND_THREADING.md](Docs/01_ARCHITECTURE_AND_THREADING.md) | how the threading works |
| [Docs/05_TAB_SHELL_MIGRATION.md](Docs/05_TAB_SHELL_MIGRATION.md) | the tab and panel contract |
| [Docs/06_YTDLNIS_APPROACH.md](Docs/06_YTDLNIS_APPROACH.md) | the yt-dlp command choices and why |
| [Docs/07_MUSIC_SCHEMA_PLAN.md](Docs/07_MUSIC_SCHEMA_PLAN.md) | the songs, artists, albums and playlists schema |
| [Docs/song_db_erd.html](Docs/song_db_erd.html) | the OpenTune backup schema |
| [Docs/vitune_db_erd.html](Docs/vitune_db_erd.html) | the ViTune backup schema |
| [Docs/opentune_vs_vitune.html](Docs/opentune_vs_vitune.html) | the two compared |

`FSD.md` is the specification and the running record of what was built and why.
