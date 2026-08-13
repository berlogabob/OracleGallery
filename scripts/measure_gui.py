"""Measure the operator GUI the way an operator meets it: rendered, at laptop size.

This is the harness that caught what the unit suite could not: after the 7->3 screen
collapse, every per-workspace test was green while CREATE stacked 3588px of content into a
659px viewport -- 5.4 screens of scroll -- with START PRINT rendered twice on PRINT. Unit
tests see registered keys; only the rendered page shows stacking, duplication and clipping.

It boots a sandboxed GUI (never the operator's live instance on 8787), drives headless
Chrome over the DevTools protocol, visits all three screens, and reports per screen:

    scroll depth (content height / visible height -- the no-scroll gate wants 1.0)
    visible cards, visible buttons, duplicate visible button labels, live iframe heights

plus a full-page screenshot per screen. Run it after any GUI change:

    uv run python scripts/measure_gui.py            # report + screenshots
    uv run python scripts/measure_gui.py --gate     # exit 1 if any screen scrolls or dupes

--gate is the per-batch acceptance check from the redesign plan (metrics S1-S3, S7). The
unit-level metrics live in tests/test_operator_metrics.py; this script owns the ones that
only exist in a real render.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GUI_PORT = 8799
CDP_PORT = 9223
SCREENS = ("PRINT", "CREATE", "SETUP")

CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("chromium") or "",
    shutil.which("google-chrome") or "",
)

MEASURE_JS = """(() => {
  const scrolls = [...document.querySelectorAll('.workspace-scroll')]
    .filter(e => e.offsetParent !== null)
    .map(e => ({h: e.scrollHeight, vis: e.clientHeight}));
  const page = document.scrollingElement;
  const cards = [...document.querySelectorAll('.oracle-card,.q-card')]
    .filter(e => e.offsetParent !== null).length;
  const labels = [...document.querySelectorAll('button')]
    .filter(e => e.offsetParent !== null)
    .map(b => b.innerText.trim()).filter(t => t.length > 1);
  const dupes = Object.entries(labels.reduce((m, t) => (m[t] = (m[t] || 0) + 1, m), {}))
    .filter(([, n]) => n > 1).map(([t, n]) => `${t} x${n}`);
  const iframes = [...document.querySelectorAll('iframe')]
    .filter(e => e.offsetParent !== null)
    .map(f => Math.round(f.getBoundingClientRect().height));
  return {
    panel_h: Math.max(0, ...scrolls.map(s => s.h)),
    panel_vis: Math.max(0, ...scrolls.map(s => s.vis)),
    page_h: page.scrollHeight, page_vis: page.clientHeight,
    cards, buttons: labels.length, dupes, iframes,
  };
})()"""


def _find_chrome() -> str:
    for candidate in CHROME_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    sys.exit("no Chrome/Chromium found for headless measurement")


def _wait_http(url: str, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.5)
    sys.exit(f"{url} did not come up within {timeout_s}s")


def _boot_sandbox_gui(sandbox: Path) -> subprocess.Popen[bytes]:
    """A fresh GUI against scratch roots. The operator's live 8787 is never touched."""
    for sub in ("sessions", "spool", "runtime"):
        (sandbox / sub).mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        NEJE_GUI_PORT=str(GUI_PORT),
        NEJE_ALLOWED_ROLES="gui_only",
        NEJE_UPLOADER_SESSION_ROOT=str(sandbox / "sessions"),
        NEJE_PLOTTER_SPOOL_ROOT=str(sandbox / "spool"),
        # The store env var is NEJE_ORACLE_RUNTIME_DB_PATH -- there is no NEJE_RUNTIME_ROOT.
        # Getting this wrong is not hypothetical: earlier ad-hoc sandboxes set the wrong name
        # and silently shared the operator's real runtime store, so the "fresh" GUI restored
        # whatever tab the audit had clicked last and the first screen measured was not PRINT.
        NEJE_ORACLE_RUNTIME_DB_PATH=str(sandbox / "runtime" / "oracle_runtime.sqlite3"),
        NEJE_ORACLE_LOGS_ROOT=str(sandbox / "logs"),
        NEJE_GUI_SETTINGS_PATH=str(sandbox / "runtime" / "gui_settings.json"),
    )
    log = (sandbox / "gui.log").open("wb")
    proc = subprocess.Popen(["uv", "run", "neje-gui"], cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT)
    _wait_http(f"http://127.0.0.1:{GUI_PORT}/", 30)
    return proc


def _boot_chrome() -> subprocess.Popen[bytes]:
    proc = subprocess.Popen(
        [
            _find_chrome(),
            "--headless=new",
            f"--remote-debugging-port={CDP_PORT}",
            "--window-size=1280,800",
            "--no-first-run",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_http(f"http://127.0.0.1:{CDP_PORT}/json/version", 20)
    return proc


def _new_target() -> dict:
    url = f"http://127.0.0.1:{CDP_PORT}/json/new?http://127.0.0.1:{GUI_PORT}/"
    for method in ("PUT", "GET"):  # newer Chrome wants PUT; older accepted GET
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, method=method)).read())
        except urllib.error.HTTPError:
            continue
    sys.exit("could not open a CDP target")


async def _measure(out_dir: Path) -> dict[str, dict]:
    import websockets  # a nicegui dependency, so always present in this venv

    target = _new_target()
    results: dict[str, dict] = {}
    async with websockets.connect(target["webSocketDebuggerUrl"], max_size=50_000_000) as ws:
        mid = 0

        async def cmd(method: str, params: dict | None = None) -> dict:
            nonlocal mid
            mid += 1
            await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == mid:
                    return msg.get("result", {})

        async def js(expr: str):
            result = await cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            return result.get("result", {}).get("value")

        await cmd("Page.enable")
        await cmd(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1280, "height": 800, "deviceScaleFactor": 1, "mobile": False},
        )
        await asyncio.sleep(9)  # nicegui websocket boot + first render

        for screen in SCREENS:
            # Always click, including the first screen: the app restores the last-used tab,
            # so "whatever came up" is not a measurement of PRINT.
            await js(
                f"[...document.querySelectorAll('.q-tab')].find(t => t.innerText.trim().includes('{screen}'))?.click()"
            )
            await asyncio.sleep(3)
            results[screen] = await js(MEASURE_JS) or {}
            shot = await cmd("Page.captureScreenshot", {"format": "png"})
            (out_dir / f"{screen.lower()}.png").write_bytes(base64.b64decode(shot["data"]))
    return results


def _report(results: dict[str, dict]) -> tuple[bool, bool]:
    scrolls = False
    dupes = False
    print(f"{'screen':8} {'content':>8} {'visible':>8} {'depth':>6}  cards  btns  dupes / iframes")
    for screen, r in results.items():
        if not r:
            print(f"{screen:8} MEASUREMENT FAILED")
            scrolls = True
            continue
        height = max(r["panel_h"], r["page_h"])
        visible = max(r["panel_vis"], 1)
        depth = height / visible
        if depth > 1.02:  # 2% slack for rounding, not for content
            scrolls = True
        if r["dupes"]:
            dupes = True
        print(
            f"{screen:8} {height:>7}px {visible:>7}px {depth:>5.1f}x  {r['cards']:>5} {r['buttons']:>5}  "
            f"{r['dupes'] or '-'} / {r['iframes'] or '-'}"
        )
    return scrolls, dupes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gate", action="store_true", help="exit 1 on any page scroll or duplicate action label")
    parser.add_argument("--out", type=Path, default=None, help="screenshot dir (default: a temp dir, printed)")
    args = parser.parse_args()

    out_dir = args.out or Path(tempfile.mkdtemp(prefix="gui-measure-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    sandbox = Path(tempfile.mkdtemp(prefix="gui-sandbox-"))

    gui = chrome = None
    try:
        gui = _boot_sandbox_gui(sandbox)
        chrome = _boot_chrome()
        results = asyncio.run(_measure(out_dir))
        scrolls, dupes = _report(results)
        print(f"\nscreenshots: {out_dir}")
        if args.gate and (scrolls or dupes):
            failures = [w for w, bad in (("page scroll", scrolls), ("duplicate actions", dupes)) if bad]
            sys.exit(f"GATE FAILED: {' + '.join(failures)}")
    finally:
        for proc in (gui, chrome):
            if proc is not None:
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()


if __name__ == "__main__":
    main()
