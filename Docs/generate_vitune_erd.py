"""Build Docs/vitune_db_erd.html from a ViTune backup.

Owns:   the ViTune entity-relationship page.
Reads:  a ViTune .db backup, read-only. Never writes to it.
Writes: Docs/vitune_db_erd.html.
Runs:   nothing else. Pure Python and sqlite3, no third-party packages.

A generator rather than a hand-written page, because a newer backup can be re-rendered
in one command instead of being edited by hand:

    python3 Docs/generate_vitune_erd.py ~/Downloads/my_music/database/ViTune_backup_*.db

Styled to match Docs/song_db_erd.html, which documents the OpenTune schema, so the two
can be read side by side. Docs/opentune_vs_vitune.html compares them directly.
"""

from __future__ import annotations

import html
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

DOCS = Path(__file__).resolve().parent
OUTPUT = DOCS / "vitune_db_erd.html"

# Where each table sits in the diagram, and what colour it takes. The layout is fixed
# rather than computed: this schema is small and stable, and a hand-placed diagram reads
# far better than anything a spring layout produces for fifteen boxes.
# (column, row, kind)
LAYOUT: dict[str, tuple[int, int, str]] = {
    "Artist": (0, 0, "entity"),
    "Album": (0, 1, "entity"),
    "Playlist": (0, 2, "entity"),
    "SongArtistMap": (1, 0, "junction"),
    "SongAlbumMap": (1, 1, "junction"),
    "SongPlaylistMap": (1, 2, "junction"),
    "Song": (2, 1, "hub"),
    "Format": (3, 0, "detail"),
    "Lyrics": (3, 1, "detail"),
    "Event": (3, 2, "detail"),
}
DETACHED = ["SearchQuery", "QueuedMediaItem", "PipedSession", "room_master_table", "android_metadata"]

KIND_COLOUR = {
    "entity": "var(--primary)",
    "junction": "var(--junction)",
    "hub": "var(--accent3)",
    "detail": "var(--accent4)",
    "loose": "var(--muted)",
}

# What each table is for, in one sentence. The schema says what a column is called; this
# says why the table exists, which is the part a schema dump cannot tell you.
PURPOSE: dict[str, str] = {
    "Song": "One row per track. The hub: everything else hangs off its YouTube video id.",
    "Artist": "One row per credited artist, keyed by the YouTube channel or browse id.",
    "Album": "One row per album, with the year, the cover and the credited authors as text.",
    "Playlist": "A user-made playlist. browseId is set when it mirrors a YouTube playlist.",
    "SongArtistMap": "Which artists are credited on which song. Many-to-many, no ordering column.",
    "SongAlbumMap": "Which album a song belongs to, with its track position.",
    "SongPlaylistMap": "Which playlist a song sits in, and where in the running order.",
    "Format": "The cached stream chosen for a song: itag, bitrate, size and loudness.",
    "Lyrics": "Fixed and time-synced lyrics for one song.",
    "Event": "One row per play, with a timestamp and how long it played for.",
    "SearchQuery": "Search box history.",
    "QueuedMediaItem": "The playback queue, serialised as a blob.",
    "PipedSession": "Credentials for a Piped instance, when one is configured.",
    "room_master_table": "Android Room's own schema-hash row. Not app data.",
    "android_metadata": "The Android locale row every Room database carries.",
}

BOX_WIDTH = 190
BOX_HEIGHT = 66
COLUMN_GAP = 250
ROW_GAP = 118
MARGIN_X = 40
MARGIN_Y = 40


def _table_names(conn: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def read_schema(path: Path) -> dict[str, dict[str, Any]]:
    """Columns, foreign keys and row counts for every table, read read-only."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        schema: dict[str, dict[str, Any]] = {}
        for table in _table_names(conn):
            columns = [
                {"name": row[1], "type": row[2] or "", "notnull": bool(row[3]), "default": row[4], "pk": int(row[5])}
                for row in conn.execute(f'PRAGMA table_info("{table}")')
            ]
            foreign_keys = [
                {"column": row[3], "target_table": row[2], "target_column": row[4]}
                for row in conn.execute(f'PRAGMA foreign_key_list("{table}")')
            ]
            count = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            schema[table] = {"columns": columns, "foreign_keys": foreign_keys, "rows": count}
        views = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'view'")]
        return {"tables": schema, "views": views}
    finally:
        conn.close()


def _position(table: str) -> tuple[int, int]:
    column, row, _ = LAYOUT[table]
    return MARGIN_X + column * COLUMN_GAP, MARGIN_Y + row * ROW_GAP


def _edges(schema: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    """Declared foreign keys, both ends of which are on the diagram."""
    seen: set[tuple[str, str]] = set()
    for table, detail in schema.items():
        if table not in LAYOUT:
            continue
        for key in detail["foreign_keys"]:
            target = key["target_table"]
            if target in LAYOUT and (table, target) not in seen:
                seen.add((table, target))
    return sorted(seen)


def build_diagram(schema: dict[str, dict[str, Any]]) -> str:
    """The SVG. Boxes are placed by LAYOUT; lines follow the declared foreign keys."""
    width = MARGIN_X * 2 + 3 * COLUMN_GAP + BOX_WIDTH
    height = MARGIN_Y * 2 + 2 * ROW_GAP + BOX_HEIGHT

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
        f'aria-label="ViTune entity relationship diagram">',
        '<defs><marker id="head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        'orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="var(--muted)"/></marker></defs>',
    ]

    for source, target in _edges(schema):
        sx, sy = _position(source)
        tx, ty = _position(target)
        # Draw from the box edge that faces the other box, so no line crosses a label.
        if tx > sx:
            x1, x2 = sx + BOX_WIDTH, tx
        elif tx < sx:
            x1, x2 = sx, tx + BOX_WIDTH
        else:
            x1, x2 = sx + BOX_WIDTH / 2, tx + BOX_WIDTH / 2
        y1, y2 = sy + BOX_HEIGHT / 2, ty + BOX_HEIGHT / 2
        midpoint = (x1 + x2) / 2
        parts.append(
            f'<path d="M {x1:.0f} {y1:.0f} C {midpoint:.0f} {y1:.0f}, {midpoint:.0f} {y2:.0f}, {x2:.0f} {y2:.0f}" '
            f'fill="none" stroke="var(--border)" stroke-width="1.6" marker-end="url(#head)"/>'
        )

    for table, (_, _, kind) in LAYOUT.items():
        if table not in schema:
            continue
        x, y = _position(table)
        colour = KIND_COLOUR[kind]
        rows = schema[table]["rows"]
        columns = len(schema[table]["columns"])
        parts.append(
            f'<g><rect x="{x}" y="{y}" width="{BOX_WIDTH}" height="{BOX_HEIGHT}" rx="10" '
            f'fill="var(--surface2)" stroke="{colour}" stroke-width="1.6"/>'
            f'<text x="{x + 14}" y="{y + 26}" fill="{colour}" font-size="14" font-weight="700">'
            f"{html.escape(table)}</text>"
            f'<text x="{x + 14}" y="{y + 47}" fill="var(--muted)" font-size="11">'
            f"{rows:,} rows &#183; {columns} cols</text></g>"
        )

    parts.append("</svg>")
    return "\n".join(parts)


def build_schema_cards(schema: dict[str, dict[str, Any]], order: list[str]) -> str:
    cards = []
    for table in order:
        if table not in schema:
            continue
        detail = schema[table]
        kind = LAYOUT.get(table, (0, 0, "loose"))[2]
        rows = []
        foreign = {key["column"]: key for key in detail["foreign_keys"]}
        for column in detail["columns"]:
            classes = []
            marker = ""
            if column["pk"]:
                classes.append("col-pk")
                marker = '<span class="key-icon">PK</span>'
            if column["name"] in foreign:
                classes.append("col-fk")
                target = foreign[column["name"]]
                marker += f'<span class="key-icon fk">FK &#8594; {html.escape(target["target_table"])}</span>'
            rows.append(
                f'<div class="row {" ".join(classes)}">'
                f'<span class="cname">{html.escape(column["name"])}</span>'
                f'<span class="ctype">{html.escape(column["type"] or "—")}</span>'
                f'<span class="cflags">{marker}</span></div>'
            )
        cards.append(
            f'<article class="ref-card {kind}">'
            f'<header class="ref-head"><span class="ref-title">{html.escape(table)}</span>'
            f'<span class="count">{detail["rows"]:,} rows</span></header>'
            f'<p class="purpose">{html.escape(PURPOSE.get(table, ""))}</p>'
            f'<div class="ref-rows">{"".join(rows)}</div></article>'
        )
    return "\n".join(cards)


def build_relationship_cards(schema: dict[str, dict[str, Any]]) -> str:
    """One card per junction, spelling out the path a query has to walk."""
    definitions = [
        (
            "Song &#8596; Artist",
            "many-to-many",
            "Song.id &#8594; SongArtistMap.songId &#8592;&#8594; SongArtistMap.artistId &#8594; Artist.id",
            "An artist name is not stored on the song. Reaching it always costs a join, and a song "
            "with three credits has three rows here. SongArtistMap has no position column, so the "
            "order the app credits artists in is not recorded.",
        ),
        (
            "Song &#8596; Album",
            "many-to-many, one in practice",
            "Song.id &#8594; SongAlbumMap.songId &#8592;&#8594; SongAlbumMap.albumId &#8594; Album.id",
            "position holds the track number. The junction allows several albums per song, which is "
            "what makes compilations expressible.",
        ),
        (
            "Song &#8596; Playlist",
            "many-to-many",
            "Song.id &#8594; SongPlaylistMap.songId &#8592;&#8594; SongPlaylistMap.playlistId &#8594; Playlist.id",
            "position is the running order. The SortedSongPlaylistMap view is this table ordered by "
            "position, so the app can read a playlist in order without an ORDER BY.",
        ),
        (
            "Song &#8594; Format",
            "one-to-one",
            "Format.songId &#8594; Song.id, with songId as the primary key",
            "One cached stream per song: itag, mime type, bitrate, content length and loudness. "
            "The primary key on songId is what makes it one-to-one rather than one-to-many.",
        ),
        (
            "Song &#8594; Lyrics",
            "one-to-one",
            "Lyrics.songId &#8594; Song.id, with songId as the primary key",
            "fixed is plain text, synced carries timings, startTime offsets them.",
        ),
        (
            "Song &#8594; Event",
            "one-to-many",
            "Event.songId &#8594; Song.id",
            "One row per play with a timestamp and playTime. Counting rows per songId gives a play "
            "count; Song.totalPlayTimeMs is the same information already summed.",
        ),
    ]
    cards = []
    for title, kind, path, description in definitions:
        cards.append(
            f'<article class="rel-card"><div class="rel-title">{title}</div>'
            f'<div class="rel-type">{kind}</div>'
            f'<div class="rel-path">{path}</div>'
            f'<p class="rel-desc">{description}</p></article>'
        )
    return "\n".join(cards)


STYLE = """
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0a0c10; --surface: #12161e; --surface2: #1a202e; --border: #252d3e;
    --primary: #00e5ff; --primary-dim: rgba(0,229,255,0.12);
    --accent: #ff6b6b; --accent2: #ffd93d; --accent3: #6bcb77; --accent4: #c77dff;
    --text: #e0e8f0; --muted: #5a6a82; --junction: #ff9a3c;
  }
  body { background: var(--bg); color: var(--text); font-family: 'JetBrains Mono', ui-monospace, monospace; min-height: 100vh; }
  header.page { padding: 28px 40px 20px; border-bottom: 1px solid var(--border);
    background: linear-gradient(180deg, #0d1119 0%, transparent 100%);
    display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
  header.page h1 { font-family: 'Syne', system-ui, sans-serif; font-size: 1.6rem; font-weight: 800; letter-spacing: -0.02em; color: #fff; }
  header.page h1 span { color: var(--primary); }
  .sub { color: var(--muted); font-size: 0.78rem; margin-top: 6px; }
  .header-badges { display: flex; gap: 8px; flex-wrap: wrap; }
  .badge { display: inline-flex; align-items: center; gap: 6px; font-size: 0.7rem; padding: 4px 10px;
    border-radius: 20px; border: 1px solid; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; }
  .badge-blue { border-color: var(--primary); color: var(--primary); background: var(--primary-dim); }
  .badge-orange { border-color: var(--junction); color: var(--junction); background: rgba(255,154,60,0.1); }
  .badge-green { border-color: var(--accent3); color: var(--accent3); background: rgba(107,203,119,0.1); }
  main { padding: 28px 40px 64px; max-width: 1400px; margin: 0 auto; }
  section { margin-bottom: 46px; }
  h2 { font-family: 'Syne', system-ui, sans-serif; font-size: 1.15rem; font-weight: 700; color: #fff;
    margin-bottom: 6px; letter-spacing: -0.01em; }
  h2::before { content: '// '; color: var(--primary); }
  .lede { color: var(--muted); font-size: 0.82rem; line-height: 1.7; margin-bottom: 18px; max-width: 80ch; }
  .legend { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; font-size: 0.72rem; color: var(--muted); }
  .legend-item { display: flex; align-items: center; gap: 7px; }
  .dot { width: 11px; height: 11px; border-radius: 3px; border: 1.6px solid; }
  .diagram-wrap { background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
    padding: 18px; overflow-x: auto; }
  .ref-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); gap: 14px; }
  .ref-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
  .ref-card.hub { border-color: var(--accent3); }
  .ref-card.entity { border-color: rgba(0,229,255,0.45); }
  .ref-card.junction { border-color: rgba(255,154,60,0.45); }
  .ref-card.detail { border-color: rgba(199,125,255,0.45); }
  .ref-head { display: flex; justify-content: space-between; align-items: center; gap: 10px;
    padding: 11px 14px; background: var(--surface2); border-bottom: 1px solid var(--border); }
  .ref-title { font-weight: 700; color: #fff; font-size: 0.9rem; }
  .count { font-size: 0.68rem; color: var(--muted); white-space: nowrap; }
  .purpose { padding: 11px 14px; font-size: 0.73rem; line-height: 1.65; color: var(--muted); border-bottom: 1px solid var(--border); }
  .ref-rows { padding: 6px 0; }
  .row { display: grid; grid-template-columns: 1fr auto auto; gap: 10px; align-items: center;
    padding: 5px 14px; font-size: 0.73rem; }
  .row:hover { background: rgba(255,255,255,0.03); }
  .cname { color: var(--text); overflow-wrap: anywhere; }
  .ctype { color: var(--muted); font-size: 0.68rem; }
  .col-pk .cname { color: var(--accent2); font-weight: 700; }
  .col-fk .cname { color: var(--junction); }
  .key-icon { display: inline-block; font-size: 0.58rem; padding: 1px 5px; border-radius: 4px; margin-left: 5px;
    background: rgba(255,217,61,0.14); color: var(--accent2); border: 1px solid rgba(255,217,61,0.35); white-space: nowrap; }
  .key-icon.fk { background: rgba(255,154,60,0.12); color: var(--junction); border-color: rgba(255,154,60,0.35); }
  .rels-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 14px; }
  .rel-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 15px 17px; }
  .rel-title { font-weight: 700; color: #fff; font-size: 0.9rem; margin-bottom: 4px; }
  .rel-type { display: inline-block; font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.07em;
    color: var(--junction); border: 1px solid rgba(255,154,60,0.35); background: rgba(255,154,60,0.1);
    padding: 2px 8px; border-radius: 20px; margin-bottom: 10px; }
  .rel-path { font-size: 0.69rem; color: var(--primary); background: var(--surface2); border: 1px solid var(--border);
    border-radius: 7px; padding: 8px 10px; margin-bottom: 10px; overflow-wrap: anywhere; }
  .rel-desc { font-size: 0.74rem; line-height: 1.7; color: var(--muted); }
  table.facts { width: 100%; border-collapse: collapse; font-size: 0.76rem; }
  table.facts th, table.facts td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border); }
  table.facts th { color: var(--primary); font-weight: 600; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em; }
  table.facts td.num { text-align: right; color: var(--accent2); }
  footer { padding: 22px 40px 40px; color: var(--muted); font-size: 0.7rem; border-top: 1px solid var(--border); }
  @media (max-width: 700px) { header.page, main, footer { padding-left: 18px; padding-right: 18px; } }
"""


def build_page(source: Path, schema_info: dict[str, Any]) -> str:
    schema = schema_info["tables"]
    views = schema_info["views"]
    total_rows = sum(detail["rows"] for detail in schema.values())

    connected = [name for name in LAYOUT if name in schema]
    loose = [name for name in DETACHED if name in schema]

    legend = "".join(
        f'<div class="legend-item"><span class="dot" style="border-color:{colour}"></span>{label}</div>'
        for label, colour in (
            ("Hub table", KIND_COLOUR["hub"]),
            ("Entity", KIND_COLOUR["entity"]),
            ("Junction", KIND_COLOUR["junction"]),
            ("Song detail", KIND_COLOUR["detail"]),
            ("Not on the diagram", KIND_COLOUR["loose"]),
        )
    )

    facts = "".join(
        f"<tr><td>{html.escape(name)}</td><td class=\"num\">{schema[name]['rows']:,}</td>"
        f"<td class=\"num\">{len(schema[name]['columns'])}</td>"
        f"<td>{html.escape(PURPOSE.get(name, ''))}</td></tr>"
        for name in sorted(schema, key=lambda n: -schema[n]["rows"])
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(source.name)} — ViTune Relationship Map</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>{STYLE}</style>
</head>
<body>
<header class="page">
  <div>
    <h1>ViTune <span>&#183; relationship map</span></h1>
    <div class="sub">{html.escape(source.name)} &#183; {len(schema)} tables &#183; {len(views)} view &#183; {total_rows:,} rows &#183; generated {datetime.now():%Y-%m-%d}</div>
  </div>
  <div class="header-badges">
    <span class="badge badge-green">Song is the hub</span>
    <span class="badge badge-orange">3 junctions</span>
    <span class="badge badge-blue">Android Room</span>
  </div>
</header>
<main>

<section>
  <h2>The shape of it</h2>
  <p class="lede">
    ViTune is an Android Room database, so every table is a Kotlin entity and every
    relationship is a declared foreign key. <strong>Song</strong> is the hub and its
    primary key is the YouTube video id, which is why a ViTune backup can be merged with
    anything else keyed the same way. Three junction tables carry the many-to-many
    relationships to artists, albums and playlists; three more tables hang one-to-one or
    one-to-many detail off a song. Everything else is app state rather than music.
  </p>
  <div class="legend">{legend}</div>
  <div class="diagram-wrap">{build_diagram(schema)}</div>
</section>

<section>
  <h2>Relationships</h2>
  <p class="lede">
    Every one of these is a real foreign key in the file, not an inferred one. The path is
    what a query has to walk to answer the question in the title.
  </p>
  <div class="rels-grid">{build_relationship_cards(schema)}</div>
</section>

<section>
  <h2>Tables that carry music</h2>
  <p class="lede">
    Primary keys in yellow, foreign keys in orange, with the table each one points at.
  </p>
  <div class="ref-grid">{build_schema_cards(schema, connected)}</div>
</section>

<section>
  <h2>Tables that do not</h2>
  <p class="lede">
    App state, not library. An importer should read none of these: they describe what the
    player was doing, not what the operator saved.
  </p>
  <div class="ref-grid">{build_schema_cards(schema, loose)}</div>
</section>

<section>
  <h2>Every table by size</h2>
  <table class="facts">
    <thead><tr><th>Table</th><th style="text-align:right">Rows</th><th style="text-align:right">Columns</th><th>What it is for</th></tr></thead>
    <tbody>{facts}</tbody>
  </table>
</section>

</main>
<footer>
  Generated by <code>Docs/generate_vitune_erd.py</code> from {html.escape(str(source))}.
  Re-run it against a newer backup to refresh this page.
  See <code>Docs/song_db_erd.html</code> for the OpenTune schema and
  <code>Docs/opentune_vs_vitune.html</code> for the comparison.
</footer>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: python3 {Path(__file__).name} <ViTune_backup.db> [output.html]", file=sys.stderr)
        return 2

    source = Path(argv[1]).expanduser()
    if not source.exists():
        print(f"No such backup: {source}", file=sys.stderr)
        return 1

    output = Path(argv[2]).expanduser() if len(argv) > 2 else OUTPUT
    schema_info = read_schema(source)
    output.write_text(build_page(source, schema_info), encoding="utf-8")
    print(f"Wrote {output} from {source.name}: {len(schema_info['tables'])} tables.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
