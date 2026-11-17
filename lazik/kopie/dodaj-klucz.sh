#!/bin/bash
# Na Pi 4: dopisuje klucz kopii jednego Pi do ~/.ssh/authorized_keys z wymuszonym poleceniem (tylko odbiornik kopii).
set -e
PI="$1"; KLUCZ="$2"
case "$PI" in rpi-5-1|rpi-zero2w-a1|rpi-zero2w-a2) ;; *) echo "nieznany Pi: $PI"; exit 2 ;; esac
mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
grep -vF "lazik-kopia@$PI" ~/.ssh/authorized_keys > ~/.ssh/authorized_keys.nowe || true
echo "command=\"/usr/local/sbin/lazik-kopia-odbierz $PI\",restrict $KLUCZ" >> ~/.ssh/authorized_keys.nowe
mv ~/.ssh/authorized_keys.nowe ~/.ssh/authorized_keys
echo "Dodano klucz dla $PI"
