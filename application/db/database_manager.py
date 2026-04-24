from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from ... import APP_CHANGELOG, APP_VERSION


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
                view_count INTEGER,
                like_count INTEGER,
                dislike_count INTEGER,
                comment_count INTEGER,
                thumbnail_url TEXT,
                video_url TEXT,
                source_id INTEGER,
                cached_at TEXT,
                FOREIGN KEY(source_id) REFERENCES sources(id)
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
            """
        )

        _ensure_column(conn, "downloads", "video_id", "TEXT")
        _ensure_column(conn, "downloads", "video_info_id", "INTEGER")
        _ensure_column(conn, "downloads", "source_id", "INTEGER")
        _ensure_column(conn, "youtube_video_information", "source_id", "INTEGER")
        _ensure_column(conn, "youtube_video_information", "cached_at", "TEXT")

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

        _backfill_relations(conn)

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
                view_count, like_count, dislike_count, comment_count, thumbnail_url,
                video_url, source_id, cached_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                title = excluded.title,
                channel_name = excluded.channel_name,
                playlist_name = excluded.playlist_name,
                upload_date = excluded.upload_date,
                duration = excluded.duration,
                view_count = excluded.view_count,
                like_count = excluded.like_count,
                dislike_count = excluded.dislike_count,
                comment_count = excluded.comment_count,
                thumbnail_url = excluded.thumbnail_url,
                video_url = excluded.video_url,
                source_id = COALESCE(excluded.source_id, youtube_video_information.source_id),
                cached_at = excluded.cached_at
            """,
            (
                video_id,
                payload.get("title"),
                payload.get("channel_name"),
                payload.get("playlist_name"),
                payload.get("upload_date"),
                payload.get("duration"),
                payload.get("view_count"),
                payload.get("like_count"),
                payload.get("dislike_count"),
                payload.get("comment_count"),
                payload.get("thumbnail_url"),
                payload.get("video_url"),
                payload.get("source_id"),
                payload.get("cached_at"),
            ),
        )
        row = conn.execute(
            "SELECT id FROM youtube_video_information WHERE video_id = ?",
            (video_id,),
        ).fetchone()
        return int(row["id"]) if row else None


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
