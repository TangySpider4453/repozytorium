#!/bin/bash
# Instalacja „głosu” serwerka na Pi (rozpoznawanie mowy, mowa, telefon SIP). Uruchamiane w tle z najniższym priorytetem:
#   sudo systemd-run --unit=instalacja-glosu --nice=19 -p IOSchedulingClass=idle bash /home/tonyg/glos/instaluj.sh
# whisper.cpp (rozpoznawanie polskiego), Piper (polski głos), pjproject + pjsua2 dla Pythona (telefon SIP).
set -euo pipefail
G=/home/tonyg/glos
LOG=$G/instalacja.log
exec >> "$LOG" 2>&1
echo "=== start $(date)"
apt-get install -y -qq cmake build-essential git libssl-dev libopus-dev uuid-dev python3-dev python3-setuptools swig python3-numpy >/dev/null
cd $G
sudo -u tonyg mkdir -p modele

# 1. whisper.cpp
if [ ! -x $G/whisper.cpp/build/bin/whisper-cli ]; then
  [ -d whisper.cpp ] || sudo -u tonyg git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git
  cd whisper.cpp
  sudo -u tonyg cmake -B build -DCMAKE_BUILD_TYPE=Release -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_EXAMPLES=ON
  sudo -u tonyg cmake --build build -j2 --config Release
  cd $G
fi
for m in base small-q5_1; do
  [ -f modele/ggml-$m.bin ] || sudo -u tonyg curl -fsSL -o modele/ggml-$m.bin "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-$m.bin"
done
echo "=== whisper gotowy $(date)"

# 2. Piper + polski głos
if [ ! -x $G/piper/piper ]; then
  sudo -u tonyg curl -fsSL -o /tmp/piper.tgz https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz
  sudo -u tonyg tar -xzf /tmp/piper.tgz -C $G && rm /tmp/piper.tgz
fi
for f in pl_PL-gosia-medium.onnx pl_PL-gosia-medium.onnx.json; do
  [ -f modele/$f ] || sudo -u tonyg curl -fsSL -o modele/$f "https://huggingface.co/rhasspy/piper-voices/resolve/main/pl/pl_PL/gosia/medium/$f"
done
echo "=== piper gotowy $(date)"

# 3. pjproject 2.15.1 z pjsua2 dla Pythona
if ! sudo -u tonyg python3 -c "import pjsua2" 2>/dev/null; then
  [ -d pjproject ] || { sudo -u tonyg curl -fsSL -o /tmp/pj.tgz https://github.com/pjsip/pjproject/archive/refs/tags/2.15.1.tar.gz; sudo -u tonyg tar -xzf /tmp/pj.tgz -C $G; mv $G/pjproject-2.15.1 $G/pjproject; rm /tmp/pj.tgz; }
  cd pjproject
  cat > pjlib/include/pj/config_site.h <<'CS'
#define PJMEDIA_HAS_VIDEO 0
#define PJMEDIA_AUDIO_DEV_HAS_ALSA 0
#define PJMEDIA_AUDIO_DEV_HAS_NULL_AUDIO 1
#define PJSUA_MAX_CALLS 4
CS
  chown -R tonyg:tonyg .
  sudo -u tonyg ./configure --enable-shared --disable-video --disable-sound --disable-libyuv --disable-libwebrtc CFLAGS="-O2 -fPIC" > /dev/null
  sudo -u tonyg make dep -j2 > /dev/null
  sudo -u tonyg make -j2 > /dev/null
  make install > /dev/null
  ldconfig
  cd pjsip-apps/src/swig/python
  sudo -u tonyg make > /dev/null
  python3 setup.py install --prefix=/usr/local > /dev/null || pip3 install --break-system-packages . > /dev/null
  cd $G
fi
sudo -u tonyg python3 -c "import pjsua2; print('pjsua2 OK', pjsua2.Endpoint().libVersion().full)"
echo "=== WSZYSTKO GOTOWE $(date)"
