"""HumanGT (the clip's own partner.wav as the "agent") and RandomPartner (another clip's
partner.wav, seeded) — OfflineAgents for judge calibration (WS5).

They are not network agents, but they *behave* like real-time ones: the partner wav is
emitted into `out` in 40 ms chunks at the right clip-relative times (t=0 = first
`push_audio`), so the same streamer/recorder path and AgentRun shape are exercised.
The Sample (and, for RandomPartner, the manifest) are constructor arguments.

Spec: plans/WS3-harness.md.
"""

from __future__ import annotations

import asyncio
import random
import time
from pathlib import Path

from ovfdb.harness.base import AUDIO_CHUNK_S, AUDIO_SR, AudioOut, Mode, OfflineAgent
from ovfdb.schema import Sample

_CHUNK_BYTES = int(AUDIO_SR * AUDIO_CHUNK_S) * 2


class PartnerPlayback(OfflineAgent):
    """Plays `wav_path` (16 kHz mono; resampled if not) as the agent, paced by wall clock."""

    name = "partner_playback"

    def __init__(self, wav_path: str | Path | None, offset_s: float = 0.0) -> None:
        super().__init__()
        self.wav_path = str(wav_path) if wav_path else None
        self.offset_s = offset_s          # clip time at which the wav's sample 0 is played
        self.meta: dict = {}
        self.errors: list[str] = []
        self.model = ""
        self._pcm: bytes = b""
        self._t0: float | None = None
        self._task: asyncio.Task | None = None

    async def start(self, system_prompt: str, mode: Mode, *, agent_speaks_first: bool = False) -> None:
        if not self.wav_path or not Path(self.wav_path).exists():
            raise FileNotFoundError(f"{self.name}: partner wav missing: {self.wav_path!r}")
        from ovfdb.harness.streamer import load_pcm16k
        self._pcm = await asyncio.to_thread(load_pcm16k, self.wav_path)
        self.meta["partner_wav"] = self.wav_path
        self.meta["partner_s"] = round(len(self._pcm) / 2 / AUDIO_SR, 3)

    async def push_audio(self, pcm16k: bytes, t: float) -> None:
        if self._t0 is None:
            self._t0 = time.monotonic()
            self._task = asyncio.create_task(self._emit())

    async def _emit(self) -> None:
        assert self._t0 is not None
        n = (len(self._pcm) + _CHUNK_BYTES - 1) // _CHUNK_BYTES
        for i in range(n):
            t = self.offset_s + i * AUDIO_CHUNK_S
            due = self._t0 + t
            now = time.monotonic()
            if due > now:
                await asyncio.sleep(due - now)
            chunk = self._pcm[i * _CHUNK_BYTES:(i + 1) * _CHUNK_BYTES]
            if len(chunk) < _CHUNK_BYTES:
                chunk = chunk + b"\x00" * (_CHUNK_BYTES - len(chunk))
            await self.out.put(AudioOut(chunk, time.monotonic() - self._t0))

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception) as e:  # noqa: BLE001
                self.meta["emitter_end"] = repr(e)
            self._task = None


class HumanGT(PartnerPlayback):
    """The clip's own partner channel: the human ground-truth "agent"."""

    name = "human_gt"

    def __init__(self, sample: Sample) -> None:
        super().__init__(sample.partner_audio_path)
        self.sample = sample
        self.meta["partner_clip_id"] = sample.clip_id


class RandomPartner(PartnerPlayback):
    """Another clip's partner channel (the calibration lower bound), chosen deterministically
    from `manifest_samples` by `seed` and this clip's id."""

    name = "random"

    def __init__(self, sample: Sample, manifest_samples: list[Sample], seed: int = 0) -> None:
        self.sample = sample
        self.seed = seed
        other = pick_other(sample, manifest_samples, seed)
        super().__init__(other.partner_audio_path if other else None)
        self.meta["partner_clip_id"] = other.clip_id if other else None
        self.meta["seed"] = seed


def pick_other(sample: Sample, manifest_samples: list[Sample], seed: int = 0) -> Sample | None:
    """Deterministic choice of a *different* conversation's sample with a partner wav."""
    cands = sorted(
        (s for s in manifest_samples
         if s.clip_id != sample.clip_id and s.conversation_id != sample.conversation_id and s.partner_audio_path),
        key=lambda s: s.clip_id,
    )
    if not cands:  # fall back to any other clip (same conversation) rather than nothing
        cands = sorted((s for s in manifest_samples if s.clip_id != sample.clip_id and s.partner_audio_path),
                       key=lambda s: s.clip_id)
    if not cands:
        return None
    rng = random.Random(f"{seed}:{sample.clip_id}")
    return rng.choice(cands)
