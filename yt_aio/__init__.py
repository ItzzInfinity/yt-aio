from .config import CONFIG_PATH, ensure_config, load_config

APP_NAME = "YT AIO"
APP_VERSION = "0.2.1"
APP_CHANGELOG = "Stable yt-dlp launcher and preserved Python path for Brave cookie fallback"

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "APP_CHANGELOG",
    "CONFIG_PATH",
    "ensure_config",
    "load_config",
]
