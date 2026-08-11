#!/usr/bin/env python3
"""Unit tests for the android-chrome-cdp-bridge forward logic.

These mock ``subprocess.run`` so they run anywhere (no adb / no phone needed)
and lock in the device-aware forwarding behavior:
  - ``adb_connect`` returns the connected serial string (or None on failure).
  - ``forward_cdp_port(serial)`` builds an ``adb -s <serial> forward ...``
    command so an ambiguous multi-device state cannot silently fail.
  - ``forward_cdp_port(None)`` still builds the bare forward (compat).
"""
import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)

# Load main.py as a module without executing its __main__ side effects.
spec = importlib.util.spec_from_file_location("bridge_main", os.path.join(_REPO, "main.py"))
assert spec is not None, "could not load main.py spec"
assert spec.loader is not None, "spec lacks a loader"
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FakeCompleted:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _make_run(connect_stdout="connected", connect_rc=0, forward_rc=0):
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(list(cmd))
        if "connect" in cmd:
            return FakeCompleted(stdout=connect_stdout, returncode=connect_rc)
        # forward
        return FakeCompleted(stdout="", returncode=forward_rc)

    return calls, fake_run


def test_adb_connect_returns_serial_on_success():
    calls, fake_run = _make_run(connect_stdout="already connected to 1.2.3.4:5555")
    mod.subprocess.run = fake_run
    ser = mod.adb_connect("192.168.68.86", 45019)
    assert ser == "192.168.68.86:45019", ser
    assert any("connect" in c for c in calls)


def test_adb_connect_returns_none_on_failure():
    calls, fake_run = _make_run(connect_stdout="failed to connect to 'x': Connection refused")
    mod.subprocess.run = fake_run
    ser = mod.adb_connect("192.168.68.86", 1)
    assert ser is None


def test_forward_cdp_port_is_device_aware():
    calls, fake_run = _make_run()
    mod.subprocess.run = fake_run
    ok = mod.forward_cdp_port("192.168.68.86:45019")
    assert ok is True
    fwd = [c for c in calls if "forward" in c][0]
    assert "-s" in fwd
    assert "192.168.68.86:45019" in fwd
    assert "tcp:9222" in fwd
    assert "localabstract:chrome_devtools_remote" in fwd


def test_forward_cdp_port_bare_when_no_serial():
    calls, fake_run = _make_run()
    mod.subprocess.run = fake_run
    ok = mod.forward_cdp_port(None)
    assert ok is True
    fwd = [c for c in calls if "forward" in c][0]
    assert "-s" not in fwd  # backward-compatible bare forward
    assert "localabstract:chrome_devtools_remote" in fwd


def test_forward_cdp_port_failure_propagates_false():
    calls, fake_run = _make_run(forward_rc=1)
    mod.subprocess.run = fake_run
    ok = mod.forward_cdp_port("192.168.68.86:45019")
    assert ok is False
