from __future__ import annotations

import importlib.util
import json
import os
import shutil
import site
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ... import APP_VERSION
from ..db.database_manager import (
    get_cached_videos,
    log_error,
    log_video_info,
    upsert_source,
)
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
    if not use_auth:
        return None

    if config.get("cookie_fallback_home"):
        return str(Path(resolve_runtime_path(str(config["cookie_fallback_home"])) or str(config["cookie_fallback_home"])).expanduser())

    browser = str(config.get("cookie_fallback_browser") or "").lower()
    if browser != "brave":
        return None

    snap_current = Path.home() / "snap" / "brave" / "current"
    if snap_current.exists():
        return str(snap_current)

    snap_root = Path.home() / "snap" / "brave"
    numeric_dirs = sorted(
        [path for path in snap_root.iterdir() if path.is_dir() and path.name.isdigit()],
        key=lambda path: int(path.name),
        reverse=True,
    ) if snap_root.exists() else []
    if numeric_dirs:
        return str(numeric_dirs[0])

    return None


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


def build_yt_dlp_base_args(config: dict[str, Any], *, use_auth: bool = False) -> list[str]:
    args: list[str] = []

    if config.get("user_agent"):
        args.extend(["--user-agent", str(config["user_agent"])])

    if config.get("proxy"):
        args.extend(["--proxy", str(config["proxy"])])

    if config.get("youtube_remote_components"):
        args.extend(["--remote-components", str(config["youtube_remote_components"])])

    if config.get("youtube_visitor_data"):
        args.extend(["--extractor-args", f"youtube:visitor_data={config['youtube_visitor_data']}"])

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
    if seconds is None:
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
            return json.loads(line)
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
                    f"[{now_string()}] {purpose} hit YouTube bot checks. Retrying with browser cookies.",
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
                    f"[{now_string()}] {purpose} hit YouTube bot checks. Retrying with browser cookies.",
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
        channel_name=data.get("channel") or "",
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
        channel_name=entry.get("channel") or "",
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
            "channel_name": data.get("channel"),
            "playlist_name": source_name if source_kind == "playlist" else None,
            "upload_date": data.get("upload_date"),
            "duration": data.get("duration"),
            "view_count": data.get("view_count"),
            "like_count": data.get("like_count"),
            "dislike_count": data.get("dislike_count"),
            "comment_count": data.get("comment_count"),
            "thumbnail_url": data.get("thumbnail"),
            "video_url": data.get("webpage_url"),
            "source_id": source_id,
            "cached_at": now_string(),
        },
    )


def fetch_video_metadata(
    video_id: str,
    config: dict[str, Any],
    token: CancellationToken,
) -> dict[str, Any] | None:
    if token.is_cancelled():
        return None

    return run_json_command(
        ["-J", f"https://www.youtube.com/watch?v={video_id}"],
        config=config,
        retries=int(config.get("max_retries", 3)),
        retry_delay=int(config.get("retry_delay", 5)),
        timeout=45,
        token=token,
    )


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
    source_id = upsert_source(
        db_path,
        {
            "source_key": source_key,
            "source_kind": source_kind,
            "source_name": source_value.strip(),
            "source_value": source_value.strip(),
            "source_url": source_url,
            "created_at": now_string(),
            "updated_at": now_string(),
        },
    )
    safe_log(logger, f"[{now_string()}] Loading {source_kind}: {source_url}")

    source_data = run_json_command(
        ["--flat-playlist", "--dump-single-json", source_url],
        config=config,
        retries=int(config.get("max_retries", 3)),
        retry_delay=int(config.get("retry_delay", 5)),
        timeout=None,
        token=token,
        logger=logger,
        purpose=f"{source_kind} listing request",
    )

    entries = source_data.get("entries") or []
    source_name = source_data.get("title") or source_value.strip()
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
    safe_log(logger, f"[{now_string()}] Found {len(entries)} entries in {source_name}")

    indexed_entries = [
        (index, entry)
        for index, entry in enumerate(entries)
        if entry and entry.get("id")
    ]
    results: list[tuple[int, VideoItem]] = []
    cached_video_map = get_cached_videos(db_path, [entry["id"] for _, entry in indexed_entries])
    pending_entries = []

    for index, entry in indexed_entries:
        cached_row = cached_video_map.get(entry["id"])
        if cached_row:
            cached_item = _cached_row_to_item(cached_row, source_name)
            cached_item.source_id = cached_item.source_id or source_id
            results.append((index, cached_item))
            continue
        pending_entries.append((index, entry))

    safe_log(
        logger,
        f"[{now_string()}] Cache hits: {len(results)}. Fresh fetch required: {len(pending_entries)}.",
    )

    if not pending_entries:
        ordered_items = [item for _, item in sorted(results, key=lambda pair: pair[0])]
        safe_log(logger, f"[{now_string()}] Listing complete: {len(ordered_items)} videos ready.")
        return ordered_items, source_name

    worker_count = min(max(1, int(config.get("max_metadata_workers", 4))), max(1, len(pending_entries)))

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {
            executor.submit(fetch_video_metadata, entry["id"], config, token): (index, entry)
            for index, entry in pending_entries
        }
        for completed_count, future in enumerate(as_completed(future_map), start=1):
            if token.is_cancelled():
                safe_log(logger, f"[{now_string()}] Listing cancelled by user.")
                break

            index, entry = future_map[future]
            video_id = entry["id"]
            try:
                data = future.result()
                if not data:
                    fallback_item = _entry_to_item(entry, source_name)
                    results.append((index, fallback_item))
                    safe_log(
                        logger,
                        f"[{now_string()}] Metadata missing for {video_id}. Using flat-playlist data.",
                    )
                    continue
                item = _metadata_to_item(data, source_name)
                if not item.url:
                    item.url = f"https://www.youtube.com/watch?v={video_id}"
                item.source_id = source_id
                item.video_info_id = _log_video_metadata(db_path, data, source_kind, source_name, source_id)
                results.append((index, item))
                safe_log(
                    logger,
                    f"[{now_string()}] Metadata {completed_count}/{len(pending_entries)}: {item.title}",
                )
            except Exception as exc:
                fallback_item = _entry_to_item(entry, source_name)
                fallback_item.source_id = source_id
                results.append((index, fallback_item))
                safe_log(
                    logger,
                    f"[{now_string()}] Failed metadata for {video_id}: {exc}. Using flat-playlist data.",
                )
                log_error(
                    db_path,
                    {
                        "error_message": str(exc),
                        "timestamp": now_string(),
                        "stack_trace": traceback.format_exc(),
                        "url": f"https://www.youtube.com/watch?v={video_id}",
                        "action": "list_videos",
                        "user_input": source_value,
                        "script_version": APP_VERSION,
                        "system_info": os.uname().sysname if hasattr(os, "uname") else os.name,
                    },
                )

    ordered_items = [item for _, item in sorted(results, key=lambda pair: pair[0])]
    safe_log(logger, f"[{now_string()}] Listing complete: {len(ordered_items)} videos ready.")
    return ordered_items, source_name
