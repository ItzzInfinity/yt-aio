"""Reading audio files that are already on disk.

Owns:   walking a folder and pulling the tags out of the audio files in it.
Reads:  the files it is pointed at. Never writes to them.
Writes: nothing.
Runs:   ffprobe, but only for a file mutagen could not read.

No Qt and no database, so a scan can be run and tested head-less.

Three readers, tried in order, because no single one covers everything:
mutagen for tags and duration, ffprobe for the containers mutagen declines, and the
file name itself, which is the only thing left for an untagged file. Whichever answered
is recorded on the track, so the panel can say where a value came from.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

LogFn = Callable[[str], None]

# .webm is here because yt-dlp's bestaudio commonly lands as opus in a webm container.
AUDIO_EXTENSIONS = {
    ".mp3", ".m4a", ".m4b", ".aac", ".flac", ".wav", ".aiff", ".aif", ".ogg", ".oga",
    ".opus", ".wma", ".alac", ".ape", ".wv", ".mpc", ".dsf", ".mka", ".webm",
}

# yt-dlp's default output template ends with the id in square brackets, and
# --add-metadata writes the watch URL into a tag. Either one identifies the video exactly.
FILENAME_ID_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\](?=\.[^.]+$|$)")
TAG_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.|music\.)?"
    r"(?:youtube\.com/(?:watch\?(?:[^\s\"'<>]*&)?v=|shorts/|embed/|v/|live/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)

# Stripped before two titles are compared. A download and a rip of the same song rarely
# agree on these, and they carry no information about which song it is. Words that turn
# up in real titles stay out of this set: dropping "song" or "full" would collapse
# "Full Moon" and "Moon" into one title.
NOISE_WORDS = {
    "official", "video", "audio", "lyric", "lyrics", "hd", "hq", "4k", "8k",
    "remaster", "remastered", "mv", "visualizer", "explicit",
}

TITLE_KEYS = ("title", "\xa9nam", "TIT2", "TITLE", "Title")
ARTIST_KEYS = ("artist", "\xa9ART", "TPE1", "ARTIST", "albumartist", "aART", "Author")
ALBUM_KEYS = ("album", "\xa9alb", "TALB", "ALBUM", "Album")

FFPROBE_TIMEOUT = 20


@dataclass
class LocalTrack:
    """One audio file found on disk."""

    file_path: str
    file_name: str
    root_path: str
    extension: str
    size_bytes: int
    modified_at: str
    title: str = ""
    artist: str = ""
    album: str = ""
    duration: int | None = None
    bitrate: int | None = None
    video_id: str = ""
    tag_source: str = "filename"

    @property
    def display_title(self) -> str:
        return self.title or Path(self.file_name).stem


def normalise_title(text: str) -> str:
    """Reduce a title to what two copies of the same song would agree on.

    Bracketed asides, the noise words above, punctuation and case all vary between a
    yt-dlp download and a tagged rip, so none of them can take part in a comparison.
    """
    if not text:
        return ""
    lowered = str(text).casefold()
    lowered = re.sub(r"\[[^\]]*\]|\([^)]*\)|\{[^}]*\}", " ", lowered)
    # A regex class cannot do this: \w excludes combining marks, which splits every
    # Bengali or Devanagari word into single letters. Keeping marks holds them together.
    letters = [
        character if character.isalnum() or unicodedata.category(character).startswith("M") else " "
        for character in lowered
    ]
    words = [word for word in "".join(letters).split() if word]
    kept = [word for word in words if word not in NOISE_WORDS]
    return " ".join(kept or words)


def _first_tag(tags: Any, keys: tuple[str, ...]) -> str:
    """Read the first key any of these tag dialects actually used."""
    if tags is None:
        return ""
    for key in keys:
        try:
            value = tags[key]
        except (KeyError, TypeError, ValueError):
            continue
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        text = str(value).strip()
        if text:
            return text
    return ""


def _video_id_from_tags(tags: Any) -> str:
    """Scan every tag value for a watch URL.

    Which tag --add-metadata lands the URL in depends on the container and the ffmpeg
    build, so reading one named tag would miss most files. Searching every value does not.
    """
    if tags is None:
        return ""
    try:
        values = list(tags.values())
    except AttributeError:
        try:
            values = [tags[key] for key in tags.keys()]
        except Exception:
            return ""
    for value in values:
        match = TAG_URL_RE.search(str(value))
        if match:
            return match.group(1)
    return ""


def _read_with_mutagen(path: Path) -> dict[str, Any] | None:
    try:
        import mutagen
    except ImportError:
        return None

    try:
        raw = mutagen.File(str(path))
    except Exception:
        return None
    if raw is None:
        return None

    info = getattr(raw, "info", None)
    length = getattr(info, "length", None)
    bitrate = getattr(info, "bitrate", None)

    try:
        easy = mutagen.File(str(path), easy=True)
    except Exception:
        easy = None

    tags = getattr(raw, "tags", None)
    easy_tags = getattr(easy, "tags", None) if easy is not None else None

    return {
        "title": _first_tag(easy_tags, TITLE_KEYS) or _first_tag(tags, TITLE_KEYS),
        "artist": _first_tag(easy_tags, ARTIST_KEYS) or _first_tag(tags, ARTIST_KEYS),
        "album": _first_tag(easy_tags, ALBUM_KEYS) or _first_tag(tags, ALBUM_KEYS),
        "duration": int(length) if length else None,
        "bitrate": int(bitrate // 1000) if bitrate else None,
        "video_id": _video_id_from_tags(tags),
        "tag_source": "mutagen",
    }


def _read_with_ffprobe(path: Path) -> dict[str, Any] | None:
    """Last resort for a container mutagen will not open."""
    command = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=FFPROBE_TIMEOUT, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None

    streams = payload.get("streams") or []
    if not any(stream.get("codec_type") == "audio" for stream in streams):
        return None

    container = payload.get("format") or {}
    tags = {str(key).casefold(): value for key, value in (container.get("tags") or {}).items()}
    duration = container.get("duration")
    bitrate = container.get("bit_rate")

    return {
        "title": str(tags.get("title") or "").strip(),
        "artist": str(tags.get("artist") or tags.get("album_artist") or "").strip(),
        "album": str(tags.get("album") or "").strip(),
        "duration": int(float(duration)) if duration else None,
        "bitrate": int(int(bitrate) // 1000) if bitrate else None,
        "video_id": _video_id_from_tags(tags),
        "tag_source": "ffprobe",
    }


def _stamp_from_epoch(epoch: float) -> str:
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")


def read_track(path: Path, root: Path) -> LocalTrack:
    """Read one file. Always returns a track, even when every reader declined."""
    stat = path.stat()
    track = LocalTrack(
        file_path=str(path),
        file_name=path.name,
        root_path=str(root),
        extension=path.suffix.casefold(),
        size_bytes=int(stat.st_size),
        modified_at=_stamp_from_epoch(stat.st_mtime),
    )

    details = _read_with_mutagen(path) or _read_with_ffprobe(path)
    if details:
        track.title = details["title"]
        track.artist = details["artist"]
        track.album = details["album"]
        track.duration = details["duration"]
        track.bitrate = details["bitrate"]
        track.video_id = details["video_id"]
        track.tag_source = details["tag_source"]

    # The name carries the id even when no tag does.
    if not track.video_id:
        match = FILENAME_ID_RE.search(path.name)
        if match:
            track.video_id = match.group(1)
    return track


def iter_audio_files(root: Path, *, recursive: bool = True) -> Iterator[Path]:
    """Every audio file under root, skipping hidden files and directories."""
    if not recursive:
        for entry in sorted(root.iterdir()):
            if entry.is_file() and not entry.name.startswith(".") and entry.suffix.casefold() in AUDIO_EXTENSIONS:
                yield entry
        return

    for directory, subdirectories, names in os.walk(root, onerror=lambda _: None):
        # Pruning in place is what stops os.walk descending into them at all.
        subdirectories[:] = sorted(name for name in subdirectories if not name.startswith("."))
        for name in sorted(names):
            if name.startswith("."):
                continue
            if Path(name).suffix.casefold() in AUDIO_EXTENSIONS:
                yield Path(directory) / name


def scan_directory(
    root_path: str | Path,
    log: LogFn,
    *,
    recursive: bool = True,
    is_cancelled: Callable[[], bool] | None = None,
) -> list[LocalTrack]:
    """Read every audio file under root_path.

    One unreadable file is reported and skipped; it never ends the scan.
    Raises NotADirectoryError when the path is not a directory that can be listed.
    """
    root = Path(root_path).expanduser()
    if not root.is_dir():
        raise NotADirectoryError(f"Not a readable directory: {root}")

    log(f"Scanning {root}{' and its subfolders' if recursive else ''}.")
    tracks: list[LocalTrack] = []
    skipped = 0
    for index, path in enumerate(iter_audio_files(root, recursive=recursive), start=1):
        if is_cancelled is not None and is_cancelled():
            log(f"Stopped after {len(tracks)} file(s).")
            break
        try:
            tracks.append(read_track(path, root))
        except OSError as exc:
            skipped += 1
            log(f"Skipped {path.name}: {exc}")
        if index % 250 == 0:
            log(f"  read {index} file(s) so far.")

    tagged = sum(1 for track in tracks if track.tag_source != "filename")
    identified = sum(1 for track in tracks if track.video_id)
    log(
        f"Found {len(tracks)} audio file(s). {tagged} had readable tags, "
        f"{identified} carry a YouTube video id, {skipped} could not be read."
    )
    return tracks
