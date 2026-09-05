"""Read and delete access to yt_aio.db.

Owns:   every query the viewing tabs run.
Reads:  sources, downloads, youtube_video_information, errors, user_actions,
        settings_changes.
Writes: deletes rows the operator selected; imports rows a backup file supplied.
Runs:   nothing.

database_manager.py owns the schema and the write path the downloader uses. This module
owns the read path, so a viewing tab never writes its own SQL.

Table and column names are never taken from user input. They come only from the specs
below, which is what keeps the string-built SQL safe.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from .database_manager import _batched, _connect, _row_to_dict, _table_columns, init_db

MAX_PAGE_SIZE = 2000


@dataclass(frozen=True)
class ViewSpec:
    """One read-only grid over one table."""

    table: str
    columns: list[str]
    headers: list[str]
    search_columns: list[str]
    order_by: str
    detail_columns: list[str] = field(default_factory=list)


LOG_VIEWS: dict[str, ViewSpec] = {
    "Download history": ViewSpec(
        table="downloads",
        columns=["id", "timestamp", "status", "type", "title", "quality", "source_name", "file_path", "url", "error_message"],
        headers=["ID", "When", "Status", "Kind", "Title", "Quality", "Source", "File", "URL", "Error"],
        search_columns=["title", "url", "status", "source_name", "video_id", "file_path"],
        order_by="timestamp DESC, id DESC",
        detail_columns=["title", "url", "file_path", "error_message"],
    ),
    "Errors": ViewSpec(
        table="errors",
        columns=["id", "timestamp", "action", "error_message", "url", "script_version", "system_info", "user_input", "stack_trace"],
        headers=["ID", "When", "Action", "Message", "URL", "Version", "System", "Input", "Stack trace"],
        search_columns=["error_message", "action", "url", "user_input", "stack_trace"],
        order_by="timestamp DESC, id DESC",
        detail_columns=["error_message", "stack_trace", "url", "user_input"],
    ),
    "User actions": ViewSpec(
        table="user_actions",
        columns=["id", "timestamp", "action"],
        headers=["ID", "When", "Action"],
        search_columns=["action"],
        order_by="timestamp DESC, id DESC",
    ),
    "Settings changes": ViewSpec(
        table="settings_changes",
        columns=["id", "timestamp", "setting_name", "old_value", "new_value"],
        headers=["ID", "When", "Setting", "Old value", "New value"],
        search_columns=["setting_name", "old_value", "new_value"],
        order_by="timestamp DESC, id DESC",
    ),
    "Version history": ViewSpec(
        table="yt_aio_version",
        columns=["id", "release_date", "version_number", "changelog"],
        headers=["ID", "Released", "Version", "Changelog"],
        search_columns=["version_number", "changelog"],
        order_by="id DESC",
    ),
}


def _available_columns(conn: sqlite3.Connection, spec: ViewSpec) -> list[str]:
    """Only ask for columns this database actually has.

    An older database is missing columns a newer build knows about. Reading with a
    fixed list would fail the whole view; reading the intersection shows what exists.
    """
    present = _table_columns(conn, spec.table)
    return [name for name in spec.columns if name in present]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def _search_clause(spec: ViewSpec, present: set[str], search: str) -> tuple[str, list[Any]]:
    columns = [name for name in spec.search_columns if name in present]
    if not search.strip() or not columns:
        return "", []
    needle = f"%{search.strip()}%"
    clause = " OR ".join(f"COALESCE({name}, '') LIKE ?" for name in columns)
    return f"WHERE ({clause})", [needle] * len(columns)


def fetch_view(
    db_path: str,
    view_name: str,
    *,
    search: str = "",
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[str], list[dict[str, Any]], int]:
    """Return (columns, rows, total matching rows) for one log view.

    A missing table is normal on a fresh database: it returns no rows, not an error.
    """
    spec = LOG_VIEWS[view_name]
    limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    offset = max(0, int(offset))

    init_db(db_path)
    with _connect(db_path) as conn:
        if not _table_exists(conn, spec.table):
            return [], [], 0

        present = _table_columns(conn, spec.table)
        columns = _available_columns(conn, spec)
        if not columns:
            return [], [], 0

        where, params = _search_clause(spec, present, search)
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM {spec.table} {where}", params
        ).fetchone()["n"]
        rows = conn.execute(
            f"SELECT {', '.join(columns)} FROM {spec.table} {where} "
            f"ORDER BY {spec.order_by} LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return columns, [_row_to_dict(row) for row in rows], int(total)


def fetch_sources(db_path: str) -> list[dict[str, Any]]:
    init_db(db_path)
    with _connect(db_path) as conn:
        if not _table_exists(conn, "sources"):
            return []
        rows = conn.execute(
            "SELECT id, source_name, source_kind, source_value FROM sources ORDER BY COALESCE(source_name, source_value)"
        ).fetchall()
        return [_row_to_dict(row) for row in rows]


# Column heading -> the SQL that orders by it. The grid may only name a key from this
# map, which is what keeps an ORDER BY clause out of reach of anything typed in the UI.
LIBRARY_SORTS: dict[str, str] = {
    "video_id": "COALESCE(v.video_id, '')",
    "title": "COALESCE(v.title, '') COLLATE NOCASE",
    "channel_name": "COALESCE(v.channel_name, v.playlist_name, '') COLLATE NOCASE",
    "duration": "COALESCE(v.duration, -1)",
    "upload_date": "COALESCE(v.upload_date, '')",
    "cached_at": "COALESCE(v.cached_at, '')",
    "is_full_metadata": "COALESCE(v.is_full_metadata, 0)",
    "download_count": "download_count",
    # Sorted by the lead credit, the album, and the first playlist. A row shows several
    # values in these columns but can only sort by one, and the lead artist is the one an
    # operator means when they say "sort by artist".
    "artists": (
        "COALESCE((SELECT a.name FROM song_artists sa JOIN artists a ON a.artist_id = sa.artist_id "
        "WHERE sa.video_id = v.video_id ORDER BY sa.position LIMIT 1), '') COLLATE NOCASE"
    ),
    "album": (
        "COALESCE((SELECT al.title FROM songs s2 JOIN albums al ON al.album_id = s2.album_id "
        "WHERE s2.video_id = v.video_id), '') COLLATE NOCASE"
    ),
    "playlists": (
        "COALESCE((SELECT pl.name FROM song_playlists sp JOIN playlists pl ON pl.playlist_id = sp.playlist_id "
        "WHERE sp.video_id = v.video_id LIMIT 1), '') COLLATE NOCASE"
    ),
}
DEFAULT_LIBRARY_SORT = "cached_at"


def _order_clause(sort_key: str, descending: bool) -> str:
    expression = LIBRARY_SORTS.get(sort_key) or LIBRARY_SORTS[DEFAULT_LIBRARY_SORT]
    direction = "DESC" if descending else "ASC"
    # v.id breaks ties so paging stays stable when the sorted values are equal.
    return f"{expression} {direction}, v.id {direction}"


def _library_filters(
    search: str,
    source_id: int | None,
    completeness: str,
    channel: str = "",
    min_duration: int | None = None,
    max_duration: int | None = None,
    artist: str = "",
    album: str = "",
    playlist: str = "",
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if search.strip():
        needle = f"%{search.strip()}%"
        clauses.append(
            "(COALESCE(v.title, '') LIKE ? OR COALESCE(v.video_id, '') LIKE ? "
            "OR COALESCE(v.channel_name, '') LIKE ? OR COALESCE(v.playlist_name, '') LIKE ? "
            "OR EXISTS (SELECT 1 FROM song_artists sa JOIN artists a ON a.artist_id = sa.artist_id "
            "WHERE sa.video_id = v.video_id AND a.name LIKE ?))"
        )
        params.extend([needle] * 5)

    if channel.strip():
        # Substring rather than equality: the drop-down offers exact names, but an
        # operator who types half a name should still get the rows.
        needle = f"%{channel.strip()}%"
        clauses.append("(COALESCE(v.channel_name, '') LIKE ? OR COALESCE(v.playlist_name, '') LIKE ?)")
        params.extend([needle] * 2)

    # A row with no duration is excluded by any duration filter. It cannot be shown to
    # satisfy a range when nothing is known about its length.
    if min_duration:
        clauses.append("v.duration IS NOT NULL AND v.duration >= ?")
        params.append(int(min_duration))
    if max_duration:
        clauses.append("v.duration IS NOT NULL AND v.duration <= ?")
        params.append(int(max_duration))

    # The music tables are reached by video_id, not by the cache row's integer id, which
    # is the whole point of the new schema: an EXISTS over an indexed key rather than a
    # LIKE over one free-text column, so a song credited to three artists matches all
    # three (Docs/07_MUSIC_SCHEMA_PLAN.md).
    if artist.strip():
        clauses.append(
            "EXISTS (SELECT 1 FROM song_artists sa JOIN artists a ON a.artist_id = sa.artist_id "
            "WHERE sa.video_id = v.video_id AND a.name LIKE ?)"
        )
        params.append(f"%{artist.strip()}%")

    if album.strip():
        clauses.append(
            "EXISTS (SELECT 1 FROM songs s2 JOIN albums al ON al.album_id = s2.album_id "
            "WHERE s2.video_id = v.video_id AND al.title LIKE ?)"
        )
        params.append(f"%{album.strip()}%")

    if playlist.strip():
        clauses.append(
            "EXISTS (SELECT 1 FROM song_playlists sp JOIN playlists pl ON pl.playlist_id = sp.playlist_id "
            "WHERE sp.video_id = v.video_id AND pl.name LIKE ?)"
        )
        params.append(f"%{playlist.strip()}%")

    if source_id is not None:
        clauses.append("v.source_id = ?")
        params.append(int(source_id))

    if completeness == "full":
        clauses.append("COALESCE(v.is_full_metadata, 0) = 1")
    elif completeness == "partial":
        clauses.append("COALESCE(v.is_full_metadata, 0) = 0")
    elif completeness == "downloaded":
        clauses.append("EXISTS (SELECT 1 FROM downloads d WHERE d.video_info_id = v.id AND d.status = 'success')")
    elif completeness == "never downloaded":
        clauses.append("NOT EXISTS (SELECT 1 FROM downloads d WHERE d.video_info_id = v.id AND d.status = 'success')")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def fetch_channels(db_path: str, limit: int = 2000) -> list[str]:
    """Every distinct channel or playlist name in the cache, for the filter drop-down."""
    init_db(db_path)
    with _connect(db_path) as conn:
        if not _table_exists(conn, "youtube_video_information"):
            return []
        rows = conn.execute(
            """
            SELECT DISTINCT name FROM (
                SELECT channel_name AS name FROM youtube_video_information
                UNION
                SELECT playlist_name AS name FROM youtube_video_information
            )
            WHERE name IS NOT NULL AND name <> ''
            ORDER BY name COLLATE NOCASE
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [str(row["name"]) for row in rows]


def _attach_music_detail(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    """Fill in artists, album and playlists for the page that was just read.

    Three small queries against the page's video ids, not a join in the main statement.
    SQLite here is 3.37, which has no ORDER BY inside GROUP_CONCAT, and the credit order
    matters: the lead artist has to come first. Assembling in Python makes that order a
    guarantee rather than an implementation detail.
    """
    video_ids = [str(row.get("video_id") or "") for row in rows if row.get("video_id")]
    if not video_ids:
        return

    artists: dict[str, list[tuple[int, str]]] = {}
    albums: dict[str, str] = {}
    playlists: dict[str, list[str]] = {}

    for batch in _batched(video_ids):
        marks = ", ".join("?" for _ in batch)
        for row in conn.execute(
            f"""
            SELECT sa.video_id, sa.position, a.name
            FROM song_artists sa JOIN artists a ON a.artist_id = sa.artist_id
            WHERE sa.video_id IN ({marks})
            """,
            batch,
        ):
            artists.setdefault(str(row["video_id"]), []).append((int(row["position"] or 0), str(row["name"])))

        for row in conn.execute(
            f"""
            SELECT s.video_id, al.title
            FROM songs s JOIN albums al ON al.album_id = s.album_id
            WHERE s.video_id IN ({marks})
            """,
            batch,
        ):
            albums[str(row["video_id"])] = str(row["title"])

        for row in conn.execute(
            f"""
            SELECT sp.video_id, pl.name
            FROM song_playlists sp JOIN playlists pl ON pl.playlist_id = sp.playlist_id
            WHERE sp.video_id IN ({marks})
            """,
            batch,
        ):
            playlists.setdefault(str(row["video_id"]), []).append(str(row["name"]))

    for row in rows:
        video_id = str(row.get("video_id") or "")
        credited = sorted(artists.get(video_id, []), key=lambda pair: pair[0])
        row["artists"] = ", ".join(name for _, name in credited)
        row["album"] = albums.get(video_id, "")
        row["playlists"] = ", ".join(playlists.get(video_id, []))


def fetch_artists(db_path: str, limit: int = 2000) -> list[str]:
    """Every credited artist name, for the filter drop-down."""
    return _fetch_names(db_path, "SELECT name FROM artists WHERE name <> '' ORDER BY name COLLATE NOCASE LIMIT ?", limit)


def fetch_albums(db_path: str, limit: int = 2000) -> list[str]:
    return _fetch_names(db_path, "SELECT title FROM albums WHERE title <> '' ORDER BY title COLLATE NOCASE LIMIT ?", limit)


def fetch_playlists(db_path: str, limit: int = 2000) -> list[str]:
    return _fetch_names(db_path, "SELECT name FROM playlists WHERE name <> '' ORDER BY name COLLATE NOCASE LIMIT ?", limit)


def _fetch_names(db_path: str, statement: str, limit: int) -> list[str]:
    """A single-column lookup list. A missing table means an empty drop-down, not a crash."""
    init_db(db_path)
    with _connect(db_path) as conn:
        try:
            return [str(row[0]) for row in conn.execute(statement, (int(limit),))]
        except sqlite3.OperationalError:
            return []



def fetch_videos(
    db_path: str,
    *,
    search: str = "",
    source_id: int | None = None,
    completeness: str = "all",
    channel: str = "",
    min_duration: int | None = None,
    max_duration: int | None = None,
    artist: str = "",
    album: str = "",
    playlist: str = "",
    sort_key: str = DEFAULT_LIBRARY_SORT,
    descending: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """One page of the cached video rows, plus the total the filters match.

    Sorting happens here rather than in the grid because the grid only ever holds one
    page. Sorting the page would order 200 rows out of thousands and read as a bug.
    """
    limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    offset = max(0, int(offset))

    init_db(db_path)
    with _connect(db_path) as conn:
        if not _table_exists(conn, "youtube_video_information"):
            return [], 0

        where, params = _library_filters(
            search, source_id, completeness, channel, min_duration, max_duration,
            artist, album, playlist,
        )
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM youtube_video_information v {where}", params
        ).fetchone()["n"]
        order = _order_clause(sort_key, descending)
        rows = conn.execute(
            f"""
            SELECT v.id, v.video_id, v.title, v.channel_name, v.playlist_name, v.duration,
                   v.upload_date, v.cached_at, v.video_url,
                   COALESCE(v.is_full_metadata, 0) AS is_full_metadata,
                   (SELECT COUNT(*) FROM downloads d
                     WHERE d.video_info_id = v.id AND d.status = 'success') AS download_count
            FROM youtube_video_information v
            {where}
            ORDER BY {order}
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        page = [_row_to_dict(row) for row in rows]
        _attach_music_detail(conn, page)
        return page, int(total)


def delete_videos(db_path: str, row_ids: list[int]) -> int:
    """Remove cached video rows and clear the download rows that pointed at them.

    Clearing the link rather than deleting the download keeps the history intact: the
    operator asked to drop the metadata, not to erase the record that a file was fetched.
    """
    if not row_ids:
        return 0

    init_db(db_path)
    with _connect(db_path) as conn:
        placeholders = ", ".join("?" for _ in row_ids)
        params = [int(value) for value in row_ids]
        conn.execute(
            f"UPDATE downloads SET video_info_id = NULL WHERE video_info_id IN ({placeholders})",
            params,
        )
        cursor = conn.execute(
            f"DELETE FROM youtube_video_information WHERE id IN ({placeholders})", params
        )
        return int(cursor.rowcount or 0)


def database_stats(db_path: str) -> dict[str, int]:
    """Row counts for the tables an operator cares about. Missing tables report zero."""
    init_db(db_path)
    counts: dict[str, int] = {}
    with _connect(db_path) as conn:
        for table in ("sources", "youtube_video_information", "downloads", "errors", "user_actions", "settings_changes"):
            if not _table_exists(conn, table):
                counts[table] = 0
                continue
            counts[table] = int(conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])
    return counts


def _song_payload_from_import(row: dict[str, Any]) -> dict[str, Any]:
    """One ImportedItem, as a dictionary, turned into an upsert_songs payload.

    A backup knows things a listing never will: every credited artist, the album, which
    playlists a song sits in, how often it was played. That is the whole reason the music
    tables exist, so all of it is passed through rather than flattened into one column.
    """
    collections = row.get("collections") or []
    credited = row.get("artists") or row.get("channel_name") or ""
    payload: dict[str, Any] = {
        "video_id": str(row.get("video_id") or "").strip(),
        "title": row.get("title") or "",
        "duration": row.get("duration_seconds"),
        "thumbnail_url": row.get("thumbnail_url"),
        "video_url": row.get("url"),
        "upload_date": row.get("upload_date"),
        "album": row.get("album") or "",
        "bitrate_label": row.get("bitrate_label"),
        "play_count": row.get("play_count") or 0,
        "liked": "Liked" in collections,
        "in_library": "Library" in collections,
        "downloaded": "Downloaded" in collections,
        "origin": row.get("origin") or "import",
    }
    if credited:
        payload["artists"] = credited
    if row.get("playlists"):
        payload["playlists"] = row["playlists"]
    return payload



def import_video_rows(db_path: str, rows: list[dict[str, Any]], source_label: str) -> tuple[int, int]:
    """Merge imported items into the cache under their own source row.

    Returns (written, skipped). Rows already present keep their richer stored metadata:
    an import must never overwrite a full yt-dlp record with a sparser backup entry.

    Writes to both layers. youtube_video_information is the flat cache the older views
    read; the music tables keep the artists, album and playlists that the flat row has
    nowhere to put (Docs/07_MUSIC_SCHEMA_PLAN.md).
    """
    from .database_manager import upsert_songs, upsert_source
    from ..utils.shared import now_string

    if not rows:
        return 0, 0

    stamp = now_string()
    source_id = upsert_source(
        db_path,
        {
            "source_key": f"import:{source_label}",
            "source_kind": "import",
            "source_name": source_label,
            "source_value": source_label,
            "source_url": None,
            "created_at": stamp,
            "updated_at": stamp,
        },
    )

    written = 0
    skipped = 0
    with _connect(db_path) as conn:
        for row in rows:
            video_id = str(row.get("video_id") or "").strip()
            if not video_id:
                skipped += 1
                continue
            # A schema-aware parser knows the real playlist or album; only fall back to
            # the file name when it does not.
            grouping = row.get("playlists") or row.get("album") or source_label
            conn.execute(
                """
                INSERT INTO youtube_video_information (
                    video_id, title, channel_name, playlist_name, upload_date, duration,
                    thumbnail_url, video_url, source_id, cached_at, is_full_metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(video_id) DO UPDATE SET
                    title = COALESCE(NULLIF(youtube_video_information.title, ''), excluded.title),
                    channel_name = COALESCE(NULLIF(youtube_video_information.channel_name, ''), excluded.channel_name),
                    playlist_name = COALESCE(NULLIF(youtube_video_information.playlist_name, ''), excluded.playlist_name),
                    upload_date = COALESCE(NULLIF(youtube_video_information.upload_date, ''), excluded.upload_date),
                    duration = COALESCE(youtube_video_information.duration, excluded.duration),
                    thumbnail_url = COALESCE(NULLIF(youtube_video_information.thumbnail_url, ''), excluded.thumbnail_url),
                    video_url = COALESCE(NULLIF(youtube_video_information.video_url, ''), excluded.video_url),
                    source_id = COALESCE(youtube_video_information.source_id, excluded.source_id)
                """,
                (
                    video_id,
                    row.get("title") or None,
                    row.get("channel_name") or None,
                    grouping,
                    row.get("upload_date") or None,
                    row.get("duration_seconds"),
                    row.get("thumbnail_url") or None,
                    row.get("url") or None,
                    source_id,
                    stamp,
                ),
            )
            written += 1

    upsert_songs(db_path, [_song_payload_from_import(row) for row in rows if row.get("video_id")])
    return written, skipped
