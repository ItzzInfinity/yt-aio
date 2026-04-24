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