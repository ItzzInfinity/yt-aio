"""Theme palettes.

Owns:   the named colour palettes and the rendering of ui/styles.template.qss.
Reads:  application/ui/styles.template.qss
Writes: nothing.
Runs:   nothing.

One template, two palettes. The template is ordinary Qt style sheet source with the
colours lifted out into `@token@` markers; a palette is a flat token-to-value mapping.
Braces cannot be the placeholder because Qt style sheet syntax is made of braces.

Adding a theme is a new entry in PALETTES. Adding a token means adding it to the
template and to every palette; `build_stylesheet` refuses to render a template whose
tokens a palette does not cover, so a half-finished palette fails loudly at start-up
instead of painting one widget in the wrong colour.
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent / "styles.template.qss"

DEFAULT_THEME = "dark"

# What each theme is called in the Settings tab. The config stores the key, not the label.
THEME_LABELS = {
    "dark": "dark (Night Mode)",
    "light": "light (Day Mode)",
}

# No font family is set, deliberately. The style sheet used to ask for
# "fonts-dejavu-core", which is a Debian package name rather than a family, so Qt matched
# nothing and used its own default: Segoe UI on Windows, the system font on macOS, the
# desktop font on Linux. That is the right answer on every platform.
#
# Naming a stack instead is worse, and visibly so. Qt takes the first family that exists
# and its fallback for missing glyphs is poorer than its first-choice matching: with
# "Noto Sans" named, a Bengali title rendered with broken conjuncts, because that face is
# installed here without Bengali shaping tables. Rendering the same string with no family
# set is correct. A library full of Bengali and Hindi titles is worth more than a
# particular Latin face.
_SHARED = {
    "font_size": "13px",
}

PALETTES: dict[str, dict[str, str]] = {
    # Night. The palette the application shipped with, unchanged.
    "dark": {
        **_SHARED,
        "window_bg": "#0d1117",
        "surface": "#12161c",
        "surface_raised": "#171c24",
        "field_bg": "#0f141b",
        "header_bg": "#1e2630",
        "border": "#2c3440",
        "border_hover": "#3a4757",
        "text": "#edf2f7",
        "text_dim": "#9fb0c3",
        "text_header": "#dce7f2",
        "accent": "#1f6feb",
        "accent_hover": "#2f81f7",
        "accent_soft": "#9ecbff",
        "on_accent": "#ffffff",
        "selection_bg": "#2e5b88",
        "selection_fg": "#ffffff",
        "grid": "#26303b",
        "alt_row": "#141b23",
        "muted_fill": "#334155",
        "disabled_fg": "#a0aec0",
        "scrollbar_bg": "#11161d",
        "tab_bg": "#1a2029",
        "tab_hover": "#232c38",
        "radio_border": "#64748b",
    },
    # Day. Same hues and the same accent, with the lightness order inverted. The accent
    # darkens on hover rather than lightening, because on a pale ground the lighter blue
    # is the one that disappears.
    "light": {
        **_SHARED,
        "window_bg": "#e8ecf2",
        "surface": "#f4f7fa",
        "surface_raised": "#ffffff",
        "field_bg": "#ffffff",
        "header_bg": "#e2e8f0",
        "border": "#c8d2df",
        "border_hover": "#94a3b8",
        "text": "#17212b",
        "text_dim": "#55677d",
        "text_header": "#24313f",
        "accent": "#1f6feb",
        "accent_hover": "#1857c4",
        "accent_soft": "#1b5cbf",
        "on_accent": "#ffffff",
        "selection_bg": "#bcd8fb",
        "selection_fg": "#0d2947",
        "grid": "#dbe2ea",
        "alt_row": "#eef2f7",
        "muted_fill": "#c4cedb",
        "disabled_fg": "#7c8899",
        "scrollbar_bg": "#e6ebf1",
        "tab_bg": "#dde5ee",
        "tab_hover": "#cfdae6",
        "radio_border": "#94a3b8",
    },
}

_TOKEN = re.compile(r"@(\w+)@")


def theme_names() -> list[str]:
    """The keys a config file may hold, dark first."""
    return sorted(PALETTES, key=lambda name: name != DEFAULT_THEME)


def resolve_theme_name(value: object) -> str:
    """Fall back to the default rather than raise, so a typo never blocks start-up."""
    name = str(value or "").strip().lower()
    # "dark (Night Mode)" is what the drop-down shows; take the key off the front.
    name = name.split(" ", 1)[0]
    return name if name in PALETTES else DEFAULT_THEME


def build_stylesheet(theme: str = DEFAULT_THEME, *, template_path: Path | None = None) -> str:
    """Render the template with one palette. Returns "" if the template is missing."""
    path = Path(template_path or TEMPLATE_PATH)
    if not path.exists():
        return ""

    palette = PALETTES[resolve_theme_name(theme)]
    missing: set[str] = set()

    def substitute(match: re.Match[str]) -> str:
        token = match.group(1)
        if token not in palette:
            missing.add(token)
            return match.group(0)
        return palette[token]

    rendered = _TOKEN.sub(substitute, path.read_text(encoding="utf-8"))
    if missing:
        raise KeyError(
            f"{path.name} uses tokens the '{theme}' palette does not define: "
            + ", ".join(sorted(missing))
        )
    return rendered


def apply_theme(app, theme: str = DEFAULT_THEME) -> str:
    """Paint a running QApplication. Returns the theme name that was actually used."""
    name = resolve_theme_name(theme)
    app.setStyleSheet(build_stylesheet(name))
    return name
