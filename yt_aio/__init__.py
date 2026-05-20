APP_NAME = "YT AIO"
APP_VERSION = "0.3.1"
APP_CHANGELOG = "Relative runtime paths in config resolved from the application base directory"

from .application.utils.config_manager import (
    CONFIG_PATH,
    ensure_config,
    load_config,
    resolve_runtime_config,
    resolve_runtime_path,
)

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "APP_CHANGELOG",
    "CONFIG_PATH",
    "ensure_config",
    "load_config",
    "resolve_runtime_config",
    "resolve_runtime_path",
]
