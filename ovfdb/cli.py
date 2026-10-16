"""`ovfdb` command line. Subcommands map 1:1 to workstreams; each one imports
lazily so an unimplemented workstream doesn't break the others."""

from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True, help="OpenVideoFDB: mine → run → score")
seamless_app = typer.Typer(help="Seamless Interaction data (WS1)")
nvidia_app = typer.Typer(help="NVIDIA VideoFDB adapter (WS7)")
app.add_typer(seamless_app, name="seamless")
app.add_typer(nvidia_app, name="nvidia")


@seamless_app.command("pairs")
def seamless_pairs(label: str = "naturalistic", split: str = "test", require_3p: bool = False):
    from ovfdb.data.seamless import pairs
    for a, b in pairs(label, split, require_3p):
        typer.echo(f"{a}\t{b}")


@seamless_app.command("fetch")
def seamless_fetch(file_id: str, kinds: str = "audio,vad,transcript,3P-V"):
    from ovfdb.data.seamless import fetch
    for kind, path in fetch(file_id, tuple(kinds.split(","))).items():
        typer.echo(f"{kind}\t{path}")


@seamless_app.command("fetch-movement")
def seamless_fetch_movement(file_id: str, features: str = "", group: str = "movement"):
    """Download 30 Hz .npy features (only files with has_imitator_movement=1 have them)."""
    from ovfdb.data.seamless import DEFAULT_MOVEMENT_FEATURES, fetch_movement
    feats = tuple(features.split(",")) if features else DEFAULT_MOVEMENT_FEATURES
    got = fetch_movement(file_id, feats, group)
    if not got:
        typer.echo(f"no {group} features on the mirror for {file_id}", err=True)
    for feature, path in got.items():
        typer.echo(f"{feature}\t{path}")


@seamless_app.command("trim")
def seamless_trim(user_id: str, partner_id: str, t0: float, t1: float, out_dir: str = "data/clips/_scratch",
                  no_video: bool = False):
    """Cut [t0, t1] of both participants to user/partner .wav (16 kHz) and .mp4 (720p30)."""
    from ovfdb.data.seamless import media_duration, trim  # WS1
    for key, path in trim(user_id, partner_id, t0, t1, out_dir, video=not no_video).items():
        typer.echo(f"{key}\t{path}\t{media_duration(path):.3f}s")


@seamless_app.command("check")
def seamless_check(user_id: str, partner_id: str = ""):
    """Quality gate: fraction of transcript words outside any VAD region (fail > 0.2)."""
    from ovfdb.data.seamless import (
        fetch,
        pair_is_consistent,
        read_transcript,
        read_vad,
        transcript_words,
        words_outside_vad_frac,
    )
    for fid in (user_id, partner_id) if partner_id else (user_id,):
        got = fetch(fid, ("vad", "transcript"))
        if "vad" in got and "transcript" in got:
            frac = words_outside_vad_frac(transcript_words(read_transcript(got["transcript"])), read_vad(got["vad"]))
            typer.echo(f"{fid}\twords_outside_vad={frac:.3f}")
        else:
            typer.echo(f"{fid}\tmissing {[k for k in ('vad', 'transcript') if k not in got]}")
    ok = pair_is_consistent(user_id, partner_id or None)
    typer.echo("OK" if ok else "REJECT")
    raise typer.Exit(code=0 if ok else 1)


@nvidia_app.command("snapshot")
def nvidia_snapshot(validation_only: bool = False, split: str = ""):
    """WS7: download the gated dataset to data/nvidia (HF_TOKEN in .env). --validation-only / --split limit the media."""
    from ovfdb.data.nvidia import snapshot  # WS7
    typer.echo(f"snapshot -> {snapshot(validation_only=validation_only, split=split or None)}")


@nvidia_app.command("load")
def nvidia_load(split: str = "validation"):
    """WS7: print the rows of a split as Samples."""
    from ovfdb.data.nvidia import load  # WS7
    for s in load(split):
        typer.echo(f"{s.clip_id}\t{s.bucket.value}\t{s.dynamic_type.value}\t{s.dynamic_start_s:.2f}-{s.dynamic_end_s:.2f}"
                   f"\tfirst={s.agent_speaks_first}\twords={len(s.user_words)}\tcaption={len(s.av_caption)}ch"
                   f"\tpartner={'yes' if s.partner_audio_path else 'no'}")


@nvidia_app.command("manifest")
def nvidia_manifest(split: str = "validation", out: str = ""):
    """WS7: write manifest/nvidia_<split>.jsonl (git-ignored) for `ovfdb run / score / report`."""
    from ovfdb.data.nvidia import write_manifest_for  # WS7
    typer.echo(f"wrote {write_manifest_for(split, out or None)}")


@app.command()
def mine(dynamics: str = "all", limit: int = 0, label: str = "naturalistic", split: str = "test",
         manifest: str = "manifest/ovfdb_v0.jsonl", verify: bool = True, workers: int = 2, scan: int = 60,
         per_pair: int = 3, max_pairs: int = 0, max_minutes: float = 0.0, require_3p: bool = False,
         tag: str = ""):
    """WS2: find, verify and trim candidate clips → manifest.

    --dynamics: comma list (pause_handling,verbal_backchanneling,verbal_interruption,turn_taking,laughter,
    nonverbal_backchanneling,face_emotion_display,emotion_matching,gaze_avoidance_with_pause,adaptor_handling,
    nonverbal_interruption), or all (day-1 dialogue), nonverbal (day-2), everything.
    --limit: max clips per (dynamic, bucket). --no-verify skips the Gemini check. --scan: pairs whose
    VAD/transcripts are scanned before choosing which media to download. --require-3p: only pairs with
    third-party text annotations (Adaptor Handling source). --tag v1: separate clip root / caches for a
    re-mined set (pair with --manifest manifest/ovfdb_v1.jsonl).
    """
    from ovfdb.mine import pipeline  # WS2
    pipeline.run(dynamics=dynamics, limit=limit, label=label, split=split, manifest=manifest, verify=verify,
                 workers=workers, scan=scan, per_pair=per_pair, max_pairs=max_pairs, max_minutes=max_minutes,
                 require_3p=require_3p, tag=tag)


@app.command()
def run(manifest: str, provider: str = typer.Option(..., "--provider", help="gemini_live | human_gt | random"),
        mode: str = "av", out: str = "", limit: int = 0, concurrency: int = 1, model: str = ""):
    """WS3: stream each clip through a provider; write runs/<out>/<clip>/agent.wav."""
    from ovfdb.harness import streamer  # WS3
    streamer.run_manifest(manifest, provider=provider, mode=mode, out=out or f"runs/{provider}_{mode}",
                          limit=limit, concurrency=concurrency, model=model)


@app.command("score-timing")
def score_timing(run_dir: str, manifest: str = "", force: bool = False):
    """WS4: ASR + timing metrics for every clip in a run.

    --manifest overrides the manifest (else run.json meta, <run_dir>/manifest.jsonl, manifest/ovfdb_v0.jsonl);
    --force recomputes timing.json (ASR words stay cached).
    """
    from ovfdb.score import pipeline  # WS4
    pipeline.score_timing(run_dir, manifest=manifest or None, force=force)


@app.command()
def score(run_dir: str, judge: str = "gpt-4o", axes: str = "all", manifest: str = "", force: bool = False):
    """WS5: ASR + timing + LLM judge; writes per-clip JSON and a summary."""
    from ovfdb.score import pipeline  # WS5
    pipeline.score(run_dir, judge=judge, axes=axes, manifest=manifest or None, force=force)


@app.command()
def review(manifest: str = "manifest/ovfdb_v1.jsonl", port: int = 8765, review_file: str = "",
           no_browser: bool = False):
    """Human annotator page: play each clip with its window, accept / reject / fix the window.

    Decisions go to data/mining/review_<manifest stem>.jsonl; fold them in with `review-apply`.
    """
    from ovfdb.review import app as R
    R.serve(manifest, port=port, review=review_file or None, open_browser=not no_browser)


@app.command("review-apply")
def review_apply(manifest: str = "manifest/ovfdb_v1.jsonl", review_file: str = "", out: str = "",
                 drop_unreviewed: bool = False):
    """Write <out> (default <manifest stem>_reviewed.jsonl): rejected rows dropped, fixed windows applied."""
    from pathlib import Path

    from ovfdb.review import app as R
    rv = review_file or str(R.review_path(manifest))
    dst = out or str(Path(manifest).with_name(Path(manifest).stem + "_reviewed.jsonl"))
    kept, dropped, fixed = R.apply_decisions(manifest, rv, dst, keep_unreviewed=not drop_unreviewed)
    print(f"{dst}: kept {kept}, dropped {dropped}, windows fixed {fixed} (decisions from {rv})")


@app.command()
def report(run_dirs: list[str], per_dynamic: bool = False, out: str = "results/summary.md",
           manifest: str = "", rows: int = 0):
    """WS5/WS8: Table-1 style summary with bootstrap CIs.

    --manifest (+ --rows N = its first N rows) restricts every run to that common row set.
    """
    from ovfdb.score import report as rep
    rep.write(run_dirs, per_dynamic=per_dynamic, out=out, manifest=manifest or None, rows=rows)


if __name__ == "__main__":
    app()
