"""Tavus CVI / Anam via headless Chrome (WS6b): the clip is the user's camera+mic, the remote avatar
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
hosted LLM). Env: TAVUS_API_KEY, TAVUS_REPLICA_ID, TAVUS_PERSONA_ID (created on first use and cached in
`.tavus_persona`), ANAM_API_KEY, ANAM_AVATAR_ID, ANAM_VOICE_ID, ANAM_LLM_ID.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
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

_QUOTA_RE = re.compile(r"usage limit|concurrency limit|upgrade your plan|insufficient|credit|quota|exceeded your", re.IGNORECASE)


class VendorQuotaError(RuntimeError):
    """The vendor refused a session for plan/usage reasons: the manifest runner stops on this."""


def _quota_check(msg: str) -> None:
    if _QUOTA_RE.search(msg or ""):
        raise VendorQuotaError(msg)

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
READY_TIMEOUT_S = 90.0
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


# --- the agent -------------------------------------------------------------------

class PlaywrightAvatar:
    """Agent for a browser-SDK avatar vendor. `vendor` = "tavus" | "anam"."""

    def __init__(self, vendor: str, sample, model: str = "", headless: bool = True) -> None:
        if vendor not in ("tavus", "anam"):
            raise ValueError(f"unknown avatar vendor {vendor!r}")
        self.vendor = vendor
        self.name = "tavus_cvi" if vendor == "tavus" else "anam"
        self.sample = sample
        self.headless = headless
        self.out: asyncio.Queue[AudioOut] = asyncio.Queue()
        self.errors: list[str] = []
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
        else:
            key = os.getenv("ANAM_API_KEY") or ""
            if not key:
                raise RuntimeError("ANAM_API_KEY missing in .env")
            self._session = AnamSession(key)
            self.model = model or f"anam/{self._session.avatar_id[:8]}/{self._session.llm_id[:8]}"

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
                elif ev in ("first_audio", "first_video"):
                    self._page_stats[f"{ev}_s"] = o.get("t")
                elif ev == "stopped":
                    self._page_stats.update(o.get("stats") or {})
                    self._stopped.set()
        except websockets.ConnectionClosed:
            pass

    # -- Agent protocol --
    async def start(self, system_prompt: str, mode: Mode, *, agent_speaks_first: bool = False) -> None:
        from playwright.async_api import async_playwright
        clip_s = _wav_seconds(self.sample.user_audio_path)
        max_s = clip_s + 60.0
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
        param = f"room={join}" if self.vendor == "tavus" else f"token={join}"
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
                          "session": getattr(self._session, "conversation_id", "") or "anam"})
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

    async def _teardown(self) -> None:
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
