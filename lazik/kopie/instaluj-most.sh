#!/bin/bash
# Instalacja mostu na Pi 4 (serwer domowy): tylko dodaje skrypt odbiornika i folder na NAS,
# nie zmienia żadnych istniejących usług. Klucze klientów dopisuje: dodaj-klucz.sh <nazwa-pi> "<klucz publiczny>".
set -e
cd "$(dirname "$0")"
sudo install -m 755 lazik-kopia-odbierz /usr/local/sbin/lazik-kopia-odbierz
mountpoint -q /mnt/nas && [ -f /mnt/nas/Raspberry/.nas ] && mkdir -p /mnt/nas/Raspberry/Kopie-lazika
echo "Most gotowy."
