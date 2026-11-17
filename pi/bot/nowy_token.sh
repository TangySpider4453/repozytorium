#!/bin/bash
# Podmiana tokenu Claude dla bota i telefonu (nowe konto). Uruchom w terminalu na Pi: bash ~/bot/nowy_token.sh
# Token nie jest nigdzie wypisywany: trafia tylko do /etc/serwerek-bot/claude.env (root, 600).
set -u
CLAUDE=/home/tonyg/.local/bin/claude
ENV=/etc/serwerek-bot/claude.env
LOG=$(mktemp); chmod 600 "$LOG"
trap 'shred -u "$LOG" 2>/dev/null; rm -f "$LOG"' EXIT

echo "1) Otworzy się logowanie Claude. Otwórz link, zaloguj się NOWYM kontem, wklej kod tutaj."
echo
# szeroki terminal, żeby token nie był łamany na linie
script -qfc "stty cols 400 2>/dev/null; $CLAUDE setup-token" "$LOG"

TOKEN=$(sed 's/\x1b\[[0-9;?]*[a-zA-Z]//g' "$LOG" | tr -d '\r' | grep -oE 'sk-ant-oat01-[A-Za-z0-9_-]+' | tail -1)
if [ -z "$TOKEN" ]; then
  echo "❌ Nie znalazłem tokenu w wyniku. Nic nie zmieniono."; exit 1
fi
echo; echo "2) Mam token (…${TOKEN: -4}). Test nowego tokenu…"
OUT=$(cd /tmp && CLAUDE_CODE_OAUTH_TOKEN="$TOKEN" timeout 120 "$CLAUDE" -p "Odpowiedz jednym słowem: OK" 2>&1 | tail -3)
if ! echo "$OUT" | grep -qi "ok"; then
  echo "❌ Test nie przeszedł: $OUT"; echo "Stary token zostaje. Nic nie zmieniono."; exit 1
fi
echo "   ✅ działa"

echo "3) Zapis do $ENV (kopia starego: $ENV.bak_$(date +%F))"
sudo cp -p "$ENV" "$ENV.bak_$(date +%F)"
printf '%s' "$TOKEN" | sudo python3 -c '
import sys
p = sys.argv[1]; t = sys.stdin.read().strip()
lines = [l for l in open(p).read().splitlines() if not l.startswith("CLAUDE_CODE_OAUTH_TOKEN=")]
lines.append("CLAUDE_CODE_OAUTH_TOKEN=" + t)
open(p, "w").write("\n".join(lines) + "\n")
' "$ENV"
sudo chown root:root "$ENV"; sudo chmod 600 "$ENV"

echo "4) Restart bota i telefonu (czeka, aż nie będzie rozmowy)…"
bash /home/tonyg/bot/bez_rozmowy.sh
echo; echo "✅ Gotowe. Napisz coś do bota na Telegramie, żeby sprawdzić."
