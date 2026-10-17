"""Tavus CVI / Anam / HeyGen LiveAvatar via headless Chrome (WS6b): the clip is the user's camera+mic, the remote avatar
track is recorded.

How it works (see `ovfdb/harness/web/avatar.html`):
- Python creates the vendor session (Tavus: persona + conversation → Daily room URL; Anam: session token),
  serves the page + the clip over a local HTTP server, opens a WebSocket for the page, and launches
  headless Chrome (`channel="chrome"`, so VP9/H.264/AAC all decode).
- The page builds the user's MediaStream from the clip (video element capture + the wav decoded into a
  16 kHz AudioContext), joins the vendor with it, and waits for the avatar's remote video+audio tracks.
- On the streamer's first `push_audio` the page starts clip playback (clip t=0 = page `t0`), starts a
  MediaRecorder on the remote tracks (→ `agent.webm` → `agent.mp4`, t=0 aligned with the clip) and an
  AudioWorklet that ships the remote audio as 16 kHz PCM chunks with clip-relative timestamps → `AudioOut`.
- The streamer's own audio/frame pushes are ignored (the page is the sender); `stop()` ends the
  recording, converts the webm, ends the vendor session and closes the browser.

Vendors: `tavus` (full CVI pipeline: Raven perception sees the user video → AV2AV; default LLM
tavus-gemma-4, stock Phoenix-4.5 replica) and `anam` (audio-only input → A2AV; stock Cara-4 avatar,
hosted LLM) and `heygen` (LiveAvatar FULL mode over LiveKit: the clip's audio is published as the user's
mic, no video in → A2AV; stock "Helen (Friendly)", LiveAvatar-hosted OpenAI LLM). Env: TAVUS_API_KEY,
TAVUS_REPLICA_ID, TAVUS_PERSONA_ID (created on first use and cached in `.tavus_persona`), ANAM_API_KEY,
ANAM_AVATAR_ID, ANAM_VOICE_ID, ANAM_LLM_ID, HEYGEN_API_KEY (the LiveAvatar key from app.liveavatar.com, not the
HeyGen platform key), HEYGEN_AVATAR_ID, HEYGEN_VOICE_ID, HEYGEN_LLM, HEYGEN_SANDBOX (1 = free sandbox avatar only).
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import hashlib
import http.server
import json
import logging
import os
import re
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import httpx
import websockets

from ovfdb.harness.base import AudioOut, Mode

log = logging.getLogger("ovfdb.avatar")

_QUOTA_RE = re.compile(r"usage limit|insufficient|credit|quota|exceeded your|NO_CREDITS", re.IGNORECASE)
_BUSY_RE = re.compile(r"concurrency limit", re.IGNORECASE)      # previous session not yet released: retry
BUSY_RETRY_S = 25.0
BUSY_RETRIES = 4


class VendorQuotaError(RuntimeError):
    """The vendor refused a session for plan/usage reasons: the manifest runner stops on this."""


def _quota_check(msg: str) -> None:
    if _QUOTA_RE.search(msg or ""):
        raise VendorQuotaError(msg)

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
READY_TIMEOUT_S = 90.0
SESSION_SLACK_S = 60.0           # vendor session max = clip + this (billing is by time actually used)
STOP_TIMEOUT_S = 30.0

TAVUS_BASE = "https://tavusapi.com/v2"
TAVUS_DEFAULT_REPLICA = "r213e42b45b3"          # "Helen - Casual", phoenix-4.5 stock
TAVUS_PERSONA_FILE = Path(".tavus_persona")
TAVUS_PERSONA_PROMPT = ("You are taking part in a casual one-to-one video call. Follow the instructions given in the "
                        "conversational context exactly; they describe who you are and how to behave.")

ANAM_BASE = "https://api.anam.ai/v1"
ANAM_DEFAULT_AVATAR = "edf6fdcb-acab-44b8-b974-ded72665ee26"   # "Mia" (studio), cara-4 stock
ANAM_DEFAULT_VOICE = "90919e2e-4fc0-11f1-84b0-52bacf74fa75"    # "Michelle - Empathetic Voice"
ANAM_DEFAULT_LLM = "27cbd128-f1e6-4b67-8ab3-9123659be08c"      # "Gemini 3 Flash Preview" (Anam-hosted)

HEYGEN_BASE = "https://api.liveavatar.com/v1"
HEYGEN_DEFAULT_AVATAR = "0cbed480-e2e3-453e-a85d-3cd69b97e2b2"  # "Helen (Friendly)", stock, its default voice
HEYGEN_SANDBOX_AVATAR = "dd73ea75-1218-4ef3-92ce-606d5f7fbc0a"  # the only avatar sandbox sessions render
HEYGEN_DEFAULT_LLM = "gpt-5.4-nano"                              # LiveAvatar's managed default (OpenAIModelEnum)
HEYGEN_MIN_MARGIN_S = 15.0       # clip + 5 s streamer tail + join/teardown must fit inside a capped session
HEYGEN_CONTEXT_FILE = Path(".heygen_context")    # JSON {key fingerprint: context id}; contexts are per account
#: One stored context for every row; the row's system prompt (≤ 424 chars on NVIDIA, limit 1000) is
#: substituted per session through `dynamic_variables`. Empty opening text: who speaks first is the
#: harness's call (a `avatar.speak_response` kick, as the Gemini/OpenAI providers do with a text turn).
HEYGEN_CONTEXT_PROMPT = "${system_prompt}"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


# --- vendor sessions ------------------------------------------------------------

class TavusSession:
    def __init__(self, api_key: str, replica_id: str = "", persona_id: str = "") -> None:
        self.h = {"x-api-key": api_key, "Content-Type": "application/json"}
        self.replica_id = replica_id or os.getenv("TAVUS_REPLICA_ID") or TAVUS_DEFAULT_REPLICA
        self.persona_id = persona_id or os.getenv("TAVUS_PERSONA_ID") or ""
        self.conversation_id = ""
        self.room_url = ""

    async def ensure_persona(self, client: httpx.AsyncClient) -> str:
        if self.persona_id:
            return self.persona_id
        if TAVUS_PERSONA_FILE.exists():
            self.persona_id = TAVUS_PERSONA_FILE.read_text().strip()
            return self.persona_id
        body = {"persona_name": "ovfdb-harness", "pipeline_mode": "full", "system_prompt": TAVUS_PERSONA_PROMPT,
                "default_replica_id": self.replica_id}
        r = await client.post(f"{TAVUS_BASE}/personas", headers=self.h, json=body)
        r.raise_for_status()
        self.persona_id = r.json()["persona_id"]
        TAVUS_PERSONA_FILE.write_text(self.persona_id)
        log.info("Tavus: created persona %s", self.persona_id)
        return self.persona_id

    async def create(self, system_prompt: str, max_s: float, agent_speaks_first: bool) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            await self.ensure_persona(client)
            body = {"replica_id": self.replica_id, "persona_id": self.persona_id,
                    "conversational_context": system_prompt,
                    "properties": {"max_call_duration": int(max_s), "participant_left_timeout": 5,
                                   "enable_recording": False}}
            if not agent_speaks_first:
                body["custom_greeting"] = " "       # replicas greet on join by default; keep it silent
            r = await client.post(f"{TAVUS_BASE}/conversations", headers=self.h, json=body)
            if r.status_code >= 400:
                _quota_check(r.text)
                raise RuntimeError(f"Tavus create conversation {r.status_code}: {r.text[:300]}")
            d = r.json()
            self.conversation_id, self.room_url = d["conversation_id"], d["conversation_url"]
            log.info("Tavus: conversation %s %s", self.conversation_id, self.room_url)
            return self.room_url

    async def end(self) -> None:
        if not self.conversation_id:
            return
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{TAVUS_BASE}/conversations/{self.conversation_id}/end", headers=self.h)
            log.info("Tavus: end conversation %s → %s", self.conversation_id, r.status_code)


class AnamSession:
    def __init__(self, api_key: str, avatar_id: str = "", voice_id: str = "", llm_id: str = "") -> None:
        self.h = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self.avatar_id = avatar_id or os.getenv("ANAM_AVATAR_ID") or ANAM_DEFAULT_AVATAR
        self.voice_id = voice_id or os.getenv("ANAM_VOICE_ID") or ANAM_DEFAULT_VOICE
        self.llm_id = llm_id or os.getenv("ANAM_LLM_ID") or ANAM_DEFAULT_LLM
        self.token = ""

    async def create(self, system_prompt: str, max_s: float, agent_speaks_first: bool) -> str:
        body = {"personaConfig": {"name": "ovfdb", "avatarId": self.avatar_id, "voiceId": self.voice_id,
                                  "llmId": self.llm_id, "systemPrompt": system_prompt,
                                  "maxSessionLengthSeconds": int(max_s), "skipGreeting": not agent_speaks_first},
                "sessionOptions": {"sessionReplay": {"enabled": False}}}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{ANAM_BASE}/auth/session-token", headers=self.h, json=body)
            if r.status_code >= 400:
                _quota_check(r.text)
                raise RuntimeError(f"Anam session token {r.status_code}: {r.text[:300]}")
            self.token = r.json()["sessionToken"]
            return self.token

    async def end(self) -> None:
        return None


class HeyGenSession:
    """LiveAvatar FULL mode: POST /sessions/token (API key) → POST /sessions/start (session token) → LiveKit."""

    def __init__(self, api_key: str, avatar_id: str = "", voice_id: str = "", llm: str = "") -> None:
        self.h = {"X-API-KEY": api_key, "Content-Type": "application/json"}
        self.key_fp = hashlib.sha256(api_key.encode()).hexdigest()[:12]
        self.sandbox = os.getenv("HEYGEN_SANDBOX", "0").strip().lower() in ("1", "true", "yes")
        default = HEYGEN_SANDBOX_AVATAR if self.sandbox else HEYGEN_DEFAULT_AVATAR
        self.avatar_id = avatar_id or os.getenv("HEYGEN_AVATAR_ID") or default
        self.voice_id = voice_id or os.getenv("HEYGEN_VOICE_ID") or ""
        self.llm = llm or os.getenv("HEYGEN_LLM") or HEYGEN_DEFAULT_LLM
        self.context_id = os.getenv("HEYGEN_CONTEXT_ID") or ""
        self.session_id = ""
        self.session_token = ""

    @staticmethod
    def _err(r: httpx.Response, what: str) -> RuntimeError:
        _quota_check(r.text)
        return RuntimeError(f"LiveAvatar {what} {r.status_code}: {r.text[:300]}")

    async def ensure_context(self, client: httpx.AsyncClient) -> str:
        if self.context_id:
            return self.context_id
        cache = json.loads(HEYGEN_CONTEXT_FILE.read_text()) if HEYGEN_CONTEXT_FILE.exists() else {}
        if cache.get(self.key_fp):
            self.context_id = cache[self.key_fp]
            return self.context_id
        body = {"name": "ovfdb-harness", "prompt": HEYGEN_CONTEXT_PROMPT, "opening_text": ""}
        r = await client.post(f"{HEYGEN_BASE}/contexts", headers=self.h, json=body)
        if r.status_code >= 400:
            raise self._err(r, "create context")
        self.context_id = r.json()["data"]["id"]
        cache[self.key_fp] = self.context_id
        HEYGEN_CONTEXT_FILE.write_text(json.dumps(cache))
        log.info("HeyGen: created context %s", self.context_id)
        return self.context_id

    async def create(self, system_prompt: str, max_s: float, agent_speaks_first: bool) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            await self.ensure_context(client)
            persona = {"context_id": self.context_id, "language": "en",
                       "llm_settings": {"provider": "openai", "model": self.llm}}
            if self.voice_id:
                persona["voice_id"] = self.voice_id
            body = {"mode": "FULL", "avatar_id": self.avatar_id, "is_sandbox": self.sandbox,
                    "video_settings": {"quality": "high", "encoding": "H264"},
                    "max_session_duration": int(max_s), "avatar_persona": persona,
                    "interactivity_type": "CONVERSATIONAL",
                    "dynamic_variables": {"system_prompt": system_prompt[:1000]}}
            r = await client.post(f"{HEYGEN_BASE}/sessions/token", headers=self.h, json=body)
            cap = re.search(r"maximum allowed \((\d+)s\)", r.text) if r.status_code == 400 else None
            if cap:
                # plan-level session cap (e.g. 120 s): fine if the clip + tail still fits with a margin
                cap_s = int(cap.group(1))
                if cap_s < max_s - SESSION_SLACK_S + HEYGEN_MIN_MARGIN_S:
                    raise RuntimeError(f"LiveAvatar session cap {cap_s}s on this key is too short for this clip "
                                       f"(needs {max_s - SESSION_SLACK_S + HEYGEN_MIN_MARGIN_S:.0f}s)")
                body["max_session_duration"] = cap_s
                r = await client.post(f"{HEYGEN_BASE}/sessions/token", headers=self.h, json=body)
            if r.status_code >= 400 or not (r.json().get("data") or {}).get("session_token"):
                raise self._err(r, "session token")
            d = r.json()["data"]
            self.session_id, self.session_token = d["session_id"], d["session_token"]
            r = await client.post(f"{HEYGEN_BASE}/sessions/start",
                                  headers={"Authorization": f"Bearer {self.session_token}"})
            if r.status_code >= 400 or not (r.json().get("data") or {}).get("livekit_client_token"):
                raise self._err(r, "start session")
            d = r.json()["data"]
            log.info("HeyGen: session %s (max %ss)", self.session_id, d.get("max_session_duration"))
            return f"{d['livekit_url']}|{d['livekit_client_token']}"

    async def end(self) -> None:
        if not self.session_id:
            return
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{HEYGEN_BASE}/sessions/stop", headers=self.h,
                                  json={"session_id": self.session_id, "reason": "USER_CLOSED"})
            log.info("HeyGen: stop session %s → %s", self.session_id, r.status_code)


# --- the agent -------------------------------------------------------------------

class PlaywrightAvatar:
    """Agent for a browser-SDK avatar vendor. `vendor` = "tavus" | "anam" | "heygen"."""

    def __init__(self, vendor: str, sample, model: str = "", headless: bool = True) -> None:
        if vendor not in ("tavus", "anam", "heygen"):
            raise ValueError(f"unknown avatar vendor {vendor!r}")
        self.vendor = vendor
        self.name = {"tavus": "tavus_cvi", "anam": "anam", "heygen": "heygen"}[vendor]
        self.sample = sample
        self.headless = headless
        self.out: asyncio.Queue[AudioOut] = asyncio.Queue()
        self.errors: list[str] = []
        self.quota_hit = ""              # set when the vendor ends a session for credits: the runner stops
        self.meta: dict = {}
        self.out_dir: Path | None = None
        self.agent_video_path: str | None = None
        self.trust_stamp_s = 60.0        # page timestamps are clip-relative; the streamer loop may stall under load
        self._started = False
        self._ws = None
        self._ws_server = None
        self._http = None
        self._tmp: Path | None = None
        self._pw = None
        self._browser = None
        self._page = None
        self._ready = asyncio.Event()
        self._stopped = asyncio.Event()
        self._webm: bytes | None = None
        self._page_stats: dict = {}
        self._session = None
        from dotenv import load_dotenv
        load_dotenv()
        if vendor == "tavus":
            key = os.getenv("TAVUS_API_KEY") or ""
            if not key:
                raise RuntimeError("TAVUS_API_KEY missing in .env")
            self._session = TavusSession(key)
            self.model = model or f"tavus-cvi/{self._session.replica_id}"
        elif vendor == "anam":
            key = os.getenv("ANAM_API_KEY") or ""
            if not key:
                raise RuntimeError("ANAM_API_KEY missing in .env")
            self._session = AnamSession(key)
            self.model = model or f"anam/{self._session.avatar_id[:8]}/{self._session.llm_id[:8]}"
        else:
            key = os.getenv("HEYGEN_API_KEY") or ""
            if not key:
                raise RuntimeError("HEYGEN_API_KEY (LiveAvatar key) missing in .env")
            self._session = HeyGenSession(key)
            self.model = model or f"liveavatar/{self._session.avatar_id[:8]}/{self._session.llm}"

    def set_out_dir(self, out_dir: str | Path) -> None:
        self.out_dir = Path(out_dir)

    # -- local servers --
    def _serve_http(self) -> int:
        self._tmp = Path(tempfile.mkdtemp(prefix="ovfdb_avatar_"))
        shutil.copy(WEB_DIR / "avatar.html", self._tmp / "avatar.html")
        os.symlink(Path(self.sample.user_video_path).resolve(), self._tmp / "user.mp4")
        os.symlink(Path(self.sample.user_audio_path).resolve(), self._tmp / "user.wav")
        port = _free_port()
        handler = functools.partial(_Quiet, directory=str(self._tmp))
        self._http = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        threading.Thread(target=self._http.serve_forever, daemon=True).start()
        return port

    async def _ws_handler(self, ws) -> None:
        self._ws = ws
        try:
            async for msg in ws:
                if isinstance(msg, bytes):
                    if msg[0] == 1:
                        t = struct.unpack_from("<d", msg, 1)[0]
                        await self.out.put(AudioOut(pcm16k=bytes(msg[9:]), t_received=max(0.0, t)))
                    elif msg[0] == 2:
                        self._webm = bytes(msg[1:])
                    continue
                o = json.loads(msg)
                ev = o.get("ev")
                if ev == "log":
                    log.info("%s page: %s", self.name, o.get("msg"))
                elif ev == "ready":
                    self._page_stats["remote_video"] = o.get("video")
                    self._ready.set()
                elif ev == "error":
                    self.errors.append(f"page: {o.get('msg')}")
                    self._ready.set()
                elif ev == "started":
                    self._page_stats["rec_start_s"] = o.get("rec_start_s")
                elif ev == "vendor_stopped":
                    reason = str(o.get("reason") or "")
                    self.errors.append(f"vendor ended session: {reason}")
                    if _QUOTA_RE.search(reason):
                        self.quota_hit = reason
                elif ev in ("first_audio", "first_video"):
                    self._page_stats[f"{ev}_s"] = o.get("t")
                elif ev == "stopped":
                    self._page_stats.update(o.get("stats") or {})
                    self._stopped.set()
        except websockets.ConnectionClosed:
            pass

    # -- Agent protocol --
    async def start(self, system_prompt: str, mode: Mode, *, agent_speaks_first: bool = False) -> None:
        clip_s = _wav_seconds(self.sample.user_audio_path)
        max_s = clip_s + SESSION_SLACK_S
        for attempt in range(BUSY_RETRIES + 1):
            try:
                await self._start_once(system_prompt, max_s, agent_speaks_first)
                return
            except RuntimeError as e:
                if attempt < BUSY_RETRIES and _BUSY_RE.search(str(e)):
                    log.warning("%s: vendor busy (%s); retry %d in %.0fs", self.name, str(e)[:80], attempt + 1, BUSY_RETRY_S)
                    await self._teardown(keep_session=False)
                    self._reset()
                    await asyncio.sleep(BUSY_RETRY_S)
                    continue
                raise

    def _reset(self) -> None:
        self._ready = asyncio.Event()
        self._stopped = asyncio.Event()
        self._ws = None
        self.errors = []

    async def _start_once(self, system_prompt: str, max_s: float, agent_speaks_first: bool) -> None:
        from playwright.async_api import async_playwright
        join = await self._session.create(system_prompt, max_s, agent_speaks_first)
        http_port = self._serve_http()
        ws_port = _free_port()
        self._ws_server = await websockets.serve(self._ws_handler, "127.0.0.1", ws_port, max_size=None)
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            channel="chrome", headless=self.headless,
            args=["--autoplay-policy=no-user-gesture-required", "--use-fake-ui-for-media-stream",
                  "--disable-features=WebRtcHideLocalIpsWithMdns"])
        ctx = await self._browser.new_context(viewport={"width": 1280, "height": 720})
        self._page = await ctx.new_page()
        self._page.on("console", lambda m: log.debug("%s console: %s", self.name, m.text))
        self._page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))
        from urllib.parse import quote
        if self.vendor == "tavus":
            param = f"room={join}"
        elif self.vendor == "anam":
            param = f"token={join}"
        else:
            lk_url, lk_token = join.split("|", 1)
            param = f"lk={quote(lk_url, safe='')}&token={lk_token}&kick={int(agent_speaks_first)}"
        url = (f"http://127.0.0.1:{http_port}/avatar.html?vendor={self.vendor}&ws={ws_port}"
               f"&video=/user.mp4&audio=/user.wav&{param}")
        t_join = time.monotonic()
        await self._page.goto(url)
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=READY_TIMEOUT_S)
        except TimeoutError:
            raise RuntimeError(f"{self.name}: avatar not ready after {READY_TIMEOUT_S:.0f}s")
        if self.errors:
            _quota_check(self.errors[-1])
            raise RuntimeError(self.errors[-1])
        self.meta.update({"vendor": self.vendor, "join_s": round(time.monotonic() - t_join, 2),
                          "session": getattr(self._session, "conversation_id", "")
                          or getattr(self._session, "session_id", "") or "anam"})
        log.info("%s: avatar ready after %.1fs", self.name, self.meta["join_s"])

    async def push_audio(self, pcm16k: bytes, t: float) -> None:
        if not self._started:
            self._started = True
            if self._ws is None:
                raise RuntimeError("page websocket not connected")
            await self._ws.send(json.dumps({"cmd": "go"}))

    async def push_frame(self, jpeg: bytes, t: float) -> None:
        return None

    async def stop(self) -> None:
        try:
            if self._ws is not None and self._started:
                await self._ws.send(json.dumps({"cmd": "stop"}))
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stopped.wait(), timeout=STOP_TIMEOUT_S)
                if not self._stopped.is_set():
                    self.errors.append("page did not confirm stop")
            self.meta.update({k: (round(v, 3) if isinstance(v, float) else v) for k, v in self._page_stats.items()})
            if self._webm and self.out_dir is not None:
                self.out_dir.mkdir(parents=True, exist_ok=True)
                webm = self.out_dir / "agent.webm"
                webm.write_bytes(self._webm)
                mp4 = self.out_dir / "agent.mp4"
                ok = await asyncio.to_thread(_webm_to_mp4, webm, mp4)
                if ok:
                    self.agent_video_path = str(mp4)
                    webm.unlink(missing_ok=True)
                else:
                    self.errors.append("ffmpeg webm→mp4 failed; kept agent.webm")
                    self.agent_video_path = str(webm)
            elif not self._webm:
                self.errors.append("no video recorded")
        finally:
            await self._teardown()

    async def _teardown(self, keep_session: bool = False) -> None:
        if not keep_session:
            with contextlib.suppress(Exception):
                await self._session.end()
        with contextlib.suppress(Exception):
            if self._browser:
                await self._browser.close()
        with contextlib.suppress(Exception):
            if self._pw:
                await self._pw.stop()
        with contextlib.suppress(Exception):
            if self._ws_server:
                self._ws_server.close()
                await self._ws_server.wait_closed()
        with contextlib.suppress(Exception):
            if self._http:
                self._http.shutdown()
        with contextlib.suppress(Exception):
            if self._tmp:
                shutil.rmtree(self._tmp, ignore_errors=True)


def _wav_seconds(path: str) -> float:
    import soundfile as sf
    info = sf.info(path)
    return info.frames / info.samplerate


def _webm_to_mp4(webm: Path, mp4: Path) -> bool:
    # WebRTC tracks change resolution mid-call (e.g. 427x240 → 1280x720); normalise so libx264 accepts them.
    vf = "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-fflags", "+genpts", "-i", str(webm), "-vf", vf, "-r", "30",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(mp4)]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        log.error("ffmpeg: %s", r.stderr[-400:])
        return False
    return mp4.exists() and mp4.stat().st_size > 0
