# Instagram Carousel MCP

An MCP server that **designs multi-slide Instagram carousels** as crisp SVG,
shows them in a **live swipeable preview**, and exports them to **PNG** ready to
upload. Pure-Python, no system image libraries required.

## What it does

- Describe a carousel as a list of slide specs → it renders each slide to SVG.
- Six slide templates: `title`, `content`, `list`, `quote`, `stat`, `cta`.
- Six themes: `midnight`, `sunset`, `mono`, `forest`, `slate`, `bubblegum`.
- Three sizes: `portrait` (1080×1350, recommended), `square` (1080×1080),
  `story` (1080×1920).
- A live preview page (swipe / arrow keys / dots) that also rasterises each
  slide to PNG **in the browser** — no extra dependencies for export.

## Tools

| Tool | Purpose |
|------|---------|
| `list_themes` | List available themes with colours. |
| `create_carousel` | Build a carousel from slide specs; writes SVGs + preview. Returns `preview_url`. |
| `update_slide` | Replace one slide (by index) and re-render. |
| `add_slide` | Insert/append a slide. |
| `get_preview_url` | Get the live preview URL for an existing carousel. |
| `export_png` | Server-side PNG export (optional; needs Playwright). |

### Slide fields

```
title    eyebrow?, heading,  subheading?, handle?
content  eyebrow?, heading,  body
list     eyebrow?, heading,  items[] (strings), ordered? (bool)
quote    quote,    author?,  role?
stat     value,    label?,   caption?
cta      eyebrow?, heading,  body?, button?, handle?
```
Any slide also accepts `handle` (e.g. `@brand`) and `page` (bool — show `n/total`).

## Viewing the output interactively

`create_carousel` returns a `preview_url` served by the MCP server itself
(e.g. `http://127.0.0.1:<port>/<carousel-id>/`). Open it in any browser for the
full interactive carousel + **Download all PNGs** button.

**In the Claude Code desktop app**, the Preview tool reads
`~/.claude/launch.json`. The included `carousel-preview` config serves a
carousel directory over `http://127.0.0.1:8745/`. To preview a specific
carousel, point its `--directory` arg at `output/<carousel-id>` and start the
preview. (Claude can do this for you on request.)

## Exporting PNGs

- **Easiest:** click **Download all PNGs** in the live preview — rasterises in
  the browser, zero setup.
- **Headless / programmatic:** `export_png`. One-time setup:
  ```
  ./.venv/bin/python -m pip install playwright
  ./.venv/bin/python -m playwright install chromium
  ```

## Registering the server

Already registered at user scope via:
```
claude mcp add instagram-carousel --scope user -- \
  /Users/vaheedsk36/instagram-carousel-mcp/.venv/bin/python \
  /Users/vaheedsk36/instagram-carousel-mcp/server.py
```

## Project layout

```
server.py              MCP server (FastMCP) — the tools
carousel/themes.py     theme palettes + fonts
carousel/render.py     slide spec -> SVG (with text wrapping & templates)
carousel/preview.py    background HTTP preview server + viewer HTML
carousel/export.py     optional Playwright SVG->PNG
output/<id>/           generated slides, manifest, preview, spec
test_render.py         smoke test covering all templates
```

## Note on this machine

The Homebrew Python 3.14 bottle shipped with a mis-linked `pyexpat` (pointed at
the system `libexpat` which lacks a newer symbol). It was repaired by repointing
the extension at Homebrew's expat:
```
install_name_tool -change /usr/lib/libexpat.1.dylib \
  /opt/homebrew/opt/expat/lib/libexpat.1.dylib <pyexpat.so>
codesign --force -s - <pyexpat.so>
```
A future `brew upgrade python@3.14` may revert this; re-run if `import
xml.parsers.expat` fails again.
