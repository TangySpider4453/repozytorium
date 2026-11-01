#!/bin/bash
# Instalacja aplikacji "Łazik: wizja" na Pi 5 (uruchamiać jako rpi, z katalogu ~/lazik/wizja).
set -e
cd "$(dirname "$0")"
sudo apt-get install -y hailo-all python3-opencv python3-pyqt5 qtwayland5
chmod +x uruchom.sh wizja.py
mkdir -p ~/Desktop ~/.local/share/applications
cp lazik-wizja.desktop ~/Desktop/
cp lazik-wizja.desktop ~/.local/share/applications/
chmod +x ~/Desktop/lazik-wizja.desktop
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
