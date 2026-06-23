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


def write_manifest(carousel_dir: Path, title: str, size: str, dims: tuple[int, int],
                   slides: list[dict], caption: str = "") -> None:
    manifest = {
        "title": title,
        "size": size,
        "width": dims[0],
        "height": dims[1],
        "count": len(slides),
        "slides": [f"slide-{i}.svg" for i in range(len(slides))],
        "specs": slides,
        "caption": caption,
    }
    (carousel_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


def write_index(carousel_dir: Path) -> None:
    (carousel_dir / "index.html").write_text(_INDEX_HTML)


def write_reel_index(reel_dir: Path, title: str, caption: str,
                     duration: float, video: str = "reel.mp4",
                     music: list[str] | None = None) -> None:
    music_html = ""
    if music:
        items = "".join(f"<li>{_esc(m)}</li>" for m in music)
        music_html = (f'<div class="music"><div class="caption-head"><span>🎵 Music ideas</span></div>'
                      f'<ul>{items}</ul></div>')
    html = _REEL_HTML.replace("__TITLE__", _esc(title)) \
                     .replace("__VIDEO__", video) \
                     .replace("__DURATION__", f"{duration:g}") \
                     .replace("__MUSIC__", music_html) \
                     .replace("__CAPTION__", _esc(caption))
    (reel_dir / "index.html").write_text(html)


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


_REEL_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>__TITLE__ — Reel</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; min-height:100vh; display:flex; flex-direction:column; align-items:center;
    gap:16px; padding:28px 16px 40px; background:#0b0d12; color:#e5e7eb;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif; }
  h1 { font-size:16px; font-weight:600; color:#cbd5e1; margin:0; }
  .meta { font-size:13px; color:#64748b; margin:-8px 0 4px; }
  video { height:min(78vh,860px); width:auto; border-radius:18px; background:#000;
    box-shadow:0 20px 60px rgba(0,0,0,.5); }
  .bar { display:flex; gap:10px; flex-wrap:wrap; justify-content:center; }
  .btn { background:#1e293b; color:#e5e7eb; border:1px solid #334155; border-radius:10px;
    padding:9px 16px; font-size:13px; cursor:pointer; font-weight:600; text-decoration:none; }
  .btn:hover { background:#334155; }
  .btn.primary { background:#38bdf8; color:#0b0d12; border-color:#38bdf8; }
  .caption { width:min(92vw,560px); background:#11151c; border:1px solid #1f2937;
    border-radius:14px; padding:16px 18px; }
  .caption-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }
  .caption-head span { font-size:12px; text-transform:uppercase; letter-spacing:1px; color:#64748b; font-weight:700; }
  .caption pre { margin:0; white-space:pre-wrap; word-break:break-word; font:inherit; font-size:14px; line-height:1.5; color:#cbd5e1; }
  .caption.empty { display:none; }
  .music { width:min(92vw,560px); background:#11151c; border:1px solid #1f2937; border-radius:14px; padding:12px 18px; }
  .music ul { margin:6px 0 2px; padding-left:18px; }
  .music li { font-size:14px; line-height:1.6; color:#cbd5e1; }
</style></head><body>
  <h1>__TITLE__</h1>
  <div class="meta">Reel · 1080×1920 · __DURATION__s</div>
  <video id="reelVideo" controls autoplay loop muted playsinline></video>
  <div class="bar">
    <a class="btn primary" href="__VIDEO__" download>Download MP4</a>
    <button class="btn" id="copyCap">Copy caption</button>
  </div>
  <div class="caption" id="caption">
    <div class="caption-head"><span>Caption</span></div>
    <pre id="captionText">__CAPTION__</pre>
  </div>
  __MUSIC__
<script>
  // Cache-bust the video so a regenerated reel.mp4 isn't served from cache.
  (() => { const v=document.getElementById('reelVideo'); v.src='__VIDEO__?t='+Date.now(); })();
  if (!document.getElementById('captionText').textContent.trim()) document.getElementById('caption').classList.add('empty');
  document.getElementById('copyCap').onclick = async () => {
    const t = document.getElementById('captionText').textContent, b = document.getElementById('copyCap');
    let ok=false;
    try { if (navigator.clipboard && window.isSecureContext){ await navigator.clipboard.writeText(t); ok=true; } } catch(e){}
    if (!ok) { try { const ta=document.createElement('textarea'); ta.value=t; ta.style.cssText='position:fixed;opacity:0'; document.body.appendChild(ta); ta.select(); ok=document.execCommand('copy'); ta.remove(); } catch(e){} }
    if (!ok) { const r=document.createRange(); r.selectNodeContents(document.getElementById('captionText')); const s=getSelection(); s.removeAllRanges(); s.addRange(r); }
    b.textContent = ok ? 'Copied ✓' : 'Selected — ⌘C'; setTimeout(()=>b.textContent='Copy caption',2000);
  };
</script>
</body></html>
"""


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
  .caption {
    width: min(92vw, 560px); background: #11151c; border: 1px solid #1f2937;
    border-radius: 14px; padding: 16px 18px; margin-top: 6px;
  }
  .caption-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
  .caption-head span { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: #64748b; font-weight: 700; }
  .caption pre { margin: 0; white-space: pre-wrap; word-break: break-word; font: inherit; font-size: 14px; line-height: 1.5; color: #cbd5e1; }
  .caption.empty { display: none; }
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
    <button class="btn primary" id="dlAll">Download all (ZIP)</button>
  </div>
  <div class="caption empty" id="caption">
    <div class="caption-head"><span>Caption</span><button class="btn" id="copyCap">Copy</button></div>
    <pre id="captionText"></pre>
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

  const cap = document.getElementById('caption');
  if (M.caption && M.caption.trim()) {
    document.getElementById('captionText').textContent = M.caption;
    cap.classList.remove('empty');
  } else {
    cap.classList.add('empty');
  }

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
// CRC32 + a minimal store-only ZIP so all slides come down as one file
// (browsers block multiple sequential downloads from a single click).
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1); t[n] = c >>> 0; }
  return t;
})();
function crc32(u8) { let c = 0xFFFFFFFF; for (let i = 0; i < u8.length; i++) c = CRC_TABLE[(c ^ u8[i]) & 0xFF] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; }

function makeZip(files) {
  const enc = new TextEncoder(), chunks = [], central = []; let offset = 0;
  for (const f of files) {
    const name = enc.encode(f.name), crc = crc32(f.data), n = f.data.length;
    const lh = new Uint8Array(30 + name.length), dv = new DataView(lh.buffer);
    dv.setUint32(0, 0x04034b50, true); dv.setUint16(4, 20, true); dv.setUint16(6, 0, true);
    dv.setUint16(8, 0, true); dv.setUint16(10, 0, true); dv.setUint16(12, 0, true);
    dv.setUint32(14, crc, true); dv.setUint32(18, n, true); dv.setUint32(22, n, true);
    dv.setUint16(26, name.length, true); dv.setUint16(28, 0, true); lh.set(name, 30);
    chunks.push(lh, f.data);
    const ch = new Uint8Array(46 + name.length), cv = new DataView(ch.buffer);
    cv.setUint32(0, 0x02014b50, true); cv.setUint16(4, 20, true); cv.setUint16(6, 20, true);
    cv.setUint16(8, 0, true); cv.setUint16(10, 0, true); cv.setUint16(12, 0, true); cv.setUint16(14, 0, true);
    cv.setUint32(16, crc, true); cv.setUint32(20, n, true); cv.setUint32(24, n, true);
    cv.setUint16(28, name.length, true); cv.setUint32(42, offset, true); ch.set(name, 46);
    central.push(ch); offset += lh.length + n;
  }
  let cdSize = 0; for (const c of central) cdSize += c.length;
  const end = new Uint8Array(22), ev = new DataView(end.buffer);
  ev.setUint32(0, 0x06054b50, true); ev.setUint16(8, files.length, true); ev.setUint16(10, files.length, true);
  ev.setUint32(12, cdSize, true); ev.setUint32(16, offset, true);
  return new Blob([...chunks, ...central, end], { type: 'application/zip' });
}

document.getElementById('dlAll').onclick = async () => {
  const btn = document.getElementById('dlAll'), label = btn.textContent;
  btn.disabled = true;
  const slug = (M.title || 'carousel').replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').toLowerCase() || 'carousel';
  try {
    const files = [];
    for (let i = 0; i < M.count; i++) {
      btn.textContent = `Building ${i + 1}/${M.count}…`;
      const blob = await svgToPng(M.slides[i], M.width, M.height);
      files.push({ name: `${slug}-${i + 1}.png`, data: new Uint8Array(await blob.arrayBuffer()) });
    }
    download(makeZip(files), `${slug}.zip`);
  } finally {
    btn.textContent = label; btn.disabled = false;
  }
};

document.getElementById('copyCap').onclick = async () => {
  const el = document.getElementById('captionText');
  const text = el.textContent;
  const b = document.getElementById('copyCap');
  let ok = false;

  // 1) Clipboard API (best, but rejects if the page isn't focused).
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      ok = true;
    }
  } catch (e) { /* fall through */ }

  // 2) Hidden textarea + execCommand fallback.
  if (!ok) {
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
      document.body.appendChild(ta);
      ta.focus(); ta.select();
      ok = document.execCommand('copy');
      ta.remove();
    } catch (e) { /* fall through */ }
  }

  // 3) Last resort: select the caption so the user can press Cmd/Ctrl+C.
  if (!ok) {
    const range = document.createRange();
    range.selectNodeContents(el);
    const sel = window.getSelection();
    sel.removeAllRanges(); sel.addRange(range);
  }

  b.textContent = ok ? 'Copied ✓' : 'Selected — press ⌘C';
  setTimeout(() => b.textContent = 'Copy', 2200);
};

load();
</script>
</body>
</html>
"""
