"""Comparing files on disk against what the database already knows.

Owns:   the local_files table's read and write path, and the matching that fills it.
Reads:  youtube_video_information and downloads, to decide what a local file is.
Writes: local_files rows. Never touches a file on disk, and never deletes a download
        record or a cached video row.
Runs:   nothing.

The question this answers is "have I already got this?", so a wrong yes is the
expensive mistake: it would stop a download the operator actually wanted. Matching is
therefore graded rather than boolean, and only the two exact signals claim certainty:

  In database      the file's own video id, or its path, is already recorded
  Probable match   the title agrees and the duration is within a few seconds
  Title clash      the title agrees but the duration does not, so a person must look
  New              nothing in the database resembles it
"""

from __future__ import annotations

from typing import Any, Callable

from ..utils.local_library import LocalTrack, normalise_title
from ..utils.shared import now_string
from .database_manager import _connect, _row_to_dict, _table_columns, init_db

LogFn = Callable[[str], None]

STATUS_IN_DATABASE = "In database"
STATUS_PROBABLE = "Probable match"
STATUS_CLASH = "Title clash"
STATUS_NEW = "New"

# How far two durations may differ and still be the same recording. A yt-dlp download
# and a tagged rip of one song routinely differ by a second or two of trailing silence.
DURATION_TOLERANCE_SECONDS = 4

MAX_PAGE_SIZE = 2000

# Heading -> the SQL that orders by it. The grid may only name a key from this map,
# which is what keeps an ORDER BY clause out of reach of anything typed in the UI.
LOCAL_SORTS: dict[str, str] = {
    "file_name": "COALESCE(l.file_name, '') COLLATE NOCASE",
    "title": "COALESCE(NULLIF(l.title, ''), l.file_name, '') COLLATE NOCASE",
    "artist": "COALESCE(l.artist, '') COLLATE NOCASE",
    "album": "COALESCE(l.album, '') COLLATE NOCASE",
    "duration": "COALESCE(l.duration, -1)",
    "bitrate": "COALESCE(l.bitrate, -1)",
    "video_id": "COALESCE(l.video_id, '')",
    "match_status": "COALESCE(l.match_status, '')",
    "size_bytes": "COALESCE(l.size_bytes, -1)",
    "modified_at": "COALESCE(l.modified_at, '')",
    "first_seen_at": "COALESCE(l.first_seen_at, '')",
}
DEFAULT_LOCAL_SORT = "match_status"


class _Index:
    """Everything needed to classify a file, read from the database once per scan.

    A scan asks the same three questions of every file. Three queries per file over a
    few thousand files is thousands of round trips; the whole cache is a few megabytes.
    """

    def __init__(self, conn) -> None:
        self.by_video_id: dict[str, dict[str, Any]] = {}
        self.by_title: dict[str, list[dict[str, Any]]] = {}
        self.downloaded_paths: dict[str, dict[str, Any]] = {}

        for row in conn.execute(
            "SELECT id, video_id, title, channel_name, duration FROM youtube_video_information"
        ):
            record = _row_to_dict(row)
            if record["video_id"]:
                self.by_video_id[str(record["video_id"])] = record
            key = normalise_title(record["title"] or "")
            if key:
                self.by_title.setdefault(key, []).append(record)

        for row in conn.execute(
            """
            SELECT file_path, video_id, video_info_id, title
            FROM downloads
            WHERE file_path IS NOT NULL AND file_path <> '' AND status = 'success'
            """
        ):
            self.downloaded_paths[str(row["file_path"])] = _row_to_dict(row)


def _duration_gap(left: int | None, right: int | None) -> int | None:
    if left is None or right is None:
        return None
    return abs(int(left) - int(right))


def classify(track: LocalTrack, index: _Index) -> tuple[str, str, int | None]:
    """Decide what one local file is. Returns (status, explanation, video_info_id)."""
    downloaded = index.downloaded_paths.get(track.file_path)
    if downloaded is not None:
        named = f" as {downloaded['title']}" if downloaded.get("title") else ""
        return (
            STATUS_IN_DATABASE,
            f"This application downloaded this exact file{named}.",
            downloaded.get("video_info_id"),
        )

    if track.video_id:
        cached = index.by_video_id.get(track.video_id)
        if cached is not None:
            return (
                STATUS_IN_DATABASE,
                f"The file carries video id {track.video_id}, already cached as "
                f"{cached.get('title') or 'an untitled row'}.",
                cached.get("id"),
            )
        return (
            STATUS_NEW,
            f"The file carries video id {track.video_id}, which is not in the database.",
            None,
        )

    key = normalise_title(track.display_title)
    candidates = index.by_title.get(key, []) if key else []
    if not candidates:
        return STATUS_NEW, "No cached row has a title like this one.", None

    # Prefer the closest duration, so one good candidate is not hidden behind a bad one.
    scored = sorted(
        candidates,
        key=lambda row: _duration_gap(track.duration, row.get("duration")) or 10**6,
    )
    best = scored[0]
    gap = _duration_gap(track.duration, best.get("duration"))

    if gap is not None and gap <= DURATION_TOLERANCE_SECONDS:
        return (
            STATUS_PROBABLE,
            f"Same title as {best.get('title')}, and the durations differ by {gap}s.",
            best.get("id"),
        )

    if gap is None:
        return (
            STATUS_CLASH,
            f"Same title as {best.get('title')}, but one of the two has no duration to compare.",
            best.get("id"),
        )

    return (
        STATUS_CLASH,
        f"Same title as {best.get('title')}, but the durations differ by {gap}s "
        f"({track.duration}s here against {best.get('duration')}s in the database).",
        best.get("id"),
    )


def record_scan(
    db_path: str,
    root_path: str,
    tracks: list[LocalTrack],
    log: LogFn,
    *,
    forget_missing: bool = True,
) -> dict[str, Any]:
    """Classify a scan's tracks and store them. Returns a summary of what was found.

    A file recorded under this root by an earlier scan but absent now is dropped when
    forget_missing is set, which is what makes a rescan report the folder as it is
    rather than as it once was.
    """
    stamp = now_string()
    init_db(db_path)

    with _connect(db_path) as conn:
        index = _Index(conn)
        log(
            f"Comparing against {len(index.by_video_id)} cached video(s) and "
            f"{len(index.downloaded_paths)} downloaded file(s)."
        )

        known_before = {
            str(row["file_path"])
            for row in conn.execute(
                "SELECT file_path FROM local_files WHERE root_path = ?", (str(root_path),)
            )
        }

        counts: dict[str, int] = {
            STATUS_IN_DATABASE: 0,
            STATUS_PROBABLE: 0,
            STATUS_CLASH: 0,
            STATUS_NEW: 0,
        }
        new_since_last_scan = 0

        for track in tracks:
            status, detail, video_info_id = classify(track, index)
            counts[status] = counts.get(status, 0) + 1
            if track.file_path not in known_before:
                new_since_last_scan += 1

            conn.execute(
                """
                INSERT INTO local_files (
                    file_path, root_path, file_name, extension, size_bytes, modified_at,
                    title, artist, album, duration, bitrate, video_id, tag_source,
                    match_status, match_detail, matched_video_info_id, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    root_path = excluded.root_path,
                    file_name = excluded.file_name,
                    extension = excluded.extension,
                    size_bytes = excluded.size_bytes,
                    modified_at = excluded.modified_at,
                    title = excluded.title,
                    artist = excluded.artist,
                    album = excluded.album,
                    duration = excluded.duration,
                    bitrate = excluded.bitrate,
                    video_id = excluded.video_id,
                    tag_source = excluded.tag_source,
                    match_status = excluded.match_status,
                    match_detail = excluded.match_detail,
                    matched_video_info_id = excluded.matched_video_info_id,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    track.file_path, str(root_path), track.file_name, track.extension,
                    track.size_bytes, track.modified_at, track.title or None,
                    track.artist or None, track.album or None, track.duration,
                    track.bitrate, track.video_id or None, track.tag_source,
                    status, detail, video_info_id, stamp, stamp,
                ),
            )

        removed = 0
        if forget_missing:
            seen = {track.file_path for track in tracks}
            gone = [path for path in known_before if path not in seen]
            for path in gone:
                conn.execute("DELETE FROM local_files WHERE file_path = ?", (path,))
            removed = len(gone)

    log(
        f"{counts[STATUS_IN_DATABASE]} already in the database, "
        f"{counts[STATUS_PROBABLE]} probable match(es), "
        f"{counts[STATUS_CLASH]} title clash(es), {counts[STATUS_NEW]} new."
    )
    if new_since_last_scan:
        log(f"{new_since_last_scan} file(s) were not here at the previous scan of this folder.")
    if removed:
        log(f"{removed} file(s) recorded by an earlier scan are no longer on disk; forgotten.")

    return {
        "root_path": str(root_path),
        "scanned_at": stamp,
        "total": len(tracks),
        "counts": counts,
        "new_since_last_scan": new_since_last_scan,
        "forgotten": removed,
    }


def _local_filters(
    root_path: str,
    search: str,
    status: str,
    artist: str,
    min_duration: int | None,
    max_duration: int | None,
    only_untagged: bool,
) -> tuple[str, list[Any]]:
    """Build the WHERE clause. Columns are qualified because the read joins two tables."""
    clauses: list[str] = []
    params: list[Any] = []

    if root_path.strip():
        clauses.append("l.root_path = ?")
        params.append(root_path.strip())

    if search.strip():
        needle = f"%{search.strip()}%"
        clauses.append(
            "(COALESCE(l.title, '') LIKE ? OR COALESCE(l.file_name, '') LIKE ? "
            "OR COALESCE(l.artist, '') LIKE ? OR COALESCE(l.album, '') LIKE ? "
            "OR COALESCE(l.video_id, '') LIKE ?)"
        )
        params.extend([needle] * 5)

    if status.strip() and status != "Everything":
        clauses.append("l.match_status = ?")
        params.append(status)

    if artist.strip():
        clauses.append("COALESCE(l.artist, '') LIKE ?")
        params.append(f"%{artist.strip()}%")

    # A file whose duration could not be read is excluded by any duration filter. It
    # cannot be shown to satisfy a range when nothing is known about its length.
    if min_duration:
        clauses.append("l.duration IS NOT NULL AND l.duration >= ?")
        params.append(int(min_duration))
    if max_duration:
        clauses.append("l.duration IS NOT NULL AND l.duration <= ?")
        params.append(int(max_duration))

    if only_untagged:
        clauses.append("(COALESCE(l.title, '') = '' OR l.tag_source = 'filename')")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def _order_clause(sort_key: str, descending: bool) -> str:
    expression = LOCAL_SORTS.get(sort_key) or LOCAL_SORTS[DEFAULT_LOCAL_SORT]
    direction = "DESC" if descending else "ASC"
    # l.id breaks ties so paging stays stable when the sorted values are equal.
    return f"{expression} {direction}, l.id {direction}"


def fetch_local_files(
    db_path: str,
    *,
    root_path: str = "",
    search: str = "",
    status: str = "Everything",
    artist: str = "",
    min_duration: int | None = None,
    max_duration: int | None = None,
    only_untagged: bool = False,
    sort_key: str = DEFAULT_LOCAL_SORT,
    descending: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """One page of scanned files, plus the total the filters match."""
    limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    offset = max(0, int(offset))

    init_db(db_path)
    with _connect(db_path) as conn:
        where, params = _local_filters(
            root_path, search, status, artist, min_duration, max_duration, only_untagged
        )
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM local_files l {where}", params
        ).fetchone()["n"]
        rows = conn.execute(
            f"""
            SELECT l.*, v.title AS matched_title, v.channel_name AS matched_channel,
                   v.duration AS matched_duration, v.video_id AS matched_video_id
            FROM local_files l
            LEFT JOIN youtube_video_information v ON v.id = l.matched_video_info_id
            {where}
            ORDER BY {_order_clause(sort_key, descending)}
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        return [_row_to_dict(row) for row in rows], int(total)


def fetch_local_roots(db_path: str) -> list[dict[str, Any]]:
    """Every folder that has been scanned, with its counts."""
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT root_path,
                   COUNT(*) AS total,
                   SUM(CASE WHEN match_status = ? THEN 1 ELSE 0 END) AS in_database,
                   SUM(CASE WHEN match_status = ? THEN 1 ELSE 0 END) AS probable,
                   SUM(CASE WHEN match_status = ? THEN 1 ELSE 0 END) AS clashes,
                   SUM(CASE WHEN match_status = ? THEN 1 ELSE 0 END) AS new_files,
                   MAX(last_seen_at) AS last_scanned
            FROM local_files
            WHERE root_path IS NOT NULL AND root_path <> ''
            GROUP BY root_path
            ORDER BY root_path
            """,
            (STATUS_IN_DATABASE, STATUS_PROBABLE, STATUS_CLASH, STATUS_NEW),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]


def fetch_local_artists(db_path: str, root_path: str = "") -> list[str]:
    """Distinct artists among the scanned files, for the filter drop-down."""
    init_db(db_path)
    with _connect(db_path) as conn:
        if root_path.strip():
            rows = conn.execute(
                "SELECT DISTINCT artist FROM local_files "
                "WHERE artist IS NOT NULL AND artist <> '' AND root_path = ? "
                "ORDER BY artist COLLATE NOCASE",
                (root_path.strip(),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT artist FROM local_files "
                "WHERE artist IS NOT NULL AND artist <> '' ORDER BY artist COLLATE NOCASE"
            ).fetchall()
        return [str(row["artist"]) for row in rows]


def forget_root(db_path: str, root_path: str) -> int:
    """Drop one folder's scan results. Files on disk are never touched."""
    init_db(db_path)
    with _connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM local_files WHERE root_path = ?", (str(root_path),))
        return int(cursor.rowcount or 0)


def local_file_columns(db_path: str) -> set[str]:
    init_db(db_path)
    with _connect(db_path) as conn:
        return _table_columns(conn, "local_files")
