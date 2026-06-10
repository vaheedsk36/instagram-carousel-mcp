"""Optional server-side SVG -> PNG export.

The primary export path is client-side (the preview page rasterises each slide
via canvas — no extra dependencies). This module provides a *programmatic*
fallback using Playwright's headless Chromium, useful for automated pipelines.

It is intentionally lazy: Playwright is only imported when ``export_png`` is
called, so the MCP server runs fine without it. If Playwright is missing, a
clear setup hint is raised.
"""
from __future__ import annotations

from pathlib import Path

_SETUP_HINT = (
    "Server-side PNG export needs Playwright. Install it once with:\n"
    "  ./.venv/bin/python -m pip install playwright\n"
    "  ./.venv/bin/python -m playwright install chromium\n"
    "Or just use the 'Download all PNGs' button in the live preview — that "
    "rasterises in-browser with no extra setup."
)


def export_png(carousel_dir: Path, width: int, height: int) -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(_SETUP_HINT) from e

    svgs = sorted(carousel_dir.glob("slide-*.svg"), key=lambda p: int(p.stem.split("-")[1]))
    out: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height},
                                device_scale_factor=1)
        for svg in svgs:
            png = svg.with_suffix(".png")
            page.goto(svg.resolve().as_uri())
            page.screenshot(path=str(png), clip={"x": 0, "y": 0, "width": width, "height": height})
            out.append(str(png))
        browser.close()
    return out
