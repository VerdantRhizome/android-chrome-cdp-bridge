# Feature Request #3: Optional WebView DevTools forwarding

- **Status:** Proposed (local issue draft — not pushed)
- **Repo:** `VerdantRhizome/android-chrome-cdp-bridge`
- **Opened by:** local session (2026-08-07)
- **Related research:** `~/.hermes/skills/hermes/hermes-cdp-attach/references/android-wifi-debug-webview.md` §2

## Summary

Add an **optional** forwarding target for **Android WebView** DevTools, in
addition to the current Chrome (`chrome_devtools_remote`) target. WebViews
expose a separate abstract socket `webview_devtools_remote`; when an app calls
`WebView.setWebContentsDebuggingEnabled(true)`, its embedded WebView becomes
inspectable/debuggable over CDP exactly like a page.

## Motivation

The bridge today only drives the device's **Chrome** browser. Many apps
(including ones an agent may want to inspect or drive) render UI inside a
WebView rather than launching Chrome. Exposing `webview_devtools_remote` lets
the same `browser.cdp_url` → `browser_*` / `browser_cdp` pipeline reach an
app's embedded WebView, not just the standalone browser.

## How WebView CDP works (verified facts)

- Socket: `localabstract:webview_devtools_remote` (parallel to Chrome's
  `chrome_devtools_remote`). Forward identically:
  `adb forward tcp:9222 localabstract:webview_devtools_remote`.
- Debugging is enabled **only by the app at runtime** via
  `WebView.setWebContentsDebuggingEnabled(true)`. It is NOT governed by the
  app's `debuggable` manifest flag.
- **Non-root limitation:** only WebViews of apps you build (or that ship
  debug-enabled WebViews) are reachable. System / production third-party app
  WebViews are invisible to CDP on a non-root device — unlike Chrome, which is
  always debuggable.
- Inspectable WebViews appear in `chrome://inspect/#devices` and as targets on
  the forwarded CDP endpoint (`/json/list`), same as Chrome pages.

## Proposed design

1. **New optional flag / env var** to select the target socket, e.g.
   `CDP_TARGET=webview` (default `chrome`) or a `--target` CLI flag. Keep the
   default behavior unchanged (backward compatible).
2. `forward_cdp_port()` forwards `localabstract:{CDP_TARGET}_devtools_remote`
   instead of the hard-coded `chrome_devtools_remote`.
3. The same `attach.py` keep-alive / lazy-attach path should honor the selected
   target so reconnects preserve it.
4. README: document the WebView option, the `setWebContentsDebuggingEnabled`
   prerequisite, and the non-root "only your own/debug-enabled apps" caveat.
5. Discovery/connect flow (`zeroconf` → `adb connect`) is unchanged — only the
   final `adb forward` socket name differs.

## Out of scope / constraints

- Does **not** bypass the non-root restriction: cannot reach a production
  app's WebView without its cooperation.
- Does not script the Wireless-debugging toggle (Android 11+ TLS pairing
  requires the phone UI + 6-digit code; verified non-scriptable, see the
  referenced notes §1). The bridge still needs Wireless debugging ON and paired
  before any forward (Chrome or WebView) can be established.

## Acceptance criteria

- [ ] `CDP_TARGET=webview` (or equivalent flag) forwards
      `webview_devtools_remote` and exposes it on the configured `CDP_PORT`.
- [ ] Default (`chrome`) behavior is byte-for-byte unchanged.
- [ ] `attach.py` reconnect preserves the selected target.
- [ ] README documents the WebView mode + non-root caveat.
- [ ] No regression to the existing Chrome E2E (navigate / snapshot / click /
      vision).

## Related

- Closes nothing yet; depends on a decision on the flag name / env var.
- Cross-ref: hermes-cdp-attach plugin is unaffected (it shells out to
  `attach.py` → `main.py`; the target selection is internal to this repo).
