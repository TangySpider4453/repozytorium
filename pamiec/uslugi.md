# Usługi na Pi 4 — stan sprawdzony 2026-11-17 09:23

| Usługa | Co robi | Stan |
|---|---|---|
| `home-portal` | portal Flask `~/portal/app.py`, port 80, wszystkie strony `/strony/*` i API | ✅ |
| `serwerek-bot` | bot Telegram + Linphone czat, Claude (Haiku szybki / Sonnet mądry), pamięć `~/bot/pamiec.db` | ✅ (token Claude z nowego konta od 17.11, ważny rok) |
| `serwerek-telefon` | rozmowy głosowe Linphone (pjsua2), `~/glos/telefon.py` | ✅ (problem: nie słyszy Antka) |
| `glos-whisper` | rozpoznawanie mowy whisper.cpp | ✅ |
| `ollama` | modele lokalne (qwen2.5:1.5b zapas rozmów, qwen2.5:3b Garmin, moondream — stary model wizji; testowe usunięte 17.11) | ✅ |
| `rtg-garmin.timer` | RestOrTrain → Garmin co 10 min | ✅ |
| `trener-web` + `trener-cykl.timer` (20 min) | apka **Trener** (`~/trener/`), HTTPS przez `tailscale serve` :443 → 127.0.0.1:8095 | ✅ od 17.11 |
| `playit`, `pi-dashboard` | tunel i panel Minecrafta | ✅ |
| `powernukkitx` | serwer Minecraft | ⏸️ wyłączony **celowo** (włączany ręcznie) |
| `airplay` | głośnik AirPlay 2 | ⏸️ inactive — nie ruszać bez zgody |
| `tailscaled`, `smbd`, `home-terminal`, `wayvnc` | sieć, Samba, terminal i VNC w przeglądarce | ✅ |

**Timery:** `kopia-pi` (02:00, pełny obraz systemu na NAS — ostatnia 17.11 OK), `logi-na-nas`, `nas-montuj`,
`google-lokalizacja`, `mc-autoupdate`, `rtg-garmin`.

**Zasoby 17.11:** 45 °C, throttled 0x0, RAM 1,8/7,6 GB, swap 0,7 GB, dysk 51% (po usunięciu testowych modeli Ollamy), uptime 19 dni.
**Zdrowie:** 0 aktywnych, 0 do przejrzenia (incydent `rtg-garmin-teraz` z 05.11 oznaczony jako przejrzany 17.11).

Szybki test: `systemctl is-active home-portal serwerek-bot serwerek-telefon glos-whisper ollama playit pi-dashboard`
