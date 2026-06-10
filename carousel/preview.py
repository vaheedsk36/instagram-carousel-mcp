"""Live preview server.

Serves the carousel output directory over HTTP on a background daemon thread so
the slides can be viewed (and exported to PNG client-side) in a browser — e.g.
via the Claude desktop Preview tool. The server lives as long as the MCP server
process. The generated ``index.html`` is a swipeable carousel viewer with
keyboard / touch / button navigation and per-slide PNG download.
"""
from __future__ import annotations

import json
import socket
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args, **kwargs):  # silence stdout (would corrupt stdio MCP)
        pass


class PreviewServer:
    """Singleton-ish HTTP server bound to one root directory."""

    _instance: "PreviewServer | None" = None

    def __init__(self, root: Path):
        self.root = root
        self.httpd: ThreadingHTTPServer | None = None
        self.port: int | None = None
        self.thread: threading.Thread | None = None

    @classmethod
    def ensure(cls, root: Path) -> "PreviewServer":
        if cls._instance is None:
            cls._instance = PreviewServer(root)
            cls._instance.start()
        return cls._instance

    def _free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def start(self) -> None:
        if self.httpd is not None:
            return
        self.port = self._free_port()
        handler = partial(_QuietHandler, directory=str(self.root))
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def url_for(self, carousel_id: str) -> str:
        return f"http://127.0.0.1:{self.port}/{carousel_id}/"


def write_manifest(carousel_dir: Path, title: str, size: str, dims: tuple[int, int], slides: list[dict]) -> None:
    manifest = {
        "title": title,
        "size": size,
        "width": dims[0],
        "height": dims[1],
        "count": len(slides),
        "slides": [f"slide-{i}.svg" for i in range(len(slides))],
        "specs": slides,
    }
    (carousel_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


def write_index(carousel_dir: Path) -> None:
    (carousel_dir / "index.html").write_text(_INDEX_HTML)


_INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Carousel preview</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: flex; flex-direction: column;
    align-items: center; gap: 18px; padding: 28px 16px 40px;
    background: #0b0d12; color: #e5e7eb;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  }
  h1 { font-size: 16px; font-weight: 600; color: #cbd5e1; margin: 0; }
  .meta { font-size: 13px; color: #64748b; margin: -10px 0 4px; }
  .stage {
    position: relative; display: flex; align-items: center; gap: 14px;
  }
  .frame {
    position: relative; overflow: hidden; border-radius: 18px;
    box-shadow: 0 20px 60px rgba(0,0,0,.5); background: #111;
    /* height drives size; width follows aspect ratio set by JS */
    height: min(72vh, 760px);
  }
  .track { display: flex; width: 100%; height: 100%; transition: transform .35s cubic-bezier(.4,0,.2,1); }
  .slide { flex: 0 0 100%; height: 100%; display: grid; place-items: center; }
  .slide img { height: 100%; width: 100%; object-fit: contain; display: block; user-select: none; -webkit-user-drag: none; }
  .nav {
    border: none; cursor: pointer; width: 46px; height: 46px; border-radius: 50%;
    background: #1e293b; color: #e5e7eb; font-size: 20px; line-height: 1;
    display: grid; place-items: center; transition: background .15s;
  }
  .nav:hover { background: #334155; }
  .nav:disabled { opacity: .3; cursor: default; }
  .dots { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; max-width: 80vw; }
  .dot { width: 9px; height: 9px; border-radius: 50%; background: #334155; border: none; cursor: pointer; padding: 0; }
  .dot.active { background: #38bdf8; width: 22px; border-radius: 5px; }
  .bar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; justify-content: center; }
  .btn {
    background: #1e293b; color: #e5e7eb; border: 1px solid #334155; border-radius: 10px;
    padding: 9px 16px; font-size: 13px; cursor: pointer; font-weight: 600;
  }
  .btn:hover { background: #334155; }
  .btn.primary { background: #38bdf8; color: #0b0d12; border-color: #38bdf8; }
  .counter { font-variant-numeric: tabular-nums; color: #94a3b8; font-size: 13px; min-width: 54px; text-align: center; }
</style>
</head>
<body>
  <h1 id="title">Carousel</h1>
  <div class="meta" id="meta"></div>
  <div class="stage">
    <button class="nav" id="prev" aria-label="Previous">‹</button>
    <div class="frame" id="frame"><div class="track" id="track"></div></div>
    <button class="nav" id="next" aria-label="Next">›</button>
  </div>
  <div class="dots" id="dots"></div>
  <div class="bar">
    <span class="counter" id="counter">1 / 1</span>
    <button class="btn" id="dlOne">Download this slide (PNG)</button>
    <button class="btn primary" id="dlAll">Download all PNGs</button>
  </div>

<script>
let M, idx = 0;

async function load() {
  M = await (await fetch('manifest.json?_=' + Date.now())).json();
  document.getElementById('title').textContent = M.title || 'Carousel';
  document.getElementById('meta').textContent =
    `${M.count} slides · ${M.width}×${M.height} · ${M.size}`;
  const ratio = M.width / M.height;
  document.querySelector('.frame').style.width = `calc(min(72vh, 760px) * ${ratio})`;

  const track = document.getElementById('track');
  const dots = document.getElementById('dots');
  track.innerHTML = ''; dots.innerHTML = '';
  M.slides.forEach((src, i) => {
    const slide = document.createElement('div');
    slide.className = 'slide';
    const img = document.createElement('img');
    img.src = src + '?_=' + Date.now();
    img.draggable = false;
    slide.appendChild(img);
    track.appendChild(slide);
    const d = document.createElement('button');
    d.className = 'dot' + (i === 0 ? ' active' : '');
    d.onclick = () => go(i);
    dots.appendChild(d);
  });
  go(Math.min(idx, M.count - 1));
}

function go(i) {
  idx = Math.max(0, Math.min(M.count - 1, i));
  document.getElementById('track').style.transform = `translateX(-${idx * 100}%)`;
  [...document.getElementById('dots').children].forEach((d, j) =>
    d.classList.toggle('active', j === idx));
  document.getElementById('counter').textContent = `${idx + 1} / ${M.count}`;
  document.getElementById('prev').disabled = idx === 0;
  document.getElementById('next').disabled = idx === M.count - 1;
}

document.getElementById('prev').onclick = () => go(idx - 1);
document.getElementById('next').onclick = () => go(idx + 1);
addEventListener('keydown', e => {
  if (e.key === 'ArrowLeft') go(idx - 1);
  if (e.key === 'ArrowRight') go(idx + 1);
});

// touch / drag swipe
let sx = null;
const frame = document.getElementById('frame');
const start = x => sx = x;
const end = x => { if (sx === null) return; const dx = x - sx; if (Math.abs(dx) > 40) go(idx + (dx < 0 ? 1 : -1)); sx = null; };
frame.addEventListener('touchstart', e => start(e.touches[0].clientX), {passive: true});
frame.addEventListener('touchend', e => end(e.changedTouches[0].clientX));
frame.addEventListener('mousedown', e => start(e.clientX));
addEventListener('mouseup', e => end(e.clientX));

async function svgToPng(src, w, h) {
  const svgText = await (await fetch(src)).text();
  const blob = new Blob([svgText], {type: 'image/svg+xml'});
  const url = URL.createObjectURL(blob);
  const img = new Image();
  await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = url; });
  const canvas = document.createElement('canvas');
  canvas.width = w; canvas.height = h;
  canvas.getContext('2d').drawImage(img, 0, 0, w, h);
  URL.revokeObjectURL(url);
  return await new Promise(res => canvas.toBlob(res, 'image/png'));
}

function download(blob, name) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

document.getElementById('dlOne').onclick = async () => {
  const blob = await svgToPng(M.slides[idx], M.width, M.height);
  download(blob, `slide-${idx + 1}.png`);
};
document.getElementById('dlAll').onclick = async () => {
  for (let i = 0; i < M.count; i++) {
    const blob = await svgToPng(M.slides[i], M.width, M.height);
    download(blob, `slide-${i + 1}.png`);
    await new Promise(r => setTimeout(r, 300));
  }
};

load();
</script>
</body>
</html>
"""
