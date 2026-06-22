"""Automatic image sourcing.

Given a short text query/prompt, returns a local image file (cached) to embed
in a slide. Providers are tried in order; the first that yields an image wins:

  1. Replicate (AI-generated, Flux)  — needs REPLICATE_API_TOKEN / .replicate_token
  2. Pexels (real stock photos)      — needs PEXELS_API_KEY / .pexels_key
  3. Openverse (CC real photos)      — free, no key, topic-relevant
  4. Picsum (random photo)           — free, no key, guaranteed last resort

So with a Replicate token you get custom AI art; with nothing configured it
still works (real CC photos). Override the order with the env var
``IMAGE_PROVIDER_ORDER`` (comma list of: replicate,pexels,openverse,picsum).

Results cache under ``assets/cache/`` keyed by (query, size) so re-renders and
``update_slide`` calls don't re-fetch or re-bill.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).parent.parent
CACHE = _ROOT / "assets" / "cache"
_UA = {"User-Agent": "carousel/1.0 (+https://github.com/vaheedsk36/instagram-carousel-mcp)"}
_EXT = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp"}


# ---- credentials -----------------------------------------------------------

def _cred(env: str, file: str) -> str | None:
    v = os.environ.get(env)
    if v and v.strip():
        return v.strip()
    f = _ROOT / file
    if f.exists():
        return f.read_text().strip() or None
    return None


def replicate_token() -> str | None:
    return _cred("REPLICATE_API_TOKEN", ".replicate_token")


def pexels_key() -> str | None:
    return _cred("PEXELS_API_KEY", ".pexels_key")


# ---- http helpers ----------------------------------------------------------

def _get(url: str, headers: dict | None = None, timeout: int = 60) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={**_UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), (r.headers.get_content_type() or "image/jpeg")


def _post_json(url: str, payload: dict, headers: dict, timeout: int = 90) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={**_UA, "Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _aspect_ratio(w: int, h: int) -> str:
    table = {(4, 5): "4:5", (1, 1): "1:1", (9, 16): "9:16", (3, 2): "3:2", (2, 3): "2:3"}
    best, ratio = "1:1", w / h
    diff = 1e9
    for (a, b), label in table.items():
        d = abs(ratio - a / b)
        if d < diff:
            diff, best = d, label
    return best


# ---- providers -------------------------------------------------------------

_last_replicate_call = [0.0]  # module-level throttle state
_MIN_REPLICATE_GAP = 4.0      # seconds between create calls to avoid 429s


def _from_replicate(query: str, w: int, h: int) -> tuple[bytes, str] | None:
    token = replicate_token()
    if not token:
        return None
    # Throttle: space out create calls to stay under Replicate's rate limit.
    gap = _MIN_REPLICATE_GAP - (time.time() - _last_replicate_call[0])
    if gap > 0:
        time.sleep(gap)
    _last_replicate_call[0] = time.time()
    hdr = {"Authorization": f"Bearer {token}", "Prefer": "wait"}
    payload = {"input": {
        "prompt": query,
        "aspect_ratio": _aspect_ratio(w, h),
        "output_format": "jpg",
        "num_outputs": 1,
        "go_fast": True,
    }}
    url = "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions"
    pred = None
    for attempt in range(5):
        try:
            pred = _post_json(url, payload, hdr, timeout=90)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 4:
                retry_after = e.headers.get("Retry-After")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else 4 * (attempt + 1)
                print(f"[images] replicate 429, retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    if pred is None:
        return None
    # With Prefer: wait the prediction usually completes; poll briefly otherwise.
    get_url = (pred.get("urls") or {}).get("get")
    for _ in range(20):
        status = pred.get("status")
        if status == "succeeded":
            break
        if status in ("failed", "canceled"):
            raise RuntimeError(f"Replicate {status}: {pred.get('error')}")
        time.sleep(1.5)
        if not get_url:
            break
        body, _ct = _get(get_url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        pred = json.loads(body)
    out = pred.get("output")
    img_url = out[0] if isinstance(out, list) and out else (out if isinstance(out, str) else None)
    if not img_url:
        return None
    return _get(img_url, timeout=40)


def _from_pexels(query: str, w: int, h: int) -> tuple[bytes, str] | None:
    key = pexels_key()
    if not key:
        return None
    orient = "portrait" if h >= w else "landscape"
    api = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode(
        {"query": query, "orientation": orient, "per_page": 1})
    data, _ = _get(api, headers={"Authorization": key}, timeout=20)
    photos = (json.loads(data).get("photos") or [])
    if not photos:
        return None
    src = photos[0]["src"]
    return _get(src.get("large2x") or src.get("large") or src.get("original"), timeout=40)


def _from_openverse(query: str, w: int, h: int) -> tuple[bytes, str] | None:
    aspect = "tall" if h > w else ("wide" if w > h else "square")
    api = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(
        {"q": query, "page_size": 6, "aspect_ratio": aspect, "license_type": "all"})
    data, _ = _get(api, timeout=25)
    for item in (json.loads(data).get("results") or []):
        url = item.get("url")
        if not url:
            continue
        try:
            return _get(url, timeout=30)
        except Exception:
            continue  # try the next result
    return None


def _from_picsum(query: str, w: int, h: int) -> tuple[bytes, str]:
    # Deterministic random photo (not topic-relevant) — last-resort guarantee.
    seed = hashlib.md5(query.encode()).hexdigest()[:10]
    return _get(f"https://picsum.photos/seed/{seed}/{w}/{h}", timeout=25)


_PROVIDERS = {
    "replicate": _from_replicate,
    "pexels": _from_pexels,
    "openverse": _from_openverse,
    "picsum": _from_picsum,
}
_DEFAULT_ORDER = ["replicate", "pexels", "openverse", "picsum"]


def get_image_path(query: str, w: int, h: int) -> Path:
    """Return a cached local image file for `query` at roughly w×h.

    Tries providers in order; Picsum guarantees a result so this rarely raises.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha1(f"{query}|{w}x{h}".encode()).hexdigest()[:16]
    for ext in ("jpg", "png", "jpeg", "webp"):
        cached = CACHE / f"{cache_key}.{ext}"
        if cached.exists():
            return cached

    order = os.environ.get("IMAGE_PROVIDER_ORDER")
    names = [n.strip() for n in order.split(",")] if order else _DEFAULT_ORDER
    for name in names:
        prov = _PROVIDERS.get(name)
        if not prov:
            continue
        try:
            result = prov(query, w, h)
        except Exception as e:
            print(f"[images] {name} failed for {query!r}: {e}", file=sys.stderr)
            continue
        if result:
            img, mime = result
            path = CACHE / f"{cache_key}.{_EXT.get(mime, 'jpg')}"
            path.write_bytes(img)
            print(f"[images] sourced via {name}: {query!r}", file=sys.stderr)
            return path
    raise RuntimeError(f"All image providers failed for {query!r}")
