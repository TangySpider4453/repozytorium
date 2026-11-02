#!/bin/bash
# Ikona „Łazik: sterowanie”: otwiera stronę sterowania (usługa lazik-sterowanie działa w tle od startu Pi).
cd "$(dirname "$0")"
KOD=$(cat kod_dostepu.txt 2>/dev/null)
FLAGI=()
[ -n "$WAYLAND_DISPLAY" ] && FLAGI+=(--ozone-platform=wayland)
exec chromium "${FLAGI[@]}" --app="http://localhost:8000/?t=$KOD" --start-maximized >/dev/null 2>&1
