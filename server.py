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

from carousel import brand as brand_mod
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


def _render_all(carousel_id: str, title: str, theme_name: str | None, size: str,
                slides: list[dict], *, brand_name: str | None = None,
                caption: str = "", hashtags: list[str] | None = None) -> dict:
    if size not in render_mod.SIZES:
        raise ValueError(f"Unknown size '{size}'. Options: {', '.join(render_mod.SIZES)}")
    if not slides:
        raise ValueError("At least one slide is required.")
    if len(slides) > 20:
        raise ValueError("Instagram carousels support at most 20 slides.")

    brand = brand_mod.load_brand(brand_name) if brand_name else None
    if brand:
        theme = brand.resolve_theme(theme_name)
        logo_uri = brand.logo_data_uri()
        # Auto-fill handle on slides that didn't set one.
        if brand.handle:
            for s in slides:
                s.setdefault("handle", brand.handle)
    else:
        theme = get_theme(theme_name or "midnight")
        logo_uri = None

    W, H = render_mod.SIZES[size]
    carousel_dir = OUTPUT_ROOT / carousel_id
    carousel_dir.mkdir(parents=True, exist_ok=True)

    # Clear stale slide files.
    for old in list(carousel_dir.glob("slide-*.svg")) + list(carousel_dir.glob("slide-*.png")):
        old.unlink()

    total = len(slides)
    for i, slide in enumerate(slides):
        svg = render_mod.render_slide(slide, theme, W, H, i, total, logo_data_uri=logo_uri)
        (carousel_dir / f"slide-{i}.svg").write_text(svg)

    full_caption = brand_mod.build_caption(caption, hashtags or [], brand)
    (carousel_dir / "caption.txt").write_text(full_caption)

    preview_mod.write_manifest(carousel_dir, title, size, (W, H), slides, caption=full_caption)
    preview_mod.write_index(carousel_dir)
    (carousel_dir / "spec.json").write_text(json.dumps({
        "title": title, "theme": theme_name, "size": size, "slides": slides,
        "brand": brand_name, "caption": caption, "hashtags": hashtags or [],
    }, indent=2))

    server = preview_mod.PreviewServer.ensure(OUTPUT_ROOT)
    return {
        "carousel_id": carousel_id,
        "slides": total,
        "dimensions": f"{W}x{H}",
        "directory": str(carousel_dir),
        "preview_url": server.url_for(carousel_id),
        "caption_file": str(carousel_dir / "caption.txt"),
        "caption": full_caption,
    }


@mcp.tool()
def list_themes() -> list[dict]:
    """List available visual themes (name, description, colours)."""
    return _list_themes()


@mcp.tool()
def create_carousel(
    slides: list[dict[str, Any]],
    title: str = "Carousel",
    theme: str | None = None,
    size: str = "portrait",
    brand: str | None = None,
    caption: str = "",
    hashtags: list[str] | None = None,
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
            Images:
              background_image: any slide — full-bleed photo behind the content
                  (text auto-switches to light + a scrim keeps it readable).
              image:    on `content` — inline rounded image card above the body.
            Image values may be a local file path, an http(s) URL, or a data URI.
            Optional on any slide: handle (e.g. "@brand"), page (bool, show n/total).
        title: human title (also used for the output folder name).
        theme: theme name (see list_themes). If a brand is given, omit this to
            use the brand's theme, or set it to override.
        size: "portrait" (1080x1350, recommended), "square" (1080x1080),
            or "story" (1080x1920).
        brand: a saved brand profile name (see list_brands / save_brand). Applies
            the brand's theme, logo, @handle, and default hashtags automatically.
        caption: the Instagram post caption text (the words under the post). The
            brand's signature and default hashtags are appended automatically.
        hashtags: extra hashtags for this post (merged with the brand's defaults).

    Returns a dict with `preview_url` (open in the Preview tool) and the assembled
    `caption` (also written to caption.txt and shown with a copy button in preview).
    """
    carousel_id = _slug(title)
    return _render_all(carousel_id, title, theme, size, slides,
                       brand_name=brand, caption=caption, hashtags=hashtags)


@mcp.tool()
def save_brand(profile: dict[str, Any]) -> dict:
    """Create or update a brand profile (persisted to brands/<name>.json).

    Fields (all optional except `name`):
        name: short id, e.g. "mypage"
        handle: "@yourpage" — auto-added to every slide's footer
        logo: path to a logo image (png/jpg/svg); embedded top-left on slides
        base_theme: a built-in theme to start from (default "midnight")
        theme: dict of overrides on top of base_theme — any of:
            bg ("#hex" | ["#a","#b"] gradient), bg_angle, text, muted,
            accent, accent_fg, font_sans, font_serif
        default_hashtags: list of hashtags appended to every caption
        caption_signature: text appended to captions, e.g. "Follow @yourpage 🚀"
        default_size: "portrait" | "square" | "story"

    Partial updates merge into any existing profile of the same name.
    """
    path = brand_mod.save_brand(profile)
    return {"saved": str(path), "brands": brand_mod.list_brands()}


@mcp.tool()
def list_brands() -> list[dict]:
    """List saved brand profiles."""
    return brand_mod.list_brands()


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
    return _render_all(carousel_id, spec["title"], spec.get("theme"), spec["size"], slides,
                       brand_name=spec.get("brand"), caption=spec.get("caption", ""),
                       hashtags=spec.get("hashtags", []))


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
    return _render_all(carousel_id, spec["title"], spec.get("theme"), spec["size"], slides,
                       brand_name=spec.get("brand"), caption=spec.get("caption", ""),
                       hashtags=spec.get("hashtags", []))


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
