"""Gemini Live provider (google-genai Live API): 16 kHz PCM audio + JPEG frames in,
24 kHz PCM audio out (resampled to 16 kHz before it reaches the recorder).

SDK calls (google-genai 2.x, checked against the installed package):
  client.aio.live.connect(model=..., config=types.LiveConnectConfig(...))
  session.send_realtime_input(audio=types.Blob(data=pcm, mime_type="audio/pcm;rate=16000"))
  session.send_realtime_input(video=types.Blob(data=jpeg, mime_type="image/jpeg"))
  session.send_client_content(turns=types.Content(role="user", parts=[types.Part(text=...)]))
  async for msg in session.receive(): msg.server_content.model_turn.parts[].inline_data.data

Server-side VAD is kept (that *is* the full-duplex behaviour under test): no
activity_start/activity_end markers are sent. `server_content.interrupted` is forwarded
to the recorder as a flush (barge-in: a real client would empty its playback queue).

agent_speaks_first: if no audio has arrived within `speak_first_wait_s` (2 s) of
start(), one text turn "Start speaking now to begin/continue the conversation." is
sent; `meta["speak_first_path"]` records which path was taken.

Model ids: the installed SDK's own live tests document `gemini-3.1-flash-live-preview`
as the Gemini-API (API-key) live model and `gemini-live-2.5-flash-native-audio` as the
Vertex one; the paper used "Gemini 2.5 Flash Native" and "Gemini 3.1 Flash Live".
Override with `ovfdb run --model ...`.

Spec: plans/WS3-harness.md.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time

from ovfdb.harness.base import AudioOut, Mode
from ovfdb.harness.recorder import resample_pcm16

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.1-flash-live-preview"
ALT_MODELS = (
    "gemini-2.5-flash-native-audio-preview-12-2025",
    "gemini-2.5-flash-native-audio-preview-09-2025",
    "gemini-live-2.5-flash-preview",
)
SPEAK_FIRST_TEXT = "Start speaking now to begin/continue the conversation."
_RATE_RE = re.compile(r"rate=(\d+)")


def _load_api_key(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    from dotenv import load_dotenv
    load_dotenv()
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GeminiLive: GOOGLE_API_KEY is not set (put it in .env, see .env.example)")
    return key


def list_live_models(api_key: str | None = None) -> list[str]:
    """Model ids whose name mentions live/native-audio (for picking a working id)."""
    from google import genai
    client = genai.Client(api_key=_load_api_key(api_key))
    names = []
    for m in client.models.list():
        n = (m.name or "").removeprefix("models/")
        if "live" in n or "native-audio" in n:
            names.append(n)
    return sorted(names)


class GeminiLive:
    name = "gemini_live"

    def __init__(self, model: str = DEFAULT_MODEL, voice: str | None = None, api_key: str | None = None,
                 speak_first_wait_s: float = 2.0, transcribe_output: bool = True,
                 temperature: float | None = None) -> None:
        self.model = model
        self.voice = voice
        self.api_key = api_key
        self.speak_first_wait_s = speak_first_wait_s
        self.transcribe_output = transcribe_output
        self.temperature = temperature
        self.out: asyncio.Queue[AudioOut] = asyncio.Queue()
        self.meta: dict = {"model": model, "output_transcript": [], "interruptions": 0}
        self.errors: list[str] = []
        self._session = None
        self._cm = None
        self._recv_task: asyncio.Task | None = None
        self._kick_task: asyncio.Task | None = None
        self._t0: float | None = None
        self._t_start: float | None = None
        self._audio_received = False
        self._dead = False
        self._n_audio_sent = 0
        self._n_frames_sent = 0

    # --- clock ------------------------------------------------------------

    def _now(self) -> float:
        base = self._t0 if self._t0 is not None else (self._t_start or time.monotonic())
        return time.monotonic() - base

    # --- Agent contract ---------------------------------------------------

    async def start(self, system_prompt: str, mode: Mode, *, agent_speaks_first: bool = False) -> None:
        from google import genai
        from google.genai import types

        key = _load_api_key(self.api_key)
        self._client = genai.Client(api_key=key)
        cfg: dict = {"response_modalities": ["AUDIO"]}
        if system_prompt:
            cfg["system_instruction"] = types.Content(parts=[types.Part(text=system_prompt)])
        if self.transcribe_output:
            cfg["output_audio_transcription"] = types.AudioTranscriptionConfig()
        if self.voice:
            cfg["speech_config"] = types.SpeechConfig(
                voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice)))
        if self.temperature is not None:
            cfg["temperature"] = self.temperature
        config = types.LiveConnectConfig(**cfg)
        self._cm = self._client.aio.live.connect(model=self.model, config=config)
        self._session = await self._cm.__aenter__()
        self._t_start = time.monotonic()
        self.meta["mode"] = mode
        self.meta["agent_speaks_first"] = agent_speaks_first
        self._recv_task = asyncio.create_task(self._recv_loop(), name="gemini-recv")
        if agent_speaks_first:
            self._kick_task = asyncio.create_task(self._kick(), name="gemini-kick")
        else:
            self.meta["speak_first_path"] = "n/a"
        log.info("GeminiLive connected: model=%s mode=%s", self.model, mode)

    async def push_audio(self, pcm16k: bytes, t: float) -> None:
        if self._t0 is None:
            self._t0 = time.monotonic()
        if self._dead or self._session is None:
            return
        from google.genai import types
        try:
            await self._session.send_realtime_input(
                audio=types.Blob(data=pcm16k, mime_type="audio/pcm;rate=16000"))
            self._n_audio_sent += 1
        except Exception as e:  # noqa: BLE001
            self._fail(f"send audio @{t:.2f}: {e!r}")

    async def push_frame(self, jpeg: bytes, t: float) -> None:
        if self._dead or self._session is None:
            return
        from google.genai import types
        try:
            await self._session.send_realtime_input(video=types.Blob(data=jpeg, mime_type="image/jpeg"))
            self._n_frames_sent += 1
        except Exception as e:  # noqa: BLE001
            self._fail(f"send frame @{t:.2f}: {e!r}")

    async def stop(self) -> None:
        for task in (self._kick_task, self._recv_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception) as e:  # noqa: BLE001
                    log.debug("GeminiLive task %s ended: %r", task.get_name(), e)
        self._kick_task = self._recv_task = None
        if self._cm is not None:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception as e:  # noqa: BLE001
                log.debug("GeminiLive close: %r", e)
        self._cm = self._session = None
        self.meta.update(n_audio_sent=self._n_audio_sent, n_frames_sent=self._n_frames_sent,
                         n_transcript_parts=len(self.meta["output_transcript"]))

    # --- internals --------------------------------------------------------

    def _fail(self, msg: str) -> None:
        if not self._dead:
            self._dead = True
            self.errors.append(msg)
            log.error("GeminiLive: %s", msg)

    async def _kick(self) -> None:
        from google.genai import types
        await asyncio.sleep(self.speak_first_wait_s)
        if self._audio_received or self._session is None or self._dead:
            self.meta["speak_first_path"] = "system_prompt_only"
            log.info("GeminiLive: agent spoke within %.1fs of start; no text kick", self.speak_first_wait_s)
            return
        try:
            await self._session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=SPEAK_FIRST_TEXT)]), turn_complete=True)
            self.meta["speak_first_path"] = "text_kick"
            self.meta["text_kick_t"] = round(self._now(), 3)
            log.info("GeminiLive: no audio after %.1fs; sent text kick", self.speak_first_wait_s)
        except Exception as e:  # noqa: BLE001
            self._fail(f"text kick: {e!r}")

    async def _recv_loop(self) -> None:
        assert self._session is not None
        try:
            while not self._dead:
                async for msg in self._session.receive():
                    self._handle(msg)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            self._fail(f"receive: {e!r}")

    def _handle(self, msg) -> None:
        sc = msg.server_content
        if msg.go_away is not None:
            self.errors.append(f"go_away: time_left={msg.go_away.time_left}")
        if sc is None:
            return
        t = self._now()
        if sc.interrupted:
            self.meta["interruptions"] += 1
            self.out.put_nowait(AudioOut(b"", t, flush=True))
        if sc.model_turn and sc.model_turn.parts:
            for part in sc.model_turn.parts:
                blob = part.inline_data
                if blob is None or not blob.data:
                    continue
                m = _RATE_RE.search(blob.mime_type or "")
                sr = int(m.group(1)) if m else 24_000
                pcm = resample_pcm16(blob.data, sr, 16_000)
                if not self._audio_received:
                    self._audio_received = True
                    self.meta["first_audio_t"] = round(t, 3)
                    self.meta["output_rate"] = sr
                self.out.put_nowait(AudioOut(pcm, t))
        tr = sc.output_transcription
        if tr is not None and tr.text:
            self.meta["output_transcript"].append({"t": round(t, 3), "text": tr.text})
