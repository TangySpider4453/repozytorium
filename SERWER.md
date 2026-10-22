# Serwer domowy (Raspberry Pi 4B): opis dla kolejnych sesji

Portal: **http://100.108.241.58/** (Tailscale, bez hasła) i **http://172.23.0.20/** (sieć domowa, z hasłem), `~/portal/app.py` (kopia w repo: `pi/app.py`), usługa
`home-portal`. Na Pi działa też **serwer Minecraft, na którym grają znajomi** (`powernukkitx`, `playit`,
`pi-dashboard`): nie restartuj ich i nie rób rebootu bez pytania. Po każdej zmianie portalu sprawdź
`systemctl is-active home-portal powernukkitx playit pi-dashboard`.

Pi jest w tej samej sieci lokalnej co serwer NAS użytkownika (eth0 172.23.0.20, wlan0 172.23.0.24), NAS: Synology
DSM 7, **172.23.0.28** (szczegóły niżej).

## NAS: zdjęcia, logi i nocna kopia systemu (od 2026-10-22)
- **Połączenie**: udział SMB `//172.23.0.28/Tony-Folder` → `/mnt/nas` (linia w `/etc/fstab`, `soft`, `nofail`),
  użytkownik `tony`, hasło **tylko** w `/etc/nas-credentials` (root, 600; nigdy w repo). `nas-montuj.timer` co 2 min
  montuje ponownie, gdy połączenie padło, i tworzy foldery. SSH na NAS dla `tony` jest zablokowane, SMB bez rozszerzeń
  POSIX (dlatego kopia systemu jest w pliku z ext4, a nie jako zwykłe pliki).
- **Widoczne foldery** w `Tony-Folder/Raspberry/` (opis: `CZYTAJ.txt`; znacznik `.nas` = to właściwy folder):
  `Logi/` (`zdrowie-dziennik.log`, `zdrowie-incydenty.json`, `kopia-systemu.log`, `system/RRRR-MM-DD.log`),
  `Progres-zdjecia/` (+ `dane.json`, `Usuniete/`), `Progres-filmy/`, `Kopia-systemu/`.
- **Portal** (`app.py`, wątek `nas_petla` co 30 s albo od razu po zmianie): zdjęcia i filmy Progres zapisuje prosto
  na NAS; gdy NAS niedostępny, do bufora na Pi (`dane/progres/zdjecia`, `filmy`) i od razu czerwona dioda
  („nas_bufor”, startuje po 1 wykryciu). Po powrocie NAS bufor przenosi się sam. Logi zdrowia i `dane.json` są
  lustrzane na NAS po każdej zmianie. Monitor: „NAS niedostępny” (czerwona), „Nocna kopia systemu nie udała się”
  (czerwona), „Dawno nie było kopii” (> 26 h żółta, > 50 h czerwona).
- **Dziennik systemu**: journald trwały (`/etc/systemd/journald.conf.d/50-trwaly.conf`, max 300 MB), `logi-na-nas.timer`
  co minutę dopisuje nowe wpisy do `Logi/system/<data>.log` (kursor w `/var/lib/kopia-pi/journal.kursor`, zaległe
  dochodzą po powrocie NAS).
- **Kopia całego systemu**: `kopia-pi.timer` codziennie 02:00 (`Persistent=true`: nadrabia, jeśli Pi było wyłączone).
  `/usr/local/sbin/kopia-pi`: plik `Kopia-systemu/raspberry-system.img` (rzadki, 64 GB, ext4) podłączany przez loop,
  `e2fsck`, `rsync -aAXH --numeric-ids --delete` całego `/` (bez /proc, /sys, /dev, /run, /tmp, /mnt, /media,
  swapu, cache), do tego `.kopia-info/` (tablica partycji, blkid, fstab, lista pakietów). Stan:
  `/var/lib/kopia-pi/stan.json`, `ostatnia-udana.json`, log na NAS `Logi/kopia-systemu.log` (gdy NAS padł:
  `/var/lib/kopia-pi/zalegly.log`, dopisywany później). Obok kopii: `JAK-PRZYWROCIC.txt` i `przywroc.sh /dev/sdX`
  (odtwarza partycje z tymi samymi PARTUUID/UUID, więc nowa karta startuje bez poprawek).
- **Panel „Kopie zapasowe i zadania w tle”** na stronie głównej portalu i na `/strony/zdrowie/` (wspólny
  `zdrowie/zadania.js`, dane `GET /api/zadania`, lista `ZADANIA` w `app.py`): kopia systemu (faza, procent, pliki,
  czas, szacowany koniec; `kopia-pi` zapisuje `/var/lib/kopia-pi/postep.json` co 5 s z `rsync --info=progress2`,
  procent = większy z bajtów i sprawdzonych plików), render filmów (procent, kolejka), bufor zdjęć, logi na NAS,
  połączenie z NAS, aktualizacja Minecrafta, aktualizacje systemu (ostatnio/następnie z `systemctl list-timers
  --output=json`). Panel jest wysuwany (domyślnie zwinięty: „!” przy błędzie lub braku NAS, znaczniki z procentem
  tego, co trwa, data ostatniej kopii). Strona Zdrowie odświeża panel co 5 s, gdy coś trwa. Pierwsza pełna kopia: 17 GB w 511 s, kolejne ~30 s.
- **Raport obciążenia** (wątek `obc_petla` w `app.py`, pomiar co 5 s): każdy przedział z CPU > 60 %, temperaturą
  > 55 °C, RAM > 60 % (progi: `config.json` → `"obciazenie"`). Start po 2 pomiarach ponad progiem (≥ 10 s), koniec po
  3 poniżej. Zapis: `dane/zdrowie/obciazenie.json` (ostatnie 3000) i logi `cpu.log`, `temperatura.log`, `ram.log`
  (START od razu, potem linia z czasem, max, średnią i 5 procesami, które najwięcej zjadały: CPU w % jednego rdzenia,
  RAM w MB; nazwa = program (usługa)), kopiowane od razu na NAS `Logi/`. API `GET /api/obciazenie`. Na stronie głównej
  i Zdrowie wysuwany panel `zdrowie/obciazenie.js` (domyślnie zwinięty, pamięta stan); zwinięty pokazuje tylko „!”,
  gdy przedział trwa teraz.
- **Bezpieczne wyłączenie**: komenda `raspiproszewylaczsie` (`/usr/local/bin`, repo `pi/nas/`): pyta o potwierdzenie
  (`-t` bez pytania), czeka na trwającą kopię (`--teraz` przerywa ją), Minecraft `save-all` + `stop` przez
  `~/powernukkitx/console.fifo`, zatrzymuje playit i portal, wpis w dzienniku zdrowia, ostatnie logi na NAS, odmontowanie
  NAS, `poweroff`.
- **Po zaniku prądu** wszystko startuje samo: usługi `enabled` (portal, Minecraft, playit, tailscale, dashboard, terminal,
  ollama, smbd, wayvnc), timery NAS/logów/kopii; NAS z fstab (`nofail`) + `nas-montuj` co 2 min; kopia z
  `Persistent=true` nadrabia pominiętą 02:00 zaraz po starcie, a przerwaną naprawia `e2fsck` przy następnym przebiegu.
- **`Raspberry/komendy.txt` na NAS**: lista komend projektu dla użytkownika (źródło `pi/nas/komendy.txt` →
  `/usr/local/lib/kopia-pi/komendy.txt`, `nas-montuj` kopiuje na NAS, gdy się różni). **Każdą nową komendę lub skrypt
  dla użytkownika dopisz tam** i zainstaluj plik na Pi.
- **Pliki w repo**: `pi/nas/` (skrypty, jednostki systemd, instrukcje, `instaluj.sh`; instalacja: skopiuj folder na Pi
  i `sudo bash instaluj.sh`).

## Zawodowe: program od nauczyciela z NAS (od 2026-10-22)
- Strona `/strony/zawodowe/` (menu portalu „🤖 Zawodowe”): ASTORINO Web Lab od nauczyciela (jeden plik HTML).
- Źródło: **`Tony-Folder/Raspberry/Zawodowe/`** na NAS. Nowa wersja = wrzucić plik `.html` (dowolna nazwa), usunąć stary,
  odświeżyć stronę; bez Claude i bez zmian w portalu. Portal (`zawodowe_odswiez` w `app.py`) bierze najnowszy `.html`
  i kopiuje go do `~/portal/sites/zawodowe/index.html` (podpis nazwa|rozmiar|czas w `zrodlo.txt`), więc strona działa
  też bez NAS. `site.json` i `CZYTAJ.txt` folderu: `pi/zawodowe/` w repo (sam program nie jest w repo).

## Dostęp z sieci domowej: hasło i ciasteczko (od 2026-10-22)
- Portal słucha na `0.0.0.0:80`. Adres z `100.64.0.0/10` (Tailscale; nftables Tailscale odrzuca takie adresy spoza
  `tailscale0`) albo `127.0.0.1` wchodzi bez hasła. Inne adresy (sieć domowa) muszą się zalogować (`before_request`
  `wymagaj_hasla`): strony → przekierowanie na `/logowanie?nast=…`, `/api/*` → 401.
- `/logowanie`: hasło sprawdzane ze skrótem w `~/portal/dane/dostep.json` (600: `hash` werkzeug/scrypt, `klucz`
  podpisu, `wersja`). Ciasteczko `portal_sesja` (itsdangerous, HttpOnly, SameSite=Lax, 365 dni) zawiera `wersja`.
  5 złych haseł z jednego adresu = 5 min blokady; każda próba w dzienniku zdrowia (`LOGOWANIE …`). `/wyloguj` usuwa
  ciasteczko; w menu portalu link „Wyloguj” pojawia się tylko z sieci domowej (`/api/dostep`).
- `portal-haslo` (`/usr/local/bin`, repo `pi/portal-haslo`) zmienia hasło i podbija `wersja` (wylogowuje wszystkie
  urządzenia). Hasła nie ma w repozytorium.
- Ciasteczko jest przypisane do adresu: `172.23.0.20` (eth0) i `172.23.0.24` (wlan0) to osobne logowania; używaj `.20`.
  `/terminal` z sieci domowej pokazuje tylko informację (terminal na porcie 7681 słucha wyłącznie na Tailscale).
  Panel Minecraft `pi-dashboard` (8090) był i jest dostępny w sieci domowej bez hasła (osobna usługa).

## Minecraft włączany ręcznie (od 2026-10-22)
- `powernukkitx` jest **disabled** (nie startuje z Pi). Komenda `/usr/local/bin/minecraft start|stop|status` (repo
  `pi/minecraft/minecraft`): start czeka na „Done (” (ok. 30 s), stop = `save-all` + `stop` przez `console.fifo`.
  `playit` i `pi-dashboard` działają dalej (mało zasobów). Serwer zajmował ok. 1,4 GB RAM i ~11% CPU bez graczy.
- Portal: `GET/POST /api/minecraft {akcja: start|stop}` (w tle, `MC_STAN.trwa`), karta „🎮 Minecraft” z przyciskiem
  na stronie głównej. Bot: przycisk 🎮 Minecraft (Włącz / Wyłącz / Restart), akcje `mc_wlacz`/`mc_wylacz` także dla Claude.
- **Auto-wyłączanie**: bot (`petla_minecrafta`, co 60 s) wyłącza serwer (`mc_wylacz`, zapis świata) po
  `ustawienia.mc_auto_min` (domyślnie 30, 0 = nigdy) minutach bez graczy, licząc od włączenia albo od ostatnich graczy
  (po restarcie bota od nowa); nieznana liczba graczy nie przybliża wyłączenia. Wiadomość w Telegramie.
- **Powiadomienia o stanie** (bot `petla_mc_stanu`, co 15 s z `/api/minecraft`): włączony, wyłączony, zrestartowany,
  wysypał się, „ktoś gra” (0 → n graczy) i „opustoszał” (n → 0); niezależnie od źródła zmiany. Gdy zmianę zrobił sam
  bot (`MC_BOT`, 2 min), nie dubluje wiadomości.
- Monitor: `uslugi_reczne` = wyłączony to OK (⏸ na stronie Zdrowie), 🔴 tylko gdy `failed`.
- `~/scripts/auto-update.sh` (kopia `.przed_recznym`): po aktualizacji PNX wyłącza serwer, jeśli był wyłączony.

## Bot Telegram @SerwerekAntek_bot (od 2026-10-22)
- Usługa `serwerek-bot` (User=tonyg), kod `~/bot/serwerek_bot.py` (repo `pi/bot/`), stan `~/bot/stan.json` (600:
  właściciel, kod parowania, wysłane powiadomienia, sesja Claude, ustawienia godzin). Tokeny tylko w
  `/etc/serwerek-bot/token.env` (TELEGRAM_TOKEN) i `claude.env` (CLAUDE_CODE_OAUTH_TOKEN z `claude setup-token`,
  ważny rok, subskrypcja właściciela), root 600, podawane przez `EnvironmentFile`. Nigdy w repo.
- Odpowiada tylko właścicielowi (pierwszy, kto wysłał `/start <kod>`). Przyciski: Stan, Sprawdziany, Kopia, Przejrzane,
  Restart (portal / Minecraft z `save-all`), Nowa rozmowa. Akcje zmieniające coś tylko po „Tak”.
- Powiadomienia (co 60 s z `/api/zdrowie` i `sprawdziany.json`): 🔴 od razu o każdej porze + „✅ Minęło”; 🟡 od razu
  poza ciszą 22–7 (z nocy jedną wiadomością rano); nauka: 18:00 dzień przed, 18:00 3 dni przed sprawdzianem, 7:00 w dniu.
- **Wejścia z sieci domowej** (wszystko spoza Tailscale i adresów samego Pi): każde zdarzenie → wizyta `WIZYTY[ip]`
  w bocie i od razu linia w logu na NAS `Logi/wejscia/RRRR-MM-DD.log` (gdy NAS padł: `~/bot/wejscia-bufor.log`,
  dopisywany później; pliki starsze niż 30 dni bot usuwa). Od razu na Telegram: 🚪 nowe wejście (z MAC i nazwą
  z DNS routera), 🔑 otwarcie panelu logowania (najwyżej co 1 min), 🔓 każde przejście zabezpieczeń (hasło portalu,
  SSH, Samba, VNC, panel MC), ⛔ nieudane próby, 🕵️ oznaki ataku (≥ 3 złe hasła, 5+ portów w minutę, ścieżki typu
  `wp-login`/`.env`). Pojedynczych przejść stron bot nie wysyła: zapisuje je od razu na Pi (`~/bot/wejscia/`, 30 dni)
  i na NAS; komenda/przycisk **🧭 Ścieżka** (`ścieżka`, `ścieżka wczoraj`, `ścieżka RRRR-MM-DD`) pokazuje wizyty z dnia
  (IP, MAC, od–do, kroki z godziną, powtórzenia ×N; wizyta kończy się po 10 min ciszy).
- **Bez powiadomień (tylko zapis w ścieżce):** wejścia przez Tailscale (portal loguje też zapytania z 100.x jako
  `tailscale: true`; w logu „Tailscale: <nazwa urządzenia>”) i **zaufane urządzenia** właściciela w sieci domowej
  (MAC w `stan.json` → `zaufane`). Przy powiadomieniu 🚪 przycisk „✅ To moje urządzenie”; lista i usuwanie: `zaufane`.
  Uwaga: iOS/macOS mogą zmieniać prywatny adres Wi-Fi (tryb „rotujący”) – wtedy urządzenie trzeba dodać ponownie.
- **📊 Stan** pokazuje też maksimum temperatury, CPU i RAM z dziś i z 7 dni (`/api/obciazenie` → `maks`; portal zapisuje
  dzienne maksima z pomiaru co 5 s w `~/portal/dane/zdrowie/maksima.json`, 60 dni).
  Źródła: portal dopisuje do `~/portal/dane/wejscia.jsonl` każde zapytanie (`zapytanie`: metoda, ścieżka, wynik,
  zalogowany), `panel_logowania`, `logowanie_ok`, `zle_haslo`, `blokada` (bot czyta co 1 s, plik > 5 MB zeruje);
  dziennik: `sshd`, Samba `smbd` (auth_audit: `log level = 1 auth_audit:3`, `logging = file syslog@3`) i `smbd_audit`
  (VFS `full_audit` w `[Pelny_System]` i `[homes]`: connect/disconnect/openat/unlinkat/renameat/mkdirat; kopia
  `smb.conf.przed_audytem_2026-10-22`), jądro: nftables `inet serwerek_log` (tylko log): `SERWEREK-WEJSCIE` (22, 139,
  445, 5900, 8090) i `SERWEREK-SKAN` (inne porty TCP). Udział `Pelny_System` = cały `/` z `force user = root`.
- **Zdjęcia i PDF-y** wysłane botowi (do 20 MB) zapisują się w `~/bot/pliki/<data>/` i idą do Claude z podpisem;
  album zdjęć = jedna wiadomość. Claude według `instrukcja.md` robi z nich nową stronę w Nauce (szablon fizyki/historii,
  wpis w `sprawdziany.json`, kontrola `node ~/bot/sprawdz_strone.js <id>`), zapisuje linię w
  `~/portal/sites/nauka/DODANE_PRZEZ_BOTA.txt`. Limit czasu jednego zadania: 30 min.
- Inny tekst → `claude -p` (Claude Code 2.1.308 w `~/.local/bin/claude`) z `--permission-mode dontAsk`, narzędzia
  z `~/bot/uprawnienia.json` (od 2026-10-22 **pełny Bash** jako tonyg, Edit/Write; zakaz czytania sekretów i edycji kodu
  bota/telefonu/portalu), instrukcja `~/bot/instrukcja.md`. Claude działa przez `setpriv --no-new-privs`, więc **sudo
  mu nie zadziała**; hook PreToolUse `~/bot/straznik.py` (przez `--settings`) blokuje z wyjaśnieniem: sudo/su,
  crontab/at/systemd-run, czytanie tokenów i `env`, wyłączanie Pi, operacje na dyskach, `rm -rf` katalogów systemu/domu/NAS,
  odcinanie Tailscale/SSH, restart bota, zmiany kodu bota/portalu. **sudo za zgodą**: Claude pisze `[[SUDO: polecenie]]`
  → bot zapisuje je w `~/bot/sudo_czeka.json` (id = sha256 polecenia, ważne 24 h, jednorazowe) → przycisk „Tak”
  w Telegramie albo „tak” w Linphone → `sudo bash -c polecenie`, wynik do czatu i do pamięci (Claude go widzi; „dalej”).
  Gotowe akcje: `[[AKCJA: kopia|restart_portalu|restart_minecrafta|przejrzane|mc_wlacz|mc_wylacz]]`.
  Strażnik to bariera przed pomyłkami, nie pełna izolacja (Claude ma prawa użytkownika tonyg).
  Nowa rozmowa po 250 tys. tokenów kontekstu (z ostatniej wiadomości w `~/.claude/projects/*/<sesja>.jsonl`)
  albo po 1 h ciszy. Zużycie liczy się do limitów subskrypcji właściciela; bot tylko dla niego (zasady Anthropic).
- Odnowienie logowania Claude (co rok): `claude setup-token` → token do `/etc/serwerek-bot/claude.env`, restart bota.

## Głos, telefon i wspólna pamięć (od 2026-10-22)
- **Pamięć** `~/bot/pamiec.db` (SQLite, `pi/bot/pamiec.py`, 90 dni): każda wiadomość (antek / bot sam z siebie /
  claude; kanał telegram / glosowka / telefon, z `tg_id`). Do Claude dopisywane: na nowej sesji ostatnie 30 wiadomości,
  zawsze to, co bot wysłał od ostatniej wiadomości Antka, i wiadomość, na którą Antek odpowiada (reply).
- **Mowa na Pi** (`~/glos/`, repo `pi/glos/`, instalacja `instaluj.sh` przez `systemd-run`): whisper.cpp
  (`ggml-base` telefon, `ggml-small-q5_1` głosówki, polski, 3 wątki), Piper `pl_PL-gosia-medium`; moduł `glos.py`
  (`rozpoznaj`, `powiedz`, `do_ogg`).
- **Głosówki w Telegramie**: rozpoznanie na Pi → „🎙 tekst” → Claude → odpowiedź tekstem i głosem (sendVoice).
- **Telefon** `serwerek-telefon` (`~/glos/telefon.py`, pjsua2 z pjproject 2.15.1 zbudowanego na Pi): konto SIP Pi na
  sip.linphone.org (konto Pi `antekserwerrpi4b`, właściciel `za_kolaz`; TCP, ICE, STUN stun.linphone.org), konfiguracja `/etc/serwerek-bot/sip.env` (`SIP_UZYTKOWNIK`,
  `SIP_HASLO`, `SIP_DOMENA`, `SIP_WLASCICIEL`). Przyjmuje połączenia tylko od właściciela (inne odrzuca i zgłasza).
  Dzwoni sam: zlecenia `~/bot/telefon/kolejka/*.json` (bot: 📞 Zadzwoń, 🔴 bez „👀 Widzę” przez 10 min, zadanie
  z `dzwon: true`), wyniki `~/bot/telefon/wyniki/*.json` → wiadomość w Telegramie (nieodebrane, zapis rozmowy).
  Rozmowa: nagrywanie (AudioMediaRecorder) → wykrycie końca wypowiedzi (energia, 0,9 s ciszy) → whisper → Claude
  (`claude_odpowiedz(kanal="telefon")`, ta sama sesja co czat) → Piper → odtworzenie. Pożegnanie albo 90 s ciszy = koniec.
  **Czat Linphone**: `onInstantMessage` (text/plain albo message/cpim; imdn/iscomposing pomijane), tylko od właściciela
  (`od_wlasciciela`: porównanie nazwy użytkownika SIP), obcy → wiadomość w Telegramie. Komendy jak w bocie (stan,
  sprawdziany, zadania, ścieżka, minecraft, „todo …”), reszta → `claude_odpowiedz(kanal="linphone")`; odpowiedź przez
  `Buddy.sendInstantMessage` (części po 1500 znaków, wskaźnik „pisze…”). Bot może pisać na Linphone: JSON w
  `~/bot/telefon/czat/`. Test lokalny: `test_czat.py` (także `PLIK:<url>` = głosówka).
  Komendy czatu: jak w bocie + `pomoc`/`help` (`POMOC_WSPOLNE` w bocie), `kopia`, `przejrzane`, `minecraft włącz|wyłącz`,
  `restart portalu`, `zadzwoń`, `nowa rozmowa`, `zaufane`; akcje (też proponowane przez Claude) potwierdza się
  odpisując „tak” w ciągu 2 min (`CZAT_AKCJA`), „nie” anuluje.
  Zadania w czacie: przypomnienia idą też na Linphone (`bot.do_linphone(..., todo_id=…)`; telefon.py zapamiętuje id
  w `OSTATNIE_ZADANIE`), odpowiedzi `zrobione [nr]`, `+15`, `+1h`, `+jutro [nr]`, `usuń <nr>`, `cofnij` (`zadanie_czat`,
  numery jak w liście `zadania` = `bot.zadania_do_zrobienia()`). Telegram: `pomoc`/`help`/`/pomoc` → pełna lista.
  **Głosówki w Linphone**: przychodzą jako `application/vnd.gsma.rcs-ft-http+xml` (adres pliku na
  files.linphone.org; Linphone wysyła `.mka` (Matroska), czasem pusty – wtedy grzeczny komunikat) → pobranie → whisper;
  odpowiedź głosem: Piper → WAV → `.mka` z Opusem 48 kHz (jak Linphone) → upload na
  `files.linphone.org/http-file-transfer-server/hft.php` (link ważny 7 dni) → wiadomość z XML
  (`voice-recording=yes`, `am:playing-length`).
- **Głos czy tekst** (`tryb_odpowiedzi` w bocie): prośba o tekst („wypisz / napisz / odpisz / tekstem / w punktach /
  nie mogę odsłuchać”) zawsze wygrywa; „przeczytaj / powiedz / nagraj / głosówką / na głos” → głosówka; bez prośby
  w Telegramie tak, jak przyszło pytanie. **W Linphone zawsze tekst**, głosówka dodatkowo tylko na wyraźną prośbę
  (odtwarzanie głosówek od Pi w Linphone niepotwierdzone; wzór głosówki z Linphone zapisuje się w
  `~/bot/telefon/ostatni_plik_z_linphone.txt` do dopasowania formatu). Bez echa „🎙 rozpoznany tekst”. Gdy głosem, Claude dostaje `GLOS_PODPOWIEDZ` (zdania do czytania, bez list i emotek); w Telegramie
  głosówka z tekstem w podpisie.
  **SRTP**: Linphone szyfruje dźwięk, więc konto ma `srtpUse = MANDATORY` (od 2026-10-22; przy OPTIONAL połączenia od Pi
  kończyły się 603 Decline i w iPhonie było „Anonymous”), `srtpSecureSignaling = 0`. Nadawca: `"Serwer Rpi" <sip:…>`;
  w dzienniku przy rozłączeniu jest kod i powód (np. `603 Decline`).
  **Dzwonienie do właściciela trwa do 60 s** (`CZAS_DZWONIENIA`): iPhone czasem od razu odsyła `603 Decline` (zwykle
  gdy Linphone jest otwarty, mimo „110 Push sent”), więc po 603/486/480/408 Pi dzwoni znowu po 5 s (`PONOW`), aż minie
  minuta; dopiero wtedy bot pisze „nie odebrałeś”.
  **Cisza w słuchawce (naprawione 2026-10-22)**: po ICE Linphone odnawia media (UPDATE), pjsua tworzy nowy port mostka;
  `onCallMediaState` podpina się teraz za każdym razem do aktualnego portu (nagrywanie i odtwarzanie).
  **Przypomnienia z telefonem**: ok. 4 min przed terminem bot (`przygotuj_rozmowe`, osobne `claude -p` z pamięcią
  rozmów, bez wspólnej sesji) układa, co Pi powie; przy dzwonieniu Piper syntezuje powitanie od razu (gotowe, zanim
  Antek odbierze), potem zwykła rozmowa z Claude. Brak przygotowanego tekstu → „Przypomnienie: …”. Dokładny log SIP: `sudo systemctl set-environment TELEFON_LOG=5`
  + restart usługi → `/tmp/telefon-sip.log` (wyłączenie: `unset-environment TELEFON_LOG`).
  Diagnostyka w razie problemów: drop-in `serwerek-telefon.service.d/diagnostyka.conf` z `Environment=TELEFON_LOG=5`
  → `/tmp/telefon-sip.log` (teraz wyłączona). Sprawdzone 2026-10-22: rozmowa z iPhone'a działa (opus, SRTP).
  Szybkość na Pi 4: rozpoznanie ok. 1 s na 1 s mowy (whisper base, okno `-ac` dopasowane do długości), Claude 5–10 s,
  Piper 2–3 s → odpowiedź ok. 15–25 s po skończeniu mówienia. Test bez Linphone: `SIP_DOMENA=lokalnie`
  (adres `sip:<użytkownik>@127.0.0.1:5070`, bez STUN) + `test_dzwoniacy.py`. Uwaga pjsua2 w Pythonie: wynik
  `getInfo()` trzymać w zmiennej (inaczej `.media` wskazuje na zwolnioną pamięć), obiekty pjsua2 zwalniać w głównym wątku.

## Zadania (todo) z przypomnieniami (od 2026-10-22)
- Dane `~/portal/dane/todo.json`: `{id, tekst, termin "RRRR-MM-DDTHH:MM"|null, powtarzaj null|dzien|tydzien|miesiac,
  zrobione, wyslano, utworzono}`. API: `GET/POST /api/todo`, `POST /api/todo/<id>` (`zrobione`, `tekst`, `termin`,
  `powtarzaj`, `odloz_min`, `wyslano`, `usun`). Zrobienie zadania powtarzanego przesuwa termin (`todo_nastepny`).
- Strona `/strony/todo/` (repo `todo/`, link „📝 Zadania” w menu): dodawanie (dzień, godzina, powtarzanie), edycja,
  zrobione/cofnij, usuwanie; sama godzina = dziś albo jutro, sam dzień = 9:00. Zrobione dawniej niż 24 h temu są
  w zwijanym „Archiwum” (liczone na stronie z pola `zrobione`, dane się nie zmieniają); przy zrobionych „do archiwum za
  X h Y min”. Karta „📚 Sprawdziany i kartkówki” (z `/strony/nauka/sprawdziany.json`, linki do stron nauki); bot dopisuje
  je (14 dni) do listy „zadania”, a przypomnienia o sprawdzianach idą też na Linphone.
- **Odhaczanie głosem**: w rozmowie z przypomnienia (`todo_id` w zleceniu telefonu) „odhaczone / odhacz / zrobione /
  gotowe / załatwione…” (bez „nie …”) oznacza zadanie jako zrobione i Pi mówi „Odhaczone.”.
- **Bardzo ważne = Pi dzwoni** (pole `dzwon`): przycisk „📞 Bardzo ważne: zadzwoń” w formularzu i 📞 przy zadaniu na
  stronie (wymaga terminu), przycisk pod „Dodane” w Telegramie (`todo_dzwon:<id>`), w tekście „ważne”, „bardzo ważne”,
  „pilne”, „zadzwoń” (`nowe_zadanie`), w Linphone „ważne [nr]”.
- Bot: przycisk 📝 Zadania (lista + ✅ 1…20), dodawanie „todo …”/„przypomnij …” (`parsuj_zadanie`: dziś/jutro/pojutrze,
  dni tygodnia, DD.MM[.RRRR], RRRR-MM-DD, „o 17”, „17:30”, „za 20 min / 2 godziny / 3 dni”, codziennie / co tydzień /
  co miesiąc). Przypomnienia co 30 s, o każdej porze (godzinę wybiera właściciel), przyciski ✅ / +15 min / +1 h / jutro.
  Claude w bocie też dodaje zadania przez API (`instrukcja.md`).

## Zdrowie serwera (od 2026-10-22)
- **Dioda** na każdej stronie HTML portalu i `/strony/*`: `app.py` dokleja `<script src="/strony/zdrowie/dioda.js">`
  przed `</body>` (`wstaw_diode` w `after_request`). Zielona = OK, żółta = do sprawdzenia albo zakończony problem
  czekający na „Przejrzane”, czerwona = aktywny problem krytyczny. Liczba = aktywne + do przejrzenia.
- **Strona**: `/strony/zdrowie/` (repo `zdrowie/`): teraz, do przejrzenia, pomiary, historia, dziennik.
- **Monitor** (wątek w `app.py`, co 60 s, `zdrowie_problemy` + `zdrowie_krok`): temperatura (70/80 °C), napięcie
  i throttling (`vcgencmd get_throttled`; „wystąpiło od uruchomienia” zapisywane raz na boot), dysk `/` i
  `/boot/firmware` (80/90 %), RAM (85/95 %), swap (80/95 %), CPU średnio ≥ 85 % przez 10 min (żółta) / ≥ 95 % przez
  30 min (czerwona), usługi krytyczne (`powernukkitx`, `playit`, `tailscaled`, `home-portal`) i zwykłe (`pi-dashboard`,
  `home-terminal`, `smbd`, `nmbd`, `wayvnc`, `ollama`), zadania (`mc-autoupdate`: wynik ostatniego przebiegu),
  `systemctl --failed`, potrzeba restartu. Problem startuje po 2 kolejnych wykryciach, kończy się po 2 kolejnych brakach.
- **Dane**: `~/portal/dane/zdrowie/incydenty.json` (problemy z `od`, `do`, `poziom` = najgorszy, `teraz`, `przejrzane`),
  `dziennik.log` (każda zmiana), `boot.json`. API: `GET /api/zdrowie[?historia=1]`, `POST /api/zdrowie/przejrzane
  {id | wszystkie:true}`, `GET /api/zdrowie/dziennik`.
- **Progi i listy usług** można zmienić w `~/portal/config.json` → `"zdrowie": {"temp": [70, 80], "uslugi": [...]}`
  (restart portalu niepotrzebny; czytane przy każdym pomiarze). Nowa usługa (np. kopia zapasowa) = dopisać do
  `uslugi`/`uslugi_kryt` albo `zadania` (dla usług uruchamianych timerem). NAS i kopia systemu: sekcja NAS wyżej.

## Dziennik
- **2026-10-22**: Monitor zdrowia, dioda na wszystkich stronach, strona „Zdrowie serwera”, link w menu portalu.
  Backup `app.py.bak_2026-10-22_zdrowie`. Pierwszy pomiar: wszystko OK (46,7 °C, throttled 0x0, 10 usług aktywnych).
