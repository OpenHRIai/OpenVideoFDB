"""Generation judge (vision-capable LLM; paper App. F.6, docs/protocol.md §6).

One call per (row, axis). System = `generation_preamble` (F.6.2) + universal axis (F.6.3:
`generation_affect_match`, `generation_fluency`) or per-category rubric (F.6.4) + an output-schema
reminder. User = JPEG frames of a side-by-side composite (USER left / AGENT right, labels burned
in, user audio L / agent audio R) sampled at `FPS` (8), capped at `MAX_FRAMES` (600) and resized
to `FRAME_WIDTH` (256 px wide, as the paper; a parameter because 256 px leaves each pane 128 px
wide), followed by the F.6.1 text block (framing note, dynamic metadata, USER STIMULUS, AGENT
OUTPUT with the audio-side ground truth and the agent–user overlap signal, agent segments and
transcript).

Universal axes return the universal schema `{analysis, rating, reasoning}`; category rubrics
return the decomposed schema `{analysis, cue_produced, cue_timing, cue_appropriateness,
reasoning}` with the F.3 consistency rules enforced after parsing (`enforce_consistency`); the
reported `rating` of the `cue_appropriateness` axis is the (consistent) cue_appropriateness.

Deviations from the paper (documented in docs/protocol.md §10 and the STATUS board):
- No Qwen-3.5 visual caption / Nemotron-Omni audio caption of the AGENT output: those lines say
  `[not available]`; the judge reads the AGENT pane of the frames directly and the agent speech
  segments mark wordless VAD regions (laughs, "mhm") as non-lexical vocalisations.
- The user-side caption is the full-clip AV caption the perception judge also gets (NVIDIA
  `qwen_caption_full` / Gemini Flash), not a caption cut at dynamic_start_s.
- When 8 fps would exceed the frame cap the frames are spread uniformly over the clip
  (effective fps = cap / duration) rather than truncated; the OpenAI API also refuses more than
  500 images per request, so gpt-4o sees at most 500 frames (`BACKEND_MAX_IMAGES`), Claude 100.
- The frames carry no audio (image inputs only); the stereo composite is written for review.
- Additions in the text block, marked `+` in `build_user_text`: a frame-timing line (frame k
  <-> t = k / fps), the annotated user cue line the perception payload v2 also carries, and
  the per-segment agent transcript with wordless regions marked.

Media caching: `<row_dir>/gen/sbs.mp4` (composite) and `<row_dir>/gen/frames/*.jpg` +
`frames.json`; re-runs re-encode nothing. Judge results cache at
`<row_dir>/judge/<axis>_<judge>.json` keyed by sha256(system, text, frames, judge).
Spec: plans/WS6-providers-avatar.md §6c.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ovfdb.schema import AgentRun, Axis, Bucket, DynamicType, Sample, Segment
from ovfdb.score import judge as J
from ovfdb.score.segments import words_to_segments

log = logging.getLogger(__name__)

DEFAULT_JUDGE = J.DEFAULT_JUDGE
#: F.6.1 frame sampling: 8 fps, at most 600 frames per call, 256 px wide JPEGs.
FPS = 8.0
MAX_FRAMES = 600
FRAME_WIDTH = 256
#: Height of each pane in the review composite (`sbs.mp4`); frames are resized from it.
COMPOSITE_PANE_H = 360
JPEG_QUALITY = 3            # ffmpeg -q:v (2 best .. 31 worst)
MAX_OUTPUT_TOKENS = 1024
#: Bumped whenever `build_user_text` / the frame plan changes shape; stored in judge.json.
PAYLOAD_VERSION = 1
NOT_AVAILABLE = "[not available]"
TIMING_VALUES = ("during", "late", "absent")
#: Per-backend hard limit on images per request; frames are thinned uniformly to fit (so for gpt-4o
#: the paper's 600-frame cap is effectively 500: clips >= 62.5 s are sampled below 8 fps).
BACKEND_MAX_IMAGES: dict[str, int] = {"openai": 500, "anthropic": 100}
#: A user utterance chunk counts as "substantive" (for the overlap signal) from this many words
#: or this long; shorter chunks are backchannels / fragments.
SUBSTANTIVE_MIN_WORDS = 3
SUBSTANTIVE_MIN_S = 1.0
OVERLAP_THRESHOLDS_S = (1.0, 1.5, 4.0)
MAX_LISTED_SEGMENTS = 8

GENERATION_AXES: frozenset[Axis] = frozenset({Axis.GEN_FLUENCY, Axis.AFFECT_MATCH, Axis.CUE_APPROPRIATENESS})
UNIVERSAL_RUBRICS: dict[Axis, str] = {
    Axis.GEN_FLUENCY: "generation_fluency",
    Axis.AFFECT_MATCH: "generation_affect_match",
}
#: F.6.4 per-category decomposed rubric per generation dynamic (Emotion Matching and Face
#: Emotion Display share one rubric in the paper).
CATEGORY_RUBRICS: dict[DynamicType, str] = {
    DynamicType.LAUGHTER: "generation_laughter",
    DynamicType.NONVERBAL_BACKCHANNELING: "generation_nonverbal_backchanneling",
    DynamicType.VERBAL_BACKCHANNELING: "generation_verbal_backchanneling",
    DynamicType.VERBAL_INTERRUPTION: "generation_verbal_interruption",
    DynamicType.FACE_EMOTION_DISPLAY: "generation_face_emotion_display",
    DynamicType.EMOTION_MATCHING: "generation_face_emotion_display",
    DynamicType.TURN_TAKING: "generation_turn_taking",
}

UNIVERSAL_SCHEMA = (
    'Respond with a JSON object only: {"analysis": "cite timings and specific visual/audio evidence; name the '
    'pane (USER/AGENT) when SBS", "rating": integer 0-5, "reasoning": "one sentence summary"}'
)
DECOMPOSED_SCHEMA = (
    "Output schema for this category axis (this replaces the universal schema above). Respond with a JSON object "
    'only: {"analysis": "cite timings and specific visual/audio evidence; name the pane (USER/AGENT) when SBS", '
    '"cue_produced": 0 or 1, "cue_timing": "during" or "late" or "absent", "cue_appropriateness": integer 0-5, '
    '"reasoning": "one sentence summary connecting all three keys"}\n'
    "Internal-consistency rules:\n"
    '- If cue_produced=0, then cue_timing="absent" and cue_appropriateness=0.\n'
    '- If cue_produced=1, cue_timing must be "during" or "late" (never "absent").\n'
    '- "during" requires the cue\'s onset to fall within [dynamic_start_s, dynamic_end_s] OR within 500ms of '
    'dynamic_start_s; later onsets are "late".\n'
    "- cue_appropriateness is graded as if the cue were on-time — timing penalties belong only to cue_timing."
)
FRAMING_NOTE = (
    "FRAMING NOTE --- frames above are a SIDE-BY-SIDE composite: LEFT = USER (context only; do NOT grade), "
    "RIGHT = AGENT (this is what you grade). Audio is stereo: USER on LEFT channel, AGENT on RIGHT."
)
VISUAL_CAPTION_NA = (
    f"{NOT_AVAILABLE} in OpenVideoFDB --- read the AGENT pane (RIGHT half) of the frames directly for the visual channel."
)
AUDIO_CAPTION_NA = (
    f"{NOT_AVAILABLE} in OpenVideoFDB --- the agent speech segments below mark wordless voice-activity regions as "
    f"{J.NO_LEXICAL}; treat those as possible laughs / backchannels / sighs."
)


class GenerationJudgeError(J.JudgeError):
    """A generation-judge failure that is not a parse error (media, unsupported row)."""


@dataclass
class GenJudgeResult(J.JudgeResult):
    """`JudgeResult` + the decomposed fields (None on the universal axes) and the frame digest."""

    cue_produced: int | None = None
    cue_timing: str | None = None
    consistency_fixes: list[str] = field(default_factory=list)
    n_frames: int = 0
    frames_sha256: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# --- rubrics / system prompt ---------------------------------------------------------------

def rubric_name(axis: Axis | str, dynamic: DynamicType | str) -> str:
    """Rubric file stem for (axis, dynamic); ValueError for a perception axis or an unmapped dynamic."""
    axis, dynamic = Axis(axis), DynamicType(dynamic)
    if axis in UNIVERSAL_RUBRICS:
        return UNIVERSAL_RUBRICS[axis]
    if axis is Axis.CUE_APPROPRIATENESS:
        try:
            return CATEGORY_RUBRICS[dynamic]
        except KeyError:
            raise ValueError(f"no generation category rubric for {dynamic.value!r}") from None
    raise ValueError(f"{axis.value!r} is not a generation axis")


def is_decomposed(axis: Axis | str) -> bool:
    return Axis(axis) is Axis.CUE_APPROPRIATENESS


def build_system_prompt(axis: Axis | str, sample: Sample) -> str:
    """F.6.2 preamble + (F.6.3 universal axis | F.6.4 category rubric) + output-schema reminder."""
    name = rubric_name(axis, sample.dynamic_type)
    schema = DECOMPOSED_SCHEMA if is_decomposed(axis) else UNIVERSAL_SCHEMA
    return "\n\n".join([J.load_rubric("generation_preamble"), J.load_rubric(name), schema])


# --- frame plan (pure) -----------------------------------------------------------------------

def effective_fps(duration_s: float, fps: float = FPS, max_frames: int = MAX_FRAMES) -> float:
    """`fps`, lowered to `max_frames / duration` when sampling at `fps` would exceed the cap."""
    if duration_s <= 0 or fps <= 0 or max_frames <= 0:
        return 0.0
    if math.floor(duration_s * fps) <= max_frames:
        return float(fps)
    return max_frames / duration_s


def frame_times(duration_s: float, fps: float = FPS, max_frames: int = MAX_FRAMES) -> list[float]:
    """Clip-relative timestamps of the sampled frames: t = k / effective_fps, k = 0.., t < duration.

    At most `max_frames`; the cap spreads the frames uniformly over the clip instead of truncating.
    """
    eff = effective_fps(duration_s, fps, max_frames)
    if eff <= 0:
        return []
    n = min(max_frames, max(1, math.floor(duration_s * eff + 1e-9)))
    return [k / eff for k in range(n)]


def thin_indices(n: int, limit: int) -> list[int]:
    """Uniformly spaced indices into range(n) with at most `limit` entries (all when n <= limit)."""
    if n <= 0 or limit <= 0:
        return []
    if n <= limit:
        return list(range(n))
    return sorted({round(i * (n - 1) / (limit - 1)) for i in range(limit)}) if limit > 1 else [0]


# --- media: composite + frames ---------------------------------------------------------------

def _probe_dims(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True,
    ).stdout.strip().split("\n")[0]
    w, h = (int(x) for x in out.split(",")[:2])
    return w, h


def _has_audio(path: Path) -> bool:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type",
                          "-of", "csv=p=0", str(path)], check=False, capture_output=True, text=True).stdout
    return "audio" in out


def label_overlay(width: int, height: int, labels: tuple[str, str] = ("USER", "AGENT"), pane_w: tuple[int, int] | None = None):
    """RGBA PIL image (`width` x `height`, transparent) with `labels` burned into the top-left corner of each pane.

    Box height is 12 % of the pane height, so the stamp drawn on the full composite and the one
    re-drawn on the resized frames cover the same area (crisp text at every scale).
    """
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    left_w = pane_w[0] if pane_w else width // 2
    box_h = max(8, round(height * 0.12))
    size = max(6, round(box_h * 0.72))
    try:
        font = ImageFont.load_default(size=size)
    except TypeError:                                   # very old Pillow: fixed-size bitmap font
        font = ImageFont.load_default()
    for x0, text in ((0, labels[0]), (left_w, labels[1])):
        tw = draw.textlength(text, font=font)
        pad = max(2, box_h // 4)
        draw.rectangle([x0, 0, x0 + tw + 2 * pad, box_h], fill=(0, 0, 0, 170))
        draw.text((x0 + pad, (box_h - size) / 2 - 1), text, fill=(255, 255, 255, 255), font=font)
    return img


def build_composite(user_video: Path, agent_video: Path, out_mp4: Path, duration_s: float, *,
                    user_audio: Path | None = None, agent_audio: Path | None = None,
                    pane_h: int = COMPOSITE_PANE_H) -> Path:
    """Side-by-side composite: USER left / AGENT right (labels burned in), user audio L / agent audio R.

    Both videos are scaled to `pane_h` high (aspect kept), stacked, trimmed/padded (last frame held)
    to `duration_s`. Audio: `user_audio` + `agent_audio` (16 kHz wavs, t=0 aligned with the videos)
    joined to stereo; falls back to the videos' own tracks, or no audio when neither exists.
    """
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    uw, uh = _probe_dims(user_video)
    aw, ah = _probe_dims(agent_video)
    pw_u = max(2, round(uw * pane_h / uh / 2) * 2)
    pw_a = max(2, round(aw * pane_h / ah / 2) * 2)
    labels_png = out_mp4.with_name(out_mp4.stem + "_labels.png")
    label_overlay(pw_u + pw_a, pane_h, pane_w=(pw_u, pw_a)).save(labels_png)

    inputs = ["-i", str(user_video), "-i", str(agent_video), "-i", str(labels_png)]
    ua = user_audio if user_audio and Path(user_audio).exists() else (user_video if _has_audio(user_video) else None)
    aa = agent_audio if agent_audio and Path(agent_audio).exists() else (agent_video if _has_audio(agent_video) else None)
    fc = [
        f"[0:v]scale={pw_u}:{pane_h},setsar=1,tpad=stop_mode=clone:stop_duration={duration_s:.3f}[u]",
        f"[1:v]scale={pw_a}:{pane_h},setsar=1,tpad=stop_mode=clone:stop_duration={duration_s:.3f}[a]",
        "[u][a]hstack=inputs=2[v0]",
        "[v0][2:v]overlay=0:0:format=auto[v]",
    ]
    maps = ["-map", "[v]"]
    if ua is not None or aa is not None:
        idx = 3
        parts = []
        for src in (ua, aa):
            if src is None:
                parts.append("anullsrc=r=16000:cl=mono")
            else:
                inputs += ["-i", str(src)]
                parts.append(f"[{idx}:a]aresample=16000,apad")
                idx += 1
        fc.append(f"{parts[0]}[l];{parts[1]}[r];[l][r]join=inputs=2:channel_layout=stereo[aud]")
        maps += ["-map", "[aud]", "-c:a", "aac", "-b:a", "96k"]
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", *inputs, "-filter_complex", ";".join(fc), *maps,
           "-t", f"{duration_s:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", str(out_mp4)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_mp4


def extract_frames(video: Path, out_dir: Path, duration_s: float, *, fps: float = FPS, max_frames: int = MAX_FRAMES,
                   width: int = FRAME_WIDTH, stamp_labels: bool = True) -> dict:
    """JPEG frames of `video` at `effective_fps(duration, fps, max_frames)`, `width` px wide, into `out_dir`.

    Returns the frames manifest {fps, width, max_frames, duration_s, n, times, files}; also written as
    `out_dir/frames.json`. Labels are re-stamped on the resized frames so they stay legible at 256 px.
    """
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    times = frame_times(duration_s, fps, max_frames)
    eff = effective_fps(duration_s, fps, max_frames)
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(video), "-t", f"{duration_s:.3f}",
           "-vf", f"fps={eff:.6f},scale={width}:-2", "-q:v", str(JPEG_QUALITY), "-start_number", "0",
           str(out_dir / "%05d.jpg")]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    files = sorted(out_dir.glob("*.jpg"))
    for extra in files[len(times):]:                   # fps filter can emit one trailing frame past the plan
        extra.unlink()
    files = files[:len(times)]
    times = times[:len(files)]
    if stamp_labels and files:
        from PIL import Image
        with Image.open(files[0]) as im0:
            w, h = im0.size
        overlay = label_overlay(w, h)
        for f in files:
            with Image.open(f) as im:
                im = im.convert("RGBA")
                im.alpha_composite(overlay)
                im.convert("RGB").save(f, quality=85)
    manifest = {"fps": eff, "nominal_fps": fps, "width": width, "max_frames": max_frames, "duration_s": duration_s,
                "n": len(files), "times": [round(t, 4) for t in times], "files": [f.name for f in files],
                "labels": "burned in (USER left, AGENT right)"}
    (out_dir / "frames.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def resolve_agent_video(sample: Sample, run: AgentRun, clip_dir: Path) -> tuple[Path | None, str]:
    """(agent video path, how it was found) or (None, why not).

    Order: run.json `agent_video_path` (avatar providers write `<clip_dir>/agent.mp4`); the human
    partner's video for `human_gt`; for `random`, the .mp4 next to the partner wav named in run.json meta.
    """
    if run.agent_video_path:
        p = Path(run.agent_video_path)
        for cand in (p, clip_dir / p.name, clip_dir / "agent.mp4"):
            if cand.exists():
                return cand, "run.json agent_video_path"
        return None, f"run.json agent_video_path {run.agent_video_path!r} does not exist"
    if run.provider == "human_gt":
        if sample.partner_video_path and Path(sample.partner_video_path).exists():
            return Path(sample.partner_video_path), "human partner video (sample.partner_video_path)"
        return None, "human_gt row without a partner video"
    if run.provider == "random":
        wav = (run.meta or {}).get("partner_wav")
        if wav:
            mp4 = Path(wav).with_suffix(".mp4")
            if mp4.exists():
                return mp4, "random partner video (run.json meta partner_wav -> .mp4)"
            return None, f"random partner video missing next to {wav!r}"
        return None, "random row without partner_wav in run.json meta"
    return None, f"provider {run.provider!r} produced no agent video (audio-only run)"


def prepare_frames(sample: Sample, run: AgentRun, clip_dir: Path, gen_dir: Path, *, fps: float = FPS,
                   max_frames: int = MAX_FRAMES, width: int = FRAME_WIDTH, force: bool = False) -> dict:
    """Composite + frames for one row, cached under `gen_dir` (`sbs.mp4`, `frames/`). Returns the frames manifest
    with `dir` and `source` added. GenerationJudgeError when the row has no agent video."""
    agent_video, how = resolve_agent_video(sample, run, clip_dir)
    if agent_video is None:
        raise GenerationJudgeError(how)
    user_video = Path(sample.user_video_path)
    if not user_video.exists():
        raise GenerationJudgeError(f"user video missing: {user_video}")
    gen_dir = Path(gen_dir)
    sbs = gen_dir / "sbs.mp4"
    if force or not sbs.exists():
        agent_wav = Path(run.agent_audio_path) if run.agent_audio_path else clip_dir / "agent.wav"
        if not agent_wav.exists():
            agent_wav = clip_dir / "agent.wav"
        build_composite(user_video, agent_video, sbs, sample.duration_s,
                        user_audio=Path(sample.user_audio_path), agent_audio=agent_wav)
    frames_dir = gen_dir / "frames"
    fj = frames_dir / "frames.json"
    manifest = None
    if not force and fj.exists():
        try:
            m = json.loads(fj.read_text(encoding="utf-8"))
            same = (abs(m.get("nominal_fps", 0) - fps) < 1e-9 and m.get("max_frames") == max_frames
                    and m.get("width") == width and abs(m.get("duration_s", -1) - sample.duration_s) < 1e-6)
            if same and m.get("n") and all((frames_dir / f).exists() for f in m["files"]):
                manifest = m
        except (json.JSONDecodeError, OSError):
            manifest = None
    if manifest is None:
        manifest = extract_frames(sbs, frames_dir, sample.duration_s, fps=fps, max_frames=max_frames, width=width)
    manifest = dict(manifest)
    manifest.update(dir=str(frames_dir), composite=str(sbs), source=how, agent_video=str(agent_video))
    return manifest


def frame_paths(manifest: dict) -> list[Path]:
    d = Path(manifest["dir"])
    return [d / f for f in manifest["files"]]


def frames_digest(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(Path(p).read_bytes())
        h.update(b"\x00")
    return h.hexdigest()


# --- text block (F.6.1) ----------------------------------------------------------------------

def _fmt_seg(s: Segment | dict) -> tuple[float, float]:
    if isinstance(s, dict):
        return float(s["start"]), float(s["end"])
    return float(s.start), float(s.end)


def _ov(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def substantive_user_segments(sample: Sample, gap: float = J.USER_CHUNK_GAP_S) -> list[Segment]:
    """User utterance chunks that are turns rather than backchannels (>= 3 words or >= 1.0 s)."""
    return [s for s in words_to_segments(sample.user_words, gap=gap)
            if s.n_words >= SUBSTANTIVE_MIN_WORDS or s.dur >= SUBSTANTIVE_MIN_S]


def overlap_signal(user_segs: list[Segment], agent_segs: list[Segment | dict],
                   thresholds: tuple[float, ...] = OVERLAP_THRESHOLDS_S) -> dict:
    """Agent-over-user overlap during substantive user speech: total seconds and event counts per threshold.

    One event = one agent segment's total overlap with substantive user speech.
    """
    events: list[float] = []
    for a in agent_segs:
        a0, a1 = _fmt_seg(a)
        ov = sum(_ov(a0, a1, u.start, u.end) for u in user_segs)
        if ov > 0:
            events.append(ov)
    return {
        "n_user_turns": len(user_segs),
        "total_s": round(sum(events), 2),
        "n_events": len(events),
        "max_event_s": round(max(events), 2) if events else 0.0,
        "events_over": {f"{t:g}": sum(1 for e in events if e > t) for t in thresholds},
    }


def overlap_line(sig: dict) -> str:
    over = sig["events_over"]
    counts = "; ".join(f"{n} events > {t}s" for t, n in over.items())
    return (f"Agent--user overlap: {sig['n_user_turns']} substantive user turns; total {sig['total_s']:.2f}s; "
            f"{counts}. (Sub-1s overlaps are normal turn-junction behavior.)")


def _list_segments(segs: list[tuple[float, float]], ds: float, de: float, kind: str) -> str:
    if not segs:
        return "none"
    shown = segs[:MAX_LISTED_SEGMENTS]
    parts = []
    for a, b in shown:
        if kind == "pre":
            parts.append(f"[{a:.2f}-{b:.2f}s] ({ds - b:.2f}s pre)")
        else:
            parts.append(f"[{a:.2f}-{b:.2f}s] (+{a - de:.2f}s post)")
    if len(segs) > len(shown):
        parts.append(f"... and {len(segs) - len(shown)} more")
    return ", ".join(parts)


def audio_ground_truth_block(sample: Sample, timing_json: dict) -> str:
    """'Agent audio-side ground truth' lines of F.6.1: window, in/pre/post-window agent audio."""
    ds, de = sample.dynamic_start_s, sample.dynamic_end_s
    segs = sorted((_fmt_seg(s) for s in timing_json.get("segments") or []), key=lambda x: x)
    in_win = [(a, b) for a, b in segs if _ov(a, b, ds, de) > 0]
    pre = [(a, b) for a, b in segs if b <= ds]
    post = [(a, b) for a, b in segs if a >= de]
    lines = ["Agent audio-side ground truth:", f"Dynamic window: {ds:.2f}-{de:.2f}s"]
    if in_win:
        spans = ", ".join(f"[{a:.2f}-{b:.2f}s] ({_ov(a, b, ds, de):.2f}s in window)" for a, b in in_win)
        lines.append(f"Agent audio overlapping the dynamic window: {spans}")
    else:
        lines.append("Agent was SILENT during the dynamic window --- no segments overlap.")
    lines.append(f"Pre-window agent audio: {_list_segments(pre, ds, de, 'pre')}")
    lines.append(f"Post-window agent audio: {_list_segments(post, ds, de, 'post')}")
    return "\n".join(lines)


def format_segment_list(timing_json: dict) -> str:
    segs = [_fmt_seg(s) for s in timing_json.get("segments") or []]
    if not segs:
        return "none (agent produced no audible speech)"
    return ", ".join(f"[{a:.2f}-{b:.2f}s]" for a, b in sorted(segs))


def frames_line(plan: dict | None) -> str | None:
    if not plan or not plan.get("n"):
        return None
    n, fps = int(plan["n"]), float(plan["fps"])
    last = (n - 1) / fps if fps > 0 else 0.0
    return (f"Frames: {n} JPEG frames sampled uniformly at {fps:.2f} fps from t=0.00s to t={last:.2f}s, in order; "
            f"frame k (0-based) shows t = k / {fps:.2f} s.")


def build_user_text(sample: Sample, timing_json: dict, plan: dict | None = None) -> str:
    """The F.6.1 text block (payload v1). `plan` is the frames manifest (None = text-only preview).

    Lines marked + are OpenVideoFDB additions: frame timing, the annotated user cue, the per-segment
    agent transcript. The agent visual / audio captions are `[not available]` (see module docstring).
    """
    ds, de = sample.dynamic_start_s, sample.dynamic_end_s
    lines = [FRAMING_NOTE]
    fl = frames_line(plan)                                           # +
    if fl:
        lines.append(fl)
    lines += [
        f"Category: {sample.dynamic_type.value}",
        f"Dynamic event (user stimulus): t={ds:.2f}s to t={de:.2f}s",
        f"Clip duration: {sample.duration_s:.2f}s",
    ]
    cue = J.cue_line(sample)                                         # +
    if cue:
        lines.append(cue)
    caption = (sample.av_caption or "").strip() or J.NO_CAPTION
    lines += [
        "USER STIMULUS (for context only --- do not grade this):",
        ("User AV caption (covers the full clip including the dynamic event; its USER/PARTNER speech attribution "
         "can be swapped --- take who-said-what from the transcripts):"),
        J._quoted(caption),
        "User speech (with timestamps):",
        J._quoted(J.format_user_speech(sample)),
        "=== AGENT OUTPUT --- GRADE THIS ===",
        audio_ground_truth_block(sample, timing_json),
        overlap_line(overlap_signal(substantive_user_segments(sample), timing_json.get("segments") or [])),
        f"Agent visual caption: {VISUAL_CAPTION_NA}",
        f"Agent audio caption: {AUDIO_CAPTION_NA}",
        f"Agent speech segments: {format_segment_list(timing_json)}",
    ]
    agent_ts = J.format_agent_speech(timing_json)                    # +
    if agent_ts is not None:
        lines += ["Agent speech (with timestamps; wordless voice activity is marked):", J._quoted(agent_ts)]
    transcript = (timing_json.get("transcript") or "").strip() or J.NO_SPEECH
    lines += [
        "Agent speech transcript:",
        J._quoted(transcript),
        ("Use the right half of each frame (and right-channel audio) to grade the agent on the 0-5 scale per the "
         "rubric above."),
    ]
    return "\n".join(lines)


# --- multimodal message assembly + backends -----------------------------------------------------

def _b64(path: Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def openai_content(frames: list[Path], text: str, detail: str = "low") -> list[dict]:
    return [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_b64(p)}", "detail": detail}}
            for p in frames] + [{"type": "text", "text": text}]


def anthropic_content(frames: list[Path], text: str) -> list[dict]:
    return [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _b64(p)}}
            for p in frames] + [{"type": "text", "text": text}]


def google_contents(frames: list[Path], text: str) -> list:
    from google.genai import types
    return [types.Part.from_bytes(data=Path(p).read_bytes(), mime_type="image/jpeg") for p in frames] + [text]


def frames_for_backend(frames: list[Path], judge: str) -> list[Path]:
    """Thin the frame list uniformly to the backend's per-request image limit (no-op for gpt/gemini)."""
    limit = BACKEND_MAX_IMAGES.get(J.backend_for(judge))
    if limit is None or len(frames) <= limit:
        return list(frames)
    return [frames[i] for i in thin_indices(len(frames), limit)]


def _call(judge: str, system: str, text: str, frames: list[Path]) -> tuple[str, dict]:
    """One vision judge call: frames as image blocks then the text block. Returns (raw text, usage)."""
    backend = J.backend_for(judge)
    client = J._client(backend, judge)
    if backend == "openai":
        r = client.chat.completions.create(
            model=judge, temperature=0, response_format={"type": "json_object"}, max_tokens=MAX_OUTPUT_TOKENS,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": openai_content(frames, text)}],
        )
        u = r.usage
        return (r.choices[0].message.content or "",
                {"prompt_tokens": getattr(u, "prompt_tokens", 0), "completion_tokens": getattr(u, "completion_tokens", 0)})
    if backend == "anthropic":
        r = client.messages.create(
            model=judge, max_tokens=MAX_OUTPUT_TOKENS, temperature=0, system=system,
            messages=[{"role": "user", "content": anthropic_content(frames, text)}],
        )
        return ("".join(getattr(b, "text", "") for b in r.content),
                {"prompt_tokens": r.usage.input_tokens, "completion_tokens": r.usage.output_tokens})
    if backend == "google":
        from google.genai import types
        r = client.models.generate_content(
            model=judge, contents=google_contents(frames, text),
            config=types.GenerateContentConfig(system_instruction=system, temperature=0,
                                               response_mime_type="application/json",
                                               max_output_tokens=MAX_OUTPUT_TOKENS),
        )
        um = getattr(r, "usage_metadata", None)
        return (r.text or "", {"prompt_tokens": getattr(um, "prompt_token_count", 0) or 0,
                               "completion_tokens": getattr(um, "candidates_token_count", 0) or 0})
    raise J.JudgeUnavailable(backend)  # pragma: no cover


# --- parsing + consistency ------------------------------------------------------------------------

def _json_object(raw: str) -> dict:
    text = raw.strip()
    m = J._FENCE.match(text)
    if m:
        text = m.group(1)
    obj = None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        if a != -1 and b > a:
            try:
                obj = json.loads(text[a:b + 1])
            except json.JSONDecodeError:
                obj = None
    if not isinstance(obj, dict):
        raise J.JudgeParseError(f"not a JSON object: {raw[:200]!r}")
    return obj


def _int_in(obj: dict, key: str, lo: int, hi: int) -> int:
    if key not in obj:
        raise J.JudgeParseError(f"missing {key!r}")
    v = obj[key]
    try:
        if isinstance(v, str):
            v = float(v.strip())
        if isinstance(v, bool) or float(v) != int(float(v)):
            raise ValueError
        v = int(float(v))
    except (TypeError, ValueError):
        raise J.JudgeParseError(f"{key} not an integer: {obj[key]!r}") from None
    if not lo <= v <= hi:
        raise J.JudgeParseError(f"{key} out of range {lo}-{hi}: {v}")
    return v


def parse_decomposed(raw: str) -> dict:
    """Parse the F.3 decomposed schema (no consistency enforcement; see `enforce_consistency`)."""
    obj = _json_object(raw)
    timing = str(obj.get("cue_timing", "")).strip().lower()
    if timing not in TIMING_VALUES:
        raise J.JudgeParseError(f"cue_timing not one of {TIMING_VALUES}: {obj.get('cue_timing')!r}")
    return {
        "analysis": str(obj.get("analysis", "")),
        "cue_produced": _int_in(obj, "cue_produced", 0, 1),
        "cue_timing": timing,
        "cue_appropriateness": _int_in(obj, "cue_appropriateness", 0, 5),
        "reasoning": str(obj.get("reasoning", "")),
    }


def enforce_consistency(d: dict) -> tuple[dict, list[str]]:
    """F.3 post-hoc rules. Returns (consistent copy, list of fixes applied).

    - cue_produced=0 -> cue_timing="absent", cue_appropriateness=0.
    - cue_produced=1 with cue_timing="absent": the judge contradicted itself; with
      cue_appropriateness=0 the cue is treated as not produced, otherwise the timing becomes "late"
      (produced, but not in the window --- the conservative reading).
    """
    out = dict(d)
    fixes: list[str] = []
    if out["cue_produced"] == 0:
        if out["cue_timing"] != "absent":
            fixes.append(f"cue_produced=0: cue_timing {out['cue_timing']!r} -> 'absent'")
            out["cue_timing"] = "absent"
        if out["cue_appropriateness"] != 0:
            fixes.append(f"cue_produced=0: cue_appropriateness {out['cue_appropriateness']} -> 0")
            out["cue_appropriateness"] = 0
    elif out["cue_timing"] == "absent":
        if out["cue_appropriateness"] == 0:
            fixes.append("cue_produced=1 with timing 'absent' and appropriateness 0: cue_produced -> 0")
            out["cue_produced"] = 0
        else:
            fixes.append("cue_produced=1 with timing 'absent': cue_timing -> 'late'")
            out["cue_timing"] = "late"
    return out, fixes


# --- scoring ----------------------------------------------------------------------------------------

def cache_key(system: str, text: str, judge: str, frames_sha: str) -> str:
    h = hashlib.sha256()
    for part in (system, text, judge, frames_sha, f"v{PAYLOAD_VERSION}"):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _load_cached(path: Path, key: str) -> GenJudgeResult | None:
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if d.get("key") != key:
        return None
    known = GenJudgeResult.__dataclass_fields__
    r = GenJudgeResult(**{k: v for k, v in d.items() if k in known})
    r.cached = True
    return r


def score_axis(sample: Sample, timing_json: dict, axis: Axis | str, frames_manifest: dict, judge: str = DEFAULT_JUDGE, *,
               cache_dir: str | Path | None = None, force: bool = False) -> GenJudgeResult:
    """Judge one generation axis of one row. One retry on an unparseable reply; JudgeParseError after that."""
    axis = Axis(axis)
    if axis not in GENERATION_AXES:
        raise ValueError(f"{axis.value} is a perception axis; use judge.score_axis")
    system = build_system_prompt(axis, sample)
    text = build_user_text(sample, timing_json, frames_manifest)
    frames = frames_for_backend(frame_paths(frames_manifest), judge)
    fsha = frames_digest(frames)
    key = cache_key(system, text, judge, fsha)
    path = J.cache_file(Path(cache_dir), axis, judge) if cache_dir is not None else None
    if path is not None and not force:
        hit = _load_cached(path, key)
        if hit is not None:
            return hit

    usage = {"prompt_tokens": 0, "completion_tokens": 0, "n_calls": 0}
    decomposed = is_decomposed(axis)
    last_err: J.JudgeParseError | None = None
    raw, parsed = "", None
    for attempt in range(2):
        prompt = text if attempt == 0 else text + "\n\nReturn ONLY the JSON object described in the system prompt."
        raw, u = _call(judge, system, prompt, frames)
        usage["prompt_tokens"] += int(u.get("prompt_tokens", 0) or 0)
        usage["completion_tokens"] += int(u.get("completion_tokens", 0) or 0)
        usage["n_calls"] += 1
        try:
            parsed = parse_decomposed(raw) if decomposed else J.parse_response(raw)
            break
        except J.JudgeParseError as e:
            last_err = e
            log.warning("gen judge %s/%s: unparseable reply on attempt %d: %s", judge, axis.value, attempt + 1, e)
    if parsed is None:
        raise J.JudgeParseError(f"{judge}/{axis.value} on {sample.clip_id}: {last_err}")

    fixes: list[str] = []
    if decomposed:
        parsed, fixes = enforce_consistency(parsed)
        if fixes:
            log.info("%s/%s: consistency fixes %s", sample.clip_id, axis.value, fixes)
    result = GenJudgeResult(
        axis=axis.value, judge=judge,
        rating=parsed["cue_appropriateness"] if decomposed else parsed["rating"],
        analysis=parsed["analysis"], reasoning=parsed["reasoning"], raw=raw,
        rubric=rubric_name(axis, sample.dynamic_type), usage=usage, cached=False, key=key,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        cue_produced=parsed["cue_produced"] if decomposed else None,
        cue_timing=parsed["cue_timing"] if decomposed else None,
        consistency_fixes=fixes, n_frames=len(frames), frames_sha256=fsha,
    )
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        d = result.to_dict()
        d.update(clip_id=sample.clip_id, dynamic_type=sample.dynamic_type.value, bucket=sample.bucket.value,
                 payload_version=PAYLOAD_VERSION, system_sha256=hashlib.sha256(system.encode()).hexdigest(),
                 user_text=text, frames_dir=frames_manifest.get("dir"), frame_width=frames_manifest.get("width"),
                 frame_fps=frames_manifest.get("fps"))
        path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def score_sample(sample: Sample, timing_json: dict, frames_manifest: dict, judge: str = DEFAULT_JUDGE, *,
                 axes=None, cache_dir: str | Path | None = None, force: bool = False) -> dict[str, GenJudgeResult]:
    """Judge every generation axis of `sample` (or the subset `axes`). Returns {axis_value: GenJudgeResult}."""
    if sample.bucket is not Bucket.GENERATION:
        log.warning("%s: bucket %s is not judged by the generation judge; skipping", sample.clip_id, sample.bucket.value)
        return {}
    wanted = sample.axes if axes is None else tuple(Axis(a) for a in axes)
    out: dict[str, GenJudgeResult] = {}
    for axis in wanted:
        if axis not in GENERATION_AXES:
            log.info("%s: axis %s is a perception axis; skipped", sample.clip_id, axis.value)
            continue
        if axis not in sample.axes:
            log.info("%s: axis %s does not apply to %s; skipped", sample.clip_id, axis.value, sample.dynamic_type.value)
            continue
        out[axis.value] = score_axis(sample, timing_json, axis, frames_manifest, judge, cache_dir=cache_dir, force=force)
    return out


def estimate_cost_usd(usage: dict, judge: str) -> float | None:
    """Indicative USD cost (image tokens are counted in prompt_tokens by all three backends)."""
    return J.estimate_cost_usd(usage, judge)
