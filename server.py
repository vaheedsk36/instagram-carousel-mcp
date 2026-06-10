"""Instagram Carousel MCP server.

Exposes tools to design multi-slide Instagram carousels as SVG, preview them
live in the browser (swipeable), and export to PNG.

Tools
  list_themes       -> available visual themes
  create_carousel   -> build a carousel from a slide spec; writes SVGs + preview
  update_slide      -> replace/edit a single slide and re-render
  get_preview_url   -> URL of the live swipeable preview (open in Preview tool)
  export_png        -> rasterise slides to PNG server-side (needs Playwright)

Slide spec: a list of dicts, each with a `template` and template-specific
fields. See render.py for the full field reference. Example slide:
  {"template": "title", "eyebrow": "Guide", "heading": "5 ways to ship faster",
   "subheading": "A field-tested playbook", "handle": "@yourbrand"}
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from carousel import export as export_mod
from carousel import preview as preview_mod
from carousel import render as render_mod
from carousel.themes import get_theme, list_themes as _list_themes

OUTPUT_ROOT = Path(__file__).parent / "output"
OUTPUT_ROOT.mkdir(exist_ok=True)

mcp = FastMCP("instagram-carousel")


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "carousel").lower()).strip("-")
    return s[:48] or "carousel"


def _render_all(carousel_id: str, title: str, theme_name: str, size: str, slides: list[dict]) -> dict:
    if size not in render_mod.SIZES:
        raise ValueError(f"Unknown size '{size}'. Options: {', '.join(render_mod.SIZES)}")
    if not slides:
        raise ValueError("At least one slide is required.")
    if len(slides) > 20:
        raise ValueError("Instagram carousels support at most 20 slides.")

    theme = get_theme(theme_name)
    W, H = render_mod.SIZES[size]
    carousel_dir = OUTPUT_ROOT / carousel_id
    carousel_dir.mkdir(parents=True, exist_ok=True)

    # Clear stale slide files.
    for old in carousel_dir.glob("slide-*.svg"):
        old.unlink()
    for old in carousel_dir.glob("slide-*.png"):
        old.unlink()

    total = len(slides)
    for i, slide in enumerate(slides):
        svg = render_mod.render_slide(slide, theme, W, H, i, total)
        (carousel_dir / f"slide-{i}.svg").write_text(svg)

    preview_mod.write_manifest(carousel_dir, title, size, (W, H), slides)
    preview_mod.write_index(carousel_dir)
    (carousel_dir / "spec.json").write_text(json.dumps(
        {"title": title, "theme": theme_name, "size": size, "slides": slides}, indent=2))

    server = preview_mod.PreviewServer.ensure(OUTPUT_ROOT)
    return {
        "carousel_id": carousel_id,
        "slides": total,
        "dimensions": f"{W}x{H}",
        "directory": str(carousel_dir),
        "preview_url": server.url_for(carousel_id),
    }


@mcp.tool()
def list_themes() -> list[dict]:
    """List available visual themes (name, description, colours)."""
    return _list_themes()


@mcp.tool()
def create_carousel(
    slides: list[dict[str, Any]],
    title: str = "Carousel",
    theme: str = "midnight",
    size: str = "portrait",
) -> dict:
    """Create an Instagram carousel from a list of slide specs.

    Args:
        slides: list of slide dicts. Each has a `template` key — one of
            "title", "content", "list", "quote", "stat", "cta" — plus fields:
              title:   eyebrow?, heading, subheading?, handle?
              content: eyebrow?, heading, body
              list:    eyebrow?, heading, items[] (strings), ordered? (bool)
              quote:   quote, author?, role?
              stat:    value, label?, caption?
              cta:     eyebrow?, heading, body?, button?, handle?
            Optional on any slide: handle (e.g. "@brand"), page (bool, show n/total).
        title: human title (also used for the output folder name).
        theme: theme name (see list_themes). Default "midnight".
        size: "portrait" (1080x1350, recommended), "square" (1080x1080),
            or "story" (1080x1920).

    Returns a dict with the preview_url — open it with the Preview tool to view
    the swipeable carousel and download PNGs.
    """
    carousel_id = _slug(title)
    return _render_all(carousel_id, title, theme, size, slides)


@mcp.tool()
def update_slide(carousel_id: str, index: int, slide: dict[str, Any]) -> dict:
    """Replace a single slide (0-based index) and re-render the carousel.

    Reads the existing spec.json for the carousel, swaps in the new slide,
    and regenerates. The live preview picks up changes on refresh.
    """
    spec_path = OUTPUT_ROOT / carousel_id / "spec.json"
    if not spec_path.exists():
        raise ValueError(f"No carousel '{carousel_id}'. Create one first.")
    spec = json.loads(spec_path.read_text())
    slides = spec["slides"]
    if not (0 <= index < len(slides)):
        raise ValueError(f"index {index} out of range (0..{len(slides)-1})")
    slides[index] = slide
    return _render_all(carousel_id, spec["title"], spec["theme"], spec["size"], slides)


@mcp.tool()
def add_slide(carousel_id: str, slide: dict[str, Any], at: int = -1) -> dict:
    """Insert a slide into an existing carousel. `at`=-1 appends to the end."""
    spec_path = OUTPUT_ROOT / carousel_id / "spec.json"
    if not spec_path.exists():
        raise ValueError(f"No carousel '{carousel_id}'. Create one first.")
    spec = json.loads(spec_path.read_text())
    slides = spec["slides"]
    if at < 0 or at > len(slides):
        slides.append(slide)
    else:
        slides.insert(at, slide)
    return _render_all(carousel_id, spec["title"], spec["theme"], spec["size"], slides)


@mcp.tool()
def get_preview_url(carousel_id: str) -> dict:
    """Return the live preview URL for a carousel (starts the server if needed)."""
    carousel_dir = OUTPUT_ROOT / carousel_id
    if not carousel_dir.exists():
        raise ValueError(f"No carousel '{carousel_id}'.")
    server = preview_mod.PreviewServer.ensure(OUTPUT_ROOT)
    return {"carousel_id": carousel_id, "preview_url": server.url_for(carousel_id)}


@mcp.tool()
def export_png(carousel_id: str) -> dict:
    """Export all slides to PNG files server-side (requires Playwright).

    The easiest export is the "Download all PNGs" button in the live preview
    (no setup). Use this tool for headless/automated export.
    """
    carousel_dir = OUTPUT_ROOT / carousel_id
    manifest_path = carousel_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"No carousel '{carousel_id}'.")
    m = json.loads(manifest_path.read_text())
    files = export_mod.export_png(carousel_dir, m["width"], m["height"])
    return {"carousel_id": carousel_id, "png_files": files, "count": len(files)}


if __name__ == "__main__":
    mcp.run()
