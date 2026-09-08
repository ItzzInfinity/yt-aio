"""Fill in the blanks an existing database was left with, keyed on video_id.

A listing run writes what a flat playlist fetch knows: an id, a title, a thumbnail and a
URL. Upload date, duration, channel and bitrate only arrive with a full metadata fetch,
which config.json turns off by default (`fetch_full_metadata`). A library built that way
ends up with tens of thousands of rows that are correct but thin, and nothing in the
application goes back to finish them.

This does. It runs in two halves, because they cost wildly different amounts:

* The local passes move facts that are already in the file from one table to another.
  `songs` and `youtube_video_information` hold the same video twice and neither is
  reliably the fuller one, so each fills the other's gaps; a download row learns which
  cache row it belongs to; a local file learns the video_id its matched cache row knows.
  Seconds, no network, and the only sensible default.
* The network pass (`--network`) asks yt-dlp for the videos still missing something. That
  is one lookup per video, so it is opt-in, resumable, and honours --limit.

Every write merges: a column is only set when it is blank and the other side has
something. Nothing here overwrites a value the library already established unless you ask
for that with --refresh, which is what makes re-running safe and makes an interrupted run
cost only its unfetched tail.

    python -m yt_aio.application.db.backfill --dry-run
    python -m yt_aio.application.db.backfill
    python -m yt_aio.application.db.backfill --network --limit 2000
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..utils.config_manager import CONFIG_PATH, load_config, resolve_runtime_config
from ..utils.shared import CancellationToken, now_string
from ..utils.video_info_extractor import extract_audio_bitrate, fetch_metadata_batch
from .database_manager import init_db, upsert_songs


# The timestamp the rest of the schema is written with, produced by SQLite so an UPDATE
# does not need a bound parameter threaded through every statement. Matches now_string().
SQL_STAMP = "strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime')"

# youtu.be/<id>, /watch?v=<id>, /shorts/<id>, /embed/<id>. YouTube ids are 11 characters
# of the URL-safe alphabet, which is specific enough to pull one out of a stored URL.
VIDEO_ID_PATTERN = re.compile(
    r"(?:v=|/shorts/|/embed/|/live/|youtu\.be/)([0-9A-Za-z_-]{11})"
)


def _blank(column: str) -> str:
    """The predicate for "this text column says nothing", NULL or whitespace alike."""
    return f"TRIM(COALESCE({column}, '')) = ''"


def _present(column: str) -> str:
    return f"TRIM(COALESCE({column}, '')) <> ''"


def _keep_text(column: str, fallback: str) -> str:
    """Assign `fallback` only where `column` is blank, and leave a kept value untouched.

    The obvious COALESCE(NULLIF(TRIM(col), ''), fallback) has a quiet second effect: when
    col is not blank it assigns the *trimmed* value back, which rewrites a stored title
    nobody asked to change. A CASE keeps the value exactly as it was found.
    """
    return f"CASE WHEN {_blank(column)} THEN {fallback} ELSE {column} END"


def _keep_number(column: str, fallback: str) -> str:
    """The same, for a column where NULL and zero both mean unknown."""
    return f"CASE WHEN COALESCE({column}, 0) = 0 THEN {fallback} ELSE {column} END"


# ---------------------------------------------------------------------------
# The census
# ---------------------------------------------------------------------------

# Every column worth counting, with what counts as empty for it. A duration or a bitrate
# is stored as a number and zero means unknown, so those cannot use the text predicate.
CENSUS: tuple[tuple[str, str, str], ...] = (
    ("songs", "duration", "duration IS NULL OR duration = 0"),
    ("songs", "upload_date", _blank("upload_date")),
    ("songs", "thumbnail_url", _blank("thumbnail_url")),
    ("songs", "bitrate_label", _blank("bitrate_label")),
    ("songs", "album_id", _blank("album_id")),
    ("youtube_video_information", "channel_name", _blank("channel_name")),
    ("youtube_video_information", "playlist_name", _blank("playlist_name")),
    ("youtube_video_information", "upload_date", _blank("upload_date")),
    ("youtube_video_information", "duration", "duration IS NULL OR duration = 0"),
    ("youtube_video_information", "thumbnail_url", _blank("thumbnail_url")),
    ("youtube_video_information", "is_full_metadata", "COALESCE(is_full_metadata, 0) = 0"),
    ("downloads", "video_id", _blank("video_id")),
    ("downloads", "video_info_id", "video_info_id IS NULL"),
    ("downloads", "file_path", f"status = 'success' AND {_blank('file_path')}"),
    ("local_files", "video_id", f"match_status <> 'New' AND {_blank('video_id')}"),
    ("local_files", "matched_video_info_id", "match_status <> 'New' AND matched_video_info_id IS NULL"),
    ("albums", "year", _blank("year")),
    ("albums", "thumbnail_url", _blank("thumbnail_url")),
    ("artists", "thumbnail_url", _blank("thumbnail_url")),
    ("artists", "channel_url", _blank("channel_url")),
)


def census(conn: sqlite3.Connection) -> list[tuple[str, int, int]]:
    """One (column, blanks, rows) row per entry in CENSUS, blanks first."""
    rows: list[tuple[str, int, int]] = []
    for table, column, predicate in CENSUS:
        blanks = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {predicate}").fetchone()[0]
        total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        rows.append((f"{table}.{column}", blanks, total))
    return rows


def print_census(conn: sqlite3.Connection, heading: str) -> None:
    print(f"\n{heading}")
    width = max(len(name) for name, _, _ in census(conn))
    for name, blanks, total in census(conn):
        if blanks:
            print(f"  {name:<{width}}  {blanks:>7,} blank of {total:>7,}")
    print()


# ---------------------------------------------------------------------------
# The local passes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pass:
    """One merge expressed once and read two ways.

    `predicate` decides which rows are candidates, and it is the whole difference between
    counting the work and doing it. Writing it once is what keeps a --dry-run figure
    honest about the run that follows it.
    """

    label: str
    table: str
    assignments: str
    predicate: str
    source: str = ""

    def count_sql(self) -> str:
        frm = f"{self.table}, {self.source}" if self.source else self.table
        return f"SELECT COUNT(*) FROM {frm} WHERE {self.predicate}"

    def update_sql(self) -> str:
        frm = f" FROM {self.source}" if self.source else ""
        return f"UPDATE {self.table} SET {self.assignments}{frm} WHERE {self.predicate}"


LOCAL_PASSES: tuple[Pass, ...] = (
    Pass(
        label="video info <- songs",
        table="youtube_video_information AS v",
        source="songs AS s",
        assignments=(
            f"duration = {_keep_number('v.duration', 's.duration')}, "
            f"upload_date = {_keep_text('v.upload_date', 's.upload_date')}, "
            f"thumbnail_url = {_keep_text('v.thumbnail_url', 's.thumbnail_url')}, "
            f"video_url = {_keep_text('v.video_url', 's.video_url')}"
        ),
        predicate=(
            "s.video_id = v.video_id AND ("
            "  ((v.duration IS NULL OR v.duration = 0) AND s.duration > 0)"
            f" OR ({_blank('v.upload_date')} AND {_present('s.upload_date')})"
            f" OR ({_blank('v.thumbnail_url')} AND {_present('s.thumbnail_url')})"
            f" OR ({_blank('v.video_url')} AND {_present('s.video_url')})"
            ")"
        ),
    ),
    Pass(
        label="songs <- video info",
        table="songs AS s",
        source="youtube_video_information AS v",
        # songs.title is NOT NULL, so where neither side has anything the fallback ends
        # on the stored value rather than on NULL.
        assignments=(
            f"""title = {_keep_text('s.title', "COALESCE(NULLIF(TRIM(v.title), ''), s.title)")}, """
            f"duration = {_keep_number('s.duration', 'v.duration')}, "
            f"upload_date = {_keep_text('s.upload_date', 'v.upload_date')}, "
            f"thumbnail_url = {_keep_text('s.thumbnail_url', 'v.thumbnail_url')}, "
            f"video_url = {_keep_text('s.video_url', 'v.video_url')}, "
            f"last_updated = {SQL_STAMP}"
        ),
        predicate=(
            "v.video_id = s.video_id AND ("
            f"  ({_blank('s.title')} AND {_present('v.title')})"
            "  OR ((s.duration IS NULL OR s.duration = 0) AND v.duration > 0)"
            f" OR ({_blank('s.upload_date')} AND {_present('v.upload_date')})"
            f" OR ({_blank('s.thumbnail_url')} AND {_present('v.thumbnail_url')})"
            f" OR ({_blank('s.video_url')} AND {_present('v.video_url')})"
            ")"
        ),
    ),
    Pass(
        label="video info channel <- artist credit",
        table="youtube_video_information AS v",
        # The first credit, not any credit: song_artists.position records the order the
        # metadata gave, and position 0 is the channel the video was published under.
        assignments=(
            "channel_name = ("
            "  SELECT a.name FROM song_artists sa JOIN artists a ON a.artist_id = sa.artist_id"
            "  WHERE sa.video_id = v.video_id ORDER BY sa.position LIMIT 1)"
        ),
        predicate=(
            f"{_blank('v.channel_name')} AND EXISTS ("
            "  SELECT 1 FROM song_artists sa JOIN artists a ON a.artist_id = sa.artist_id"
            f"  WHERE sa.video_id = v.video_id AND {_present('a.name')})"
        ),
    ),
    Pass(
        label="songs album <- song_albums",
        table="songs AS s",
        assignments=(
            "album_id = (SELECT sa.album_id FROM song_albums sa WHERE sa.video_id = s.video_id"
            "  ORDER BY COALESCE(sa.position, 0) LIMIT 1), "
            f"last_updated = {SQL_STAMP}"
        ),
        predicate=(
            f"{_blank('s.album_id')} AND "
            "EXISTS (SELECT 1 FROM song_albums sa WHERE sa.video_id = s.video_id)"
        ),
    ),
    Pass(
        label="songs in_library <- local files",
        table="songs AS s",
        assignments=f"in_library = 1, last_updated = {SQL_STAMP}",
        predicate=(
            "s.in_library = 0 AND "
            "EXISTS (SELECT 1 FROM local_files lf WHERE lf.video_id = s.video_id)"
        ),
    ),
    Pass(
        label="songs downloaded <- download history",
        table="songs AS s",
        assignments=f"downloaded = 1, last_updated = {SQL_STAMP}",
        predicate=(
            "s.downloaded = 0 AND EXISTS ("
            "  SELECT 1 FROM downloads d WHERE d.video_id = s.video_id AND d.status = 'success')"
        ),
    ),
    Pass(
        label="songs bitrate <- local files",
        table="songs AS s",
        # local_files.bitrate is bits per second from mutagen and occasionally kilobits
        # from ffprobe, the same ambiguity local_files._bitrate_label resolves, and by the
        # same rule: anything above a thousand is the former.
        assignments=(
            "bitrate_label = (SELECT CASE WHEN lf.bitrate > 1000"
            "    THEN CAST(lf.bitrate / 1000 AS TEXT) || 'k'"
            "    ELSE CAST(lf.bitrate AS TEXT) || 'k' END"
            "  FROM local_files lf WHERE lf.video_id = s.video_id AND lf.bitrate > 0"
            "  ORDER BY lf.bitrate DESC LIMIT 1), "
            f"last_updated = {SQL_STAMP}"
        ),
        predicate=(
            f"{_blank('s.bitrate_label')} AND EXISTS ("
            "  SELECT 1 FROM local_files lf WHERE lf.video_id = s.video_id AND lf.bitrate > 0)"
        ),
    ),
    Pass(
        label="downloads -> video info link",
        table="downloads AS d",
        source="youtube_video_information AS v",
        assignments=(
            "video_info_id = COALESCE(d.video_info_id, v.id), "
            "source_id = COALESCE(d.source_id, v.source_id)"
        ),
        predicate=(
            f"v.video_id = d.video_id AND {_present('d.video_id')} AND "
            "(d.video_info_id IS NULL OR d.source_id IS NULL)"
        ),
    ),
    Pass(
        label="downloads file_path <- local files",
        table="downloads AS d",
        # Only for a download that reported success. A failed or cancelled row has no
        # file because none was ever written, and inventing one would turn a truthful
        # blank into a claim the disk cannot back.
        assignments=(
            "file_path = (SELECT lf.file_path FROM local_files lf"
            "  WHERE lf.video_id = d.video_id ORDER BY lf.last_seen_at DESC LIMIT 1)"
        ),
        predicate=(
            f"d.status = 'success' AND {_blank('d.file_path')} AND {_present('d.video_id')} AND "
            "EXISTS (SELECT 1 FROM local_files lf WHERE lf.video_id = d.video_id)"
        ),
    ),
    Pass(
        label="local files video_id <- matched cache row",
        table="local_files AS lf",
        source="youtube_video_information AS v",
        assignments="video_id = v.video_id",
        predicate=(
            f"v.id = lf.matched_video_info_id AND {_blank('lf.video_id')} AND {_present('v.video_id')}"
        ),
    ),
    Pass(
        label="local files matched id <- video_id",
        table="local_files AS lf",
        source="youtube_video_information AS v",
        assignments="matched_video_info_id = v.id",
        predicate=(
            f"v.video_id = lf.video_id AND {_present('lf.video_id')} AND "
            "lf.matched_video_info_id IS NULL"
        ),
    ),
)


# Inference, not retrieval: an album has no upload date or artwork of its own here, so
# these read one off its tracks. Close enough to be useful and wrong often enough to be
# opt-in, which is why they sit behind --derive-albums rather than in LOCAL_PASSES.
DERIVED_PASSES: tuple[Pass, ...] = (
    Pass(
        label="albums year <- earliest track upload date",
        table="albums AS a",
        assignments=(
            "year = (SELECT SUBSTR(MIN(s.upload_date), 1, 4) FROM song_albums sa"
            "  JOIN songs s ON s.video_id = sa.video_id"
            f"  WHERE sa.album_id = a.album_id AND {_present('s.upload_date')})"
        ),
        predicate=(
            f"{_blank('a.year')} AND EXISTS ("
            "  SELECT 1 FROM song_albums sa JOIN songs s ON s.video_id = sa.video_id"
            f"  WHERE sa.album_id = a.album_id AND {_present('s.upload_date')})"
        ),
    ),
    Pass(
        label="albums artwork <- first track thumbnail",
        table="albums AS a",
        assignments=(
            "thumbnail_url = (SELECT s.thumbnail_url FROM song_albums sa"
            "  JOIN songs s ON s.video_id = sa.video_id"
            f"  WHERE sa.album_id = a.album_id AND {_present('s.thumbnail_url')}"
            "  ORDER BY COALESCE(sa.position, 0) LIMIT 1)"
        ),
        predicate=(
            f"{_blank('a.thumbnail_url')} AND EXISTS ("
            "  SELECT 1 FROM song_albums sa JOIN songs s ON s.video_id = sa.video_id"
            f"  WHERE sa.album_id = a.album_id AND {_present('s.thumbnail_url')})"
        ),
    ),
)


def run_passes(conn: sqlite3.Connection, passes: tuple[Pass, ...], *, dry_run: bool) -> int:
    total = 0
    for step in passes:
        candidates = conn.execute(step.count_sql()).fetchone()[0]
        if not candidates:
            continue
        if not dry_run:
            conn.execute(step.update_sql())
        verb = "would fill" if dry_run else "filled"
        print(f"  {verb} {candidates:>7,}  {step.label}")
        total += candidates
    return total


def fill_download_video_ids(conn: sqlite3.Connection, *, dry_run: bool) -> int:
    """Read the video_id back out of the URL a download row already stores.

    SQL could slice this out, but the stored URLs are whatever was pasted, including a
    shorts link and, in at least one row, two URLs separated by a newline. A regex reads
    the first id it finds and leaves anything it cannot recognise alone.
    """
    rows = conn.execute(
        f"SELECT id, url FROM downloads WHERE {_blank('video_id')} AND {_present('url')}"
    ).fetchall()

    updates = []
    for row in rows:
        found = VIDEO_ID_PATTERN.search(row["url"])
        if found:
            updates.append((found.group(1), row["id"]))

    if updates and not dry_run:
        conn.executemany("UPDATE downloads SET video_id = ? WHERE id = ?", updates)
    if updates:
        verb = "would fill" if dry_run else "filled"
        print(f"  {verb} {len(updates):>7,}  downloads video_id <- url")
    return len(updates)


# ---------------------------------------------------------------------------
# The network pass
# ---------------------------------------------------------------------------


def network_candidates(conn: sqlite3.Connection, limit: int | None) -> list[str]:
    """Every video still missing something only a metadata fetch can supply.

    A row whose gaps are all in the local half of this script never appears here, because
    the local passes run first and close them. What is left genuinely needs YouTube.
    """
    rows = conn.execute(
        f"""
        SELECT s.video_id
        FROM songs s
        LEFT JOIN youtube_video_information v ON v.video_id = s.video_id
        WHERE (s.duration IS NULL OR s.duration = 0)
           OR {_blank('s.upload_date')}
           OR {_blank('s.thumbnail_url')}
           OR {_blank('s.bitrate_label')}
           OR v.video_id IS NULL
           OR {_blank('v.channel_name')}
           OR (v.duration IS NULL OR v.duration = 0)
           OR {_blank('v.upload_date')}
           OR {_blank('v.thumbnail_url')}
        UNION
        SELECT v.video_id
        FROM youtube_video_information v
        LEFT JOIN songs s ON s.video_id = v.video_id
        WHERE s.video_id IS NULL
        ORDER BY 1
        """
    ).fetchall()
    ids = [row[0] for row in rows if row[0]]
    return ids[:limit] if limit else ids


def _payloads(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Split one yt-dlp result into a cache row and a songs row.

    The channel falls back through the same four keys the extractor uses, and a bitrate
    of "Unknown" becomes an empty string so the merge treats it as nothing learned rather
    than as a value worth storing.
    """
    video_id = data.get("id")
    if not video_id:
        return None

    channel = (
        data.get("channel")
        or data.get("uploader")
        or data.get("playlist_channel")
        or data.get("playlist_uploader")
        or ""
    )
    bitrate = extract_audio_bitrate(data.get("formats"))
    if bitrate == "Unknown":
        bitrate = ""

    info = {
        "video_id": video_id,
        "title": data.get("title"),
        "channel_name": channel or None,
        "upload_date": data.get("upload_date"),
        "duration": data.get("duration"),
        "thumbnail_url": data.get("thumbnail"),
        "video_url": data.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}",
        "cached_at": now_string(),
    }
    song = {
        "video_id": video_id,
        "title": data.get("title") or "",
        "duration": data.get("duration"),
        "thumbnail_url": data.get("thumbnail"),
        "video_url": info["video_url"],
        "upload_date": data.get("upload_date"),
        "bitrate_label": bitrate,
    }
    # An absent key means "this fetch knows nothing here", which upsert_songs reads as
    # leave the credits alone. An empty list would read as "this song has no artists".
    if channel:
        song["artists"] = [channel]
    return info, song


# The cache-row half of a fetch, in two readings of "merge". The default keeps whatever
# the row already had; --refresh lets the fetch win any column it actually filled. Built
# from the helpers because six near-identical CASE expressions is where a typo hides.
def _fetch_merge_sql(*, refresh: bool) -> str:
    columns = ("title", "channel_name", "upload_date", "thumbnail_url", "video_url")
    if refresh:
        updates = [
            f"{name} = COALESCE(NULLIF(TRIM(excluded.{name}), ''), youtube_video_information.{name})"
            for name in columns
        ]
        updates.append(
            "duration = COALESCE(NULLIF(excluded.duration, 0), youtube_video_information.duration)"
        )
    else:
        updates = [
            f"{name} = {_keep_text(f'youtube_video_information.{name}', f'excluded.{name}')}"
            for name in columns
        ]
        updates.append(
            f"duration = {_keep_number('youtube_video_information.duration', 'excluded.duration')}"
        )
    updates += ["cached_at = excluded.cached_at", "is_full_metadata = 1"]

    return f"""
        INSERT INTO youtube_video_information (
            video_id, title, channel_name, upload_date, duration,
            thumbnail_url, video_url, cached_at, is_full_metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(video_id) DO UPDATE SET
            {", ".join(updates)}
    """


# What "this column already says something" means, per songs column a fetch can supply.
SONG_FIELDS: tuple[str, ...] = (
    "title",
    "duration",
    "thumbnail_url",
    "video_url",
    "upload_date",
    "bitrate_label",
)


def _stored_song_rows(conn: sqlite3.Connection, video_ids: list[str]) -> dict[str, sqlite3.Row]:
    marks = ",".join("?" * len(video_ids))
    columns = ", ".join(SONG_FIELDS)
    rows = conn.execute(
        f"SELECT video_id, {columns} FROM songs WHERE video_id IN ({marks})", video_ids
    ).fetchall()
    return {row["video_id"]: row for row in rows}


def _prune_to_blanks(song: dict[str, Any], stored: sqlite3.Row | None) -> dict[str, Any]:
    """Drop every key the stored row can already answer for itself.

    upsert_songs merges by letting a non-empty incoming value win, which is right for a
    listing that just read the source and wrong for a backfill: YouTube's current title
    for a track is sometimes the plainer one, and accepting it turns "DARKHAAST (feat.
    Sunidhi Chauhan & Arijit Singh)" into "DARKHAAST". Removing the key rather than
    guarding the SQL keeps that decision here, where the intent lives, and leaves
    upsert_songs to the merge it already documents.

    `artists` is never pruned. Its junction rows are additive, so a credit this fetch
    knows about is added without displacing one already recorded.
    """
    if stored is None:
        return song

    pruned = dict(song)
    for field in SONG_FIELDS:
        value = stored[field]
        occupied = (value or 0) > 0 if field == "duration" else str(value or "").strip() != ""
        if occupied:
            pruned.pop(field, None)
    return pruned


def write_fetched(
    db_path: str,
    batch: list[tuple[dict[str, Any], dict[str, Any]]],
    *,
    refresh: bool = False,
) -> None:
    """Merge one batch of fetched metadata into both tables.

    log_video_info_batch would be the obvious reuse, but it assigns each column from the
    incoming row outright. That is right for a listing, which is authoritative about the
    source it just read, and wrong here: a fetch that comes back without a thumbnail
    would erase the one the library already had. So the cache row gets its own merging
    upsert, and songs goes through upsert_songs with the payload pruned to the columns
    that are actually blank.

    `refresh` skips that pruning and lets the fetch win every column it filled, which is
    what to ask for when the stored values are stale rather than missing.
    """
    if not batch:
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        statement = _fetch_merge_sql(refresh=refresh)
        for info, _song in batch:
            conn.execute(
                statement,
                (
                    info["video_id"],
                    info["title"],
                    info["channel_name"],
                    info["upload_date"],
                    info["duration"],
                    info["thumbnail_url"],
                    info["video_url"],
                    info["cached_at"],
                ),
            )
        conn.commit()

        songs = [song for _info, song in batch]
        if not refresh:
            stored = _stored_song_rows(conn, [song["video_id"] for song in songs])
            songs = [_prune_to_blanks(song, stored.get(song["video_id"])) for song in songs]
    finally:
        conn.close()

    upsert_songs(db_path, songs)


def run_network_pass(
    db_path: str,
    config: dict[str, Any],
    video_ids: list[str],
    *,
    flush_every: int,
    refresh: bool,
) -> int:
    """Fetch and merge, flushing as results arrive so a stopped run keeps its progress."""
    token = CancellationToken()
    buffer: list[tuple[dict[str, Any], dict[str, Any]]] = []
    written = 0
    started = time.monotonic()

    def on_video(video_id: str, data: dict[str, Any]) -> None:
        nonlocal written
        pair = _payloads(data)
        if pair is None:
            return
        buffer.append(pair)
        if len(buffer) >= flush_every:
            write_fetched(db_path, buffer, refresh=refresh)
            written += len(buffer)
            buffer.clear()
            elapsed = max(1e-6, time.monotonic() - started)
            rate = written / elapsed
            remaining = (len(video_ids) - written) / rate if rate else 0
            print(
                f"  {written:>7,} of {len(video_ids):,} merged"
                f"  ({rate:.1f}/s, about {remaining / 60:.0f} min left)",
                flush=True,
            )

    # fetch_metadata_batch calls on_video under its own lock, so the buffer above needs
    # none of its own and a flush can safely touch the database from inside it.
    fetch_metadata_batch(video_ids, config, token, logger=None, on_video=on_video)

    write_fetched(db_path, buffer, refresh=refresh)
    written += len(buffer)
    return written


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def backup_database(db_path: str) -> Path:
    """A consistent copy, taken through SQLite rather than the file system.

    Copying the file would leave the write-ahead log behind, and this database keeps
    megabytes of committed data there. The backup API folds the WAL into the copy.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = Path(db_path).with_suffix(f".backup-{stamp}.db")
    source = sqlite3.connect(db_path)
    try:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()
    return target


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m yt_aio.application.db.backfill",
        description="Fill the blank columns in the yt_aio database, keyed on video_id.",
    )
    parser.add_argument("--db", help="Database file. Defaults to the one config.json names.")
    parser.add_argument(
        "--network",
        action="store_true",
        help="Also ask yt-dlp for the videos the local passes cannot finish.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Fetch at most this many videos in the network pass. Re-run for the rest.",
    )
    parser.add_argument(
        "--derive-albums",
        action="store_true",
        help="Infer album year and artwork from the album's own tracks.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what each pass would fill and write nothing.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Let a fetch replace stored values too, not only fill blank ones.",
    )
    parser.add_argument("--no-backup", action="store_true", help="Skip the pre-run backup copy.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.db:
        db_path = str(Path(args.db).expanduser().resolve())
    else:
        config_for_path = resolve_runtime_config(load_config(CONFIG_PATH))
        db_path = config_for_path.get("log_file_path") or ""
    if not db_path or not Path(db_path).exists():
        print(f"No database at {db_path or '(unset)'}.", file=sys.stderr)
        return 1

    config = resolve_runtime_config(load_config(CONFIG_PATH))
    print(f"Database: {db_path}")

    if not args.dry_run and not args.no_backup:
        print(f"Backup:   {backup_database(db_path)}")

    # init_db is what the application calls on every start. It adds any column this
    # database predates, so the passes below can assume the current schema.
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        print_census(conn, "Blanks before:")

        print("Local passes:")
        # First, because the passes that link a download to its cache row and to its file
        # both key on downloads.video_id, and this is what puts one there.
        filled = fill_download_video_ids(conn, dry_run=args.dry_run)
        filled += run_passes(conn, LOCAL_PASSES, dry_run=args.dry_run)
        if args.derive_albums:
            filled += run_passes(conn, DERIVED_PASSES, dry_run=args.dry_run)
        if not filled:
            print("  nothing left that one table can answer for another")
        if not args.dry_run:
            conn.commit()

        pending = network_candidates(conn, args.limit)
    finally:
        conn.close()

    if not args.network:
        if pending:
            print(
                f"\n{len(pending):,} videos still need a metadata fetch. "
                "Re-run with --network to collect them."
            )
    elif args.dry_run:
        print(f"\nWould fetch metadata for {len(pending):,} videos.")
    elif pending:
        print(f"\nNetwork pass: {len(pending):,} videos, {config.get('max_metadata_workers', 4)} workers")
        try:
            written = run_network_pass(
                db_path, config, pending, flush_every=100, refresh=args.refresh
            )
        except KeyboardInterrupt:
            print("\nStopped. Everything merged so far is saved; re-run to continue.")
            return 130
        print(f"  merged {written:,} of {len(pending):,}")

        # The fetch fills upload dates and thumbnails the derived album passes read, so
        # they are worth a second run once it is done.
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            if args.derive_albums:
                print("Derived passes, second run:")
                run_passes(conn, DERIVED_PASSES, dry_run=False)
                conn.commit()
            print_census(conn, "Blanks after:")
        finally:
            conn.close()
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        print_census(conn, "Blanks after:" if not args.dry_run else "Blanks now (nothing written):")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
