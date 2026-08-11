# Android Chrome CDP Bridge

A zero-touch auto-discovery pipeline to enable local AI agents (like Hermes) to control an Android device's Chrome browser directly via the Chrome DevTools Protocol (CDP), using ADB over Wi-Fi.

> **What this is / is not:** this is a *CDP bridge/forwarder* for Android Chrome — it is **not** a port of `agent-browser` (vercel-labs/agent-browser, written in Rust, which cannot run on `android-arm64`). It exposes the host Android device's live Chrome instance as a local CDP endpoint that an agent can connect to.

## How it works

Android 11+ randomizes the Wireless Debugging port every time it's toggled or Wi-Fi reconnects. This script uses `zeroconf` (mDNS) to automatically scan your local network for the Android device's broadcasted `_adb-tls-connect._tcp.local.` service. 

It will automatically find the randomized port, connect via `adb`, and forward the `chrome_devtools_remote` unix socket to a local TCP port (default `9333`).

## Prerequisites

1. Termux with `android-tools` installed (`pkg install android-tools`)
2. Python 3+
3. Android device connected to the same Wi-Fi network with **Wireless Debugging** enabled in Developer Options.

## Installation & Usage

This project uses `uv` for blazing-fast, reproducible dependency management. You do not need to manually create virtual environments or install dependencies.

```bash
git clone https://github.com/AveryRPeterson/android-chrome-cdp-bridge.git
cd android-chrome-cdp-bridge
uv run main.py
```

If it is your first time connecting, the script will interactively guide you through the ADB pairing process. Once paired, subsequent runs will automatically discover the port and connect.

### Configuration

You can override the default CDP forwarding port by setting the `CDP_PORT` environment variable:

```bash
export CDP_PORT=9222
uv run main.py
```

## Connecting your Agent

Once the script successfully runs, configure your AI agent to connect to the exposed CDP endpoint. 

For **Hermes**, you can use the slash command:
```
/browser connect http://localhost:9222
```
Or set it in `~/.hermes/config.yaml`:
```yaml
browser:
  cdp_url: "http://localhost:9222"
```

> Note: the default CDP forwarding port is configurable via the `CDP_PORT`
> environment variable (see [Configuration](#configuration)). The examples
> above use `9222`; if you run the connector with a different `CDP_PORT`,
> point Hermes at that port instead.

## Device serial: "emulator-5554" IS the tablet

When connecting over **Wireless Debugging**, the real Tab S9 (SM-X810) shows up
in `adb devices` as:

```
emulator-5554   device  product:gts9pwifieea model:SM_X810 ...
```

That `emulator-5554` serial is **the actual tablet**, not a phantom emulator.
Don't try to "remove" it or forward around it — pass it straight to
`adb -s emulator-5554` (the connector does this automatically via the
`-s <serial>` selector once paired). A *true* phantom would only appear as a
leftover from a prior `adb tcpip` experiment; the `gts9pwifieea` product string
is how you tell them apart.

> Pairing note: Wireless Debugging pairing is version-sensitive. If `adb pair`
> reports `protocol fault ... Connection reset by peer` / `couldn't read status
> message: Success`, the `adb` client version doesn't match the tablet's
> `adbd`. Re-pair from the tablet's Wireless debugging screen (OFF → ON, then
> "Pair device with pairing code") and tap **Allow** when the prompt appears.

## Driving the browser (what works on Termux)

On `android-arm64` (Termux) Hermes's high-level browser tools
(`browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`,
`browser_vision`, …) are built on the `agent-browser` subprocess, which cannot
install/run here (npm: `Unsupported platform: android-arm64`). They used to
fail before touching Chrome.

**That is now fixed by a local patch** in the Hermes agent checkout
(`~/.hermes/hermes-agent/`): a raw-WebSocket CDP backend
(`tools/browser_raw_cdp.py`) plus a hand-off in `tools/browser_tool.py`
(`_run_browser_command` routes to it when `browser.cdp_url` is set and camofox
mode is off). The high-level tools then drive the phone's Chrome directly via
CDP — no `agent-browser` Node subprocess. This patch lives on the
`feat/android-chrome-raw-cdp` branch of the fork
`AveryRPeterson/hermes-agent` (not yet merged upstream).

Three ways to drive the browser:

### 1. Hermes high-level browser tools (patched — preferred)

With `browser.cdp_url: "http://localhost:9222"` in `~/.hermes/config.yaml`
and the patch applied, just use the normal tools:

```
browser_navigate(url="https://example.com")
browser_snapshot()        # returns text outline + @eN refs
browser_click(ref="@e3")  # clicks the resolved element
browser_vision(question="what is on this page")
```

Under the hood these call `run_raw_cdp_command` → your phone's Chrome. Verified
end-to-end (live 6/6: navigate / snapshot / click / vision / wake-lock).

**Keep the tab awake:** the patch auto-applies a Screen Wake Lock (re-acquired
on `visibilitychange`) plus `Emulation.setIdleOverride` on every `open`, so the
foregrounded tab does not sleep. Caveat: if Android fully backgrounds the
Chrome app, the OS can still suspend it — keep Chrome open/foregrounded while
driving it.

### 2. `cdp_helper.py` (this repo) — friendly wrapper

A standalone WebSocket CDP client that exposes the same operations the blocked
tools would, but actually functional on the phone. Requires the `websockets`
dep (`uv add websockets` — already in `pyproject.toml`).

```bash
# Open a URL and print its title
uv run cdp_helper.py title https://example.com

# List all links on a page
uv run cdp_helper.py links https://example.com

# Run arbitrary JavaScript on a page (returns JSON)
uv run cdp_helper.py eval "document.querySelector('h1').textContent"

# Capture a PNG screenshot (writes to a writable path)
uv run cdp_helper.py screenshot https://example.com -o ~/shot.png
```

From Python (e.g. inside an agent `execute_code` block):

```python
from cdp_helper import ChromeSession
with ChromeSession() as tab:
    tab.navigate("https://example.com")
    print(tab.title())                 # -> "Example Domain"
    print(tab.links())                 # -> ["https://iana.org/domains/example"]
    tab.click_element("a#some-link")   # click via CDP Input
    tab.type_text("input#q", "hello")  # type via CDP Input
    tab.screenshot("~/shot.png")       # PNG bytes
```

`ChromeSession` auto-creates + attaches a tab and manages the CDP session, so
you never handle `sessionId`s by hand.

### 3. Hermes `browser_cdp` tool (raw CDP)

Hermes's `browser_cdp` tool sends raw CDP commands and is **not** subject to
the android-arm64 guard, so it works directly. Example:

```
browser_cdp(method="Target.createTarget", params={"url": "https://example.com"})
browser_cdp(method="Runtime.evaluate",
            params={"expression": "document.title", "returnByValue": true},
            target_id="<id from above>")
```

## CI for the Hermes patch

The `feat/android-chrome-raw-cdp` branch carries `.github/workflows/integration.yml`:

- `mock-e2e` — runs the deterministic scripted-CDP test
  (`tools/tests/test_browser_raw_cdp_mock.py`, 15 checks) on `ubuntu-latest`
  across Python 3.11/3.12. Fires on push / manual dispatch using the branch's
  **own** workflow file (no main merge required).
- `live-e2e` — gated behind a `workflow_dispatch` `run_live` input and
  `runs-on: self-hosted`. It needs a self-hosted runner reachable to the
  phone's CDP. We intentionally do **not** run it in CI (standing up a
  self-hosted runner inside Termux requires proot-distro glibc, which is heavy);
  the live path is instead verified on-demand locally (the 6/6 high-level E2E).

To re-run the live E2E locally (keep Chrome foregrounded):

```bash
cd ~/.hermes/hermes-agent
~/.hermes/hermes-agent/venv/bin/python /data/data/com.termux/files/usr/tmp/hermes-verify-hl.py
```

## Future improvement: keep-alive cron

The `adb forward` rule is **ephemeral** — it dies when the phone drops Wi-Fi,
Android re-randomizes the Wireless-debugging port, or the adb daemon is
restarted. The [`hermes-cdp-attach`](https://hermes-agent.nousresearch.com/docs)
plugin already lazy-reconnects on the first `browser_*` tool call, but a
periodic keep-alive closes the gap between a drop and the next tool use (up to
a minute of dead time otherwise).

Add a local 1-minute cron that health-checks the endpoint and re-runs the
connector only when the socket is down:

```bash
# ~/.hermes/cron / or schedule via: hermes cron create
hermes cron create \
  --schedule "*/1 * * * *" \
  --name "cdp-keepalive" \
  --prompt "Run: cd ~/projects/android-chrome-cdp-bridge && CDP_PORT=9222 uv run attach.py --port 9222
If the CDP forward is already live (HTTP 200 on http://localhost:9222/json/version)
the script exits immediately and does nothing. Only reconnect when it is dead." \
  --deliver local
```

`attach.py` is fast when healthy (sub-200ms heartbeat) and only shells out to
`uv run main.py` when the port is unreachable, so this cron is cheap to run
every minute. This complements — it does not replace — the per-tool
`pre_tool_call` lazy-attach in the `hermes-cdp-attach` plugin.

## Host-environment portability

This bridge is a *CDP forwarder*, not `agent-browser`, so it runs wherever
Python + `adb` can reach the phone's Wireless-Debugging port on the LAN. It is
not limited to Termux. Confirmed / expected to work:

- **Termux** (primary) — directly on the phone.
- **proot-distro (Ubuntu/Alpine under Termux)** — `agent-browser`'s Rust
  binary still can't run here, but this pure-Python bridge does. Note: proot's
  network namespace may not share the host's loopback, so the forwarded
  `localhost:9222` might need the host's LAN IP or a proot `-p`/linker forward
  to be visible inside the proot environment.
- **UserLAnd / Andronix** (Linux-on-Android) — same as above; just needs `adb`
  present and LAN reach to the phone.
- **A Linux laptop on the same Wi-Fi** driving the phone — the bridge doesn't
  know it's "on Android"; it only needs `adb` + LAN reach to the device.

**Out of scope (documented limitation):** cloud CI runners reaching a phone
have no `adb`/LAN path to the device. That is why the hermes-agent
`feat/android-chrome-raw-cdp` `live-e2e` CI job is intentionally not run; live
verification stays on-demand and local.
