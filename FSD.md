<!-- Functional Specification Document -->
# 1. Project name: YT AIO

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