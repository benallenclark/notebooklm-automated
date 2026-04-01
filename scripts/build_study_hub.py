#!/usr/bin/env python3
"""
Build a simple static HTML study hub from Markdown files.

What it does:
- Reads all .md files from an input directory (default: output/)
- Creates a hub page (index.html) listing every concept file
- Creates one HTML page per markdown file
- Each concept page includes a Home button back to the hub
- Links open in the same tab by default

Usage:
    python build_study_hub.py
    python build_study_hub.py --input output --site-dir study_hub
    python build_study_hub.py --title "NotebookLM Study Hub"
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
from pathlib import Path


# -----------------------------
# Markdown rendering helpers
# -----------------------------
def slugify(name: str) -> str:
    """Turn a filename stem into a filesystem-safe slug."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower())
    return slug.strip("-") or "document"


def inline_markdown(text: str) -> str:
    """Very small inline markdown renderer for common patterns."""
    escaped = html.escape(text)

    # Code spans
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    # Bold
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    # Italic
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
    # Markdown links
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2">\1</a>',
        escaped,
    )

    return escaped


def markdown_to_html(md_text: str) -> str:
    """
    Render a small subset of markdown without external dependencies.

    Supports:
    - #, ##, ### headings
    - horizontal rules (---)
    - paragraphs
    - unordered list items starting with -, *, or ·
    - inline bold/italic/code/links
    """
    lines = md_text.splitlines()
    parts: list[str] = []
    paragraph_buffer: list[str] = []
    list_buffer: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_buffer:
            text = " ".join(item.strip() for item in paragraph_buffer if item.strip())
            if text:
                parts.append(f"<p>{inline_markdown(text)}</p>")
            paragraph_buffer.clear()

    def flush_list() -> None:
        if list_buffer:
            items = "\n".join(f"<li>{inline_markdown(item)}</li>" for item in list_buffer)
            parts.append(f"<ul>\n{items}\n</ul>")
            list_buffer.clear()

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        if stripped == "---":
            flush_paragraph()
            flush_list()
            parts.append("<hr>")
            continue

        if stripped.startswith("### "):
            flush_paragraph()
            flush_list()
            parts.append(f"<h3>{inline_markdown(stripped[4:])}</h3>")
            continue

        if stripped.startswith("## "):
            flush_paragraph()
            flush_list()
            parts.append(f"<h2>{inline_markdown(stripped[3:])}</h2>")
            continue

        if stripped.startswith("# "):
            flush_paragraph()
            flush_list()
            parts.append(f"<h1>{inline_markdown(stripped[2:])}</h1>")
            continue

        list_match = re.match(r"^[-*·]\s+(.*)$", stripped)
        if list_match:
            flush_paragraph()
            list_buffer.append(list_match.group(1))
            continue

        flush_list()
        paragraph_buffer.append(stripped)

    flush_paragraph()
    flush_list()

    return "\n".join(parts)


# -----------------------------
# HTML builders
# -----------------------------
def base_html(title: str, body: str) -> str:
    """Wrap content in a simple readable HTML shell."""
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #0b1020;
      --surface: #121a31;
      --surface-2: #1b2647;
      --text: #eef2ff;
      --muted: #b6c2e2;
      --border: #31406d;
      --link: #9ec5ff;
      --accent: #6aa6ff;
      --accent-2: #84b8ff;
      --shadow: 0 10px 30px rgba(0,0,0,.25);
    }}

    @media (prefers-color-scheme: light) {{
      :root {{
        --bg: #f6f8fc;
        --surface: #ffffff;
        --surface-2: #f0f4fb;
        --text: #18243d;
        --muted: #53627f;
        --border: #dbe4f3;
        --link: #0b61ff;
        --accent: #0b61ff;
        --accent-2: #2a73ff;
        --shadow: 0 12px 28px rgba(19,35,68,.08);
      }}
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.65;
    }}

    .wrap {{
      max-width: 1000px;
      margin: 0 auto;
      padding: 32px 20px 56px;
    }}

    .panel {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 28px;
      box-shadow: var(--shadow);
    }}

    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }}

    .home-btn, .raw-btn {{
      display: inline-block;
      text-decoration: none;
      color: white;
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      padding: 10px 14px;
      border-radius: 12px;
      font-weight: 600;
      border: none;
    }}

    .raw-btn {{
      color: var(--text);
      background: var(--surface-2);
      border: 1px solid var(--border);
    }}

    .meta {{
      color: var(--muted);
      font-size: 0.95rem;
      margin-bottom: 18px;
    }}

    h1, h2, h3 {{
      line-height: 1.2;
      margin-top: 1.4em;
      margin-bottom: 0.6em;
    }}

    h1 {{ font-size: 2rem; margin-top: 0; }}
    h2 {{ font-size: 1.35rem; padding-top: 0.35rem; border-top: 1px solid var(--border); }}
    h3 {{ font-size: 1.05rem; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }}

    p, ul {{ margin: 0.8em 0; }}
    ul {{ padding-left: 1.35rem; }}
    li {{ margin: 0.35em 0; }}

    hr {{
      border: 0;
      border-top: 1px solid var(--border);
      margin: 1.5rem 0;
    }}

    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      background: var(--surface-2);
      padding: 0.15em 0.4em;
      border-radius: 6px;
      border: 1px solid var(--border);
      font-size: .95em;
    }}

    a {{ color: var(--link); }}

    .hub-list {{
      list-style: none;
      padding: 0;
      margin: 1.25rem 0 0;
      display: grid;
      gap: 14px;
    }}

    .hub-card {{
      display: block;
      text-decoration: none;
      color: inherit;
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 18px 18px;
      transition: transform .12s ease, border-color .12s ease;
    }}

    .hub-card:hover {{
      transform: translateY(-1px);
      border-color: var(--accent);
    }}

    .hub-title {{
      font-size: 1.05rem;
      font-weight: 700;
      margin-bottom: 6px;
    }}

    .hub-sub {{ color: var(--muted); font-size: .95rem; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="panel">
      {body}
    </div>
  </div>
</body>
</html>
"""


def build_index_page(title: str, entries: list[dict[str, str]]) -> str:
    cards = []
    for entry in entries:
        cards.append(
            f"""
<li>
  <a class="hub-card" href="{html.escape(entry['html_filename'])}">
    <div class="hub-title">{html.escape(entry['title'])}</div>
    <div class="hub-sub">{html.escape(entry['md_filename'])}</div>
  </a>
</li>
"""
        )

    body = f"""
<div class="topbar">
  <div>
    <h1 style="margin:0;">{html.escape(title)}</h1>
    <div class="meta">Click a concept to open it in this same tab.</div>
  </div>
</div>

<ul class="hub-list">
  {''.join(cards)}
</ul>
"""
    return base_html(title, body)


def build_concept_page(hub_title: str, entry_title: str, raw_md_filename: str, content_html: str) -> str:
    body = f"""
<div class="topbar">
  <a class="home-btn" href="index.html">← Home</a>
  <a class="raw-btn" href="raw/{html.escape(raw_md_filename)}">Open raw markdown</a>
</div>

<div class="meta">{html.escape(hub_title)}</div>
{content_html}
"""
    return base_html(entry_title, body)


# -----------------------------
# Main build logic
# -----------------------------
def build_site(input_dir: Path, site_dir: Path, title: str) -> None:
    md_files = sorted(input_dir.glob("*.md"))
    if not md_files:
        raise FileNotFoundError(f"No .md files found in: {input_dir}")

    site_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = site_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, str]] = []

    for md_path in md_files:
        raw_text = md_path.read_text(encoding="utf-8")
        stem = md_path.stem
        html_filename = f"{slugify(stem)}.html"

        # Derive title from first markdown H1 if available
        title_match = re.search(r"^#\s+(.+)$", raw_text, flags=re.MULTILINE)
        entry_title = title_match.group(1).strip() if title_match else stem.replace("_", " ").title()

        # Copy raw markdown into site/raw for optional access
        shutil.copy2(md_path, raw_dir / md_path.name)

        # Build concept page
        concept_html = markdown_to_html(raw_text)
        concept_page = build_concept_page(title, entry_title, md_path.name, concept_html)
        (site_dir / html_filename).write_text(concept_page, encoding="utf-8")

        entries.append(
            {
                "title": entry_title,
                "html_filename": html_filename,
                "md_filename": md_path.name,
            }
        )

    # Build hub page
    index_html = build_index_page(title, entries)
    (site_dir / "index.html").write_text(index_html, encoding="utf-8")


# -----------------------------
# CLI
# -----------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an HTML study hub from Markdown files.")
    parser.add_argument(
        "--input",
        default="output",
        help="Directory containing .md files (default: output)",
    )
    parser.add_argument(
        "--site-dir",
        default="study_hub",
        help="Directory where HTML files will be written (default: study_hub)",
    )
    parser.add_argument(
        "--title",
        default="NotebookLM Study Hub",
        help="Title shown on the hub page (default: NotebookLM Study Hub)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input).resolve()
    site_dir = Path(args.site_dir).resolve()
    build_site(input_dir=input_dir, site_dir=site_dir, title=args.title)
    print(f"Study hub created: {site_dir / 'index.html'}")


if __name__ == "__main__":
    main()
