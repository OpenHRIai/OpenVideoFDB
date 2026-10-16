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


@nvidia_app.command("load")
def nvidia_load(split: str = "validation"):
    from ovfdb.data.nvidia import load  # WS7
    for s in load(split):
        typer.echo(f"{s.clip_id}\t{s.bucket.value}\t{s.dynamic_type.value}\t{s.dynamic_start_s:.2f}-{s.dynamic_end_s:.2f}")


@app.command()
def mine(dynamics: str = "all", limit: int = 0, label: str = "naturalistic", split: str = "test",
         manifest: str = "manifest/ovfdb_v0.jsonl", verify: bool = True, workers: int = 2, scan: int = 60,
         per_pair: int = 3, max_pairs: int = 0, max_minutes: float = 0.0, require_3p: bool = False):
    """WS2: find, verify and trim candidate clips → manifest.

    --dynamics: comma list (pause_handling,verbal_backchanneling,verbal_interruption,turn_taking,laughter,
    nonverbal_backchanneling,face_emotion_display,emotion_matching,gaze_avoidance_with_pause,adaptor_handling,
    nonverbal_interruption), or all (day-1 dialogue), nonverbal (day-2), everything.
    --limit: max clips per (dynamic, bucket). --no-verify skips the Gemini check. --scan: pairs whose
    VAD/transcripts are scanned before choosing which media to download. --require-3p: only pairs with
    third-party text annotations (Adaptor Handling source).
    """
    from ovfdb.mine import pipeline  # WS2
    pipeline.run(dynamics=dynamics, limit=limit, label=label, split=split, manifest=manifest, verify=verify,
                 workers=workers, scan=scan, per_pair=per_pair, max_pairs=max_pairs, max_minutes=max_minutes,
                 require_3p=require_3p)


@app.command()
def run(manifest: str, provider: str = typer.Option(..., "--provider", help="gemini_live | human_gt | random"),
        mode: str = "av", out: str = "", limit: int = 0, concurrency: int = 1, model: str = ""):
    """WS3: stream each clip through a provider; write runs/<out>/<clip>/agent.wav."""
    from ovfdb.harness import streamer  # WS3
    streamer.run_manifest(manifest, provider=provider, mode=mode, out=out or f"runs/{provider}_{mode}",
                          limit=limit, concurrency=concurrency, model=model)


@app.command("score-timing")
def score_timing(run_dir: str):
    """WS4: ASR + timing metrics for every clip in a run."""
    from ovfdb.score import pipeline  # WS4
    pipeline.score_timing(run_dir)


@app.command()
def score(run_dir: str, judge: str = "gpt-4o", axes: str = "all", manifest: str = "", force: bool = False):
    """WS5: ASR + timing + LLM judge; writes per-clip JSON and a summary."""
    from ovfdb.score import pipeline  # WS5
    pipeline.score(run_dir, judge=judge, axes=axes, manifest=manifest or None, force=force)


@app.command()
def report(run_dirs: list[str], per_dynamic: bool = False, out: str = "results/summary.md"):
    """WS5/WS8: Table-1 style summary with bootstrap CIs."""
    from ovfdb.score import report as rep
    rep.write(run_dirs, per_dynamic=per_dynamic, out=out)


if __name__ == "__main__":
    app()
