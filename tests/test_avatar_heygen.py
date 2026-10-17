"""WS6b HeyGen LiveAvatar: REST session flow (mocked HTTP), per-key context cache, plan session caps,
credit exhaustion before and during a row, plus the run tooling (key-rotation cleanup, memory guard tree).

No network, no browser: LiveAvatar is an httpx.MockTransport, the page WebSocket is a fake iterator, and the
mid-row quota test streams 1 s synthetic clips through a fake agent.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import struct
import sys
from pathlib import Path
from typing import ClassVar

import httpx
import pytest

from ovfdb.harness import streamer
from ovfdb.harness.base import AudioOut
from ovfdb.harness.providers import playwright_avatar as PA
from ovfdb.schema import write_manifest
from tests.test_streamer import _sample

REPO = Path(__file__).resolve().parents[1]


# --- mocked LiveAvatar ---------------------------------------------------------------

class FakeLiveAvatar:
    """Records requests; `token_replies` / `start_replies` are consumed in order (last one repeats)."""

    def __init__(self, token_replies=None, start_replies=None) -> None:
        self.calls: list[tuple[str, str, dict, dict]] = []
        self.n_contexts = 0
        self.token_replies = token_replies or [(200, {"code": 1000, "data": {"session_id": "s-1",
                                                                             "session_token": "tok-1"}})]
        self.start_replies = start_replies or [(201, {"code": 1000, "data": {
            "session_id": "s-1", "livekit_url": "wss://lk.example", "livekit_client_token": "lk-tok",
            "max_session_duration": 110}})]

    @staticmethod
    def _next(replies):
        return replies.pop(0) if len(replies) > 1 else replies[0]

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        self.calls.append((request.method, request.url.path, dict(request.headers), body))
        if request.url.path == "/v1/contexts":
            self.n_contexts += 1
            return httpx.Response(200, json={"code": 1000, "data": {"id": f"ctx-{self.n_contexts}"}})
        if request.url.path == "/v1/sessions/token":
            code, js = self._next(self.token_replies)
            return httpx.Response(code, json=js)
        if request.url.path == "/v1/sessions/start":
            code, js = self._next(self.start_replies)
            return httpx.Response(code, json=js)
        if request.url.path == "/v1/sessions/stop":
            return httpx.Response(200, json={"code": 1000, "data": None})
        return httpx.Response(404, json={"message": "not found"})

    def paths(self) -> list[str]:
        return [c[1] for c in self.calls]

    def bodies(self, path: str) -> list[dict]:
        return [c[3] for c in self.calls if c[1] == path]


@pytest.fixture
def liveavatar(monkeypatch, tmp_path):
    """Route every httpx.AsyncClient in the provider module to a FakeLiveAvatar; cwd = tmp (context cache)."""
    fake = FakeLiveAvatar()
    real = httpx.AsyncClient

    def client(*a, **kw):
        kw["transport"] = httpx.MockTransport(fake.handler)
        return real(*a, **kw)

    monkeypatch.setattr(PA.httpx, "AsyncClient", client)
    monkeypatch.chdir(tmp_path)
    for k in ("HEYGEN_SANDBOX", "HEYGEN_AVATAR_ID", "HEYGEN_VOICE_ID", "HEYGEN_LLM", "HEYGEN_CONTEXT_ID"):
        monkeypatch.delenv(k, raising=False)
    return fake


def cap_error(cap: int, asked: int) -> tuple[int, dict]:
    msg = f"max_session_duration ({asked}s) exceeds the maximum allowed ({cap}s)"
    return 400, {"code": 4000, "data": [{"loc": ["max_session_duration"], "message": msg}], "message": msg}


# --- session flow --------------------------------------------------------------------

async def test_create_full_mode_session(liveavatar):
    s = PA.HeyGenSession("key-A")
    join = await s.create("Be warm and brief.", max_s=110.0, agent_speaks_first=False)

    assert join == "wss://lk.example|lk-tok"
    assert liveavatar.paths() == ["/v1/contexts", "/v1/sessions/token", "/v1/sessions/start"]
    ctx = liveavatar.bodies("/v1/contexts")[0]
    assert ctx["prompt"] == "${system_prompt}" and ctx["opening_text"] == ""
    tok = liveavatar.bodies("/v1/sessions/token")[0]
    assert tok["mode"] == "FULL" and tok["interactivity_type"] == "CONVERSATIONAL"
    assert tok["avatar_id"] == PA.HEYGEN_DEFAULT_AVATAR and tok["is_sandbox"] is False
    assert tok["max_session_duration"] == 110
    assert tok["dynamic_variables"] == {"system_prompt": "Be warm and brief."}
    assert tok["avatar_persona"]["context_id"] == "ctx-1"
    assert tok["avatar_persona"]["llm_settings"] == {"provider": "openai", "model": PA.HEYGEN_DEFAULT_LLM}
    assert "voice_id" not in tok["avatar_persona"]            # avatar's default voice
    hdr = {c[1]: c[2] for c in liveavatar.calls}
    assert hdr["/v1/sessions/token"]["x-api-key"] == "key-A"
    assert hdr["/v1/sessions/start"]["authorization"] == "Bearer tok-1"
    assert s.session_id == "s-1"

    await s.end()
    assert liveavatar.bodies("/v1/sessions/stop") == [{"session_id": "s-1", "reason": "USER_CLOSED"}]


async def test_long_system_prompt_is_truncated_to_the_dynamic_variable_limit(liveavatar):
    await PA.HeyGenSession("key-A").create("x" * 1500, max_s=60.0, agent_speaks_first=False)
    assert len(liveavatar.bodies("/v1/sessions/token")[0]["dynamic_variables"]["system_prompt"]) == 1000


async def test_context_is_cached_per_key(liveavatar):
    await PA.HeyGenSession("key-A").create("p", 60.0, False)
    await PA.HeyGenSession("key-A").create("p", 60.0, False)       # reuses ctx-1
    await PA.HeyGenSession("key-B").create("p", 60.0, False)       # contexts are per account → ctx-2
    assert liveavatar.n_contexts == 2
    cache = json.loads(PA.HEYGEN_CONTEXT_FILE.read_text())
    assert sorted(cache.values()) == ["ctx-1", "ctx-2"] and len(cache) == 2
    assert "key-A" not in PA.HEYGEN_CONTEXT_FILE.read_text()       # fingerprints, not keys
    ctx_ids = [b["avatar_persona"]["context_id"] for b in liveavatar.bodies("/v1/sessions/token")]
    assert ctx_ids == ["ctx-1", "ctx-1", "ctx-2"]


async def test_env_overrides_and_sandbox(liveavatar, monkeypatch):
    monkeypatch.setenv("HEYGEN_SANDBOX", "1")
    monkeypatch.setenv("HEYGEN_VOICE_ID", "voice-9")
    monkeypatch.setenv("HEYGEN_LLM", "gpt-4o-mini")
    s = PA.HeyGenSession("key-A")
    assert s.sandbox and s.avatar_id == PA.HEYGEN_SANDBOX_AVATAR
    await s.create("p", 60.0, False)
    tok = liveavatar.bodies("/v1/sessions/token")[0]
    assert tok["is_sandbox"] is True and tok["avatar_persona"]["voice_id"] == "voice-9"
    assert tok["avatar_persona"]["llm_settings"]["model"] == "gpt-4o-mini"


async def test_end_without_session_is_a_noop(liveavatar):
    await PA.HeyGenSession("key-A").end()
    assert liveavatar.calls == []


# --- plan session cap -----------------------------------------------------------------

async def test_session_cap_retries_at_the_cap_when_the_clip_fits(liveavatar):
    clip = 50.0
    max_s = clip + PA.SESSION_SLACK_S                       # 110 s asked, plan allows 100 s
    liveavatar.token_replies = [cap_error(100, int(max_s)),
                                (200, {"code": 1000, "data": {"session_id": "s-2", "session_token": "tok-2"}})]
    join = await PA.HeyGenSession("key-A").create("p", max_s, False)
    assert join == "wss://lk.example|lk-tok"
    asked = [b["max_session_duration"] for b in liveavatar.bodies("/v1/sessions/token")]
    assert asked == [110, 100]


async def test_session_cap_too_short_for_the_clip_fails_without_retry(liveavatar):
    clip = 112.0                                           # needs 112 + 15 = 127 s > 120 s cap
    max_s = clip + PA.SESSION_SLACK_S
    liveavatar.token_replies = [cap_error(120, int(max_s))]
    with pytest.raises(RuntimeError, match="too short") as e:
        await PA.HeyGenSession("key-A").create("p", max_s, False)
    assert not isinstance(e.value, PA.VendorQuotaError)    # a plan limit, not a credit stop: the run goes on
    assert len(liveavatar.bodies("/v1/sessions/token")) == 1
    assert "/v1/sessions/start" not in liveavatar.paths()


@pytest.mark.parametrize("clip,ok", [(105.0, True), (105.5, False)])
async def test_session_cap_boundary(liveavatar, clip, ok):
    """A 120 s cap holds a clip of up to 120 - HEYGEN_MIN_MARGIN_S = 105 s."""
    max_s = clip + PA.SESSION_SLACK_S
    liveavatar.token_replies = [cap_error(120, int(max_s)),
                                (200, {"code": 1000, "data": {"session_id": "s-3", "session_token": "tok-3"}})]
    if ok:
        await PA.HeyGenSession("key-A").create("p", max_s, False)
        assert liveavatar.bodies("/v1/sessions/token")[-1]["max_session_duration"] == 120
    else:
        with pytest.raises(RuntimeError, match="too short"):
            await PA.HeyGenSession("key-A").create("p", max_s, False)


# --- credit exhaustion ------------------------------------------------------------------

async def test_no_credits_on_start_raises_vendor_quota(liveavatar):
    liveavatar.start_replies = [(403, {"code": 4033, "data": None,
                                       "message": "No credits available for start session"})]
    with pytest.raises(PA.VendorQuotaError):
        await PA.HeyGenSession("key-A").create("p", 60.0, False)


async def test_no_credits_on_token_raises_vendor_quota(liveavatar):
    liveavatar.token_replies = [(402, {"code": 4033, "data": None, "message": "Insufficient credits"})]
    with pytest.raises(PA.VendorQuotaError):
        await PA.HeyGenSession("key-A").create("p", 60.0, False)


async def test_other_token_errors_are_plain_runtime_errors(liveavatar):
    liveavatar.token_replies = [(401, {"code": 4001, "data": None, "message": "Invalid API key"})]
    with pytest.raises(RuntimeError) as e:
        await PA.HeyGenSession("key-A").create("p", 60.0, False)
    assert not isinstance(e.value, PA.VendorQuotaError) and "401" in str(e.value)


@pytest.mark.parametrize("msg,quota", [
    ("No credits available for start session", True),
    ("NO_CREDITS", True),
    ("Usage limit reached", True),
    ("max_session_duration (138s) exceeds the maximum allowed (120s)", False),
    ("Concurrency limit", False),
    ("Invalid API key", False),
])
def test_quota_regex(msg, quota):
    assert bool(PA._QUOTA_RE.search(msg)) is quota


# --- page events --------------------------------------------------------------------------

class FakeWS:
    def __init__(self, msgs) -> None:
        self.msgs = list(msgs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.msgs:
            raise StopAsyncIteration
        return self.msgs.pop(0)


def _agent(monkeypatch, tmp_path) -> PA.PlaywrightAvatar:
    monkeypatch.setenv("HEYGEN_API_KEY", "key-A")
    return PA.PlaywrightAvatar("heygen", _sample(tmp_path, "h_c00", 1.0))


async def test_page_vendor_stopped_no_credits_sets_quota_hit(monkeypatch, tmp_path):
    a = _agent(monkeypatch, tmp_path)
    assert a.name == "heygen" and a.model.startswith("liveavatar/") and a.quota_hit == ""
    pcm = b"\x01\x00" * 320
    audio = bytes([1]) + struct.pack("<d", 2.5) + pcm          # 0x01 + float64 t + PCM16
    await a._ws_handler(FakeWS([json.dumps({"ev": "ready", "video": {"width": 1280}}), audio,
                                json.dumps({"ev": "vendor_stopped", "reason": "NO_CREDITS"})]))
    assert a.quota_hit == "NO_CREDITS"
    assert a.errors == ["vendor ended session: NO_CREDITS"]
    out: AudioOut = a.out.get_nowait()
    assert out.t_received == pytest.approx(2.5) and out.pcm16k == pcm


async def test_page_vendor_stopped_other_reason_is_only_an_error(monkeypatch, tmp_path):
    a = _agent(monkeypatch, tmp_path)
    await a._ws_handler(FakeWS([json.dumps({"ev": "vendor_stopped", "reason": "MAX_DURATION_REACHED"})]))
    assert a.quota_hit == "" and a.errors == ["vendor ended session: MAX_DURATION_REACHED"]


# --- runner: credits run out mid-row ---------------------------------------------------------

class QuotaMidRowAgent:
    """Echo-free agent whose vendor ends the session for credits during the row."""

    name = "fake_quota"
    calls: ClassVar[list[str]] = []

    def __init__(self, clip_id: str) -> None:
        self.clip_id = clip_id
        self.out: asyncio.Queue[AudioOut] = asyncio.Queue()
        self.errors: list[str] = []
        self.meta: dict = {}
        self.quota_hit = ""

    async def start(self, system_prompt, mode, *, agent_speaks_first=False) -> None:
        QuotaMidRowAgent.calls.append(self.clip_id)

    async def push_audio(self, pcm16k, t) -> None:
        if t >= 0.5 and not self.quota_hit:
            self.quota_hit = "NO_CREDITS"
            self.errors.append("vendor ended session: NO_CREDITS")

    async def push_frame(self, jpeg, t) -> None:
        return None

    async def stop(self) -> None:
        return None


def test_run_manifest_stops_and_leaves_the_row_when_credits_end_mid_row(tmp_path, monkeypatch):
    samples = [_sample(tmp_path, f"q_c0{i}", 1.0) for i in range(3)]
    manifest = tmp_path / "m.jsonl"
    write_manifest(samples, manifest)
    QuotaMidRowAgent.calls = []
    monkeypatch.setitem(streamer.PROVIDERS, "fake_quota", lambda s, ss, m: QuotaMidRowAgent(s.clip_id))
    out = tmp_path / "runs"

    runs = streamer.run_manifest(manifest, provider="fake_quota", mode="a2a", out=out, tail_s=0.2)

    assert runs == []
    assert QuotaMidRowAgent.calls == ["q_c00"]                     # aborted: later rows never started
    assert not (out / "q_c00" / "run.json").exists()               # the cut row re-runs on resume
    assert not (out / "q_c01").exists() and not (out / "q_c02").exists()


# --- run tooling ---------------------------------------------------------------------------------

def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_key_rotation_cleanup_removes_only_unusable_rows(tmp_path, monkeypatch):
    rk = _load_script("run_avatar_keys")
    monkeypatch.setattr(rk, "OUT", tmp_path)
    rows = {"ok": [], "start": ["start: RuntimeError('LiveAvatar session cap 120s ... too short')"],
            "notready": ["page: heygen: avatar not ready after 90s"],
            "novideo": ["page did not confirm stop", "no video recorded"],
            "drift": ["push_audio@3.00: RuntimeError('x')"]}
    for name, errs in rows.items():
        (tmp_path / name).mkdir()
        (tmp_path / name / "run.json").write_text(json.dumps({"errors": errs}))
    assert rk.n_done() == 5
    assert rk.clean_failed_starts() == 3
    assert sorted(p.name for p in tmp_path.iterdir()) == ["drift", "ok"]


def test_memguard_harness_trees_follow_descendants_not_lookalikes():
    mg = _load_script("memguard")
    pw = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome --remote-debugging-pipe --headless"
    helper = "Google Chrome Helper (Renderer) --type=renderer --remote-debugging-pipe"
    procs = {
        10: (9, "python -c streamer.run_manifest"),
        11: (10, pw),                       # harness browser root
        12: (11, helper),                   # helpers carry the flag too
        13: (11, "Google Chrome Helper (GPU) --type=gpu-process"),
        14: (13, "Google Chrome Helper --type=utility"),
        20: (1, "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),   # the user's Chrome
        21: (20, "Google Chrome Helper (Renderer) --type=renderer"),
    }
    trees = mg.harness_trees(procs)
    assert list(trees) == [11] and trees[11] == {11, 12, 13, 14}
    assert mg.short(helper) == "Google Chrome Helper (Renderer)[renderer]"
    assert mg.footprint_mb(10**7) == 0.0                         # no such pid → 0, no exception
