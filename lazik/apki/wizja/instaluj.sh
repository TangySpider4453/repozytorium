#!/bin/bash
# Instalacja aplikacji "Łazik: wizja" na Pi 5 (uruchamiać jako rpi, z katalogu ~/lazik/wizja).
set -e
cd "$(dirname "$0")"
sudo apt-get install -y hailo-all python3-opencv python3-pyqt5 qtwayland5 v4l-utils
chmod +x uruchom.sh wizja.py skany.sh
# model głębi dla trybu „Przestrzeń” (Hailo Model Zoo, wersja zgodna z HailoRT 4.23) i three.js do podglądu skanów
mkdir -p modele skany zdjecia
[ -f modele/scdepthv3.hef ] || curl -fsSL -o modele/scdepthv3.hef \
  https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v2.17.0/hailo8/scdepthv3.hef
for m in yolov8m yolov8x; do  # większe modele obiektów (wybór przyciskiem „Model” w aplikacji)
  [ -f modele/$m.hef ] || curl -fsSL -o modele/$m.hef \
    https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v2.17.0/hailo8/$m.hef
done
mkdir -p nagrania
[ -f three.min.js ] || curl -fsSL -o three.min.js https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js
mkdir -p ~/Desktop ~/.local/share/applications
for d in lazik-wizja.desktop lazik-skany.desktop; do
  cp $d ~/Desktop/ && cp $d ~/.local/share/applications/ && chmod +x ~/Desktop/$d
done
# pulpit (pcmanfm) uruchamia ikonę od razu, bez pytania "wykonać?"
mkdir -p ~/.config/libfm
if [ -f ~/.config/libfm/libfm.conf ]; then
  grep -q '^quick_exec=' ~/.config/libfm/libfm.conf \
    && sed -i 's/^quick_exec=.*/quick_exec=1/' ~/.config/libfm/libfm.conf \
    || sed -i '/^\[config\]/a quick_exec=1' ~/.config/libfm/libfm.conf
else
  printf '[config]\nquick_exec=1\n' > ~/.config/libfm/libfm.conf
fi
echo "Gotowe. Po instalacji hailo-all pierwszy raz: sudo reboot."
