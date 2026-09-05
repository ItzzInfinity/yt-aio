# Giving YT AIO an OpenTune-grade music schema

The FSD asks for a database that answers questions about songs and artists the way the
OpenTune backup does, and for the current data to be revived under a video-id primary
key. This is the step-by-step plan: what tables to create, how they relate, how rows get
in, how they come out, and what the UI does with them.

Read `Docs/song_db_erd.html` for the OpenTune schema this borrows from, and
`features/importer/opentune.py` for the reader that already understands it.

---

## 1. What is wrong with the schema we have

Two tables carry everything today.

| Table | Key | Holds |
|---|---|---|
| `youtube_video_information` | `id` INTEGER, with `video_id` merely UNIQUE | one flat row per video: title, channel name, playlist name, duration, thumbnail |
| `downloads` | `id` INTEGER | one row per download attempt, pointing back by `video_info_id` |

Three problems follow from that shape.

**An artist is a string, not a thing.** `channel_name` is one text field. A song with
three credited artists gets the first one and loses the rest. "Show me everything by this
artist" is a `LIKE` over free text, which matches `Arijit Singh` and misses
`Arijit Singh, Shreya Ghoshal`.

**A song belongs to one playlist.** `playlist_name` is a single column, so the second
playlist a song appears in overwrites the first. OpenTune models this as a junction table
precisely because the relationship is many-to-many.

**The natural key is not the key.** `video_id` is unique but the primary key is an
autoincrementing integer, so every other table refers to a video by an integer that means
nothing outside this file. A backup, a merge or a re-import has to renumber. YouTube has
already assigned a stable 11-character identifier; that is the key.

---

## 2. The tables to create

Six new tables. Nothing existing is dropped: `youtube_video_information` stays as the
raw yt-dlp fetch cache, `downloads` keeps its history, and `local_files` keeps the Local
Scan results. The music tables are the library layer above them.

### 2.1 `songs` — the spine

```sql
CREATE TABLE IF NOT EXISTS songs (
    video_id        TEXT PRIMARY KEY,          -- the natural key, at last
    title           TEXT NOT NULL DEFAULT '',
    duration        INTEGER,                   -- seconds
    thumbnail_url   TEXT,
    video_url       TEXT,
    upload_date     TEXT,                      -- YYYYMMDD or YYYY, as the source gave it
    album_id        TEXT REFERENCES albums(album_id) ON DELETE SET NULL,
    liked           INTEGER NOT NULL DEFAULT 0,
    in_library      INTEGER NOT NULL DEFAULT 0,
    downloaded      INTEGER NOT NULL DEFAULT 0,
    play_count      INTEGER NOT NULL DEFAULT 0,
    bitrate_label   TEXT,                      -- "129k mp4a", as cached by the source app
    first_seen      TEXT,
    last_updated    TEXT
);
```

`album_id` is denormalised onto the song even though `song_albums` exists, exactly as
OpenTune denormalises `albumName` onto its `song` table. A song has one album in
practice, and the junction covers the rare compilation case.

### 2.2 `artists` and `song_artists`

```sql
CREATE TABLE IF NOT EXISTS artists (
    artist_id       TEXT PRIMARY KEY,          -- YouTube channel id when known, else "name:<slug>"
    name            TEXT NOT NULL,
    thumbnail_url   TEXT,
    channel_url     TEXT,
    first_seen      TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_artists_name ON artists(name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS song_artists (
    video_id        TEXT NOT NULL REFERENCES songs(video_id) ON DELETE CASCADE,
    artist_id       TEXT NOT NULL REFERENCES artists(artist_id) ON DELETE CASCADE,
    position        INTEGER NOT NULL DEFAULT 0,   -- credit order: 0 is the lead artist
    PRIMARY KEY (video_id, artist_id)
);
CREATE INDEX IF NOT EXISTS idx_song_artists_artist ON song_artists(artist_id);
```

The synthetic `name:<slug>` id matters. Most of our sources give an artist name and no
channel id: a CSV, a file tag, a `channel_name` column. Refusing to record those would
throw away most of the artists we have. Slugging the lower-cased name gives a stable key
that merges duplicates by name, and a real channel id supersedes it when one arrives.

### 2.3 `albums` and `song_albums`

```sql
CREATE TABLE IF NOT EXISTS albums (
    album_id        TEXT PRIMARY KEY,          -- browse id when known, else "title:<slug>"
    title           TEXT NOT NULL,
    year            TEXT,
    thumbnail_url   TEXT,
    first_seen      TEXT
);

CREATE TABLE IF NOT EXISTS song_albums (
    video_id        TEXT NOT NULL REFERENCES songs(video_id) ON DELETE CASCADE,
    album_id        TEXT NOT NULL REFERENCES albums(album_id) ON DELETE CASCADE,
    position        INTEGER,                   -- track number where the source knows it
    PRIMARY KEY (video_id, album_id)
);
```

### 2.4 `playlists` and `song_playlists`

```sql
CREATE TABLE IF NOT EXISTS playlists (
    playlist_id     TEXT PRIMARY KEY,          -- YouTube list id when known, else "name:<slug>"
    name            TEXT NOT NULL,
    origin          TEXT,                      -- which import or listing produced it
    first_seen      TEXT
);

CREATE TABLE IF NOT EXISTS song_playlists (
    video_id        TEXT NOT NULL REFERENCES songs(video_id) ON DELETE CASCADE,
    playlist_id     TEXT NOT NULL REFERENCES playlists(playlist_id) ON DELETE CASCADE,
    position        INTEGER,
    PRIMARY KEY (video_id, playlist_id)
);
CREATE INDEX IF NOT EXISTS idx_song_playlists_playlist ON song_playlists(playlist_id);
```

### 2.5 The relationship map

```
artists ──< song_artists >── songs ──< song_playlists >── playlists
                               │  │
                               │  └──< song_albums >── albums
                               │
                               ├──── album_id ─────────> albums     (denormalised, one album)
                               ├──── video_id ─────────> youtube_video_information.video_id
                               ├──── video_id ─────────> downloads.video_id
                               └──── video_id ─────────> local_files.video_id
```

The last three are joins by value, not declared foreign keys. `songs` is the library and
the other three are logs of what happened to a video; a song must be allowed to exist
with no download and a download must survive its song being deleted from the library.

---

## 3. Migration and the video-id revival

`init_db` already grows the schema in place with `CREATE TABLE IF NOT EXISTS` and an
`_ensure_column` helper, so the new tables slot in beside the old ones with no separate
migration step. What needs writing is the one-time backfill.

1. **Create the tables.** Add the statements above to `init_db`. Existing databases gain
   them empty on the next start; nothing is rewritten.
2. **Backfill `songs` from `youtube_video_information`.** One row per distinct
   `video_id`, taking the newest by `cached_at` where the id appears twice.
3. **Backfill `artists` from `channel_name`.** Every distinct non-empty `channel_name`
   becomes an artist under a `name:<slug>` id, with a `song_artists` row at position 0.
   A comma-separated `channel_name` is split, because the CSV imports produced those.
4. **Backfill `playlists` from `playlist_name`** and from `sources` where the source kind
   is `playlist`, then link them.
5. **Mark `downloaded`.** Set `songs.downloaded = 1` where a `downloads` row for that
   video id has status `success`.
6. **Record it.** Insert a `yt_aio_version` row so a second run can see the backfill has
   already happened, and guard the whole step on a `songs` count of zero so it is
   idempotent.

The backfill reads and never destroys: `youtube_video_information` keeps its integer id
and its `video_info_id` references from `downloads`, so nothing that works today stops
working. `songs.video_id` is the key everything *new* is written against.

---

## 4. Insertion

One entry point, mirroring `log_video_info_batch`:

```python
def upsert_songs(db_path: str, payloads: list[dict[str, Any]]) -> int
```

Each payload carries the song fields plus `artists: list[str]`, `album: str | None` and
`playlists: list[str]`. The function, inside a single transaction:

1. Upserts each artist, album and playlist by its resolved id, keeping the first
   `first_seen` and refreshing the name only when the stored one is empty.
2. Upserts the song with `ON CONFLICT(video_id) DO UPDATE`, and — this is the important
   part — **only overwrites a column when the incoming value is not empty**:
   `title = COALESCE(NULLIF(excluded.title, ''), songs.title)`. A thin CSV import must
   never blank a title a full metadata fetch already established.
3. Replaces that song's junction rows for the kinds present in the payload. Absent means
   "this source knows nothing about playlists", which is different from "this song is in
   no playlist", so an absent key leaves the existing rows alone.
4. Takes the maximum of the stored and incoming `play_count`, and ORs the three flags.

Callers:

| Caller | Where | What it supplies |
|---|---|---|
| Import tab merge | `features/importer/panel.py` | everything an `ImportedItem` has: artists, album, playlists, play count, collections |
| Listing and metadata fetch | `utils/video_info_extractor.py`, beside `log_video_info` | title, duration, thumbnail, upload date, uploader as a single artist |
| Local Scan | `features/local_scan/panel.py` | title and artist read from the file tags, for files that matched a video id |

### 4.1 Id resolution

```python
def artist_id_for(name: str, channel_id: str | None) -> str
```

Returns `channel_id` when one is given, otherwise `"name:" + slug(name)` where `slug`
lower-cases, strips accents and collapses everything that is not a letter or digit to a
single hyphen. `Arijit Singh` and `arijit  singh` therefore land on one row. Albums and
playlists use the same rule with a `title:` and `name:` prefix.

---

## 5. Retrieval

Five queries in `db/queries.py` cover what the UI needs. Every one of them is paged in
SQL, because the Library tab already refuses to load its table whole and the music tables
will be larger, not smaller.

```python
fetch_songs(db_path, *, search, artist, album, playlist, collection,
            duration_min, duration_max, sort_key, descending, limit, offset)
fetch_song_detail(db_path, video_id)      # one song with every artist, album, playlist
fetch_artists(db_path, *, search, limit)  # name, song count, total duration
fetch_albums(db_path, *, artist, limit)
fetch_playlists(db_path, limit)
```

`fetch_songs` is the one that earns the schema. Filtering by artist becomes an
`EXISTS (SELECT 1 FROM song_artists ...)` against an indexed key rather than a `LIKE`
over a free-text column, so it is both correct for multi-artist songs and fast.

The artist column shown in a row is assembled with
`GROUP_CONCAT(a.name, ', ') ORDER BY sa.position`, so the grid shows every credited
artist in the order the source credited them, and the lead artist is still first.

---

## 6. Display

**Library tab.** Three new columns — Artists, Album, Playlists — and three new filters
beside the existing search, source and status ones. The artist and album filters are
editable drop-downs filled from `fetch_artists` and `fetch_albums`, matching the pattern
the duration and channel filters already use. Every new column sorts in SQL.

**Detail pane.** Selecting a song shows the full credit list, the album with its year,
every playlist it belongs to, the play count carried over from the source app, and the
download and local-file rows for that video id. This is the "all the info about the songs
and the artists" the FSD asks for, in one place.

**Import tab.** Unchanged on screen. Its merge path writes through `upsert_songs`
instead of `import_video_rows`, so the artists, album and playlists that
`features/importer/opentune.py` already extracts stop being flattened into one text
column on the way in.

---

## 7. Order of work

Each step leaves the application running.

1. `C2` — the tables and their indexes in `init_db`.
2. `C3` — the backfill, guarded and idempotent.
3. `C4` — `upsert_songs` and the Import tab writing through it.
4. `C5` — `fetch_songs` and the Library columns, filters and detail pane.

Steps 1 and 2 change no behaviour on screen, which is the point: the data is in place and
correct before anything reads it.

---

## 8. What is deliberately not copied from OpenTune

- **`related_song_map`.** It is the recommendation graph and the largest table in a
  backup. We do not generate recommendations, and `features/importer/opentune.py`
  already skips it on the way in for the same reason.
- **`search_history` and `queue`.** They describe a music player. This is a downloader.
- **`lyrics`.** Worth having one day, but it needs a lyrics source, which is a feature of
  its own rather than a column.
- **`format` as a table.** The one useful field is the cached bitrate, which lands on
  `songs.bitrate_label`. A whole table for one string is not worth the join.
