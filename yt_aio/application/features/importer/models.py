"""What an import produces.

Owns:   ImportedItem, the one row shape every parser returns.
Reads:  nothing.
Writes: nothing.
Runs:   nothing. Pure Python, no Qt, so it can be run and tested head-less.

Split out of parsers.py so the schema-aware readers (opentune.py) and the generic
scanners can share one row type without importing each other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# youtu.be/ID, watch?v=ID, shorts/ID, embed/ID, v/ID, live/ID, and a bare 11-char id
# in a field named like a video id. The id alphabet is fixed at 11 URL-safe characters.
VIDEO_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.|music\.)?"
    r"(?:youtube\.com/(?:watch\?(?:[^\s\"'<>]*&)?v=|shorts/|embed/|v/|live/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)
BARE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# Where an item came from inside the backup. A phone music app caches far more songs
# than the operator ever saved, so the collection is what separates "my library" from
# "something the recommendation engine touched once".
COLLECTION_LIBRARY = "Library"
COLLECTION_LIKED = "Liked"
COLLECTION_DOWNLOADED = "Downloaded"
COLLECTION_PLAYLIST = "Playlist"
COLLECTION_ALBUM = "Album"
COLLECTION_HISTORY = "History"
COLLECTION_CACHED = "Cached"

# Most to least deliberate. The first one an item carries is the one shown.
COLLECTION_ORDER = [
    COLLECTION_DOWNLOADED,
    COLLECTION_LIKED,
    COLLECTION_LIBRARY,
    COLLECTION_PLAYLIST,
    COLLECTION_ALBUM,
    COLLECTION_HISTORY,
    COLLECTION_CACHED,
]


@dataclass
class ImportedItem:
    video_id: str
    url: str
    title: str = ""
    channel_name: str = ""
    duration_seconds: int | None = None
    upload_date: str = ""
    origin: str = ""
    album: str = ""
    artists: str = ""
    playlists: str = ""
    thumbnail_url: str = ""
    bitrate_label: str = ""
    play_count: int = 0
    collections: list[str] = field(default_factory=list)

    @property
    def display_title(self) -> str:
        return self.title or self.video_id

    @property
    def collection_label(self) -> str:
        """The strongest signal this item carries, for the grid's Collection column."""
        for name in COLLECTION_ORDER:
            if name in self.collections:
                return name
        return self.collections[0] if self.collections else COLLECTION_CACHED


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def coerce_duration(value: Any) -> int | None:
    """Backup files store duration as seconds, as milliseconds, or as 'mm:ss'."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        seconds = int(value)
        # NewPipe and several others store milliseconds. Nothing on YouTube runs for
        # more than a day, so a value that large is a millisecond count.
        return seconds // 1000 if seconds > 86_400 else seconds
    text = str(value).strip()
    if text.isdigit():
        return coerce_duration(int(text))
    if ":" in text:
        parts = text.split(":")
        try:
            numbers = [int(part) for part in parts]
        except ValueError:
            return None
        total = 0
        for number in numbers:
            total = total * 60 + number
        return total
    return None


def dedupe(items: list[ImportedItem]) -> list[ImportedItem]:
    """First occurrence wins, but a later richer copy fills in what the first lacked."""
    merged: dict[str, ImportedItem] = {}
    for item in items:
        existing = merged.get(item.video_id)
        if existing is None:
            merged[item.video_id] = item
            continue
        existing.title = existing.title or item.title
        existing.channel_name = existing.channel_name or item.channel_name
        existing.duration_seconds = existing.duration_seconds or item.duration_seconds
        existing.upload_date = existing.upload_date or item.upload_date
        existing.album = existing.album or item.album
        existing.artists = existing.artists or item.artists
        existing.thumbnail_url = existing.thumbnail_url or item.thumbnail_url
        existing.bitrate_label = existing.bitrate_label or item.bitrate_label
        existing.play_count = max(existing.play_count, item.play_count)
        existing.playlists = existing.playlists or item.playlists
        for name in item.collections:
            if name not in existing.collections:
                existing.collections.append(name)
    return list(merged.values())
