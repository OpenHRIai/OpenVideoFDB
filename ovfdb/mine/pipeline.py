"""WS2 mining pipeline: Seamless pairs -> candidates -> clips -> VLM verify -> prompts -> manifest.

``run()`` is what ``ovfdb mine`` calls. Flow per run:

1. Scan the first ``scan`` consistent pairs' VAD + transcripts (tiny files)
   and run the dialogue finders; rank pairs by how many still-needed
   dynamics they cover so few 430 MB media pairs get downloaded.
2. For each pair in that order: pick <= ``per_pair`` candidates per
   (dynamic, bucket) (best rule score, distinct windows), detect laughter
   on the audio tracks if Laughter is wanted, trim clips (``to_sample``),
   build the SBS composite, verify with Gemini, generate the system prompt
   + AV caption for accepted clips, and append them to the manifest.
3. Stop when every wanted (dynamic, bucket) has ``limit`` clips in the
   manifest or pairs run out. Clip ids already in the manifest are skipped.

Media for rejected candidates is deleted (the SBS composite is kept under
``data/mining/rejected/`` for the review page).
"""

from __future__ import annotations

import logging
import shutil
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from ovfdb.data import seamless as sm
from ovfdb.mine import clip as C
from ovfdb.mine import dialogue as D
from ovfdb.mine import nonverbal as NV
from ovfdb.mine import verify as V
from ovfdb.schema import Bucket, DynamicType, Sample, read_manifest, write_manifest

log = logging.getLogger("ovfdb.mine")

DAY1_DYNAMICS = tuple(D.FINDERS)
DAY2_DYNAMICS = tuple(NV.FINDERS)      # nonverbal (movement features + 3P-V + Gemini event pass)
CLIP_ROOT = Path("data/clips")
REJECTED_DIR = Path("data/mining/rejected")
SCAN_DEFAULT = 60
MIN_WINDOW_SEP = 4.0      # two candidates of the same dynamic in one pair must be this far apart


def parse_dynamics(spec: str) -> list[DynamicType]:
    """'all' = the day-1 dialogue dynamics, 'nonverbal' = the day-2 ones, 'everything' = both,
    otherwise a comma list of enum names (pause_handling) or values ("Pause Handling")."""
    if spec in ("", "all"):
        return list(DAY1_DYNAMICS)
    if spec == "nonverbal":
        return list(DAY2_DYNAMICS)
    if spec == "everything":
        return list(DAY1_DYNAMICS) + list(DAY2_DYNAMICS)
    out = []
    for name in spec.split(","):
        key = name.strip().upper().replace("-", "_").replace(" ", "_")
        try:
            out.append(DynamicType[key])
        except KeyError:
            try:
                out.append(DynamicType(name.strip()))
            except ValueError as e:
                raise ValueError(f"unknown dynamic {name!r}; use e.g. pause_handling") from e
    return out


@dataclass
class PairData:
    a: str
    b: str
    vad: dict[str, list]
    utts: dict[str, list]
    cands: list[D.Candidate] = field(default_factory=list)
    anns: dict[str, list] = field(default_factory=dict)     # 3P-V annotations per file (may be empty)
    events: dict[str, list] | None = None                   # nonverbal events per file, once computed

    def frame(self, user_role: str) -> tuple[str, str]:
        return (self.a, self.b) if user_role == "a" else (self.b, self.a)


def load_pair(a: str, b: str, with_3p: bool = False) -> PairData | None:
    kinds = ("vad", "transcript", "3P-V") if with_3p else ("vad", "transcript")
    ga, gb = sm.fetch(a, kinds), sm.fetch(b, kinds)
    if any(k not in g for g in (ga, gb) for k in ("vad", "transcript")):
        return None
    if not sm.pair_is_consistent(a, b):
        return None
    anns = {fid: sm.read_annotations(g["3P-V"]) for fid, g in ((a, ga), (b, gb)) if "3P-V" in g}
    return PairData(a, b,
                    {a: sm.read_vad(ga["vad"]), b: sm.read_vad(gb["vad"])},
                    {a: sm.read_transcript(ga["transcript"]), b: sm.read_transcript(gb["transcript"])},
                    anns=anns)


def select_candidates(cands: list[D.Candidate], need: dict[tuple[DynamicType, Bucket], int],
                      per_pair: int) -> list[D.Candidate]:
    """Best-scoring candidates per (dynamic, bucket), at most ``per_pair`` and
    ``need`` each, with windows >= MIN_WINDOW_SEP apart (pure)."""
    chosen: list[D.Candidate] = []
    by_key: dict[tuple[DynamicType, Bucket], list[D.Candidate]] = defaultdict(list)
    for c in cands:
        by_key[(c.dynamic_type, c.bucket)].append(c)
    for key, group in by_key.items():
        quota = min(per_pair, need.get(key, 0))
        if quota <= 0:
            continue
        taken: list[D.Candidate] = []
        for c in sorted(group, key=lambda c: -c.evidence.get("score", 0.0)):
            if any(t.user_role == c.user_role and abs(t.ds_raw - c.ds_raw) < MIN_WINDOW_SEP for t in taken):
                continue
            taken.append(c)
            if len(taken) >= quota:
                break
        chosen.extend(taken)
    return chosen


def _existing_index_map(samples: list[Sample], verify_cache: dict) -> dict[tuple[str, float, float], int]:
    out: dict[tuple[str, float, float], int] = {}
    for s in samples:
        m = s.source_meta
        if "t0" in m and "user_file_id" in m:
            out[(m["user_file_id"], round(float(m["t0"]), 2), round(float(m["t1"]), 2))] = int(s.clip_id.rsplit("_c", 1)[1])
    for d in verify_cache.values():
        if "t0" in d and "t1" in d:
            uid, idx = d["clip_id"].rsplit("_c", 1)
            out.setdefault((uid, round(float(d["t0"]), 2), round(float(d["t1"]), 2)), int(idx))
    return out


@dataclass
class Work:
    pair: PairData
    cands: list[D.Candidate]          # same user file + window (1 per bucket)
    bounds: C.ClipBounds
    clip_index: int

    @property
    def user_id(self) -> str:
        return self.pair.frame(self.cands[0].user_role)[0]

    @property
    def clip_id(self) -> str:
        return C.clip_id_for(self.user_id, self.clip_index)


def process(work: Work, do_verify: bool, verify_cache: dict, counts: Counter) -> list[Sample]:
    """Trim, verify, prompt, caption. Returns accepted Samples (0..n)."""
    from ovfdb.mine import prompts as P

    user_id, partner_id = work.pair.frame(work.cands[0].user_role)
    b = work.bounds
    first = work.cands[0]
    t = time.time()
    base = sm.to_sample(
        user_id, partner_id, b.t0, b.t1, first.bucket, first.dynamic_type, b.ds, b.de, work.clip_index,
        out_root=CLIP_ROOT, agent_speaks_first=b.agent_speaks_first,
        mining_rule=first.evidence.get("rule", ""), evidence=first.evidence, lead_turns=b.lead_turns,
    )
    sbs = V.sbs_composite(base.user_video_path, base.partner_video_path, Path(base.user_video_path).parent / "sbs.mp4")
    log.info("  %s trimmed %.1fs clip in %.0fs", work.clip_id, base.duration_s, time.time() - t)
    accepted: list[Sample] = []
    for cand in work.cands:
        key = (cand.dynamic_type, cand.bucket)
        counts[("trimmed",) + key] += 1
        s = Sample(**{k: v for k, v in vars(base).items()})   # shallow copy, one row per bucket
        s.bucket, s.dynamic_type = cand.bucket, cand.dynamic_type
        s.source_meta = {**base.source_meta, "mining_rule": cand.evidence.get("rule", ""), "evidence": cand.evidence,
                         "t0": b.t0, "t1": b.t1}
        if do_verify:
            v = V.verify(work.clip_id, sbs, cand.dynamic_type, cand.bucket, s.dynamic_start_s, s.dynamic_end_s,
                         s.duration_s, cand.evidence, cache=verify_cache, window=(b.t0, b.t1))
            s.source_meta["verify"] = {"is_dynamic": v.is_dynamic, "confidence": v.confidence, "notes": v.notes,
                                       "refined": v.refined, "cached": v.cached}
            log.info("  %s %s/%s -> %s (conf %.2f) %s", work.clip_id, cand.dynamic_type.value, cand.bucket.value,
                     "ACCEPT" if v.accepted else "reject", v.confidence, v.notes[:140])
            if not v.accepted:
                counts[("rejected",) + key] += 1
                continue
            if v.refined:
                s.dynamic_start_s, s.dynamic_end_s = v.ds, v.de
                s.source_meta["dynamic_start_raw_s"] = round(b.t0 + v.ds, 3)
                s.source_meta["dynamic_end_raw_s"] = round(b.t0 + v.de, 3)
        counts[("accepted",) + key] += 1
        try:
            s.system_prompt = P.system_prompt(s)
            s.av_caption = P.av_caption(s)
        except Exception as e:  # noqa: BLE001 - keep the clip, prompts can be regenerated
            log.warning("  %s prompt/caption failed: %s", work.clip_id, e)
        accepted.append(s)
    if not accepted:
        REJECTED_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(sbs), REJECTED_DIR / f"{work.clip_id}.mp4")
        shutil.rmtree(Path(base.user_video_path).parent, ignore_errors=True)
    return accepted


def laughter_candidates(pd: PairData, wanted_roles: tuple[str, ...] = ("a", "b")) -> list[D.Candidate]:
    from ovfdb.mine import laughter as L

    out = []
    for role in wanted_roles:
        uid, pid = pd.frame(role)
        got = sm.fetch(uid, ("audio",))
        if "audio" not in got:
            continue
        laughs = L.detect(got["audio"], pd.vad[uid], pd.utts[uid])
        for c in D.find_laughter(pd.vad[uid], pd.utts[uid], pd.vad[pid], pd.utts[pid], laughs_a=laughs):
            c.user_role = role
            feats = laughs[0].__dict__.get("features") if laughs else None
            if feats is not None:
                c.evidence["detector"] = "gemini-audio" if isinstance(feats, dict) else "dsp"
            out.append(c)
    return out


def nonverbal_candidates(pd: PairData, wanted: set[DynamicType]) -> list[D.Candidate]:
    """Fetch both videos, run the Gemini event pass (+ 3P-V + movement events) once per pair
    (cached on ``pd.events``), then the pure nonverbal finders with both role assignments."""
    if pd.events is None:
        media = {fid: sm.fetch(fid, ("video",)) for fid in (pd.a, pd.b)}
        if any("video" not in m for m in media.values()):
            log.warning("  no video for %s / %s; skipping nonverbal pass", pd.a, pd.b)
            pd.events = {pd.a: [], pd.b: []}
            return []
        pd.events = NV.events_for_pair(pd.a, pd.b, media[pd.a]["video"], media[pd.b]["video"], anns=pd.anns)
        log.info("  nonverbal events: %s", {fid: Counter(e.kind for e in ev).most_common(6) for fid, ev in pd.events.items()})
    return NV.find_all(pd.events[pd.a], pd.vad[pd.a], pd.utts[pd.a], pd.events[pd.b], pd.vad[pd.b], pd.utts[pd.b],
                       dynamics=wanted)


def group_works(chosen: list[D.Candidate], pd: PairData, media: dict[str, float],
                need: dict[tuple[DynamicType, Bucket], int]) -> dict[tuple, Work]:
    """Clip bounds per candidate, grouped by (user file, window) so a clip shared by two
    buckets is trimmed once. A clip can hold only one dynamic per bucket (manifest rows are
    keyed by (clip_id, bucket)); on a collision the scarcer dynamic keeps the window."""
    works: dict[tuple, Work] = {}
    ordered = sorted(chosen, key=lambda c: -need.get((c.dynamic_type, c.bucket), 0))
    for c in ordered:
        uid, pid = pd.frame(c.user_role)
        turns = D.turns(pd.vad[uid], pd.utts[uid], pd.vad[pid], pd.utts[pid])
        b = C.clip_bounds(c, turns, min(media[uid], media[pid]), pd.vad[pid])
        if b.dur < 5 or b.t0 < 0 or b.ds < b.t0 or b.de > b.t1:
            continue    # e.g. a movement event at the very start of the file, inside the edge margin
        key = C.window_key(uid, b)
        if key in works:
            if any(x.bucket is c.bucket for x in works[key].cands):
                continue
            works[key].cands.append(c)
        else:
            works[key] = Work(pd, [c], b, 0)
    return works


def run(dynamics: str = "all", limit: int = 0, label: str = "naturalistic", split: str = "test",
        manifest: str = "manifest/ovfdb_v0.jsonl", verify: bool = True, workers: int = 2,
        scan: int = SCAN_DEFAULT, per_pair: int = 3, max_pairs: int = 0, max_minutes: float = 0.0,
        require_3p: bool = False) -> Counter:
    """Mine clips into ``manifest``. ``limit`` = max clips per (dynamic, bucket); 0 = no cap.
    ``require_3p`` restricts the scan to pairs with third-party (3P-V) annotations."""
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "httpcore", "google_genai", "google_genai.models", "openai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    t_start = time.time()
    wanted = parse_dynamics(dynamics)
    keys = [(d, b) for d in wanted for b in (Bucket.PERCEPTION, Bucket.GENERATION)
            if (d, b) in V.PARTNER_EXPECTATION]
    dialogue_wanted = {d for d in wanted if d in D.FINDERS and d is not DynamicType.LAUGHTER}
    nv_wanted = {d for d in wanted if d in NV.FINDERS}
    nv_keys = [k for k in keys if k[0] in nv_wanted]

    manifest_path = Path(manifest)
    samples = read_manifest(manifest_path) if manifest_path.exists() else []
    have = Counter((s.dynamic_type, s.bucket) for s in samples)
    present = {(s.clip_id, s.bucket) for s in samples}
    verify_cache = V.load_cache() if verify else {}
    index_map = _existing_index_map(samples, verify_cache)
    counts: Counter = Counter()
    cap = limit if limit > 0 else 10**9

    def need() -> dict[tuple[DynamicType, Bucket], int]:
        return {k: max(0, cap - have[k]) for k in keys}

    # --- 1. scan + rank pairs (media already on disk first)
    all_pairs = sm.pairs(label, split, require_3p)
    def local(p):
        return all(sm.local_path(f, "video", label, split).exists() for f in p)
    all_pairs.sort(key=lambda p: not local(p))
    scanned: list[PairData] = []
    for a, b in all_pairs[: max(scan, 1)]:
        pd = load_pair(a, b, with_3p=bool(nv_wanted))
        if pd is None:
            counts[("pairs_rejected",)] += 1
            continue
        pd.cands = D.find_all(pd.vad[a], pd.utts[a], pd.vad[b], pd.utts[b], dynamics=dialogue_wanted) if dialogue_wanted else []
        scanned.append(pd)
    for pd in scanned:
        for c in pd.cands:
            counts[("found", c.dynamic_type, c.bucket)] += 1
    log.info("scanned %d pairs (%d consistent); candidates: %s", min(scan, len(all_pairs)), len(scanned),
             {f"{k[1].value}/{k[2].value}": n for k, n in counts.items() if k[0] == "found"})

    def pair_value(pd: PairData) -> float:
        n = need()
        got = Counter((c.dynamic_type, c.bucket) for c in pd.cands)
        v = sum(min(got[k], per_pair, n[k]) for k in keys if n[k] > 0)
        if (DynamicType.LAUGHTER, Bucket.PERCEPTION) in n and n[(DynamicType.LAUGHTER, Bucket.PERCEPTION)] > 0:
            v += 0.5   # laughter is unknown until the audio pass; any pair may have it
        if pd.events is not None:
            got_nv = Counter((c.dynamic_type, c.bucket) for c in nonverbal_candidates(pd, nv_wanted))
            v += sum(min(got_nv[k], per_pair, n[k]) for k in nv_keys if n[k] > 0)
        elif any(n[k] > 0 for k in nv_keys):
            v += 0.5   # nonverbal events are unknown until the video pass
            if (DynamicType.ADAPTOR_HANDLING, Bucket.PERCEPTION) in nv_keys and pd.anns:
                v += 0.3   # 3P-V text is a cheap adaptor source
        return v + (0.1 if local((pd.a, pd.b)) else 0.0)

    # --- 2. process pairs
    processed = 0
    pool = ThreadPoolExecutor(max_workers=max(1, workers))
    remaining = list(scanned)
    while remaining:
        n = need()
        if all(v <= 0 for v in n.values()):
            log.info("all targets met")
            break
        if max_pairs and processed >= max_pairs:
            break
        if max_minutes and (time.time() - t_start) / 60 > max_minutes:
            log.info("time budget reached")
            break
        remaining.sort(key=pair_value, reverse=True)
        pd = remaining.pop(0)
        if pair_value(pd) <= 0.2:
            continue
        cands = list(pd.cands)
        if DynamicType.LAUGHTER in wanted and (n.get((DynamicType.LAUGHTER, Bucket.PERCEPTION), 0) > 0 or
                                              n.get((DynamicType.LAUGHTER, Bucket.GENERATION), 0) > 0):
            lc = laughter_candidates(pd)
            counts[("found", DynamicType.LAUGHTER, Bucket.PERCEPTION)] += sum(1 for c in lc if c.bucket is Bucket.PERCEPTION)
            counts[("found", DynamicType.LAUGHTER, Bucket.GENERATION)] += sum(1 for c in lc if c.bucket is Bucket.GENERATION)
            cands += lc
        if nv_wanted and any(n[k] > 0 for k in nv_keys):
            fresh = pd.events is None
            try:
                nc = nonverbal_candidates(pd, nv_wanted)
            except Exception as e:  # noqa: BLE001 - a failed video pass must not kill the run
                log.warning("  nonverbal pass failed for %s / %s: %s", pd.a, pd.b, e)
                pd.events = {pd.a: [], pd.b: []}
                nc = []
            if fresh:
                for c in nc:
                    counts[("found", c.dynamic_type, c.bucket)] += 1
            cands += nc
        chosen = select_candidates(cands, n, per_pair)
        if not chosen:
            continue
        processed += 1
        log.info("pair %s / %s: %d candidates chosen (%s)", pd.a, pd.b, len(chosen),
                 Counter(f"{c.dynamic_type.value}/{c.bucket.value}" for c in chosen))
        # media + duration
        media = {}
        for fid in (pd.a, pd.b):
            got = sm.fetch(fid, ("audio", "video"))
            if "audio" not in got or "video" not in got:
                log.warning("  no media for %s; skipping pair", fid)
                media = None
                break
            media[fid] = min(sm.media_duration(got["audio"]), sm.media_duration(got["video"]))
        if not media:
            continue
        # clip bounds, grouped by window so a clip shared by two buckets is trimmed once
        works = group_works(chosen, pd, media, n)
        index_map = C.assign_clip_indices(list(works), index_map)
        todo = []
        for key, w in works.items():
            w.clip_index = index_map[key]
            w.cands = [c for c in w.cands if (w.clip_id, c.bucket) not in present]
            if w.cands:
                todo.append(w)

        def job(w: Work):
            try:
                return process(w, verify, verify_cache, counts)
            except Exception as e:  # noqa: BLE001 - one bad clip must not kill the run
                log.warning("  %s failed: %s", w.clip_id, e)
                counts[("errors",)] += 1
                return []

        new: list[Sample] = []
        for res in pool.map(job, todo):
            new.extend(res)
        for s in new:
            if (s.clip_id, s.bucket) in present:
                continue
            samples.append(s)
            present.add((s.clip_id, s.bucket))
            have[(s.dynamic_type, s.bucket)] += 1
        if new:
            write_manifest(samples, manifest_path)
        log.info("  pair done: +%d clips; manifest=%d; elapsed %.1f min", len(new), len(samples), (time.time() - t_start) / 60)

    pool.shutdown(wait=True)
    # --- summary
    log.info("=== mining summary (%.1f min) ===", (time.time() - t_start) / 60)
    for d, b in keys:
        f, t, r, a = (counts[(tag, d, b)] for tag in ("found", "trimmed", "rejected", "accepted"))
        log.info("%-24s %-10s found=%-4d trimmed=%-3d vlm_rejected=%-3d accepted=%-3d in_manifest=%d",
                 d.value, b.value, f, t, r, a, have[(d, b)])
    log.info("pairs processed=%d errors=%d manifest=%s (%d rows)", processed, counts[("errors",)], manifest_path, len(samples))
    return counts
