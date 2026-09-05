"""ViTune / ViMusic backup reader.

Owns:   reading the Android Room database ViTune and its ViMusic ancestors export.
Reads:  the backup, always read-only. Never writes to it.
Writes: nothing.
Runs:   nothing. Pure Python, no Qt, so it can be run and tested head-less.

Schema documented in Docs/vitune_db_erd.html, and compared with OpenTune's in
Docs/opentune_vs_vitune.html. It is a separate reader from opentune.py rather than a
branch inside it, because four differences change how the rows have to be read:

1.  Tables are PascalCase (`Song`, `SongArtistMap`), not snake_case. Nothing matches.
2.  Duration is `durationText`, the string "3:35", not a number of seconds.
3.  `SongArtistMap` is often empty for a song, and `Song.artistsText` carries the credit
    as the app wrote it. On a real backup 5085 songs share only 6094 map rows, and songs
    with six credited artists have none at all, so the text column cannot be ignored.
4.  There is no `inLibrary` and no `dateDownload`. ViTune records what was played, liked
    or filed; it does not record what was downloaded, so no item is marked Downloaded.

The generic scanner in parsers.py gets this file wrong the same way it got OpenTune
wrong: it walks `Event`, which holds 18394 play records against 5085 songs, and it
attaches no artist to anything, because an artist name is reachable only through a
junction or a text column it does not know to read.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any, Callable

from .models import (
    COLLECTION_ALBUM,
    COLLECTION_CACHED,
    COLLECTION_HISTORY,
    COLLECTION_LIKED,
    COLLECTION_PLAYLIST,
    ImportedItem,
    canonical_url,
    coerce_duration,
)

LogFn = Callable[[str], None]

# Song plus the two PascalCase junctions. OpenTune's tables are lower case, so the two
# formats cannot be confused even though they describe the same kind of library.
REQUIRED_TABLES = {"Song", "Artist", "SongArtistMap"}
CORROBORATING_TABLES = {"SongPlaylistMap", "SongAlbumMap", "Format", "Event", "QueuedMediaItem"}

# ViTune writes a credit the way YouTube Music formats one, "A, B & C", and 32 of the 5085
# songs in a real backup use pipes instead. A comma and a pipe never appear inside an
# artist's name, so they always separate. A spaced ampersand usually does, but not in
# "Simon & Garfunkel", so `_credited` checks the whole string against the Artist table
# before it splits on one.
ARTIST_SPLIT = re.compile(r"[,|]|\s&\s")

# Runs of whitespace, including the non-breaking spaces ViTune stores in nine of those
# 5085 credits. A name holding one can never be matched by anyone typing it.
WHITESPACE = re.compile(r"\s+")


def _clean(value: Any) -> str:
    return WHITESPACE.sub(" ", str(value or "")).strip()

# A song ViTune imported from the phone's own storage. It has no video id and nothing to
# download, so it is not something this application can act on.
LOCAL_ID_PREFIX = "local:"


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def looks_like_vitune(conn: sqlite3.Connection) -> bool:
    """True when this database is a ViTune or ViMusic export.

    Corroboration is required as well as the core tables, for the same reason as in
    opentune.py: three table names on their own are a coincidence waiting to happen.
    """
    present = _tables(conn)
    return REQUIRED_TABLES.issubset(present) and bool(CORROBORATING_TABLES & present)


def _select(conn: sqlite3.Connection, table: str, wanted: list[str]) -> list[sqlite3.Row]:
    """Read only the columns this particular export actually has.

    ViMusic and its forks have diverged over releases: `blacklisted` and `explicit` are
    recent, `loudnessBoost` newer still. A fixed column list fails the whole read on an
    older file, so the intersection reads what is there.
    """
    if table not in _tables(conn):
        return []
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


def _mapped_artists(conn: sqlite3.Connection, log: LogFn) -> tuple[dict[str, list[str]], set[str]]:
    """(songId -> artist names through SongArtistMap, every name the Artist table holds).

    The junction has no position column, so its order is the order the rows happen to be
    stored in. `_credited` puts it right using the text column where one exists, and the
    second return value is what tells it when an ampersand is part of a name.
    """
    names = {
        str(_value(row, "id")): _clean(_value(row, "name"))
        for row in _select(conn, "Artist", ["id", "name"])
    }
    known = {name.casefold() for name in names.values() if name}
    if not names:
        return {}, known

    by_song: dict[str, list[str]] = {}
    for row in _select(conn, "SongArtistMap", ["songId", "artistId"]):
        song_id = str(_value(row, "songId") or "")
        name = names.get(str(_value(row, "artistId") or ""), "")
        if not song_id or not name:
            continue
        bucket = by_song.setdefault(song_id, [])
        if name not in bucket:
            bucket.append(name)

    log(f"  Artist: {len(names)} artist(s) linked to {len(by_song)} song(s) through SongArtistMap.")
    return by_song, known


def _credited(artists_text: str, mapped: list[str], known: set[str] | None = None) -> list[str]:
    """Merge the text credit with the linked artists, keeping the best of each.

    The text column has the order the app credits artists in and every name; the Artist
    table has the canonical spelling, because ViTune stores what the user typed. So the
    text supplies the sequence, a linked name replaces a text one when they match apart
    from case, and any linked artist the text never mentions is appended.

    A credit the Artist table already knows in full is never split. That is what keeps
    "Simon & Garfunkel" one artist while "Jasleen Royal & Arijit Singh" becomes two.
    """
    whole = _clean(artists_text)
    if whole and known and whole.casefold() in known:
        return [whole]

    written = [_clean(part) for part in ARTIST_SPLIT.split(whole) if _clean(part)]
    if not written:
        return list(mapped)
    if not mapped:
        return written

    canonical = {name.casefold(): name for name in mapped}
    merged: list[str] = []
    for name in written:
        chosen = canonical.get(name.casefold(), name)
        if chosen not in merged:
            merged.append(chosen)
    for name in mapped:
        if name not in merged:
            merged.append(name)
    return merged


def _album_titles(conn: sqlite3.Connection, log: LogFn) -> dict[str, str]:
    """songId -> album title, through SongAlbumMap."""
    titles = {
        str(_value(row, "id")): _clean(_value(row, "title"))
        for row in _select(conn, "Album", ["id", "title"])
    }
    by_song: dict[str, str] = {}
    for row in _select(conn, "SongAlbumMap", ["songId", "albumId"]):
        title = titles.get(str(_value(row, "albumId") or ""), "")
        song_id = str(_value(row, "songId") or "")
        if song_id and title:
            by_song[song_id] = title
    if titles:
        log(f"  Album: {len(titles)} album(s), {len(by_song)} song(s) mapped.")
    return by_song


def _playlist_names(conn: sqlite3.Connection, log: LogFn) -> dict[str, list[str]]:
    """songId -> the playlists it belongs to, in running order."""
    names = {
        str(_value(row, "id")): _clean(_value(row, "name"))
        for row in _select(conn, "Playlist", ["id", "name"])
    }
    if not names:
        return {}

    ordered: dict[str, list[tuple[int, str]]] = {}
    for row in _select(conn, "SongPlaylistMap", ["songId", "playlistId", "position"]):
        song_id = str(_value(row, "songId") or "")
        name = names.get(str(_value(row, "playlistId") or ""), "")
        if not song_id or not name:
            continue
        ordered.setdefault(song_id, []).append((int(_value(row, "position") or 0), name))

    by_song: dict[str, list[str]] = {}
    for song_id, pairs in ordered.items():
        seen: list[str] = []
        for _, name in sorted(pairs, key=lambda pair: pair[0]):
            if name not in seen:
                seen.append(name)
        by_song[song_id] = seen

    log(f"  Playlist: {len(names)} playlist(s) covering {len(by_song)} song(s).")
    return by_song


def _bitrates(conn: sqlite3.Connection, log: LogFn) -> dict[str, str]:
    """songId -> a readable bitrate and container, from the cached stream format.

    ViTune's Format is keyed on songId and stores mimeType rather than a codec string,
    so the container is taken off the subtype: "audio/mp4; codecs=..." becomes "mp4".
    """
    labels: dict[str, str] = {}
    for row in _select(conn, "Format", ["songId", "bitrate", "mimeType"]):
        song_id = str(_value(row, "songId") or "")
        if not song_id:
            continue
        parts = []
        bitrate = _value(row, "bitrate")
        if bitrate:
            try:
                parts.append(f"{int(bitrate) // 1000}k")
            except (TypeError, ValueError):
                pass
        mime = str(_value(row, "mimeType") or "")
        if "/" in mime:
            parts.append(mime.split("/", 1)[1].split(";")[0].strip())
        if parts:
            labels[song_id] = " ".join(parts)
    if labels:
        log(f"  Format: cached stream details for {len(labels)} song(s).")
    return labels


def _play_counts(conn: sqlite3.Connection, log: LogFn) -> dict[str, int]:
    """songId -> how many plays Event recorded."""
    counts: dict[str, int] = {}
    if "Event" not in _tables(conn) or "songId" not in _columns(conn, "Event"):
        return counts
    for row in conn.execute('SELECT songId, COUNT(*) FROM "Event" GROUP BY songId'):
        song_id = str(row[0] or "")
        if song_id:
            counts[song_id] = int(row[1] or 0)
    if counts:
        log(f"  Event: play history for {len(counts)} song(s).")
    return counts


def _collections(row: sqlite3.Row, playlists: list[str], album: str, plays: int) -> list[str]:
    """Why this song is in the file.

    No Downloaded and no Library: ViTune has no column for either. Claiming a song was
    downloaded because a stream was cached would be a guess, and the wrong one would stop
    a download the operator wanted.
    """
    found: list[str] = []
    if _value(row, "likedAt") not in (None, "", 0):
        found.append(COLLECTION_LIKED)
    if playlists:
        found.append(COLLECTION_PLAYLIST)
    if album:
        found.append(COLLECTION_ALBUM)
    if plays or _value(row, "totalPlayTimeMs"):
        found.append(COLLECTION_HISTORY)
    return found or [COLLECTION_CACHED]


def parse_vitune(conn: sqlite3.Connection, log: LogFn, origin: str) -> list[ImportedItem]:
    """Read one ViTune backup into items.

    Only the Song table produces rows, for the same reason as in opentune.py: everything
    else describes a song rather than being one.
    """
    log("Recognised the ViTune / ViMusic schema; reading it by its tables.")

    mapped, known_artists = _mapped_artists(conn, log)
    album_by_song = _album_titles(conn, log)
    playlists = _playlist_names(conn, log)
    bitrates = _bitrates(conn, log)
    plays = _play_counts(conn, log)

    song_rows = _select(
        conn,
        "Song",
        ["id", "title", "artistsText", "durationText", "thumbnailUrl", "likedAt", "totalPlayTimeMs", "blacklisted"],
    )

    items: list[ImportedItem] = []
    local_files = 0
    blacklisted = 0

    for row in song_rows:
        song_id = str(_value(row, "id") or "").strip()
        if not song_id:
            continue
        if song_id.startswith(LOCAL_ID_PREFIX):
            local_files += 1
            continue
        if _value(row, "blacklisted") in (1, True, "1"):
            blacklisted += 1
            continue

        credited = _credited(_value(row, "artistsText"), mapped.get(song_id, []), known_artists)
        album = album_by_song.get(song_id, "")
        in_playlists = playlists.get(song_id, [])
        play_count = plays.get(song_id, 0)

        items.append(
            ImportedItem(
                video_id=song_id,
                url=canonical_url(song_id),
                title=_clean(_value(row, "title")),
                channel_name=credited[0] if credited else "",
                duration_seconds=coerce_duration(_value(row, "durationText")),
                upload_date="",
                origin=f"{origin}:Song",
                album=album,
                artists=", ".join(credited),
                playlists=", ".join(in_playlists),
                thumbnail_url=str(_value(row, "thumbnailUrl") or "").strip(),
                bitrate_label=bitrates.get(song_id, ""),
                play_count=play_count,
                collections=_collections(row, in_playlists, album, play_count),
            )
        )

    kept = sum(1 for item in items if item.collection_label != COLLECTION_CACHED)
    log(
        f"  Song: {len(song_rows)} row(s) read, {len(items)} kept. {kept} are liked, played "
        f"or filed under a playlist or album; the rest are cache only."
    )
    if local_files:
        log(f"  Skipped {local_files} on-device file(s): a 'local:' id is not a YouTube video.")
    if blacklisted:
        log(f"  Skipped {blacklisted} song(s) the app has blacklisted.")
    return items
