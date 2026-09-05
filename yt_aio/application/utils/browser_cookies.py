r"""Where a browser keeps its cookies.

Owns:   finding the directory yt-dlp's --cookies-from-browser needs to be pointed at.
Reads:  the user's home directory, looking for profile directories. Never opens a
        cookie database, and never reads a cookie value.
Writes: nothing.
Runs:   nothing. Pure Python, no Qt, so it can be run and tested head-less.

Every platform puts them somewhere different, and on Linux so does every packaging
format:

    Linux package   ~/.config/BraveSoftware/Brave-Browser/Default/Cookies
    Linux snap      ~/snap/brave/<revision>/.config/BraveSoftware/Brave-Browser/...
    Linux flatpak   ~/.var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/...
    Windows         %LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data\Default\Network\Cookies
    macOS           ~/Library/Application Support/BraveSoftware/Brave-Browser/...

yt-dlp knows the plain Windows, macOS and Linux-package locations and finds those by
itself. It does not know the snap and flatpak ones, which is what the returned home is
for: `video_info_extractor.build_yt_dlp_env` sets HOME to it so the two line up. On the
machine this was written on, Brave is a snap and its cookies are under a numbered
revision.

Two details that cost time. Chromium moved the cookie database from `<profile>/Cookies`
to `<profile>/Network/Cookies` a few releases ago, and both are still in the wild, so
both are checked. And the presence of a cookie file is the test, never the presence of a
directory: `~/.config/BraveSoftware/Brave-Browser` exists on a machine where Brave is a
snap and holds no profile at all.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

# Chromium-family browsers, by the name yt-dlp knows them by. Each entry says where that
# browser keeps its user data on each platform; None means "this browser is not shipped
# that way". The Windows entry is (environment variable, path under it).
CHROMIUM_BROWSERS: dict[str, dict[str, Any]] = {
    "brave": {
        "linux": "BraveSoftware/Brave-Browser",
        "snap": "brave",
        "flatpak": "com.brave.Browser",
        "windows": ("LOCALAPPDATA", "BraveSoftware/Brave-Browser/User Data"),
        "macos": "BraveSoftware/Brave-Browser",
    },
    "chrome": {
        "linux": "google-chrome",
        "snap": None,
        "flatpak": "com.google.Chrome",
        "windows": ("LOCALAPPDATA", "Google/Chrome/User Data"),
        "macos": "Google/Chrome",
    },
    "chromium": {
        "linux": "chromium",
        "snap": "chromium",
        "flatpak": "org.chromium.Chromium",
        "windows": ("LOCALAPPDATA", "Chromium/User Data"),
        "macos": "Chromium",
    },
    "edge": {
        "linux": "microsoft-edge",
        "snap": None,
        "flatpak": "com.microsoft.Edge",
        "windows": ("LOCALAPPDATA", "Microsoft/Edge/User Data"),
        "macos": "Microsoft Edge",
    },
    "opera": {
        "linux": "opera",
        "snap": "opera",
        "flatpak": "com.opera.Opera",
        "windows": ("APPDATA", "Opera Software/Opera Stable"),
        "macos": "com.operasoftware.Opera",
    },
    "vivaldi": {
        "linux": "vivaldi",
        "snap": "vivaldi",
        "flatpak": "com.vivaldi.Vivaldi",
        "windows": ("LOCALAPPDATA", "Vivaldi/User Data"),
        "macos": "Vivaldi",
    },
    "whale": {
        "linux": "naver-whale",
        "snap": None,
        "flatpak": None,
        "windows": ("LOCALAPPDATA", "Naver/Naver Whale/User Data"),
        "macos": "Naver/Whale",
    },
}

# Firefox stores cookies per profile under a different tree and a different file name.
LINUX_FIREFOX_ROOTS = (".mozilla/firefox", "snap/firefox/common/.mozilla/firefox", ".var/app/org.mozilla.firefox/.mozilla/firefox")
WINDOWS_FIREFOX_ROOT = ("APPDATA", "Mozilla/Firefox/Profiles")
MACOS_FIREFOX_ROOT = "Library/Application Support/Firefox/Profiles"

COOKIE_FILE = "Cookies"
FIREFOX_COOKIE_FILE = "cookies.sqlite"


def _snap_revision_homes(package: str, home: Path) -> list[Path]:
    """Every snap revision directory, newest first, plus `current` when it exists.

    `current` is a symlink the snap system maintains and it is not always there, so the
    numbered revisions are searched as well rather than only as a fallback.
    """
    root = home / "snap" / package
    if not root.is_dir():
        return []

    found: list[Path] = []
    current = root / "current"
    if current.exists():
        found.append(current)

    revisions = [entry for entry in root.iterdir() if entry.is_dir() and entry.name.isdigit()]
    found.extend(sorted(revisions, key=lambda entry: int(entry.name), reverse=True))
    return found


def _has_cookie_file(profile: Path) -> bool:
    """Chromium moved the database into a Network subdirectory; both are still in use."""
    return (profile / COOKIE_FILE).is_file() or (profile / "Network" / COOKIE_FILE).is_file()


def _profile_dirs(config_root: Path) -> list[Path]:
    """The profile directories under one user-data root that hold cookies."""
    if not config_root.is_dir():
        return []
    try:
        entries = sorted(config_root.iterdir(), key=lambda entry: entry.name)
    except OSError:
        return []
    return [entry for entry in entries if entry.is_dir() and _has_cookie_file(entry)]


def _has_chromium_profile(config_root: Path) -> bool:
    """True when at least one profile under this root holds a cookie database."""
    return bool(_profile_dirs(config_root))


def _windows_root(variable: str, relative: str) -> Path | None:
    """A path under %LOCALAPPDATA% or %APPDATA%, or None when the variable is unset."""
    base = os.environ.get(variable)
    if not base:
        return None
    return Path(base).joinpath(*relative.split("/"))


def chromium_installations(browser: str, home: Path | None = None) -> list[tuple[str, Path | None, Path]]:
    """Every install of one browser that actually has cookies.

    Returns (kind, home_for_yt_dlp, config_root). The middle value is what HOME has to be
    set to for yt-dlp to find the profile, and it is None whenever no override is needed,
    which is every Windows and macOS install and every Linux package install. Only a snap
    or a flatpak hides the profile somewhere yt-dlp does not look.
    """
    entry = CHROMIUM_BROWSERS.get(str(browser or "").lower())
    if entry is None:
        return []

    base = Path(home) if home is not None else Path.home()
    found: list[tuple[str, Path | None, Path]] = []

    if IS_WINDOWS:
        windows = entry.get("windows")
        if windows:
            root = _windows_root(*windows)
            if root is not None and _has_chromium_profile(root):
                found.append(("windows", None, root))
        return found

    if IS_MACOS:
        macos = entry.get("macos")
        if macos:
            root = base / "Library" / "Application Support"
            root = root.joinpath(*macos.split("/"))
            if _has_chromium_profile(root):
                found.append(("macos", None, root))
        return found

    package_root = base / ".config"
    package_root = package_root.joinpath(*str(entry["linux"]).split("/"))
    if _has_chromium_profile(package_root):
        found.append(("package", None, package_root))

    if entry.get("snap"):
        for revision_home in _snap_revision_homes(str(entry["snap"]), base):
            config_root = revision_home / ".config"
            config_root = config_root.joinpath(*str(entry["linux"]).split("/"))
            if _has_chromium_profile(config_root):
                found.append(("snap", revision_home, config_root))

    if entry.get("flatpak"):
        # A flatpak keeps its config under config/ rather than .config/, so yt-dlp needs
        # HOME pointed at the application directory for the two to line up.
        flatpak_home = base / ".var" / "app" / str(entry["flatpak"])
        config_root = flatpak_home / "config"
        config_root = config_root.joinpath(*str(entry["linux"]).split("/"))
        if _has_chromium_profile(config_root):
            found.append(("flatpak", flatpak_home, config_root))

    return found


def cookie_home_for(browser: str, home: Path | None = None) -> str | None:
    """The HOME yt-dlp needs for this browser, or None when it needs no override."""
    for _, browser_home, _ in chromium_installations(browser, home):
        return str(browser_home) if browser_home is not None else None
    return None


def profile_names(browser: str, home: Path | None = None) -> list[str]:
    """The profiles that have cookies, "Default" first, for the settings drop-down."""
    names: list[str] = []
    for _, _, config_root in chromium_installations(browser, home):
        for profile in _profile_dirs(config_root):
            if profile.name not in names:
                names.append(profile.name)
    return sorted(names, key=lambda name: (name != "Default", name))


def all_profile_names(home: Path | None = None) -> list[str]:
    """Every profile name found across every Chromium-family browser, "Default" first."""
    names: list[str] = []
    for browser in CHROMIUM_BROWSERS:
        for name in profile_names(browser, home):
            if name not in names:
                names.append(name)
    return sorted(names, key=lambda name: (name != "Default", name))


def firefox_homes(home: Path | None = None) -> list[str]:
    """Directories holding a Firefox profile with a cookie database.

    Firefox is listed for completeness: yt-dlp finds it on every platform without help,
    so these are offered as information rather than as an override anyone needs.
    """
    base = Path(home) if home is not None else Path.home()
    roots: list[Path] = []

    if IS_WINDOWS:
        root = _windows_root(*WINDOWS_FIREFOX_ROOT)
        if root is not None:
            roots.append(root)
    elif IS_MACOS:
        roots.append(base.joinpath(*MACOS_FIREFOX_ROOT.split("/")))
    else:
        roots.extend(base.joinpath(*relative.split("/")) for relative in LINUX_FIREFOX_ROOTS)

    found: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        if any(entry.is_dir() and (entry / FIREFOX_COOKIE_FILE).is_file() for entry in entries):
            value = str(root)
            if value not in found:
                found.append(value)
    return found


def cookie_home_suggestions(home: Path | None = None) -> list[str]:
    """Every browser home worth offering in the Settings tab, most likely first.

    Empty comes first, because empty is the right answer almost everywhere: yt-dlp finds
    the browser by itself on Windows, on macOS and for a Linux package install. Only a
    snap or a flatpak needs to be pointed at.
    """
    suggestions: list[str] = [""]
    for browser in CHROMIUM_BROWSERS:
        for _, browser_home, _ in chromium_installations(browser, home):
            if browser_home is None:
                continue
            value = str(browser_home)
            if value not in suggestions:
                suggestions.append(value)
    for value in firefox_homes(home):
        if value not in suggestions:
            suggestions.append(value)
    base = str(Path(home) if home is not None else Path.home())
    if base not in suggestions:
        suggestions.append(base)
    return suggestions


def describe(browser: str, home: Path | None = None) -> str:
    """One line for the Settings tab, saying what was actually found on this machine."""
    installations = chromium_installations(browser, home)
    if not installations:
        if str(browser).lower() == "firefox":
            homes = firefox_homes(home)
            if homes:
                return f"Firefox profile found at {homes[0]}."
        return f"No {browser} profile with cookies was found on this machine."

    kind, browser_home, config_root = installations[0]
    profiles = profile_names(browser, home)
    listed = ", ".join(profiles) if profiles else "none"
    where = {"windows": "Windows", "macos": "macOS", "package": "package", "snap": "snap", "flatpak": "flatpak"}.get(kind, kind)

    found = f"Found under {config_root}. Profiles: {listed}."
    if browser_home is None:
        return f"{found} yt-dlp finds a {where} install by itself, so cookie_fallback_home can stay empty."
    return f"{found} This is a {where} install, so set cookie_fallback_home to {browser_home}."
