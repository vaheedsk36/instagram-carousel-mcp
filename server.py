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
from carousel import news as news_mod
from carousel import reel as reel_mod
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


def _render_reel(reel_id: str, title: str, theme_name: str | None,
                 scenes: list[dict], *, brand_name: str | None = None,
                 caption: str = "", hashtags: list[str] | None = None,
                 per_scene: float = 3.2, transition: float = 0.6,
                 music: list[str] | None = None, strategy: str = "") -> dict:
    if not scenes:
        raise ValueError("A reel needs at least one scene.")
    if len(scenes) > 12:
        raise ValueError("Keep reels to 12 scenes or fewer.")

    brand = brand_mod.load_brand(brand_name) if brand_name else None
    if brand:
        theme = brand.resolve_theme(theme_name)
        logo_uri = brand.logo_data_uri()
        if brand.handle:
            for s in scenes:
                s.setdefault("handle", brand.handle)
    else:
        theme = get_theme(theme_name or "midnight")
        logo_uri = None

    W, H = render_mod.SIZES["story"]  # reels are always vertical 9:16
    reel_dir = OUTPUT_ROOT / reel_id
    reel_dir.mkdir(parents=True, exist_ok=True)
    for old in (list(reel_dir.glob("scene-*.svg")) + list(reel_dir.glob("scene-*.png"))
                + list(reel_dir.glob("bug.*"))):
        old.unlink()

    # Channel brand bug (persistent watermark): brand handle/logo, else a
    # handle set on the scenes.
    bug_handle = brand.handle if brand and brand.handle else next(
        (s["handle"] for s in scenes if s.get("handle")), "")
    bug_png = None
    if bug_handle or logo_uri:
        bug_svg = render_mod.render_brand_bug(theme, bug_handle, logo_uri, W, H)
        (reel_dir / "bug.svg").write_text(bug_svg)
        bug_png = reel_dir / "bug.png"
        reel_mod.rasterize(reel_dir / "bug.svg", bug_png)

    # Reserve a clear header band so top-aligned text doesn't collide with the bug.
    inset = 130 if bug_png else 0

    total = len(scenes)
    bg_pngs, fg_pngs, configs = [], [], []
    for i, scene in enumerate(scenes):
        # Render a copy: no footer handle/page (the bug handles branding), but
        # leave `scenes` untouched so spec.json round-trips for regeneration.
        rscene = {**scene, "page": False, "handle": None}
        for lyr, bucket in (("bg", bg_pngs), ("fg", fg_pngs)):
            svg = render_mod.render_slide(rscene, theme, W, H, i, total,
                                          logo_data_uri=None, layer=lyr, top_inset=inset)
            svg_path = reel_dir / f"scene-{i}-{lyr}.svg"
            png_path = reel_dir / f"scene-{i}-{lyr}.png"
            svg_path.write_text(svg)
            reel_mod.rasterize(svg_path, png_path)
            bucket.append(png_path)
        configs.append({
            "duration": scene.get("duration"),
            "motion": scene.get("motion"),
            "transition": scene.get("transition"),
            "transition_dur": scene.get("transition_dur"),
        })

    out_mp4 = reel_dir / "reel.mp4"
    reel_mod.compile_video(bg_pngs, fg_pngs, out_mp4, configs=configs, bug_path=bug_png,
                           per_scene=per_scene, transition=transition)
    durs = [float(c.get("duration") or per_scene) for c in configs]
    tdurs = [float(c.get("transition_dur") or transition) for c in configs]
    duration = reel_mod.total_duration(durs, tdurs)

    full_caption = brand_mod.build_caption(caption, hashtags or [], brand, max_hashtags=5)
    (reel_dir / "caption.txt").write_text(full_caption)
    if music:
        (reel_dir / "music.txt").write_text("\n".join(music))
    if strategy:
        (reel_dir / "strategy.md").write_text(strategy)
    preview_mod.write_reel_index(reel_dir, title, full_caption, duration, music=music or [])
    pv = preview_mod.PreviewServer.ensure(OUTPUT_ROOT)
    (reel_dir / "spec.json").write_text(json.dumps({
        "title": title, "theme": theme_name, "scenes": scenes, "brand": brand_name,
        "caption": caption, "hashtags": hashtags or [], "kind": "reel",
        "per_scene": per_scene, "transition": transition,
        "music": music or [], "strategy": strategy,
    }, indent=2))

    return {
        "reel_id": reel_id,
        "scenes": total,
        "dimensions": f"{W}x{H}",
        "duration_sec": duration,
        "video": str(out_mp4),
        "directory": str(reel_dir),
        "preview_url": pv.url_for(reel_id),
        "caption": full_caption,
        "music": music or [],
    }


@mcp.tool()
def list_themes() -> list[dict]:
    """List available visual themes (name, description, colours)."""
    return _list_themes()


@mcp.tool()
def create_reel(
    scenes: list[dict[str, Any]],
    title: str = "Reel",
    theme: str | None = None,
    brand: str | None = None,
    caption: str = "",
    hashtags: list[str] | None = None,
    per_scene: float = 3.2,
    transition: float = 0.6,
    music: list[str] | None = None,
    strategy: str = "",
) -> dict:
    """Create a vertical Instagram Reel (1080x1920 MP4) from text/image scenes.

    Build engagement-driven, not generic: open with a scroll-stopping hook,
    use specific/expert points (numbers, names, a surprising claim) not filler,
    keep hashtags to <=5 sharp tags, and provide music ideas.

    Each scene uses the SAME spec as a carousel slide (template + fields). For
    visuals choose the right source per scene:
      portrait="Name" / logo -> real person/brand (source of truth)
      background_photo / photo -> a REAL photo (news, reporting, real-world);
          fetched from stock (Pexels/Openverse), cheaper and truthful
      background_query / image_query -> AI-GENERATED (conceptual/abstract only)
    Use real photos for anything factual/newsy; generate only for concepts.

    Per-scene creative controls (tailor to the content — punchy hook vs. a stat
    that holds): duration, motion ("zoomin"/"zoomout"/"panleft"/"panright"/
    "none"), transition (any ffmpeg xfade: "fade","slideup","wipeleft",
    "circleopen","dissolve"...), transition_dur.

    music: 3-5 trending/audio recommendations (track — artist — why it fits),
        written to music.txt and shown in the preview (IG audio can't be API-set,
        so the creator adds it in-app).
    strategy: optional markdown brief (hook, retention plan) saved as strategy.md.

    Per-scene creative controls (set on each scene dict; tailor them to the
    content — punchy hook vs. a stat that holds, etc.):
        duration: seconds this scene is on screen (e.g. 2.4 hook, 3.6 stat).
        motion: "zoomin" | "zoomout" | "panleft" | "panright" | "none".
        transition: the crossfade INTO the next scene — any ffmpeg xfade name,
            e.g. "fade", "slideleft", "wipeup", "circleopen", "dissolve",
            "zoomin", "pixelize".
        transition_dur: seconds for that crossfade (default 0.6).

    Args:
        scenes: list of scene specs (like carousel slides). 3-7 works best.
        title: used for the output folder/file name.
        theme: theme name, or omit to use the brand's theme.
        brand: a saved brand profile (applies theme, logo, @handle, hashtags).
        caption: the post caption (signature + hashtags appended automatically).
        hashtags: extra hashtags for this reel.
        per_scene: seconds each scene is shown (default 3.2).
        transition: crossfade seconds between scenes (default 0.6).

    Returns the MP4 path, duration, and assembled caption. Requires ffmpeg and
    rsvg-convert installed.
    """
    reel_id = _slug(title)
    return _render_reel(reel_id, title, theme, scenes, brand_name=brand,
                        caption=caption, hashtags=hashtags,
                        per_scene=per_scene, transition=transition,
                        music=music, strategy=strategy)


@mcp.tool()
def trending_topics(query: str, limit: int = 10, days: int = 7) -> list[dict]:
    """Find recent/trending news headlines for a topic (Google News, no API key).

    Use this to discover a timely angle before building a carousel: fetch
    headlines for the subject, pick the most compelling/relevant story, then
    research it and call create_carousel. Each result has title, source,
    published date, and link.

    Args:
        query: the subject to search news for, e.g. "AI agents", "fitness".
        limit: max headlines to return (default 10).
        days: only include items from the last N days (default 7; 0 = no limit).
    """
    return news_mod.trending(query, limit=limit, days=days)


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
              portrait: a real person's name (e.g. "Mark Zuckerberg") — fetches
                  their actual photo from Wikipedia as a full-bleed background.
              background_query / image_query: a text description — the server
                  auto-sources a fitting image (Replicate/Flux → Pexels →
                  Openverse → Picsum) and embeds it. Zero manual files needed.
            Policy: for real entities (people, company logos) prefer a source of
            truth — `portrait` for people, and fetch logos via Wikimedia — and
            only GENERATE (background_query/image_query) for conceptual/abstract
            visuals. Never fabricate a real person's face or a brand's logo.
            *_image values may be a local file path, an http(s) URL, or data URI.
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
