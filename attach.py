#!/usr/bin/env python3
"""hermes-cdp-attach: keep the Android-Chrome CDP forward alive.

This is the *lazy-load* bridge for the Termux Agent Browser project. Hermes
points ``browser.cdp_url`` at ``http://localhost:<PORT>``. That forward is
ephemeral: it dies whenever the phone drops off Wi-Fi, Android re-randomizes
the Wireless-debugging port, or the adb daemon is restarted. This script is
what brings it back *on demand*.

Design goals
------------
- Fast when healthy: a sub-200 ms HTTP heartbeat. No shelling out, no scans.
- Cheap when dead: only then does it run ``uv run main.py`` (which does the
  mDNS discovery -> adb connect -> adb forward dance).
- Idempotent: safe to call on every browser tool invocation.
- Observable: every reattach attempt is logged to ``attach.log`` next to this
  file so you can see *why* a connection dropped.

Port selection
--------------
The target port is, in order of precedence:
  1. ``$CDP_PORT``  (so it matches whatever you passed to ``main.py``)
  2. ``--port`` CLI flag
  3. ``9222``       (the project default)

If the configured port is already serving a live CDP endpoint we do nothing
and exit 0 immediately -- the only cost is one HTTP GET.
"""
from __future__ import annotations

import argparse
import http.client
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG_PATH = HERE / "attach.log"
DEFAULT_PORT = 9222


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n"
    try:
        with LOG_PATH.open("a") as fh:
            fh.write(line)
    except Exception:
        pass
    # Also surface to stderr for callers that capture it (e.g. the plugin).
    sys.stderr.write(line)


def is_cdp_alive(host: str, port: int, timeout: float = 0.2) -> bool:
    """Return True if ``host:port`` serves a Chrome DevTools /json/version."""
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request("GET", "/json/version")
        resp = conn.getresponse()
        ok = 200 <= resp.status < 300
        conn.close()
        return ok
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Lazy-attach the Android Chrome CDP forward.")
    parser.add_argument("--host", default="localhost", help="CDP host to probe (default: localhost)")
    parser.add_argument("--port", type=int, default=None, help="CDP port (default: $CDP_PORT or 9222)")
    parser.add_argument(
        "--project-dir",
        default=str(HERE),
        help="Directory containing main.py (default: this script's directory)",
    )
    parser.add_argument(
        "--connect-timeout",
        type=int,
        default=60,
        help="Max seconds to wait for main.py to bring the port up (default: 60)",
    )
    args = parser.parse_args()

    port = args.port or int(os.environ.get("CDP_PORT", DEFAULT_PORT))

    # Fast path: already connected -> nothing to do.
    if is_cdp_alive(args.host, port):
        return 0

    log(f"[attach] CDP not reachable at {args.host}:{port} -- launching reconnect")

    project_dir = Path(args.project_dir).resolve()
    main_py = project_dir / "main.py"
    if not main_py.exists():
        log(f"[attach] ERROR: {main_py} not found; cannot reconnect")
        return 2

    # Run the project's reconnect entrypoint with the SAME port so the forward
    # lands where Hermes expects it. We deliberately do NOT use any shell-array
    # trickery -- invoke uv as a plain argv list so quoting/word-splitting can
    # never break it the way a fish `var=(...)` assignment would.
    env = dict(os.environ)
    env["CDP_PORT"] = str(port)
    try:
        proc = subprocess.run(
            ["uv", "run", "main.py"],
            cwd=str(project_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=args.connect_timeout,
        )
    except subprocess.TimeoutExpired:
        log(f"[attach] ERROR: uv run main.py timed out after {args.connect_timeout}s")
        return 3
    except FileNotFoundError:
        # No uv? Fall back to plain python3.
        try:
            proc = subprocess.run(
                [sys.executable, "main.py"],
                cwd=str(project_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=args.connect_timeout,
            )
        except Exception as exc:  # noqa: BLE001
            log(f"[attach] ERROR: fallback python3 main.py failed: {exc}")
            return 4
    except Exception as exc:  # noqa: BLE001
        log(f"[attach] ERROR: failed to launch reconnect: {exc}")
        return 5

    for line in (proc.stdout or "").splitlines():
        log(f"[main.py] {line}")
    if proc.returncode != 0:
        for line in (proc.stderr or "").splitlines():
            log(f"[main.py!] {line}")
        log(f"[attach] reconnect exited {proc.returncode}")

    # Re-probe: did it actually come up?
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if is_cdp_alive(args.host, port):
            log(f"[attach] OK -- CDP live at {args.host}:{port}")
            return 0
        time.sleep(0.25)

    log(f"[attach] FAILED -- {args.host}:{port} still dead after reconnect")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
