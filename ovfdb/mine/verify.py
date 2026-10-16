"""VLM verification of mined candidates with gemini-2.5-flash (plans/WS2-mining.md).

For each trimmed clip we build a side-by-side 480p composite (USER left,
PARTNER right, both audio tracks mixed) and ask the model whether the clip
shows the dynamic inside the candidate window. Decisions are appended to
``data/mining/verify.jsonl`` and cached by ``(clip_id, dynamic, bucket)``.

Keep rule: ``is_dynamic and confidence >= 0.7``. The model's refined window
replaces the rule window when both ends move by < 1.5 s and it does not
collapse (>= 0.5 s and >= half the rule window; the model tends to answer
with point events).
"""

from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from ovfdb.mine import gemini as G
from ovfdb.schema import Bucket, DynamicType

VERIFY_LOG = Path("data/mining/verify.jsonl")
MIN_CONFIDENCE = 0.7
MAX_WINDOW_SHIFT = 1.5
MIN_WINDOW_S = 0.5        # never let a refinement collapse the window (the model likes point events)
SBS_HEIGHT = 480
_lock = threading.Lock()

#: docs/protocol.md §1 (paper Table 2): what the user does / expected agent behaviour.
DEFINITIONS: dict[DynamicType, tuple[str, str]] = {
    DynamicType.PAUSE_HANDLING: ("pauses mid-thought but keeps the floor (not finished speaking)",
                                 "stay silent and let the user continue"),
    DynamicType.GAZE_AVOIDANCE_WITH_PAUSE: ("looks away while pausing (a thinking cue)", "read it as thinking, stay silent"),
    DynamicType.ADAPTOR_HANDLING: ("makes a self-directed gesture (scratch, hair, fidget)", "ignore it; no reaction"),
    DynamicType.NONVERBAL_INTERRUPTION: ("raises a hand / shakes head / signals 'stop' while the agent speaks",
                                         "yield within ~1-1.5 s"),
    DynamicType.FACE_EMOTION_DISPLAY: ("shows a visible facial expression", "respond with congruent affect"),
    DynamicType.NONVERBAL_BACKCHANNELING: ("nods / smiles while the agent speaks", "keep talking (P) / nod-smile-'mhm' (G)"),
    DynamicType.LAUGHTER: ("laughs at the partner's words (P) or laughs while speaking and the partner reacts (G)",
                           "warm continuation (P) / laugh back in the window (G)"),
    DynamicType.EMOTION_MATCHING: ("shows affect", "agent's combined audio-visual response matches"),
    DynamicType.VERBAL_BACKCHANNELING: ("is speaking a longer turn",
                                        ("emit at least one short verbal acknowledgement (< 1 s, < 2 words, e.g. 'mhm', 'yeah') "
                                        "without taking the floor")),
    DynamicType.VERBAL_INTERRUPTION: ("interrupts the partner verbally while the partner is mid-sentence",
                                      "halt within ~1.5 s and stay yielded while the user holds the floor"),
    DynamicType.TURN_TAKING: ("finishes a turn and offers the floor (clear completion, often a question)",
                              "start speaking within the handoff window; no talk-over"),
}

#: What our rule expects the human partner (= GT agent) to be doing, so the VLM checks both sides.
PARTNER_EXPECTATION: dict[tuple[DynamicType, Bucket], str] = {
    (DynamicType.PAUSE_HANDLING, Bucket.PERCEPTION):
        "the PARTNER stays silent during the pause and the USER resumes the same thought afterwards",
    (DynamicType.VERBAL_BACKCHANNELING, Bucket.GENERATION):
        "the PARTNER produces a short verbal backchannel ('mhm', 'yeah', 'right') inside the window while the USER keeps talking; "
        "a cough, breath or laugh does not count",
    (DynamicType.VERBAL_INTERRUPTION, Bucket.GENERATION):
        "the PARTNER is mid-sentence when the USER starts talking over them with real content (not a backchannel), "
        "and the PARTNER stops and lets the USER continue",
    (DynamicType.TURN_TAKING, Bucket.GENERATION):
        "the USER clearly finishes and yields; the PARTNER starts a real reply at the end of the window without overlap",
    (DynamicType.LAUGHTER, Bucket.PERCEPTION):
        "the USER audibly/visibly laughs in the window in reaction to what the PARTNER just said",
    (DynamicType.LAUGHTER, Bucket.GENERATION):
        "the USER laughs during their own turn and the PARTNER reacts (laughs or smiles back) within ~2 s",
    # --- day 2: nonverbal dynamics (docs/protocol.md §1; paper App. C.2 timing classes)
    (DynamicType.NONVERBAL_BACKCHANNELING, Bucket.PERCEPTION):
        "the PARTNER is mid-turn (talking before, during and after the window) and the USER, who is listening, "
        "visibly nods / smiles / raises eyebrows inside the window as listener feedback WITHOUT taking the floor "
        "(at most a short 'mhm'); the PARTNER keeps talking. A nod while the USER is the one speaking does not count",
    (DynamicType.NONVERBAL_BACKCHANNELING, Bucket.GENERATION):
        "the USER is mid-turn and the PARTNER, listening, visibly nods / smiles / raises eyebrows inside the window "
        "(optionally with a short 'mhm') without taking the floor; the USER keeps talking",
    (DynamicType.FACE_EMOTION_DISPLAY, Bucket.PERCEPTION):
        "the USER shows a clearly visible facial expression with affect (smile, grin, grimace, frown, surprise, concern) "
        "inside the window, and the PARTNER then replies in an affectively congruent way (warm reply to a smile, "
        "concern to a frown) within a few seconds; a neutral face or a mere mouth movement while talking does not count",
    (DynamicType.FACE_EMOTION_DISPLAY, Bucket.GENERATION):
        "the USER shows a clearly visible facial expression with affect inside the window and the PARTNER visibly "
        "mirrors it in face and/or voice (smiles back, nods warmly, shows concern) starting within ~2.5 s of the "
        "USER's expression; the clip is useless if the PARTNER's face stays neutral",
    (DynamicType.EMOTION_MATCHING, Bucket.GENERATION):
        "the USER shows affect (smile/laugh = positive, frown/grimace/concern = negative) at the start of the window "
        "and the PARTNER's face and/or voice take on the SAME affect within ~2 s, still inside the window; "
        "the PARTNER merely continuing to listen neutrally is NOT a match",
    (DynamicType.GAZE_AVOIDANCE_WITH_PAUSE, Bucket.PERCEPTION):
        "the USER pauses mid-thought (not finished speaking) AND looks away from the PARTNER (up, down or sideways) "
        "during the pause as a thinking cue, then resumes the same thought; the PARTNER stays silent through the pause "
        "(a short backchannel is fine). A pause with the USER still looking at the PARTNER is Pause Handling, not this",
    (DynamicType.ADAPTOR_HANDLING, Bucket.PERCEPTION):
        "the USER makes a self-directed, non-communicative gesture inside the window (scratches, rubs face/head/neck, "
        "adjusts hair or glasses, fidgets with clothing) that carries no conversational meaning; the PARTNER does not "
        "react to it and, if the PARTNER was talking, keeps talking. Hand gestures that illustrate speech, pointing "
        "or waving do NOT count",
    (DynamicType.NONVERBAL_INTERRUPTION, Bucket.PERCEPTION):
        "the PARTNER is mid-sentence when the USER, still silent, makes a visible interruption gesture at the start of "
        "the window (raised hand / palm, head shake, 'stop' / 'wait' gesture, leaning in with a pointed finger); the "
        "PARTNER then stops talking within ~1.5 s and the USER takes the floor. A nod, smile or a gesture made while "
        "the USER is already talking does NOT count",
}


@dataclass
class Verdict:
    clip_id: str
    dynamic_type: str
    bucket: str
    is_dynamic: bool
    confidence: float
    start_s: float | None
    end_s: float | None
    notes: str
    accepted: bool
    ds: float
    de: float
    refined: bool
    usage: dict
    cached: bool = False


def sbs_composite(user_mp4: Path | str, partner_mp4: Path | str, out: Path | str, height: int = SBS_HEIGHT) -> Path:
    """USER left | PARTNER right at ``height`` px, both audio tracks mixed. Idempotent."""
    out = Path(out)
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    fc = (f"[0:v]scale=-2:{height},setsar=1[l];[1:v]scale=-2:{height},setsar=1[r];"
          f"[l][r]hstack=inputs=2[v];[0:a][1:a]amix=inputs=2:duration=longest:normalize=0[a]")
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(user_mp4), "-i", str(partner_mp4),
           "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(out)]
    p = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg sbs failed: {p.stderr[-1500:]}")
    return out


def build_prompt(dynamic: DynamicType, bucket: Bucket, ds: float, de: float, dur: float, evidence: dict | None = None) -> str:
    user_does, agent_should = DEFINITIONS[dynamic]
    expect = PARTNER_EXPECTATION.get((dynamic, bucket), "")
    ev = ""
    if evidence:
        keep = {k: v for k, v in evidence.items() if k in ("text_before", "text_after", "backchannel_text", "a_text",
                                                           "b_text", "b_text_before", "gap_s", "handoff_gap_s", "b_stop_s",
                                                           "event", "partner_event", "mode", "lag_s", "mirror_lag_s")}
        for k in ("event", "partner_event"):
            if isinstance(keep.get(k), dict):   # event times are raw-file seconds; show the kind + note only
                keep[k] = {kk: vv for kk, vv in keep[k].items() if kk in ("kind", "note", "source")}
        if keep:
            ev = "Rule evidence from VAD/ASR (may be wrong): " + json.dumps(keep, ensure_ascii=False) + "\n"
    return (
        "You are verifying a candidate clip for a benchmark of conversational dynamics.\n"
        "The video is a side-by-side composite of a face-to-face conversation: LEFT pane = USER, RIGHT pane = PARTNER. "
        "Both voices are mixed into one audio track; use lip movement to tell who speaks.\n\n"
        f"Dynamic: {dynamic.value} ({bucket.value} bucket)\n"
        f"Definition: the USER {user_does}; the expected agent behaviour is to {agent_should}.\n"
        f"What a positive example must show here: {expect}\n"
        f"Candidate window: {ds:.2f} s to {de:.2f} s (clip is {dur:.1f} s long, timestamps from the clip start).\n"
        f"{ev}\n"
        "Watch the whole clip. Decide whether the window really contains this dynamic, performed by the USER (left) "
        "with the PARTNER (right) behaving as described. Be strict: reject if the roles are swapped, if the event is "
        "absent or ambiguous, or if the event clearly lies outside the window. If the event is present but the window "
        "is slightly off, give a corrected start_s/end_s.\n"
        'Return JSON: {"is_dynamic": bool, "confidence": number 0-1, "start_s": number, "end_s": number, '
        '"notes": "one or two sentences citing what you saw/heard with timestamps"}'
    )


def _cache_key(clip_id: str, dynamic: DynamicType, bucket: Bucket) -> str:
    return f"{clip_id}|{dynamic.value}|{bucket.value}"


def load_cache(log: Path = VERIFY_LOG) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if log.exists():
        for line in log.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                out[_cache_key(d["clip_id"], DynamicType(d["dynamic_type"]), Bucket(d["bucket"]))] = d
    return out


def _append(log: Path, d: dict) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with _lock, log.open("a") as f:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")


def verify(clip_id: str, sbs_mp4: Path | str, dynamic: DynamicType, bucket: Bucket, ds: float, de: float,
           dur: float, evidence: dict | None = None, log: Path = VERIFY_LOG, cache: dict | None = None,
           min_conf: float = MIN_CONFIDENCE, window: tuple[float, float] | None = None) -> Verdict:
    """Ask the VLM; log and return the decision. ``cache`` (from ``load_cache``) skips repeat calls
    for the same clip id, unless the logged raw window ``(t0, t1)`` differs from ``window``."""
    key = _cache_key(clip_id, dynamic, bucket)
    cache = cache if cache is not None else load_cache(log)
    if key in cache:
        d = cache[key]
        same = window is None or "t0" not in d or (abs(d["t0"] - window[0]) < 0.05 and abs(d["t1"] - window[1]) < 0.05)
        if same:
            return Verdict(**{k: d.get(k) for k in Verdict.__dataclass_fields__ if k != "cached"}, cached=True)

    out, usage = G.generate(build_prompt(dynamic, bucket, ds, de, dur, evidence), Path(sbs_mp4), mime="video/mp4")
    out = out if isinstance(out, dict) else {}
    is_dyn = bool(out.get("is_dynamic", False))
    try:
        conf = float(out.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    s, e = out.get("start_s"), out.get("end_s")
    try:
        s = None if s is None else float(s)
        e = None if e is None else float(e)
    except (TypeError, ValueError):
        s = e = None
    refined = False
    nds, nde = ds, de
    if s is not None and e is not None and e > s and abs(s - ds) < MAX_WINDOW_SHIFT and abs(e - de) < MAX_WINDOW_SHIFT \
            and (abs(s - ds) > 0.05 or abs(e - de) > 0.05) and (e - s) >= max(MIN_WINDOW_S, 0.5 * (de - ds)):
        nds, nde, refined = round(max(0.0, s), 3), round(min(dur, e), 3), True
    v = Verdict(clip_id=clip_id, dynamic_type=dynamic.value, bucket=bucket.value, is_dynamic=is_dyn, confidence=conf,
                start_s=s, end_s=e, notes=str(out.get("notes", ""))[:600], accepted=is_dyn and conf >= min_conf,
                ds=nds, de=nde, refined=refined, usage=usage)
    d = {k: getattr(v, k) for k in Verdict.__dataclass_fields__ if k != "cached"}
    d["rule_ds"], d["rule_de"] = ds, de
    if window is not None:
        d["t0"], d["t1"] = float(window[0]), float(window[1])
    _append(log, d)
    cache[key] = d
    return v
