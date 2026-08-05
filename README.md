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
/browser connect http://localhost:9333
```
Or set it in `~/.hermes/config.yaml`:
```yaml
browser:
  cdp_url: "http://localhost:9333"
```
