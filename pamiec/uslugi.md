# Usługi na Pi 4 — stan sprawdzony 2026-11-17 09:06

| Usługa | Co robi | Stan |
|---|---|---|
| `home-portal` | portal Flask `~/portal/app.py`, port 80, wszystkie strony `/strony/*` i API | ✅ |
| `serwerek-bot` | bot Telegram + Linphone czat, Claude (Haiku szybki / Sonnet mądry), pamięć `~/bot/pamiec.db` | ✅ (token Claude jeszcze ze **starego konta**) |
| `serwerek-telefon` | rozmowy głosowe Linphone (pjsua2), `~/glos/telefon.py` | ✅ (problem: nie słyszy Antka) |
| `glos-whisper` | rozpoznawanie mowy whisper.cpp | ✅ |
| `ollama` | modele lokalne (qwen2.5:1.5b zapas rozmów, qwen2.5:3b Garmin, + testowe) | ✅ |
| `rtg-garmin.timer` | RestOrTrain → Garmin co 10 min | ✅ |
| `playit`, `pi-dashboard` | tunel i panel Minecrafta | ✅ |
| `powernukkitx` | serwer Minecraft | ⏸️ wyłączony **celowo** (włączany ręcznie) |
| `airplay` | głośnik AirPlay 2 | ⏸️ inactive — nie ruszać bez zgody |
| `tailscaled`, `smbd`, `home-terminal`, `wayvnc` | sieć, Samba, terminal i VNC w przeglądarce | ✅ |

**Timery:** `kopia-pi` (02:00, pełny obraz systemu na NAS — ostatnia 17.11 OK), `logi-na-nas`, `nas-montuj`,
`google-lokalizacja`, `mc-autoupdate`, `rtg-garmin`.

**Zasoby 17.11:** 45 °C, throttled 0x0, RAM 1,8/7,6 GB, swap 0,7 GB, dysk 61%, uptime 19 dni.
**Zdrowie:** 0 aktywnych, 1 do przejrzenia (`rtg-garmin-teraz.service` failed 05.11, zakończony).

Szybki test: `systemctl is-active home-portal serwerek-bot serwerek-telefon glos-whisper ollama playit pi-dashboard`
