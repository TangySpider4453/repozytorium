#!/bin/bash
# Instalacja kopii zapasowych na Pi 5 / Zero 2W (jako użytkownik z sudo, z katalogu z tymi plikami).
# Wypisuje klucz publiczny, który trzeba dopisać na Pi 4 (zrobi to instaluj-most.sh albo Claude).
set -e
cd "$(dirname "$0")"
sudo apt-get install -y -q zstd >/dev/null
sudo install -m 755 lazik-kopia /usr/local/sbin/lazik-kopia
sudo install -m 644 lazik-kopia.service lazik-kopia.timer /etc/systemd/system/
sudo mkdir -p /root/.ssh && sudo chmod 700 /root/.ssh
sudo test -f /root/.ssh/lazik_kopia || sudo ssh-keygen -q -t ed25519 -N "" -C "lazik-kopia@$(hostname)" -f /root/.ssh/lazik_kopia
sudo systemctl daemon-reload
sudo systemctl enable --now lazik-kopia.timer
echo "KLUCZ: $(sudo cat /root/.ssh/lazik_kopia.pub)"
