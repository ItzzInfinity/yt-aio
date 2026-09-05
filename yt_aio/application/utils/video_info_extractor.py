from __future__ import annotations

import importlib.util
import json
import os
import shutil
import site
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from ... import APP_VERSION
from ..db.database_manager import (
    get_cached_videos,
    log_error,
    log_video_info,
    log_video_info_batch,
    upsert_source,
)
from .browser_cookies import cookie_home_for
from .config_manager import resolve_runtime_path
from .shared import CancellationToken, LogFn, VideoItem, now_string, safe_log


BOT_CHALLENGE_MARKERS = (
    "http error 429",
    "too many requests",
    "sign in to confirm you're not a bot",
    "sign in to confirm you’re not a bot",
    "n challenge solving failed",
    "remote components challenge solver",
    "visitor data",
)
YT_DLP_SPEC = importlib.util.find_spec("yt_dlp")
YT_DLP_IMPORT_ROOT = (
    str(Path(YT_DLP_SPEC.origin).resolve().parent.parent)
    if YT_DLP_SPEC and YT_DLP_SPEC.origin
    else None
)
YT_DLP_USER_SITE = site.getusersitepackages()


def _should_retry_with_auth(output: str, config: dict[str, Any], attempted_auth: bool) -> bool:
    if attempted_auth or not config.get("cookie_fallback_enabled", False):
        return False

    if not (config.get("cookie_file") or config.get("cookie_fallback_browser")):
        return False

    lowered = output.lower()
    return any(marker in lowered for marker in BOT_CHALLENGE_MARKERS)


def _cookie_browser_spec(config: dict[str, Any]) -> str | None:
    browser = config.get("cookie_fallback_browser")
    if not browser:
        return None
    profile = config.get("cookie_fallback_profile")
    if profile:
        return f"{browser}:{profile}"
    return str(browser)


def _cookie_home_override(config: dict[str, Any], use_auth: bool) -> str | None:
    """The HOME yt-dlp needs so it can find the browser profile, or None.

    An explicit cookie_fallback_home always wins. Otherwise the browser is looked up in
    utils/browser_cookies.py, which knows the snap and flatpak layouts yt-dlp does not.
    A package install needs no override and returns None.
    """
    if not use_auth:
        return None

    configured = config.get("cookie_fallback_home")
    if configured:
        resolved = resolve_runtime_path(str(configured)) or str(configured)
        return str(Path(resolved).expanduser())

    browser = str(config.get("cookie_fallback_browser") or "")
    return cookie_home_for(browser) if browser else None


def build_yt_dlp_env(config: dict[str, Any], *, use_auth: bool = False) -> dict[str, str]:
    env = os.environ.copy()
    home_override = _cookie_home_override(config, use_auth)
    if home_override:
        env["HOME"] = home_override

        python_paths = [path for path in env.get("PYTHONPATH", "").split(os.pathsep) if path]
        for candidate in (YT_DLP_IMPORT_ROOT, YT_DLP_USER_SITE):
            if candidate and candidate not in python_paths:
                python_paths.insert(0, candidate)
        if python_paths:
            env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(python_paths))
    return env


def build_youtube_extractor_args(config: dict[str, Any]) -> list[str]:
    """One --extractor-args value for the youtube extractor (06_YTDLNIS_APPROACH.md 3.7).

    yt-dlp keeps only the last --extractor-args for a given extractor, so visitor data,
    the player client list and PO tokens have to be joined with ";" into a single option
    rather than passed as three. Player clients and PO tokens are the current answer to
    bot checks; the cookie fallback stays as the second line, not the first.

    Defined above its caller on purpose. It previously sat below, between two other
    helpers, and an edit that replaced the function above it took this one with it.
    """
    parts: list[str] = []

    clients = str(config.get("youtube_player_clients") or "").strip()
    if clients:
        parts.append(f"player_client={clients}")

    visitor = str(config.get("youtube_visitor_data") or "").strip()
    if visitor:
        parts.append(f"visitor_data={visitor}")

    # Several tokens are allowed; the config holds them comma separated for readability
    # and they are re-joined here the way yt-dlp expects.
    tokens = [token.strip() for token in str(config.get("youtube_po_tokens") or "").split(",") if token.strip()]
    if tokens:
        parts.append("po_token=" + ",".join(tokens))

    if not parts:
        return []
    return ["--extractor-args", "youtube:" + ";".join(parts)]


def build_yt_dlp_base_args(config: dict[str, Any], *, use_auth: bool = False) -> list[str]:
    args: list[str] = []

    if config.get("user_agent"):
        args.extend(["--user-agent", str(config["user_agent"])])

    if config.get("proxy"):
        args.extend(["--proxy", str(config["proxy"])])

    if config.get("youtube_remote_components"):
        args.extend(["--remote-components", str(config["youtube_remote_components"])])

    args.extend(build_youtube_extractor_args(config))

    if use_auth:
        if config.get("cookie_file"):
            cookie_path = resolve_runtime_path(str(config["cookie_file"])) or str(config["cookie_file"])
            args.extend(["--cookies", str(Path(cookie_path).expanduser())])
        else:
            browser_spec = _cookie_browser_spec(config)
            if browser_spec:
                args.extend(["--cookies-from-browser", browser_spec])

    return args


def build_yt_dlp_command(
    config: dict[str, Any],
    command_parts: list[str],
    *,
    use_auth: bool = False,
) -> list[str]:
    launcher = [sys.executable, "-m", "yt_dlp"]
    if not (YT_DLP_SPEC and shutil.which(sys.executable)):
        launcher = ["yt-dlp"]
    return [*launcher, *build_yt_dlp_base_args(config, use_auth=use_auth), *command_parts]


def build_listing_args(config: dict[str, Any]) -> list[str]:
    """The flat-playlist listing options, from Docs/06_YTDLNIS_APPROACH.md section 3.5.

    --lazy-playlist streams entries as the extractor finds them instead of collecting the
    whole playlist first, which is what made a large channel time out (FSD 1.8.1). -R 1 and
    a socket timeout make a bad entry fail in seconds rather than stall the run.

    --no-warnings is deliberately not passed, although the source document lists it. Two of
    the bot-challenge markers we watch for arrive as warnings, so silencing warnings would
    silence the cookie retry with them.
    """
    timeout = config.get("socket_timeout", 15)
    try:
        timeout = max(1, int(timeout))
    except (TypeError, ValueError):
        timeout = 15

    return [
        "--flat-playlist",
        "--lazy-playlist",
        "-j",
        "--ignore-errors",
        "-R",
        "1",
        "--socket-timeout",
        str(timeout),
        "--extractor-args",
        "youtubetab:approximate_date",
    ]


def resolve_source_url(source_kind: str, raw_value: str) -> str:
    value = raw_value.strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value

    if source_kind == "playlist":
        return f"https://www.youtube.com/playlist?list={value}"

    if value.startswith("@"):
        return f"https://www.youtube.com/{value}/videos"

    if value.startswith("UC"):
        return f"https://www.youtube.com/channel/{value}/videos"

    return f"https://www.youtube.com/@{value}/videos"


def validate_youtube_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        return False

    host = parsed.netloc.lower()
    if "youtube.com" not in host and "youtu.be" not in host:
        return False

    return True


def parse_quick_download_urls(raw_text: str) -> tuple[list[str], list[str]]:
    stripped = raw_text.strip()
    if not stripped or stripped.upper() == "NULL":
        return [], []

    valid: list[str] = []
    invalid: list[str] = []
    for part in stripped.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        if validate_youtube_url(candidate):
            valid.append(candidate)
        else:
            invalid.append(candidate)
    return valid, invalid


def format_duration(seconds: int | None) -> str:
    # A negative value is a sentinel for "not known", which several backup formats use.
    # Formatting one produces nonsense like -1:59:59, so it is reported as unknown.
    if seconds is None or int(seconds) < 0:
        return "Unknown"

    minutes, second = divmod(int(seconds), 60)
    hour, minute = divmod(minutes, 60)
    if hour:
        return f"{hour:02d}:{minute:02d}:{second:02d}"
    return f"{minute:02d}:{second:02d}"


def extract_audio_bitrate(formats: list[dict[str, Any]] | None) -> str:
    if not formats:
        return "Unknown"

    bitrates = []
    for fmt in formats:
        abr = fmt.get("abr")
        acodec = fmt.get("acodec")
        if abr and acodec and acodec != "none":
            try:
                bitrates.append(int(float(abr)))
            except (TypeError, ValueError):
                continue

    if not bitrates:
        return "Unknown"

    return f"{max(bitrates)}k"


def _load_json_from_stdout(stdout: str) -> Any:
    for line in reversed([line.strip() for line in stdout.splitlines() if line.strip()]):
        try:
            val = json.loads(line)
            if val is not None:
                return val
        except json.JSONDecodeError:
            continue
    raise RuntimeError("yt-dlp did not return valid JSON output")


def run_json_command(
    command_parts: list[str],
    *,
    config: dict[str, Any],
    retries: int,
    retry_delay: int,
    timeout: int | None = None,
    token: CancellationToken | None = None,
    logger: LogFn | None = None,
    purpose: str = "yt-dlp metadata request",
) -> Any:
    last_error = "Unknown error"
    attempted_auth = False
    for _ in range(max(1, retries) + 1):
        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(
                build_yt_dlp_command(config, command_parts, use_auth=attempted_auth),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=build_yt_dlp_env(config, use_auth=attempted_auth),
            )
            if token is not None:
                token.register(process)

            start_time = time.monotonic()
            while True:
                if token is not None and token.is_cancelled():
                    process.terminate()
                    raise RuntimeError("Cancelled by user")

                if timeout is not None and (time.monotonic() - start_time) > timeout:
                    process.kill()
                    raise RuntimeError("yt-dlp command timed out")

                try:
                    stdout, stderr = process.communicate(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    continue

            combined_output = "\n".join(part for part in [stdout, stderr] if part).strip()
            if _should_retry_with_auth(combined_output, config, attempted_auth):
                attempted_auth = True
                safe_log(
                    logger,
                    f"[{now_string()}] [WARN] {purpose} hit YouTube bot checks. Retrying with browser cookies.",
                )
                continue

            if process.returncode != 0 and not stdout.strip():
                raise RuntimeError(combined_output or "yt-dlp command failed")
            return _load_json_from_stdout(stdout)
        except Exception as exc:
            last_error = str(exc)
            if token is not None and token.is_cancelled():
                raise RuntimeError("Cancelled by user") from exc
            if _should_retry_with_auth(last_error, config, attempted_auth):
                attempted_auth = True
                safe_log(
                    logger,
                    f"[{now_string()}] [WARN] {purpose} hit YouTube bot checks. Retrying with browser cookies.",
                )
                continue
            time.sleep(max(0, retry_delay))
        finally:
            if token is not None and process is not None:
                token.unregister(process)
    raise RuntimeError(last_error)


def _metadata_to_item(data: dict[str, Any], source_name: str) -> VideoItem:
    return VideoItem(
        video_id=data.get("id") or "",
        title=data.get("title") or "Unknown title",
        url=data.get("webpage_url") or "",
        duration_seconds=data.get("duration"),
        duration_label=format_duration(data.get("duration")),
        available_bitrate=extract_audio_bitrate(data.get("formats")),
        channel_name=data.get("channel") or data.get("uploader") or data.get("playlist_channel") or data.get("playlist_uploader") or "",
        source_name=source_name,
        upload_date=data.get("upload_date") or "",
        view_count=data.get("view_count"),
    )


def _entry_to_item(entry: dict[str, Any], source_name: str) -> VideoItem:
    video_id = entry.get("id") or ""
    url = entry.get("url") or f"https://www.youtube.com/watch?v={video_id}"
    return VideoItem(
        video_id=video_id,
        title=entry.get("title") or "Unknown title",
        url=url,
        duration_seconds=entry.get("duration"),
        duration_label=format_duration(entry.get("duration")),
        available_bitrate="Unknown",
        channel_name=entry.get("channel") or entry.get("uploader") or entry.get("playlist_channel") or entry.get("playlist_uploader") or "",
        source_name=source_name,
        upload_date=entry.get("upload_date") or "",
        view_count=entry.get("view_count"),
    )


def _cached_row_to_item(row: dict[str, Any], source_name: str) -> VideoItem:
    return VideoItem(
        video_id=row.get("video_id") or "",
        title=row.get("title") or "Unknown title",
        url=row.get("video_url") or f"https://www.youtube.com/watch?v={row.get('video_id')}",
        duration_seconds=row.get("duration"),
        duration_label=format_duration(row.get("duration")),
        available_bitrate="Unknown",
        channel_name=row.get("channel_name") or "",
        source_name=source_name,
        upload_date=row.get("upload_date") or "",
        view_count=row.get("view_count"),
        video_info_id=row.get("id"),
        source_id=row.get("source_id"),
    )


def _log_video_metadata(
    db_path: str,
    data: dict[str, Any],
    source_kind: str,
    source_name: str,
    source_id: int | None,
) -> int | None:
    return log_video_info(
        db_path,
        {
            "video_id": data.get("id"),
            "title": data.get("title"),
            "channel_name": data.get("channel") or data.get("uploader") or data.get("playlist_channel") or data.get("playlist_uploader"),
            "playlist_name": source_name if source_kind == "playlist" else None,
            "upload_date": data.get("upload_date"),
            "duration": data.get("duration"),
            "thumbnail_url": data.get("thumbnail"),
            "video_url": data.get("webpage_url"),
            "source_id": source_id,
            "cached_at": now_string(),
            "is_full_metadata": 1,
        },
    )


# Every field the viewers and the cache need, asked for in one --print template. Cheaper
# than -J, which serialises far more than this, but `formats` stays because the bitrate
# column is read off it and yt-dlp has no shorthand for a slice of a list of objects.
BATCH_METADATA_FIELDS = (
    "id",
    "title",
    "channel",
    "uploader",
    "playlist_channel",
    "playlist_uploader",
    "duration",
    "upload_date",
    "thumbnail",
    "webpage_url",
    "view_count",
    "formats",
)
BATCH_METADATA_TEMPLATE = "%(.{" + ",".join(BATCH_METADATA_FIELDS) + "})j"


def _info_cache_dir(config: dict[str, Any]) -> Path | None:
    """The directory holding one JSON file per video, or None when caching is off."""
    if not config.get("info_cache_enabled", True):
        return None
    raw = str(config.get("info_cache_dir") or "./db/info_cache")
    resolved = resolve_runtime_path(raw) or raw
    directory = Path(resolved).expanduser()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return directory


def _info_cache_max_age(config: dict[str, Any]) -> float:
    try:
        hours = max(0, int(config.get("info_cache_max_age_hours", 168)))
    except (TypeError, ValueError):
        hours = 168
    return hours * 3600.0


def read_cached_info(video_id: str, config: dict[str, Any]) -> dict[str, Any] | None:
    """The stored metadata for one video, if it is present and young enough.

    Docs/06_YTDLNIS_APPROACH.md section 3.6 reaches for --load-info-json. Storing our own
    field subset and reading it directly is the same idea taken one step further: a second
    pass runs no yt-dlp process at all, rather than a cheaper one. Their CRC32 file names
    solve an Android path problem; a video id is already a safe file name here.
    """
    directory = _info_cache_dir(config)
    if directory is None:
        return None

    path = directory / f"{video_id}.json"
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return None

    max_age = _info_cache_max_age(config)
    if max_age and age > max_age:
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and data.get("id") else None


def write_cached_info(data: dict[str, Any], config: dict[str, Any]) -> None:
    """Store one video's metadata. A failure here is never worth failing a fetch for."""
    directory = _info_cache_dir(config)
    video_id = data.get("id")
    if directory is None or not video_id:
        return
    target = directory / f"{video_id}.json"
    temporary = target.with_suffix(".json.tmp")
    try:
        temporary.write_text(json.dumps(data), encoding="utf-8")
        os.replace(temporary, target)
    except OSError:
        try:
            temporary.unlink()
        except OSError:
            pass


def _metadata_batch_size(config: dict[str, Any]) -> int:
    """How many URLs one yt-dlp process is given."""
    try:
        return max(1, int(config.get("metadata_batch_size", 25)))
    except (TypeError, ValueError):
        return 25


def _metadata_process_count(config: dict[str, Any]) -> int:
    """How many of those processes run at once."""
    try:
        return max(1, int(config.get("max_metadata_workers", 4)))
    except (TypeError, ValueError):
        return 4


def _run_metadata_chunk(
    video_ids: list[str],
    config: dict[str, Any],
    token: CancellationToken,
    logger: LogFn | None,
    *,
    use_auth: bool,
) -> tuple[dict[str, dict[str, Any]], str]:
    """One yt-dlp process for a whole chunk. Returns what it produced and its stderr."""
    timeout = config.get("socket_timeout", 15)
    try:
        timeout = max(1, int(timeout))
    except (TypeError, ValueError):
        timeout = 15

    handle, url_file = tempfile.mkstemp(prefix="yt_aio_urls_", suffix=".txt", text=True)
    collected: dict[str, dict[str, Any]] = {}
    stderr_text = ""
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            for video_id in video_ids:
                stream.write(f"https://www.youtube.com/watch?v={video_id}\n")

        command = build_yt_dlp_command(
            config,
            [
                "-a",
                url_file,
                "--skip-download",
                "--ignore-errors",
                "-R",
                "1",
                "--socket-timeout",
                str(timeout),
                "--print",
                BATCH_METADATA_TEMPLATE,
            ],
            use_auth=use_auth,
        )
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=build_yt_dlp_env(config, use_auth=use_auth),
        )
        token.register(process)
        try:
            assert process.stdout is not None
            for line in process.stdout:
                if token.is_cancelled():
                    process.terminate()
                    break
                cleaned = line.strip()
                if not cleaned or not cleaned.startswith("{"):
                    continue
                try:
                    data = json.loads(cleaned)
                except json.JSONDecodeError:
                    continue
                video_id = data.get("id")
                if video_id:
                    collected[video_id] = data

            if process.stderr is not None:
                stderr_text = process.stderr.read() or ""
            process.wait()
        finally:
            token.unregister(process)
    finally:
        try:
            os.unlink(url_file)
        except OSError:
            pass

    return collected, stderr_text


def fetch_metadata_batch(
    video_ids: list[str],
    config: dict[str, Any],
    token: CancellationToken,
    logger: LogFn | None = None,
    *,
    on_video: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Full metadata for many videos (06_YTDLNIS_APPROACH.md 3.1), batched and parallel.

    The source document batches and then runs the batches in sequence. Measured here, that
    is slower than the thread pool it replaces: one process spends about a second starting
    up and then fetches its URLs one after another, so a sequential run gives up all the
    network overlap to save a startup. Batching and keeping the pool wins twice, so
    `metadata_batch_size` URLs go to one process and `max_metadata_workers` processes run
    together. `max_metadata_workers` therefore keeps the meaning it already had.

    `on_video` is called once per result, from a lock, so a caller may touch the database
    and its own lists inside it without adding one of its own.
    """
    wanted = [video_id for video_id in video_ids if video_id]
    if not wanted:
        return {}

    results: dict[str, dict[str, Any]] = {}
    pending: list[str] = []
    for video_id in wanted:
        cached = read_cached_info(video_id, config)
        if cached is None:
            pending.append(video_id)
            continue
        results[video_id] = cached
        if on_video is not None:
            on_video(video_id, cached)

    if results:
        safe_log(logger, f"[{now_string()}] [INFO] {len(results)} of {len(wanted)} served from the info cache.")
    if not pending:
        return results

    batch_size = _metadata_batch_size(config)
    chunks = [pending[start : start + batch_size] for start in range(0, len(pending), batch_size)]
    process_count = min(_metadata_process_count(config), len(chunks))

    guard = threading.Lock()

    def handle(chunk: list[str]) -> None:
        if token.is_cancelled():
            return
        collected, stderr_text = _run_metadata_chunk(chunk, config, token, logger, use_auth=False)

        # A chunk that produced nothing may have hit a bot check rather than bad URLs.
        # Retry that chunk once with cookies; a chunk that produced anything is kept.
        if not collected and not token.is_cancelled() and _should_retry_with_auth(stderr_text, config, False):
            safe_log(
                logger,
                f"[{now_string()}] [WARN] Metadata batch hit YouTube bot checks. Retrying with browser cookies.",
            )
            collected, stderr_text = _run_metadata_chunk(chunk, config, token, logger, use_auth=True)

        for data in collected.values():
            write_cached_info(data, config)

        with guard:
            for video_id, data in collected.items():
                results[video_id] = data
                if on_video is not None:
                    on_video(video_id, data)

            missing = [video_id for video_id in chunk if video_id not in collected]
            if missing and not token.is_cancelled():
                safe_log(
                    logger,
                    f"[{now_string()}] [WARN] No metadata for {len(missing)} of {len(chunk)} in this batch: "
                    + ", ".join(missing[:5])
                    + ("..." if len(missing) > 5 else ""),
                )

    if process_count == 1:
        for chunk in chunks:
            handle(chunk)
        return results

    with ThreadPoolExecutor(max_workers=process_count) as executor:
        for future in as_completed([executor.submit(handle, chunk) for chunk in chunks]):
            try:
                future.result()
            except Exception as exc:
                safe_log(logger, f"[{now_string()}] [WARN] A metadata batch failed: {exc}")

    return results


def _log_flat_video_metadata(
    db_path: str,
    entry: dict[str, Any],
    source_kind: str,
    source_name: str,
    source_id: int | None,
) -> int | None:
    thumbnails = entry.get("thumbnails") or []
    thumbnail_url = thumbnails[0].get("url") if thumbnails else None

    duration = entry.get("duration")
    if duration is not None:
        try:
            duration = int(float(duration))
        except (ValueError, TypeError):
            duration = None

    video_url = entry.get("url") or entry.get("webpage_url") or f"https://www.youtube.com/watch?v={entry.get('id')}"

    return log_video_info(
        db_path,
        {
            "video_id": entry.get("id"),
            "title": entry.get("title"),
            "channel_name": entry.get("channel") or entry.get("uploader") or entry.get("playlist_channel") or entry.get("playlist_uploader"),
            "playlist_name": source_name if source_kind == "playlist" else None,
            "upload_date": entry.get("upload_date"),
            "duration": duration,
            "thumbnail_url": thumbnail_url,
            "video_url": video_url,
            "source_id": source_id,
            "cached_at": now_string(),
            "is_full_metadata": 0,
        },
    )


def _stream_flat_playlist(
    cmd: list[str],
    env: dict[str, str],
    config: dict[str, Any],
    source_kind: str,
    source_value: str,
    source_url: str,
    source_key: str,
    db_path: str,
    logger: LogFn | None,
    token: CancellationToken,
) -> tuple[list[VideoItem], str, bool, str]:
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )
    token.register(process)

    raw_entries: list[dict[str, Any]] = []
    hit_bot_checks = False
    stderr_lines = []

    try:
        assert process.stdout is not None
        while True:
            if token.is_cancelled():
                process.terminate()
                safe_log(logger, f"[{now_string()}] [WARN] Listing cancelled by user.")
                break

            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break
                continue

            cleaned_line = line.strip()
            if not cleaned_line:
                continue

            try:
                entry = json.loads(cleaned_line)
                if entry and entry.get("id"):
                    raw_entries.append(entry)
                    if len(raw_entries) % 100 == 0:
                        safe_log(logger, f"[{now_string()}] [INFO] Streamed {len(raw_entries)} video entries...")
            except json.JSONDecodeError:
                stderr_lines.append(cleaned_line)
                continue

        if process.stderr:
            for err_line in process.stderr:
                stderr_lines.append(err_line.strip())

        process.wait()
        combined_err = "\n".join(stderr_lines)
        if not raw_entries:
            # --ignore-errors lets yt-dlp exit zero having extracted nothing, so the
            # decision to retry with cookies reads the stderr text, not the exit code.
            if _should_retry_with_auth(combined_err, config, attempted_auth=False):
                hit_bot_checks = True
            return [], source_value.strip(), hit_bot_checks, combined_err

        source_name = source_value.strip()
        for entry in raw_entries:
            name = entry.get("playlist") or entry.get("playlist_title")
            if name:
                source_name = name
                break

        source_id = upsert_source(
            db_path,
            {
                "source_key": source_key,
                "source_kind": source_kind,
                "source_name": source_name,
                "source_value": source_value.strip(),
                "source_url": source_url,
                "created_at": now_string(),
                "updated_at": now_string(),
            },
        )

        video_ids = [entry["id"] for entry in raw_entries]
        cached_video_map = get_cached_videos(db_path, video_ids)

        uncached_indices = []
        uncached_payloads = []
        results: list[VideoItem | None] = [None] * len(raw_entries)

        for i, entry in enumerate(raw_entries):
            video_id = entry["id"]
            cached_row = cached_video_map.get(video_id)
            if cached_row:
                cached_item = _cached_row_to_item(cached_row, source_name)
                cached_item.source_id = cached_item.source_id or source_id
                results[i] = cached_item
            else:
                uncached_indices.append(i)
                thumbnails = entry.get("thumbnails") or []
                thumbnail_url = thumbnails[0].get("url") if thumbnails else None
                duration = entry.get("duration")
                if duration is not None:
                    try:
                        duration = int(float(duration))
                    except (ValueError, TypeError):
                        duration = None
                video_url = entry.get("url") or entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"

                payload = {
                    "video_id": video_id,
                    "title": entry.get("title"),
                    "channel_name": entry.get("channel") or entry.get("uploader") or entry.get("playlist_channel") or entry.get("playlist_uploader"),
                    "playlist_name": source_name if source_kind == "playlist" else None,
                    "upload_date": entry.get("upload_date"),
                    "duration": duration,
                    "thumbnail_url": thumbnail_url,
                    "video_url": video_url,
                    "source_id": source_id,
                    "cached_at": now_string(),
                    "is_full_metadata": 0,
                }
                uncached_payloads.append(payload)

        if uncached_payloads:
            safe_log(
                logger,
                f"[{now_string()}] [INFO] Cache hits: {len(raw_entries) - len(uncached_payloads)}. Caching {len(uncached_payloads)} new entries in database...",
            )
            inserted_ids = log_video_info_batch(db_path, uncached_payloads)

            for index_in_uncached, original_idx in enumerate(uncached_indices):
                entry = raw_entries[original_idx]
                item = _entry_to_item(entry, source_name)
                item.source_id = source_id
                item.video_info_id = inserted_ids[index_in_uncached]
                results[original_idx] = item

        final_results = [r for r in results if r is not None]
        return final_results, source_name, False, combined_err

    finally:
        token.unregister(process)


def list_videos(
    source_kind: str,
    source_value: str,
    config: dict[str, Any],
    db_path: str,
    logger: LogFn | None,
    token: CancellationToken,
) -> tuple[list[VideoItem], str]:
    source_url = resolve_source_url(source_kind, source_value)
    source_key = f"{source_kind}:{source_value.strip()}"

    attempted_auth = False
    cmd_parts = [*build_listing_args(config), source_url]

    cmd = build_yt_dlp_command(config, cmd_parts, use_auth=attempted_auth)
    env = build_yt_dlp_env(config, use_auth=attempted_auth)

    results, source_name, hit_bot, err = _stream_flat_playlist(
        cmd, env, config, source_kind, source_value, source_url, source_key, db_path, logger, token
    )

    if hit_bot and not token.is_cancelled():
        safe_log(logger, f"[{now_string()}] [WARN] Listing hit bot checks. Retrying with browser cookies...")
        attempted_auth = True
        cmd = build_yt_dlp_command(config, cmd_parts, use_auth=attempted_auth)
        env = build_yt_dlp_env(config, use_auth=attempted_auth)
        results, source_name, hit_bot, err = _stream_flat_playlist(
            cmd, env, config, source_kind, source_value, source_url, source_key, db_path, logger, token
        )

    if not results and not token.is_cancelled():
        raise RuntimeError(err or "yt-dlp flat-playlist command returned no videos")

    fetch_full = bool(config.get("fetch_full_metadata", False))
    if fetch_full and results and not token.is_cancelled():
        video_ids = [item.video_id for item in results]
        db_rows = get_cached_videos(db_path, video_ids)

        pending_items = []
        for item in results:
            row = db_rows.get(item.video_id)
            if not row or not row.get("is_full_metadata"):
                pending_items.append(item)

        if pending_items:
            safe_log(logger, f"[{now_string()}] [INFO] Fetching full metadata for {len(pending_items)} uncached videos...")
            video_to_index = {item.video_id: i for i, item in enumerate(results)}
            done = 0

            def absorb(video_id: str, data: dict[str, Any]) -> None:
                """Fold one batch result back into the list the caller is waiting on."""
                nonlocal done
                index = video_to_index.get(video_id)
                if index is None:
                    return
                old_item = results[index]
                try:
                    new_item = _metadata_to_item(data, source_name)
                    new_item.source_id = old_item.source_id
                    new_item.video_info_id = _log_video_metadata(
                        db_path, data, source_kind, source_name, old_item.source_id
                    )
                    results[index] = new_item
                    done += 1
                    safe_log(
                        logger,
                        f"[{now_string()}] [INFO] Full metadata {done}/{len(pending_items)}: {new_item.title}",
                    )
                except Exception as exc:
                    safe_log(logger, f"[{now_string()}] [WARN] Failed full metadata for {video_id}: {exc}")
                    log_error(
                        db_path,
                        {
                            "error_message": str(exc),
                            "timestamp": now_string(),
                            "stack_trace": traceback.format_exc(),
                            "url": f"https://www.youtube.com/watch?v={video_id}",
                            "action": "fetch_full_metadata",
                            "user_input": source_value,
                            "script_version": APP_VERSION,
                            "system_info": os.uname().sysname if hasattr(os, "uname") else os.name,
                        },
                    )

            fetch_metadata_batch(
                [item.video_id for item in pending_items],
                config,
                token,
                logger,
                on_video=absorb,
            )

    safe_log(logger, f"[{now_string()}] [INFO] Listing complete: {len(results)} videos ready.")
    return results, source_name
