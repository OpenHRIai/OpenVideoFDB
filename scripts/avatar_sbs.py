"""Side-by-side video of one clip: the user (left), the human partner + three avatars (2x2 grid, right),
and one timeline underneath on which events pop in as they happen (user stops speaking,
each responder's onset with its latency); each responder pane carries its own speech strip at its bottom — for posts / talks, Seamless (CC-BY-NC) clips only.

    uv run python scripts/avatar_sbs.py <clip_id> --runs runs_v1/post --manifest runs_v1/post/manifest.jsonl \
        --out data/announcement/avatars_<clip>.mp4 [--panes gt:Human,heygen_a2av:HeyGen,tavus_av2av:Tavus,anam_a2av:Anam]

Needs `<runs>/<run>/<clip>/{agent.mp4|run.json, <bucket>/timing.json}` (run `ovfdb score-timing` first: the
timeline uses its `segments`). The user lane comes from the manifest's `user_words`. Audio = user + the avatar
panes at -6 dB (the human pane is muted: it is the visual reference). Layout 1920x1080: user 640x1080 | grid
2x2 of 640x360 | timeline 1280x360.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ovfdb.schema import read_manifest
from ovfdb.score.vad import speech_regions

FONT = next((f for f in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf") if Path(f).exists()), None)
W, H = 1920, 1080
USER_W = 640
PANE_W, PANE_H = 640, 360
TL_W, TL_H = 1280, 360
FPS = 30
COLORS = {"user": (90, 160, 255), "lane": (255, 196, 80)}
ATTRIBUTION = "Clip: Seamless Interaction Dataset (Meta FAIR), CC BY-NC 4.0 · OpenVideoFDB"


def _font(size: int):
    return ImageFont.truetype(FONT, size) if FONT else ImageFont.load_default()


def _segments_from_timing(run_dir: Path, clip_id: str) -> list[tuple[float, float]]:
    for d in sorted(run_dir.glob(f"{clip_id}*")):
        for tj in d.glob("*/timing.json"):
            t = json.loads(tj.read_text())
            return [(s["start"], s["end"]) for s in t.get("segments", [])]
    raise FileNotFoundError(f"no timing.json under {run_dir}/{clip_id}* (run `ovfdb score-timing {run_dir}`)")


def _agent_video(run_dir: Path, clip_id: str, fallback: str | None = None) -> Path:
    """The run's agent.mp4; the human-reference run has none, so `fallback` = the manifest's partner video."""
    if fallback and Path(fallback).exists() and not any(run_dir.glob(f"{clip_id}*/agent.mp4")):
        return Path(fallback)
    for d in sorted(run_dir.glob(f"{clip_id}*")):
        rj = d / "run.json"
        if rj.exists():
            p = json.loads(rj.read_text()).get("agent_video_path")
            if p and Path(p).exists():
                return Path(p)
            if (d / "agent.mp4").exists():
                return d / "agent.mp4"
    raise FileNotFoundError(f"no agent video under {run_dir}/{clip_id}*")


PANE_COLORS = [(110, 210, 140), (255, 196, 80), (120, 170, 255), (235, 120, 200)]


def _ease(a: float) -> float:
    a = min(1.0, max(0.0, a))
    return 1 - (1 - a) ** 3


def render_timeline(frames_dir: Path, user_segs: list[tuple[float, float]],
                    responders: list[tuple[str, list[tuple[float, float]]]], dur: float, ds: float, de: float,
                    title: str) -> tuple[int, list[tuple[str, float]]]:
    """PNG per video frame: one timeline bar; the user's speech on it; events pop in as the playhead passes
    them — "user stops speaking" at the handover, then each responder's first onset after it with its latency.
    Returns (frame count, user_end, [(label, latency_s)])."""
    n = int(dur * FPS) + 1
    pad = 28
    x0, x1 = pad + 8, TL_W - pad - 8
    sx = (x1 - x0) / dur
    y_bar = 236
    f_title, f_lab, f_lat, f_small = _font(26), _font(22), _font(24), _font(16)
    ends = [e for _, e in user_segs if e <= ds + 0.4]
    user_end = max(ends) if ends else ds
    events: list[tuple[float, str, float | None, tuple[int, int, int]]] = [(user_end, "User stops speaking", None, (200, 200, 210))]
    for i, (label, segs) in enumerate(responders):
        on = next((st for st, _ in segs if st >= user_end - 0.3), None)
        if on is not None:
            events.append((on, label, on - user_end, PANE_COLORS[i % len(PANE_COLORS)]))
    events.sort(key=lambda e: e[0])
    rows = {ev[1]: r for r, ev in enumerate(e for e in events if e[2] is not None)}
    lat_out = [(label, lat) for _, label, lat, _ in events if lat is not None]

    base = Image.new("RGB", (TL_W, TL_H), (18, 18, 22))
    dr = ImageDraw.Draw(base)
    dr.text((pad, 16), title, fill=(235, 235, 235), font=f_title)
    dr.rectangle([x0 + ds * sx, y_bar - 9, x0 + de * sx, y_bar + 9], fill=(50, 50, 70))
    dr.line([x0, y_bar, x1, y_bar], fill=(70, 70, 80), width=4)
    for t in range(0, int(dur) + 1, 5):
        dr.line([x0 + t * sx, y_bar + 10, x0 + t * sx, y_bar + 16], fill=(110, 110, 120), width=1)
        dr.text((x0 + t * sx - 8, y_bar + 20), f"{t} s", fill=(130, 130, 140), font=f_small)
    dr.text((pad, TL_H - 24), ATTRIBUTION, fill=(120, 120, 130), font=f_small)

    for k in range(n):
        T = k / FPS
        im = base.copy()
        d = ImageDraw.Draw(im)
        # the user's speech, revealed up to the playhead
        for st, en in user_segs:
            if st <= T:
                d.rectangle([x0 + st * sx, y_bar - 7, x0 + min(en, T) * sx, y_bar + 7], fill=COLORS["user"])
        # events that have happened, with a 0.3 s pop
        for t_e, label, lat, col in events:
            if t_e > T:
                continue
            a = _ease((T - t_e) / 0.3)
            x = x0 + t_e * sx
            layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            if lat is None:
                ld.line([x, y_bar - 14, x, y_bar + 14], fill=col + (255,), width=3)
                ld.polygon([(x - 7, y_bar - 26), (x + 7, y_bar - 26), (x, y_bar - 14)], fill=col + (255,))
                tw = f_lab.getlength(label)          # right-aligned left of the marker: responder boxes go right
                ld.text((x - tw - 14, y_bar - 48 + 10 * (1 - a)), label, fill=col + (255,), font=f_lab)
            else:
                r = rows[label]
                y_lab = y_bar - 60 - r * 42
                ld.line([x, y_lab + 18, x, y_bar - 10], fill=col + (160,), width=2)
                ld.ellipse([x - 7, y_bar - 7, x + 7, y_bar + 7], fill=col + (255,))
                text = f"{label}   +{lat:.1f} s"
                tw = f_lat.getlength(text)
                bx = min(max(x + 10, x0), x1 - tw - 24)
                yy = y_lab + 10 * (1 - a)
                ld.rounded_rectangle([bx, yy, bx + tw + 20, yy + 36], radius=8, fill=col + (235,))
                ld.text((bx + 10, yy + 5), text, fill=(20, 20, 24, 255), font=f_lat)
            if a < 1:
                alpha = layer.split()[3].point(lambda v, a=a: int(v * a))
                layer.putalpha(alpha)
            im = Image.alpha_composite(im.convert("RGBA"), layer).convert("RGB")
            d = ImageDraw.Draw(im)
        xp = x0 + T * sx
        d.line([xp, y_bar - 30, xp, y_bar + 40], fill=(255, 80, 80), width=3)
        im.save(frames_dir / f"{k:05d}.png")
    return n, user_end, lat_out


STRIP_H = 44


def render_pane_strips(dirs: list[Path], responders: list[tuple[str, list[tuple[float, float]]]], dur: float,
                       user_end: float) -> None:
    """One RGBA PNG per frame per responder: a translucent band for the bottom of its pane with its own speech
    (revealed up to the playhead), the user's stop marker and the playhead."""
    n = int(dur * FPS) + 1
    x0, x1 = 12, PANE_W - 12
    sx = (x1 - x0) / dur
    yb = STRIP_H // 2
    for i, (frames_dir, (_, segs)) in enumerate(zip(dirs, responders, strict=True)):
        col = PANE_COLORS[i % len(PANE_COLORS)]
        base = Image.new("RGBA", (PANE_W, STRIP_H), (0, 0, 0, 0))
        d = ImageDraw.Draw(base)
        d.rectangle([0, 0, PANE_W, STRIP_H], fill=(0, 0, 0, 140))
        d.line([x0, yb, x1, yb], fill=(255, 255, 255, 70), width=2)
        xe = x0 + user_end * sx
        d.polygon([(xe - 5, yb - 12), (xe + 5, yb - 12), (xe, yb - 4)], fill=(230, 230, 230, 255))
        for k in range(n):
            T = k / FPS
            im = base.copy()
            dd = ImageDraw.Draw(im)
            for st, en in segs:
                if st <= T:
                    dd.rectangle([x0 + st * sx, yb - 6, x0 + min(en, T) * sx, yb + 6], fill=col + (255,))
            xp = x0 + T * sx
            dd.line([xp, 6, xp, STRIP_H - 6], fill=(255, 80, 80, 255), width=2)
            im.save(frames_dir / f"{k:05d}.png")


def _label_png(path: Path, text: str) -> Path:
    """Label as a transparent PNG (this ffmpeg has no drawtext): white text on a half-black box."""
    f = _font(30)
    tw = int(f.getlength(text)) if hasattr(f, "getlength") else 16 * len(text)
    im = Image.new("RGBA", (tw + 24, 48), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, tw + 23, 47], fill=(0, 0, 0, 128))
    d.text((12, 6), text, fill=(255, 255, 255, 255), font=f)
    im.save(path)
    return path


def build(clip_id: str, runs: Path, manifest: Path, out: Path, panes: list[tuple[str, str]], title: str | None,
          crop_top: int) -> Path:
    s = next(x for x in read_manifest(manifest) if x.clip_id == clip_id)
    dur = float(s.duration_s)
    user_segs = speech_regions(s.user_audio_path)          # VAD: the transcript's word alignment can smear a word
    responders = [(label, _segments_from_timing(runs / run, clip_id)) for run, label in panes]
    videos = [_agent_video(runs / run, clip_id, s.partner_video_path if run.startswith("gt") else None)
              for run, _ in panes]
    title = title or f"{s.dynamic_type.value} latency"
    tmp = Path(tempfile.mkdtemp(prefix="ovfdb_sbs_"))
    try:
        frames = tmp / "tl"
        frames.mkdir()
        _, user_end, lats = render_timeline(frames, user_segs, responders, dur, s.dynamic_start_s, s.dynamic_end_s,
                                            title)
        print("latencies:", ", ".join(f"{label} +{lat:.2f}s" for label, lat in lats))
        strip_dirs = [tmp / f"strip{i}" for i in range(len(panes))]
        for sd in strip_dirs:
            sd.mkdir()
        render_pane_strips(strip_dirs, responders, dur, user_end)
        inputs = ["-i", s.user_video_path, "-i", s.user_audio_path]
        for v in videos:
            inputs += ["-i", str(v)]
        inputs += ["-framerate", str(FPS), "-i", str(frames / "%05d.png")]
        n_pane = len(videos)
        tl_idx = 2 + n_pane
        labels = ["User"] + [label for _, label in panes]
        lab_idx = tl_idx + 1                          # one still PNG input per label, overlaid at (16, 16)
        for k, text in enumerate(labels):
            inputs += ["-i", str(_label_png(tmp / f"label{k}.png", text))]
        strip_idx = lab_idx + len(labels)             # one PNG sequence per pane, overlaid at its bottom
        for sd in strip_dirs:
            inputs += ["-framerate", str(FPS), "-i", str(sd / "%05d.png")]
        # portrait 720x1280 source: crop at the pane's aspect from the top (head kept, feet trimmed), no bars
        crop_h = int(720 * H / USER_W)
        fc = [(f"[0:v]crop=720:{crop_h}:0:0,scale={USER_W}:{H}[u0];"
               f"[u0][{lab_idx}:v]overlay=16:16[u]")]
        for i, ((run, label), v) in enumerate(zip(panes, videos, strict=True)):
            src = f"[{2 + i}:v]"
            is_portrait = run.startswith("gt")
            pre = f"crop=720:405:0:{crop_top}," if is_portrait else ""
            fc.append(f"{src}{pre}scale={PANE_W}:{PANE_H}:force_original_aspect_ratio=decrease,"
                      f"pad={PANE_W}:{PANE_H}:(ow-iw)/2:(oh-ih)/2,setsar=1[q{i}];"
                      f"[q{i}][{lab_idx + 1 + i}:v]overlay=16:16[r{i}];"
                      f"[r{i}][{strip_idx + i}:v]overlay=0:{PANE_H - STRIP_H}[p{i}]")
        fc.append("[p0][p1][p2][p3]xstack=inputs=4:layout=0_0|w0_0|0_h0|w0_h0[grid]")
        fc.append(f"[{tl_idx}:v]scale={TL_W}:{TL_H}[tl]")
        fc.append("[grid][tl]vstack[right]")
        fc.append("[u][right]hstack[v]")
        # audio: user + avatar panes (-6 dB), human pane muted
        amix = ["[1:a]"]
        for i, (run, _) in enumerate(panes):
            if not run.startswith("gt"):
                fc.append(f"[{2 + i}:a]volume=0.5[a{i}]")
                amix.append(f"[a{i}]")
        fc.append(f"{''.join(amix)}amix=inputs={len(amix)}:duration=first:normalize=0[a]")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(fc),
               "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", "-r", str(FPS), "-c:v", "libx264", "-preset",
               "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags",
               "+faststart", str(out)]
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(cmd, check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip_id")
    ap.add_argument("--runs", default="runs_v1/post")
    ap.add_argument("--manifest", default="runs_v1/post/manifest.jsonl")
    ap.add_argument("--out", default="")
    ap.add_argument("--panes", default="gt:Human partner,heygen_a2av:HeyGen LiveAvatar,tavus_av2av:Tavus CVI,anam_a2av:Anam")
    ap.add_argument("--title", default=None)
    ap.add_argument("--crop-top", type=int, default=60, help="y offset of the 720x405 head crop for portrait panes")
    a = ap.parse_args()
    panes = [tuple(p.split(":", 1)) for p in a.panes.split(",")]
    out = Path(a.out or f"data/announcement/avatars_{a.clip_id}.mp4")
    print(build(a.clip_id, Path(a.runs), Path(a.manifest), out, panes, a.title, a.crop_top))


if __name__ == "__main__":
    main()
