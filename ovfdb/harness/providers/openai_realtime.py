"""OpenAI Realtime provider (WebSocket, GA protocol): 16 kHz PCM audio in (resampled to
24 kHz), JPEG frames as `input_image` conversation items, 24 kHz PCM audio out
(resampled to 16 kHz before it reaches the recorder).

Transport (openai 3.x, checked against the installed package):
  AsyncOpenAI().realtime.connect(model=...)  →  AsyncRealtimeConnection
  conn.send_raw(json)  /  conn.recv_bytes()   (plain JSON events; no typed wrappers so
  the parser is trivially testable with a fake connection).

Event names are the GA ones from `openai.types.realtime` (not the 2024 beta names):
  client → server: session.update, input_audio_buffer.append, conversation.item.create,
                   conversation.item.truncate, response.create
  server → client: session.created / session.updated, response.created,
                   response.output_audio.delta, response.output_audio_transcript.done,
                   input_audio_buffer.speech_started / speech_stopped, response.done,
                   conversation.item.input_audio_transcription.completed, error

Server VAD is kept (that *is* the full-duplex behaviour under test): no commit /
response.create is sent except for the agent_speaks_first text kick. With
`turn_detection.interrupt_response=true` (the default) a `speech_started` during an
in-progress response makes the server cancel it (`response.done` status=cancelled,
reason=turn_detected). That is forwarded to the recorder as a flush (a real client
empties its playback queue on `speech_started`) and the item is truncated server-side
(`conversation.item.truncate`) to the audio "played" so far, as the docs prescribe.

Video: the user-message content union has `input_image` (data-URI PNG/JPEG), so in AV
mode every `push_frame` becomes one `conversation.item.create` user item
(`meta["video_path"] = "image_items"`). The model sees those items in its next
response; there is no continuous video stream like Gemini Live.

agent_speaks_first: if no audio has arrived within `speak_first_wait_s` (2 s) of
start(), one user text item "Start speaking now to begin/continue the conversation."
plus `response.create` is sent; `meta["speak_first_path"]` records which path was taken.

Model ids (from the SDK's session `model` literal): `gpt-realtime`, `gpt-realtime-mini`,
dated variants, and `gpt-4o-realtime-preview*`. Override with `ovfdb run --model ...`.

Spec: plans/WS6-providers-avatar.md §6a.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time

import numpy as np

from ovfdb.harness.base import AudioOut, Mode
from ovfdb.harness.recorder import resample_pcm16

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-realtime"
ALT_MODELS = ("gpt-realtime-mini", "gpt-realtime-2025-08-28", "gpt-4o-realtime-preview")
API_RATE = 24_000          # the only PCM rate the Realtime API accepts (both directions)
LOCAL_RATE = 16_000
SPEAK_FIRST_TEXT = "Start speaking now to begin/continue the conversation."
SESSION_READY_WAIT_S = 1.5

# Exact server event types handled (GA names, see openai.types.realtime.*).
EV_AUDIO_DELTA = "response.output_audio.delta"
EV_TRANSCRIPT_DONE = "response.output_audio_transcript.done"
EV_SPEECH_STARTED = "input_audio_buffer.speech_started"
EV_SPEECH_STOPPED = "input_audio_buffer.speech_stopped"
EV_RESPONSE_CREATED = "response.created"
EV_RESPONSE_DONE = "response.done"
EV_INPUT_TRANSCRIPT = "conversation.item.input_audio_transcription.completed"
EV_SESSION_CREATED = "session.created"
EV_SESSION_UPDATED = "session.updated"
EV_ERROR = "error"


def _load_api_key(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    from dotenv import load_dotenv
    load_dotenv()
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OpenAIRealtime: OPENAI_API_KEY is not set (put it in .env, see .env.example)")
    return key


class StreamResampler:
    """Chunk-wise int16 resampler with a short input context so chunk boundaries don't
    get the FIR edge effect of a stateless `resample_pcm16` call on every 40 ms chunk.

    The previous `context` input samples are prepended to each chunk, the block is
    resampled, and the output that corresponds to the context is dropped. The trailing
    edge of each chunk is still filtered against zeros (~0.6 ms of the default FIR),
    which is negligible; the lead edge — where the stateless version produced a step
    every chunk — is now exact.
    """

    def __init__(self, sr_in: int, sr_out: int, context: int = 64) -> None:
        self.sr_in, self.sr_out = sr_in, sr_out
        self.context = context
        self._tail = np.zeros(0, dtype=np.int16)
        self.n_in = 0
        self.n_out = 0

    def process(self, pcm: bytes) -> bytes:
        if self.sr_in == self.sr_out or not pcm:
            return pcm
        x = np.frombuffer(pcm, dtype=np.int16)
        ctx = self._tail
        block = np.concatenate([ctx, x]) if len(ctx) else x
        y = np.frombuffer(resample_pcm16(block.tobytes(), self.sr_in, self.sr_out), dtype=np.int16)
        # exact length bookkeeping so the output stream never drifts against the input
        want_total = (self.n_in + len(x)) * self.sr_out // self.sr_in
        skip = len(y) - (want_total - self.n_out)
        y = y[max(0, skip):]
        self._tail = x[-self.context:] if len(x) >= self.context else np.concatenate([ctx, x])[-self.context:]
        self.n_in += len(x)
        self.n_out += len(y)
        return y.tobytes()


class OpenAIRealtime:
    name = "openai_realtime"

    def __init__(self, model: str = DEFAULT_MODEL, voice: str | None = None, api_key: str | None = None,
                 speak_first_wait_s: float = 2.0, transcribe_input: bool = True,
                 interrupt_response: bool = True, image_detail: str = "auto") -> None:
        self.model = model
        self.voice = voice
        self.api_key = api_key
        self.speak_first_wait_s = speak_first_wait_s
        self.transcribe_input = transcribe_input
        self.interrupt_response = interrupt_response
        self.image_detail = image_detail
        self.out: asyncio.Queue[AudioOut] = asyncio.Queue()
        self.meta: dict = {"model": model, "output_transcript": [], "input_transcript": [], "interruptions": 0,
                           "responses": 0, "responses_cancelled": 0, "truncations": 0, "video_supported": True,
                           "api_rate": API_RATE, "event_counts": {}}
        self.errors: list[str] = []
        self._client = None
        self._cm = None
        self._conn = None
        self._recv_task: asyncio.Task | None = None
        self._kick_task: asyncio.Task | None = None
        self._t0: float | None = None
        self._t_start: float | None = None
        self._audio_received = False
        self._dead = False
        self._closed = False
        self._mode: Mode = "a2a"
        self._n_audio_sent = 0
        self._n_frames_sent = 0
        self._n_frames_dropped = 0
        self._session_ready = asyncio.Event()
        self._in_resampler = StreamResampler(LOCAL_RATE, API_RATE)
        # in-progress response bookkeeping (for barge-in flush + truncate)
        self._response_id: str | None = None
        self._item_id: str | None = None
        self._item_content_index = 0
        self._item_first_t: float | None = None
        self._item_bytes_24k = 0

    # --- clock ------------------------------------------------------------

    def _now(self) -> float:
        base = self._t0 if self._t0 is not None else (self._t_start or time.monotonic())
        return time.monotonic() - base

    # --- Agent contract ---------------------------------------------------

    async def start(self, system_prompt: str, mode: Mode, *, agent_speaks_first: bool = False) -> None:
        self._mode = mode
        self._conn = await self._open()
        self._t_start = time.monotonic()
        self.meta["mode"] = mode
        self.meta["agent_speaks_first"] = agent_speaks_first
        self.meta["video_path"] = "image_items" if mode == "av" else "n/a"
        self._recv_task = asyncio.create_task(self._recv_loop(), name="openai-recv")
        await self._send(self._session_update(system_prompt))
        try:
            await asyncio.wait_for(self._session_ready.wait(), SESSION_READY_WAIT_S)
        except TimeoutError:
            log.warning("OpenAIRealtime: no session.updated within %.1fs; streaming anyway", SESSION_READY_WAIT_S)
            self.meta["session_updated"] = False
        if agent_speaks_first:
            self._kick_task = asyncio.create_task(self._kick(), name="openai-kick")
        else:
            self.meta["speak_first_path"] = "n/a"
        log.info("OpenAIRealtime connected: model=%s mode=%s", self.model, mode)

    async def push_audio(self, pcm16k: bytes, t: float) -> None:
        if self._t0 is None:
            self._t0 = time.monotonic()
        if self._dead or self._conn is None:
            return
        pcm24k = self._in_resampler.process(pcm16k)
        if not pcm24k:
            return
        try:
            await self._send({"type": "input_audio_buffer.append",
                              "audio": base64.b64encode(pcm24k).decode("ascii")})
            self._n_audio_sent += 1
        except Exception as e:  # noqa: BLE001
            self._fail(f"send audio @{t:.2f}: {e!r}")

    async def push_frame(self, jpeg: bytes, t: float) -> None:
        if self._dead or self._conn is None or self._mode != "av":
            self._n_frames_dropped += 1
            return
        item = {"type": "message", "role": "user",
                "content": [{"type": "input_image", "detail": self.image_detail,
                             "image_url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")}]}
        try:
            await self._send({"type": "conversation.item.create", "item": item})
            self._n_frames_sent += 1
        except Exception as e:  # noqa: BLE001
            self._fail(f"send frame @{t:.2f}: {e!r}")

    async def stop(self) -> None:
        self._closed = True
        for task in (self._kick_task, self._recv_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception) as e:  # noqa: BLE001
                    log.debug("OpenAIRealtime task %s ended: %r", task.get_name(), e)
        self._kick_task = self._recv_task = None
        if self._cm is not None:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception as e:  # noqa: BLE001
                log.debug("OpenAIRealtime close: %r", e)
        elif self._conn is not None:
            try:
                await self._conn.close()
            except Exception as e:  # noqa: BLE001
                log.debug("OpenAIRealtime close: %r", e)
        self._cm = self._conn = None
        self.meta.update(n_audio_sent=self._n_audio_sent, n_frames_sent=self._n_frames_sent,
                         n_frames_dropped=self._n_frames_dropped,
                         n_transcript_parts=len(self.meta["output_transcript"]))

    # --- connection -------------------------------------------------------

    async def _open(self):
        """Open the WebSocket via the SDK; returns an object with send_raw/recv_bytes/close.
        Tests replace this method with one returning a fake connection."""
        from openai import AsyncOpenAI
        key = _load_api_key(self.api_key)
        self._client = AsyncOpenAI(api_key=key)
        self._cm = self._client.realtime.connect(model=self.model)
        return await self._cm.__aenter__()

    async def _send(self, event: dict) -> None:
        assert self._conn is not None
        await self._conn.send_raw(json.dumps(event))

    def _session_update(self, system_prompt: str) -> dict:
        audio_in: dict = {"format": {"type": "audio/pcm", "rate": API_RATE},
                          "turn_detection": {"type": "server_vad", "create_response": True,
                                             "interrupt_response": self.interrupt_response}}
        if self.transcribe_input:
            audio_in["transcription"] = {"model": "gpt-4o-mini-transcribe"}
        audio_out: dict = {"format": {"type": "audio/pcm", "rate": API_RATE}}
        if self.voice:
            audio_out["voice"] = self.voice
        session: dict = {"type": "realtime", "output_modalities": ["audio"],
                         "audio": {"input": audio_in, "output": audio_out}}
        if system_prompt:
            session["instructions"] = system_prompt
        return {"type": "session.update", "session": session}

    # --- internals --------------------------------------------------------

    def _fail(self, msg: str) -> None:
        if not self._dead:
            self._dead = True
            self.errors.append(msg)
            log.error("OpenAIRealtime: %s", msg)

    async def _kick(self) -> None:
        await asyncio.sleep(self.speak_first_wait_s)
        if self._audio_received or self._conn is None or self._dead:
            self.meta["speak_first_path"] = "system_prompt_only"
            log.info("OpenAIRealtime: agent spoke within %.1fs of start; no text kick", self.speak_first_wait_s)
            return
        try:
            await self._send({"type": "conversation.item.create",
                              "item": {"type": "message", "role": "user",
                                       "content": [{"type": "input_text", "text": SPEAK_FIRST_TEXT}]}})
            await self._send({"type": "response.create"})
            self.meta["speak_first_path"] = "text_kick"
            self.meta["text_kick_t"] = round(self._now(), 3)
            log.info("OpenAIRealtime: no audio after %.1fs; sent text kick", self.speak_first_wait_s)
        except Exception as e:  # noqa: BLE001
            self._fail(f"text kick: {e!r}")

    async def _recv_loop(self) -> None:
        assert self._conn is not None
        try:
            while not self._dead:
                raw = await self._conn.recv_bytes()
                try:
                    ev = json.loads(raw)
                except ValueError:
                    self.errors.append(f"unparseable message ({len(raw)} bytes)")
                    continue
                await self._handle(ev)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            if self._closed or type(e).__name__ == "ConnectionClosedOK":
                log.debug("OpenAIRealtime: connection closed: %r", e)
            else:
                self._fail(f"receive: {e!r}")

    async def _handle(self, ev: dict) -> None:
        typ = ev.get("type", "")
        counts = self.meta["event_counts"]
        counts[typ] = counts.get(typ, 0) + 1
        t = self._now()
        if typ == EV_AUDIO_DELTA:
            raw = base64.b64decode(ev.get("delta", ""))
            if not raw:
                return
            item_id = ev.get("item_id")
            if item_id != self._item_id:
                self._item_id = item_id
                self._item_content_index = int(ev.get("content_index", 0))
                self._item_first_t = t
                self._item_bytes_24k = 0
            self._item_bytes_24k += len(raw)
            pcm = resample_pcm16(raw, API_RATE, LOCAL_RATE)
            if not self._audio_received:
                self._audio_received = True
                self.meta["first_audio_t"] = round(t, 3)
                self.meta["output_rate"] = API_RATE
            self.out.put_nowait(AudioOut(pcm, t))
        elif typ == EV_TRANSCRIPT_DONE:
            text = ev.get("transcript") or ""
            if text:
                self.meta["output_transcript"].append({"t": round(t, 3), "text": text})
        elif typ == EV_SPEECH_STARTED:
            await self._on_speech_started(t, ev)
        elif typ == EV_RESPONSE_CREATED:
            self._response_id = (ev.get("response") or {}).get("id")
            self.meta["responses"] += 1
        elif typ == EV_RESPONSE_DONE:
            resp = ev.get("response") or {}
            status = resp.get("status")
            details = resp.get("status_details") or {}
            if status == "cancelled":
                self.meta["responses_cancelled"] += 1
            elif status in ("failed", "incomplete"):
                self.errors.append(f"response.done status={status} details={json.dumps(details)}")
            self._response_id = None
            self._item_id = None
            self._item_first_t = None
        elif typ == EV_INPUT_TRANSCRIPT:
            text = ev.get("transcript") or ""
            if text:
                self.meta["input_transcript"].append({"t": round(t, 3), "text": text.strip()})
        elif typ == EV_SESSION_CREATED:
            self.meta["session_id"] = (ev.get("session") or {}).get("id")
        elif typ == EV_SESSION_UPDATED:
            self.meta["session_updated"] = True
            sess = ev.get("session") or {}
            self.meta["session_model"] = sess.get("model")
            self._session_ready.set()
        elif typ == EV_ERROR:
            err = ev.get("error") or {}
            self.errors.append(f"error: {json.dumps(err, sort_keys=True)}")
            log.error("OpenAIRealtime error event: %s", err)

    async def _on_speech_started(self, t: float, ev: dict) -> None:
        """Barge-in: user speech while a response is streaming. With interrupt_response the
        server cancels the response; a real client stops playback here, so flush the
        recorder queue and tell the server how much of the item was heard."""
        if self._response_id is None or self._item_id is None or self._item_first_t is None:
            log.debug("OpenAIRealtime: speech_started (no response in progress) at %.2f", t)
            return
        if not self.interrupt_response:
            log.info("OpenAIRealtime: speech_started during response at %.2f (interrupt_response off; no flush)", t)
            return
        self.meta["interruptions"] += 1
        self.out.put_nowait(AudioOut(b"", t, flush=True))
        received_ms = int(self._item_bytes_24k / 2 / API_RATE * 1000)
        played_ms = max(0, int((t - self._item_first_t) * 1000))
        audio_end_ms = min(received_ms, played_ms)
        try:
            await self._send({"type": "conversation.item.truncate", "item_id": self._item_id,
                              "content_index": self._item_content_index, "audio_end_ms": audio_end_ms})
            self.meta["truncations"] += 1
        except Exception as e:  # noqa: BLE001
            self._fail(f"truncate: {e!r}")
        log.info("OpenAIRealtime: barge-in at %.2f (item %s, heard %d ms of %d)", t, self._item_id,
                 audio_end_ms, received_ms)
        # the server will send response.done(status=cancelled); don't truncate the same item twice
        self._item_id = None
        self._item_first_t = None
