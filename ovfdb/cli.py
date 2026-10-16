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


@seamless_app.command("trim")
def seamless_trim(user_id: str, partner_id: str, t0: float, t1: float, out_dir: str = "data/clips/_scratch"):
    from ovfdb.data.seamless import trim  # WS1
    typer.echo(trim(user_id, partner_id, t0, t1, out_dir))


@nvidia_app.command("load")
def nvidia_load(split: str = "validation"):
    from ovfdb.data.nvidia import load  # WS7
    for s in load(split):
        typer.echo(f"{s.clip_id}\t{s.bucket.value}\t{s.dynamic_type.value}\t{s.dynamic_start_s:.2f}-{s.dynamic_end_s:.2f}")


@app.command()
def mine(dynamics: str = "all", limit: int = 0, label: str = "naturalistic", split: str = "test",
         manifest: str = "manifest/ovfdb_v0.jsonl"):
    """WS2: find, verify and trim candidate clips → manifest."""
    from ovfdb.mine import pipeline  # WS2
    pipeline.run(dynamics=dynamics, limit=limit, label=label, split=split, manifest=manifest)


@app.command()
def run(manifest: str, provider: str, mode: str = "av", out: str = "", limit: int = 0, concurrency: int = 1,
        model: str = ""):
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
def score(run_dir: str, judge: str = "gpt-4o", axes: str = "all"):
    """WS5: ASR + timing + LLM judge; writes per-clip JSON and a summary."""
    from ovfdb.score import pipeline  # WS5
    pipeline.score(run_dir, judge=judge, axes=axes)


@app.command()
def report(run_dirs: list[str], per_dynamic: bool = False, out: str = "results/summary.md"):
    """WS5/WS8: Table-1 style summary with bootstrap CIs."""
    from ovfdb.score import report as rep
    rep.write(run_dirs, per_dynamic=per_dynamic, out=out)


if __name__ == "__main__":
    app()
