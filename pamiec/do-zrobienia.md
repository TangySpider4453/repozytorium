# Do zrobienia (stan 2026-11-17)

## Pilne / zmiana konta
- [x] Token Claude dla bota i telefonu z nowego konta (17.11, ważny rok → odnowić ~11.2027 przez
  `bash ~/bot/nowy_token.sh` albo tak jak w `decyzje.md`).
- [ ] **Unieważnić/zmienić** sekrety, które padły w starych czatach (lista w `DOSTEP_PRYWATNE.md` na Pi): hasło NAS,
  Linphone Pi, portalu, token bota Telegram, stary klucz Tailscale.
- [x] Scalić gałęzie z domyślną (2026-11-17). Ewentualnie usunąć stare gałęzie na GitHubie.
- [x] Hook łączy się sam kluczem `TS_AUTHKEY` (potwierdzone 17.11); `ssh pi` nadal pyta o link „check”.

## Trener (nowa apka, 17.11)
- [ ] Antek: otworzyć apkę na iPhonie, Add to Home Screen, włączyć push, wypełnić **ankietę startową** (karta „Zacznijmy” → 7 kroków + dopytanie). Bez niej apka nie planuje.
- [ ] Po pierwszym planie i jego sprawdzeniu na zegarku: wyłączyć stary most (`sudo systemctl disable --now rtg-garmin.timer`)
  i zdecydować, czy RestOrTrain w ogóle zostaje.
- [ ] Sprawdzić, czy `trener-historia` (pobieranie od 2021) skończył: `kv.historia_postep == "gotowe"`.
- [ ] Antek: podać terminy ferii/egzaminów i ewentualnych zawodów (trener wstawi je do periodyzacji).
- [ ] Pomysły: porównanie plan vs wykonanie w analizach, rekordy mocy (power curve), FTP z testu, pływanie/inne sporty.

## Problemy
- [ ] 📞 Telefon nie słyszy Antka (od ~11.11): zadzwonić, mówić, odczytać `journalctl -u serwerek-telefon`
  („nasłuch: X s, poziom Y”). 0 s = brak RTP, poziom < 500 = wyciszony mikrofon.
- [ ] 🚗 Łazik: I2C zawiesza się od silników (kondensatory 100 nF, przewody, ew. 50 kHz za zgodą).
- [x] Zdrowie: incydent `rtg-garmin-teraz` z 05.11 oznaczony jako przejrzany (17.11).

## Czeka na decyzję / dane od Antka
- [ ] Poczta: 4 hasła aplikacji (3× Gmail, 1× iCloud).
- [ ] Google Calendar OAuth (`python3 ~/bot/gkal.py link`).
- [ ] Aktualizacja Ollamy + test Gemma 3 (klasyfikator zablokował instalator — zgoda Antka).
- [ ] Mapowanie „Rozpiętki” w Garminie (hantle vs maszyna).
- [ ] Polski: tekst Tetmajera z podręcznikiem (s. 90); edukacja obywatelska: czy temat 4 obowiązuje.

## Pomysły
- Łazik: iPhone 14 Pro LiDAR przez Record3D jako kamera głębi; nowy OLED; radio DX-LR03 na UART.
- Planer nauki bez modelu: gotowy patch `niewdrozone_planer_i_lokalny_zapas.patch` w kopiach na Pi.
- Interaktywna wersja tej mapy jako strona na portalu.
