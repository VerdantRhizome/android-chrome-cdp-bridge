#!/bin/sh
# Capture the Tab S9 screen to a PNG so Hermes can inspect the Android UI
# (Wireless-debugging dialogs, the "Allow" prompt, etc.) via vision_analyze.
#
# Usage: capture_tab.sh [output.png]
#   default output: <project>/screen.png
# Requires a working `adb` connection (after pairing).
set -e
OUT="${1:-/data/data/com.termux/files/home/projects/android-chrome-cdp-bridge/screen.png}"
mkdir -p "$(dirname "$OUT")"
adb exec-out screencap -p > "$OUT"
echo "saved: $OUT"
