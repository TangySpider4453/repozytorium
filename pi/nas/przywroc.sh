#!/bin/bash
# Odtwarza karte SD Raspberry Pi z kopii raspberry-system.img (ten folder na NAS).
#
#   sudo ./przywroc.sh /dev/sdX [raspberry-system.img]
#
# /dev/sdX = NOWA karta SD w czytniku (CALA zostanie wyczyszczona). Uruchom na dowolnym Linuksie: laptop, inne Pi,
# albo to samo Pi uruchomione z pendrive'a. Karta musi miec co najmniej tyle miejsca, ile zajmuje kopia (~25 GB).
# Partycje dostaja te same identyfikatory (PARTUUID, UUID) co stara karta, wiec Pi uruchomi sie bez zadnych poprawek.
set -euo pipefail
DEV=${1:-}
IMG=${2:-$(dirname "$0")/raspberry-system.img}
[ "$(id -u)" = 0 ] || { echo "Uruchom jako root (sudo)."; exit 1; }
[ -b "$DEV" ] || { echo "Uzycie: sudo $0 /dev/sdX [raspberry-system.img]   (/dev/sdX = nowa karta)"; lsblk -d -o NAME,SIZE,MODEL,TRAN; exit 1; }
[ -f "$IMG" ] || { echo "Nie ma pliku kopii: $IMG"; exit 1; }
if lsblk -no MOUNTPOINT "$DEV" | grep -qx '/'; then echo "$DEV to dysk z dzialajacym systemem. Przerwano."; exit 1; fi
for x in mkfs.vfat mkfs.ext4 sfdisk rsync partprobe; do command -v $x >/dev/null || { echo "Brak programu: $x (apt install dosfstools e2fsprogs fdisk rsync parted)"; exit 1; }; done

lsblk "$DEV"
read -r -p "WSZYSTKO na $DEV zostanie skasowane. Wpisz TAK, aby kontynuowac: " ok
[ "$ok" = TAK ] || exit 1

W=$(mktemp -d)
mkdir -p "$W/kopia" "$W/root" "$W/boot"
sprzataj() { set +e; umount "$W/boot" "$W/root" 2>/dev/null; umount "$W/kopia" 2>/dev/null; rmdir "$W"/* "$W" 2>/dev/null; }
trap sprzataj EXIT
mount -o ro,loop "$IMG" "$W/kopia"
I=$W/kopia/.kopia-info
echo "Kopia z: $(cat "$I/data-kopii.txt" 2>/dev/null)"

umount "$DEV"?* 2>/dev/null || true
# ta sama tablica partycji; ostatnia partycja (system) wypelnia cala nowa karte
sed -E '/^\/dev\/[a-z0-9]+(p)?2 :/ s/size= *[0-9]+, *//' "$I/partycje.sfdisk" | grep -v '^last-lba' | sfdisk --wipe always "$DEV"
partprobe "$DEV"; sleep 3
P1=$(lsblk -lnpo NAME "$DEV" | sed -n 2p); P2=$(lsblk -lnpo NAME "$DEV" | sed -n 3p)
pole() { grep "p$1:" "$I/blkid.txt" | grep -o " $2=\"[^\"]*\"" | cut -d'"' -f2; }
BOOT_UUID=$(pole 1 UUID | tr -d '-'); ROOT_UUID=$(pole 2 UUID)
mkfs.vfat -F 32 -n bootfs ${BOOT_UUID:+-i $BOOT_UUID} "$P1"
mkfs.ext4 -F -L rootfs ${ROOT_UUID:+-U $ROOT_UUID} "$P2"
mount "$P2" "$W/root"
echo "Kopiuje system (to potrwa)..."
rsync -aAXH --numeric-ids --info=progress2 --exclude='/.kopia-info' --exclude='/boot/firmware/*' "$W/kopia/" "$W/root/"
mkdir -p "$W/root/boot/firmware"
mount "$P1" "$W/boot"
rsync -rt --info=progress2 "$W/kopia/boot/firmware/" "$W/boot/"
sync
echo "Gotowe. Wloz karte do Raspberry Pi i wlacz zasilanie."
