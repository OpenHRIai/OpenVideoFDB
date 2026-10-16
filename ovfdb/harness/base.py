"""Agent contract for the real-time harness (plans/WS3-harness.md).

A provider implements `Agent`. The streamer (`streamer.py`) paces a Sample's
user audio/frames into it by wall clock and the recorder places received audio
at clip-relative receive times. Changing this file is a contract change:
record it in STATUS.md.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

Mode = Literal["av", "a2a"]

#: Chunk size the streamer pushes; providers may re-buffer internally.
AUDIO_CHUNK_S = 0.04          # 40 ms @ 16 kHz = 640 samples = 1280 bytes
AUDIO_SR = 16_000
DEFAULT_FRAME_FPS = 1.0
DEFAULT_TAIL_S = 5.0          # silence streamed after the clip to catch late responses


@dataclass
class AudioOut:
    """A chunk of agent audio and the clip-relative time it was received.

    Providers stamp `t_received` from their own clock (t=0 at the first `push_audio`);
    the streamer re-stamps it on drain with its own t0 and keeps the provider's value
    in the event log as `t_agent`. `flush=True` (with empty `pcm16k`) tells the
    recorder to drop any already-queued audio not yet "played" at `t_received` — the
    full-duplex barge-in signal (Gemini `server_content.interrupted`)."""

    pcm16k: bytes
    t_received: float
    flush: bool = False


@runtime_checkable
class Agent(Protocol):
    name: str
    #: The streamer drains this; providers put `AudioOut` here as audio arrives.
    out: asyncio.Queue[AudioOut]

    async def start(self, system_prompt: str, mode: Mode, *, agent_speaks_first: bool = False) -> None: ...
    async def push_audio(self, pcm16k: bytes, t: float) -> None: ...
    async def push_frame(self, jpeg: bytes, t: float) -> None: ...
    async def stop(self) -> None: ...


class OfflineAgent:
    """Base for non-network agents (human GT, random partner): the "response" is a
    pre-recorded wav. The streamer still runs so AgentRun has the same shape."""

    name = "offline"

    def __init__(self) -> None:
        self.out: asyncio.Queue[AudioOut] = asyncio.Queue()

    async def start(self, system_prompt: str, mode: Mode, *, agent_speaks_first: bool = False) -> None:
        return None

    async def push_audio(self, pcm16k: bytes, t: float) -> None:
        return None

    async def push_frame(self, jpeg: bytes, t: float) -> None:
        return None

    async def stop(self) -> None:
        return None
