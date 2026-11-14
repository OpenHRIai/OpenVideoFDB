"""Side-by-side video of one clip for posts and talks: the user (left), the human partner and three avatars (2x2
grid, right), and one lane chart underneath with everyone's speech on a single shared time axis. Seamless
(CC BY-NC) clips only.

    uv run python scripts/avatar_sbs.py <clip_id> --runs runs_v1/post --manifest runs_v1/post/manifest.jsonl \
        --out data/announcement/avatars_<clip>.mp4 [--panes gt:Human partner,heygen_a2av:HeyGen LiveAvatar,...]

Layout (1920x1216): user 640x1080 | grid 2x2 of 640x360 | lane chart 1280x360, and a 136 px strip along the bottom
with only the attribution, so a browser's play bar (shown whenever the video is paused) covers no data.

Design rules (2026-11-14 redesign; the first version had a separate speech strip in every pane, each on its own
scale, so its marks could not line up with the timeline under them):
- One time axis. Every speech band, the "user stops" line, the handoff window and the playhead are drawn in one
  chart with one x scale, so anything at the same moment sits at the same x.
- One colour per speaker, fixed by identity (the same in every clip), used for the pane frame, the pane label and
  the lane. The user is neutral grey, so no responder shares a colour with them. Okabe-Ito hues, readable with
  the common colour-vision deficiencies.
- Latency is drawn as a length: a thin line in each responder's lane from the end of the user's speech to that
  responder's first reply, with a right-hand column that counts up while it waits and freezes at the reply.
- Lanes and grid panes in the same order: responders sorted by latency, fastest first.
- Labels sit next to what they name (no legend), and the user's words are captioned for muted playback.

Inputs: `<runs>/<run>/<clip>/{agent.mp4|run.json, <bucket>/timing.json}` (run `ovfdb score-timing` first; its
`segments` are VAD-based). The user's lane is VAD on user.wav; the caption uses the manifest's `user_words`.
Audio: every voice loudness-normalised to -18 LUFS (avatars 3 dB under), mixed and limited.
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

_FONT_DIR = Path("/System/Library/Fonts/Supplemental")
FONT = next((str(f) for f in (_FONT_DIR / "Arial.ttf", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
             if f.exists()), None)
FONT_BOLD = next((str(f) for f in (_FONT_DIR / "Arial Bold.ttf",
                                   Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")) if f.exists()), FONT)
W, H = 1920, 1080
OUT_H = 1216                       # H plus the bottom strip for the browser's controls
USER_W = 640
PANE_W, PANE_H = 640, 360
TL_X, TL_Y, TL_W, TL_H = 640, 720, 1280, 360
FPS = 30
BG = (18, 18, 22)
INK, MUTED, FAINT = (235, 235, 238), (150, 150, 160), (70, 70, 80)
USER_COL = (200, 200, 208)
# Okabe-Ito hues, lightened where needed for a dark background; keyed by run-name prefix so a vendor keeps its colour
COLORS = {"gt": (0, 190, 140), "tavus": (86, 180, 233), "heygen": (230, 159, 0), "anam": (204, 121, 167)}
SPARE = [(240, 228, 66), (213, 94, 0)]
ATTRIBUTION = "Clip: Seamless Interaction Dataset (Meta FAIR), CC BY-NC 4.0 · OpenVideoFDB"


def _font(size: int, bold: bool = False):
    f = FONT_BOLD if bold else FONT
    return ImageFont.truetype(f, size) if f else ImageFont.load_default()


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


def first_onset(segs: list[tuple[float, float]], user_end: float) -> float | None:
    """First speech onset that counts as the reply: starts at most 0.3 s before the user's speech ends."""
    return next((st for st, _ in segs if st >= user_end - 0.3), None)


def caption_groups(words: list[tuple[str, float, float]], gap: float = 0.6) -> list[list[tuple[str, float, float]]]:
    """Split words into caption lines at sentence punctuation or a pause longer than `gap` seconds."""
    groups: list[list[tuple[str, float, float]]] = []
    for w in words:
        if not groups or groups[-1][-1][0].rstrip().endswith((".", "?", "!")) or w[1] - groups[-1][-1][2] > gap:
            groups.append([])
        groups[-1].append(w)
    return groups


def _chunks(group, font, width: int, max_lines: int = 2):
    """Split a caption group into pieces of at most `max_lines` wrapped lines, each timed by its own words."""
    lines = _wrap([w for w, _, _ in group], font, width)
    return [[group[i] for ln in lines[k:k + max_lines] for i in ln] for k in range(0, len(lines), max_lines)]


def _wrap(words: list[str], font, width: int) -> list[list[int]]:
    """Word indices per wrapped line."""
    lines: list[list[int]] = [[]]
    for i, w in enumerate(words):
        trial = " ".join(words[j] for j in lines[-1] + [i])
        if lines[-1] and font.getlength(trial) > width:
            lines.append([])
        lines[-1].append(i)
    return lines


class Overlay:
    """Draws one transparent 1920x1216 overlay per video frame: the lane chart, pane frames and labels, caption."""

    def __init__(self, dur: float, user_segs, user_words, responders, ds: float, de: float, title: str):
        self.dur, self.user_segs, self.responders, self.ds, self.de = dur, user_segs, responders, ds, de
        ends = [e for _, e in user_segs if e <= ds + 0.4]
        self.user_end = max(ends) if ends else ds
        self.onsets = [first_onset(segs, self.user_end) for _, _, segs in responders]
        self.f_chip, self.f_chip_b, self.f_cap = _font(26), _font(26, True), _font(32)
        self.groups = [c for g in caption_groups(user_words) for c in _chunks(g, self.f_cap, USER_W - 80)]
        # sizes for a 1920-wide frame shown about 960 px wide on the blog: nothing under 18 px here (9 px there)
        self.f_title, self.f_sub, self.f_lane = _font(32, True), _font(22), _font(25)
        self.f_col, self.f_small, self.f_tiny = _font(28, True), _font(21), _font(20)
        self.f_wait = _font(28)
        # lane chart geometry, panel-local pixels
        self.lane_top, self.lane_h = 122, 34
        self.x0, self.x1 = 270, 1110
        self.col_r = TL_W - 28
        self.y_axis = self.lane_top + self.lane_h * (1 + len(responders)) + 4
        self.sx = (self.x1 - self.x0) / dur
        self.base = self._panel_base(title)

    def X(self, t: float) -> float:
        return self.x0 + t * self.sx

    def yc(self, lane: int) -> float:
        return self.lane_top + self.lane_h * lane + self.lane_h / 2

    def _panel_base(self, title: str) -> Image.Image:
        im = Image.new("RGB", (TL_W, TL_H), BG)
        d = ImageDraw.Draw(im, "RGBA")
        d.text((28, 10), title, fill=INK, font=self.f_title)
        d.text((28, 52), "Bars: who is speaking. Thin line: the wait from the end of the user's speech to the "
               "first reply.", fill=MUTED, font=self.f_sub)
        tw = self.f_small.getlength("reply after")
        d.text((self.col_r - tw, 90), "reply after", fill=MUTED, font=self.f_small)
        lanes = [("User", USER_COL)] + [(label, col) for label, col, _ in self.responders]
        for k, (label, col) in enumerate(lanes):
            y = self.yc(k)
            lw = self.f_lane.getlength(label)
            d.text((self.x0 - 16 - lw, y - 15), label, fill=col, font=self.f_lane)
            d.line([self.x0, y, self.x1, y], fill=(255, 255, 255, 28), width=2)
        for t in range(int(self.dur) + 1):
            x = self.X(t)
            d.line([x, self.y_axis, x, self.y_axis + (7 if t % 5 == 0 else 4)], fill=MUTED, width=1)
            if t % 5 == 0:
                d.text((x - 8, self.y_axis + 9), f"{t} s", fill=MUTED, font=self.f_tiny)
        return im

    def _panel(self, T: float) -> Image.Image:
        im = self.base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        ue, n_lanes = self.user_end, 1 + len(self.responders)
        top, bot = self.lane_top - 4, self.lane_top + self.lane_h * n_lanes
        if T >= ue:                                     # the user stops: reference line and the handoff window
            a = min(1.0, (T - ue) / 0.25)
            d.rectangle([self.X(self.ds), self.lane_top + self.lane_h, self.X(self.de), bot],
                        fill=(255, 255, 255, int(24 * a)))
            for y in range(int(top), int(bot), 8):
                d.line([self.X(ue), y, self.X(ue), y + 4], fill=(230, 230, 235, int(220 * a)), width=2)
            lab = "user stops"
            d.text((self.X(ue) - 8 - self.f_small.getlength(lab), 90), lab, fill=(230, 230, 235, int(255 * a)),
                   font=self.f_small)
            d.text((self.X(self.ds) + 8, 90), f"handoff window ({self.de - self.ds:.1f} s)",
                   fill=(170, 170, 180, int(255 * a)), font=self.f_small)
        lanes = [(USER_COL, self.user_segs, None)] + [(col, segs, on) for (_, col, segs), on
                                                      in zip(self.responders, self.onsets, strict=True)]
        for k, (col, segs, on) in enumerate(lanes):
            y = self.yc(k)
            if k > 0 and T > ue:                          # the wait, drawn as a length
                xe = self.X(min(T, on) if on is not None else T)
                d.line([self.X(ue), y, xe, y], fill=col + (190,), width=3)
            for st, en in segs:
                if st <= T and st < self.dur:
                    d.rounded_rectangle([self.X(st), y - 9, self.X(min(en, T, self.dur)), y + 9], radius=4,
                                        fill=col)
            if k > 0 and T >= ue:                         # the latency column: counts up, then freezes
                if on is not None and T >= on:
                    txt, font, fill = f"+{on - ue:.1f} s", self.f_col, col
                elif on is None and T >= self.dur - 1 / FPS:
                    txt, font, fill = "no reply", self.f_small, MUTED
                else:
                    txt, font, fill = f"+{T - ue:.1f} s", self.f_wait, MUTED     # grey while still counting
                d.text((self.col_r - font.getlength(txt), y - 16), txt, fill=fill, font=font)
        xp = self.X(min(T, self.dur))
        d.line([xp, top - 2, xp, self.y_axis + 2], fill=(255, 255, 255, 210), width=2)
        return im

    def _chip(self, d: ImageDraw.ImageDraw, x: int, y: int, label: str, col, speaking: bool, lat: float | None):
        name_w = self.f_chip.getlength(label)
        lat_txt = f"  +{lat:.1f} s" if lat is not None else ""
        lat_w = self.f_chip_b.getlength(lat_txt) if lat_txt else 0
        w = int(44 + name_w + lat_w + 14)
        d.rounded_rectangle([x, y, x + w, y + 44], radius=8, fill=(0, 0, 0, 165))
        cx, cy = x + 22, y + 22
        if speaking:
            d.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=col + (255,))
        else:
            d.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], outline=col + (255,), width=2)
        d.text((x + 40, y + 7), label, fill=(255, 255, 255, 255), font=self.f_chip)
        if lat_txt:
            d.text((x + 40 + name_w, y + 7), lat_txt, fill=col + (255,), font=self.f_chip_b)

    def _caption(self, d: ImageDraw.ImageDraw, T: float):
        for gi, g in enumerate(self.groups):
            nxt = self.groups[gi + 1][0][1] if gi + 1 < len(self.groups) else 1e9
            # off 1 s after the last word; the word alignment can stretch a final word over the following
            # silence (P0222_c00: "Yeah," 7.1-16.9 s), so a word counts as at most 0.8 s long here
            last_end = min(g[-1][2], g[-1][1] + 0.8)
            if not (g[0][1] <= T < min(last_end + 1.0, nxt)):
                continue
            words = [w for w, _, _ in g]
            lines = _wrap(words, self.f_cap, USER_W - 80)
            lh = 42
            box_h = lh * len(lines) + 20
            y0 = H - 48 - box_h
            widths = [self.f_cap.getlength(" ".join(words[i] for i in ln)) for ln in lines]
            bw = max(widths) + 32
            d.rounded_rectangle([(USER_W - bw) / 2, y0, (USER_W + bw) / 2, y0 + box_h], radius=8,
                                fill=(0, 0, 0, 170))
            for li, ln in enumerate(lines):
                x = (USER_W - widths[li]) / 2
                for i in ln:                                # words appear as they are spoken
                    w, st, _ = g[i]
                    if st <= T:
                        d.text((x, y0 + 10 + li * lh), w, fill=(255, 255, 255, 255), font=self.f_cap)
                    x += self.f_cap.getlength(w + " ")

    def frame(self, T: float) -> Image.Image:
        im = Image.new("RGBA", (W, OUT_H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([0, H, W, OUT_H], fill=BG + (255,))
        d.text((28, H + 22), ATTRIBUTION, fill=(130, 130, 140, 255), font=_font(21))
        # the user pane
        speaking = any(st <= T < en for st, en in self.user_segs)
        self._chip(d, 14, 14, "User", USER_COL, speaking, None)
        self._caption(d, T)
        # responder panes: frame in the speaker's colour, label with a speaking dot and, once replied, the latency
        for i, ((label, col, segs), on) in enumerate(zip(self.responders, self.onsets, strict=True)):
            px, py = USER_W + (i % 2) * PANE_W, (i // 2) * PANE_H
            d.rectangle([px + 1, py + 1, px + PANE_W - 2, py + PANE_H - 2], outline=col + (230,), width=3)
            spk = any(st <= T < en for st, en in segs)
            self._chip(d, px + 14, py + 14, label, col, spk, (on - self.user_end) if on is not None and T >= on
                       else None)
        im.paste(self._panel(T), (TL_X, TL_Y))
        return im


def build(clip_id: str, runs: Path, manifest: Path, out: Path, panes: list[tuple[str, str]], title: str | None,
          crop_top: int) -> Path:
    s = next(x for x in read_manifest(manifest) if x.clip_id == clip_id)
    dur = float(s.duration_s)
    user_segs = speech_regions(s.user_audio_path)          # VAD: the transcript's word alignment can smear a word
    user_words = [(w.text, w.start, w.end) for w in s.user_words]
    spare = iter(SPARE)
    rows = []
    for run, label in panes:
        col = next((c for k, c in COLORS.items() if run.startswith(k)), None) or next(spare)
        segs = _segments_from_timing(runs / run, clip_id)
        video = _agent_video(runs / run, clip_id, s.partner_video_path if run.startswith("gt") else None)
        rows.append((run, label, col, segs, video))
    ov0 = Overlay(dur, user_segs, user_words, [(r[1], r[2], r[3]) for r in rows], s.dynamic_start_s,
                  s.dynamic_end_s, title or f"{s.dynamic_type.value} latency")
    order = sorted(range(len(rows)), key=lambda i: (ov0.onsets[i] is None, ov0.onsets[i] or 0))
    rows = [rows[i] for i in order]                         # fastest first, in the lanes and in the grid
    ov = Overlay(dur, user_segs, user_words, [(r[1], r[2], r[3]) for r in rows], s.dynamic_start_s,
                 s.dynamic_end_s, title or f"{s.dynamic_type.value} latency")
    print("latencies:", ", ".join(f"{r[1]} +{on - ov.user_end:.2f}s" if on is not None else f"{r[1]} none"
                                  for r, on in zip(rows, ov.onsets, strict=True)))
    tmp = Path(tempfile.mkdtemp(prefix="ovfdb_sbs_"))
    try:
        frames = tmp / "ov"
        frames.mkdir()
        n = int(dur * FPS) + 1
        for k in range(n):
            ov.frame(k / FPS).save(frames / f"{k:05d}.png", compress_level=1)
        inputs = ["-i", s.user_video_path, "-i", s.user_audio_path]
        for r in rows:
            inputs += ["-i", str(r[4])]
        ov_idx = 2 + len(rows)
        inputs += ["-framerate", str(FPS), "-i", str(frames / "%05d.png")]
        crop_h = int(720 * H / USER_W)        # portrait 720x1280 user: crop at the pane's aspect from the top
        fc = [f"color=c=0x121216:s={W}x{OUT_H}:r={FPS}:d={dur:.3f}[bg]",
              f"[0:v]crop=720:{crop_h}:0:0,scale={USER_W}:{H},setsar=1[u]", "[bg][u]overlay=0:0[b0]"]
        for i, r in enumerate(rows):
            pre = f"crop=720:405:0:{crop_top}," if r[0].startswith("gt") else ""
            fc.append(f"[{2 + i}:v]{pre}scale={PANE_W}:{PANE_H}:force_original_aspect_ratio=decrease,"
                      f"pad={PANE_W}:{PANE_H}:(ow-iw)/2:(oh-ih)/2,setsar=1[q{i}]")
            fc.append(f"[b{i}][q{i}]overlay={USER_W + (i % 2) * PANE_W}:{(i // 2) * PANE_H}[b{i + 1}]")
        fc.append(f"[b{len(rows)}][{ov_idx}:v]overlay=0:0[v]")
        # audio: the lapel mics peak at -30 dB, the avatars' TTS at 0 dB; user and human partner at -18 LUFS,
        # the avatars 3 dB under them; limited after the mix
        fc.append("[1:a]loudnorm=I=-18:TP=-2:LRA=11[au]")
        amix = ["[au]"]
        for i, r in enumerate(rows):
            gain = "" if r[0].startswith("gt") else ",volume=0.7"
            fc.append(f"[{2 + i}:a]loudnorm=I=-18:TP=-2:LRA=11{gain}[a{i}]")
            amix.append(f"[a{i}]")
        fc.append(f"{''.join(amix)}amix=inputs={len(amix)}:duration=first:normalize=0,alimiter=limit=0.9,"
                  f"aresample=48000[a]")
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
    ap.add_argument("--panes", default="gt:Human partner,heygen_a2av:HeyGen LiveAvatar,tavus_av2av:Tavus CVI,"
                                       "anam_a2av:Anam")
    ap.add_argument("--title", default=None)
    ap.add_argument("--crop-top", type=int, default=60, help="y offset of the 720x405 head crop for portrait panes")
    a = ap.parse_args()
    panes = [tuple(p.split(":", 1)) for p in a.panes.split(",")]
    out = Path(a.out or f"data/announcement/avatars_{a.clip_id}.mp4")
    print(build(a.clip_id, Path(a.runs), Path(a.manifest), out, panes, a.title, a.crop_top))


if __name__ == "__main__":
    main()
