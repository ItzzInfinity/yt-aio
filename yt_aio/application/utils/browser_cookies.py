"""Where a browser keeps its cookies.

Owns:   finding the directory yt-dlp's --cookies-from-browser needs to be pointed at.
Reads:  the user's home directory, looking for profile directories. Never opens a
        cookie database, and never reads a cookie value.
Writes: nothing.
Runs:   nothing. Pure Python, no Qt, so it can be run and tested head-less.

yt-dlp finds a Chromium-family browser by looking under `$HOME/.config/<vendor>`. That is
right for a browser installed from a distribution package and wrong for every other way a
browser gets onto a Linux machine:

    package   ~/.config/BraveSoftware/Brave-Browser/Default/Cookies
    snap      ~/snap/brave/<revision>/.config/BraveSoftware/Brave-Browser/Default/Cookies
    flatpak   ~/.var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/Default/Cookies

So a snap install is invisible to yt-dlp unless HOME is overridden to the revision
directory, which is what `video_info_extractor.build_yt_dlp_env` does with what this
module finds. On this machine Brave is a snap, `~/snap/brave/current` does not exist, and
the cookies live under the numbered revision `678`.

The presence of a cookie file is the test. A directory that merely exists proves nothing:
`~/.config/BraveSoftware/Brave-Browser` is present here and holds no profile at all.
"""

from __future__ import annotations

from pathlib import Path

# Chromium-family browsers, by the name yt-dlp knows them by.
# (config subdirectory, snap package name, flatpak application id)
CHROMIUM_BROWSERS: dict[str, tuple[str, str | None, str | None]] = {
    "brave": ("BraveSoftware/Brave-Browser", "brave", "com.brave.Browser"),
    "chrome": ("google-chrome", None, "com.google.Chrome"),
    "chromium": ("chromium", "chromium", "org.chromium.Chromium"),
    "edge": ("microsoft-edge", None, "com.microsoft.Edge"),
    "opera": ("opera", "opera", "com.opera.Opera"),
    "vivaldi": ("vivaldi", "vivaldi", "com.vivaldi.Vivaldi"),
    "whale": ("naver-whale", None, None),
}

# Firefox stores cookies per profile under a different tree and a different file name.
FIREFOX_ROOTS = (".mozilla/firefox", "snap/firefox/common/.mozilla/firefox")
FIREFOX_FLATPAK = ".var/app/org.mozilla.firefox/.mozilla/firefox"

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


def _has_chromium_profile(config_root: Path) -> bool:
    """True when at least one profile under this root holds a cookie database."""
    if not config_root.is_dir():
        return False
    try:
        entries = list(config_root.iterdir())
    except OSError:
        return False
    return any(entry.is_dir() and (entry / COOKIE_FILE).is_file() for entry in entries)


def chromium_installations(browser: str, home: Path | None = None) -> list[tuple[str, Path, Path]]:
    """Every install of one browser that actually has cookies.

    Returns (kind, home_for_yt_dlp, config_root) for each, package install first. The
    middle value is what HOME has to be set to for yt-dlp to find the profile; for a
    package install that is the real home, so nothing has to be overridden.
    """
    entry = CHROMIUM_BROWSERS.get(str(browser or "").lower())
    if entry is None:
        return []

    config_subdir, snap_package, flatpak_id = entry
    base = Path(home) if home is not None else Path.home()
    found: list[tuple[str, Path, Path]] = []

    package_root = base / ".config" / config_subdir
    if _has_chromium_profile(package_root):
        found.append(("package", base, package_root))

    if snap_package:
        for revision_home in _snap_revision_homes(snap_package, base):
            config_root = revision_home / ".config" / config_subdir
            if _has_chromium_profile(config_root):
                found.append(("snap", revision_home, config_root))

    if flatpak_id:
        # A flatpak keeps its config under config/ rather than .config/, so yt-dlp needs
        # HOME pointed at the application directory for the two to line up.
        flatpak_home = base / ".var" / "app" / flatpak_id
        config_root = flatpak_home / "config" / config_subdir
        if _has_chromium_profile(config_root):
            found.append(("flatpak", flatpak_home, config_root))

    return found


def cookie_home_for(browser: str, home: Path | None = None) -> str | None:
    """The HOME yt-dlp needs for this browser, or None when it needs no override.

    A package install returns None: the real home already works, and overriding it would
    only risk breaking something that was fine.
    """
    for kind, browser_home, _ in chromium_installations(browser, home):
        if kind == "package":
            return None
        return str(browser_home)
    return None


def profile_names(browser: str, home: Path | None = None) -> list[str]:
    """The profiles that have cookies, "Default" first, for the settings drop-down."""
    names: list[str] = []
    for _, _, config_root in chromium_installations(browser, home):
        try:
            entries = sorted(config_root.iterdir(), key=lambda entry: entry.name)
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir() and (entry / COOKIE_FILE).is_file() and entry.name not in names:
                names.append(entry.name)
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
    """Directories holding a Firefox profile with a cookie database."""
    base = Path(home) if home is not None else Path.home()
    found: list[str] = []
    for relative in (*FIREFOX_ROOTS, FIREFOX_FLATPAK):
        root = base / relative
        if not root.is_dir():
            continue
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        if any(entry.is_dir() and (entry / FIREFOX_COOKIE_FILE).is_file() for entry in entries):
            found.append(str(root))
    return found


def cookie_home_suggestions(home: Path | None = None) -> list[str]:
    """Every browser home worth offering in the Settings tab, most likely first.

    Empty comes first, because empty is the right answer for a package install: the
    override is only needed when a browser is confined.
    """
    suggestions: list[str] = [""]
    for browser in CHROMIUM_BROWSERS:
        for kind, browser_home, _ in chromium_installations(browser, home):
            if kind == "package":
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
    """One line for the Settings tab tool tip, saying what was actually found."""
    installations = chromium_installations(browser, home)
    if not installations:
        if browser.lower() == "firefox":
            homes = firefox_homes(home)
            if homes:
                return f"Firefox profile found at {homes[0]}."
        return f"No {browser} profile with cookies was found."

    kind, browser_home, config_root = installations[0]
    profiles = profile_names(browser, home)
    listed = ", ".join(profiles) if profiles else "none"
    if kind == "package":
        return f"{browser} found as a package install at {config_root}. Profiles: {listed}."
    return (
        f"{browser} found as a {kind} install at {config_root}. "
        f"Profiles: {listed}. Set cookie_fallback_home to {browser_home}."
    )
