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
        "--add-metadata",
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
        command.extend(
            [
                "-f",
                "bestaudio[ext=m4a]/bestaudio",
                "--extract-audio",
                "--audio-format",
                str(config.get("default_audio_quality", "m4a")),
                "--audio-quality",
                "0",
            ]
        )
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
                safe_log(logger, cleaned)
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
            f"[{now_string()}] Could not resolve title for {target.url}: {exc}. Using fallback title.",
        )
    safe_log(logger, f"[{now_string()}] Starting {media_type} download: {title}")
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
            f"[{now_string()}] Raw download hit YouTube bot checks. Retrying with browser cookies.",
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
        safe_log(logger, f"[{now_string()}] Download failed: {title}")
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
    safe_log(logger, f"[{now_string()}] Download complete: {title}")
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
        f"[{now_string()}] Download queue started with {len(targets)} items and {worker_count} workers.",
    )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {
            executor.submit(download_one, target, media_type, config, db_path, logger, token, source_name): target
            for target in targets
        }
        for future in as_completed(future_map):
            target = future_map[future]
            if token.is_cancelled():
                safe_log(logger, f"[{now_string()}] Stop requested. Remaining downloads will be cancelled.")
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
                safe_log(logger, f"[{now_string()}] Unexpected download error for {target.url}: {exc}")

    summary = f"Completed downloads. Success: {success_count}, Failed/Cancelled: {failure_count}"
    safe_log(logger, f"[{now_string()}] {summary}")
    return summary


def record_user_action(db_path: str, action: str) -> None:
    init_db(db_path)
    log_user_action(db_path, action, now_string())
