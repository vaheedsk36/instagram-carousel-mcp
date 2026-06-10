"""Brand profiles.

A brand profile bundles the things that make a carousel look like *your* page:
handle, logo, a custom colour theme, and default hashtags / caption signature.
Profiles are stored as JSON under ``brands/<name>.json`` so they persist and
sync with the repo (and therefore across devices).
"""
from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path

from .themes import Theme, custom_theme, get_theme

BRANDS_DIR = Path(__file__).parent.parent / "brands"


@dataclass
class Brand:
    name: str
    handle: str = ""                       # e.g. "@yourpage"
    logo: str = ""                         # path to a logo image (png/jpg/svg)
    theme: dict | None = None              # custom theme overrides (see themes.custom_theme)
    base_theme: str = "midnight"           # theme to fall back on / extend
    default_hashtags: list[str] = field(default_factory=list)
    caption_signature: str = ""            # appended to captions, e.g. "Follow @yourpage 🚀"
    default_size: str = "portrait"

    def resolve_theme(self, override: str | None = None) -> Theme:
        if override:
            return get_theme(override)
        if self.theme:
            return custom_theme(self.theme, self.base_theme)
        return get_theme(self.base_theme)

    def logo_data_uri(self) -> str | None:
        if not self.logo:
            return None
        p = Path(self.logo).expanduser()
        if not p.is_absolute():
            p = (BRANDS_DIR / self.logo).resolve()
        if not p.exists():
            raise ValueError(f"Brand '{self.name}' logo not found: {p}")
        mime = mimetypes.guess_type(str(p))[0] or "image/png"
        if p.suffix.lower() == ".svg":
            mime = "image/svg+xml"
        data = base64.b64encode(p.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{data}"


def save_brand(profile: dict) -> Path:
    name = (profile.get("name") or "").strip().lower()
    if not name:
        raise ValueError("Brand profile needs a 'name'.")
    BRANDS_DIR.mkdir(exist_ok=True)
    path = BRANDS_DIR / f"{name}.json"
    # Merge over an existing profile so partial updates work.
    existing = json.loads(path.read_text()) if path.exists() else {}
    existing.update({k: v for k, v in profile.items() if v is not None})
    existing["name"] = name
    path.write_text(json.dumps(existing, indent=2))
    return path


def load_brand(name: str) -> Brand:
    path = BRANDS_DIR / f"{name.strip().lower()}.json"
    if not path.exists():
        avail = ", ".join(p.stem for p in BRANDS_DIR.glob("*.json")) or "(none)"
        raise ValueError(f"No brand '{name}'. Available: {avail}")
    data = json.loads(path.read_text())
    known = Brand.__dataclass_fields__.keys()
    return Brand(**{k: v for k, v in data.items() if k in known})


def list_brands() -> list[dict]:
    if not BRANDS_DIR.exists():
        return []
    out = []
    for p in sorted(BRANDS_DIR.glob("*.json")):
        d = json.loads(p.read_text())
        out.append({
            "name": d.get("name", p.stem),
            "handle": d.get("handle", ""),
            "has_logo": bool(d.get("logo")),
            "base_theme": d.get("base_theme", "midnight"),
            "default_hashtags": len(d.get("default_hashtags", [])),
        })
    return out


def build_caption(caption: str, hashtags: list[str], brand: Brand | None,
                  extra_hashtags: list[str] | None = None) -> str:
    """Assemble the final post caption: body + signature + hashtag block.

    Brand default hashtags and per-call hashtags are merged (deduped, order
    preserved). Hashtags get a leading '#' if missing.
    """
    parts: list[str] = []
    if caption:
        parts.append(caption.strip())
    if brand and brand.caption_signature:
        parts.append(brand.caption_signature.strip())

    tags: list[str] = []
    seen = set()
    for group in (hashtags or [], extra_hashtags or [],
                  brand.default_hashtags if brand else []):
        for t in group:
            t = t.strip()
            if not t:
                continue
            if not t.startswith("#"):
                t = "#" + t.lstrip("#")
            key = t.lower()
            if key not in seen:
                seen.add(key)
                tags.append(t)
    if tags:
        parts.append(" ".join(tags))
    return "\n\n".join(parts)
