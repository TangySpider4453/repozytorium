#!/bin/bash
# Instalacja polaczenia z NAS, logow na NAS i nocnej kopii systemu (uruchom na Pi: sudo bash instaluj.sh).
# Wymaga /etc/nas-credentials (username=..., password=..., chmod 600, wlasciciel root) - nie ma go w repozytorium.
set -e
cd "$(dirname "$0")"
[ -f /etc/nas-credentials ] || { echo "Brak /etc/nas-credentials"; exit 1; }
chmod 600 /etc/nas-credentials
apt-get install -y -qq cifs-utils rsync dosfstools e2fsprogs > /dev/null
install -m 755 nas-montuj kopia-pi logi-na-nas /usr/local/sbin/
install -m 755 raspiproszewylaczsie /usr/local/bin/
install -d /usr/local/lib/kopia-pi /var/lib/kopia-pi /mnt/nas
install -m 644 JAK-PRZYWROCIC.txt CZYTAJ.txt /usr/local/lib/kopia-pi/
install -m 755 przywroc.sh /usr/local/lib/kopia-pi/
install -m 644 nas-montuj.service nas-montuj.timer logi-na-nas.service logi-na-nas.timer kopia-pi.service kopia-pi.timer /etc/systemd/system/
install -d /etc/systemd/journald.conf.d
install -m 644 journald-trwaly.conf /etc/systemd/journald.conf.d/50-trwaly.conf
LINIA='//172.23.0.28/Tony-Folder /mnt/nas cifs credentials=/etc/nas-credentials,vers=3.0,uid=1000,gid=1000,file_mode=0660,dir_mode=0770,iocharset=utf8,soft,echo_interval=10,_netdev,nofail,x-systemd.mount-timeout=30 0 0'
if ! grep -q ' /mnt/nas cifs ' /etc/fstab; then
    cp /etc/fstab /etc/fstab.przed_nasem
    echo "$LINIA" >> /etc/fstab
fi
systemctl daemon-reload
mkdir -p /var/log/journal && systemd-tmpfiles --create --prefix /var/log/journal && systemctl restart systemd-journald
systemctl enable --now nas-montuj.timer logi-na-nas.timer kopia-pi.timer
/usr/local/sbin/nas-montuj
mountpoint -q /mnt/nas && echo "NAS zamontowany: $(ls /mnt/nas/Raspberry)" || echo "UWAGA: NAS nie zamontowany"
