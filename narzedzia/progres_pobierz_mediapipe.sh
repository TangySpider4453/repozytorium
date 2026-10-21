#!/bin/bash
# Pobiera MediaPipe Tasks Vision (rozpoznawanie sylwetki) do ~/portal/sites/progres/mp/ na Raspberry Pi.
# Uruchamiać NA PI. Pliki nie są w repozytorium (ok. 37 MB).
set -euo pipefail
V=0.10.14
D=~/portal/sites/progres/mp
B=https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@$V
mkdir -p "$D/wasm"
for f in vision_bundle.mjs wasm/vision_wasm_internal.js wasm/vision_wasm_internal.wasm wasm/vision_wasm_nosimd_internal.js wasm/vision_wasm_nosimd_internal.wasm; do
  curl -sSfL -o "$D/$f" "$B/$f"
done
curl -sSfL -o "$D/pose_landmarker_full.task" https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task
cd "$D" && sha256sum vision_bundle.mjs wasm/* pose_landmarker_full.task
