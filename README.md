# Termux Agent Browser

A zero-touch auto-discovery pipeline to enable local AI agents (like Hermes) to control an Android device's Chrome browser directly via the Chrome DevTools Protocol (CDP), using ADB over Wi-Fi.

Because native headless browsers like Playwright (`agent-browser`) do not compile on the Android Termux `aarch64` environment, this tool bridges the gap by exposing the host Android device's live Chrome instance as a local CDP endpoint that the agent can connect to.

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
git clone https://github.com/AveryRPeterson/termux-agent-browser.git
cd termux-agent-browser
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

## Driving the browser (what works on Termux)

On `android-arm64` (Termux) Hermes's high-level browser tools
(`browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`,
`browser_vision`, …) are built on the `agent-browser` subprocess, which cannot
install/run here (npm: `Unsupported platform: android-arm64`). They fail
before touching Chrome. **This is a known Hermes-core limitation** (tracked
for a fix — see the GitHub issue), not a problem with this connector.

What *does* work is the **raw CDP endpoint**, because `main.py` forwards the
phone's real Chrome DevTools socket to `localhost:9222`. Two ways to use it:

### 1. `cdp_helper.py` (this repo) — friendly wrapper

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

### 2. Hermes `browser_cdp` tool (raw CDP)

Hermes's `browser_cdp` tool sends raw CDP commands and is **not** subject to
the android-arm64 guard, so it works directly. Example:

```
browser_cdp(method="Target.createTarget", params={"url": "https://example.com"})
browser_cdp(method="Runtime.evaluate",
            params={"expression": "document.title", "returnByValue": true},
            target_id="<id from above>")
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
  --prompt "Run: cd ~/projects/termux-agent-browser && CDP_PORT=9222 uv run attach.py --port 9222
If the CDP forward is already live (HTTP 200 on http://localhost:9222/json/version)
the script exits immediately and does nothing. Only reconnect when it is dead." \
  --deliver local
```

`attach.py` is fast when healthy (sub-200ms heartbeat) and only shells out to
`uv run main.py` when the port is unreachable, so this cron is cheap to run
every minute. This complements — it does not replace — the per-tool
`pre_tool_call` lazy-attach in the `hermes-cdp-attach` plugin.
