#!/bin/bash
# Instalacja „Łazik: sterowanie” na Pi 5 (jako rpi, z ~/lazik/sterowanie). Wymaga ~/lazik/wizja (modele, wspólny kod).
set -e
cd "$(dirname "$0")"
sudo apt-get install -y -q python3-flask python3-gpiozero python3-lgpio python3-opencv >/dev/null
chmod +x lazik_serwer.py otworz.sh
sudo cp lazik-sterowanie.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lazik-sterowanie.service
cp lazik-sterowanie.desktop ~/Desktop/ && cp lazik-sterowanie.desktop ~/.local/share/applications/ && chmod +x ~/Desktop/lazik-sterowanie.desktop
echo "Gotowe. Strona: http://$(hostname -I | cut -d' ' -f1):8000/?t=\$(cat kod_dostepu.txt)"
