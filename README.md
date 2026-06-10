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
| `create_carousel` | Build a carousel from slide specs; writes SVGs + preview. Accepts `brand`, `caption`, `hashtags`. Returns `preview_url`. |
| `update_slide` | Replace one slide (by index) and re-render. |
| `add_slide` | Insert/append a slide. |
| `save_brand` | Create/update a brand profile (handle, logo, custom theme, default hashtags). |
| `list_brands` | List saved brand profiles. |
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

### Images

Slides aren't text-only — you can add photos:

- **`background_image`** (any slide): a full-bleed photo behind the content. Text
  automatically switches to light and a gradient scrim is added so it stays
  readable on top of the image.
- **`image`** (on the `content` template): an inline rounded image card shown
  between the heading and the body text.

You don't have to supply files at all — use **`background_query`** / **`image_query`**
with a text description and the server auto-sources a fitting image, trying in
order: **Replicate/Flux** (AI, needs `REPLICATE_API_TOKEN`) → **Pexels** (stock,
needs `PEXELS_API_KEY`) → **Openverse** (free CC photos, no key) → **Picsum**
(random, guaranteed). Results cache under `assets/cache/`. Override the order
with `IMAGE_PROVIDER_ORDER`. So image-sourcing works with zero setup (real
photos) and upgrades to custom AI art once a Replicate token is present.

```jsonc
{ "template": "title", "heading": "The State of Remote Work",
  "background_query": "minimal home office, soft morning light" }
{ "template": "content", "heading": "Hybrid is winning",
  "image_query": "team collaborating in a bright office",
  "body": "58% of teams now run hybrid." }
```

Or supply images explicitly: `background_image` / `image` values can be a
**local file path**, an **http(s) URL** (downloaded), or a **data URI** — all
base64-embedded so exported PNGs are self-contained. Drop files in `assets/`:

```jsonc
{ "template": "title", "heading": "2026 Report",
  "background_image": "assets/cover.jpg" }
{ "template": "content", "heading": "Hybrid is winning",
  "image": "https://example.com/chart.png",
  "body": "58% of teams now run hybrid — up from 41% last year." }
```

## Brand your page (theme + logo)

Save a brand profile once, then pass `brand: "<name>"` to `create_carousel` and
every slide gets your colours, logo, @handle, and default hashtags.

```jsonc
// save_brand({ profile: { ... } })  -> brands/mypage.json
{
  "name": "mypage",
  "handle": "@mypage",
  "logo": "mypage-logo.png",          // path; absolute, or relative to brands/
  "base_theme": "midnight",           // theme to extend
  "theme": {                          // override only what you want
    "accent": "#f472b6",
    "bg": ["#1e1b4b", "#312e81"]      // "#hex" solid, or ["#a","#b"] gradient
  },
  "default_hashtags": ["#buildinpublic", "#startup"],
  "caption_signature": "Follow @mypage 🚀",
  "default_size": "portrait"
}
```

- **Logo:** any PNG/JPG/SVG. It's base64-embedded into each slide (top-left), so
  exported PNGs are fully self-contained. Drop your logo in `brands/` (or give an
  absolute path) and set `logo` to it.
- **Theme:** start from a built-in `base_theme` and override any of `accent`,
  `bg`, `bg_angle`, `text`, `muted`, `accent_fg`, `font_sans`, `font_serif`.
- Profiles are JSON in `brands/`, so they commit to the repo and sync across
  devices.

## Captions & hashtags

`create_carousel` (and a follow-up) take `caption` and `hashtags`. The final
post text is assembled as **caption → brand signature → merged hashtags**
(per-call + brand defaults, deduped), written to `caption.txt`, and shown in the
live preview with a **Copy** button — paste straight into Instagram.

```
create_carousel(
  slides=[...],
  brand="mypage",
  caption="Speed compounds. Here are 5 moves that cut our cycle time in half.",
  hashtags=["#shipfast", "#engineering"],
)
```

## Viewing the output interactively

`create_carousel` returns a `preview_url` served by the MCP server itself
(e.g. `http://127.0.0.1:<port>/<carousel-id>/`). Open it in any browser for the
full interactive carousel + **Download all (ZIP)** button.

**In the Claude Code desktop app**, the Preview tool reads
`~/.claude/launch.json`. The included `carousel-preview` config serves a
carousel directory over `http://127.0.0.1:8745/`. To preview a specific
carousel, point its `--directory` arg at `output/<carousel-id>` and start the
preview. (Claude can do this for you on request.)

## Exporting PNGs

- **Easiest:** click **Download all (ZIP)** in the live preview — rasterises all
  slides in the browser and bundles them into one ZIP (a single download, so the
  browser's multi-download block never trips). Zero setup. "Download this slide
  (PNG)" grabs just the current one.
- **Headless / programmatic:** `export_png`. One-time setup:
  ```
  ./.venv/bin/python -m pip install playwright
  ./.venv/bin/python -m playwright install chromium
  ```

## Run it on another device

Prerequisites: **Python 3.10+** and the **`claude`** CLI on PATH.

```bash
git clone https://github.com/vaheedsk36/instagram-carousel-mcp.git
cd instagram-carousel-mcp
./setup.sh           # creates .venv, installs deps, registers the MCP server
```

`setup.sh` registers the server at user scope so it's available in every Claude
Code session on that machine. Verify with `claude mcp list | grep carousel`.
Your brand profiles travel with the repo (they live in `brands/`), so the same
look is available everywhere.

Manual equivalent if you'd rather not run the script:
```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
claude mcp add instagram-carousel --scope user -- \
  "$(pwd)/.venv/bin/python" "$(pwd)/server.py"
```

> Note: the `.venv` is machine-specific and git-ignored — always recreate it per
> device. Only the source and `brands/` profiles are committed.

## Project layout

```
server.py              MCP server (FastMCP) — the tools
carousel/themes.py     theme palettes + custom-theme builder
carousel/brand.py      brand profiles (handle, logo, theme, hashtags) + caption assembly
carousel/render.py     slide spec -> SVG (text wrapping, templates, logo embedding)
carousel/preview.py    background HTTP preview server + viewer HTML (caption + copy)
carousel/export.py     optional Playwright SVG->PNG
brands/                saved brand profiles (committed; sync across devices)
output/<id>/           generated slides, manifest, preview, caption.txt, spec
setup.sh               one-shot setup for a fresh machine
requirements.txt       Python dependencies
test_render.py         smoke test covering all templates
test_brand.py          smoke test for brand + logo + caption
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
