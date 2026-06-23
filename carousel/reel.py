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


# xfade transitions worth picking by beat (any ffmpeg xfade name also works).
TRANSITIONS = {
    "fade", "fadeblack", "fadewhite", "dissolve", "slideleft", "slideright",
    "slideup", "slidedown", "wipeleft", "wiperight", "wipeup", "wipedown",
    "smoothleft", "smoothright", "circleopen", "circleclose", "radial",
    "zoomin", "pixelize", "diagtl", "diagbr",
}
MOTIONS = {"zoomin", "zoomout", "panleft", "panright", "none"}


def _motion_filter(motion: str, frames: int) -> str:
    """zoompan expression for a scene's Ken-Burns motion, as a function of the
    output frame index `on` so it spans the scene regardless of duration."""
    rate = 0.16 / max(frames, 1)
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if motion == "zoomout":
        return f"zoompan=z='max(1.16-{rate:.6f}*on,1.0)':x='{cx}':y='{cy}'"
    if motion == "panleft":
        return f"zoompan=z='1.12':x='(iw-iw/zoom)*(1-on/{frames})':y='{cy}'"
    if motion == "panright":
        return f"zoompan=z='1.12':x='(iw-iw/zoom)*(on/{frames})':y='{cy}'"
    if motion == "none":
        return f"zoompan=z='1.0':x='{cx}':y='{cy}'"
    # default: zoomin
    return f"zoompan=z='min(1.0+{rate:.6f}*on,1.16)':x='{cx}':y='{cy}'"


def compile_video(bg_paths: list[Path], fg_paths: list[Path], out_path: Path,
                  configs: list[dict] | None = None, bug_path: Path | None = None,
                  per_scene: float = 3.2, transition: float = 0.6) -> Path:
    """Compile layered scenes into a Reel MP4.

    Each scene = a background PNG (gets a Ken-Burns zoom) + a transparent
    foreground PNG (text/accent) that ANIMATES IN (slide-up + fade) over the
    background — so it reads as a reel, not a panned carousel. An optional
    brand-bug PNG is overlaid persistently as a channel watermark.

    configs[i] (optional): {duration, motion, transition, transition_dur}.
    """
    ff = _require("ffmpeg")
    n = len(bg_paths)
    if n == 0:
        raise ValueError("No scenes to compile.")
    configs = (configs or []) + [{}] * n
    durs = [float(configs[i].get("duration") or per_scene) for i in range(n)]
    motions = [str(configs[i].get("motion") or "zoomin") for i in range(n)]
    trans = [str(configs[i].get("transition") or "fade") for i in range(n)]
    tdurs = [float(configs[i].get("transition_dur") or transition) for i in range(n)]
    total = total_duration(durs, tdurs)

    inputs: list[str] = []
    for i in range(n):
        inputs += ["-loop", "1", "-t", f"{durs[i]}", "-i", str(bg_paths[i])]
        inputs += ["-loop", "1", "-t", f"{durs[i]}", "-i", str(fg_paths[i])]
    if bug_path:
        inputs += ["-loop", "1", "-t", f"{total}", "-i", str(bug_path)]

    # Slide-up + fade entrance for the foreground (escaped commas for ffmpeg).
    intro = 0.5
    yexpr = rf"if(lt(t\,{intro})\,(({intro}-t)/{intro})*80\,0)"

    filters: list[str] = []
    for i in range(n):
        bi, fi = 2 * i, 2 * i + 1
        frames = int(durs[i] * FPS)
        zp = _motion_filter(motions[i], frames)
        filters.append(
            f"[{bi}:v]scale=1620:2880,{zp}:d={frames}:s={W}x{H}:fps={FPS},"
            f"trim=duration={durs[i]},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[bg{i}]"
        )
        filters.append(
            f"[{fi}:v]scale={W}:{H},fps={FPS},format=rgba,"
            f"fade=t=in:st=0:d={intro}:alpha=1,trim=duration={durs[i]},setpts=PTS-STARTPTS[fg{i}]"
        )
        filters.append(f"[bg{i}][fg{i}]overlay=x=0:y='{yexpr}':format=auto[c{i}]")

    if n == 1:
        last = "[c0]"
    else:
        prev, acc = "[c0]", durs[0]
        for i in range(1, n):
            out = f"[x{i}]"
            td = tdurs[i - 1]
            filters.append(
                f"{prev}[c{i}]xfade=transition={trans[i-1]}:duration={td}:"
                f"offset={acc - td:.3f}{out}"
            )
            prev, acc = out, acc + durs[i] - td
        last = prev

    if bug_path:
        filters.append(f"{last}[{2*n}:v]overlay=x=0:y=0[outv]")
        last = "[outv]"

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
        raise RuntimeError(f"ffmpeg failed:\n{proc.stderr[-2000:]}")
    return out_path


def total_duration(durs: list[float], tdurs: list[float]) -> float:
    if not durs:
        return 0.0
    return round(sum(durs) - sum(tdurs[:len(durs) - 1]), 2)
