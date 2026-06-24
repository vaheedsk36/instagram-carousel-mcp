"""AI video clip generation (Seedance on Replicate) for reel scene backgrounds.

Used by the `video_query` scene field. Needs a Replicate token (env
REPLICATE_API_TOKEN or a .replicate_token file). Clips are cached by
(prompt, size, duration) so re-renders don't re-bill.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.request

from . import images  # reuse token lookup, CACHE, aspect-ratio helper

MODEL = "bytedance/seedance-1-lite"  # cheap text-to-video, 5s/10s, 480p/720p


def get_video_clip(prompt: str, duration: float = 5, w: int = 1080, h: int = 1920):
    """Generate (or reuse cached) a Seedance clip for `prompt`. Returns a Path
    to an mp4. Raises if no Replicate token or generation fails."""
    token = images.replicate_token()
    if not token:
        raise RuntimeError(
            "video_query needs a Replicate token — put it in .replicate_token "
            "(or set REPLICATE_API_TOKEN). Or use background_query/background_photo instead."
        )
    images.CACHE.mkdir(parents=True, exist_ok=True)
    dur = 5 if duration <= 5 else 10
    aspect = images._aspect_ratio(w, h)
    key = hashlib.sha1(f"video:{prompt}|{aspect}|{dur}".encode()).hexdigest()[:16]
    cached = images.CACHE / f"{key}.mp4"
    if cached.exists():
        return cached

    hdr = {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
           "User-Agent": "carousel/1.0"}
    payload = {"input": {"prompt": prompt, "duration": dur, "resolution": "720p",
                         "aspect_ratio": aspect, "camera_fixed": False}}
    url = f"https://api.replicate.com/v1/models/{MODEL}/predictions"

    pred = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                         headers={**hdr, "Prefer": "wait"})
            with urllib.request.urlopen(req, timeout=300) as r:
                pred = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 4:
                time.sleep(8)
                continue
            raise
    get_url = (pred.get("urls") or {}).get("get")
    for _ in range(90):
        st = pred.get("status")
        if st == "succeeded":
            break
        if st in ("failed", "canceled"):
            raise RuntimeError(f"Seedance {st}: {pred.get('error')}")
        time.sleep(4)
        with urllib.request.urlopen(urllib.request.Request(get_url, headers=hdr), timeout=30) as r:
            pred = json.loads(r.read())
    out = pred.get("output")
    vurl = out[0] if isinstance(out, list) and out else (out if isinstance(out, str) else None)
    if not vurl:
        raise RuntimeError("Seedance returned no output")
    with urllib.request.urlopen(
            urllib.request.Request(vurl, headers={"User-Agent": "carousel/1.0"}), timeout=180) as r:
        cached.write_bytes(r.read())
    print(f"[videos] seedance clip for {prompt[:60]!r}", file=sys.stderr)
    return cached
