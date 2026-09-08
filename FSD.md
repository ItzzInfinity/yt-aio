<!-- Functional Specification Document -->
# 1. Project name: YT AIO

## Current state — 2026-09-08 (session 6) — downloaded means the file is on this disk

- **Current phase:** 1.13 complete. `downloaded` means the file is in the local music library and nothing else.
- **Last completed task:** O5, the end-to-end verification on a copy of the live database.
- **Next task:** Nothing pending in the roadmap. Start the application once so `init_db` repairs the live database, then rescan `~/Downloads/my_music/downloaded` and press `Add to database` to flag what is really there.

### Session summary
1. O1 — the Import payload dropped the `downloaded` key, and `upsert_songs` moved the flag out of the `MAX` conflict clause into the same override UPDATE `liked` uses. It now only changes when a payload names it.
2. O2 — the two history-driven writers are gone: the revival seeds every song at 0, and the `songs downloaded <- download history` backfill pass was removed and replaced with a comment saying why it should not come back.
3. O3 — `clear_stale_downloaded_flags` lowers the flag for any song the local index no longer holds, from `init_db` and from the end of `record_scan`. It only ever lowers; raising stays with the operator pressing `Add to database`.
4. O4 — the Library `Downloaded` filter reads `songs.downloaded` instead of the download history, and `Never downloaded` was relabelled `Not downloaded`.
5. O5 — verified on a copy of the live database, on the real OpenTune backup, and on a three-file round trip through scan, add, delete and rescan.

**Gotchas learned this session:**
- `python -m compileall -q yt_aio`, the project's own self-check, was failing before any of this on `db/tempCodeRunnerFile.py`, a committed VS Code Code Runner artifact holding one indented line of a shell command. It is not a module and nothing imports it. Removed.
- The four writers of `downloaded` were spread across four files and only one of them mentioned the local library, which is how the flag drifted to 8895 on a machine holding 3612 identified files. Grep for the column name, not for the word download.
- `local_files` prunes rows for files that disappeared only when `forget_missing` is set, which is the default, so it is a trustworthy present-on-disk index. That is what makes the lowering pass one cheap UPDATE rather than a filesystem walk.

### Partially done
- none

### Blocked
- none

### Next step (exact)
Run the application. `init_db` will take `songs.downloaded` from 8895 to about 3568 on the live database. Then open Local Scan, rescan `/home/itzzinfinity/Downloads/my_music/downloaded`, and press `Add to database` with no filters set; the log should report roughly 3612 files with a video id and the newly flagged count. Check the Library `Show` drop-down: `Downloaded` and `Not downloaded` should now split on that flag.

### Assumptions
- A download this application performs does not flag itself. FSD 1.8.4 names `local scan -> add to database` as the gate, and the download folder is not necessarily the music library. If you want a finished download to flag itself, say so and it becomes a scan of the output path at the end of a job.

## Previous state — 2026-09-05 (session 5) — liked songs from OpenTune and ViTune

- **Current phase:** 1.12 complete. Liked is carried, filterable and overridden by a re-import.
- **Last completed task:** N4, the Library Liked column and filter.
- **Next task:** Nothing pending. Re-import your OpenTune and ViTune backups from the Import tab to populate the flag; the live database has the column but no likes yet, because nothing has been imported since it came back.

### Session summary
1. **N1.** `songs.liked` restored, with `_ensure_column` for a database written while it was gone. `play_count` stays dropped.
2. **N2.** `liked` overrides instead of merging, and only when the payload names it. It sits outside the conflict clause and is settled by a follow-up UPDATE, which is what lets a 1 become a 0.
3. **N3.** The importer always sends the flag, and reports likes added and removed separately.
4. **N4.** A Liked column, `Liked` and `Not liked` in the Show drop-down, and a sort key, all in SQL.

**Gotchas learned this session:**
- **`MAX` in an upsert makes a flag one-way, which is right for one field and wrong for another.** `downloaded` should never go back to 0 because a file on disk does not stop existing when a backup is silent about it. `liked` must be able to, because a backup is the only authority on it. Same statement, opposite rules, and the reason belongs in a comment beside each.
- **SQLite cannot make one `ON CONFLICT` clause conditional per row.** Wanting "override when the source names it, leave alone when silent" from a single statement needs a NULL sentinel, which a `NOT NULL` column forbids. Leaving the column out of the conflict clause and settling it with a follow-up UPDATE is two statements and no cleverness.
- **Override across two backups is not what it sounds like.** Importing OpenTune after ViTune removed 334 likes, because every song the two share takes the later file's answer. That is exactly what was asked for, but a single "N flags changed" number hides it, so added and removed are counted apart.
- **A restored column starts empty.** The live database has `liked` back and zero likes in it, because the flag only arrives with an import. Adding a column is not the same as having the data.

### Partially done
- none

### Blocked
- none

### Next step (exact)
Open the Import tab, load `ViTune_backup_20250831122626.db`, tick everything and press the merge button. Read the log line: it should report the number liked in the backup, how many were newly liked and how many were unliked. Then open the Library tab and set Show to `Liked`. Repeat with an OpenTune backup and expect the count to move, because the second import overrides shared songs.

### Assumptions
- Liked is read-only in this application. Nothing here lets you like a song; the flag only ever arrives from a backup, which is why a re-import is treated as the authority.
- `play_count` stays out. Only `liked` was asked for.

## Previous state — 2026-09-05 (session 4) — the 1.8.3 batch: final schema, Local Scan writes, Library delete

- **Current phase:** 1.11 roadmap complete. All four requests in FSD 1.8.3 are closed.
- **Last completed task:** L1, the Library delete button.
- **Next task:** Nothing pending. Worth doing by hand: press ADD TO DATABASE on a folder of your own music and check the counts in the log against what you expected.

### Session summary
1. **J — the final schema.** `songs.liked` and `songs.play_count` are gone, from the schema, from every write path, and from any database that already had them. The parsers still read a backup's plays and likes, because that is what decides the Import grid's Collection label.
2. **K — Local Scan writes to the library.** A new `local_only_tracks` table for audio with no video id, `add_local_files_to_library` in the database layer, and an `ADD TO DATABASE` button that runs it on the background thread.
3. **L — Library.** `Delete selected` now enables when rows are ticked individually, which it never did before.

**Gotchas learned this session:**
- **`CREATE TABLE IF NOT EXISTS` never removes a column.** Editing the DDL changes what a new database gets and nothing else. A column only disappears if something explicitly drops it, so a schema change needs a migration beside the edit or the two diverge silently and only on other people's machines.
- **A grid that fills itself fires `itemChanged` for every cell.** Connecting to it without blocking the signal during `_render` means every reload looks like two hundred selections. Block while filling, unblock after.
- **`@pyqtSlot(object)` is not a wildcard.** It declares the slot as taking `PyQt_PyObject`, so connecting it to `itemChanged(QTableWidgetItem*)` fails outright at construction with `Incompatible sender/receiver arguments`. A plain undecorated method connects fine.
- **Enablement computed once at construction is computed before the data exists.** The ADD TO DATABASE button depends on whether any row matched, which is unknown until the first query returns, so `_render` has to recompute it. The same shape of bug as the Library delete button, in a different tab.
- **"Update the existing files if the metadata changed" needed a decision, not just code.** A local file's ID3 tag is often worse than a yt-dlp record, so the file fills gaps in a song rather than overwriting it, and `local_files` keeps the file's own values for comparison. Stated in the code and in the annotation, because the other reading was defensible.

### Partially done
- none

### Blocked
- none

### Next step (exact)
Open the Local Scan tab, scan a folder of music that was not downloaded by this application, and press ADD TO DATABASE. Check the log line: files with a video id should be counted under Songs and files without under "No video id". Then open the Library tab, tick two rows individually, and confirm `Delete selected` becomes available without touching `Select all on this page`.

### Assumptions
- The ADD TO DATABASE button acts on everything the filters match rather than on a selection, because the Local Scan grid has no tick boxes and is filter-driven throughout.
- `local_only_tracks` has no tab of its own yet. `fetch_local_only_tracks` exists for one, but nothing in the FSD asked to display those rows, only to stop them polluting the song queries.

## Previous state — 2026-09-05 (session 3) — Windows compatibility and clone-and-run

- **Current phase:** 1.10 roadmap complete. Runs on Windows, macOS and Linux from a fresh clone.
- **Last completed task:** I2, the README rewrite, plus undoing the font regression found while verifying H5.
- **Next task:** Nothing pending. Commit, push, then clone it on an actual Windows machine and run it, which is the one thing that cannot be checked from here.

### Session summary
1. **G — clone-and-run.** 45 files left the git index: 42 `__pycache__` entries, a 9.7 MB personal library database, a `config.json` holding one machine's absolute download path, and the download archive. Added `pyproject.toml`, `requirements.txt` and a real `.gitignore`. A clean tree of 69 files now runs `python -m yt_aio` and builds its own config and database.
2. **H — Windows correctness.** Every subprocess decodes UTF-8 instead of the system code page, which was a guaranteed crash on the first non-ASCII title. The finished-file path no longer has to start with `/`. Console windows are suppressed. Browser profiles are found where Windows and macOS keep them, including Chromium's newer `Network/Cookies` location. `os.uname()` is gone. ffmpeg and ffprobe are located rather than assumed.
3. **I — telling the user.** A preflight that names what is missing and how to install it, and a README with per-platform instructions.

**Gotchas learned this session:**
- **`text=True` is not enough.** It decodes with the locale encoding, which is UTF-8 here and the ANSI code page on Windows. yt-dlp writes UTF-8, so on Windows the first Bengali, Hindi or accented title raises UnicodeDecodeError mid-listing. Always state `encoding="utf-8"`, and `errors="replace"` so one odd byte costs a character rather than the run.
- **Naming a font family is riskier than naming none.** Qt takes the first family that exists and its fallback for missing glyphs is poorer than its first-choice matching. Naming `Noto Sans` broke Bengali conjuncts because that face is installed here without Bengali shaping tables. With no family set, Qt picks the platform UI font and shapes every script correctly. The Qt warning about missing OpenType support was printed but easy to miss; the screenshot was what caught it.
- **A start-up check cannot import the package it is checking.** The preflight exists to say "PyQt is not installed", so it must reach PyQt on no import path of its own. `application/utils/__init__.py` re-exported eagerly and pulled in PyQt through the panels, so it had to become lazy first. That also removed the db-to-utils cycle noted in session 1.
- **`git ls-files` lists tracked files only.** Testing a clone by building a tree from the index silently omits everything not yet staged, which made a passing test fail for the wrong reason. Stage new files before testing what a clone contains.
- **setuptools 59 reads no PEP 621 metadata and says nothing.** A `--no-build-isolation` build produced `UNKNOWN-0.0.0` with no error. Build with isolation, which is what `pip install` does anyway.

### Partially done
- none

### Blocked
- **Actually running on Windows.** Everything platform-specific was verified by faking the platform: `sys.platform`, `%LOCALAPPDATA%`, and fabricated Brave, Chrome and winget directory trees. That covers the logic but not the environment.

### Next step (exact)
Commit and push. Then on a Windows machine: `git clone`, `python -m pip install -r requirements.txt`, `winget install Gyan.FFmpeg`, `python -m yt_aio`. Confirm the window opens, fetch a playlist that has a non-ASCII title in it, and download one track. Those three prove the UTF-8 decoding, the ffmpeg discovery and the output-path detection together.

### Assumptions
- PyQt6 is the declared dependency and PyQt5 stays a fallback rather than a supported install path, because a dependency list cannot express "either of these".
- The personal database and config are untracked, not deleted. Both are still on disk and the application keeps using them.

## Previous state — 2026-09-05 (session 2) — fixed the two regressions reported in 1.6

- **Current phase:** 1.6 items 10 and 11 closed. Roadmap clear.
- **Last completed task:** F2, separating the Settings help text from the config keys.
- **Next task:** Nothing pending. Still worth doing on live data: update yt-dlp, sign in to Brave once, then fetch a real playlist and download one file.

### Session summary
1. **F1.** `build_youtube_extractor_args` was missing from `utils/video_info_extractor.py` entirely, so every download raised `NameError`. The E1 edit last session rewrote `_cookie_home_override` by replacing the text from its own `def` up to the next one, and this function was in that gap. Restored above its only caller and the call uncommented. Checked against the last commit that it was the only casualty.
2. **F2.** The Settings tab packed the key name and its help into one word-wrapped label. That read as a run-on string and collapsed the form: 49 rows needing 1800 pixels were pinned to a 690-pixel viewport, no scroll bar was offered, and every row was squeezed to 8 pixels. The key is now its own label, the help is a caption under its editor, and the form gets a real minimum height.

**Gotchas learned this session:**
- **An index-to-index text replacement is only as safe as what sits between the two anchors.** Replacing from `def a(` to `def b(` silently deletes anything written between them. When a function's only reference is inside another function, Python raises nothing until that line runs, so neither `compileall` nor importing the module catches it. Comparing the module's top-level function names against the previous commit does, and takes seconds.
- **A word-wrapped QLabel inside a resizable QScrollArea collapses the layout.** Its height depends on its width, so the scroll area sizes the child to the viewport instead of to the content, and every row is squeezed with no scroll bar to show for it. Keep labels single-line, or set an explicit minimum height on the scrolled widget.
- **Measure the layout after `activate()`, never during the build.** `QFormLayout.sizeHint()` mid-build returned 18 pixels, the margins alone. Setting that as the minimum height was worse than setting none, because it pinned the form smaller than Qt would have on its own.

### Partially done
- none

### Blocked
- **Live download verification**, unchanged from session 1. Update yt-dlp first; it is 2026.03.17 and reports itself as stale.

### Next step (exact)
Start the application, open Settings, and confirm the scroll bar reaches `ui_theme` at the bottom with every key on its own line above its help. Then run one download from the Downloader tab and confirm it no longer raises `NameError: name 'build_youtube_extractor_args' is not defined`.

### Assumptions
- The help text stays visible on screen rather than moving into tooltips only. It is also on the key's tooltip, so both work.

## Previous state — 2026-09-05 (session 1) — applied the 1.8.2 batch end to end

- **Current phase:** 1.9 roadmap complete. Every request from FSD 1.8.2 line 243 onwards is closed.
- **Last completed task:** E2, balancing the Library filter row.
- **Next task:** Nothing pending. Update yt-dlp, sign in to Brave once, then run a real download and a real channel listing to confirm on live data what could only be verified structurally here.

### Session summary
1. **A — theme.** `ui/styles.qss` became `styles.template.qss` with 26 `@token@` markers; `ui/theme.py` holds the dark and light palettes and renders it. `ui_theme` is a normal setting, so the Settings tab grew the drop-down on its own, and the shell repaints on `config_changed`.
2. **B — the YTDLnis change list**, all nine sections. Listing hardened with `--lazy-playlist` and a socket timeout, metadata fetch batched into `-a urls.txt` runs, tags rewritten with `--embed-metadata` and two `--parse-metadata` rules, audio selection moved to `-f ba/b` plus `-S`, download tuning, a download archive, an info cache and PO-token support. Fourteen new settings.
3. **C — the music schema.** `Docs/07_MUSIC_SCHEMA_PLAN.md`, then seven tables, a guarded backfill of the 3461 existing rows, `upsert_songs` on both write paths, and Library columns, filters and sorts.
4. **D — ViTune.** `Docs/generate_vitune_erd.py` producing `Docs/vitune_db_erd.html`, the `vitune.py` reader registered ahead of the blind scan, and `Docs/opentune_vs_vitune.html`.
5. **E — Brave.** `utils/browser_cookies.py` finds snap, flatpak and package installs by looking for a cookie file, and feeds both the Settings suggestions and the extractor's HOME override.

**Gotchas learned this session:**
- **The document's advice is not always right on this machine, and only measuring shows it.** Three of the YTDLnis recommendations were wrong here: sequential batching is slower than the pool it replaces (12.7s vs 7.0s), `+size` in the audio sort picks 49 kbps over 130, and `--no-warnings` on the listing hides two of the bot-challenge markers the cookie retry depends on. All three came from a phone app where the trade-offs differ.
- **A directory existing proves nothing about a browser profile.** `~/.config/BraveSoftware/Brave-Browser` is present on this machine and holds no profile; the cookies are in the snap revision `~/snap/brave/678`, and `~/snap/brave/current` does not exist either. Test for the `Cookies` file itself.
- **Backups carry characters that look like a space and are not.** Nine ViTune credits hold `\u00a0`, which made `Arijit Singh` typed normally match 2 songs instead of 212. Every name is normalised before it is stored now.
- **A sentinel is not a value.** OpenTune writes `-1` for an unknown duration and 8050 of its 9583 songs carry it, which the grid rendered as `-1:59:59` and the duration filter treated as a real length.
- **SQLite here is 3.37**, so `GROUP_CONCAT(x, y ORDER BY z)` does not exist. The Library assembles a page's artist credits in Python, which also makes the lead-artist-first order a guarantee rather than an implementation detail.
- **db cannot import utils at module level.** `utils/__init__.py` eagerly imports `download_manager`, which imports `db`, so a top-level `db -> utils` import is a cycle. `database_manager` keeps its own `now_string` and `clean_name` for that reason.

### Partially done
- none

### Blocked
- **Live download verification.** Every download on this machine returns `HTTP Error 403: Forbidden`, including the unmodified old command, because the installed yt-dlp is 2026.03.17 and reports itself as more than 90 days stale. Command construction and format selection were verified with `--print` instead. Brave's cookies are also stale and yt-dlp reports them as rotated.

### Next step (exact)
Run `python3 -m pip install -U yt-dlp`, sign in to YouTube in Brave once, then start the application and fetch a real playlist in the Downloader tab with `fetch_full_metadata` on. Confirm three things: entries appear within a second or two rather than after the whole list is collected, the metadata phase logs one batch per `metadata_batch_size` videos rather than one line per video, and a downloaded file carries an artist tag with no ` - Topic` suffix.

### Assumptions
- The music tables are written alongside `youtube_video_information` rather than replacing it, so every existing view keeps working. Retiring the flat table is a later decision, not this batch's.
- No item from a ViTune backup is marked Downloaded, because that schema has no column for it. Inferring it from a cached `Format` row would be a guess, and a wrong "already have it" stops a download that was wanted.

## 1.0. Create a New project Directory
- Make a Distributed Folder structure for the project
- Make a README.md file for the project
- Make a progression Log in markdown for this project adjacent to the README.md file Where every update will be logged with time stamp and well commented manner.

## 1.1. Make UI using PyQt5 and PyQt6
- Make a simple UI with PyQt5 and PyQt6 to test the functionality of the script and to make it more user friendly. The UI should have the following features:
- An open textbox to mimic the terminal output for the script to show the progress of the script and any errors that may occur.
- A Textbox to input channel name or playlist ID 
- Just beside it there will be a Radio button to select whether the input is a channel or a playlist
- Beside these buttons there will be two buttons to select Audio or Video 
- A button to start the script (Download) and a button to stop the script (Ctrl + C)
- A button to clear the textbox (Clear)
- A button to open config.json where Default Filepath and other settings are stored (Config)
- 
```
===================================================================================
|-------LOG-------| Text Box for CH or PL | O Channel O Playlist <- Radio Buttons |
|                 |                       | O Audio O Video <- Radio Buttons      |
|                 |                                                               |
|    mimic        |                                                               |
|                 |    Selectale Text Box                                         |
|    Terminal     |___________________________________________                    |
|                 | ID | Name | Duration | Bitrate (Available)|                   |
|    Output       |                                           |                   |
|                 |                                           |                   |
|    Here         |    <After loading CH or PL contents       |                   |
|                 |          will be displayed>               |                   |
|                 |                                           |                   |
|                 |     <I will be clicking on this and       |                   |
|                 |     IDs will get selected for further     |                   |
|                 |             processing>                   |                   |
|                 |___________________________________________|                   |
|                 |                                                               |
|                 |___________________________________________                    |
|                 |Text Box for Quick Download with full link |                   |
|                 | It Will be comma separated                |                   |
|                 |https://www.youtube.com/watch?v=<ID1>,     |                   |
|                 |https://www.youtube.com/watch?v=<ID2>,     |                   |
|                 |___________________________________________|                   |
|                 |_____________________________________________________________  |
|                 | Download Button | Stop Button | Clear Button | Config Button  |
===================================================================================


```
- Qt Stylesheets will be used to make the UI look more appealing and user friendly. I want the UI to be Fluid and Minimalistic with a dark theme. The buttons should have hover effects and the selected radio button should be highlighted. The text box should have a scrollbar for better readability when there is a lot of output. The selectable text box should have alternating row colors for better readability and the selected row should be highlighted. The overall layout should be clean and organized to make it easy for the user to navigate and use the application.

## 1.2. Make script functions into discrete Defs to be used independently 

- For Video it will automatically select the best quality video and for Audio it will automatically m4a as my script already does 
- The script should be able to take the input from the UI and process it accordingly. For example, if the user selects a channel and clicks on the download button, the script should fetch all the videos from that channel and display them in the selectable text box. The user can then select the videos they want to download and click on the download button again to start the download process. The same goes for playlists. If the user selects a playlist and clicks on the download button, the script should fetch all the videos from that playlist and display them in the selectable text box for further processing.
- The script should also be able to take the input from the quick download textbox and start downloading the videos from the links provided in the textbox when the download button is clicked. The links should be comma separated and the script should be able to handle multiple links at once.
-  The script should also validate the links provided in the textbox and show an error message in the main textbox if any of the links are invalid or if there is any issue with the download process for any of the links.
- The script should continue with the next link in the list if there is an error with any of the links and should not stop the whole download process. 
- The script should also show the progress of the download for each link in the main textbox and should show a message when the download is complete for each link. 
- The script should also log the download process for each link in the logging system that will be implemented later in the project.

## 1.3. Make it failsafe for each and every step 

- If the script fails at any point it should not crash the whole program and should show the error in the textbox and should continue with the next item in the list.
- If the script is already running and the user tries to start it again it should show a message in the textbox that the script is already running and should not start a new instance of the script.
- If the user tries to stop the script when it is not running it should show a message in the textbox that the script is not running and should not do anything.
- If the user tries to clear the textbox when the script is running it should show a message in the textbox that the script is running and should not clear the textbox.
- If the user tries to open the config file when the script is running it should show a message in the textbox that the script is running and should not open the config file.
- If the user tries to start the script without selecting a channel or playlist it should show a message in the textbox that the user should select a channel or playlist and should not start the script. or put a Quick Download link in the textbox and start downloading that.
- If the user tries to start the script without selecting Audio or Video it should show a message / by default it will select Audio and start downloading that.
- If the user tries to start the script without selecting a channel or playlist / by default its set to channel
- fill a keyword to QUICK DOWNLOAD text <NULL> which will indicate that there is no quick download link and the script should proceed with the channel or playlist download. If there is a quick download link in the textbox it should ignore the channel or playlist selection and start downloading the quick download links.
- If the user tries to start the script without selecting a channel or playlist and there is no quick download link in the textbox it should show a message in the textbox that the user should select a channel or playlist or put a quick download link in the textbox and should not start the script.

## 1.4. Make a config.json file to store default settings like default download path, default quality for video and audio, etc.
- The config file should be created in the same directory as the script and should be named config.json.
- Need to add a function to check if the config file exists, if not create a new config file with default settings.
- Need to make the config as detailed as possible to include all the settings that the user may want to change in the future. This will make it easier for the user to customize the script according to their needs without having to change the code.
- The config file should be editable through the UI by clicking on the Config button which will open the config file in the gedit or any other text editor for the user to edit the settings. The changes made in the config file should be reflected in the script when it is run again.
- The script should read the settings from the config file and use them as default settings for the download process. If the user does not select any quality for video or audio it should use the default settings from the config file.
- The config file should have the following settings:
```
{
    "default_download_path": "/home/user/Downloads",
    "default_video_quality": "best",
    "default_audio_quality": "m4a",
    "max_retries": 3,
    "retry_delay": 5,
    "log_file_path": "/home/user/Downloads/yt_aio.db",
    "log_level": "INFO",
        "proxy": null,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "download_subtitles": false,
        "subtitle_language": "en",
        "download_thumbnail": false,
        "thumbnail_quality": "best",
        "download_description": false,
        "description_format": "txt",
        "download_comments": false,
        "comments_format": "txt",
        "max_concurrent_downloads": n-2 (where n is the number of CPU cores),
        "download_history": true,
        "history_file_path": "/home/user/Downloads/yt_aio.db",
        "history_file_table_name": "download_history",
}
```

## 1.5. Make a logging system 
-   Make a sqlite3 .db file with following tables
    -   downloads
        -   id (primary key)
        -   title
        -   url
        -   status (success, failed, in progress)
        -   error_message (if any)
        -   timestamp
        -   file_path (where the file is saved)
        -   quality (audio or video quality)
        -   type (audio or video)
        -   Channel or Playlist name (if any)
    - YouTube Video Information
        -   id (primary key)
        -   video_id
        -   title
        -   channel_name
        -   Playlist name (if any)
        -   upload_date
        -   duration
        -   view_count
        -   like_count
        -   dislike_count
        -   comment_count
        -   thumbnail_url
        -   video_url
    -   settings_changes
        -   id (primary key)
        -   setting_name
        -   old_value
        -   new_value
        -   timestamp
    -  errors
        -   id (primary key)
        -   error_message
        -   timestamp
        -   stack_trace
        -   url (if any)
        -   action (start, stop, clear, open config)
        -   user_input (if any)
        -   script_version
        -   system_info
    -  user_actions
        -   id (primary key)
        -   action (start, stop, clear, open config)
        -   timestamp
    -  YT_AIO_Version
        -   id (primary key)
        -   version_number
        -   release_date
        -   changelog
 -  The logging system should log all the downloads with their status, any errors that occur during the download process, any changes made to the settings in the config file, and any user actions like starting or stopping the script, clearing the textbox, or opening the config file. This will help in debugging and also in keeping track of the downloads and settings changes.


## 1.6. Issues
- Here issues with each iteration will be put down and will be asked to resolve in the further version 
- **NOTE: AFTER EVERY PATCH FIX Version No. SHOULD BE INCREMENTED IN THE README.md FILE AND ALSO LOGGED IN THE PROGRESSION LOG WITH TIME STAMP AND IN DB TOO**
- 1. The channel / playlist function is not working properly, its fetching the videos but not displaying them in the selectable text box for further processing. Need to fix this issue in the next iteration. -  it says Yt dlp time out. but the same I have done in /home/itzzinfinity/Downloads/my_music/automation/youtube_scraping_stuff/yt_video_list_extractor.py and it works fine there. Need to check the code and see what is causing the issue in the main script. - **Closed**
- 2. in database (yt_aio.db) the download history is not being logged properly, the title is NULL which is not accurate. - need to fix it. - **Closed**
- 3. after clicking download for the first time its working or not need some indication of that. - **Closed**
- 4. Need to make the database relational - **Closed**
- 5. Need to check in the database if the video is already fetched or not before fetching it again to avoid duplicates in the database. And act as cache for the video information. - **Reopened**
  - 5.1. Video infos are being fetched but not being stored in the database. Need to check the code and see what is causing the issue. 
- 6. Downloading Videos got failed. Read logs and take necessary actions to fix the issue.
- 7. migrate all dependencies / all files to the project directory except for run_yt_aio_gui.py - **Closed**
- 8. Default priority for URL download over channel or playlist download is not working. Need to check the code and see what is causing the issue.
- 9. Its showing yt-dlp module not found error. Need to check the logs and see what is causing the issue.
- 10. In `settings` All the texts read from config.json are overlapped with config parsing systems **HELP Dictionary**. Need to fix it. - **Fixed**. Two faults, both mine from the previous session. The help text was being glued onto the key name inside one label as `key\nhelp`, so the two read as a single run-on string. Worse, a word-wrapped label has a height that depends on its width, and that collapsed the whole form: the 49 rows needed about 1800 pixels, the scroll area pinned them to the 690-pixel viewport, offered no scroll bar at all, and squeezed every row to 8 pixels, which is why the key names looked clipped and overlapped. The key is now its own single-line label and the help is a muted caption under the editor it describes, and `_sync_form_height` gives the form its real height so the scroll bar appears. It measures after `activate()` and once more on a deferred pass, because asking during the build returns 18 pixels, the margins alone, and setting that as the minimum was worse than setting nothing.
- 11. While downloading getting this error `name 'build_youtube_extractor_args' is not defined` - Need to check the code. I have commented `yt_aio/application/utils/video_info_extractor.py:117:    args.extend(build_youtube_extractor_args(config))` and it works fine. Need to check the code and see what is causing the issue. - **Fixed**. Your workaround was the right call but it silently dropped `youtube_visitor_data`, which the code passed before. Root cause: the function was never in the file. It was written between `_cookie_home_override` and `build_yt_dlp_env`, and the later edit that rewrote `_cookie_home_override` replaced everything from its own `def` up to the next one, taking this function with it. Nothing caught it because the only reference is inside another function, so it is a NameError at call time and not an ImportError at start-up. Restored, and moved directly above its one caller so the same class of accident cannot repeat. Checked against the last commit that no other function went with it: this was the only one. The commented-out call is live again.

## 1.7. Modularity
- The code should be modular and should be organized.
- Currently its hardcoded `/home/itzzinfinity/Downloads/my_music/automation` directory which is not good. Need to make it more flexible and modular so that it can be used by other users as well without having to change the code.
- there is a folder `yt_aio` which is called by the main script `run_yt_aio_gui.py` which contains all the code for the UI and the functionality of the script. This folder should be organized in a way 
  - `ui` folder for all the UI related code and files
  - `utils` folder for all the utility functions and files
  - `db` folder for all the database related code and files
  - `logs` folder for all the log files
  - `config` folder for the config file and related code
  - `yt_aio` will contain `run_yt_aio_gui.py` and inside there will be `application` directory currently which is `yt_aio` 
  - so it can be moved to any where and it will work without any issues as long as the dependencies.
  - `/home/itzzinfinity/Downloads/my_music/automation` `yt_aio` directory structure will be like this:
    - `application`
      - `ui`
        - `main_window.py` (code for the main window of the UI)
        - `styles.qss` (Qt stylesheet for the UI)
      - `utils`
        - `video_info_extractor.py` (code for extracting video information using yt-dlp)
        - `download_manager.py` (code for managing the download process)
        - `config_manager.py` (code for managing the config file)
      - `db`
        - `database_manager.py` (code for managing the database and logging)
        - `yt_aio.db` (sqlite3 database file for logging downloads, video information, settings changes, errors, user actions, and version history)
      - `config`
        - `config.json` (config file for storing default settings)
    - `run_yt_aio_gui.py` (main script for running the UI and the functionality of the script)
  ### 1.7.1. More thoughts on modularity
  - I have moved the `run_yt_aio_gui.py` inn this directory so this BASE DIR can be moved anywhere and it will work without any issues as long as the dependencies are installed and the config file is set up properly inside the subdirectories. make it that way.
  - I noticed that the `config.json` contains
  - ```
      "default_download_path": "/home/itzzinfinity/Downloads",
      "log_file_path": "/home/itzzinfinity/Downloads/my_music/automation/yt_aio/application/db/yt_aio.db",
      "history_file_path": "/home/itzzinfinity/Downloads/my_music/automation/yt_aio/application/db/yt_aio.db",
      "logs_directory": "/home/itzzinfinity/Downloads/my_music/automation/yt_aio/application/logs"
      ```

  - these paths should be relative to the BASE DIR and not hardcoded to a specific directory. Need to change these paths in the config file and also in the code where these paths are being used to make it more flexible and modular. 
  - ```
      "default_download_path": "/home/itzzinfinity/Downloads",
      "log_file_path": "./db/yt_aio.db",
      "history_file_path": "./db/yt_aio.db",
      "logs_directory": "./logs"
  ``` 
  - make it like this and also make sure that the code is using these relative paths instead of hardcoded paths to avoid any issues when the directory is moved to another location.
### 1.7.2. Read `dev_guide.md` 
- Read `dev_guide.md` for more details on the modularity and list all the changes that need to be made in the code to make it like the documented structure and also tell me the expected output after the changes are made. In this document mainly focus on how to move the current app to a single tab so I can add another features into other tabs in the future. The main idea is to make the code more modular and organized so that it can be easily maintained and updated in the future without having to change the whole codebase.  - **Closed**
- Answer written to `Docs/05_TAB_SHELL_MIGRATION.md`: placeholder mapping from `dev_guide.md` onto this tree, the full change list (A new files, B edits to the moved code, C shell and entry point, D docs), the shell and panel code shape, the SQLite cross-panel contract, the five-tab roster, and the expected output with a verification and smoke-test section.
- That plan was then implemented in version `0.4.0`: `application/shell.py` owns the window and the tab bar, the old `MainWindow` is now `DownloaderPanel(QWidget)` mounted as the `Downloader` tab, and `AppContext` holds the shared config and database path. Remaining tabs from `1.8.2` slot in with one `addTab` line each.

## 1.8. Feature Updates
### 1.8.1. While Fetching the videos from the channel or playlist facing timeout error - need to make it sclable and make it work without any issues. 
  - Need to check the code and see what is causing the issue in the main script.
  - Need to check the logs and see what is causing the issue.
  - Need to check the yt-dlp version and see if there are any updates available for yt-dlp and update it if necessary to see if it fixes the issue
  - If these are fine then need to check how to get the --flat-playlist in chunks to avoid the timeout error and to make it more efficient and faster.
### 1.8.2. Tabs as Containers - **Closed** in `0.5.0`
- I have few apps running in my phone which saves and backup the data. make a tab where I can parse that file and get the data from it and then download the videos from the links in that file. or add those database into my database. - **Done** as the `Import` tab. The format is detected from the file's own bytes, not its extension, so SQLite backups, ZIP archives, JSON, CSV and plain lists of links all work. Parsed items can be merged into the database or downloaded directly. No sample backup file was supplied, so the parser was written to be format-agnostic; point it at a real export and it can be narrowed if anything is missed.
- Make a new tab in the UI where I can view the logs and the download history from the database. and errors and the stack trace from the database.  - **Done** as the `Logs` tab. Read-only, with search, paging and a detail pane that shows the full stack trace. Deletion deliberately lives in the `Library` tab instead.
- Make a new tab in the UI where I can view the settings and change them from the UI instead of opening the config file in a text editor. - **Done** as the `Settings` tab. The form is generated from `build_default_config`, so a new setting shows up on its own. Saving is atomic and every change is recorded in `settings_changes`, with credential-shaped values redacted.
- Make a new tab in the UI where I can view the view the existing data in the database and also delete the data from the database if necessary. with filters and search options to make it easier to find the data in the database. (Note all the data is mainly audio information so optimize accordingly) - **Done** as the `Library` tab. Search, source and status filters, all paged in SQL so the 3462-row cache is never loaded whole. Deleting metadata keeps the download history and never touches files on disk.
- Make a new tab in the UI where I can add a path with `browse` button to select the path and check the added folder and its sub folders for any audio files, run metadata extraction on those files and compare them with the existing data in the database so I can refrain from downloading the same audio files again and also to check if there are any new audio files in the added folder. Also allow to compare if there are any new audio files if the name/metadata clashes occur. - **Done** as the `Local Scan` tab. Tags are read by mutagen, then ffprobe for anything mutagen declines, then the file name; whichever answered is shown per row. A file is graded rather than judged yes or no, because a wrong "already have it" would stop a download you wanted: `In database` when the video id or the file path is already recorded, `Probable match` when the title agrees and the durations are within four seconds, `Title clash` when the title agrees but the duration does not, `New` when nothing resembles it. Clashes get a side-by-side comparison of the file and the database row in the detail pane. Results persist in a new `local_files` table, so a rescan also reports which files were not there last time and forgets the ones that have gone.
- In the `settings` tab add all available suggestions for that particular setting which can be applied in that field. - **Done**. 20 text fields became editable drop-downs fed from `SETTING_SUGGESTIONS`, and 5 numeric fields got a real range and a typical-value tool tip instead of 0 to 1000000. The 7 remaining keys are booleans, which were already tick boxes. Every field still accepts anything typed: yt-dlp takes far more than can be enumerated, so the list is a shortcut and never a validator. The value currently in the file is always offered, so a working setting the catalogue has not heard of never has to be retyped.
- Read `./home/itzzinfinity/Downloads/ytdlnis/` and tell me what are the differenct commands and what kind of approach is taken which is a better approach than the current one. Also tell me how to implement that in the current script and what changes need to be made in the code to implement that approach. - **Answered** in `Docs/06_YTDLNIS_APPROACH.md`. Everything worth having is in one file, `YTDLPUtil.kt`. The commands, the eight changes worth making with the file and function for each, and the four things not worth copying are all written up there. The largest single difference: for full metadata they write every URL to a file and run yt-dlp once with `-a urls.txt`, where we start one process per video. Others worth naming are `--download-archive` for duplicate prevention, `--parse-metadata` to strip YouTube's ` - Topic` suffix off the artist, `-S` format sorting instead of a fixed `-f`, and `--lazy-playlist` with `-R 1`, which is the direct answer to the timeout in 1.8.1. Nothing was implemented; the item asked what to change, so the answer is the change list.
- In ./Docs/song_db_erd.html file opentune backup file database schema is given. Read it and implement `Import` tab correctly - **Done**. A schema-aware reader, `features/importer/opentune.py`, now recognises the OpenTune / InnerTune Room database and reads it by its tables; the blind scan stays as the fallback for everything else. The generic scan was wrong here in two ways that mattered. It walked `related_song_map`, which is the recommendation graph and the largest table in the file, so it imported songs you never saved. And it attached no artist to anything, because an artist name is only reachable through `song_artist_map`, so every row came out with an empty channel. Only the `song` table now produces rows, each carrying its artists, album, playlists, cached bitrate and play count, plus the collection that explains why it is there. On a 300-song, 4000-relation test backup the reader returns 300 songs with artists where the old scan returned 301 with none, the extra one being an album's playlist id mistaken for a video. The tab opens on the 50 saved, liked, downloaded, played or playlisted items rather than on all 300.
- In each **Viewer** part (either in library or Import) 
  - Add a filter for Duration, Channel and also add sorting options for each column in the table. - **Done** in the Library, Import and the new Local Scan viewers. Duration is a pair of minute spin boxes where zero means unbounded, and a row with no duration is excluded by any duration filter rather than shown as if it matched. Channel and artist are editable drop-downs with substring completion, filled from the data actually present. Every column heading sorts, and clicking the same one again reverses it. Library and Local Scan sort in SQL because they are paged, since sorting one page out of 3462 rows would look like a sort and behave like a bug; Import sorts in memory because a parsed file is held whole. Import's tick boxes are keyed by video id rather than by row, so a selection survives a change of filter or sort, and the count is shown next to the buttons so what the actions will act on is never in doubt.
  - Add a toggle in settings for Night Mode and Day Mode for the UI. - **Done**. `ui/styles.qss` became a template with its 26 colours lifted into markers, and `ui/theme.py` holds a `dark` (Night) and a `light` (Day) palette that render it. The setting is `ui_theme`, which the Settings tab picks up as a drop-down on its own because it comes from `build_default_config`. The shell listens for the config change and repaints the whole window, so the switch takes effect on Save with no restart.
  - Apply fixes from `./Docs/06_YTDLNIS_APPROACH.md` to the current script and make the necessary changes in the code to implement that approach. - **Done**, all nine sections, in the order that document recommends. Three of its recommendations were measured and changed rather than copied. Batching the metadata fetch *and running the batches in sequence* was slower than the thread pool it replaced, because a yt-dlp process spends about a second starting and then fetches its URLs one after another, so the batches keep a pool: 12.7s became 7.0s for six videos. The audio sort's `+size` term picks the smallest stream rather than the best, and chose 49 kbps where every other selector chose 130, so it is dropped. `--no-warnings` on the listing would have silenced two of the bot-challenge markers the cookie retry watches for, so it is not passed. `--config-locations` was evaluated and skipped: with every option on the command is 49 arguments and 907 bytes against a 2 MB limit, and it never touches a shell. Fourteen new settings came with it. The listing now streams from the first second instead of collecting a whole channel, which is the direct answer to 1.8.1, and a second metadata pass over the same videos runs no yt-dlp at all.
  - Opentune Database is very good and has a lot of information about the songs and the artists. - Make a document / step by step approach to implement the same in the current script and make my database a similar one so I can get all the info about the songs and the artists from the database. - **Done**, planned in `Docs/07_MUSIC_SCHEMA_PLAN.md` and then built. Seven tables now sit beside the old two: `songs` keyed on the video id, plus `artists`, `albums`, `playlists` and three junctions. The existing 3461 cached rows were revived into them with nothing lost. An artist is a row rather than a column, so a song with three credits keeps all three and is found by any of them: on the real OpenTune backup that is 4091 songs the old single `channel_name` column could never have described.
    - Steps include table creattion, table relationships, data insertion, data retrieval, and data display in the UI. - **Done**. Creation and relationships in `db/database_manager.py`, insertion through one `upsert_songs` that both the importer and the listing write through, retrieval through `fetch_songs`-style filters in `db/queries.py`, and display as three new Library columns with three filter drop-downs. Every one sorts and filters in SQL.
    - Also current database info reviving with PRIMARY KEY - Video ID - **Done**. `songs.video_id` is the primary key, and the backfill runs from `init_db` guarded on an empty table so it happens once and is safe to re-run. `youtube_video_information` keeps its integer id and the `downloads.video_info_id` references that point at it, so nothing that worked before stopped working.
  - Like  `./Docs/song_db_erd.html` file, make a similar ERD for `./home/itzzinfinity/Downloads/my_music/database/ViTune_backup_20250831122626.db` and add a parser for that database in the `Import` tab so I can import the data from that database into my current database. 
    - AND JUST FOR MY UNDERSTANDING, MAKE A DOCUMENT OF COMPARISION BETWEEN OPENTUNE and VITUNE DATABASE. - MAKE HTML FILE - **Done** as `Docs/opentune_vs_vitune.html`. All 16 tables side by side with real row counts from both of your backups, 13 questions an importer has to answer, and the mapping onto the new music tables. The short version: OpenTune records more about a song, ViTune records more about listening, and neither is a superset of the other.
  - I have installed Brave Browser in the settings tab add the path for cookies from Brave Browser as a fallback - **Done**. Your Brave is a snap, so its cookies are at `~/snap/brave/678/.config/BraveSoftware/Brave-Browser/Default/`, which is not where yt-dlp looks. `~/.config/BraveSoftware/Brave-Browser` exists on your machine and contains no profile at all, which is why testing for a directory was never enough. The Settings tab now offers the real path in `cookie_fallback_home`, lists the profiles it found in `cookie_fallback_profile`, and prints under the browser field exactly what was found and what to set. One caveat: the cookies themselves are currently stale, and yt-dlp reports them as rotated. Sign in to YouTube in Brave once and they will work.

  - **Not part of the request, but you should know**: every download on this machine fails with `HTTP Error 403: Forbidden`, including the old command with none of these changes applied. The installed yt-dlp is version 2026.03.17, which it reports as more than 90 days stale. Run `python3 -m pip install -U yt-dlp` before trusting a download test.
### 1.8.3. Combine the best of opentune and vitune database which will be my final database.
- Read `./Docs/opentune_vs_vitune.html` file and make a final database `songs.play_count` & `songs.liked` I dont need them - **Done**. Both columns are gone from the schema, from every write path, and from any database that already had them, through a migration guarded so it runs once and is safe to re-run. **Reopened** for `liked` in 1.12: you wanted it back so the Library can filter on it, and it is now carried with override semantics, so a re-import is the authority. `play_count` stays dropped and that part still holds, because a play count is a running total that is stale the moment it is read where a like is a decision. The parsers still read a backup's plays and likes, because that is how the Import grid decides the Collection label for the file you are looking at. Verified by importing your real 5029-song ViTune backup into a migrated copy: 8519 songs, 11610 credits, artist filter unchanged.
- in local scan tab I want a button `ADD TO DATABASE` which will add the new audio files to the database (if they have video id) and also update the existing audio files in the database if they have any changes in the metadata. And check if already they exist but not flagged as downloaded then update the flag to downloaded. - **Done**. The button acts on everything the filters currently match, not the page on screen, because this grid filters rather than selects, and it says how many before it does anything. One judgement call worth knowing: a file fills in what a song is missing but does not overwrite what it already has, because a yt-dlp title is better evidence than an ID3 tag from an unknown ripper, and `local_files` already keeps the file's own values refreshed on every scan for comparison. Tested on 92 of your real downloads and on a folder built for the purpose: an unflagged video went to downloaded with no duplicate row, and a second press added nothing.
- If video id is not present then add them in a different table so they will be logged but not interfere with direct access to the query and give false positive for the existing audio files in the database. - **Done** as `local_only_tracks`, keyed on the file path. Exactly the reasoning you gave: a song in `songs` has a YouTube identity that can be looked up and re-fetched, a file with only an ID3 tag has none, and mixing them would make a title collision read as a match it is not. Three untagged files in the test folder landed there with none reaching `songs`.
- in `Library` Tab until I click select all on this page it wont allow me to delete the selected audio files from the database. - **Fixed**. Root cause: nothing watched the individual tick boxes, so the only code path that ever enabled `Delete selected` was the select-all checkbox. Deleting one row meant selecting the whole page and unticking the rest. The grid's own change signal now drives the button. Two traps on the way: filling the grid fires that signal for every cell and none of those are selections, so `_render` blocks it; and declaring the slot as taking `object` makes Qt refuse the connection outright, because the signal carries a table item.

### 1.8.4 `Downloaded` Needs Concern
- The app should only flag **downloaded** those ones which are present in local music library (e.g. Laptop or PC) after `local scan` --> `add to database` - **Done**. `Local Scan -> Add to database` is now the only writer that can raise the flag, and a song whose file has left the local index loses it again, checked on every start and after every scan. Root cause of the 8895 wrong flags on your database: three of the four things that set the flag had never looked at this disk. An OpenTune backup's Downloaded collection describes a phone, the revival seeded from the `downloads` history, and a backfill pass re-raised it from the same history afterwards. History records that a file was written once, which is a different claim from the file being here now. On your data the truth is 3568. One consequence worth knowing: a download this app performs does not flag itself either, because nothing has yet seen the file where the library lives, so it turns up on the next scan and add.
- Backup files which are added to main db should not flag **downloaded** as **1** - **Done**. The import payload no longer carries the key at all, and `downloaded` left the `MAX` merge that made the flag one-way, so a wrong 1 can now be corrected instead of being permanent. Verified with your real OpenTune backup: 5729 of its 15691 items claim Downloaded and the count in the database did not move. The Import grid still shows the Downloaded label, because there it describes the backup on screen rather than this laptop.

## 1.9. Roadmap — batch from FSD 1.8.2 (line 243 onwards)

The five requests at the end of `1.8.2` are split here into atomic tasks. One task per
pass: implement it, run the self-check, tick it with the date and a one-line summary.
The bullets above stay as written and are annotated in place when the whole request closes.

### A. Day / Night theme toggle
- [x] A1 — Turn `ui/styles.qss` into a token-driven theme module with a dark and a light palette — done 2026-09-05; `styles.qss` became `styles.template.qss` with its 26 colours lifted into `@token@` markers, new `ui/theme.py` holds the `dark` and `light` palettes and renders the template, and the shell paints through `apply_theme` after the config loads. Verified by rendering both palettes and asserting no marker survives.
- [x] A2 — Add the `ui_theme` setting and apply the theme live from the Settings tab — done 2026-09-05; `ui_theme` joins `build_default_config` and `SETTING_SUGGESTIONS`, so the Settings tab renders it as a drop-down with no change to that panel, and the shell listens on `config_changed` and repaints the whole window when the palette actually differs. Verified offscreen: saving light swapped the application style sheet and saving dark put it back.

### B. Apply `Docs/06_YTDLNIS_APPROACH.md` (its own §5 order)
- [x] B1 — §3.5 harden the listing: `--lazy-playlist`, `-R 1`, `--socket-timeout`, `youtubetab:approximate_date` — done 2026-09-05; new `build_listing_args` in `utils/video_info_extractor.py` builds the list once for both the first attempt and the cookie retry, and `socket_timeout` joins the config with a 1-to-300 range. `--no-warnings` was left out on purpose: two bot-challenge markers arrive as warnings, so silencing warnings would silence the cookie retry with them. Because `--ignore-errors` can exit zero with nothing extracted, the retry decision now reads stderr rather than the exit code. Verified against a real playlist: entries stream from the first second instead of after the whole list is collected.
- [x] B2 — §3.1 batch the full-metadata fetch with `-a urls.txt` and `--print`, in chunks — done 2026-09-05; new `fetch_metadata_batch` writes each chunk's URLs to a temporary file and runs one yt-dlp with `--print` over a field subset instead of one `-J` process per video, and `list_videos` folds the results back through a callback so progress still streams. The source document runs the chunks in sequence; measured, that was slower than the thread pool it replaced, because a process spends about a second starting and then fetches its URLs one after another. So the chunks keep a pool: `metadata_batch_size` URLs per process, `max_metadata_workers` processes at once. Six real videos took 12.7s one process at a time and 7.0s across three, with the dead URL skipped and reported rather than failing the run.
- [x] B3 — §3.3 replace `--add-metadata` with `--embed-metadata` plus the `--parse-metadata` rules — done 2026-09-05; new `build_metadata_args` in `utils/download_manager.py` writes the two Topic-stripping rules on every download, with the playlist-to-album rule behind the new `embed_album_from_playlist` flag, off by default because a playlist title is usually a mix name and a wrong album tag is harder to spot than a missing one. Verified against a real auto-generated upload: the uploader tag went from `WB V2 MIX - Topic` to `WB V2 MIX`, and an official artist channel's existing artist and album survived untouched. This also feeds Local Scan, which matches on title and artist.
- [x] B4 — §3.4 + §3.8 `-f ba/b` with `-S` sorting, and `-N` / retries / rate limit pass-through — done 2026-09-05; `build_audio_format_args` and `build_tuning_args` in `utils/download_manager.py`, with six new settings: `preferred_audio_codec`, `concurrent_fragments`, `download_retries`, `fragment_retries`, `limit_rate` and `restrict_filenames`. The retry counts are deliberately not `max_retries`, which re-runs the whole command, because one number would multiply the two. The document's sort ends with `+size` and that term is dropped: user sort terms outrank yt-dlp's own bitrate term, so on a real track `+size` selected a 49 kbps stream where both the old selector and the sort without it selected 130 kbps. Format selection verified with `--print` on a real video. The transfer itself could not be verified here: every download 403s on this machine, including the old command unchanged, because the installed yt-dlp is 2026.03.17 and about six months stale.
- [x] B5 — §3.2 `--download-archive`, kept alongside the database check — done 2026-09-05; `build_archive_args` adds the option with the path from the new `download_archive_path` setting, defaulting to `./db/downloaded.txt`, behind the new `enable_download_archive` switch. The archive is what stops the fetch with no gap between the check and the download; the `downloads` table is still what the Library and Local Scan tabs read, so both are kept. An unwritable archive directory drops the option rather than failing the download. Verified against a real archive file: the recorded id was skipped and an unrecorded one reached the fetch.
- [x] B6 — §3.6 + §3.7 info-JSON cache reuse, player clients and PO tokens — done 2026-09-05; `build_youtube_extractor_args` now joins visitor data, `youtube_player_clients` and `youtube_po_tokens` into the single `--extractor-args youtube:` value yt-dlp expects, because it keeps only the last such option per extractor. The cache stores our own field subset as one JSON file per video id and `fetch_metadata_batch` reads it before deciding what to fetch, which goes one step past the document's `--load-info-json`: a second pass starts no yt-dlp process at all. Measured on two real videos, 5.66s cold and 0.00s warm. Settings gained `info_cache_enabled`, `info_cache_dir` and `info_cache_max_age_hours`.
- [x] B7 — §3.9 `--config-locations` for the long argument list, only if it has become unwieldy — closed 2026-09-05 without a change, the condition is not met. With every optional feature switched on at once the download command is 49 arguments and 907 bytes against a 2 MB limit, and it is handed to `subprocess` as a list, so there is no shell and no quoting to get wrong. Writing those arguments to a file would add a temporary file, a cleanup path and a second place an option can come from, and buy nothing. The source document itself calls this insurance rather than a speed-up and puts it last. Revisit only if the list ever nears the limit.

### C. OpenTune-grade music schema
- [x] C1 — Write `Docs/07_MUSIC_SCHEMA_PLAN.md`: tables, relationships, insertion, retrieval, UI, video-id key — done 2026-09-05; eight sections covering what the two-table schema gets wrong, the six new tables with their SQL and the relationship map, the guarded backfill that revives the existing rows under a `video_id` primary key, one `upsert_songs` entry point with the empty-value rule that stops a thin import blanking a good title, the five paged read queries, the Library columns and detail pane, and the four OpenTune tables not worth copying.
- [x] C2 — Create the music tables and their migration in `db/database_manager.py` — done 2026-09-05; `songs`, `artists`, `albums`, `playlists` and the three junction tables now sit in the `init_db` script with eight indexes, `songs` keyed on `video_id`. Nothing existing was touched, so the upgrade runs on the live database in place: the real file gained all seven tables with its 3461 cached videos and 23 downloads unchanged.
- [x] C3 — Backfill the existing `youtube_video_information` rows into `songs`, keyed by video id — done 2026-09-05; `_backfill_music_tables` runs from `init_db`, guarded on an empty `songs` table so it is idempotent, with `_slug` and the three `*_id_for` helpers giving a stable key to names that have no identifier. On the real database it produced 3461 songs, 3 artists with 3461 credits, 2 playlists with 20 memberships, and marked 13 songs downloaded, which is every distinct video id among the 15 successful downloads, 2 of which carry no video id at all. A second run changed nothing. `channel_name` is deliberately not split on commas: no row has one, and a channel named `Smith, Jones & Co` would be torn in half by the guess.
- [x] C4 — Write path: the Import tab merges parsed items into the music tables — done 2026-09-05; `upsert_songs` in `db/database_manager.py` merges a song with its artists, album and playlists in one call, overwriting a column only when the incoming value is not empty and leaving junction rows alone for any kind the payload does not mention, so a thin import cannot blank a good title or delete credits it never knew about. Both write paths feed it: `import_video_rows` for a backup and `log_video_info` / `log_video_info_batch` for a listing, each outside the cache transaction so a music-table failure cannot cost a cache row. Verified on a copy of the live database with the real 9583-song OpenTune backup: 4895 artists, 20025 credits and 4091 songs with more than one credited artist, which is exactly what a single `channel_name` column could never hold.
- [x] C5 — Read path: Library shows and filters on artist, album and playlist — done 2026-09-05; the Library grid gained Artists, Album and Playlists columns and a filter row of three editable drop-downs fed by the new `fetch_artists`, `fetch_albums` and `fetch_playlists`. Filtering is an `EXISTS` over an indexed key rather than a `LIKE` over one text column, so a song credited to three artists is found by any of the three: `Mika Singh` returns 38 rows, most of which do not have that name first. The search box reaches the credits too. All three columns sort in SQL, by lead credit, album and first playlist. The page's credits are assembled in Python because SQLite here is 3.37, which has no `ORDER BY` inside `GROUP_CONCAT`, and the lead artist has to come first. Sorting 13044 rows by any of the three took under 0.05s. Verified offscreen end to end.
- [x] C6 — Treat a negative duration as unknown — done 2026-09-05; found while verifying C5. OpenTune writes `-1` for a song whose length it never learned, and 8050 of the 9583 songs in the real backup carry it, so the grid showed `-1:59:59`. `coerce_duration` now returns None for a negative value and `format_duration` reports `Unknown` rather than formatting one. The duration filter already excluded rows with no duration, so those rows are now honestly excluded instead of matching every range.

### D. ViTune backup
- [x] D1 — Generate `Docs/vitune_db_erd.html` from the ViTune backup, in the style of `song_db_erd.html` — done 2026-09-05; written as a generator, `Docs/generate_vitune_erd.py`, so a newer backup is one command rather than a hand edit. It reads the backup read-only and emits the diagram, the six relationship cards, a card per table with primary and foreign keys marked, and a size table. On `ViTune_backup_20250831122626.db` that is 15 tables, 1 view and 43,792 rows. Checked by rendering the page headless: every box, edge and card lays out correctly.
- [x] D2 — Add `features/importer/vitune.py` and register it in the Import tab — done 2026-09-05; a separate reader from `opentune.py`, because ViTune's tables are PascalCase, its duration is the string `3:35`, its `SongArtistMap` is empty for a fifth of the songs so `artistsText` cannot be ignored, and it has no download or library column, so nothing is marked Downloaded rather than guessed. Registered ahead of the blind scan in `parsers.py`. On the real backup it reads 5085 rows and keeps 5029, skipping 42 on-device `local:` files and 14 blacklisted songs, and finds 2104 multi-artist songs, 3936 albums and 329 playlist memberships.
- [x] D2a — Fix two credit-parsing faults found while verifying D2 — done 2026-09-05; nine ViTune credits hold a non-breaking space, so `Arijit Singh` typed normally matched 2 songs instead of 212. `clean_name` in `db/database_manager.py` now collapses every whitespace run before a name is stored, and the parser does the same on the way out. Splitting a credit on a spaced ampersand also tore `Simon & Garfunkel` in half, so a credit the Artist table already knows in full is no longer split at all. The heuristic still splits a duo the table has never heard of, which is the honest limit of it. Pipes always separate: 32 songs use them and no artist name contains one.
- [x] D3 — Write `Docs/opentune_vs_vitune.html`, the schema comparison — done 2026-09-05; six verdict cards, a table-for-table comparison of all 16 tables with real row counts from both backups, a feature-by-feature table of 13 questions an importer has to answer, and the mapping onto the YT AIO music tables. The short version: OpenTune records more about a song, ViTune records more about listening, and neither is a superset, which is why there are two readers. Checked by rendering the page headless.

### F. Regressions reported after the 1.9 batch (FSD 1.6 items 10 and 11)
- [x] F1 — Restore `build_youtube_extractor_args`, deleted by the E1 edit — done 2026-09-05; the helper sat between `_cookie_home_override` and `build_yt_dlp_env`, and the E1 rewrite of the first replaced the text up to the second, taking it with it. Every download then raised `NameError` at call time, which no import check could catch. Restored above its only caller and the call uncommented, so `youtube_visitor_data`, `youtube_player_clients` and `youtube_po_tokens` reach yt-dlp again. Verified against the last commit that no other function was lost, and by building the base arguments with each combination.
- [x] F2 — Stop the Settings help text overlapping the config keys — done 2026-09-05; the key and its help shared one word-wrapped label, which both read as a run-on string and collapsed the form, because a wrapped label's height depends on its width and the scroll area then pinned 49 rows into a 690-pixel viewport at 8 pixels each with no scroll bar. The key is now its own single-line label, the help is a muted caption under its editor, and `_sync_form_height` sets a real minimum height after `activate()` plus one deferred pass. Measured before and after: host height 687 with scroll range 0 and 8-pixel rows, against 2335 with scroll range 1618 and 22-to-32-pixel rows. Confirmed by screenshot in both themes.

### E. Brave cookies
- [x] E1 — Detect the Brave profile and cookie paths and offer them in the Settings tab — done 2026-09-05; new `utils/browser_cookies.py` knows the three layouts a browser can have on Linux and tests for an actual cookie file rather than a directory, which matters here: `~/.config/BraveSoftware/Brave-Browser` exists on this machine and holds no profile at all, while the real cookies are in the snap revision `~/snap/brave/678`. `cookie_fallback_home` and `cookie_fallback_profile` are now filled from what is installed instead of from a guessed list, and the Settings tab prints under the browser field exactly what was found and what to set. The extractor's own snap-only lookup was replaced by the shared one, so flatpak and package installs are handled too. Verified: `brave` resolves to the snap revision, `chrome` correctly resolves to no override because it is a package install, and an explicit home still wins.
- [x] E2 — Balance the Library filter row — done 2026-09-05; noticed while screenshotting E1. The channel drop-down was built by hand with no stretch, so a 2000-entry list gave it a size hint that swallowed the row and left the search box 40 pixels wide. It now goes through the same builder as the three new lookups, which also caps a drop-down at 340 pixels, and the hand-rolled setup and its duplicate refill code are gone.

## 1.10. Roadmap — run on Windows, and run from a fresh clone

Goal: someone clones the repository on Windows, macOS or Linux, installs the
dependencies, runs `python -m yt_aio`, and the application starts and works. Today it
does not, for two separate reasons: five subprocess calls decode yt-dlp's output with the
system code page, which crashes on any non-ASCII title on Windows, and the repository
ships generated files that carry one particular machine's absolute paths.

### G. Clone-and-run
- [x] G1 — Untrack generated and machine-specific files, and write a real `.gitignore` — done 2026-09-05; 45 files left the index and stayed on disk: 42 `__pycache__` entries, the 9.7 MB `yt_aio.db` holding one person's 3490-song library, `config.json` carrying `/home/itzzinfinity/Downloads` as an absolute path, and `downloaded.txt`. A clone now contains 65 files, all source and documentation. The logs directory keeps its `.gitkeep` so the directory still arrives; only its contents are ignored.
- [x] G2 — Add `pyproject.toml` and `requirements.txt` declaring every dependency — done 2026-09-05; PyQt6, yt-dlp and mutagen, `requires-python >=3.10`, a `qt5` extra for a machine where PyQt6 will not build, and a `yt-aio` console script. Verified by building a wheel: metadata correct, all 38 modules present, and `styles.template.qss` shipped, which it would not have been without the package-data entry. Note that setuptools 59 on this machine is too old to read PEP 621 metadata and silently produced an `UNKNOWN-0.0.0` wheel with `--no-build-isolation`; the isolated build, which is what `pip install` does by default, is correct.
- [x] G3 — First run on a clean machine creates its own config, database and directories — done 2026-09-05; no code change was needed, only the untracking in G1: `ensure_config` already wrote a default config and `init_db` already created the schema, but a committed `config.json` meant a clone inherited someone else's absolute download path instead. Verified by building a clean tree from the git index, which contains no database, config or cache, and running it: all six tabs opened, and it created its own config and database with `default_download_path` resolved from `Path.home()` on the running machine.

### H. Windows correctness
- [x] H1 — Decode every subprocess as UTF-8 instead of the system code page — done 2026-09-05; new `process_kwargs` in `utils/shared.py` is now the only way this application starts a process, and all five sites use it. `text=True` on its own decodes with the locale encoding, which is UTF-8 here and the ANSI code page on Windows, so the first non-ASCII title raised UnicodeDecodeError mid-listing and took the batch with it. Demonstrated with a real title from the library: decoding those bytes as cp1252 fails on byte 0x8d, and the same video now fetches correctly through the batched path. `errors="replace"` means an unexpected byte costs one character rather than the run.
- [x] H2 — Stop `infer_output_path` assuming a path starts with `/` — done 2026-09-05; true of every absolute path on Linux and of none on Windows, where they start with a drive letter, so on Windows every download succeeded and no file path was ever recorded. It now asks pathlib whether the line is absolute and exists, which rejects yt-dlp's progress lines just as firmly. Checked against a real file, a relative path, a Windows path, a progress line and no output at all.
- [x] H3 — Hide the console window each subprocess opens on Windows — done 2026-09-05; `process_kwargs` adds CREATE_NO_WINDOW on Windows only, so yt-dlp does not blink a console on screen once per download and once per metadata batch. Nothing is lost, because stdout and stderr are piped and the Downloader tab shows every line. Verified by faking the platform: the flag appears on Windows and is absent elsewhere.
- [x] H4 — Find Brave and the other browsers where Windows actually keeps them — done 2026-09-05; `browser_cookies.py` now holds a per-platform table for seven Chromium-family browsers plus Firefox, covering `%LOCALAPPDATA%` and `%APPDATA%` on Windows and Application Support on macOS. It also checks `<profile>/Network/Cookies`, which is where Chromium moved the database and which the old code missed entirely. On Windows and macOS no HOME override is returned, because yt-dlp finds those itself; only a snap or flatpak needs pointing at. Verified against fabricated Windows and macOS layouts, including a Guest Profile with no cookie file being correctly ignored, with Linux behaviour unchanged.
- [x] H5 — Replace `os.uname()` and the Debian font-package name with portable equivalents — done 2026-09-05; `os.uname()` does not exist on Windows and the three guarded call sites fell back to `os.name`, which reports `nt` and says nothing. One `system_info()` built on `platform` replaces them and reports the release and the Python version too. Separately the style sheet asked for the font family `fonts-dejavu-core`, which is a Debian package name and matched nothing on any machine. Replacing it with a named stack was worse and had to be undone: Qt takes the first family that exists, and with `Noto Sans` named a Bengali title rendered with broken conjuncts, because that face is installed here without Bengali shaping tables. Rendering the same string with no family set is correct, so the declaration is gone entirely and Qt uses its own default, which is Segoe UI on Windows and the system font elsewhere. Caught by screenshotting the library, which is full of Bengali and Hindi titles, rather than by the warning Qt printed.
- [x] H6 — Locate ffmpeg and ffprobe, and say so plainly when they are missing — done 2026-09-05; new `utils/external_tools.py` tries the `ffmpeg_location` setting, then PATH, then a `bin` folder beside the project, then the directories winget, Chocolatey, Scoop and Homebrew use. `--ffmpeg-location` is passed only when PATH does not already have it. ffprobe in Local Scan is resolved rather than assumed, and returns no tags instead of raising when it is genuinely absent. All five discovery paths tested, including a fabricated winget shim directory.

### I. Telling the user
- [x] I1 — A start-up preflight that names what is missing instead of failing obscurely — done 2026-09-05; new `yt_aio/preflight.py` runs from `__main__` before the shell is imported, because importing the shell reaches PyQt on its third line and a check that runs afterwards never runs on the machine that needs it. It separates what blocks start-up, the Python version, a Qt binding and yt-dlp, from what only limits it, mutagen and ffmpeg, and prints the pip command for each. Enabling this meant making `application/utils/__init__.py` lazy: its eager re-exports pulled in PyQt through the panels, so the check could not run without the thing it checks for. That also removes the db-to-utils import cycle noted in session 1. Verified both ways: a healthy machine prints nothing and starts, and a machine with nothing installed gets named requirements and exit code 1.
- [x] I2 — Rewrite `README.md` with per-platform install and run instructions — done 2026-09-05; copy-pasteable clone-install-run blocks for Windows, macOS and Linux, four ways to satisfy ffmpeg on Windows, the note that `python3` is not usually a Windows command, what the preflight prints when something is missing, what the first run creates, and a layout table. The old README described a `styles.qss` that no longer exists and listed the config and database as project files when they are now generated. Every documentation link and every path in the layout table was checked to exist.

## 1.11. Roadmap — batch from FSD 1.8.3

The four requests in `1.8.3`, split into atomic tasks. One per pass: implement it, run the
self-check, tick it with the date and a one-line summary.

### J. The final schema
- [x] J1 — Drop `songs.liked` and `songs.play_count`, with a migration for existing databases — done 2026-09-05; gone from the `init_db` script, and `_drop_retired_columns` removes them from a database that predates the change, because `CREATE TABLE IF NOT EXISTS` leaves an existing table exactly as it was. SQLite here is 3.37 and `DROP COLUMN` arrived in 3.35; on anything older the column is left alone, which is harmless once nothing reads it. Verified on a copy of the live database: 3490 rows and all 13 downloaded flags survived, and a second run changed nothing.
- [x] J2 — Stop every write path filling them — done 2026-09-05; removed from the `upsert_songs` insert, its conflict clause and its parameters, and from the importer's payload builder. The parsers still read a backup's play counts and likes, because that is how they decide the Collection label and the Import grid's Plays column, which describes the file being looked at rather than the library. Verified by importing the real 5029-song ViTune backup into a migrated database: 8519 songs, 11610 credits, and the artist filter still returning 212 for Arijit Singh.

### K. Local Scan writes to the library
- [x] K1 — A `local_only_tracks` table for audio that carries no video id — done 2026-09-05; keyed on the file path, with title, artist, album, duration, bitrate and where it was found, plus three indexes. Kept out of `songs` deliberately: a song there has a YouTube identity that can be looked up and re-fetched, and a file with only an ID3 tag has none, so letting the two share a table would make every duplicate check step over rows it can never resolve and turn a title collision into a false match. Added to an existing database with the 8519 songs untouched.
- [x] K2 — `add_local_files_to_library` in the database layer: insert, update, and flag as downloaded — done 2026-09-05; one function, two destinations, decided by whether the file carries a video id. A file that does becomes a song through `upsert_songs` with `downloaded` set; a file that does not goes to `local_only_tracks`. The file fills gaps rather than overwriting, because a yt-dlp title is better evidence than a tag from an unknown ripper, and `local_files` already keeps the file's own values refreshed on every scan. Verified on 92 real downloads and then on a fabricated mixed folder: a video already in `songs` but unflagged had its flag flipped 0 to 1 with no duplicate row, three untagged files landed in `local_only_tracks` with none leaking into `songs`, and a second run added nothing and flagged nothing.
- [x] K3 — The `ADD TO DATABASE` button and its worker in the Local Scan tab — done 2026-09-05; runs on the shared `CallableThread` like the scan does, acts on the whole filtered set rather than the page because this grid filters instead of selecting, and states the count in the confirmation. Enablement had to move into `_render`: it was computed once at construction, before any row existed, so the button stayed dead. Verified in the running application: enabled with 1463 matches, disabled when a filter matches none, enabled again when cleared, and disabled while a task runs.

### L. Library
- [x] L1 — Enable `Delete selected` when rows are ticked one at a time, not only by select-all — done 2026-09-05; nothing watched the individual tick boxes, so `setEnabled` was only ever reached through the select-all checkbox and deleting one row meant selecting the whole page and unticking the rest. The grid's `itemChanged` now drives it, filtered to the tick box column. Two details made it work: `_render` blocks the signal while it fills the grid, because setting a cell fires `itemChanged` for every cell and none of those are selections, and the slot carries no `pyqtSlot(object)` decorator, which declares a signature Qt refuses to connect to `itemChanged(QTableWidgetItem*)`. Verified through all seven states: load, one tick, two ticks, untick, select all, clear, and reload.

## 1.12. Roadmap — liked songs, from FSD 1.8.3 reopened

`songs.liked` was dropped in 1.11 and is wanted back: OpenTune and ViTune both record
which songs were liked, and that should be filterable in the Library. `play_count` stays
dropped, which was not part of the reversal.

The important detail is that a re-import must **override** the flag rather than merge it.
A song unliked on the phone has to come back unliked here, so `liked` cannot use the
`MAX` rule that `downloaded` uses. Those two differ for a good reason: a backup is the
only authority on what is liked, and no authority at all on what is on this disk.

- [x] N1 — Restore `songs.liked`, re-adding the column to databases that already dropped it — done 2026-09-05; back in the `init_db` script and off the retired list, with an `_ensure_column` call because a database written between 1.11 and 1.12 has no such column and `CREATE TABLE IF NOT EXISTS` will not add one. `play_count` stays retired: a like is a decision worth keeping, a play count is a running total that is stale the moment it is read. Verified from both older shapes: a database with no `liked` gained it at 0 with its 21923 songs and 8858 downloaded flags intact, and one that still had `play_count` kept all 498 of its liked rows while losing only the count.
- [x] N2 — `upsert_songs` overrides `liked` when a payload names it and leaves it alone when silent — done 2026-09-05; `liked` is deliberately absent from the conflict clause and settled by a follow-up UPDATE, which is what lets a 1 become a 0. `MAX`, the rule `downloaded` uses, would make the flag one-way and unliking impossible. The two differ because a backup is the sole authority on what is liked and no authority at all on what is on this disk. Verified across eight cases: liking, unliking, re-liking, a silent listing leaving it alone, `downloaded` still refusing to go back to 0, and a new row from a silent source starting at 0.
- [x] N3 — The Import path sends `liked`, and says how many flags it changed — done 2026-09-05; the key is always present, never conditional, so a song a backup does not list as liked arrives as an explicit False and overrides what an older import left. Added and removed are counted apart rather than as one number, because overriding means the last backup wins for every song two backups share. On the real files: ViTune contributed 686 likes, then OpenTune added 67 and removed 334, leaving 419. Re-importing the same backup changed nothing, and unliking one song on the phone propagated as a single removal.
- [x] N4 — Library: a Liked column and a Liked filter, both resolved in SQL — done 2026-09-05; a Liked column showing a heart, `Liked` and `Not liked` in the Show drop-down, and a sort key, all as correlated subqueries against `songs` so paging stays correct. Measured on 21980 rows: the filter returns 419 in 0.10s and the sort runs in 0.04s, and it composes with the artist filter, giving 23 liked songs credited to Arijit Singh. Checked in the running application.

## 1.13. Roadmap — batch from FSD 1.8.4

`songs.downloaded` currently means "some evidence once suggested this was downloaded",
which is why 8858 rows carry it on a machine that holds far fewer files. Four sources
raise it: an OpenTune backup's Downloaded collection, the revival seed from the
`downloads` history, the `songs downloaded <- download history` backfill pass, and the
Local Scan `Add to database` button. Only the last one has ever looked at this disk.

1.8.4 settles the meaning: **the file is in the local music library**. So the flag is
raised by exactly one action, `Local Scan -> Add to database`, and it is lowered again
whenever the local index no longer holds the file. A backup describes a phone; it is no
authority at all on what is on this laptop. Consequence worth stating: a download this
app performs does not raise the flag by itself either, because nothing has yet seen the
file where the library lives. The next scan and add does that.

- [x] O1 — Import stops sending `downloaded`, and `upsert_songs` only changes the flag when a payload names it — done 2026-09-08; the key is gone from `_song_payload_from_import`, so a backup's Downloaded collection now only colours the Import grid, and `downloaded` left the `MAX` conflict clause to be settled by the same follow-up UPDATE `liked` uses. The two now share one loop and differ from `in_library`, which still merges. Verified on six cases: an import claiming Downloaded left the flag at 0, a local add raised it, a silent listing left it alone, an explicit False lowered it, and a new row from a silent source started at 0.
- [x] O2 — The two history-driven sources stop raising it: the revival seed and the `songs downloaded <- download history` backfill pass — done 2026-09-08; the revival now seeds every song at 0 instead of consulting `downloads`, and the backfill pass is gone, replaced by a comment saying why there will not be another. A successful download row says a file was written once, which is not the same claim as the file being in the music library now: it can be moved, renamed, deleted or copied to a phone. Both sites keep the reasoning inline so the pass does not get reinstated by someone reading the schema alone.
- [x] O3 — A song with no file in the local index loses the flag, from `init_db` and after every scan, which also repairs the databases that already have it wrong — done 2026-09-08; `clear_stale_downloaded_flags` is one UPDATE against `local_files` by video id, called from `init_db` and from the end of `record_scan`, and it only ever lowers. The asymmetry is the point: raising is the operator pressing `Add to database` on the files the filters match, lowering is arithmetic on what is still there, so a file deleted outside the application, a forgotten folder and an unplugged drive all end the same way. Verified on a built database: a song with a local file kept the flag, one without lost it, a re-run changed nothing, and deleting the local row took the last flag with it.
- [x] O4 — The Library `Downloaded` / `Never downloaded` filters read `songs.downloaded` instead of the download history — done 2026-09-08; both branches became correlated subqueries against `songs`, matching the shape the Liked filter already uses, so the drop-down and the flag finally answer the same question. `Never downloaded` is now labelled `Not downloaded`, because a song fetched last year and since deleted belongs on that side and `never` would be a lie. The Downloads column still counts history rows and is left alone: a song can honestly show two downloads and no flag. Verified on a database where both videos had a successful download row and only one had a file: the filters returned one each.
- [x] O5 — Verify the whole rule end to end on a copy of the real database — done 2026-09-08; on a copy of the live database the repair took 8895 flags down to 3568, which is exactly the set that has a file in `local_files`, leaving songs, likes and credits untouched and running again in 0.70s with nothing left to do. Then the real OpenTune backup, 15691 items of which 5729 claim the Downloaded collection, was imported into that copy and raised no flag at all while still moving 54 likes in and 354 out. Finally the full round trip on three real files: scanning alone flagged nothing, `Add to database` flagged all three, and deleting one file and rescanning lowered that one flag and left the other two.

## Self-check

```
python -m compileall -q yt_aio
python -c "import yt_aio.application.shell"
```
