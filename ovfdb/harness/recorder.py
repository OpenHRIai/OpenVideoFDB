"""Places received agent audio at clip-relative times into a silence buffer and writes
16 kHz mono `agent.wav` plus an `events.jsonl` send/receive log.

Placement semantics (`overlap="queue"`, the default): a chunk starts at
`max(t_received, play_head)` where `play_head` is the end of the previously placed
chunk. This emulates what a real-time client does with a playback queue: agents such
as Gemini Live deliver audio in faster-than-realtime bursts, so stacking those chunks
at their raw receive times would overlap them. Chunks that arrive within `snap_s` of
the play head are butted against it (no micro-gaps from scheduler jitter); chunks
that arrive later than the head start at their receive time (silence in between).
`overlap="sum"` instead places every chunk exactly at `t_received` and sums
overlaps with int16 clipping (useful for synthetic/echo agents).

`flush(t)` drops queued audio not yet played at `t` (barge-in / `interrupted`).

Spec: plans/WS3-harness.md.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly  # imported eagerly: a lazy import stalls the event loop ~1 s

from ovfdb.harness.base import AUDIO_SR


def resample_pcm16(data: bytes, sr_in: int, sr_out: int) -> bytes:
    """Resample int16 PCM bytes from `sr_in` to `sr_out` (polyphase FIR, scipy).

    Stateless: each call is resampled independently, so chunk boundaries get a few
    samples of FIR edge effect. Call it on message-sized buffers (≥100 ms) rather
    than on tiny chunks where possible.
    """
    if sr_in == sr_out or not data:
        return data
    x = np.frombuffer(data, dtype=np.int16).astype(np.float32)
    g = math.gcd(sr_in, sr_out)
    y = resample_poly(x, sr_out // g, sr_in // g)
    return np.clip(np.rint(y), -32768, 32767).astype(np.int16).tobytes()


class Recorder:
    def __init__(self, sr: int = AUDIO_SR, overlap: Literal["queue", "sum"] = "queue",
                 snap_s: float = 0.02) -> None:
        self.sr = sr
        self.overlap = overlap
        self.snap_s = snap_s
        self._buf = np.zeros(0, dtype=np.int16)
        self._head = 0           # play head, in samples (end of last placed chunk)
        self.events: list[dict] = []
        self.n_chunks = 0

    # --- events -----------------------------------------------------------

    def log(self, type: str, t: float, n_bytes: int = 0, **extra) -> None:
        ev = {"type": type, "t": round(float(t), 4), "n_bytes": int(n_bytes), "wall": time.time()}
        ev.update(extra)
        self.events.append(ev)

    # --- audio ------------------------------------------------------------

    def _ensure(self, n: int) -> None:
        if n > len(self._buf):
            grow = max(n - len(self._buf), self.sr * 5)
            self._buf = np.concatenate([self._buf, np.zeros(grow, dtype=np.int16)])

    def place(self, pcm16k: bytes, t: float, *, t_agent: float | None = None) -> float:
        """Place a chunk received at clip time `t`. Returns the clip time it was placed at."""
        x = np.frombuffer(pcm16k, dtype=np.int16)
        t = max(0.0, float(t))
        req = round(t * self.sr)
        if self.overlap == "queue":
            if req - self._head < int(self.snap_s * self.sr):
                start = self._head   # burst (req < head) or jitter (req ≈ head): butt against head
            else:
                start = req          # real gap: silence between head and req
        else:
            start = req
        end = start + len(x)
        self._ensure(end)
        if self.overlap == "sum":
            mixed = self._buf[start:end].astype(np.int32) + x.astype(np.int32)
            self._buf[start:end] = np.clip(mixed, -32768, 32767).astype(np.int16)
        else:
            self._buf[start:end] = x
        self._head = max(self._head, end) if self.overlap == "sum" else end
        self.n_chunks += 1
        placed = start / self.sr
        ev = {"placed_t": round(placed, 4)}
        if t_agent is not None:
            ev["t_agent"] = round(float(t_agent), 4)
        self.log("recv", t, len(pcm16k), **ev)
        return placed

    def flush(self, t: float) -> float:
        """Drop audio queued beyond clip time `t` (barge-in). Returns seconds dropped."""
        idx = max(0, round(float(t) * self.sr))
        dropped = 0.0
        if idx < self._head:
            self._buf[idx:self._head] = 0
            dropped = (self._head - idx) / self.sr
            self._head = idx
        self.log("flush", t, 0, dropped_s=round(dropped, 4))
        return dropped

    @property
    def play_head_s(self) -> float:
        return self._head / self.sr

    def audio(self, duration_s: float | None = None) -> np.ndarray:
        """The int16 buffer; `duration_s` pads/truncates to an exact length."""
        if duration_s is None:
            return self._buf[: self._head].copy()
        n = round(duration_s * self.sr)
        out = np.zeros(n, dtype=np.int16)
        m = min(n, len(self._buf))
        out[:m] = self._buf[:m]
        return out

    # --- output -----------------------------------------------------------

    def write(self, path: str | Path, duration_s: float | None = None,
              events_path: str | Path | None = None) -> tuple[Path, Path]:
        """Write the wav (16 kHz mono PCM16) and the events jsonl next to it."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), self.audio(duration_s), self.sr, subtype="PCM_16")
        events_path = Path(events_path) if events_path else path.with_name("events.jsonl")
        with events_path.open("w") as f:
            for ev in self.events:
                f.write(json.dumps(ev) + "\n")
        return path, events_path
