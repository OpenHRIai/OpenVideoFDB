"""WS6a: OpenAI Realtime provider, offline against a fake WebSocket connection
(event parsing → AudioOut chunks and timestamps, resampling, barge-in, speak-first kick)
plus a `network`-marked real session."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time

import numpy as np
import pytest

from ovfdb.harness.base import AUDIO_SR, AudioOut
from ovfdb.harness.providers.openai_realtime import (
    API_RATE,
    EV_AUDIO_DELTA,
    EV_ERROR,
    EV_RESPONSE_CREATED,
    EV_RESPONSE_DONE,
    EV_SESSION_UPDATED,
    EV_SPEECH_STARTED,
    EV_TRANSCRIPT_DONE,
    SPEAK_FIRST_TEXT,
    OpenAIRealtime,
    StreamResampler,
)
from ovfdb.harness.recorder import resample_pcm16
from ovfdb.harness.streamer import PROVIDERS

# --- fake connection ------------------------------------------------------------

class FakeConn:
    """Stands in for openai's AsyncRealtimeConnection: `send_raw` records client events,
    `recv_bytes` yields server events queued by the test (and auto-acks session.update)."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.inbox: asyncio.Queue[bytes] = asyncio.Queue()
        self.closed = False
        # the server greets a fresh connection with session.created before anything else
        self.push({"type": "session.created", "session": {"id": "sess_1", "model": "gpt-realtime"}})

    async def send_raw(self, data: str | bytes) -> None:
        ev = json.loads(data)
        self.sent.append(ev)
        if ev["type"] == "session.update":
            self.push({"type": EV_SESSION_UPDATED, "session": {"id": "sess_1", "model": "gpt-realtime"}})

    async def recv_bytes(self) -> bytes:
        return await self.inbox.get()

    def push(self, ev: dict) -> None:
        self.inbox.put_nowait(json.dumps(ev).encode())

    async def close(self) -> None:
        self.closed = True


def _sine(dur: float, sr: int, f: float = 440.0, amp: float = 0.5) -> bytes:
    t = np.arange(int(dur * sr)) / sr
    return (amp * 32767 * np.sin(2 * np.pi * f * t)).astype(np.int16).tobytes()


def _delta(pcm24k: bytes, item_id: str = "item_1", response_id: str = "resp_1") -> dict:
    return {"type": EV_AUDIO_DELTA, "delta": base64.b64encode(pcm24k).decode(), "item_id": item_id,
            "response_id": response_id, "content_index": 0, "output_index": 0, "event_id": "ev"}


def _drain(agent: OpenAIRealtime) -> list[AudioOut]:
    items = []
    while not agent.out.empty():
        items.append(agent.out.get_nowait())
    return items


async def _started(conn: FakeConn, prompt: str = "Be brief.", mode: str = "a2a", **kw) -> OpenAIRealtime:
    speak_first = kw.pop("_speak_first", False)
    agent = OpenAIRealtime(**kw)

    async def _open():
        return conn
    agent._open = _open  # type: ignore[method-assign]
    await agent.start(prompt, mode, agent_speaks_first=speak_first)
    return agent


# --- session config -------------------------------------------------------------

async def test_session_update_shape():
    conn = FakeConn()
    agent = await _started(conn, prompt="You are a test partner.", voice="marin")
    await asyncio.sleep(0.05)
    upd = [e for e in conn.sent if e["type"] == "session.update"]
    assert len(upd) == 1
    s = upd[0]["session"]
    assert s["type"] == "realtime"
    assert s["instructions"] == "You are a test partner."
    assert s["output_modalities"] == ["audio"]
    assert s["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert s["audio"]["output"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert s["audio"]["input"]["turn_detection"]["type"] == "server_vad"
    assert s["audio"]["output"]["voice"] == "marin"
    assert agent.meta["session_updated"] is True
    assert agent.meta["session_id"] == "sess_1"
    assert agent.meta["speak_first_path"] == "n/a"
    # no manual commit / response.create under server VAD
    assert not [e for e in conn.sent if e["type"] in ("input_audio_buffer.commit", "response.create")]
    await agent.stop()
    assert conn.closed


# --- audio in -------------------------------------------------------------------

async def test_push_audio_resamples_to_24k_and_appends():
    conn = FakeConn()
    agent = await _started(conn)
    chunk = _sine(0.04, AUDIO_SR)              # one 40 ms streamer chunk (1280 bytes)
    for i in range(5):
        await agent.push_audio(chunk, i * 0.04)
    appends = [e for e in conn.sent if e["type"] == "input_audio_buffer.append"]
    assert len(appends) == 5
    for e in appends:
        assert len(base64.b64decode(e["audio"])) == 1280 * 3 // 2   # 960 samples @ 24 kHz
    assert agent._t0 is not None
    await agent.stop()
    assert agent.meta["n_audio_sent"] == 5
    assert not agent.errors


def test_stream_resampler_matches_whole_buffer_and_keeps_length():
    sr_in, sr_out = AUDIO_SR, API_RATE
    x = _sine(1.0, sr_in, f=300.0)
    whole = np.frombuffer(resample_pcm16(x, sr_in, sr_out), dtype=np.int16).astype(np.float32)
    rs = StreamResampler(sr_in, sr_out)
    chunk = 1280
    parts = [rs.process(x[i:i + chunk]) for i in range(0, len(x), chunk)]
    streamed = np.frombuffer(b"".join(parts), dtype=np.int16).astype(np.float32)
    assert len(streamed) == len(whole) == sr_out
    # ignore the first/last few ms (whole-buffer version has its own edge effects there)
    a, b = whole[200:-200], streamed[200:-200]
    err = np.sqrt(np.mean((a - b) ** 2)) / np.sqrt(np.mean(a ** 2))
    assert err < 0.02, err
    # ... and the round trip back to 16 kHz reproduces the input
    back = np.frombuffer(resample_pcm16(b"".join(parts), sr_out, sr_in), dtype=np.int16).astype(np.float32)
    x_f = np.frombuffer(x, dtype=np.int16).astype(np.float32)
    err2 = np.sqrt(np.mean((back[200:-200] - x_f[200:-200]) ** 2)) / np.sqrt(np.mean(x_f ** 2))
    assert err2 < 0.02, err2


# --- audio out ------------------------------------------------------------------

async def test_audio_delta_to_audioout_with_provider_clock():
    conn = FakeConn()
    agent = await _started(conn)
    await agent.push_audio(b"\x00" * 1280, 0.0)      # starts the provider clock (t=0)
    t0 = agent._t0
    conn.push({"type": EV_RESPONSE_CREATED, "response": {"id": "resp_1"}})
    conn.push(_delta(_sine(0.2, API_RATE)))
    conn.push(_delta(_sine(0.1, API_RATE)))
    conn.push({"type": EV_TRANSCRIPT_DONE, "transcript": "Hello there.", "item_id": "item_1"})
    conn.push({"type": EV_RESPONSE_DONE, "response": {"id": "resp_1", "status": "completed"}})
    await asyncio.sleep(0.1)
    items = _drain(agent)
    assert len(items) == 2
    assert [len(i.pcm16k) for i in items] == [int(0.2 * AUDIO_SR) * 2, int(0.1 * AUDIO_SR) * 2]
    assert all(not i.flush for i in items)
    assert 0.0 <= items[0].t_received <= time.monotonic() - t0 + 1e-6
    assert items[0].t_received <= items[1].t_received
    assert agent.meta["first_audio_t"] == round(items[0].t_received, 3)
    assert agent.meta["output_rate"] == 24000
    assert agent.meta["output_transcript"] == [{"t": pytest.approx(items[1].t_received, abs=0.1),
                                                "text": "Hello there."}]
    assert agent.meta["responses"] == 1 and agent.meta["responses_cancelled"] == 0
    await agent.stop()
    assert not agent.errors


async def test_audio_delta_content_is_resampled_sine():
    conn = FakeConn()
    agent = await _started(conn)
    await agent.push_audio(b"\x00" * 1280, 0.0)
    conn.push(_delta(_sine(0.5, API_RATE, f=440.0)))
    await asyncio.sleep(0.05)
    (item,) = _drain(agent)
    y = np.frombuffer(item.pcm16k, dtype=np.int16).astype(np.float32)
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    peak_hz = np.argmax(spec) * AUDIO_SR / len(y)
    assert abs(peak_hz - 440.0) < 5.0
    await agent.stop()


# --- barge-in -------------------------------------------------------------------

async def test_speech_started_during_response_flushes_and_truncates():
    conn = FakeConn()
    agent = await _started(conn)
    await agent.push_audio(b"\x00" * 1280, 0.0)
    conn.push({"type": EV_RESPONSE_CREATED, "response": {"id": "resp_1"}})
    conn.push(_delta(_sine(1.0, API_RATE)))      # 1000 ms of audio for item_1
    await asyncio.sleep(0.15)                      # "play" ~150 ms of it
    conn.push({"type": EV_SPEECH_STARTED, "audio_start_ms": 1200, "item_id": "item_user"})
    conn.push({"type": EV_RESPONSE_DONE, "response": {"id": "resp_1", "status": "cancelled",
                                                      "status_details": {"type": "cancelled",
                                                                         "reason": "turn_detected"}}})
    await asyncio.sleep(0.05)
    items = _drain(agent)
    assert len(items) == 2
    assert not items[0].flush and items[1].flush and items[1].pcm16k == b""
    assert items[1].t_received >= items[0].t_received
    trunc = [e for e in conn.sent if e["type"] == "conversation.item.truncate"]
    assert len(trunc) == 1
    assert trunc[0]["item_id"] == "item_1" and trunc[0]["content_index"] == 0
    assert 100 <= trunc[0]["audio_end_ms"] <= 1000
    assert agent.meta["interruptions"] == 1
    assert agent.meta["truncations"] == 1
    assert agent.meta["responses_cancelled"] == 1
    await agent.stop()
    assert not agent.errors


async def test_speech_started_without_response_is_not_a_flush():
    conn = FakeConn()
    agent = await _started(conn)
    await agent.push_audio(b"\x00" * 1280, 0.0)
    conn.push({"type": EV_SPEECH_STARTED, "audio_start_ms": 100, "item_id": "item_user"})
    conn.push({"type": "input_audio_buffer.speech_stopped", "audio_end_ms": 900, "item_id": "item_user"})
    await asyncio.sleep(0.05)
    assert _drain(agent) == []
    assert agent.meta["interruptions"] == 0
    assert not [e for e in conn.sent if e["type"] == "conversation.item.truncate"]
    await agent.stop()


async def test_speech_started_with_interrupt_off_only_logs():
    conn = FakeConn()
    agent = await _started(conn, interrupt_response=False)
    upd = next(e for e in conn.sent if e["type"] == "session.update")
    assert upd["session"]["audio"]["input"]["turn_detection"]["interrupt_response"] is False
    await agent.push_audio(b"\x00" * 1280, 0.0)
    conn.push({"type": EV_RESPONSE_CREATED, "response": {"id": "resp_1"}})
    conn.push(_delta(_sine(0.5, API_RATE)))
    conn.push({"type": EV_SPEECH_STARTED, "audio_start_ms": 100, "item_id": "item_user"})
    await asyncio.sleep(0.05)
    items = _drain(agent)
    assert len(items) == 1 and not items[0].flush
    assert agent.meta["interruptions"] == 0
    await agent.stop()


# --- errors ---------------------------------------------------------------------

async def test_error_events_collected_verbatim_and_session_survives():
    conn = FakeConn()
    agent = await _started(conn)
    await agent.push_audio(b"\x00" * 1280, 0.0)
    err = {"type": "invalid_request_error", "code": "unknown_parameter", "message": "Unknown parameter: 'x'.",
           "param": "x", "event_id": "evt_1"}
    conn.push({"type": EV_ERROR, "error": err, "event_id": "ev_err"})
    conn.push(_delta(_sine(0.1, API_RATE)))
    await asyncio.sleep(0.05)
    assert agent.errors == [f"error: {json.dumps(err, sort_keys=True)}"]
    assert len(_drain(agent)) == 1          # error events are not fatal; audio still flows
    assert not agent._dead
    await agent.push_audio(b"\x00" * 1280, 0.04)
    assert len([e for e in conn.sent if e["type"] == "input_audio_buffer.append"]) == 2
    await agent.stop()


async def test_transport_failure_marks_dead_and_reports():
    conn = FakeConn()
    agent = await _started(conn)

    async def boom(data):
        raise OSError("socket gone")
    conn.send_raw = boom  # type: ignore[assignment]
    await agent.push_audio(b"\x00" * 1280, 0.0)
    assert agent._dead
    assert agent.errors and "send audio @0.00" in agent.errors[0]
    await agent.push_audio(b"\x00" * 1280, 0.04)     # silently dropped once dead
    assert len(agent.errors) == 1
    await agent.stop()


# --- video ----------------------------------------------------------------------

async def test_push_frame_av_sends_input_image_item():
    conn = FakeConn()
    agent = await _started(conn, mode="av")
    assert agent.meta["video_path"] == "image_items" and agent.meta["video_supported"] is True
    jpeg = b"\xff\xd8\xff\xe0fakejpeg\xff\xd9"
    await agent.push_frame(jpeg, 0.0)
    await agent.push_frame(jpeg, 1.0)
    items = [e for e in conn.sent if e["type"] == "conversation.item.create"]
    assert len(items) == 2
    it = items[0]["item"]
    assert it["type"] == "message" and it["role"] == "user"
    (part,) = it["content"]
    assert part["type"] == "input_image"
    assert part["image_url"] == "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
    await agent.stop()
    assert agent.meta["n_frames_sent"] == 2 and agent.meta["n_frames_dropped"] == 0


async def test_push_frame_a2a_is_dropped():
    conn = FakeConn()
    agent = await _started(conn, mode="a2a")
    await agent.push_frame(b"jpeg", 0.0)
    assert not [e for e in conn.sent if e["type"] == "conversation.item.create"]
    await agent.stop()
    assert agent.meta["n_frames_sent"] == 0 and agent.meta["n_frames_dropped"] == 1
    assert agent.meta["video_path"] == "n/a"


# --- agent_speaks_first ---------------------------------------------------------

async def test_speak_first_text_kick_when_silent():
    conn = FakeConn()
    agent = await _started(conn, speak_first_wait_s=0.2, _speak_first=True)
    await agent.push_audio(b"\x00" * 1280, 0.0)
    await asyncio.sleep(0.35)
    creates = [e for e in conn.sent if e["type"] == "conversation.item.create"]
    assert len(creates) == 1
    assert creates[0]["item"]["content"] == [{"type": "input_text", "text": SPEAK_FIRST_TEXT}]
    assert conn.sent[-1]["type"] == "response.create"
    assert agent.meta["speak_first_path"] == "text_kick"
    assert 0.15 <= agent.meta["text_kick_t"] <= 0.6
    await agent.stop()


async def test_speak_first_no_kick_when_agent_already_spoke():
    conn = FakeConn()
    agent = await _started(conn, speak_first_wait_s=0.2, _speak_first=True)
    await agent.push_audio(b"\x00" * 1280, 0.0)
    conn.push(_delta(_sine(0.1, API_RATE)))
    await asyncio.sleep(0.35)
    assert not [e for e in conn.sent if e["type"] in ("conversation.item.create", "response.create")]
    assert agent.meta["speak_first_path"] == "system_prompt_only"
    await agent.stop()


# --- registry -------------------------------------------------------------------

def test_registered_in_streamer_with_model_passthrough():
    assert "openai_realtime" in PROVIDERS
    agent = PROVIDERS["openai_realtime"](None, [], "gpt-realtime-mini")  # type: ignore[arg-type]
    assert isinstance(agent, OpenAIRealtime) and agent.model == "gpt-realtime-mini"
    assert PROVIDERS["openai_realtime"](None, [], "").model == "gpt-realtime"  # type: ignore[arg-type]


# --- network --------------------------------------------------------------------

@pytest.mark.network
@pytest.mark.skipif(not (os.environ.get("OPENAI_API_KEY") or os.path.exists(".env")), reason="no API key")
async def test_real_session_speaks_on_text_kick():
    from dotenv import load_dotenv
    load_dotenv()
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    agent = OpenAIRealtime(model="gpt-realtime-mini", speak_first_wait_s=0.5, transcribe_input=False)
    await agent.start("Reply with one short sentence.", "a2a", agent_speaks_first=True)
    silence = b"\x00" * 1280
    t_end = time.monotonic() + 8.0
    i = 0
    while time.monotonic() < t_end and not agent._audio_received:
        await agent.push_audio(silence, i * 0.04)
        i += 1
        await asyncio.sleep(0.04)
    await asyncio.sleep(1.0)
    await agent.stop()
    assert not agent.errors, agent.errors
    assert agent.meta["speak_first_path"] == "text_kick"
    items = _drain(agent)
    assert items and sum(len(i.pcm16k) for i in items) > 0
