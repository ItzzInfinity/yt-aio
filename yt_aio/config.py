from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parent
LEGACY_PROJECT_ROOT = PACKAGE_ROOT.parent

CONFIG_PATH = PACKAGE_ROOT / "config.json"
LEGACY_CONFIG_PATH = LEGACY_PROJECT_ROOT / "config.json"
PROJECT_DB_PATH = PACKAGE_ROOT / "yt_aio.db"
LEGACY_DB_PATH = LEGACY_PROJECT_ROOT / "yt_aio.db"


def _default_download_path() -> str:
    return str(Path.home() / "Downloads")


def _default_db_path() -> str:
    return str(PROJECT_DB_PATH)


def build_default_config() -> dict[str, Any]:
    cpu_count = os.cpu_count() or 4
    return {
        "default_download_path": _default_download_path(),
        "default_video_quality": "bv*+ba/b",
        "default_audio_quality": "m4a",
        "max_retries": 3,
        "retry_delay": 5,
        "log_file_path": _default_db_path(),
        "log_level": "INFO",
        "proxy": None,
        "user_agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        ),
        "download_subtitles": False,
        "subtitle_language": "en",
        "download_thumbnail": False,
        "thumbnail_quality": "best",
        "download_description": False,
        "description_format": "txt",
        "download_comments": False,
        "comments_format": "txt",
        "max_concurrent_downloads": max(1, cpu_count - 2),
        "max_metadata_workers": min(4, max(1, cpu_count - 1)),
        "download_history": True,
        "history_file_path": _default_db_path(),
        "history_file_table_name": "downloads",
        "cookie_fallback_enabled": True,
        "cookie_fallback_browser": "brave",
        "cookie_fallback_profile": None,
        "cookie_fallback_home": None,
        "cookie_file": None,
        "youtube_visitor_data": None,
        "youtube_remote_components": "ejs:github",
    }


def _move_if_missing(source: Path, target: Path) -> None:
    if source.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)


def _migrate_legacy_project_files() -> None:
    _move_if_missing(LEGACY_CONFIG_PATH, CONFIG_PATH)
    _move_if_missing(LEGACY_DB_PATH, PROJECT_DB_PATH)
    _move_if_missing(LEGACY_DB_PATH.with_name("yt_aio.db-wal"), PROJECT_DB_PATH.with_name("yt_aio.db-wal"))
    _move_if_missing(LEGACY_DB_PATH.with_name("yt_aio.db-shm"), PROJECT_DB_PATH.with_name("yt_aio.db-shm"))


def ensure_config(path: Path | None = None) -> Path:
    _migrate_legacy_project_files()

    config_path = Path(path or CONFIG_PATH)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    defaults = build_default_config()
    if not config_path.exists():
        config_path.write_text(json.dumps(defaults, indent=4), encoding="utf-8")
        return config_path

    loaded = json.loads(config_path.read_text(encoding="utf-8"))
    changed = False

    if loaded.get("log_file_path") == str(LEGACY_DB_PATH):
        loaded["log_file_path"] = str(PROJECT_DB_PATH)
        changed = True

    if loaded.get("history_file_path") == str(LEGACY_DB_PATH):
        loaded["history_file_path"] = str(PROJECT_DB_PATH)
        changed = True

    for key, value in defaults.items():
        if key not in loaded:
            loaded[key] = value
            changed = True

    if changed:
        config_path.write_text(json.dumps(loaded, indent=4), encoding="utf-8")

    return config_path


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = ensure_config(path)
    return json.loads(config_path.read_text(encoding="utf-8"))
