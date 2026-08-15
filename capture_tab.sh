#!/bin/sh
# Capture the device screen to a PNG so Hermes can inspect the Android UI
# (Wireless-debugging dialogs, the "Allow" prompt, etc.) via vision_analyze.
#
# Usage: capture_tab.sh [output.png]
#   default output: ./screen.png (current directory)
# Requires a working `adb` connection (after pairing).
set -e
OUT="${1:-screen.png}"
mkdir -p "$(dirname "$OUT")"
adb exec-out screencap -p > "$OUT"
echo "saved: $OUT"
