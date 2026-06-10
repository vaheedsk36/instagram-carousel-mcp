"""Visual themes for carousel slides.

A theme defines the colour palette and font stacks used when rendering an SVG
slide. Backgrounds may be a solid colour or a linear gradient. Fonts use system
stacks so the resulting SVG renders identically in a browser preview and when
rasterised to PNG, with no font embedding required.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Theme:
    name: str
    # Background gradient stops as (offset 0..1, hex colour). One stop == solid.
    bg: list[tuple[float, str]]
    bg_angle: int  # gradient direction in degrees (0 = left->right, 90 = top->bottom)
    text: str      # primary text colour
    muted: str     # secondary / supporting text colour
    accent: str    # accent colour (eyebrows, bullets, decorative marks)
    accent_fg: str # text colour that sits on top of `accent` (e.g. CTA buttons)
    font_sans: str
    font_serif: str
    description: str = ""


_SANS = "'Helvetica Neue', Helvetica, Arial, system-ui, sans-serif"
_SERIF = "Georgia, 'Times New Roman', serif"


THEMES: dict[str, Theme] = {
    "midnight": Theme(
        name="midnight",
        bg=[(0.0, "#0f172a"), (1.0, "#1e293b")],
        bg_angle=135,
        text="#f8fafc",
        muted="#94a3b8",
        accent="#38bdf8",
        accent_fg="#0f172a",
        font_sans=_SANS,
        font_serif=_SERIF,
        description="Dark navy gradient, cyan accent. Crisp and techy.",
    ),
    "sunset": Theme(
        name="sunset",
        bg=[(0.0, "#ff7e5f"), (1.0, "#feb47b")],
        bg_angle=135,
        text="#3b1f1a",
        muted="#7a4a3a",
        accent="#ffffff",
        accent_fg="#ff7e5f",
        font_sans=_SANS,
        font_serif=_SERIF,
        description="Warm orange-to-peach gradient. Friendly and bold.",
    ),
    "mono": Theme(
        name="mono",
        bg=[(0.0, "#ffffff")],
        bg_angle=90,
        text="#0a0a0a",
        muted="#737373",
        accent="#0a0a0a",
        accent_fg="#ffffff",
        font_sans=_SANS,
        font_serif=_SERIF,
        description="Clean white, black text. Minimal editorial look.",
    ),
    "forest": Theme(
        name="forest",
        bg=[(0.0, "#0b3d2e"), (1.0, "#14532d")],
        bg_angle=135,
        text="#f0fdf4",
        muted="#86efac",
        accent="#fbbf24",
        accent_fg="#0b3d2e",
        font_sans=_SANS,
        font_serif=_SERIF,
        description="Deep green with gold accent. Calm and premium.",
    ),
    "bubblegum": Theme(
        name="bubblegum",
        bg=[(0.0, "#fce7f3"), (1.0, "#fbcfe8")],
        bg_angle=135,
        text="#831843",
        muted="#be185d",
        accent="#db2777",
        accent_fg="#ffffff",
        font_sans=_SANS,
        font_serif=_SERIF,
        description="Soft pink, playful and bright.",
    ),
    "slate": Theme(
        name="slate",
        bg=[(0.0, "#f8fafc"), (1.0, "#e2e8f0")],
        bg_angle=135,
        text="#1e293b",
        muted="#64748b",
        accent="#6366f1",
        accent_fg="#ffffff",
        font_sans=_SANS,
        font_serif=_SERIF,
        description="Light grey, indigo accent. Professional and neutral.",
    ),
}


def get_theme(name: str) -> Theme:
    key = (name or "midnight").strip().lower()
    if key not in THEMES:
        raise ValueError(
            f"Unknown theme '{name}'. Available: {', '.join(sorted(THEMES))}"
        )
    return THEMES[key]


def custom_theme(spec: dict, base: str = "midnight") -> Theme:
    """Build a Theme from a partial dict, falling back to `base` for any
    missing field. Lets a brand define just its colours (e.g. accent + bg)
    without restating everything.

    `bg` may be a single hex string (solid), a list of hex strings (gradient),
    or a list of (offset, hex) pairs.
    """
    b = get_theme(base)
    bg = spec.get("bg")
    if bg is None:
        bg_stops = b.bg
    elif isinstance(bg, str):
        bg_stops = [(0.0, bg)]
    elif bg and isinstance(bg[0], str):
        n = len(bg)
        bg_stops = [(i / (n - 1) if n > 1 else 0.0, c) for i, c in enumerate(bg)]
    else:
        bg_stops = [(float(o), c) for o, c in bg]
    return Theme(
        name=spec.get("name", "custom"),
        bg=bg_stops,
        bg_angle=int(spec.get("bg_angle", b.bg_angle)),
        text=spec.get("text", b.text),
        muted=spec.get("muted", b.muted),
        accent=spec.get("accent", b.accent),
        accent_fg=spec.get("accent_fg", b.accent_fg),
        font_sans=spec.get("font_sans", b.font_sans),
        font_serif=spec.get("font_serif", b.font_serif),
        description=spec.get("description", "Custom brand theme"),
    )


def list_themes() -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "accent": t.accent,
            "background": t.bg[0][1] if len(t.bg) == 1 else f"{t.bg[0][1]} → {t.bg[-1][1]}",
        }
        for t in THEMES.values()
    ]
