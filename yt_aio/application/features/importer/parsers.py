"""Backup file parsing.

Owns:   turning a file exported by a phone app into a list of YouTube items.
Reads:  the file the operator chose. Never writes to it.
Writes: nothing.
Runs:   nothing. Pure Python, no Qt, so it can be run and tested head-less.

Format is detected from the file's own bytes, not from its extension, because backup
files are routinely handed over with the wrong suffix or none at all. Supported:
SQLite databases, ZIP archives containing any supported file, JSON, CSV and plain text.
Anything else is scanned as text, which still finds links inside an unknown wrapper.

A SQLite backup whose schema is recognised is read by that schema instead of scanned
table by table; see opentune.py and vitune.py. The blind scan stays as the fallback for
everything else, and it is the wrong tool whenever the layout is actually known.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

from .models import (
    BARE_ID_RE,
    VIDEO_URL_RE,
    ImportedItem,
    canonical_url,
    coerce_duration,
    dedupe,
)
from .opentune import looks_like_opentune, parse_opentune
from .vitune import looks_like_vitune, parse_vitune

LogFn = Callable[[str], None]

SQLITE_MAGIC = b"SQLite format 3\x00"
ZIP_MAGIC = b"PK\x03\x04"

MAX_TEXT_BYTES = 64 * 1024 * 1024
MAX_ROWS_PER_TABLE = 200_000
MAX_ZIP_MEMBER_BYTES = 256 * 1024 * 1024

TITLE_FIELDS = ("title", "name", "stream_title", "video_title", "track", "song")
CHANNEL_FIELDS = ("uploader", "channel", "channel_name", "author", "artist", "uploader_name")
DURATION_FIELDS = ("duration", "length", "duration_seconds", "seconds")
DATE_FIELDS = ("upload_date", "upload_time", "published", "publish_date", "date", "added_at")


def _first_field(record: dict[str, Any], names: tuple[str, ...]) -> Any:
    lowered = {str(key).lower(): value for key, value in record.items()}
    for name in names:
        if lowered.get(name) not in (None, ""):
            return lowered[name]
    return None


def _ids_in(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    text = str(value)
    found = VIDEO_URL_RE.findall(text)
    if found:
        return found
    return [text] if BARE_ID_RE.match(text.strip()) else []


def _item_from_record(record: dict[str, Any], origin: str) -> list[ImportedItem]:
    """Pull every video this record refers to, carrying whatever metadata sits beside it."""
    ids: list[str] = []
    for key, value in record.items():
        if isinstance(value, (dict, list)):
            continue
        # A bare id only counts when the column says it is one; an arbitrary 11
        # character string is not a video id.
        if BARE_ID_RE.match(str(value or "").strip()) and "id" not in str(key).lower():
            continue
        ids.extend(_ids_in(value))

    if not ids:
        return []

    title = _first_field(record, TITLE_FIELDS)
    channel = _first_field(record, CHANNEL_FIELDS)
    duration = coerce_duration(_first_field(record, DURATION_FIELDS))
    uploaded = _first_field(record, DATE_FIELDS)

    items = []
    for video_id in dict.fromkeys(ids):
        items.append(
            ImportedItem(
                video_id=video_id,
                url=canonical_url(video_id),
                title=str(title).strip() if title else "",
                channel_name=str(channel).strip() if channel else "",
                duration_seconds=duration,
                upload_date=str(uploaded).strip() if uploaded else "",
                origin=origin,
            )
        )
    return items


# --------------------------------------------------------------------- formats
def _scan_every_table(conn: sqlite3.Connection, name: str, origin: str, log: LogFn) -> list[ImportedItem]:
    """The fallback: pull ids out of whatever tables happen to be there."""
    items: list[ImportedItem] = []
    tables = [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    log(f"Schema not recognised. Scanning all {len(tables)} table(s) in {name}.")
    for table in tables:
        try:
            rows = conn.execute(f'SELECT * FROM "{table}" LIMIT {MAX_ROWS_PER_TABLE}').fetchall()
        except sqlite3.Error as exc:
            log(f"Skipped table {table}: {exc}")
            continue
        found: list[ImportedItem] = []
        for row in rows:
            found.extend(_item_from_record({key: row[key] for key in row.keys()}, f"{origin}:{table}"))
        if found:
            log(f"  {table}: {len(found)} item(s) from {len(rows)} row(s).")
        items.extend(found)
    return items


def parse_sqlite(path: Path, log: LogFn, origin: str = "") -> tuple[list[ImportedItem], str]:
    """Read a database another app wrote. Returns the items and the schema used.

    Opened read-only through a URI so a backup can never be modified by being read.
    A known schema is read by its own reader; anything else falls back to the scan.
    """
    origin = origin or path.name
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if looks_like_opentune(conn):
            return parse_opentune(conn, log, origin), "OpenTune backup"
        if looks_like_vitune(conn):
            return parse_vitune(conn, log, origin), "ViTune backup"
        return _scan_every_table(conn, path.name, origin, log), "SQLite database"
    finally:
        conn.close()


def parse_json(text: str, log: LogFn, origin: str) -> list[ImportedItem]:
    data = json.loads(text)
    items: list[ImportedItem] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            items.extend(_item_from_record(node, origin))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str):
            for video_id in VIDEO_URL_RE.findall(node):
                items.append(ImportedItem(video_id=video_id, url=canonical_url(video_id), origin=origin))

    walk(data)
    log(f"Read {len(items)} item(s) from JSON.")
    return items


def parse_csv(text: str, log: LogFn, origin: str) -> list[ImportedItem]:
    try:
        dialect = csv.Sniffer().sniff(text[:8192])
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    items: list[ImportedItem] = []
    for record in reader:
        items.extend(_item_from_record({k: v for k, v in record.items() if k}, origin))
    log(f"Read {len(items)} item(s) from {len(reader.fieldnames or [])} CSV column(s).")
    return items


def parse_text(text: str, log: LogFn, origin: str) -> list[ImportedItem]:
    ids = VIDEO_URL_RE.findall(text)
    log(f"Found {len(ids)} link(s) by scanning the file as text.")
    return [ImportedItem(video_id=video_id, url=canonical_url(video_id), origin=origin) for video_id in ids]


def _parse_bytes(payload: bytes, name: str, log: LogFn) -> tuple[list[ImportedItem], str]:
    """Dispatch on the content itself. Returns the items and a label for the format."""
    if payload.startswith(SQLITE_MAGIC):
        with tempfile.TemporaryDirectory() as tmp:
            # Member names are never trusted for a path; only the basename is used, and
            # only inside a directory we created. That is what closes zip-slip.
            target = Path(tmp) / (os.path.basename(name) or "backup.db")
            target.write_bytes(payload)
            return parse_sqlite(target, log, origin=name)

    text = payload.decode("utf-8", errors="replace")
    stripped = text.lstrip()
    if stripped[:1] in "{[":
        try:
            return parse_json(text, log, name), "JSON"
        except json.JSONDecodeError as exc:
            log(f"Not valid JSON ({exc.msg}); falling back to a text scan.")
    elif "," in text[:4096] or "\t" in text[:4096]:
        try:
            items = parse_csv(text, log, name)
            if items:
                return items, "CSV"
        except csv.Error as exc:
            log(f"Not valid CSV ({exc}); falling back to a text scan.")

    return parse_text(text, log, name), "Plain text"


def parse_zip(path: Path, log: LogFn) -> tuple[list[ImportedItem], str]:
    items: list[ImportedItem] = []
    formats: list[str] = []
    with zipfile.ZipFile(path) as archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        log(f"Archive holds {len(members)} file(s).")
        for info in members:
            if info.file_size > MAX_ZIP_MEMBER_BYTES:
                log(f"Skipped {info.filename}: {info.file_size} bytes is over the limit.")
                continue
            payload = archive.read(info)
            found, label = _parse_bytes(payload, info.filename, log)
            if found:
                log(f"  {info.filename}: {len(found)} item(s) as {label}.")
                formats.append(label)
            items.extend(found)
    label = f"ZIP archive ({', '.join(dict.fromkeys(formats))})" if formats else "ZIP archive"
    return items, label


def parse_backup_file(path: str | Path, log: LogFn) -> tuple[list[ImportedItem], str]:
    """Parse one exported file. Returns the deduplicated items and the detected format.

    Raises FileNotFoundError when the path is not a readable file, and ValueError when
    the file is larger than this parser will read.
    """
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise FileNotFoundError(f"Not a readable file: {file_path}")

    size = file_path.stat().st_size
    log(f"Reading {file_path.name}, {size} bytes.")

    header = file_path.open("rb").read(len(SQLITE_MAGIC))
    if header.startswith(SQLITE_MAGIC):
        items, label = parse_sqlite(file_path, log)
    elif header.startswith(ZIP_MAGIC):
        items, label = parse_zip(file_path, log)
    else:
        if size > MAX_TEXT_BYTES:
            raise ValueError(f"File is {size} bytes, over the {MAX_TEXT_BYTES} byte text limit.")
        items, label = _parse_bytes(file_path.read_bytes(), file_path.name, log)

    unique = dedupe(items)
    log(f"Detected format: {label}. {len(items)} raw item(s), {len(unique)} unique video(s).")
    return unique, label
