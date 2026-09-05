from __future__ import annotations

import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from ... import APP_CHANGELOG, APP_VERSION


def now_string() -> str:
    """Local time, second resolution. Matches the format utils/shared.py writes."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


@contextmanager
def _connect(db_path: str):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
        conn.commit()
    finally:
        conn.close()


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    if column_name in _table_columns(conn, table_name):
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _ensure_index(conn: sqlite3.Connection, name: str, statement: str) -> None:
    conn.execute(statement.replace("{name}", name))


def _batched(values: list[str], batch_size: int = 500) -> Iterable[list[str]]:
    for start in range(0, len(values), batch_size):
        yield values[start:start + batch_size]


def _ensure_source_row(
    conn: sqlite3.Connection,
    *,
    source_key: str,
    source_kind: str,
    source_name: str,
) -> int:
    conn.execute(
        """
        INSERT INTO sources (
            source_key, source_kind, source_name, source_value, source_url, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        ON CONFLICT(source_key) DO UPDATE SET
            source_kind = excluded.source_kind,
            source_name = excluded.source_name,
            updated_at = excluded.updated_at
        """,
        (source_key, source_kind, source_name, source_name, None),
    )
    row = conn.execute(
        "SELECT id FROM sources WHERE source_key = ?",
        (source_key,),
    ).fetchone()
    return int(row["id"])


def _backfill_relations(conn: sqlite3.Connection) -> None:
    video_rows = conn.execute(
        """
        SELECT id, channel_name, playlist_name
        FROM youtube_video_information
        WHERE source_id IS NULL
          AND (playlist_name IS NOT NULL OR channel_name IS NOT NULL)
        """
    ).fetchall()
    for row in video_rows:
        source_kind = "playlist" if row["playlist_name"] else "channel"
        source_name = row["playlist_name"] or row["channel_name"]
        source_key = f"legacy:{source_kind}:{source_name}"
        source_id = _ensure_source_row(
            conn,
            source_key=source_key,
            source_kind=source_kind,
            source_name=source_name,
        )
        conn.execute(
            """
            UPDATE youtube_video_information
            SET source_id = ?, cached_at = COALESCE(cached_at, datetime('now'))
            WHERE id = ?
            """,
            (source_id, row["id"]),
        )

    download_rows = conn.execute(
        """
        SELECT id, source_name, video_id, url
        FROM downloads
        WHERE source_id IS NULL OR video_info_id IS NULL OR video_id IS NULL
        """
    ).fetchall()
    for row in download_rows:
        source_id = None
        if row["source_name"]:
            source_id = _ensure_source_row(
                conn,
                source_key=f"legacy:download:{row['source_name']}",
                source_kind="download",
                source_name=row["source_name"],
            )

        video_info_row = conn.execute(
            """
            SELECT id, video_id, source_id
            FROM youtube_video_information
            WHERE (video_id = ? AND ? IS NOT NULL) OR video_url = ?
            LIMIT 1
            """,
            (row["video_id"], row["video_id"], row["url"]),
        ).fetchone()

        resolved_video_info_id = video_info_row["id"] if video_info_row else None
        resolved_video_id = video_info_row["video_id"] if video_info_row else row["video_id"]
        resolved_source_id = source_id or (video_info_row["source_id"] if video_info_row else None)

        conn.execute(
            """
            UPDATE downloads
            SET source_id = COALESCE(?, source_id),
                video_info_id = COALESCE(?, video_info_id),
                video_id = COALESCE(?, video_id)
            WHERE id = ?
            """,
            (resolved_source_id, resolved_video_info_id, resolved_video_id, row["id"]),
        )


_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_WHITESPACE = re.compile(r"\s+")


def clean_name(value: Any) -> str:
    """Trim a display name and make every run of whitespace one ordinary space.

    Backups carry characters that look like a space and are not. A real ViTune file
    stores "Arijit\u00a0singh" with a non-breaking space, and a name like that can never
    be matched by anyone typing it, which silently empties an artist filter. Python's
    \\s covers the non-breaking and thin spaces as well as the ordinary one.
    """
    return _WHITESPACE.sub(" ", str(value or "")).strip()


def _drop_retired_columns(conn: sqlite3.Connection) -> None:
    """Remove columns the schema no longer has, from a database that predates the change.

    `liked` was here briefly and is not any more: it went out in 1.11 and came back in
    1.12, so a database written in between has to have it added again rather than
    dropped. `_ensure_column` in init_db does that.

    CREATE TABLE IF NOT EXISTS leaves an existing table exactly as it was, so a column
    only ever disappears if something removes it. DROP COLUMN needs SQLite 3.35, released
    in 2021; on anything older the column is left in place, which is harmless because
    nothing reads or writes it any more.
    """
    retired = {"songs": ("play_count",)}
    for table, columns in retired.items():
        if not _table_exists(conn, table):
            continue
        present = _table_columns(conn, table)
        for column in columns:
            if column not in present:
                continue
            try:
                conn.execute(f'ALTER TABLE "{table}" DROP COLUMN "{column}"')
            except sqlite3.OperationalError:
                pass


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def _slug(text: str) -> str:
    """A stable key for a name that has no identifier of its own.

    Accents are folded and everything else collapses to single hyphens, so "Arijit Singh"
    and "arijit  singh" reach the same artist row instead of two.
    """
    folded = unicodedata.normalize("NFKD", clean_name(text))
    ascii_only = "".join(char for char in folded if not unicodedata.combining(char))
    return _SLUG_STRIP.sub("-", ascii_only.casefold()).strip("-")


def artist_id_for(name: str, channel_id: str | None = None) -> str:
    """A real channel id when there is one; otherwise a key derived from the name.

    Most sources hand us an artist name and nothing else: a CSV column, a file tag, a
    channel_name. Refusing those would drop most of the artists we actually have.
    """
    if channel_id:
        return str(channel_id).strip()
    return f"name:{_slug(name)}"


def album_id_for(title: str, browse_id: str | None = None) -> str:
    if browse_id:
        return str(browse_id).strip()
    return f"title:{_slug(title)}"


def playlist_id_for(name: str, list_id: str | None = None) -> str:
    if list_id:
        return str(list_id).strip()
    return f"name:{_slug(name)}"


def _music_backfill_done(conn: sqlite3.Connection) -> bool:
    """The backfill runs once. A songs table with anything in it has already had it.

    Guarding on the row count rather than a flag means a database restored from before
    the music tables existed is still picked up, and a user who deliberately emptied
    songs gets it rebuilt.
    """
    return bool(conn.execute("SELECT 1 FROM songs LIMIT 1").fetchone())


def _backfill_music_tables(conn: sqlite3.Connection) -> None:
    """Revive youtube_video_information under a video-id key (07_MUSIC_SCHEMA_PLAN.md 3).

    Reads and never destroys. youtube_video_information keeps its integer id and the
    video_info_id references from downloads, so nothing that works today stops working.
    """
    if _music_backfill_done(conn):
        return

    rows = conn.execute(
        """
        SELECT video_id, title, channel_name, playlist_name, upload_date,
               duration, thumbnail_url, video_url, cached_at
        FROM youtube_video_information
        WHERE video_id IS NOT NULL AND TRIM(video_id) <> ''
        ORDER BY COALESCE(cached_at, '') ASC
        """
    ).fetchall()
    if not rows:
        return

    stamp = now_string()
    downloaded = {
        str(row[0])
        for row in conn.execute(
            "SELECT DISTINCT video_id FROM downloads WHERE status = 'success' AND video_id IS NOT NULL"
        )
    }

    songs: dict[str, tuple] = {}
    artists: dict[str, str] = {}
    playlists: dict[str, str] = {}
    song_artists: dict[tuple[str, str], int] = {}
    song_playlists: set[tuple[str, str]] = set()

    for row in rows:
        video_id = str(row["video_id"]).strip()
        # Ordered oldest first, so a later, richer row simply replaces the earlier one.
        songs[video_id] = (
            video_id,
            str(row["title"] or ""),
            row["duration"],
            row["thumbnail_url"],
            row["video_url"] or f"https://www.youtube.com/watch?v={video_id}",
            row["upload_date"],
            1 if video_id in downloaded else 0,
            stamp,
            stamp,
        )

        # channel_name is not split on commas. No row in the wild has one, and a channel
        # legitimately named "Smith, Jones & Co" would be torn in half by the guess. The
        # import path supplies a real artist list instead.
        name = clean_name(row["channel_name"])
        if name:
            key = artist_id_for(name)
            artists[key] = name
            song_artists[(video_id, key)] = 0

        playlist_name = clean_name(row["playlist_name"])
        if playlist_name:
            key = playlist_id_for(playlist_name)
            playlists[key] = playlist_name
            song_playlists.add((video_id, key))

    conn.executemany(
        "INSERT OR IGNORE INTO artists (artist_id, name, first_seen) VALUES (?, ?, ?)",
        [(key, name, stamp) for key, name in artists.items()],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO playlists (playlist_id, name, origin, first_seen) VALUES (?, ?, ?, ?)",
        [(key, name, "backfill:youtube_video_information", stamp) for key, name in playlists.items()],
    )
    conn.executemany(
        """
        INSERT OR REPLACE INTO songs
            (video_id, title, duration, thumbnail_url, video_url, upload_date,
             downloaded, first_seen, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        list(songs.values()),
    )
    conn.executemany(
        "INSERT OR IGNORE INTO song_artists (video_id, artist_id, position) VALUES (?, ?, ?)",
        [(video_id, artist, position) for (video_id, artist), position in song_artists.items()],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO song_playlists (video_id, playlist_id) VALUES (?, ?)",
        sorted(song_playlists),
    )


def init_db(db_path: str) -> None:
    with _connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_key TEXT NOT NULL UNIQUE,
                source_kind TEXT,
                source_name TEXT,
                source_value TEXT,
                source_url TEXT,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                url TEXT,
                status TEXT,
                error_message TEXT,
                timestamp TEXT,
                file_path TEXT,
                quality TEXT,
                type TEXT,
                source_name TEXT,
                video_id TEXT,
                video_info_id INTEGER,
                source_id INTEGER,
                FOREIGN KEY(video_info_id) REFERENCES youtube_video_information(id),
                FOREIGN KEY(source_id) REFERENCES sources(id)
            );

            CREATE TABLE IF NOT EXISTS youtube_video_information (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT UNIQUE,
                title TEXT,
                channel_name TEXT,
                playlist_name TEXT,
                upload_date TEXT,
                duration INTEGER,
                thumbnail_url TEXT,
                video_url TEXT,
                source_id INTEGER,
                cached_at TEXT,
                is_full_metadata INTEGER DEFAULT 0,
                FOREIGN KEY(source_id) REFERENCES sources(id)
            );

            CREATE TABLE IF NOT EXISTS local_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL UNIQUE,
                root_path TEXT,
                file_name TEXT,
                extension TEXT,
                size_bytes INTEGER,
                modified_at TEXT,
                title TEXT,
                artist TEXT,
                album TEXT,
                duration INTEGER,
                bitrate INTEGER,
                video_id TEXT,
                tag_source TEXT,
                match_status TEXT,
                match_detail TEXT,
                matched_video_info_id INTEGER,
                first_seen_at TEXT,
                last_seen_at TEXT,
                FOREIGN KEY(matched_video_info_id) REFERENCES youtube_video_information(id)
            );

            CREATE TABLE IF NOT EXISTS settings_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_name TEXT,
                old_value TEXT,
                new_value TEXT,
                timestamp TEXT
            );

            CREATE TABLE IF NOT EXISTS errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_message TEXT,
                timestamp TEXT,
                stack_trace TEXT,
                url TEXT,
                action TEXT,
                user_input TEXT,
                script_version TEXT,
                system_info TEXT
            );

            CREATE TABLE IF NOT EXISTS user_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT,
                timestamp TEXT
            );

            CREATE TABLE IF NOT EXISTS yt_aio_version (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version_number TEXT,
                release_date TEXT,
                changelog TEXT
            );

            -- Music library layer (Docs/07_MUSIC_SCHEMA_PLAN.md). Keyed by the identifier
            -- YouTube already assigned, so nothing has to be renumbered across a merge,
            -- a backup or a re-import. youtube_video_information stays as the raw fetch
            -- cache underneath; these tables are what the library is made of.
            CREATE TABLE IF NOT EXISTS artists (
                artist_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                thumbnail_url TEXT,
                channel_url TEXT,
                first_seen TEXT
            );

            CREATE TABLE IF NOT EXISTS albums (
                album_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                year TEXT,
                thumbnail_url TEXT,
                first_seen TEXT
            );

            CREATE TABLE IF NOT EXISTS playlists (
                playlist_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                origin TEXT,
                first_seen TEXT
            );

            -- `liked` is carried, `play_count` is not (FSD 1.8.3, then 1.12). Both come
            -- from a phone music player and neither can be produced here, but they are
            -- not the same kind of fact. Liked is a decision worth keeping and filtering
            -- on; a play count is a running total that is stale the moment it is read.
            CREATE TABLE IF NOT EXISTS songs (
                video_id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                duration INTEGER,
                thumbnail_url TEXT,
                video_url TEXT,
                upload_date TEXT,
                album_id TEXT,
                liked INTEGER NOT NULL DEFAULT 0,
                in_library INTEGER NOT NULL DEFAULT 0,
                downloaded INTEGER NOT NULL DEFAULT 0,
                bitrate_label TEXT,
                first_seen TEXT,
                last_updated TEXT
            );

            CREATE TABLE IF NOT EXISTS song_artists (
                video_id TEXT NOT NULL,
                artist_id TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (video_id, artist_id)
            );

            CREATE TABLE IF NOT EXISTS song_albums (
                video_id TEXT NOT NULL,
                album_id TEXT NOT NULL,
                position INTEGER,
                PRIMARY KEY (video_id, album_id)
            );

            -- Audio on disk that carries no video id (FSD 1.8.3). It is kept out of
            -- `songs` on purpose. A song there is something with a YouTube identity that
            -- can be looked up, re-fetched and matched; a file with only a file name and
            -- an ID3 tag is none of those. Putting the two in one table would mean every
            -- duplicate check, every artist filter and every "do I already have this"
            -- answer had to step over rows it can never resolve, and a title collision
            -- would read as a match that is not one.
            CREATE TABLE IF NOT EXISTS local_only_tracks (
                file_path TEXT PRIMARY KEY,
                root_path TEXT,
                file_name TEXT,
                title TEXT,
                artist TEXT,
                album TEXT,
                duration INTEGER,
                bitrate INTEGER,
                size_bytes INTEGER,
                modified_at TEXT,
                tag_source TEXT,
                first_seen TEXT,
                last_updated TEXT
            );

            CREATE TABLE IF NOT EXISTS song_playlists (
                video_id TEXT NOT NULL,
                playlist_id TEXT NOT NULL,
                position INTEGER,
                PRIMARY KEY (video_id, playlist_id)
            );
            """
        )

        _ensure_column(conn, "downloads", "video_id", "TEXT")
        _ensure_column(conn, "downloads", "video_info_id", "INTEGER")
        _ensure_column(conn, "downloads", "source_id", "INTEGER")
        _ensure_column(conn, "youtube_video_information", "source_id", "INTEGER")
        _ensure_column(conn, "youtube_video_information", "cached_at", "TEXT")
        _ensure_column(conn, "youtube_video_information", "is_full_metadata", "INTEGER DEFAULT 0")
        # Dropped in 1.11, wanted back in 1.12. A database written in between has no
        # liked column and CREATE TABLE IF NOT EXISTS will not add one.
        _ensure_column(conn, "songs", "liked", "INTEGER NOT NULL DEFAULT 0")

        _ensure_index(
            conn,
            "idx_sources_source_key",
            "CREATE UNIQUE INDEX IF NOT EXISTS {name} ON sources(source_key)",
        )
        _ensure_index(
            conn,
            "idx_video_info_video_id",
            "CREATE UNIQUE INDEX IF NOT EXISTS {name} ON youtube_video_information(video_id)",
        )
        _ensure_index(
            conn,
            "idx_video_info_video_url",
            "CREATE INDEX IF NOT EXISTS {name} ON youtube_video_information(video_url)",
        )
        _ensure_index(
            conn,
            "idx_video_info_source_id",
            "CREATE INDEX IF NOT EXISTS {name} ON youtube_video_information(source_id)",
        )
        _ensure_index(
            conn,
            "idx_downloads_video_id",
            "CREATE INDEX IF NOT EXISTS {name} ON downloads(video_id)",
        )
        _ensure_index(
            conn,
            "idx_downloads_video_info_id",
            "CREATE INDEX IF NOT EXISTS {name} ON downloads(video_info_id)",
        )
        _ensure_index(
            conn,
            "idx_downloads_source_id",
            "CREATE INDEX IF NOT EXISTS {name} ON downloads(source_id)",
        )
        _ensure_index(
            conn,
            "idx_downloads_file_path",
            "CREATE INDEX IF NOT EXISTS {name} ON downloads(file_path)",
        )
        _ensure_index(
            conn,
            "idx_local_files_file_path",
            "CREATE UNIQUE INDEX IF NOT EXISTS {name} ON local_files(file_path)",
        )
        _ensure_index(
            conn,
            "idx_local_files_root_path",
            "CREATE INDEX IF NOT EXISTS {name} ON local_files(root_path)",
        )
        _ensure_index(
            conn,
            "idx_local_files_video_id",
            "CREATE INDEX IF NOT EXISTS {name} ON local_files(video_id)",
        )
        _ensure_index(
            conn,
            "idx_local_files_match_status",
            "CREATE INDEX IF NOT EXISTS {name} ON local_files(match_status)",
        )

        for name, statement in (
            ("idx_artists_name", "CREATE UNIQUE INDEX IF NOT EXISTS {name} ON artists(name COLLATE NOCASE)"),
            ("idx_albums_title", "CREATE INDEX IF NOT EXISTS {name} ON albums(title COLLATE NOCASE)"),
            ("idx_playlists_name", "CREATE INDEX IF NOT EXISTS {name} ON playlists(name COLLATE NOCASE)"),
            ("idx_songs_title", "CREATE INDEX IF NOT EXISTS {name} ON songs(title COLLATE NOCASE)"),
            ("idx_songs_album_id", "CREATE INDEX IF NOT EXISTS {name} ON songs(album_id)"),
            ("idx_song_artists_artist", "CREATE INDEX IF NOT EXISTS {name} ON song_artists(artist_id)"),
            ("idx_song_albums_album", "CREATE INDEX IF NOT EXISTS {name} ON song_albums(album_id)"),
            ("idx_song_playlists_playlist", "CREATE INDEX IF NOT EXISTS {name} ON song_playlists(playlist_id)"),
            ("idx_local_only_title", "CREATE INDEX IF NOT EXISTS {name} ON local_only_tracks(title COLLATE NOCASE)"),
            ("idx_local_only_artist", "CREATE INDEX IF NOT EXISTS {name} ON local_only_tracks(artist COLLATE NOCASE)"),
            ("idx_local_only_root", "CREATE INDEX IF NOT EXISTS {name} ON local_only_tracks(root_path)"),
        ):
            _ensure_index(conn, name, statement)

        _drop_retired_columns(conn)
        _backfill_relations(conn)
        _backfill_music_tables(conn)

        # Drop columns no longer needed
        columns = _table_columns(conn, "youtube_video_information")
        for col in ["view_count", "like_count", "dislike_count", "comment_count"]:
            if col in columns:
                try:
                    conn.execute(f"ALTER TABLE youtube_video_information DROP COLUMN {col}")
                except sqlite3.OperationalError:
                    pass

        existing = conn.execute(
            "SELECT id, changelog FROM yt_aio_version WHERE version_number = ?",
            (APP_VERSION,),
        ).fetchone()
        if not existing:
            conn.execute(
                """
                INSERT INTO yt_aio_version (version_number, release_date, changelog)
                VALUES (?, datetime('now'), ?)
                """,
                (APP_VERSION, APP_CHANGELOG),
            )
        elif existing["changelog"] != APP_CHANGELOG:
            conn.execute(
                """
                UPDATE yt_aio_version
                SET changelog = ?
                WHERE id = ?
                """,
                (APP_CHANGELOG, existing["id"]),
            )



def _split_names(value: Any) -> list[str]:
    """A list stays a list; a comma-separated string becomes one, blanks dropped."""
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        candidates = [str(entry) for entry in value]
    else:
        candidates = str(value).split(",")
    names: list[str] = []
    for candidate in candidates:
        name = clean_name(candidate)
        if name and name not in names:
            names.append(name)
    return names


def upsert_songs(db_path: str, payloads: list[dict[str, Any]]) -> int:
    """Merge songs and their artists, album and playlists (07_MUSIC_SCHEMA_PLAN.md 4).

    A column is only overwritten when the incoming value is not empty, so a thin CSV
    import can never blank a title a full metadata fetch established. Junction rows are
    only touched for the kinds the payload actually mentions: an absent `artists` key
    means "this source knows nothing about artists", which is not the same as "this song
    has no artists", and silently deleting the credits would be the worse reading.

    `liked` is the one field that overrides instead of merging, and only when the payload
    names it. See the comment beside that statement for why it differs from `downloaded`.
    """
    if not payloads:
        return 0

    stamp = now_string()
    written = 0

    with _connect(db_path) as conn:
        for payload in payloads:
            video_id = str(payload.get("video_id") or "").strip()
            if not video_id:
                continue

            album_title = clean_name(payload.get("album"))
            album_key = album_id_for(album_title, payload.get("album_id")) if album_title else None
            if album_key:
                conn.execute(
                    """
                    INSERT INTO albums (album_id, title, year, thumbnail_url, first_seen)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(album_id) DO UPDATE SET
                        title = COALESCE(NULLIF(albums.title, ''), excluded.title),
                        year = COALESCE(NULLIF(albums.year, ''), excluded.year),
                        thumbnail_url = COALESCE(NULLIF(albums.thumbnail_url, ''), excluded.thumbnail_url)
                    """,
                    (album_key, album_title, payload.get("year"), payload.get("album_thumbnail"), stamp),
                )

            conn.execute(
                """
                INSERT INTO songs (
                    video_id, title, duration, thumbnail_url, video_url, upload_date,
                    album_id, liked, in_library, downloaded, bitrate_label,
                    first_seen, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    title = COALESCE(NULLIF(excluded.title, ''), songs.title),
                    duration = COALESCE(excluded.duration, songs.duration),
                    thumbnail_url = COALESCE(NULLIF(excluded.thumbnail_url, ''), songs.thumbnail_url),
                    video_url = COALESCE(NULLIF(excluded.video_url, ''), songs.video_url),
                    upload_date = COALESCE(NULLIF(excluded.upload_date, ''), songs.upload_date),
                    album_id = COALESCE(excluded.album_id, songs.album_id),
                    in_library = MAX(songs.in_library, excluded.in_library),
                    downloaded = MAX(songs.downloaded, excluded.downloaded),
                    bitrate_label = COALESCE(NULLIF(excluded.bitrate_label, ''), songs.bitrate_label),
                    last_updated = excluded.last_updated
                """,
                (
                    video_id,
                    str(payload.get("title") or ""),
                    payload.get("duration"),
                    payload.get("thumbnail_url"),
                    payload.get("video_url") or f"https://www.youtube.com/watch?v={video_id}",
                    payload.get("upload_date"),
                    album_key,
                    1 if payload.get("liked") else 0,
                    1 if payload.get("in_library") else 0,
                    1 if payload.get("downloaded") else 0,
                    payload.get("bitrate_label"),
                    stamp,
                    stamp,
                ),
            )

            # `liked` overrides rather than merges, and only when the payload names it.
            # A backup is the sole authority on what is liked, so unliking a song on the
            # phone has to come back through here as a 0; MAX, which `downloaded` uses,
            # would make the flag one-way and unliking impossible. The insert above sets
            # the value for a brand new row and this statement settles an existing one.
            # A source that says nothing about likes leaves the stored flag alone.
            if "liked" in payload:
                conn.execute(
                    "UPDATE songs SET liked = ? WHERE video_id = ?",
                    (1 if payload["liked"] else 0, video_id),
                )

            if album_key:
                conn.execute(
                    "INSERT OR IGNORE INTO song_albums (video_id, album_id, position) VALUES (?, ?, ?)",
                    (video_id, album_key, payload.get("track_number")),
                )

            if "artists" in payload:
                for position, name in enumerate(_split_names(payload.get("artists"))):
                    key = artist_id_for(name)
                    conn.execute(
                        """
                        INSERT INTO artists (artist_id, name, first_seen) VALUES (?, ?, ?)
                        ON CONFLICT(artist_id) DO UPDATE SET
                            name = COALESCE(NULLIF(artists.name, ''), excluded.name)
                        """,
                        (key, name, stamp),
                    )
                    conn.execute(
                        """
                        INSERT INTO song_artists (video_id, artist_id, position) VALUES (?, ?, ?)
                        ON CONFLICT(video_id, artist_id) DO UPDATE SET position = excluded.position
                        """,
                        (video_id, key, position),
                    )

            if "playlists" in payload:
                for name in _split_names(payload.get("playlists")):
                    key = playlist_id_for(name)
                    conn.execute(
                        """
                        INSERT INTO playlists (playlist_id, name, origin, first_seen) VALUES (?, ?, ?, ?)
                        ON CONFLICT(playlist_id) DO UPDATE SET
                            name = COALESCE(NULLIF(playlists.name, ''), excluded.name)
                        """,
                        (key, name, payload.get("origin"), stamp),
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO song_playlists (video_id, playlist_id) VALUES (?, ?)",
                        (video_id, key),
                    )

            written += 1

    return written


def upsert_source(db_path: str, payload: dict[str, Any]) -> int:
    init_db(db_path)
    source_key = payload["source_key"]
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sources (
                source_key, source_kind, source_name, source_value, source_url, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_key) DO UPDATE SET
                source_kind = excluded.source_kind,
                source_name = excluded.source_name,
                source_value = excluded.source_value,
                source_url = excluded.source_url,
                updated_at = excluded.updated_at
            """,
            (
                source_key,
                payload.get("source_kind"),
                payload.get("source_name"),
                payload.get("source_value"),
                payload.get("source_url"),
                payload.get("created_at"),
                payload.get("updated_at"),
            ),
        )
        row = conn.execute(
            "SELECT id FROM sources WHERE source_key = ?",
            (source_key,),
        ).fetchone()
        return int(row["id"])


def get_cached_videos(db_path: str, video_ids: list[str]) -> dict[str, dict[str, Any]]:
    init_db(db_path)
    if not video_ids:
        return {}

    cached: dict[str, dict[str, Any]] = {}
    with _connect(db_path) as conn:
        for batch in _batched(video_ids):
            placeholders = ", ".join("?" for _ in batch)
            rows = conn.execute(
                f"""
                SELECT *
                FROM youtube_video_information
                WHERE video_id IN ({placeholders})
                """,
                batch,
            ).fetchall()
            for row in rows:
                cached[row["video_id"]] = _row_to_dict(row)
    return cached


def get_cached_video_by_url(db_path: str, url: str) -> dict[str, Any] | None:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM youtube_video_information
            WHERE video_url = ?
            LIMIT 1
            """,
            (url,),
        ).fetchone()
        return _row_to_dict(row) if row else None


def log_download(db_path: str, payload: dict[str, Any]) -> None:
    init_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO downloads (
                title, url, status, error_message, timestamp, file_path, quality, type,
                source_name, video_id, video_info_id, source_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("title"),
                payload.get("url"),
                payload.get("status"),
                payload.get("error_message"),
                payload.get("timestamp"),
                payload.get("file_path"),
                payload.get("quality"),
                payload.get("type"),
                payload.get("source_name"),
                payload.get("video_id"),
                payload.get("video_info_id"),
                payload.get("source_id"),
            ),
        )


def _song_payload_from_video_info(payload: dict[str, Any]) -> dict[str, Any]:
    """Turn one youtube_video_information payload into an upsert_songs payload.

    The listing knows one uploader and, for a playlist source, one playlist name. Those
    keys are only included when there is something to say, because upsert_songs treats an
    absent key as "this source knows nothing here" and leaves the stored rows alone.
    """
    song: dict[str, Any] = {
        "video_id": payload.get("video_id"),
        "title": payload.get("title") or "",
        "duration": payload.get("duration"),
        "thumbnail_url": payload.get("thumbnail_url"),
        "video_url": payload.get("video_url"),
        "upload_date": payload.get("upload_date"),
    }
    channel = str(payload.get("channel_name") or "").strip()
    if channel:
        song["artists"] = [channel]
    playlist = str(payload.get("playlist_name") or "").strip()
    if playlist:
        song["playlists"] = [playlist]
        song["origin"] = "listing"
    return song



def log_video_info(db_path: str, payload: dict[str, Any]) -> int | None:
    init_db(db_path)
    video_id = payload.get("video_id")
    if not video_id:
        return None

    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO youtube_video_information (
                video_id, title, channel_name, playlist_name, upload_date, duration,
                thumbnail_url, video_url, source_id, cached_at, is_full_metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                title = excluded.title,
                channel_name = excluded.channel_name,
                playlist_name = excluded.playlist_name,
                upload_date = excluded.upload_date,
                duration = excluded.duration,
                thumbnail_url = excluded.thumbnail_url,
                video_url = excluded.video_url,
                source_id = COALESCE(excluded.source_id, youtube_video_information.source_id),
                cached_at = excluded.cached_at,
                is_full_metadata = excluded.is_full_metadata
            """,
            (
                video_id,
                payload.get("title"),
                payload.get("channel_name"),
                payload.get("playlist_name"),
                payload.get("upload_date"),
                payload.get("duration"),
                payload.get("thumbnail_url"),
                payload.get("video_url"),
                payload.get("source_id"),
                payload.get("cached_at"),
                payload.get("is_full_metadata", 0),
            ),
        )
        row = conn.execute(
            "SELECT id FROM youtube_video_information WHERE video_id = ?",
            (video_id,),
        ).fetchone()
        info_id = int(row["id"]) if row else None

    # Outside the transaction above: the music tables are a separate write, and a failure
    # there must not lose the cache row that already succeeded.
    upsert_songs(db_path, [_song_payload_from_video_info(payload)])
    return info_id


def log_video_info_batch(db_path: str, payloads: list[dict[str, Any]]) -> list[int | None]:
    init_db(db_path)
    if not payloads:
        return []

    ids: list[int | None] = []
    with _connect(db_path) as conn:
        for payload in payloads:
            video_id = payload.get("video_id")
            if not video_id:
                ids.append(None)
                continue

            conn.execute(
                """
                INSERT INTO youtube_video_information (
                    video_id, title, channel_name, playlist_name, upload_date, duration,
                    thumbnail_url, video_url, source_id, cached_at, is_full_metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    title = excluded.title,
                    channel_name = excluded.channel_name,
                    playlist_name = excluded.playlist_name,
                    upload_date = excluded.upload_date,
                    duration = excluded.duration,
                    thumbnail_url = excluded.thumbnail_url,
                    video_url = excluded.video_url,
                    source_id = COALESCE(excluded.source_id, youtube_video_information.source_id),
                    cached_at = excluded.cached_at,
                    is_full_metadata = excluded.is_full_metadata
                """,
                (
                    video_id,
                    payload.get("title"),
                    payload.get("channel_name"),
                    payload.get("playlist_name"),
                    payload.get("upload_date"),
                    payload.get("duration"),
                    payload.get("thumbnail_url"),
                    payload.get("video_url"),
                    payload.get("source_id"),
                    payload.get("cached_at"),
                    payload.get("is_full_metadata", 0),
                ),
            )
            row = conn.execute(
                "SELECT id FROM youtube_video_information WHERE video_id = ?",
                (video_id,),
            ).fetchone()
            ids.append(int(row["id"]) if row else None)

    # One call for the whole batch, outside the cache transaction for the same reason as
    # in log_video_info: a music-table failure must not cost the cache rows.
    upsert_songs(db_path, [_song_payload_from_video_info(payload) for payload in payloads])
    return ids


def log_error(db_path: str, payload: dict[str, Any]) -> None:
    init_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO errors (
                error_message, timestamp, stack_trace, url, action, user_input, script_version, system_info
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("error_message"),
                payload.get("timestamp"),
                payload.get("stack_trace"),
                payload.get("url"),
                payload.get("action"),
                payload.get("user_input"),
                payload.get("script_version", APP_VERSION),
                payload.get("system_info"),
            ),
        )


def log_setting_change(
    db_path: str,
    setting_name: str,
    old_value: str | None,
    new_value: str | None,
    timestamp: str,
) -> None:
    init_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO settings_changes (setting_name, old_value, new_value, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (setting_name, old_value, new_value, timestamp),
        )


def log_user_action(db_path: str, action: str, timestamp: str) -> None:
    init_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO user_actions (action, timestamp) VALUES (?, ?)",
            (action, timestamp),
        )
