#!/bin/bash
# Start aplikacji "Łazik: analiza wideo" (ikona na pulpicie). Log: ~/lazik/analiza/analizator.log
cd "$(dirname "$0")"
if [ -n "$WAYLAND_DISPLAY" ]; then export QT_QPA_PLATFORM=wayland; fi
exec python3 analizator.py "$@" >analizator.log 2>&1
