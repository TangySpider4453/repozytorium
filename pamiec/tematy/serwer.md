# Serwer Pi 4: portal, bot, telefon, zdrowie, NAS

Czytaj, gdy: portal (`pi/app.py`), bot, telefon, token Claude na Pi, zdrowie, NAS, kopie, usługi.
Pełna dokumentacja: `SERWER.md`. Zasady restartów: `zasady.md`.

## Usługi na Pi 4 — stan sprawdzony 2026-11-17 09:23

| Usługa | Co robi | Stan |
|---|---|---|
| `home-portal` | portal Flask `~/portal/app.py`, port 80, wszystkie strony `/strony/*` i API | ✅ |
| `serwerek-bot` | bot Telegram + Linphone czat, Claude (Haiku szybki / Sonnet mądry), pamięć `~/bot/pamiec.db` | ✅ (token Claude z nowego konta od 17.11, ważny rok) |
| `serwerek-telefon` | rozmowy głosowe Linphone (pjsua2), `~/glos/telefon.py` | ✅ (problem: nie słyszy Antka) |
| `glos-whisper` | rozpoznawanie mowy whisper.cpp | ✅ |
| `ollama` | modele lokalne (qwen2.5:1.5b zapas rozmów, qwen2.5:3b Garmin, moondream — stary model wizji; testowe usunięte 17.11) | ✅ |
| `trener-web` + `trener-cykl.timer` (15 min) + `trener-szybki.timer` (1 min: nowy trening → cykl) | apka **Trener** (`~/trener/`), HTTPS przez **Tailscale Funnel** :443 → 127.0.0.1:8095 (publicznie; `/api` tylko z zapamiętanym urządzeniem albo po haśle) | ✅ od 17.11 |
| portal przez **Funnel :8443** → 127.0.0.1:80 | panel z internetu, tylko po haśle (to samo co Trener) | ✅ od 22.11 |
| `playit`, `pi-dashboard` | tunel i panel Minecrafta | ✅ |
| `powernukkitx` | serwer Minecraft | ⏸️ wyłączony **celowo** (włączany ręcznie) |
| `airplay` | głośnik AirPlay 2 | ⏸️ inactive — nie ruszać bez zgody |
| `tailscaled`, `smbd`, `home-terminal`, `wayvnc` | sieć, Samba, terminal i VNC w przeglądarce | ✅ |

**Timery:** `kopia-pi` (02:00, pełny obraz systemu na NAS — ostatnia 17.11 OK), `logi-na-nas`, `nas-montuj`,
`google-lokalizacja`, `mc-autoupdate` (`rtg-garmin` usunięty 18.11).

**Zasoby 17.11:** 45 °C, throttled 0x0, RAM 1,8/7,6 GB, swap 0,7 GB, dysk 51% (po usunięciu testowych modeli Ollamy), uptime 19 dni.
**Zdrowie:** 0 aktywnych, 0 do przejrzenia (incydent `rtg-garmin-teraz` z 05.11 oznaczony jako przejrzany 17.11).

Szybki test: `systemctl is-active home-portal serwerek-bot serwerek-telefon glos-whisper ollama playit pi-dashboard`

## Projekty na portalu
| Projekt | Gdzie | Stan |
|---|---|---|
| 🤖 Bot Telegram/Linphone, todo, budziki | `~/bot/` | działa; token Claude z nowego konta (17.11, ważny do ~11.2027) |
| 📞 Telefon (rozmowy głosowe) | `~/glos/` | ❌ Pi nie słyszy Antka od ~11.11 |
| 🩺 Zdrowie serwera, NAS, kopia systemu | `/strony/zdrowie/` | działa |
| 📅 Kalendarz, Zadania, ZTM, Zawodowe, Zdalne, Automatyczne | portal | działa; Google Calendar OAuth odłożony |
| 📬 Poczta (tylko odczyt) | bot | czeka na 4 hasła aplikacji |
| 🔊 AirPlay 2 | Pi 4 | nie ruszać bez zgody |

## Ustalenia
- 2026-11-16: bez lokalnego modelu do rozmów i planowania (za wolny: 79–164 s). Garmin w bocie = parser regułowy + qwen2.5:3b.
- 2026-11-17: każdy Claude na Pi domyślnie Haiku; Sonnet tylko do cięższych rzeczy; **Opus nigdy** (za drogi).
- 2026-11-22: jedno hasło do portalu i Trenera (skrót tylko w `~/portal/dane/dostep.json`, zmiana `portal-haslo`).
  Portal z internetu przez Funnel :8443 (tylko po haśle; terminal i VNC tylko Tailscale). Ciasteczka `trener_klucz` /
  `portal_sesja` przyjmowane w obie strony (ten sam host ts.net), `/trener` w portalu = przejście do apki.
- 2026-11-26: rozmowa telefoniczna = Sonnet effort low (proces „rozmowa”), nie Haiku i nie medium: szybko i w miarę dokładnie.

### Token Claude na Pi (2026-11-17)
- Bot i telefon używają `CLAUDE_CODE_OAUTH_TOKEN` z `/etc/serwerek-bot/claude.env` (z `claude setup-token`, ważny rok). **Nigdy nie wypisuj.**
- Odnawianie z chmury: `tmux new -d -x 400 claude setup-token` na Pi → link Antkowi → jego jednorazowy kod przez
  `tmux send-keys` → token z `capture-pane` do pliku 600 (sed maskuje `sk-ant-…`) → test `claude -p` → zapis do env →
  `bez_rozmowy.sh`. Albo Antek sam: `bash ~/bot/nowy_token.sh` w terminalu portalu.
- Claude Code na Pi: `~/.claude/settings.json` = `autoCompactWindow` 200000 + `CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS=100000`.

## Otwarte
- [ ] 📞 Telefon nie słyszy Antka (od ~11.11): zadzwonić, mówić, `journalctl -u serwerek-telefon` („nasłuch: X s,
  poziom Y”). 0 s = brak RTP, poziom < 500 = wyciszony mikrofon.
- [ ] **Unieważnić/zmienić** sekrety ze starych czatów (lista w `DOSTEP_PRYWATNE.md` na Pi): hasło NAS, Linphone Pi,
  token bota Telegram, stary klucz Tailscale (hasło portalu zmienione 22.11).
- [ ] Portal: usunąć martwe resztki mostu RestOrTrain (`/api/garmin`, `/api/garmin/silownia`, moduł `garmin` na
  Automatycznych, strona Siłownia). Restart portalu: zapytać Antka.
- [ ] Sprawdzić z internetu (bez Tailscale) panel na :8443 i przełączniki Trener ⇄ panel (z kontenera Claude 8443 zablokowany).
- [ ] Czeka na Antka: poczta (4 hasła aplikacji: 3× Gmail, 1× iCloud), Google Calendar OAuth (`python3 ~/bot/gkal.py link`),
  aktualizacja Ollamy + test Gemma 3 (klasyfikator zablokował instalator).
- Pomysł: interaktywna wersja mapy mózgu jako strona na portalu.

## Dziennik (najnowsze na górze; starsze: `archiwum/`)
- 2026-11-26: telefon szybszy: pauza końca mowy 3 s → 1,1 s (+ próg ciszy względem głośności mowy), Sonnet low
  w procesie „rozmowa” rozgrzewanym przy odebraniu, log czasów każdej odpowiedzi. Wcześniej Antek rozłączał się,
  zanim Pi odpowiedziało (np. 20.11: 12 s od końca mowy do rozpoznania).
- 2026-11-22: logowanie hasłem w Trenerze i portal przez Funnel :8443 z przełączaniem bez logowania; hasło portalu
  zmienione (`portal-haslo`); usunięto 60 śmieciowych „urządzeń” curl z tabeli Trenera.
- 2026-11-17: nowy token Claude (stary przestał działać), usunięte testowe modele Ollamy (dysk 61% → 51%),
  incydent `rtg-garmin-teraz` oznaczony jako przejrzany.
