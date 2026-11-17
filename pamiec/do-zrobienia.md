# Do zrobienia (stan 2026-11-17)

## Pilne / zmiana konta
- [ ] **Token Claude dla bota i telefonu** ze starego konta → Antek: na Pi `claude setup-token` (nowe konto),
  wpisać do `/etc/serwerek-bot/claude.env` jako `CLAUDE_CODE_OAUTH_TOKEN=…`, potem `bash ~/bot/bez_rozmowy.sh`.
- [ ] **Unieważnić/zmienić** sekrety, które padły w starych czatach (lista w `DOSTEP_PRYWATNE.md` na Pi): hasło NAS,
  Linphone Pi, portalu, token bota Telegram, stary klucz Tailscale.
- [ ] Scalić gałęzie (`claude/nauka-z-claude`, `lazik-mapa`, `claude/pamiec`) z domyślną — decyzja Antka.
- [ ] W nowej sesji sprawdzić, czy hook łączy się sam kluczem `TS_AUTHKEY`.

## Problemy
- [ ] 📞 Telefon nie słyszy Antka (od ~11.11): zadzwonić, mówić, odczytać `journalctl -u serwerek-telefon`
  („nasłuch: X s, poziom Y”). 0 s = brak RTP, poziom < 500 = wyciszony mikrofon.
- [ ] 🚗 Łazik: I2C zawiesza się od silników (kondensatory 100 nF, przewody, ew. 50 kHz za zgodą).
- [ ] Zdrowie: 1 incydent do „Przejrzane” (`rtg-garmin-teraz` z 05.11).

## Czeka na decyzję / dane od Antka
- [ ] Poczta: 4 hasła aplikacji (3× Gmail, 1× iCloud).
- [ ] Google Calendar OAuth (`python3 ~/bot/gkal.py link`).
- [ ] Aktualizacja Ollamy + test Gemma 3 (klasyfikator zablokował instalator — zgoda Antka).
- [ ] Mapowanie „Rozpiętki” w Garminie (hantle vs maszyna).
- [ ] Polski: tekst Tetmajera z podręcznikiem (s. 90); edukacja obywatelska: czy temat 4 obowiązuje.

## Pomysły
- Usunąć testowe modele Ollamy (`qwen3:*`, `llama3.2:3b`) — miejsce.
- Łazik: iPhone 14 Pro LiDAR przez Record3D jako kamera głębi; nowy OLED; radio DX-LR03 na UART.
- Planer nauki bez modelu: gotowy patch `niewdrozone_planer_i_lokalny_zapas.patch` w kopiach na Pi.
- Interaktywna wersja tej mapy jako strona na portalu.
