"""Utility package.

Re-exports the names other layers use, but imports the modules only when one of those
names is actually asked for.

The eager version of this file was a real problem twice. It made `yt_aio.application.db`
unable to import anything from `utils` at module level, because `utils` imported
`download_manager`, which imports `db`. And it meant that touching any utility at all
pulled in `video_info_extractor` and, through the panels, PyQt, so the start-up check that
exists to say "PyQt is not installed" could not run without PyQt.

Nothing in the tree imports from this package rather than from a module inside it, so
these names are a convenience for anything outside it.
"""

from __future__ import annotations

from typing import Any

_EXPORTS = {
    "CONFIG_PATH": "config_manager",
    "ensure_config": "config_manager",
    "load_config": "config_manager",
    "resolve_runtime_config": "config_manager",
    "resolve_runtime_path": "config_manager",
    "download_many": "download_manager",
    "record_user_action": "download_manager",
    "CancellationToken": "shared",
    "DownloadTarget": "shared",
    "VideoItem": "shared",
    "now_string": "shared",
    "list_videos": "video_info_extractor",
    "parse_quick_download_urls": "video_info_extractor",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    """Import the owning module on first use (PEP 562)."""
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from importlib import import_module

    value = getattr(import_module(f".{module_name}", __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return __all__
