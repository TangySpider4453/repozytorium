# Trener — własny RestOrTrain (webapka na Pi 4)

Dane z Garmin Connect (nieoficjalne API, `garminconnect`) → SQLite → analizy i plany od Claude → treningi
(rower, bieg, siłka) automatycznie na zegarek/Edge → powiadomienia (push w webapce + Linphone) → czat z trenerem.

## Gdzie co jest (Pi 4, `~/trener/`)
| Część | Plik |
|---|---|
| synchronizacja (dni: sen, HRV, podsumowanie, gotowość, status; aktywności + serie siłowe) | `trener/sync.py`, wartości dnia `trener/dane.py` |
| kontekst dla Claude (14 dni, aktywności 28 dni, tygodnie, miesiące z całej historii, plan, pamięć) | `trener/kontekst.py` |
| Claude CLI (`--json-schema`, bez narzędzi, pusty katalog) | `trener/ai.py` |
| analizy: rano (po śnie), po treningu, tydzień (pon.) | `trener/analiza.py` |
| plan na 7 dni (`zostaw_id` = bez zmian), walidacja, diff | `trener/plan.py` |
| plan → JSON treningu Garmin (strefy tętna, moc, tempo, kadencja; siłka z listą ćwiczeń) | `trener/budowa.py`, `trener/zasoby/` |
| wysyłanie / usuwanie (TYLKO ze znacznikiem `auto: trener` w opisie) | `trener/zegarek.py` |
| czat (akcje: przeplanuj, zapamiętaj, ustawienia, dane z dowolnego okresu) | `trener/czat.py` |
| push (VAPID w `dane/vapid.json`) + kolejka bota | `trener/powiadom.py` |
| cykl co 20 min | `trener/cykl.py`, `systemd/trener-cykl.*` |
| webapka (Flask 127.0.0.1:8095) + PWA | `trener/web.py`, `static/` |

## Uruchamianie
- `trener-web.service` (Flask) i `trener-cykl.timer` (co 20 min), oba z `EnvironmentFile=/etc/serwerek-bot/claude.env`.
- Na zewnątrz tylko w tailnecie: `sudo tailscale serve --bg --https=443 http://127.0.0.1:8095` (certyfikat Let's Encrypt
  od Tailscale). Adres apki: `https://<nazwa Pi w tailnecie>/` (zapisany też w bazie, `kv.adres_apki`; nie w repo).
- Ręcznie: `.venv/bin/python -m trener sync | historia | dzien RRRR-MM-DD | cykl | analiza rano | plan "prośba"`.
  Polecenia z Claude potrzebują tokenu: `sudo systemd-run --uid=tonyg -p EnvironmentFile=/etc/serwerek-bot/claude.env
  -E HOME=/home/tonyg --wait --pipe ...`.
- Token Garmina wspólny z `~/restortrain-garmin/tokens` (logowanie z blokadą `dane/garmin.lock`).

## iPhone
Safari → adres apki → Share → **Add to Home Screen** → otwórz z ekranu głównego → ⚙️ → **Włącz powiadomienia**.
(Push w webapkach iOS działa tylko z ekranu głównego, iOS 16.4+.)

## Dane (`dane/`, poza gitem)
`trener.db` (surowe odpowiedzi skompresowane zlib, aktywności, dni, analizy, plan, czat, push), `ustawienia.json`,
`vapid.json`.
