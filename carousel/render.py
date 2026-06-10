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

Common optional fields on every slide: ``page`` (bool, show "n / total"),
``handle`` (e.g. "@yourbrand"). Sizes are chosen for a 1080px-wide canvas and
scale with the canvas height.
"""
from __future__ import annotations

from .themes import Theme

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
                 logo_data_uri: str | None = None) -> str:
    template = (slide.get("template") or "content").lower()
    grad_id = f"bg{index}"
    inner_w = W - 2 * PAD
    body: list[str] = []

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
            f'<text x="{PAD - 6}" y="{PAD + 150}" fill="{theme.accent}" '
            f'font-family="{theme.font_serif}" font-size="240" font-weight="700" '
            f'opacity="0.85">&#8220;</text>'
        )
        q_lines = wrap_text(slide.get("quote", ""), 60, inner_w, 0.5)
        svg, bottom = _text_lines(q_lines, PAD, PAD + 320, size=60, fill=theme.text,
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
        eb, y = _eyebrow(slide, theme, PAD + 30 + (96 if logo_data_uri else 0))
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
        eb, y = _eyebrow(slide, theme, PAD + 30 + (96 if logo_data_uri else 0))
        body.append(eb)
        head_lines = wrap_text(slide.get("heading", ""), 64, inner_w, 0.57)
        svg, bottom = _text_lines(head_lines, PAD, y, size=64, fill=theme.text,
                                  weight=800, family=theme.font_sans, line_height=1.12)
        body.append(svg)
        body.append(f'<rect x="{PAD}" y="{bottom + 44}" width="72" height="6" rx="3" fill="{theme.accent}"/>')
        if slide.get("body"):
            b_lines = wrap_text(slide["body"], 40, inner_w)
            svg, _ = _text_lines(b_lines, PAD, bottom + 130, size=40, fill=theme.text,
                                 weight=400, family=theme.font_sans, line_height=1.42)
            body.append(svg)

    defs = _gradient_defs(theme, grad_id)
    footer = _footer(slide, theme, W, H, index, total)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="{theme.font_sans}">'
        f"<defs>{defs}</defs>"
        f'<rect width="{W}" height="{H}" fill="{_bg_fill(theme, grad_id)}"/>'
        f"{''.join(body)}{_logo_svg(logo_data_uri)}{footer}</svg>"
    )
