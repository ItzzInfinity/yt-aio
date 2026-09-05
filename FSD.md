<!-- Functional Specification Document -->
# 1. Project name: YT AIO

## Current state — 2026-09-05 (session 2) — fixed the two regressions reported in 1.6

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

## Self-check

```
python -m compileall -q yt_aio
python -c "import yt_aio.application.shell"
```
