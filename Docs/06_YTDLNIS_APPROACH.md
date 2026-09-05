# How YTDLnis drives yt-dlp, and what YT AIO should take from it

Source read: `~/Downloads/ytdlnis`, version 1.8.9.1 (2026-06). Almost every yt-dlp
decision in that app lives in one file,
`app/src/main/java/com/deniscerri/ytdl/util/extractors/ytdlp/YTDLPUtil.kt` (1681 lines).
Line numbers below refer to it.

The app builds a yt-dlp argument list and hands it to `youtubedl-android`, which runs
the same yt-dlp Python we run. So every option below is one we can pass verbatim.

---

## 1. The commands it builds

### 1.1 Listing and searching

Every fetch starts from one shared preamble, `applyDefaultOptionsForFetchingData`
(line 63):

```
--skip-download --quiet --ignore-errors --no-warnings
-R 1
--compat-options manifest-filesize-approx
--socket-timeout 5
-P <cache>/tmp
[-4] [--cookies FILE] [--add-header User-Agent:...] [--proxy ...] [--no-check-certificates]
```

`getFromYTDL` (line 126) then adds the listing options:

```
--flat-playlist --lazy-playlist -j          # -J for a single item
--extractor-args youtube:player_client=...;po_token=...
```

Two details matter more than they look.

- **`-R 1`** caps retries at one for a *listing*. A listing that is going to fail
  should fail fast; the default retry count turns one dead entry into a long stall.
- **`--lazy-playlist`** makes yt-dlp emit entries as it walks the playlist instead of
  resolving the whole thing first. Combined with reading stdout line by line, the first
  rows appear almost immediately on a channel with thousands of videos.

It also has first-class support for YouTube's own feed pseudo-URLs (lines 330 to 393),
which are a single argument each: `:ytwatchlater`, `:ytrec`, `:ytfav`, `:ythis`.

### 1.2 Fetching formats for many videos at once

This is the most important thing in the file. `getFormatsForAll` (line 407) does **not**
loop over URLs. It writes every URL to a text file and runs yt-dlp **once**:

```
yt-dlp --print formats -a /cache/urls.txt <shared preamble>
```

One process, one Python start-up, one extractor warm-up, N results streamed back on
stdout in input order. `getFormats` (line 489) is the single-URL variant and uses
`--print "%(formats)j"` plus `--print "%(duration)s"` rather than a full `-J` dump, so
yt-dlp serialises two values instead of a whole info dictionary.

### 1.3 Caching the info JSON

`addWriteInfoJson` (line 678) writes the full info dictionary to a cache file during the
fetch, keyed by a CRC32 hash of the video id:

```
--no-clean-info-json --print-to-file video:%()j <cache>/<hash><timestamp>video.info.json
```

On the next operation for that URL it passes `--load-info-json <file>` (lines 506, 1121)
and yt-dlp does **no network work at all**. A second fetch of a video already seen costs
a file read.

### 1.4 Downloading

`buildYTDLRequest` (line 896) is long, but the shape is:

```
--newline
--no-quiet --no-simulate --print after_move:'%(filepath,_filename)s'
--restrict-filenames --trim-filenames <254 - len(dir)>
-N <concurrent fragments>   --retries N   --fragment-retries N
-r <rate limit>   --buffer-size N --no-resize-buffer   --socket-timeout N
--download-archive <archive file>
[--downloader libaria2c.so]
-f <selector>  -S <sort>  -x  --audio-format <ext>  -P <dir>
--embed-metadata  --parse-metadata ...  --replace-in-metadata ...
```

Three parts of that are worth copying on their own.

**Audio format selection** (line 1150 onward) is a `-f` fallback chain plus a `-S`
sort, not a fixed format string:

```
-f ba/b                       # or ba[format_id$=-drc]/ba/b, ba[language^=xx]/ba/b
-S hasaud,acodec:opus,aext:m4a,+size
```

`-f` says what is acceptable, `-S` says which of the acceptable ones is best. A fixed
`-f bestaudio[ext=m4a]/bestaudio` cannot express "prefer opus, then m4a, smallest first".

**Metadata rewriting** (lines 1073 to 1082, 1244 to 1259) is where a music library is
won or lost:

```
--embed-metadata
--parse-metadata "%(uploader,channel,creator|)l:^(?P<uploader>.*?)(?:(?= - Topic)|$)"
--parse-metadata "%(uploader)s:%(artist)s"
--parse-metadata "%(playlist_uploader,artist,uploader|)s:^(?P<first_artist>.*?)(?:(?=,\s+)|$)"
--replace-in-metadata title "^.*$" "<the title the user chose>"
```

The first of those strips YouTube's ` - Topic` suffix off auto-generated artist channels,
so the file lands tagged `Radiohead` rather than `Radiohead - Topic`. The rest promote
the uploader to the artist field and optionally treat the playlist as the album.

**Duplicate prevention** (line 1135) is a single option:

```
--download-archive <file>
```

yt-dlp records every completed id and refuses to fetch it again, with no database
lookup and no race between "check" and "download".

### 1.5 Long or awkward argument lists

`addConfig` (line 873) writes the extra options into a temporary text file and passes
`--config-locations <file>` instead of appending them as arguments. That sidesteps
argument-length limits and every quoting problem in one move.

---

## 2. What is genuinely better than what we do now

Our listing path is already close: `list_videos` in `utils/video_info_extractor.py`
runs `--flat-playlist -j` and streams stdout line by line, which is the same idea as
their `getFromYTDL`. The gap is elsewhere.

| Area | YT AIO today | YTDLnis | Why theirs wins |
|---|---|---|---|
| Full metadata for N videos | N separate `yt-dlp -J` processes in a thread pool | one process, `-a urls.txt` | N process start-ups become one |
| Repeat fetch of one video | SQLite cache, but yt-dlp still re-runs for full metadata | `--load-info-json` from a hashed cache file | no network at all on the second pass |
| Not re-downloading | our own check against the `downloads` table | `--download-archive` | yt-dlp enforces it; no check-then-act gap |
| Audio format | fixed `-f bestaudio[ext=m4a]/bestaudio` | `-f` chain plus `-S` sort | expresses preference, not just acceptance |
| Tags on the file | `--add-metadata` | `--embed-metadata` plus `--parse-metadata` rules | artist and album come out right |
| Listing timeouts | no timeout or retry caps on the listing | `-R 1`, `--socket-timeout`, `--lazy-playlist` | a bad entry fails fast instead of stalling |
| Long option sets | appended as arguments | `--config-locations` file | no length or quoting limits |
| YouTube bot checks | retry with `--cookies-from-browser` | `player_client` selection and PO tokens | the cookie retry is the older, weaker lever |

The batched metadata fetch is the single biggest win. Our `list_videos` currently opens
one subprocess per video when `fetch_full_metadata` is on. On a 500-video channel that is
500 Python interpreter start-ups.

---

## 3. What to change in our code

Ordered by payoff against effort. Nothing here has been implemented; this section is the
plan the FSD asked for.

### 3.1 Batch the full-metadata fetch (largest win)

**Where:** `utils/video_info_extractor.py`, the `ThreadPoolExecutor` block in
`list_videos` (around line 630) and `fetch_video_metadata`.

Replace the pool with one call. Write the pending URLs to a temporary file and run:

```
yt-dlp -a <urls.txt> --skip-download --ignore-errors --no-warnings \
       --print "%(.{id,title,channel,duration,upload_date,thumbnail,webpage_url})j"
```

Read stdout line by line, one JSON object per video, and feed each into the existing
`log_video_info_batch`. `--print` with a field subset is far cheaper than `-J`, which
serialises every format of every video.

Keep `max_metadata_workers` as a chunk size rather than a thread count: split the URL
file into chunks of that many and run the chunks in sequence, so a cancel is still
responsive and one poisoned URL cannot take down the whole batch.

### 3.2 Add a download archive

**Where:** `utils/download_manager.py`, `build_download_command`.

Add `--download-archive <archive>` with the path from a new config key
`download_archive_path`, defaulting to `./db/downloaded.txt`. Keep our database check as
well: the archive stops the fetch, the database is what the Library and Local Scan tabs
read. Add an `enable_download_archive` boolean so it can be turned off, because an
archive silently skipping a file the operator asked for is surprising the first time.

### 3.3 Fix the tags we write

**Where:** `utils/download_manager.py`, `build_download_command`, the audio branch.

Replace `--add-metadata` with:

```
--embed-metadata
--parse-metadata "%(uploader,channel,creator|)l:^(?P<uploader>.*?)(?:(?= - Topic)|$)"
--parse-metadata "%(uploader)s:%(artist)s"
--parse-metadata "%(playlist_title)s:%(album)s"     # behind a config flag
```

This one also pays for itself inside this project: the Local Scan tab matches a file to
the database by title and artist, and files tagged `Radiohead - Topic` with no album are
exactly the ones that come back as a clash.

### 3.4 Switch audio selection to `-f` plus `-S`

**Where:** `utils/download_manager.py`, the audio branch.

```
-f "ba/b"
-S "hasaud,acodec:<preferred>,aext:<container>,+size"
--extract-audio --audio-format <container>
```

Add `preferred_audio_codec` (opus, aac, mp3, flac, vorbis, alac) to
`build_default_config` and to `SETTING_SUGGESTIONS`, which the Settings tab already
renders as a drop-down without further work.

### 3.5 Harden the listing command

**Where:** `utils/video_info_extractor.py`, the `cmd_parts` list in `list_videos`.

```
--flat-playlist --lazy-playlist -j
--ignore-errors --no-warnings
-R 1 --socket-timeout <config>
--extractor-args youtubetab:approximate_date
```

`--lazy-playlist` and `-R 1` between them are the direct answer to the timeout complaint
recorded in FSD 1.8.1. Add `socket_timeout` to the config, default 15.

### 3.6 Reuse a cached info JSON

**Where:** a new helper beside `run_json_command`.

Write `--print-to-file "%()j" <cache>/<video_id>.info.json` during a full-metadata
fetch, and pass `--load-info-json` when that file exists and is newer than a
configurable age. Their CRC32 hashing exists because Android file names are awkward; the
video id is already a safe file name for us, so use it directly.

### 3.7 Player clients and PO tokens

**Where:** `utils/video_info_extractor.py`, `build_yt_dlp_base_args`.

We already pass `--extractor-args youtube:visitor_data=...`. Extend the same option to
carry a client list and PO tokens, joined with `;` as they do at line 862:

```
--extractor-args "youtube:player_client=default,web_safari,tv;po_token=web.gvs+XXX"
```

Add `youtube_player_clients` and `youtube_po_tokens` as config keys. This is the current
answer to bot checks; our cookie fallback should stay as the second line, not the first.

### 3.8 Download tuning

**Where:** `utils/download_manager.py`, `build_download_command`.

Pass through `-N <concurrent_fragments>`, `--retries`, `--fragment-retries`,
`-r <limit_rate>`, `--restrict-filenames`. All of these are one config key and one line
each, and `-N` alone materially speeds up a large file.

### 3.9 Config file for long option sets

**Where:** `utils/video_info_extractor.py`, `build_yt_dlp_command`.

Once 3.3 and 3.4 land, the argument list is long enough to be worth writing to a
temporary file and passing `--config-locations`. Do this last; it is insurance, not a
speed-up.

---

## 4. What not to copy

- **aria2c as an external downloader.** They ship `libaria2c.so` because Android's
  network stack is what it is. On a desktop, yt-dlp's own downloader with `-N` is fine,
  and an external downloader is another binary to install and another failure mode.
- **Their command-template system.** It exists so a phone user can paste arbitrary
  yt-dlp flags. Our Settings tab with typed fields and suggestions is the better fit for
  a desktop application, and mixing the two would give two places where an option can
  come from.
- **CRC32 hashing of cache file names.** Solves an Android path problem we do not have.
- **NewPipe as an alternative extractor.** A second extraction engine doubles the
  surface area to maintain, and their own changelog opens with a NewPipe bug telling
  users to switch back to yt-dlp.

---

## 5. Suggested order

1. §3.5, the listing hardening. One line list, closes FSD 1.8.1.
2. §3.1, the batched metadata fetch. The big one.
3. §3.3, the metadata rewriting. Improves Local Scan matching as a side effect.
4. §3.4 and §3.8, format sorting and download tuning.
5. §3.2, the download archive.
6. §3.6 and §3.7, info JSON reuse and PO tokens.
7. §3.9, the config file, only if the argument list becomes unwieldy.
