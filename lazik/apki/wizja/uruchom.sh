#!/bin/bash
# Start aplikacji "Łazik: wizja" (ikona na pulpicie). Log: ~/lazik/wizja/wizja.log
cd "$(dirname "$0")"
# pulpit Pi 5 to Wayland (labwc); bez tego Qt5 próbuje X11 i nie startuje
if [ -n "$WAYLAND_DISPLAY" ]; then export QT_QPA_PLATFORM=wayland; fi
exec python3 wizja.py "$@" >wizja.log 2>&1
