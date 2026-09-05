"""OpenTune / InnerTune backup reader.

Owns:   reading the Android Room database those music apps export.
Reads:  the backup, always read-only. Never writes to it.
Writes: nothing.
Runs:   nothing. Pure Python, no Qt, so it can be run and tested head-less.

Schema documented in Docs/song_db_erd.html. Why this exists rather than letting the
generic scanner in parsers.py handle it:

1.  related_song_map is the largest table in the file and holds recommendations, not
    saved music. Scanning every table imports tens of thousands of songs the operator
    never chose. Reading the schema means only the song table produces rows, and each
    one carries the collection that explains why it is there.
2.  An artist name is not stored beside the song. It is reachable only through
    song_artist_map, so a table-by-table scan gives every song an empty channel.
3.  album, playlist, format and event add the album name, playlist membership,
    bitrate and play count that a blind scan drops on the floor.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Callable

from .models import (
    COLLECTION_ALBUM,
    COLLECTION_CACHED,
    COLLECTION_DOWNLOADED,
    COLLECTION_HISTORY,
    COLLECTION_LIBRARY,
    COLLECTION_LIKED,
    COLLECTION_PLAYLIST,
    ImportedItem,
    canonical_url,
    coerce_duration,
)

LogFn = Callable[[str], None]

# The tables that identify the format. song plus the artist junction is the smallest
# set no other backup in the wild happens to have.
REQUIRED_TABLES = {"song", "artist", "song_artist_map"}
CORROBORATING_TABLES = {"related_song_map", "format", "playlist_song_map", "song_album_map", "event"}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def looks_like_opentune(conn: sqlite3.Connection) -> bool:
    """True when this database is an OpenTune or InnerTune export.

    Corroboration is required as well as the core tables, because a hand-rolled
    database could plausibly own three tables with those names and nothing else.
    """
    present = _tables(conn)
    return REQUIRED_TABLES.issubset(present) and bool(CORROBORATING_TABLES & present)


def _select(conn: sqlite3.Connection, table: str, wanted: list[str]) -> list[sqlite3.Row]:
    """Read only the columns this particular export actually has.

    OpenTune and InnerTune have diverged over releases, and a fixed column list fails
    the whole read on the older one. The intersection reads what is there.
    """
    available = _columns(conn, table)
    columns = [name for name in wanted if name in available]
    if not columns:
        return []
    quoted = ", ".join(f'"{name}"' for name in columns)
    return conn.execute(f'SELECT {quoted} FROM "{table}"').fetchall()


def _value(row: sqlite3.Row, key: str) -> Any:
    try:
        return row[key]
    except (IndexError, KeyError):
        return None


def _artist_names(conn: sqlite3.Connection, log: LogFn) -> dict[str, list[str]]:
    """songId -> artist names, in the order the app credits them."""
    names = {
        str(_value(row, "id")): str(_value(row, "name") or "").strip()
        for row in _select(conn, "artist", ["id", "name"])
    }
    if not names:
        return {}

    ordered: dict[str, list[tuple[int, str]]] = {}
    for row in _select(conn, "song_artist_map", ["songId", "artistId", "position"]):
        song_id = str(_value(row, "songId") or "")
        name = names.get(str(_value(row, "artistId") or ""), "")
        if not song_id or not name:
            continue
        position = _value(row, "position")
        ordered.setdefault(song_id, []).append((int(position or 0), name))

    log(f"  artist: {len(names)} artist(s) credited across {len(ordered)} song(s).")
    return {
        song_id: [name for _, name in sorted(pairs, key=lambda pair: pair[0])]
        for song_id, pairs in ordered.items()
    }


def _album_titles(conn: sqlite3.Connection, log: LogFn) -> tuple[dict[str, str], dict[str, str]]:
    """(albumId -> title, songId -> album title reached through song_album_map)."""
    titles = {
        str(_value(row, "id")): str(_value(row, "title") or "").strip()
        for row in _select(conn, "album", ["id", "title"])
    }
    by_song: dict[str, str] = {}
    for row in _select(conn, "song_album_map", ["songId", "albumId"]):
        title = titles.get(str(_value(row, "albumId") or ""), "")
        song_id = str(_value(row, "songId") or "")
        if song_id and title:
            by_song[song_id] = title
    if titles:
        log(f"  album: {len(titles)} album(s), {len(by_song)} song(s) mapped.")
    return titles, by_song


def _playlist_names(conn: sqlite3.Connection, log: LogFn) -> dict[str, list[str]]:
    """songId -> the playlists it belongs to."""
    names = {
        str(_value(row, "id")): str(_value(row, "name") or "").strip()
        for row in _select(conn, "playlist", ["id", "name"])
    }
    if not names:
        return {}

    by_song: dict[str, list[str]] = {}
    for row in _select(conn, "playlist_song_map", ["playlistId", "songId"]):
        name = names.get(str(_value(row, "playlistId") or ""), "")
        song_id = str(_value(row, "songId") or "")
        if not song_id or not name:
            continue
        bucket = by_song.setdefault(song_id, [])
        if name not in bucket:
            bucket.append(name)

    log(f"  playlist: {len(names)} playlist(s) covering {len(by_song)} song(s).")
    return by_song


def _bitrates(conn: sqlite3.Connection, log: LogFn) -> dict[str, str]:
    """songId -> a readable bitrate and codec, from the cached stream format."""
    labels: dict[str, str] = {}
    for row in _select(conn, "format", ["id", "bitrate", "codecs", "mimeType"]):
        song_id = str(_value(row, "id") or "")
        if not song_id:
            continue
        bitrate = _value(row, "bitrate")
        codec = str(_value(row, "codecs") or "").split(".")[0]
        parts = []
        if bitrate:
            try:
                parts.append(f"{int(bitrate) // 1000}k")
            except (TypeError, ValueError):
                pass
        if codec:
            parts.append(codec)
        if parts:
            labels[song_id] = " ".join(parts)
    if labels:
        log(f"  format: cached stream details for {len(labels)} song(s).")
    return labels


def _play_counts(conn: sqlite3.Connection, log: LogFn) -> dict[str, int]:
    """songId -> how many times the app logged a play."""
    counts: dict[str, int] = {}
    available = _tables(conn)
    if "event" not in available or "songId" not in _columns(conn, "event"):
        return counts
    for row in conn.execute('SELECT songId, COUNT(*) AS n FROM "event" GROUP BY songId'):
        song_id = str(row[0] or "")
        if song_id:
            counts[song_id] = int(row[1] or 0)
    if counts:
        log(f"  event: play history for {len(counts)} song(s).")
    return counts


def _upload_date(row: sqlite3.Row) -> str:
    """song stores a full date on some releases and only a year on others."""
    date = _value(row, "date")
    if date not in (None, ""):
        return str(date).strip()
    year = _value(row, "year")
    return str(year).strip() if year not in (None, "") else ""


def _collections(row: sqlite3.Row, song_id: str, playlists: list[str], album: str, plays: int) -> list[str]:
    found: list[str] = []
    if _value(row, "dateDownload") not in (None, "", 0):
        found.append(COLLECTION_DOWNLOADED)
    if _value(row, "liked") in (1, True, "1"):
        found.append(COLLECTION_LIKED)
    if _value(row, "inLibrary") not in (None, "", 0):
        found.append(COLLECTION_LIBRARY)
    if playlists:
        found.append(COLLECTION_PLAYLIST)
    if album:
        found.append(COLLECTION_ALBUM)
    if plays:
        found.append(COLLECTION_HISTORY)
    return found or [COLLECTION_CACHED]


def parse_opentune(conn: sqlite3.Connection, log: LogFn, origin: str) -> list[ImportedItem]:
    """Read one OpenTune backup into items.

    Only the song table produces rows. Everything else supplies the detail hung off
    them, which is what keeps the recommendation graph out of the result.
    """
    log("Recognised the OpenTune / InnerTune schema; reading it by its tables.")

    artists = _artist_names(conn, log)
    _, album_by_song = _album_titles(conn, log)
    playlists = _playlist_names(conn, log)
    bitrates = _bitrates(conn, log)
    plays = _play_counts(conn, log)

    song_rows = _select(
        conn,
        "song",
        [
            "id", "title", "duration", "thumbnailUrl", "albumId", "albumName",
            "year", "date", "liked", "likedDate", "totalPlayTime", "inLibrary", "dateDownload",
        ],
    )

    items: list[ImportedItem] = []
    for row in song_rows:
        song_id = str(_value(row, "id") or "").strip()
        if not song_id:
            continue

        credited = artists.get(song_id, [])
        # albumName is denormalised onto the song; the junction is the fallback.
        album = str(_value(row, "albumName") or "").strip() or album_by_song.get(song_id, "")
        in_playlists = playlists.get(song_id, [])
        play_count = plays.get(song_id, 0)

        items.append(
            ImportedItem(
                video_id=song_id,
                url=canonical_url(song_id),
                title=str(_value(row, "title") or "").strip(),
                channel_name=credited[0] if credited else "",
                duration_seconds=coerce_duration(_value(row, "duration")),
                upload_date=_upload_date(row),
                origin=f"{origin}:song",
                album=album,
                artists=", ".join(credited),
                playlists=", ".join(in_playlists),
                thumbnail_url=str(_value(row, "thumbnailUrl") or "").strip(),
                bitrate_label=bitrates.get(song_id, ""),
                play_count=play_count,
                collections=_collections(row, song_id, in_playlists, album, play_count),
            )
        )

    kept = sum(1 for item in items if item.collection_label != COLLECTION_CACHED)
    log(
        f"  song: {len(items)} song(s) read. {kept} are saved, liked, downloaded, "
        f"played or in a playlist; the rest are cache only."
    )
    return items
