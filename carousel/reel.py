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


_INTRO = 0.5  # text slide-up + fade-in seconds
_YEXPR = rf"if(lt(t\,{_INTRO})\,(({_INTRO}-t)/{_INTRO})*80\,0)"


def make_scrim(path: Path) -> Path:
    """A reusable text-protection plate: transparent top/bottom, dark centre
    band, so text stays legible over any photo/video background."""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}"><defs>'
           '<linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
           '<stop offset="0%" stop-color="#000" stop-opacity="0"/>'
           '<stop offset="22%" stop-color="#000" stop-opacity="0.62"/>'
           '<stop offset="78%" stop-color="#000" stop-opacity="0.62"/>'
           '<stop offset="100%" stop-color="#000" stop-opacity="0"/>'
           f'</linearGradient></defs><rect width="{W}" height="{H}" fill="url(#g)"/></svg>')
    svgp = path.with_suffix(".svg")
    svgp.write_text(svg)
    subprocess.run([_require("rsvg-convert"), "-w", str(W), "-h", str(H),
                    str(svgp), "-o", str(path)], check=True, capture_output=True)
    return path


def _composite_scene(bg: Path, is_video: bool, fg: Path, dur: float, motion: str,
                     out: Path, scrim: Path | None = None, bug: Path | None = None) -> None:
    """Build one scene clip: background (real video OR Ken-Burns still) ->
    dark scrim plate -> animated text -> brand bug. Trimmed to `dur`."""
    ff = _require("ffmpeg")
    inputs = (["-i", str(bg)] if is_video
              else ["-loop", "1", "-t", f"{dur}", "-i", str(bg)])
    idx = 1
    scr_i = bug_i = None
    if scrim:
        inputs += ["-loop", "1", "-t", f"{dur}", "-i", str(scrim)]; scr_i = idx; idx += 1
    inputs += ["-loop", "1", "-t", f"{dur}", "-i", str(fg)]; fg_i = idx; idx += 1
    if bug:
        inputs += ["-loop", "1", "-t", f"{dur}", "-i", str(bug)]; bug_i = idx; idx += 1

    frames = int(dur * FPS)
    if is_video:  # real clip: dim + slightly desaturate -> backdrop, not subject
        chain = [f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                 f"eq=brightness=-0.10:saturation=0.85,setsar=1,fps={FPS},"
                 f"drawbox=x=0:y=0:w=iw:h=ih:color=black@0.40:t=fill,"
                 f"trim=duration={dur},setpts=PTS-STARTPTS[bg]"]
    else:  # still: Ken-Burns zoom
        chain = [f"[0:v]scale=1620:2880,{_motion_filter(motion, frames)}:d={frames}:s={W}x{H}:"
                 f"fps={FPS},trim=duration={dur},setpts=PTS-STARTPTS,setsar=1[bg]"]
    cur = "[bg]"
    if scrim:
        chain.append(f"[{scr_i}:v]scale={W}:{H},trim=duration={dur},setpts=PTS-STARTPTS[scr]")
        chain.append(f"{cur}[scr]overlay=0:0[bs]"); cur = "[bs]"
    chain.append(f"[{fg_i}:v]scale={W}:{H},format=rgba,fade=t=in:st=0:d={_INTRO}:alpha=1,"
                 f"trim=duration={dur},setpts=PTS-STARTPTS[fg]")
    chain.append(f"{cur}[fg]overlay=x=0:y='{_YEXPR}'[vf]"); cur = "[vf]"
    if bug:
        chain.append(f"{cur}[{bug_i}:v]overlay=0:0[vb]"); cur = "[vb]"
    cmd = [ff, "-y", *inputs, "-filter_complex", ";".join(chain), "-map", cur,
           "-t", f"{dur}", "-r", str(FPS), "-an", "-c:v", "libx264", "-preset", "medium",
           "-crf", "20", "-pix_fmt", "yuv420p", str(out)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg (scene composite) failed:\n{p.stderr[-1500:]}")


def compile_video(scenes: list[dict], out_path: Path, bug_path: Path | None = None,
                  scrim_path: Path | None = None, per_scene: float = 3.2,
                  transition: float = 0.6) -> Path:
    """Compile a Reel MP4 from per-scene specs. Each scene dict:
        bg (Path), is_video (bool), fg (Path), duration, motion, transition,
        transition_dur. Backgrounds may be real video clips or Ken-Burns stills;
        a scrim plate + brand bug are applied to every scene. Scenes are built
        individually then crossfaded (robust vs. one giant filtergraph)."""
    n = len(scenes)
    if n == 0:
        raise ValueError("No scenes to compile.")
    work = out_path.parent / "_comp"
    work.mkdir(exist_ok=True)
    comps, durs, tdurs, trans = [], [], [], []
    for i, s in enumerate(scenes):
        D = float(s.get("duration") or per_scene)
        comp = work / f"comp-{i}.mp4"
        _composite_scene(s["bg"], bool(s.get("is_video")), s["fg"], D,
                         str(s.get("motion") or "zoomin"), comp, scrim_path, bug_path)
        comps.append(comp); durs.append(D)
        tdurs.append(float(s.get("transition_dur") or transition))
        trans.append(str(s.get("transition") or "fade"))

    ff = _require("ffmpeg")
    inputs = []
    for c in comps:
        inputs += ["-i", str(c)]
    if n == 1:
        cmd = [ff, "-y", *inputs, "-map", "0:v"]
    else:
        filt, prev, acc = [], "[0:v]", durs[0]
        for i in range(1, n):
            o = f"[x{i}]"; td = tdurs[i - 1]
            filt.append(f"{prev}[{i}:v]xfade=transition={trans[i-1]}:duration={td}:"
                        f"offset={acc - td:.3f}{o}")
            prev, acc = o, acc + durs[i] - td
        cmd = [ff, "-y", *inputs, "-filter_complex", ";".join(filt), "-map", prev]
    cmd += ["-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_path)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg (stitch) failed:\n{p.stderr[-1500:]}")
    return out_path


def total_duration(durs: list[float], tdurs: list[float]) -> float:
    if not durs:
        return 0.0
    return round(sum(durs) - sum(tdurs[:len(durs) - 1]), 2)
