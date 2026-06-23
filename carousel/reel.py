"""Compile vertical 9:16 scenes into an Instagram Reel (MP4).

Each scene is a normal slide spec rendered at story size (1080x1920), rasterised
to PNG with rsvg-convert, then compiled with ffmpeg into a slideshow video with
a subtle Ken-Burns zoom per scene and crossfades between scenes. No audio —
creators add trending audio in the Instagram app.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

W, H = 1080, 1920
FPS = 30


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise RuntimeError(
            f"'{tool}' not found. Install it (e.g. `brew install "
            f"{'librsvg' if tool == 'rsvg-convert' else 'ffmpeg'}`)."
        )
    return path


def rasterize(svg_path: Path, png_path: Path) -> None:
    subprocess.run(
        [_require("rsvg-convert"), "-w", str(W), "-h", str(H),
         str(svg_path), "-o", str(png_path)],
        check=True, capture_output=True,
    )


def compile_video(png_paths: list[Path], out_path: Path,
                  per_scene: float = 3.2, transition: float = 0.6,
                  zoom: bool = True) -> Path:
    """Compile PNG scenes into an MP4 with per-scene zoom + crossfades."""
    ff = _require("ffmpeg")
    n = len(png_paths)
    if n == 0:
        raise ValueError("No scenes to compile.")

    inputs: list[str] = []
    for p in png_paths:
        inputs += ["-loop", "1", "-t", f"{per_scene}", "-i", str(p)]

    frames = int(per_scene * FPS)
    zexpr = "min(zoom+0.0009,1.15)" if zoom else "1.0"
    filters: list[str] = []
    for i in range(n):
        # Scale up first so the zoom stays crisp; trim to an exact duration.
        filters.append(
            f"[{i}:v]scale=1620:2880,"
            f"zoompan=z='{zexpr}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={W}x{H}:fps={FPS},trim=duration={per_scene},setpts=PTS-STARTPTS,"
            f"setsar=1,format=yuv420p[v{i}]"
        )

    if n == 1:
        last = "[v0]"
    else:
        prev, acc = "[v0]", per_scene
        for i in range(1, n):
            out = f"[x{i}]"
            offset = acc - transition
            filters.append(
                f"{prev}[v{i}]xfade=transition=fade:duration={transition}:"
                f"offset={offset:.3f}{out}"
            )
            prev, acc = out, acc + per_scene - transition
        last = prev

    cmd = [
        ff, "-y", *inputs,
        "-filter_complex", ";".join(filters),
        "-map", last,
        "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{proc.stderr[-1500:]}")
    return out_path


def total_duration(n: int, per_scene: float = 3.2, transition: float = 0.6) -> float:
    return round(n * per_scene - (n - 1) * transition, 2) if n else 0.0
