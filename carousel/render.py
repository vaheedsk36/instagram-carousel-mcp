"""Render a carousel slide spec into a self-contained SVG string.

A *slide* is a dict with a ``template`` key plus template-specific fields. The
renderer lays text out top-to-bottom (or centred for hero templates), wrapping
long strings into ``<tspan>`` lines using an approximate character-width model
(SVG has no native text wrapping).

Supported templates and their fields:

  title    eyebrow?, heading,  subheading?, handle?
  content  eyebrow?, heading,  body
  list     eyebrow?, heading,  items[] (strings), ordered? (bool)
  quote    quote,    author?,  role?
  stat     value,    label?,   caption?
  cta      eyebrow?, heading,  body?, button?, handle?

Images:
  background_image  any slide — a full-bleed photo behind the content, with an
                    automatic dark scrim so text stays readable (text switches
                    to light automatically). Value: file path, URL, or data URI.
  image             on the `content` template — an inline image card shown
                    between the heading and the body text.

Common optional fields on every slide: ``page`` (bool, show "n / total"),
``handle`` (e.g. "@yourbrand"). Sizes are chosen for a 1080px-wide canvas and
scale with the canvas height.
"""
from __future__ import annotations

import base64
import mimetypes
import urllib.request
from dataclasses import replace
from pathlib import Path

from .themes import Theme

# Where relative image paths are resolved from (project root).
_ROOT = Path(__file__).parent.parent


def _real_uri(kind: str, name: str, w: int, h: int) -> str | None:
    """Source-of-truth image (real person portrait / company logo) as a data
    URI. Returns None if no authoritative image exists — we never fabricate a
    real person's face or a brand's logo."""
    try:
        from . import images
        return to_data_uri(str(images.get_real_image(name, kind)))
    except Exception as e:  # noqa: BLE001
        import sys
        print(f"[render] no source-of-truth {kind} for {name!r}: {e}", file=sys.stderr)
        return None


def _sourced_uri(query: str, w: int, h: int, providers: list[str] | None = None) -> str | None:
    """Auto-source an image for a text query and return it as a data URI.

    `providers` lets the caller force REAL photos (e.g. ["pexels","openverse",
    "picsum"]) instead of AI generation. Failures are swallowed (returns None)
    so a missing image never breaks the carousel.
    """
    try:
        from . import images
        return to_data_uri(str(images.get_image_path(query, w, h, providers=providers)))
    except Exception as e:  # noqa: BLE001
        import sys
        print(f"[render] image source failed for {query!r}: {e}", file=sys.stderr)
        return None


# Real-photo providers (no AI generation) — for news/reporting/real-world scenes.
_PHOTO_PROVIDERS = ["pexels", "openverse", "picsum"]


def to_data_uri(src: str | None) -> str | None:
    """Resolve an image reference to a base64 data URI so it embeds in the SVG.

    Accepts an existing data URI, an http(s) URL (fetched), an absolute path, or
    a path relative to the project root. Returns None for falsy input.
    """
    if not src:
        return None
    if src.startswith("data:"):
        return src
    if src.startswith(("http://", "https://")):
        req = urllib.request.Request(src, headers={"User-Agent": "carousel/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
            mime = r.headers.get_content_type() or "image/jpeg"
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    p = Path(src).expanduser()
    if not p.is_absolute():
        p = (_ROOT / src).resolve()
    if not p.exists():
        raise ValueError(f"Image not found: {src} (looked at {p})")
    mime = mimetypes.guess_type(str(p))[0] or "image/png"
    if p.suffix.lower() == ".svg":
        mime = "image/svg+xml"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"

# Canvas presets (width, height) in pixels — Instagram-friendly aspect ratios.
SIZES: dict[str, tuple[int, int]] = {
    "portrait": (1080, 1350),  # 4:5  — recommended for feed carousels
    "square": (1080, 1080),    # 1:1
    "story": (1080, 1920),     # 9:16 — reels/stories
}

PAD = 96  # outer padding


def esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def wrap_text(text: str, font_size: float, max_width: float, char_ratio: float = 0.56) -> list[str]:
    """Greedy word-wrap. Approximates glyph width as ``char_ratio * font_size``."""
    if not text:
        return [""]
    max_chars = max(1, int(max_width / (char_ratio * font_size)))
    lines: list[str] = []
    for paragraph in str(text).split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            if len(cur) + 1 + len(w) <= max_chars:
                cur += " " + w
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def _gradient_defs(theme: Theme, grad_id: str) -> str:
    if len(theme.bg) == 1:
        return ""
    import math

    angle = math.radians(theme.bg_angle)
    x2 = round(0.5 + math.cos(angle) * 0.5, 4)
    y2 = round(0.5 + math.sin(angle) * 0.5, 4)
    x1 = round(0.5 - math.cos(angle) * 0.5, 4)
    y1 = round(0.5 - math.sin(angle) * 0.5, 4)
    stops = "".join(
        f'<stop offset="{o*100:.0f}%" stop-color="{c}"/>' for o, c in theme.bg
    )
    return (
        f'<linearGradient id="{grad_id}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">'
        f"{stops}</linearGradient>"
    )


def _bg_fill(theme: Theme, grad_id: str) -> str:
    return theme.bg[0][1] if len(theme.bg) == 1 else f"url(#{grad_id})"


def _text_lines(
    lines: list[str],
    x: float,
    y: float,
    *,
    size: float,
    fill: str,
    weight: int = 400,
    line_height: float = 1.15,
    family: str,
    anchor: str = "start",
    letter_spacing: float | None = None,
    uppercase: bool = False,
) -> tuple[str, float]:
    """Emit a multi-line text block. Returns (svg, bottom_y)."""
    ls = f' letter-spacing="{letter_spacing}"' if letter_spacing is not None else ""
    spans = []
    for i, ln in enumerate(lines):
        content = esc(ln.upper() if uppercase else ln)
        dy = "0" if i == 0 else f"{line_height:.3f}em"
        spans.append(f'<tspan x="{x}" dy="{dy}">{content}</tspan>')
    svg = (
        f'<text x="{x}" y="{y:.1f}" fill="{fill}" font-family="{family}" '
        f'font-size="{size:.0f}" font-weight="{weight}" text-anchor="{anchor}"{ls}>'
        f'{"".join(spans)}</text>'
    )
    bottom = y + max(0, (len(lines) - 1)) * size * line_height
    return svg, bottom


def _footer(slide: dict, theme: Theme, W: int, H: int, index: int, total: int) -> str:
    parts = []
    handle = slide.get("handle")
    if handle:
        parts.append(
            f'<text x="{PAD}" y="{H - PAD + 8}" fill="{theme.muted}" '
            f'font-family="{theme.font_sans}" font-size="30" font-weight="600">'
            f"{esc(handle)}</text>"
        )
    if slide.get("page", True) and total > 1:
        parts.append(
            f'<text x="{W - PAD}" y="{H - PAD + 8}" fill="{theme.muted}" '
            f'font-family="{theme.font_sans}" font-size="30" font-weight="600" '
            f'text-anchor="end">{index + 1} / {total}</text>'
        )
    return "".join(parts)


def _eyebrow(slide: dict, theme: Theme, y: float) -> tuple[str, float]:
    eb = slide.get("eyebrow")
    if not eb:
        return "", y
    svg, bottom = _text_lines(
        [eb], PAD, y, size=30, fill=theme.accent, weight=700,
        family=theme.font_sans, letter_spacing=4, uppercase=True,
    )
    return svg, bottom + 56


def _logo_svg(logo_data_uri: str | None) -> str:
    if not logo_data_uri:
        return ""
    # Top-left brand mark, scaled to fit a 240x64 box preserving aspect ratio.
    return (
        f'<image x="{PAD}" y="{PAD}" width="240" height="64" '
        f'preserveAspectRatio="xMinYMin meet" href="{logo_data_uri}"/>'
    )


def render_slide(slide: dict, theme: Theme, W: int, H: int, index: int, total: int,
                 logo_data_uri: str | None = None, layer: str = "full",
                 top_inset: int = 0) -> str:
    """layer: 'full' (carousel), 'bg' (background+image only, for a Ken-Burns
    video layer) or 'fg' (transparent text/accent layer that gets animated in).
    top_inset: extra top padding for top-aligned templates (e.g. to clear a
    persistent brand bug on reels)."""
    template = (slide.get("template") or "content").lower()
    grad_id = f"bg{index}"
    inner_w = W - 2 * PAD
    body: list[str] = []

    # Full-bleed background photo: embed, add a dark scrim, and switch text to
    # light so any template stays readable on top of the image.
    bg_uri = to_data_uri(slide.get("background_image"))
    if not bg_uri and slide.get("portrait"):
        bg_uri = _real_uri("portrait", slide["portrait"], W, H)
    if not bg_uri and slide.get("background_photo"):  # real photo (news/real-world)
        bg_uri = _sourced_uri(slide["background_photo"], W, H, providers=_PHOTO_PROVIDERS)
    if not bg_uri and slide.get("background_query"):  # AI-generated (conceptual)
        bg_uri = _sourced_uri(slide["background_query"], W, H)
    bg_layer = ""
    if bg_uri:
        theme = replace(theme, text="#ffffff", muted="rgba(255,255,255,0.85)")
        bg_layer = (
            f'<image x="0" y="0" width="{W}" height="{H}" '
            f'preserveAspectRatio="xMidYMid slice" href="{bg_uri}"/>'
            f'<rect width="{W}" height="{H}" fill="#000000" opacity="0.45"/>'
            f'<rect x="0" y="{H*0.45:.0f}" width="{W}" height="{H*0.55:.0f}" '
            f'fill="url(#scrim{index})"/>'
        )

    if template == "title":
        # Vertically centred hero.
        head_lines = wrap_text(slide.get("heading", ""), 92, inner_w, 0.58)
        sub_lines = wrap_text(slide.get("subheading", ""), 40, inner_w) if slide.get("subheading") else []
        block_h = len(head_lines) * 92 * 1.08 + (len(sub_lines) * 40 * 1.35 + 48 if sub_lines else 0)
        start = (H - block_h) / 2 + 92
        if slide.get("eyebrow"):
            eb, _ = _text_lines([slide["eyebrow"]], PAD, start - 92 - 8, size=30,
                                fill=theme.accent, weight=700, family=theme.font_sans,
                                letter_spacing=4, uppercase=True)
            body.append(eb)
        svg, bottom = _text_lines(head_lines, PAD, start, size=92, fill=theme.text,
                                  weight=800, family=theme.font_sans, line_height=1.08)
        body.append(svg)
        if sub_lines:
            svg, _ = _text_lines(sub_lines, PAD, bottom + 88, size=40, fill=theme.muted,
                                 weight=400, family=theme.font_sans, line_height=1.35)
            body.append(svg)
        # accent rule under eyebrow area
        body.append(f'<rect x="{PAD}" y="{start - 92 - 56}" width="72" height="6" rx="3" fill="{theme.accent}"/>')

    elif template == "quote":
        body.append(
            f'<text x="{PAD - 6}" y="{PAD + 150 + top_inset}" fill="{theme.accent}" '
            f'font-family="{theme.font_serif}" font-size="240" font-weight="700" '
            f'opacity="0.85">&#8220;</text>'
        )
        q_lines = wrap_text(slide.get("quote", ""), 60, inner_w, 0.5)
        svg, bottom = _text_lines(q_lines, PAD, PAD + 320 + top_inset, size=60, fill=theme.text,
                                  weight=500, family=theme.font_serif, line_height=1.3)
        body.append(svg)
        author = slide.get("author")
        if author:
            body.append(f'<rect x="{PAD}" y="{bottom + 60}" width="56" height="5" rx="2" fill="{theme.accent}"/>')
            svg, ab = _text_lines([author], PAD, bottom + 130, size=38, fill=theme.text,
                                  weight=700, family=theme.font_sans)
            body.append(svg)
            if slide.get("role"):
                svg, _ = _text_lines([slide["role"]], PAD, ab + 46, size=30,
                                     fill=theme.muted, weight=400, family=theme.font_sans)
                body.append(svg)

    elif template == "stat":
        value = str(slide.get("value", ""))
        v_size = 220 if len(value) <= 4 else (170 if len(value) <= 7 else 120)
        cy = H / 2
        if slide.get("label"):
            svg, _ = _text_lines([slide["label"]], W / 2, cy - v_size * 0.75, size=34,
                                 fill=theme.accent, weight=700, family=theme.font_sans,
                                 anchor="middle", letter_spacing=4, uppercase=True)
            body.append(svg)
        svg, bottom = _text_lines([value], W / 2, cy + v_size * 0.32, size=v_size,
                                  fill=theme.text, weight=800, family=theme.font_sans,
                                  anchor="middle")
        body.append(svg)
        if slide.get("caption"):
            cap_lines = wrap_text(slide["caption"], 38, inner_w)
            svg, _ = _text_lines(cap_lines, W / 2, bottom + 90, size=38, fill=theme.muted,
                                 weight=400, family=theme.font_sans, anchor="middle",
                                 line_height=1.35)
            body.append(svg)

    elif template == "list":
        eb, y = _eyebrow(slide, theme, PAD + 30 + (96 if logo_data_uri else 0) + top_inset)
        body.append(eb)
        head_lines = wrap_text(slide.get("heading", ""), 64, inner_w, 0.57)
        svg, bottom = _text_lines(head_lines, PAD, y, size=64, fill=theme.text,
                                  weight=800, family=theme.font_sans, line_height=1.12)
        body.append(svg)
        items = slide.get("items", []) or []
        ordered = bool(slide.get("ordered"))
        iy = bottom + 100
        for i, item in enumerate(items):
            marker_x = PAD
            text_x = PAD + 76
            if ordered:
                body.append(
                    f'<text x="{marker_x}" y="{iy + 8}" fill="{theme.accent}" '
                    f'font-family="{theme.font_sans}" font-size="44" font-weight="800">{i + 1}</text>'
                )
            else:
                body.append(f'<circle cx="{marker_x + 12}" cy="{iy - 6}" r="11" fill="{theme.accent}"/>')
            it_lines = wrap_text(str(item), 40, inner_w - 76)
            svg, ib = _text_lines(it_lines, text_x, iy, size=40, fill=theme.text,
                                  weight=500, family=theme.font_sans, line_height=1.3)
            body.append(svg)
            iy = ib + 64

    elif template == "cta":
        cy = H / 2
        if slide.get("eyebrow"):
            svg, _ = _text_lines([slide["eyebrow"]], W / 2, cy - 200, size=30,
                                 fill=theme.accent, weight=700, family=theme.font_sans,
                                 anchor="middle", letter_spacing=4, uppercase=True)
            body.append(svg)
        head_lines = wrap_text(slide.get("heading", ""), 72, inner_w, 0.57)
        svg, bottom = _text_lines(head_lines, W / 2, cy - 80, size=72, fill=theme.text,
                                  weight=800, family=theme.font_sans, anchor="middle",
                                  line_height=1.1)
        body.append(svg)
        if slide.get("body"):
            b_lines = wrap_text(slide["body"], 38, inner_w)
            svg, bottom = _text_lines(b_lines, W / 2, bottom + 80, size=38, fill=theme.muted,
                                      weight=400, family=theme.font_sans, anchor="middle",
                                      line_height=1.35)
            body.append(svg)
        button = slide.get("button")
        if button:
            bw = max(280, int(len(button) * 22) + 96)
            bx = (W - bw) / 2
            by = bottom + 80
            body.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="96" rx="48" fill="{theme.accent}"/>')
            body.append(
                f'<text x="{W / 2}" y="{by + 62}" fill="{theme.accent_fg}" '
                f'font-family="{theme.font_sans}" font-size="38" font-weight="700" '
                f'text-anchor="middle">{esc(button)}</text>'
            )

    else:  # "content" (default)
        eb, y = _eyebrow(slide, theme, PAD + 30 + (96 if logo_data_uri else 0) + top_inset)
        body.append(eb)
        head_lines = wrap_text(slide.get("heading", ""), 64, inner_w, 0.57)
        svg, bottom = _text_lines(head_lines, PAD, y, size=64, fill=theme.text,
                                  weight=800, family=theme.font_sans, line_height=1.12)
        body.append(svg)
        img_uri = to_data_uri(slide.get("image"))
        if not img_uri and slide.get("photo"):  # real photo
            img_uri = _sourced_uri(slide["photo"], 1200, 800, providers=_PHOTO_PROVIDERS)
        if not img_uri and slide.get("image_query"):  # AI-generated
            img_uri = _sourced_uri(slide["image_query"], 1200, 800)
        if img_uri:
            # Rounded image card between heading and body.
            iy = bottom + 56
            ih = min(560, H - iy - PAD - 220)
            body.append(
                f'<clipPath id="imgclip{index}"><rect x="{PAD}" y="{iy:.0f}" '
                f'width="{inner_w}" height="{ih:.0f}" rx="28"/></clipPath>'
                f'<image x="{PAD}" y="{iy:.0f}" width="{inner_w}" height="{ih:.0f}" '
                f'preserveAspectRatio="xMidYMid slice" clip-path="url(#imgclip{index})" '
                f'href="{img_uri}"/>'
            )
            text_top = iy + ih + 64
        else:
            body.append(f'<rect x="{PAD}" y="{bottom + 44}" width="72" height="6" rx="3" fill="{theme.accent}"/>')
            text_top = bottom + 130
        if slide.get("body"):
            b_lines = wrap_text(slide["body"], 40, inner_w)
            svg, _ = _text_lines(b_lines, PAD, text_top, size=40, fill=theme.text,
                                 weight=400, family=theme.font_sans, line_height=1.42)
            body.append(svg)

    defs = _gradient_defs(theme, grad_id)
    if bg_uri:
        defs += (
            f'<linearGradient id="scrim{index}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0%" stop-color="#000000" stop-opacity="0"/>'
            f'<stop offset="100%" stop-color="#000000" stop-opacity="0.65"/>'
            f"</linearGradient>"
        )
    footer = _footer(slide, theme, W, H, index, total)
    open_tag = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
                f'viewBox="0 0 {W} {H}" font-family="{theme.font_sans}">')
    if layer == "bg":
        # Just the painted background + photo/scrim — gets a Ken-Burns zoom.
        return (f'{open_tag}<defs>{defs}</defs>'
                f'<rect width="{W}" height="{H}" fill="{_bg_fill(theme, grad_id)}"/>'
                f"{bg_layer}</svg>")
    if layer == "fg":
        # Transparent text/accent layer — animated in over the background.
        return f'{open_tag}{"".join(body)}{_logo_svg(logo_data_uri)}{footer}</svg>'
    return (
        f"{open_tag}<defs>{defs}</defs>"
        f'<rect width="{W}" height="{H}" fill="{_bg_fill(theme, grad_id)}"/>'
        f"{bg_layer}{''.join(body)}{_logo_svg(logo_data_uri)}{footer}</svg>"
    )


def render_brand_bug(theme: Theme, handle: str, logo_data_uri: str | None,
                     W: int, H: int) -> str:
    """A persistent channel watermark (logo + @handle) as a full-frame
    transparent overlay — pinned top-left, on a subtle dark pill for legibility
    over any scene."""
    items = []
    x = 56
    pill_x, pill_y, pill_h = 48, 56, 84
    cx = pill_x + 24
    has_logo = bool(logo_data_uri)
    if has_logo:
        items.append(f'<image x="{cx}" y="{pill_y + 14}" width="120" height="56" '
                     f'preserveAspectRatio="xMinYMid meet" href="{logo_data_uri}"/>')
        cx += 136
    text = handle or ""
    text_w = int(len(text) * 19) if text else 0
    if text:
        items.append(f'<text x="{cx}" y="{pill_y + 54}" fill="#ffffff" '
                     f'font-family="{theme.font_sans}" font-size="34" font-weight="700">'
                     f'{esc(text)}</text>')
    pill_w = (cx - pill_x) + text_w + 36
    pill = (f'<rect x="{pill_x}" y="{pill_y}" width="{pill_w}" height="{pill_h}" '
            f'rx="42" fill="#000000" opacity="0.32"/>')
    accent_dot = (f'<circle cx="{pill_x + pill_w - 22}" cy="{pill_y + pill_h/2:.0f}" '
                  f'r="7" fill="{theme.accent}"/>') if text else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}" font-family="{theme.font_sans}">'
            f'{pill}{"".join(items)}{accent_dot}</svg>')
