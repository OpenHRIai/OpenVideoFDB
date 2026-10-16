"""Human annotator page for mined clips (plans/WS2-mining.md "Review page").

`ovfdb review --manifest manifest/ovfdb_v1.jsonl` serves a single-page app on localhost:
the side-by-side clip (USER left, PARTNER right) with the dynamic window marked on a
timeline, "play window" / "play clip" controls, the mined cue, the rule evidence, the VLM
verdict, both speakers' words with the in-window ones highlighted (so the partner's real
reaction is visible), and accept / reject / unsure buttons with keyboard shortcuts.

Decisions append to `data/mining/review_<manifest stem>.jsonl` (latest per (clip_id, bucket)
wins); `ovfdb review-apply` writes a manifest with rejected rows dropped and corrected
windows applied. Standard library only (http.server with Range support for video seeking);
media is served from the clip directories named in the manifest and never leaves the machine.
"""

from __future__ import annotations

import json
import mimetypes
import re
import threading
import webbrowser
from datetime import UTC, datetime
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import unquote, urlparse

from ovfdb.schema import Sample, Word, read_manifest, write_manifest

DECISIONS = ("accept", "reject", "unsure")
REVIEW_DIR = Path("data/mining")


def review_path(manifest: str | Path) -> Path:
    return REVIEW_DIR / f"review_{Path(manifest).stem}.jsonl"


# --- decisions ------------------------------------------------------------------------

def load_decisions(path: str | Path) -> dict[tuple[str, str], dict]:
    """{(clip_id, bucket): latest decision record}."""
    out: dict[tuple[str, str], dict] = {}
    p = Path(path)
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            out[(d["clip_id"], d["bucket"])] = d
    return out


def record_decision(path: str | Path, clip_id: str, bucket: str, decision: str, note: str = "",
                    start_s: float | None = None, end_s: float | None = None) -> dict:
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}, got {decision!r}")
    d = {"clip_id": clip_id, "bucket": bucket, "decision": decision, "note": (note or "").strip()[:1000],
         "start_s": None if start_s is None else round(float(start_s), 3),
         "end_s": None if end_s is None else round(float(end_s), 3),
         "ts": datetime.now(UTC).isoformat(timespec="seconds")}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")
    return d


def apply_decisions(manifest: str | Path, review: str | Path, out: str | Path, *,
                    keep_unreviewed: bool = True) -> tuple[int, int, int]:
    """Write `out`: rejected rows dropped, corrected windows applied, decision noted in `source_meta`.

    Returns (kept, dropped, window_fixed). Unreviewed rows are kept unless `keep_unreviewed=False`.
    """
    decisions = load_decisions(review)
    kept: list[Sample] = []
    dropped = fixed = 0
    for s in read_manifest(manifest):
        d = decisions.get((s.clip_id, s.bucket.value))
        if d is None:
            if keep_unreviewed:
                kept.append(s)
            else:
                dropped += 1
            continue
        if d["decision"] == "reject":
            dropped += 1
            continue
        has_fix = d.get("start_s") is not None and d.get("end_s") is not None and d["end_s"] > d["start_s"]
        if has_fix and (abs(d["start_s"] - s.dynamic_start_s) > 1e-3 or abs(d["end_s"] - s.dynamic_end_s) > 1e-3):
            t0 = float(s.source_meta.get("t0", 0.0))
            s.dynamic_start_s, s.dynamic_end_s = float(d["start_s"]), float(d["end_s"])
            s.source_meta["dynamic_start_raw_s"] = round(t0 + s.dynamic_start_s, 3)
            s.source_meta["dynamic_end_raw_s"] = round(t0 + s.dynamic_end_s, 3)
            fixed += 1
        s.source_meta["review"] = {"decision": d["decision"], "note": d.get("note", ""), "ts": d.get("ts")}
        kept.append(s)
    write_manifest(kept, out)
    return len(kept), dropped, fixed


# --- rows --------------------------------------------------------------------------------

def _partner_words(s: Sample) -> list[Word]:
    """The partner's transcript words in clip time (Seamless per-channel transcript, local cache)."""
    meta = s.source_meta or {}
    pid, t0, t1 = meta.get("partner_file_id"), meta.get("t0"), meta.get("t1")
    if not pid or t0 is None or t1 is None:
        return []
    try:
        from ovfdb.data import seamless as sm
        got = sm.fetch(pid, ("transcript",))
        if "transcript" not in got:
            return []
        return sm.rebase_words(sm.transcript_words(sm.read_transcript(got["transcript"])), float(t0), float(t1))
    except Exception:  # noqa: BLE001 - the page must work without the data layer
        return []


def _cue(s: Sample) -> str:
    try:
        from ovfdb.score.judge import cue_line
        return cue_line(s) or ""
    except Exception:  # noqa: BLE001
        return ""


def build_rows(manifest: str | Path) -> list[dict]:
    rows = []
    for s in read_manifest(manifest):
        clip_dir = Path(s.user_video_path).parent
        sbs = clip_dir / "sbs.mp4"
        meta = s.source_meta or {}
        rows.append({
            "clip_id": s.clip_id, "bucket": s.bucket.value, "dynamic_type": s.dynamic_type.value,
            "agent_role": s.agent_role.value, "ds": round(s.dynamic_start_s, 3), "de": round(s.dynamic_end_s, 3),
            "duration": round(s.duration_s, 3), "agent_speaks_first": s.agent_speaks_first,
            "video": f"/media/{sbs if sbs.exists() else Path(s.user_video_path)}",
            "sbs": sbs.exists(),
            "cue": _cue(s),
            "evidence": meta.get("evidence", {}), "mining_rule": meta.get("mining_rule", ""),
            "verify": meta.get("verify", {}),
            "user_words": [{"t": round(w.start, 2), "e": round(w.end, 2), "w": w.text} for w in s.user_words],
            "partner_words": [{"t": round(w.start, 2), "e": round(w.end, 2), "w": w.text} for w in _partner_words(s)],
            "caption": s.av_caption or "",
            "system_prompt": s.system_prompt or "",
        })
    return rows


# --- server ------------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    rows: ClassVar[list[dict]] = []
    review_file: ClassVar[Path] = Path("review.jsonl")
    roots: ClassVar[list[Path]] = []

    def log_message(self, fmt, *args):  # quiet
        pass

    def _json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif u.path == "/api/rows":
            dec = load_decisions(self.review_file)
            for r in self.rows:
                r["decision"] = dec.get((r["clip_id"], r["bucket"]))
            self._json({"rows": self.rows, "review_file": str(self.review_file)})
        elif u.path.startswith("/media/"):
            self._media(unquote(u.path[len("/media/"):]))
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        data = json.loads(self.rfile.read(n) or b"{}")
        if u.path == "/api/review":
            try:
                d = record_decision(self.review_file, data["clip_id"], data["bucket"], data["decision"],
                                    data.get("note", ""), data.get("start_s"), data.get("end_s"))
            except (KeyError, ValueError) as e:
                self._json({"error": str(e)}, 400)
                return
            self._json({"ok": True, "decision": d})
        else:
            self._json({"error": "not found"}, 404)

    def _media(self, rel: str) -> None:
        p = Path(rel).resolve()
        if not any(str(p).startswith(str(root)) for root in self.roots) or not p.is_file():
            self._json({"error": "forbidden"}, 403)
            return
        size = p.stat().st_size
        ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        status = 200
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                    if m.group(2):
                        end = min(int(m.group(2)), size - 1)
                elif m.group(2):
                    start = max(0, size - int(m.group(2)))
                status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with p.open("rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(1 << 20, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remaining -= len(chunk)


def serve(manifest: str | Path, port: int = 8765, review: str | Path | None = None, open_browser: bool = True) -> None:
    rows = build_rows(manifest)
    if not rows:
        raise SystemExit(f"no rows in {manifest}")
    roots = sorted({Path(r["video"][len("/media/"):]).resolve().parent.parent for r in rows})
    handler = partial(_Handler)
    _Handler.rows = rows
    _Handler.review_file = Path(review) if review else review_path(manifest)
    _Handler.roots = roots
    httpd = None
    for p in range(port, port + 20):              # the requested port may be busy: take the next free one
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", p), handler)
            port = p
            break
        except OSError:
            continue
    if httpd is None:
        raise SystemExit(f"no free port in {port}-{port + 19}")
    url = f"http://127.0.0.1:{port}/"
    print(f"review: {len(rows)} rows from {manifest}; decisions -> {_Handler.review_file}\nopen {url}  (Ctrl-C to stop)")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


# --- page ---------------------------------------------------------------------------------

PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>OpenVideoFDB review</title>
<style>
:root{--bg:#f6f7f9;--fg:#1c1e21;--muted:#6b7280;--card:#fff;--line:#e5e7eb;--win:#f59e0b;--ok:#16a34a;--bad:#dc2626;--unsure:#2563eb}
@media(prefers-color-scheme:dark){:root{--bg:#111318;--fg:#e8eaed;--muted:#9aa0a6;--card:#1b1e24;--line:#2a2e36}}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 system-ui,sans-serif;background:var(--bg);color:var(--fg);display:grid;grid-template-columns:300px 1fr;height:100vh}
aside{border-right:1px solid var(--line);overflow:auto;padding:10px}main{overflow:auto;padding:14px 18px}
h1{font-size:15px;margin:0 0 8px}select,input,textarea,button{font:inherit;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:4px 8px}
button{cursor:pointer}button.primary{font-weight:600}
.row{padding:5px 6px;border-radius:6px;cursor:pointer;display:flex;gap:6px;align-items:center}.row:hover{background:var(--line)}.row.sel{background:var(--line);font-weight:600}
.dot{width:9px;height:9px;border-radius:50%;background:var(--muted);flex:none}.dot.accept{background:var(--ok)}.dot.reject{background:var(--bad)}.dot.unsure{background:var(--unsure)}
.grp{margin:10px 0 2px;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
video{width:100%;max-height:52vh;background:#000;border-radius:8px}
.bar{position:relative;height:14px;background:var(--line);border-radius:4px;margin:6px 0 10px;cursor:pointer}.bar .win{position:absolute;top:0;bottom:0;background:var(--win);opacity:.7}.bar .pos{position:absolute;top:-3px;width:2px;height:20px;background:var(--fg)}
.ctl{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px}.kbd{font:12px ui-monospace,monospace;color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin:8px 0}
.words{display:flex;flex-wrap:wrap;gap:3px 4px;font-size:13px}.words span{padding:0 3px;border-radius:3px;cursor:pointer}.words span.in{background:var(--win);color:#000}.words span.near{outline:1px dashed var(--win)}
.decide button{padding:6px 14px}.decide .accept{border-color:var(--ok)}.decide .reject{border-color:var(--bad)}.decide .unsure{border-color:var(--unsure)}
.meta{color:var(--muted);font-size:12px}details summary{cursor:pointer;color:var(--muted)}pre{white-space:pre-wrap;font-size:12px}
.badge{display:inline-block;padding:1px 7px;border-radius:10px;font-size:12px;border:1px solid var(--line)}
</style></head><body>
<aside>
<h1>OpenVideoFDB review</h1>
<div class="meta" id="progress"></div>
<div style="margin:6px 0"><select id="fDyn"><option value="">all dynamics</option></select> <select id="fStatus"><option value="">all</option><option value="todo">unreviewed</option><option value="accept">accepted</option><option value="reject">rejected</option><option value="unsure">unsure</option></select></div>
<div id="list"></div>
</aside>
<main>
<div id="title" style="font-size:16px;font-weight:600;margin-bottom:6px"></div>
<video id="v" controls preload="auto"></video>
<div class="bar" id="bar"><div class="win" id="win"></div><div class="pos" id="pos"></div></div>
<div class="ctl">
<button class="primary" id="bWin">▶ window ±2 s <span class="kbd">W</span></button>
<button id="bClip">▶ whole clip <span class="kbd">C</span></button>
<button id="bPause">⏯ <span class="kbd">space</span></button>
<label>speed <select id="rate"><option>0.5</option><option selected>1</option><option>1.5</option></select></label>
<span class="meta">window <b id="winTxt"></b> · clip <span id="durTxt"></span> · <span id="role"></span></span>
</div>
<div class="card decide">
<button class="accept" id="bAcc">✓ accept <span class="kbd">A</span></button>
<button class="reject" id="bRej">✗ reject <span class="kbd">R</span></button>
<button class="unsure" id="bUns">? unsure <span class="kbd">U</span></button>
<span class="meta">then <span class="kbd">J</span>/<span class="kbd">K</span> prev/next · <span class="kbd">N</span> next unreviewed</span>
<div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
<label>fix window: start <input id="fixS" size="6"></label><label>end <input id="fixE" size="6"></label><button id="bReset">reset</button>
<input id="note" placeholder="note (optional)" style="flex:1;min-width:220px">
</div>
<div class="meta" id="saved"></div>
</div>
<div class="card"><b>Mined cue</b><div id="cue"></div><div class="meta" id="rule"></div></div>
<div class="card"><b>USER words</b> <span class="meta">(click a word to seek; highlighted = inside the window)</span><div class="words" id="uw"></div></div>
<div class="card"><b>PARTNER words</b> <span class="meta">(the real human reaction — what we measure, not what we select on)</span><div class="words" id="pw"></div></div>
<div class="card"><b>VLM verdict</b> <span id="vlm"></span></div>
<div class="card"><details><summary>rule evidence</summary><pre id="ev"></pre></details><details><summary>AV caption</summary><pre id="cap"></pre></details><details><summary>agent system prompt</summary><pre id="sp"></pre></details></div>
</main>
<script>
let rows=[],cur=-1,stopAt=null;
const $=id=>document.getElementById(id);const v=$('v');
const key=r=>r.clip_id+'|'+r.bucket;
async function load(){const j=await (await fetch('/api/rows')).json();rows=j.rows;
 const dyns=[...new Set(rows.map(r=>r.dynamic_type))].sort();$('fDyn').innerHTML='<option value="">all dynamics</option>'+dyns.map(d=>`<option>${d}</option>`).join('');
 renderList();if(cur<0){const i=rows.findIndex(r=>!r.decision);select(i>=0?i:0);}else select(cur);}
function visible(){const d=$('fDyn').value,s=$('fStatus').value;return rows.map((r,i)=>[r,i]).filter(([r])=>(!d||r.dynamic_type===d)&&(!s||(s==='todo'?!r.decision:(r.decision&&r.decision.decision===s))));}
function renderList(){const vis=visible();let html='',g='';for(const [r,i] of vis){const grp=r.dynamic_type+' / '+r.bucket;if(grp!==g){g=grp;html+=`<div class="grp">${grp}</div>`;}
 const dec=r.decision?r.decision.decision:'';html+=`<div class="row ${i===cur?'sel':''}" data-i="${i}"><span class="dot ${dec}"></span><span>${r.clip_id.replace(/^V\d+_/,'')}</span></div>`;}
 $('list').innerHTML=html;document.querySelectorAll('.row').forEach(e=>e.onclick=()=>select(+e.dataset.i));
 const n=rows.length,done=rows.filter(r=>r.decision).length,acc=rows.filter(r=>r.decision&&r.decision.decision==='accept').length,rej=rows.filter(r=>r.decision&&r.decision.decision==='reject').length;
 $('progress').textContent=`${done}/${n} reviewed · ${acc} accepted · ${rej} rejected`;}
function fmt(t){return t.toFixed(2)+'s'}
function select(i){if(i<0||i>=rows.length)return;cur=i;const r=rows[i];stopAt=null;
 $('title').textContent=`${r.dynamic_type} · ${r.bucket} · ${r.clip_id}`;
 if(v.getAttribute('src')!==r.video){v.src=r.video;}
 $('winTxt').textContent=`${fmt(r.ds)} – ${fmt(r.de)}`;$('durTxt').textContent=fmt(r.duration);$('role').textContent=`agent role ${r.agent_role}${r.agent_speaks_first?' · agent speaks first':''}${r.sbs?'':' · (user pane only)'}`;
 $('win').style.left=(100*r.ds/r.duration)+'%';$('win').style.width=(100*(r.de-r.ds)/r.duration)+'%';
 $('cue').textContent=r.cue||'(no mined cue)';$('rule').textContent='rule: '+(r.mining_rule||'?');
 $('uw').innerHTML=words(r.user_words,r);$('pw').innerHTML=r.partner_words.length?words(r.partner_words,r):'<span class="meta">(no partner transcript available)</span>';
 document.querySelectorAll('.words span[data-t]').forEach(e=>e.onclick=()=>{v.currentTime=Math.max(0,+e.dataset.t-0.3);v.play();});
 const vl=r.verify||{};$('vlm').innerHTML=vl.notes?`<span class="badge">${vl.is_dynamic?'is dynamic':'not dynamic'} · conf ${(vl.confidence||0).toFixed(2)}${vl.refined?' · window refined':''}</span> ${vl.notes}`:'<span class="meta">(not verified)</span>';
 $('ev').textContent=JSON.stringify(r.evidence,null,1);$('cap').textContent=r.caption||'(none)';$('sp').textContent=r.system_prompt||'(none)';
 const d=r.decision;$('fixS').value=d&&d.start_s!=null?d.start_s:r.ds;$('fixE').value=d&&d.end_s!=null?d.end_s:r.de;$('note').value=d?d.note||'':'';
 $('saved').textContent=d?`saved: ${d.decision} at ${d.ts}`:'';renderList();
 const el=document.querySelector('.row.sel');if(el)el.scrollIntoView({block:'nearest'});
 v.onloadeddata=()=>playWindow();if(v.readyState>=2)playWindow();}
function words(ws,r){return ws.map(w=>{const cls=(w.e>r.ds&&w.t<r.de)?'in':((w.e>r.ds-2&&w.t<r.de+2)?'near':'');return `<span class="${cls}" data-t="${w.t}" title="${fmt(w.t)}">${w.w}</span>`}).join(' ');}
function playWindow(){const r=rows[cur];v.currentTime=Math.max(0,r.ds-2);stopAt=Math.min(r.duration,r.de+2);v.play();}
function playClip(){stopAt=null;v.currentTime=0;v.play();}
v.ontimeupdate=()=>{const r=rows[cur];if(!r)return;$('pos').style.left=(100*v.currentTime/r.duration)+'%';if(stopAt!==null&&v.currentTime>=stopAt){v.pause();stopAt=null;}};
$('bar').onclick=e=>{const r=rows[cur];const x=(e.clientX-e.currentTarget.getBoundingClientRect().left)/e.currentTarget.clientWidth;stopAt=null;v.currentTime=x*r.duration;v.play();};
$('rate').onchange=()=>v.playbackRate=+$('rate').value;
async function decide(dec){const r=rows[cur];const s=parseFloat($('fixS').value),e=parseFloat($('fixE').value);
 const body={clip_id:r.clip_id,bucket:r.bucket,decision:dec,note:$('note').value,start_s:isNaN(s)?null:s,end_s:isNaN(e)?null:e};
 const j=await (await fetch('/api/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
 if(j.ok){r.decision=j.decision;$('saved').textContent=`saved: ${dec}`;renderList();}else alert(j.error);}
function next(unreviewed){const vis=visible().map(([r,i])=>i);let k=vis.indexOf(cur);for(let s=1;s<=vis.length;s++){const i=vis[(k+s)%vis.length];if(!unreviewed||!rows[i].decision){select(i);return;}}}
function prev(){const vis=visible().map(([r,i])=>i);const k=vis.indexOf(cur);select(vis[(k-1+vis.length)%vis.length]);}
$('bWin').onclick=playWindow;$('bClip').onclick=playClip;$('bPause').onclick=()=>v.paused?v.play():v.pause();
$('bAcc').onclick=()=>decide('accept');$('bRej').onclick=()=>decide('reject');$('bUns').onclick=()=>decide('unsure');
$('bReset').onclick=()=>{const r=rows[cur];$('fixS').value=r.ds;$('fixE').value=r.de;};
$('fDyn').onchange=$('fStatus').onchange=()=>{renderList();const vis=visible();if(vis.length&&!vis.some(([r,i])=>i===cur))select(vis[0][1]);};
document.addEventListener('keydown',e=>{if(['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName))return;
 const k=e.key.toLowerCase();if(k==='a')decide('accept');else if(k==='r')decide('reject');else if(k==='u')decide('unsure');else if(k==='w')playWindow();else if(k==='c')playClip();
 else if(k==='j')prev();else if(k==='k')next(false);else if(k==='n')next(true);else if(k===' '){e.preventDefault();v.paused?v.play():v.pause();}else return;e.preventDefault();});
load();
</script></body></html>
"""
