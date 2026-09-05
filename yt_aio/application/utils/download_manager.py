from __future__ import annotations

import os
import subprocess
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from ... import APP_VERSION
from ..db.database_manager import (
    get_cached_video_by_url,
    init_db,
    log_download,
    log_error,
    log_user_action,
)
from .config_manager import resolve_runtime_path
from .shared import CancellationToken, DownloadTarget, LogFn, now_string, safe_log
from .video_info_extractor import (
    _should_retry_with_auth,
    build_yt_dlp_command,
    build_yt_dlp_env,
    run_json_command,
)


def resolve_download_title(
    db_path: str,
    target: DownloadTarget,
    config: dict[str, Any],
    token: CancellationToken,
) -> str:
    if target.title:
        return target.title

    cached = get_cached_video_by_url(db_path, target.url)
    if cached and cached.get("title"):
        return str(cached["title"])

    data = run_json_command(
        ["--skip-download", "-J", target.url],
        config=config,
        retries=int(config.get("max_retries", 3)),
        retry_delay=int(config.get("retry_delay", 5)),
        timeout=30,
        token=token,
    )
    return data.get("title") or target.url


# Docs/06_YTDLNIS_APPROACH.md section 3.3. YouTube's auto-generated music channels are
# named "<artist> - Topic", and that suffix ends up in the file's uploader and artist
# tags. The first rule rewrites uploader to everything before " - Topic"; the second
# copies the cleaned uploader into artist. Verified against a real Topic upload: the
# uploader went from "WB V2 MIX - Topic" to "WB V2 MIX".
PARSE_METADATA_RULES = (
    "%(uploader,channel,creator|)l:^(?P<uploader>.*?)(?:(?= - Topic)|$)",
    "%(uploader)s:%(artist)s",
)
# Off by default: a playlist title is often a mood or a mix name, not an album, and a
# wrong album tag is harder to notice than a missing one.
PLAYLIST_ALBUM_RULE = "%(playlist_title)s:%(album)s"


def build_metadata_args(config: dict[str, Any]) -> list[str]:
    """Tag-writing options. --embed-metadata is the current name for --add-metadata."""
    args = ["--embed-metadata"]
    for rule in PARSE_METADATA_RULES:
        args.extend(["--parse-metadata", rule])
    if config.get("embed_album_from_playlist"):
        args.extend(["--parse-metadata", PLAYLIST_ALBUM_RULE])
    return args


def build_tuning_args(config: dict[str, Any]) -> list[str]:
    """Throughput and robustness options (06_YTDLNIS_APPROACH.md section 3.8).

    The retry counts are separate from `max_retries`, which governs our own re-run of the
    whole command. Sharing one number would multiply the two together.
    """
    args: list[str] = []

    def whole(key: str, default: int, low: int, high: int) -> int:
        try:
            return min(high, max(low, int(config.get(key, default))))
        except (TypeError, ValueError):
            return default

    args.extend(["-N", str(whole("concurrent_fragments", 4, 1, 16))])
    args.extend(["--retries", str(whole("download_retries", 10, 0, 100))])
    args.extend(["--fragment-retries", str(whole("fragment_retries", 10, 0, 100))])

    limit = str(config.get("limit_rate") or "").strip()
    if limit:
        args.extend(["-r", limit])

    if config.get("restrict_filenames"):
        args.append("--restrict-filenames")

    return args


def build_audio_format_args(config: dict[str, Any]) -> list[str]:
    """Audio selection as a preference, not a filter (06_YTDLNIS_APPROACH.md section 3.4).

    The old `-f bestaudio[ext=m4a]/bestaudio` rejects everything that is not m4a before it
    looks at quality. `-f ba/b` accepts any audio and `-S` then ranks what came back, so a
    better opus stream is still reachable when no m4a exists.

    The source document ends its sort with `+size`, which is dropped here. User sort terms
    outrank yt-dlp's own bitrate term, so `+size` asks for the smallest stream rather than
    the best one: on a real track it chose 49 kbps where every other selector chose 130.
    That trade belongs to a phone on mobile data, not to a music library.
    """
    container = str(config.get("default_audio_quality", "m4a") or "m4a")
    codec = str(config.get("preferred_audio_codec") or "").strip()

    sort_terms = ["hasaud"]
    if codec:
        sort_terms.append(f"acodec:{codec}")
    if container and container != "best":
        sort_terms.append(f"aext:{container}")

    return [
        "-f",
        "ba/b",
        "-S",
        ",".join(sort_terms),
        "--extract-audio",
        "--audio-format",
        container,
        "--audio-quality",
        "0",
    ]


def build_archive_args(config: dict[str, Any]) -> list[str]:
    """--download-archive (06_YTDLNIS_APPROACH.md section 3.2).

    The archive and the database answer different questions. yt-dlp reads the archive and
    refuses the fetch, with no gap between the check and the download; the `downloads`
    table is what the Library and Local Scan tabs read. Both are kept.

    On by default, but behind a switch, because an archive silently skipping a file the
    operator explicitly asked for is surprising the first time it happens.
    """
    if not config.get("enable_download_archive", True):
        return []

    raw = str(config.get("download_archive_path") or "./db/downloaded.txt")
    resolved = resolve_runtime_path(raw) or raw
    archive = Path(resolved).expanduser()
    try:
        archive.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        # An unwritable archive path must not stop the download; yt-dlp would fail on it,
        # so drop the option and let the database check carry the duplicate detection.
        return []
    return ["--download-archive", str(archive)]


def build_download_command(
    url: str,
    media_type: str,
    config: dict[str, Any],
    *,
    use_auth: bool = False,
) -> list[str]:
    download_dir = str(Path(resolve_runtime_path(str(config["default_download_path"])) or config["default_download_path"]).expanduser())
    command = [
        "--newline",
        "--ignore-errors",
        "--no-overwrites",
        *build_metadata_args(config),
        *build_tuning_args(config),
        *build_archive_args(config),
        "--paths",
        download_dir,
        "--print",
        "after_move:filepath",
    ]

    if config.get("download_subtitles"):
        command.extend(["--write-subs", "--sub-langs", str(config.get("subtitle_language", "en"))])

    if config.get("download_description"):
        command.append("--write-description")

    if media_type == "video":
        command.extend(
            [
                "-f",
                str(config.get("default_video_quality", "bv*+ba/b")),
                "--merge-output-format",
                "mp4",
            ]
        )
    else:
        command.extend(build_audio_format_args(config))
        if config.get("download_thumbnail"):
            command.append("--embed-thumbnail")

    command.append(url)
    return build_yt_dlp_command(config, command, use_auth=use_auth)


def run_streaming_command(
    command: list[str],
    token: CancellationToken,
    logger: LogFn | None,
    env: dict[str, str] | None = None,
) -> tuple[int, list[str]]:
    safe_log(logger, f"[{now_string()}] [TX] {os.path.basename(command[0])} -> {command[-1]}")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    token.register(process)
    output_lines: list[str] = []
    try:
        assert process.stdout is not None
        while True:
            if token.is_cancelled():
                process.terminate()
            line = process.stdout.readline()
            if line:
                cleaned = line.rstrip()
                output_lines.append(cleaned)
                safe_log(logger, f"[{now_string()}] [RX] {cleaned}")
                continue
            if process.poll() is not None:
                break
        return process.wait(), output_lines
    finally:
        token.unregister(process)


def infer_output_path(output_lines: list[str]) -> str | None:
    for line in reversed(output_lines):
        candidate = line.strip()
        if candidate.startswith("/") and Path(candidate).exists():
            return candidate
    return None


def download_one(
    target: DownloadTarget,
    media_type: str,
    config: dict[str, Any],
    db_path: str,
    logger: LogFn | None,
    token: CancellationToken,
    source_name: str,
) -> bool:
    if token.is_cancelled():
        return False

    try:
        title = resolve_download_title(db_path, target, config, token)
    except Exception as exc:
        title = target.title or target.url
        safe_log(
            logger,
            f"[{now_string()}] [WARN] Could not resolve title for {target.url}: {exc}. Using fallback title.",
        )
    safe_log(logger, f"[{now_string()}] [INFO] Starting {media_type} download: {title}")
    command = build_download_command(target.url, media_type, config, use_auth=False)
    return_code, output_lines = run_streaming_command(
        command,
        token,
        logger,
        env=build_yt_dlp_env(config, use_auth=False),
    )
    combined_output = "\n".join(output_lines)

    if return_code != 0 and _should_retry_with_auth(combined_output, config, attempted_auth=False):
        safe_log(
            logger,
            f"[{now_string()}] [WARN] Raw download hit YouTube bot checks. Retrying with browser cookies.",
        )
        command = build_download_command(target.url, media_type, config, use_auth=True)
        return_code, output_lines = run_streaming_command(
            command,
            token,
            logger,
            env=build_yt_dlp_env(config, use_auth=True),
        )
        combined_output = "\n".join(output_lines)

    output_path = infer_output_path(output_lines)

    if token.is_cancelled():
        log_download(
            db_path,
            {
                "title": title,
                "url": target.url,
                "status": "cancelled",
                "error_message": "Cancelled by user",
                "timestamp": now_string(),
                "file_path": output_path,
                "quality": config.get(f"default_{media_type}_quality"),
                "type": media_type,
                "source_name": source_name,
                "video_id": target.video_id,
                "video_info_id": target.video_info_id,
                "source_id": target.source_id,
            },
        )
        return False

    if return_code != 0:
        error_message = "\n".join(output_lines[-10:]) or combined_output or "yt-dlp exited with non-zero status"
        log_download(
            db_path,
            {
                "title": title,
                "url": target.url,
                "status": "failed",
                "error_message": error_message,
                "timestamp": now_string(),
                "file_path": output_path,
                "quality": config.get(f"default_{media_type}_quality"),
                "type": media_type,
                "source_name": source_name,
                "video_id": target.video_id,
                "video_info_id": target.video_info_id,
                "source_id": target.source_id,
            },
        )
        log_error(
            db_path,
            {
                "error_message": error_message,
                "timestamp": now_string(),
                "url": target.url,
                "action": "download",
                "user_input": source_name,
                "script_version": APP_VERSION,
                "system_info": os.uname().sysname if hasattr(os, "uname") else os.name,
            },
        )
        safe_log(logger, f"[{now_string()}] [ERR] Download failed: {title}")
        return False

    log_download(
        db_path,
        {
            "title": title,
            "url": target.url,
            "status": "success",
            "error_message": None,
            "timestamp": now_string(),
            "file_path": output_path,
            "quality": config.get(f"default_{media_type}_quality"),
            "type": media_type,
            "source_name": source_name,
            "video_id": target.video_id,
            "video_info_id": target.video_info_id,
            "source_id": target.source_id,
        },
    )
    safe_log(logger, f"[{now_string()}] [INFO] Download complete: {title}")
    return True


def download_many(
    targets: list[DownloadTarget],
    media_type: str,
    config: dict[str, Any],
    db_path: str,
    logger: LogFn | None,
    token: CancellationToken,
    source_name: str,
) -> str:
    init_db(db_path)
    success_count = 0
    failure_count = 0

    worker_count = min(max(1, int(config.get("max_concurrent_downloads", 2))), max(1, len(targets)))
    safe_log(
        logger,
        f"[{now_string()}] [INFO] Download queue started with {len(targets)} items and {worker_count} workers.",
    )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {
            executor.submit(download_one, target, media_type, config, db_path, logger, token, source_name): target
            for target in targets
        }
        for future in as_completed(future_map):
            target = future_map[future]
            if token.is_cancelled():
                safe_log(logger, f"[{now_string()}] [WARN] Stop requested. Remaining downloads will be cancelled.")
                break
            try:
                if future.result():
                    success_count += 1
                else:
                    failure_count += 1
            except Exception as exc:
                failure_count += 1
                log_error(
                    db_path,
                    {
                        "error_message": str(exc),
                        "timestamp": now_string(),
                        "stack_trace": traceback.format_exc(),
                        "url": target.url,
                        "action": "download_many",
                        "user_input": source_name,
                        "script_version": APP_VERSION,
                        "system_info": os.uname().sysname if hasattr(os, "uname") else os.name,
                    },
                )
                safe_log(logger, f"[{now_string()}] [ERR] Unexpected download error for {target.url}: {exc}")

    summary = f"Completed downloads. Success: {success_count}, Failed/Cancelled: {failure_count}"
    safe_log(logger, f"[{now_string()}] [INFO] {summary}")
    return summary


def record_user_action(db_path: str, action: str) -> None:
    init_db(db_path)
    log_user_action(db_path, action, now_string())
