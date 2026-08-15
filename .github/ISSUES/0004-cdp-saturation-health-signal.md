# Feature Request #4: CDP target-list saturation health signal (inactive Chrome windows)

- **Status:** Proposed (local issue draft — not pushed)
- **Repo:** `VerdantRhizome/android-chrome-cdp-bridge`
- **Opened by:** local session (2026-08-07)
- **Related:** issue #3 (WebView forwarding); research in
  `~/.hermes/skills/hermes/hermes-cdp-attach/references/android-chrome-cdp-quirks.md`
  ("Native Android reality: inactive Chrome windows").

## Context (why this matters)

On real Android devices, Chrome keeps **backgrounded/inactive windows** alive in
its session (Android suspends them for memory; Chrome preserves them under
*Manage windows → Inactive (N)*). CDP's `GET /json/list` enumerates **every tab
across every window** — including the suspended ones whose page sockets are
asleep.

Measured on this device: **189 `/json/list` entries → only 1 ALIVE**, 188 DEAD
(13 inactive windows holding ~167 tabs; one window alone had 127 tabs).

Consequence: when the CDP server is saturated by dead targets, the high-level
open path can return **HTTP 500** (`server rejected WebSocket connection`), and
repeatedly doing so can **wedge the entire endpoint** (ConnectionRefused) and
even drop the adb wireless-debug link. The live (foreground) tab itself stays
100% reliable — it is the *discovery/open* path that breaks.

This is a **native Android reality**, not a bug: it will exist on essentially
every non-fresh Android device a Hermes session runs on. The backend's correct
defense is to **filter `Target.getTargets` to `attached == true`** (the raw-CDP
backend already does this), which is robust regardless of tab count. This issue
is about giving the *user/operator* a signal when saturation is hurting, so they
can relieve it without guessing.

## Proposal

Add a **non-blocking saturation health signal** to the forwarder/attach path:

1. After (re)establishing the forward, count `GET /json/list` entries.
2. If the count exceeds a threshold (e.g. **> 50**), emit a **clear, actionable
   log/hint** — NOT an error, just a notice:
   > CDP target list is large (N entries). If browser automation fails with
   > HTTP 500, close inactive Chrome windows (Manage windows → Inactive) to
   > relieve devtools saturation. The backend filters to live targets and still
   > works regardless.
3. The signal must be **purely advisory** — it must never block, fail, or change
   behavior when the count is high. The bridge's job (keep the forward up)
   continues unchanged.
4. Make the threshold configurable (env var / config, default 50) so it can be
   tuned per device.
5. Optionally expose the count in `attach.py`'s return/health output so the
   `hermes-cdp-attach` plugin can surface it (companion to the plugin-side
   signal added in `hermes-cdp-attach` `__init__.py`).

## Why not just "close the tabs" as the fix

Closing inactive windows is a valid *user* remedy (drops 189 → ~1 and removes
500s), but it is not a code fix: inactive windows are permanent on Android, and
requiring the user to manually purge them before every session is fragile. The
robust defense is the `attached`-filter (backend-side, already implemented);
this issue is the complementary *visibility* layer so degradation is explainable
instead of silent.

## Acceptance criteria

- [ ] Forwarder counts `/json/list` entries after connecting.
- [ ] Emits an advisory hint when count > threshold (default 50).
- [ ] Hint is non-blocking; high count never alters forward behavior.
- [ ] Threshold is configurable via env/config.
- [ ] (Optional) count surfaced for the plugin to consume.
- [ ] README documents the inactive-window reality + the signal.

## Related

- Depends on nothing; companion to the `hermes-cdp-attach` plugin health signal.
- Does not change the `attached`-filter backend behavior (that lives in the
  hermes-agent patch, not this repo).
