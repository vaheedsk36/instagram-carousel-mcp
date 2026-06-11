"""Trending-topic discovery via Google News RSS (no API key required).

Given a subject, returns recent headlines (title, source, date, link) so a
carousel can be built around a timely, real story rather than guessed content.
"""
from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

_UA = {"User-Agent": "Mozilla/5.0 (carousel/1.0)"}


def trending(query: str, limit: int = 10, days: int = 7) -> list[dict]:
    """Recent news items for `query`. `days` limits recency (0 = no limit)."""
    q = f"{query} when:{days}d" if days else query
    url = ("https://news.google.com/rss/search?"
           + urllib.parse.urlencode({"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"}))
    req = urllib.request.Request(url, headers=_UA)
    data = urllib.request.urlopen(req, timeout=20).read()
    root = ET.fromstring(data)

    items: list[dict] = []
    for it in root.findall(".//item")[:limit]:
        title = (it.findtext("title", "") or "").strip()
        src_el = it.find("{*}source")
        source = (src_el.text or "").strip() if src_el is not None else ""
        # Google appends " - Source" to titles; drop it for a clean headline.
        if source and title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)].strip()
        items.append({
            "title": title,
            "source": source,
            "published": (it.findtext("pubDate", "") or "")[:16],
            "link": it.findtext("link", "") or "",
        })
    return items
