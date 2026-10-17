"""Memory guard for long avatar runs (macOS): logs the largest processes by physical footprint and kills
runaway harness browsers.

    uv run python scripts/memguard.py [--limit-gb 6] [--every 3] [--log runs_nv/memguard.log]

Footprint = `proc_pid_rusage(...).ri_phys_footprint`, the number Activity Monitor and the Force Quit dialog
show (RSS excludes compressed memory and badly under-reports a leaking browser). A "harness browser" is a
Chrome launched by Playwright (`--remote-debugging-pipe`) plus all its descendants; when one tree exceeds
--limit-gb it is SIGKILLed and an ALERT line is printed (stdout, one line per event). A run process
(`streamer.run_manifest` / `run_avatar_keys.py`) above --py-limit-gb is killed the same way. System-wide:
below --warn-free % free memory (`kern.memorystatus_level`) the top processes are printed; below
--kill-free % every run process and harness browser is killed, so the machine never reaches the
"out of application memory" dialog.
"""
import argparse
import ctypes
import os
import signal
import subprocess
import time

_libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib")


class _RUsageV0(ctypes.Structure):
    _fields_ = [("uuid", ctypes.c_uint8 * 16)] + [(n, ctypes.c_uint64) for n in (
        "user_time", "system_time", "pkg_idle_wkups", "interrupt_wkups", "pageins", "wired_size",
        "resident_size", "phys_footprint", "proc_start_abstime", "proc_exit_abstime")]


def footprint_mb(pid: int) -> float:
    buf = _RUsageV0()
    if _libc.proc_pid_rusage(pid, 0, ctypes.byref(buf)) != 0:
        return 0.0
    return buf.phys_footprint / 2**20


def processes() -> dict[int, tuple[int, str]]:
    out = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], check=False, capture_output=True, text=True).stdout
    procs = {}
    for line in out.splitlines():
        p = line.split(None, 2)
        if len(p) == 3:
            procs[int(p[0])] = (int(p[1]), p[2])
    return procs


def harness_trees(procs) -> dict[int, set[int]]:
    flagged = {pid for pid, (_, cmd) in procs.items() if "--remote-debugging-pipe" in cmd}
    roots = {pid for pid in flagged if procs[pid][0] not in flagged}
    trees = {}
    for r in roots:
        tree, changed = {r}, True
        while changed:
            changed = False
            for pid, (ppid, _) in procs.items():
                if ppid in tree and pid not in tree:
                    tree.add(pid)
                    changed = True
        trees[r] = tree
    return trees


def short(cmd: str) -> str:
    exe = cmd.split(" --")[0]
    t = cmd.split("--type=")[1].split()[0] if "--type=" in cmd else ""
    return (os.path.basename(exe) + (f"[{t}]" if t else ""))[:60]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-gb", type=float, default=6.0)
    ap.add_argument("--py-limit-gb", type=float, default=8.0)
    ap.add_argument("--warn-free", type=int, default=25)
    ap.add_argument("--kill-free", type=int, default=12)
    ap.add_argument("--every", type=float, default=3.0)
    ap.add_argument("--log", default="runs_nv/memguard.log")
    a = ap.parse_args()
    with open(a.log, "a", buffering=1) as log:
        _loop(a, log)


def _kill(pids) -> None:
    for p in pids:
        try:
            os.kill(p, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _free_pct() -> int:
    r = subprocess.run(["sysctl", "-n", "kern.memorystatus_level"], check=False, capture_output=True, text=True)
    return int(r.stdout.strip() or 100)


RUN_MARKERS = ("streamer.run_manifest", "run_avatar_keys.py")


def _loop(a, log) -> None:
    last_warn = 0.0
    last_big: dict[int, float] = {}
    while True:
        procs = processes()
        fp = {pid: footprint_mb(pid) for pid in procs}
        stamp = time.strftime("%H:%M:%S")
        top = sorted(fp.items(), key=lambda kv: -kv[1])[:8]
        log.write(f"{stamp} free {_free_pct()}% " + " | ".join(f"{short(procs[p][1])}:{p} {mb:.0f}MB" for p, mb in top) + "\n")
        for root, tree in harness_trees(procs).items():
            total = sum(fp.get(p, 0.0) for p in tree)
            worst = max(tree, key=lambda p: fp.get(p, 0.0))
            log.write(f"{stamp}   harness browser {root}: {len(tree)} procs {total:.0f}MB "
                      f"(max {short(procs[worst][1])} {fp.get(worst, 0):.0f}MB)\n")
            if total > a.limit_gb * 1024:
                _kill(tree)
                print(f"{stamp} ALERT killed harness browser {root}: {total:.0f}MB > {a.limit_gb} GB "
                      f"(largest {short(procs[worst][1])} {fp.get(worst, 0):.0f}MB)", flush=True)
        runs = {p for p, (_, cmd) in procs.items() if any(k in cmd for k in RUN_MARKERS) and "zsh" not in cmd}
        for p in runs:
            if fp.get(p, 0.0) > a.py_limit_gb * 1024:
                _kill([p])
                print(f"{stamp} ALERT killed run process {p}: {fp[p]:.0f}MB > {a.py_limit_gb} GB", flush=True)
        free = _free_pct()
        if free < a.warn_free and time.time() - last_warn > 60:
            last_warn = time.time()
            print(f"{stamp} WARN free memory {free}%: " + ", ".join(
                f"{short(procs[p][1])}:{p} {mb:.0f}MB" for p, mb in top[:5]), flush=True)
        if free < a.kill_free:
            trees = harness_trees(procs)
            _kill(runs | {p for t in trees.values() for p in t})
            print(f"{stamp} ALERT free memory {free}% < {a.kill_free}%: killed {len(runs)} run process(es) and "
                  f"{len(trees)} harness browser(s); top: " + ", ".join(
                      f"{short(procs[p][1])}:{p} {mb:.0f}MB" for p, mb in top[:5]), flush=True)
        big = [(p, mb) for p, mb in top if mb > 8 * 1024]
        for p, mb in big:                      # not ours to kill: report, at most every 5 min per process
            if time.time() - last_big.get(p, 0.0) > 300:
                last_big[p] = time.time()
                print(f"{stamp} ALERT large process {short(procs[p][1])}:{p} {mb:.0f}MB", flush=True)
        time.sleep(a.every)


if __name__ == "__main__":
    main()
