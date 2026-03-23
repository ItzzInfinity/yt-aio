from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
APPLICATION_ROOT = PACKAGE_ROOT / "application"
CONFIG_DIR = APPLICATION_ROOT / "config"
DB_DIR = APPLICATION_ROOT / "db"
LOGS_DIR = APPLICATION_ROOT / "logs"
RUNTIME_PATH_KEYS = {
    "default_download_path",
    "log_file_path",
    "history_file_path",
    "logs_directory",
    "cookie_file",
    "cookie_fallback_home",
}
RUNTIME_RELATIVE_DEFAULTS = {
    "log_file_path": "./db/yt_aio.db",
    "history_file_path": "./db/yt_aio.db",
    "logs_directory": "./logs",
}

CONFIG_PATH = CONFIG_DIR / "config.json"
LEGACY_PACKAGE_CONFIG_PATH = PACKAGE_ROOT / "config.json"
LEGACY_PROJECT_ROOT = PACKAGE_ROOT.parent
LEGACY_PROJECT_CONFIG_PATH = LEGACY_PROJECT_ROOT / "config.json"

PROJECT_DB_PATH = DB_DIR / "yt_aio.db"
LEGACY_PACKAGE_DB_PATH = PACKAGE_ROOT / "yt_aio.db"
LEGACY_PROJECT_DB_PATH = LEGACY_PROJECT_ROOT / "yt_aio.db"


def _default_download_path() -> str:
    return str(Path.home() / "Downloads")


def _default_db_path() -> str:
    return "./db/yt_aio.db"


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
        "logs_directory": "./logs",
    }


def resolve_runtime_path(path_value: str | None, *, base_dir: Path = APPLICATION_ROOT) -> str | None:
    if path_value in (None, ""):
        return path_value

    candidate = Path(str(path_value)).expanduser()
    if candidate.is_absolute():
        return str(candidate)
    return str((base_dir / candidate).resolve())


def resolve_runtime_config(config: dict[str, Any], *, base_dir: Path = APPLICATION_ROOT) -> dict[str, Any]:
    resolved = dict(config)
    for key in RUNTIME_PATH_KEYS:
        value = resolved.get(key)
        if value in (None, ""):
            continue
        resolved[key] = resolve_runtime_path(str(value), base_dir=base_dir)
    return resolved


def _ensure_runtime_directories() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DB_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _move_if_missing(source: Path, target: Path) -> None:
    if source.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)


def _migrate_legacy_project_files() -> None:
    _ensure_runtime_directories()

    _move_if_missing(LEGACY_PACKAGE_CONFIG_PATH, CONFIG_PATH)
    _move_if_missing(LEGACY_PROJECT_CONFIG_PATH, CONFIG_PATH)

    for source in (LEGACY_PACKAGE_DB_PATH, LEGACY_PROJECT_DB_PATH):
        _move_if_missing(source, PROJECT_DB_PATH)
        _move_if_missing(source.with_name("yt_aio.db-wal"), PROJECT_DB_PATH.with_name("yt_aio.db-wal"))
        _move_if_missing(source.with_name("yt_aio.db-shm"), PROJECT_DB_PATH.with_name("yt_aio.db-shm"))


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

    legacy_paths = {
        str(LEGACY_PACKAGE_DB_PATH),
        str(LEGACY_PROJECT_DB_PATH),
        str(PROJECT_DB_PATH),
    }
    if loaded.get("log_file_path") in legacy_paths or resolve_runtime_path(loaded.get("log_file_path")) == str(PROJECT_DB_PATH):
        if loaded.get("log_file_path") != RUNTIME_RELATIVE_DEFAULTS["log_file_path"]:
            loaded["log_file_path"] = RUNTIME_RELATIVE_DEFAULTS["log_file_path"]
            changed = True

    if loaded.get("history_file_path") in legacy_paths or resolve_runtime_path(loaded.get("history_file_path")) == str(PROJECT_DB_PATH):
        if loaded.get("history_file_path") != RUNTIME_RELATIVE_DEFAULTS["history_file_path"]:
            loaded["history_file_path"] = RUNTIME_RELATIVE_DEFAULTS["history_file_path"]
            changed = True

    if resolve_runtime_path(loaded.get("logs_directory")) == str(LOGS_DIR):
        if loaded.get("logs_directory") != RUNTIME_RELATIVE_DEFAULTS["logs_directory"]:
            loaded["logs_directory"] = RUNTIME_RELATIVE_DEFAULTS["logs_directory"]
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
