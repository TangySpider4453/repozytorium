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
- Hasła Apple / pęk kluczy: formularz `/logowanie` ma widoczne pole „Użytkownik” (`serwerek`, `autocomplete=username`)
  i hasło `current-password`, więc iPhone proponuje zapisanie i sam wpisuje hasło (zapis pod adresem, z którego wchodzisz,
  np. `raspberrypi.local`). Pulpit VNC na /zdalne ma pole `tonyg` + hasło, też do autouzupełniania.
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

## Budziki, Mobidziennik i poczta (od 2026-10-22)
- **Budziki**: `/api/alarmy` (portal, `dane/alarmy.json`: godzina + data albo dni tygodnia 0=pon). Bot
  (`petla_budzikow`, co 15 s): ok. 3 min wcześniej `przygotuj_budzik` zbiera `poranne_dane()` (serwer, poczta, lekcje
  z Mobidziennika, sprawdziany, zadania) i Claude układa wypowiedź; o czasie `zadzwon(..., budzik=id, proba=1)`;
  nieodebrany (po minucie dzwonienia z ponowieniami 603) → jeszcze 2 próby co 5 min (`BUDZIK_PONOW`). Komendy
  (`komenda_budzik`, Telegram, Linphone, rozmowa): „budzik jutro 6:15”, „obudź mnie o 7”, „budzik w dni robocze 6:30”,
  „budziki”, „usuń budzik 2”. Po odebraniu Pi czeka 2,5 s (`CZEKAJ_PO_ODEBRANIU`).
- **Mobidziennik** (`pi/bot/mobi.py`, tylko odczyt, jedyny POST = logowanie): co 10 min w 6–22 logowanie i GET
  `planlekcji?typ=podstawowy&tydzien=<pon>` (ten i następny tydzień; klasy `bx pz` lekcja, `lz` zastępstwo, `lo`
  odwołana), `zastepstwa`, `sprawdziany`, `zadaniadomowe`. Stan `~/bot/mobi/stan.json`; zmiany → `powiadom()`
  (zmiana planu, przesunięty termin, nowe zadanie domowe); nowy sprawdzian, którego nie ma w Nauce → Claude
  (`mobi_nowy_sprawdzian`, do 30 min) robi stronę i 2–3 sesje nauki w todo albo prosi o materiały. Dane logowania:
  `/etc/serwerek-bot/mobi.env` (MOBI_ADRES/LOGIN/HASLO, root 600; usuwane ze środowiska Claude, strażnik blokuje).
  Komenda „plan [jutro|w poniedziałek]”. API portalu `/api/mobi` (bez haseł), karta na „Automatyczne” i strona
  `/strony/mobi/` (repo `mobi/`: cały plan tego i następnego tygodnia z zastępstwami/odwołaniami, sprawdziany z
  tematyką, zadania domowe; „↻ Sprawdź teraz” = `POST /api/mobi/odswiez` → znacznik `~/bot/mobi/odswiez` dla bota).
  Zadania domowe są też w planie (przy lekcji, na którą są zadane); pełną treść bot czyta raz ze strony szczegółów
  (GET `wyslijzadanie/?id_zadania=…`, tylko podgląd: przycisku „oznacz jako zrobione” ani formularza nie używa).
- Strona `/strony/budziki/` (repo `budziki/`): lista, włącz/wyłącz, usuń, dodawanie (jednorazowy z datą albo dni tygodnia).
- **Poczta** (`pi/bot/poczta.py`): konta w `/etc/serwerek-bot/poczta.env` (`POCZTA_n=nazwa|imap.serwer|login|hasło do
  aplikacji`; Gmail: imap.gmail.com, iCloud: imap.mail.me.com). Co 10 min UNSEEN z 3 dni (BODY.PEEK) → Claude BEZ
  narzędzi (`claude_bez_narzedzi`: `--tools ""`, bez pamięci, maile jako dane) daje kategorię: spam → \Seen,
  ważne → `powiadom()` i czekanie („przeczytaj mail”, „przeczytany”, „później” = za 3 h; bez reakcji przypomnienie
  po 30 min; w nocy czeka), inne → poranny przegląd. Nigdy nie wysyła (bez SMTP). `/api/poczta`, komenda „maile”.

## Treningi intervals.icu i kreatyna (od 2026-10-26)
- `pi/bot/intervals.py`, tylko odczyt (GET `/api/v1/athlete/0/events?category=WORKOUT` i `/activities`, Basic
  `API_KEY:<klucz>`), co 5 min (`petla_intervals`). Klucz `INTERVALS_API_KEY` w `/etc/serwerek-bot/intervals.env`
  (root 600, `EnvironmentFile=-` w `serwerek-bot.service`); odcięty od Claude (`INTERVALS_` w env i strażniku).
- Stan `~/bot/intervals/stan.json` (treningi 7 dni, ostatnie aktywności, `kreatyna` = data → id biegu), włącznik
  `~/bot/intervals/ustawienia.json` (`kreatyna`, zapisuje portal). API portalu `GET/POST /api/intervals` (`?data=`).
- **Kreatyna**: bieg (Run/TrailRun/VirtualRun/Treadmill) zaczęty przed 12:00 dziś → zadanie „💊 Weź kreatynę (po
  porannym biegu)” z `dzwon: true` na koniec biegu + 10 min (raz dziennie). Bieg wykryty później niż godzinę po tym
  terminie = bez przypomnienia. Wyłącznik na stronie Automatyczne (karta 🏃) albo „kreatyna wyłącz / włącz”.
- Komendy (Telegram, Linphone, w rozmowie bez AI): „trening”, „jaki mam trening jutro / we wtorek”, „co mam dziś do
  biegania”. W rozmowie same nazwy, na czacie ze szczegółami. Budzik: sama nazwa treningu na dziś (`poranne_dane`).
  telefon.py nie ma klucza: komendy czytają stan zapisany przez bota.

## Claude w bocie: dwa stałe procesy, Haiku i Sonnet (od 2026-10-23)
- `pi/bot/klaud.py`: Claude Code w trybie `--input-format/--output-format stream-json` startuje raz i dostaje kolejne
  wiadomości (bez ok. 6 s startu przy każdej). Procesy: „szybki” = `claude-haiku-5-5 --effort low`, „madry” =
  `claude-sonnet-5-5 --effort medium`; osobne dla bota i usługi telefonu (`USLUGA`), rozgrzewane przy starcie
  (`rozgrzej`), razem ok. 0,9 GB RAM. Pomiar 2026-10-23: proste pytanie 0,9–2,3 s (Haiku), awaria/naprawa 6–8 s (Sonnet z
  narzędziami); wcześniej 7–9 s na każde.
- Wybór (`wybierz_model`): Sonnet dla plików, tekstów > 220 znaków i słów typu napraw / nie działa / awaria / NAS /
  dysk / kod / strona / nauka / dlaczego (`TRUDNE_RE`), reszta Haiku; Haiku sam oddaje trudne `[[TRUDNE]]` (wtedy to samo
  idzie do Sonneta). Wspólna pamięć: przed wiadomością model dostaje `pamiec.od_id()` (co od jego ostatniej odpowiedzi
  napisał drugi model, bot albo inny kanał). Nowa rozmowa po 1 h ciszy albo 250 tys. tokenów; sesje w `stan.json → sesje`.
- Instrukcja = `instrukcja.md` + `wiedza_serwer.md` (diagnoza i naprawy: NAS, usługi, zasoby, sieć, typowe naprawy
  ze znacznikami SUDO/AKCJA, przekręcona mowa). W rozmowie telefonicznej akcje potwierdza się głosem („tak” / „nie”).
- Rozpoznawanie mowy przy telefonie: whisper base zachłannie (`-bs 1 -bo 1 -nf`, ok. 30% szybciej), głosówki: small.
  `claude_jednorazowo` (budzik, przypomnienia, nowe sprawdziany) zostaje jako osobne wywołanie.

## Zdalne: terminal i pulpit VNC w przeglądarce (od 2026-10-23)
- Strona `/zdalne` (menu „🖥️ Zdalne”, zamiast „Terminal”; `/terminal` przekierowuje), tylko przez Tailscale, zakładki
  „💻 Terminal” (jak dotąd: `home-terminal`, port 7681, logowanie hasłem Linuksa) i „🖥️ Pulpit (VNC)”.
- VNC: noVNC 1.5.0 hostowany na Pi (`~/portal/sites/zdalne/novnc/`, core + vendor z GitHuba) → websockify
  (`serwerek-vnc-ws.service`, repo `pi/zdalne/`, `100.108.241.58:6080`, `--token-plugin TokenFile`) → wayvnc
  Raspberry Pi Connect (gniazdo `/run/user/1000/rpi-connect-wayvnc.sock`, bez hasła, tylko dla tonyg). Hasło: portal
  `POST /api/zdalne/vnc {haslo}` sprawdza hasło Linuksa przez PAM (`python3-pam`, usługa `login`), 5 złych prób =
  5 min blokady, po sukcesie bilet w `dane/vnc_tokeny/` (ważny 60 s). Bez biletu websockify nie łączy.
  Główny wayvnc (port 5900, PAM + TLS/RSA-AES) zostaje dla zwykłych klientów VNC; noVNC go nie obsługuje (VeNCrypt TLS,
  RSA-AES 5/129).

## Szybkie odpowiedzi bez AI (od 2026-10-23)
- `pi/bot/szybkie.py`: typowe pytania rozpoznane wzorcami (po `norm()`: bez polskich znaków i wypełniaczy; określenie
  dnia „jutro / w piątek…” wycinane przed dopasowaniem i odczytywane przez odpowiedź) → odpowiedź z danych na Pi
  w < 0,1 s (autobusy ok. 0,5 s): pierwsza/ostatnia lekcja, ile lekcji / czy jest szkoła, plan dnia, teraz/następna
  lekcja, sala, kiedy przedmiot, zastępstwa, sprawdziany (z „za ile dni”), zadania domowe, todo, budzik, godzina, data,
  serwer, Minecraft, poczta, autobus, do domu; od 2026-10-23 też prosto z systemu: temperatura (/sys), procesor
  (/proc/stat), RAM, miejsce (karta i NAS), uptime, zasilanie (vcgencmd get_throttled), NAS, kopia, usługi (systemctl
  is-active / --failed), co obciąża (top), internet i IP, lokalizacja. `_luzno`: krótkie pytania z przekręconej mowy
  po słowach kluczowych (temperatura, RAM, miejsce, obciążenie, NAS), bez słów typu napraw/dlaczego/wyłącz. Hak na początku `claude_odpowiedz` (wszystkie kanały: Telegram, Linphone, głosówki, telefon).
- Uczenie: Claude dopisuje `[[INTENCJA: nazwa]]`, gdy pytanie było jedną z intencji; bot zapisuje sformułowanie
  w `~/bot/szybkie_nauczone.json` i następnym razem (podobieństwo słów i trigramów ≥ 0,82) odpowiada sam.
  Statystyka trafień: `~/bot/szybkie_statystyka.json`. Test: `python3 pi/bot/test_szybkie.py` (308 zdań, w tym 30,
  które mają iść do Claude).

## Kanał: Linphone główny, Telegram zapasowy (od 2026-10-22)
- Odpowiedź zawsze tam, skąd przyszło pytanie. Powiadomienia bota (`powiadom()`: alarmy, przypomnienia, sprawdziany,
  wyniki połączeń, Minecraft, wejścia z sieci) idą kanałem, którym Antek ostatnio pisał (`stan.json` → `kanal`,
  domyślnie Linphone); gdy Linphone nie działa (`~/bot/telefon/stan.json` od telefon.py: rejestracja, odświeżane co
  minutę, ważne 3 min), do Telegrama. Lokalizacja, zdjęcia i przyciski Telegrama kanału nie zmieniają.
- W Linphone zamiast przycisków: „widzę” (nie dzwoń w sprawie 🔴), „przejrzane”, „to moje” (urządzenie z ostatniego
  powiadomienia o wejściu), „zrobione / +15…” przy przypomnieniach.

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

## Automatyczne (od 2026-10-22)
- Strona `/strony/automatyczne/` (repo `automatyczne/`, w menu „⚙️ Automatyczne” zamiast „📝 Zadania”): karty automatyzacji
  ze stanem na żywo: 📝 Zadania (link do `/strony/todo/`, która ma powrót „← Automatyczne”), 📚 Sprawdziany i kartkówki,
  📧 Poczta i 🚌 Komunikacja miejska („wkrótce”). Nowa automatyzacja = wpis w tablicy `AUTOMATY` w `index.html`.

## Komunikacja miejska ZTM Poznań i lokalizacja (od 2026-10-22)
- Moduł portalu `~/portal/ztm.py` (repo `pi/ztm.py`): rozkład GTFS z ztm.poznan.pl pobierany przy starcie i codziennie
  o 3:40 (wątek `ztm`, ok. 30 s) do `~/portal/dane/ztm/rozklad.{npz,json}`; opóźnienia GTFS-RT (`trip_updates.pb`,
  własny mini-dekoder protobuf, pamięć 20 s; na pętli „przed czasem” ignorowane). Trasa: Connection Scan Algorithm,
  dojście do 1 km, przesiadki pieszo do 400 m, okno 3 h, 2 warianty (ok. 1–2 s na Pi). Adresy: OSM Nominatim (pamięć
  `dane/ztm/adresy.json`).
- API: `GET /api/ztm/odjazdy?skad=<tu|miejsce|przystanek|adres>&ile=10`, `GET /api/ztm/trasa?skad=…&dokad=…`
  (pole `tekst` gotowe do wysłania), `GET/POST /api/lokalizacja` (`{lat, lon, acc, zrodlo}` albo format OwnTracks,
  odpowiedź `[]`), `POST /api/miejsca` (`{nazwa, tu:true | adres | lat, lon | usun}`). Lokalizacja: tylko ostatnia,
  `dane/lokalizacja.json`; miejsca `dane/miejsca.json` (prywatne, nie w repo).
- Bot: przycisk „📍 Odjazdy obok mnie” (Telegram wysyła lokalizację), lokalizacja „na żywo” (edycje zapisywane po cichu),
  „🏠 Do domu”, komendy `odjazdy [przystanek]`, `do domu`, `trasa [z X] do Y`, `zapisz <nazwa> [adres]`, `miejsca`
  (`komenda_ztm`, też w czacie Linphone); Claude używa API (`instrukcja.md`), także przez telefon.
- Miejsca słowami (`komenda_miejsca`, czat, Linphone i rozmowa telefoniczna bez pytania Claude): „ustaw tu, gdzie teraz
  jestem, jako dom”, „zapisz to miejsce jako szkoła”, „ustaw tutaj szkołę”, „zapisz dom ul. … 5”, „usuń miejsce X”.
  Samo „zapisz X” tylko dla typowych nazw (`ZWYKLE_MIEJSCA`), inaczej odpowiada Claude.
- Strona `/strony/komunikacja/` (repo `komunikacja/`) i karta na „⚙️ Automatyczne”.
- OwnTracks (iPhone, stała lokalizacja): tryb HTTP, URL `http://100.108.241.58/api/lokalizacja` (przez Tailscale).
- **Google Maps (od 2026-10-22, główne źródło)**: Antek udostępnia lokalizację drugiemu kontu Google; timer
  `google-lokalizacja.timer` co 15 min uruchamia `~/lokalizacja/google_lokalizacja.py` (venv `~/lokalizacja/venv`,
  nieoficjalne locationsharinglib, repo `pi/lokalizacja/`), który czyta ją ciasteczkami tego konta
  (`~/portal/dane/google_cookies.txt`, 600) i wysyła do `/api/lokalizacja` z czasem z Google. Nowe ciasteczka: plik .txt
  do `Tony-Folder/Raspberry/Google/` na NAS (instrukcja `CZYTAJ.txt` tam), skrypt go zabiera i kasuje. Stan/błąd:
  `dane/lokalizacja_google.json`, dopisywany do żółtego alarmu „Brak aktualnej lokalizacji”.
- Monitor zdrowia (tylko gdy są ciasteczka Google, czyli działa automatyczne źródło): w dzień (7–22) lokalizacja starsza niż 30 min (`LOKALIZACJA_MAX_MIN`) = 🟡 „Brak aktualnej
  lokalizacji”, chyba że trwa lokalizacja „na żywo” z Telegrama (`na_zywo_do` = wysłanie + live_period).
  iPhone nie pozwala serwerowi samemu pobrać lokalizacji: musi ją wysyłać aplikacja (OwnTracks albo Telegram).

## Zadania (todo) z przypomnieniami (od 2026-10-22)
- Dane `~/portal/dane/todo.json`: `{id, tekst, termin "RRRR-MM-DDTHH:MM"|null, powtarzaj null|dzien|tydzien|miesiac,
  zrobione, wyslano, utworzono}`. API: `GET/POST /api/todo`, `POST /api/todo/<id>` (`zrobione`, `tekst`, `termin`,
  `powtarzaj`, `odloz_min`, `wyslano`, `usun`). Zrobienie zadania powtarzanego przesuwa termin (`todo_nastepny`).
- Strona `/strony/todo/` (repo `todo/`, link „📝 Zadania” w menu): dodawanie (dzień, godzina, powtarzanie), edycja,
  zrobione/cofnij, usuwanie; sama godzina = dziś albo jutro, sam dzień = 9:00. Zrobione dawniej niż 24 h temu są
  w zwijanym „Archiwum” (liczone na stronie z pola `zrobione`, dane się nie zmieniają); przy zrobionych „do archiwum za
  X h Y min”. Karta „📚 Sprawdziany i kartkówki” (z `/strony/nauka/sprawdziany.json`, linki do stron nauki); bot dopisuje
  je (14 dni) do listy „zadania”, a przypomnienia o sprawdzianach idą też na Linphone.
- **Szczegóły na czat zamiast czytania**: przy mowie (telefon, głosówki, budzik, przypomnienia) Claude mówi krótko, a adresy,
  maile, numery, kody, ścieżki i kroki daje w `[[CZAT: …]]` → `szczegoly_na_czat` wysyła je „📋 Szczegóły” na czat
  (także gdy w mówionej odpowiedzi jest adres/mail/numer bez znacznika). `glos.do_mowy` i tak nie czyta adresów, domen,
  maili, numerów, kodów (litery+cyfry ≥ 8 znaków) ani ścieżek („… na czacie”). Na prośbę („powiedz szczegóły”) czyta całość.
- **Numer telefonu w zadaniu** (`numer_z`, 9 cyfr, opcjonalnie +48): zadanie z numerem zawsze dzwoni; „zadzwoń do X
  <numer>” zostaje w treści (nie jest brane jako „Pi ma dzwonić”). O czasie: osobna wiadomość „📞 Zadzwoń: +48 …”
  (Linphone/Telegram, dotknięcie = połączenie), a Pi w rozmowie mówi „zadzwoń na numer, który wysłałem na czacie”.
- **Wiadomość w chwili mówienia** (od 2026-10-23): przy przypomnieniu z numerem/szczegółami Pi mówi „wysyłam Ci teraz
  wiadomość z numerem/szczegółami” i dokładnie wtedy wysyła ją na czat (`zlecenie["czat"]` → `mow(tekst, czat=…)` w
  telefon.py, wysyłka po starcie odtwarzania). Tak samo `[[CZAT: …]]` w odpowiedziach Claude w rozmowie. Nieodebrane →
  szczegóły dochodzą w wiadomości „Dzwoniłem, ale nie odebrałeś”.
- **Domyślnie telefon**: „przypomnij mi za X / o 17 …” z terminem = Pi dzwoni. Tylko wiadomość, gdy Antek podkreśli:
  „napisz”, „wiadomością”, „bez dzwonienia”, „nie dzwoń” (`nowe_zadanie`: `dzwon = bool(termin) and not tylko_napisz`).
- **Restart bota/telefonu tylko poza rozmową**: `bash ~/bot/bez_rozmowy.sh` czeka, aż `~/glos/stan.json` ma
  `"rozmowa": false`, i dopiero wtedy restartuje serwerek-bot i serwerek-telefon. Każde wdrożenie przez ten skrypt.
- **„Dzwoń” = telefon od razu**: „dzwoń”, „zadzwoń (do mnie)”, „dzwoń asap / szybko / teraz”, „możesz zadzwonić?” w Linphone
  i Telegramie idą bez Claude (`chce_telefon`, `DZWON_TERAZ_RE`) prosto do kolejki telefonu (połączenie w ~1 s). Z czasem
  albo z adresatem („zadzwoń za 10 min”, „zadzwoń do mamy”) dalej przypomnienie/zadanie.
- **Zatrzymanie telefonu = rozłączenie**: przy SIGTERM telefon.py rozłącza trwające rozmowy (BYE) i dopiero kończy.
  2026-10-23 restart w trakcie rozmowy zostawił w Linphone na iPhonie „wiszące” połączenie: potem w każdej rozmowie
  iPhone dostawał dźwięk Pi, ale go nie grał i nie wysyłał mikrofonu (Pi: RX 0 pakietów). Naprawa: zamknąć Linphone.
- **Diagnostyka SIP**: `echo 5 > ~/bot/telefon/diag_sip` + restart telefonu = pełny zapis do `/tmp/telefon-sip.log`
  (usunięcie pliku wyłącza). Telefon loguje też `media …`, `mówię …`, `graj: …`.
- **Odhaczanie głosem**: w rozmowie z przypomnienia (`todo_id` w zleceniu telefonu) „odhaczone / odhacz / zrobione /
  gotowe / załatwione…” (bez „nie …”) oznacza zadanie jako zrobione i Pi mówi „Odhaczone.”.
- **Bardzo ważne = Pi dzwoni** (pole `dzwon`): przycisk „📞 Bardzo ważne: zadzwoń” w formularzu i 📞 przy zadaniu na
  stronie (wymaga terminu), przycisk pod „Dodane” w Telegramie (`todo_dzwon:<id>`), w tekście „ważne”, „bardzo ważne”,
  „pilne”, „zadzwoń” (`nowe_zadanie`), w Linphone „ważne [nr]”.
- Bot: przycisk 📝 Zadania (lista + ✅ 1…20), dodawanie „todo …”/„przypomnij …” (`parsuj_zadanie`: dziś/jutro/pojutrze,
  dni tygodnia, DD.MM[.RRRR], RRRR-MM-DD, „o 17”, „17:30”, „za 20 min / 2 godziny / 3 dni”, codziennie / co tydzień /
  co miesiąc). Przypomnienia co 30 s, o każdej porze (godzinę wybiera właściciel), przyciski ✅ / +15 min / +1 h / jutro.
  Claude w bocie też dodaje zadania przez API (`instrukcja.md`).

## Powiadomienia o wejściach: adres do rozpoznania (od 2026-10-26)
- „🚪 Nowe wejście” pokazuje IPv4 z sieci domowej także dla wejść z IPv6 (`fe80::…` → MAC → `ip -4 neigh`,
  `ipv4_z_mac`), a w nawiasie nazwę Tailscale tego urządzenia i jego adres 100.x (z `tailscale status --json`:
  CurAddr/Addrs w sieci domowej, zapamiętywane w `TS_NAZWY["lan"]`), nazwę z DNS routera, MAC i oryginalny IPv6.

## Ustawienia automatyzacji na stronach (od 2026-10-26)
- Panel „⚙️ Ustawienia” na dole stron Mobidziennik, Zadania (zadania + sprawdziany), Budziki, Komunikacja i zbiorczo na
  Automatycznych (wszystkie moduły, też poczta i treningi). Wspólny skrypt `wspolne/ustawienia.js` (→ `sites/wspolne/`),
  kontener `<div data-ustawienia="mobi,…">`. Zapis od razu: `POST /api/automaty/<moduł>`; schemat (`AUTOMATY_SCHEMAT` w
  `app.py`, typy bool/godzina/liczba/wybor) i wartości `GET /api/automaty`; plik `~/portal/dane/automaty.json`.
- Bot: `ust(moduł)` (cache 30 s). mobi: włącznik, godziny od–do, co ile minut, wiadomość przy zmianie, **telefon rano /
  wieczorem ze zmianami** (`mobi_zmiana` zbiera zmiany w `~/bot/mobi/do_rozmowy.json`, `mobi_telefon` dzwoni o godzinie
  do 30 min później, raz dziennie na porę, tylko gdy są zmiany; tekst układa Claude). sprawdziany: włącznik, 3 dni przed,
  godziny. zadania: przypomnienia, domyślne dzwonienie. budziki: włącznik, poranny przegląd, liczba prób, co ile min.
  poczta: włącznik, co ile min, ważne. treningi: włącznik, kreatyna, minuty po biegu, „poranny do”, nazwa w budziku.
  komunikacja: odpowiedzi ZTM, liczba odjazdów (też domyślne `ile` w `/api/ztm/odjazdy`).

## Oceny z Mobidziennika (od 2026-10-26)
- `mobi.oceny()` czyta stronę `oceny` (bieżący okres): przedmiot, oceny (`Wartość oceny`, „Liczona do średniej”, kategoria,
  opis, data, nauczyciel). Średnia **zwykła** (bez wag) z ocen liczonych i > 0 („+”, „np” = 0, nie liczone); ogólna =
  średnia ze średnich przedmiotów. Nowa ocena → „🎓 Nowa ocena: … , średnia …” (pierwszy odczyt bez powiadomień).
- `/api/mobi` (`oceny`, `srednia`), karta „🎓 Oceny i średnie” na `/strony/mobi/`, komendy „oceny”, „średnia”, „oceny z
  fizyki” (`komenda_oceny`, `znajdz_przedmiot` z aliasami matma/wf/polak…), w rozmowie bez AI.

## Kalendarz (od 2026-10-26)
- `/strony/kalendarz/` (repo `kalendarz/`): miesiąc (na telefonie kropki kategorii) + lista wybranego dnia i 6 następnych.
  Osobne kalendarze przez `#nauka`, `#lekcje`, `#treningi`, `#zadania`, `#budziki`, razem `#wszystko`; karta 🗓️ na
  Automatycznych z linkami. API `GET /api/kalendarz?od&do&kat` (`kal_zdarzenia` w `app.py`): plan lekcji z Mobidziennika,
  sprawdziany (Nauka + Mobidziennik bez duplikatów), zadania domowe, sesje nauki (zadania z przedmiotem albo „powtórz/
  fiszki/quiz…”), treningi plan i wykonane (intervals czyta teraz ±35 dni, `kalendarz_aktywnosci`), zadania (z
  powtarzaniem), budziki. Tylko podgląd.

- **Planowanie nauki z kalendarzem**: `GET /api/kalendarz/wolne?data&minuty[&bez=id]` (`kal_zajete`, `kal_wolne`): zajęte =
  lekcje z dojazdem 40 min (`KAL_DOJAZD`), treningi (plan bez godziny = zwykła pora tego typu z historii, mediana; gdy
  wypada w szkole albo na innym treningu: najbliższa wolna pora przed/po; `kal_godzina_treningu`), zadania z godziną;
  nauka 8:00–21:30 (`KAL_DZIEN`), odstęp 10 min. Zaplanowany trening już wykonany (ten sam typ i dzień) nie jest
  pokazywany. Bot `pilnuj_nauki` (co 5 min): sesja nauki nachodząca na coś → najbliższe wolne okienko tego dnia albo
  wcześniejszego (do dziś), wiadomość „📚 Przesunąłem…”; bez okienka: wiadomość z prośbą. Ręczna zmiana godziny po
  przesunięciu nie jest ruszana (`stan["nauka_przes"]`). Claude układa nowe sesje z `/api/kalendarz/wolne`.

- **Przypomnienia z kalendarza** (od 2026-10-28, `przypomnij_kalendarz`, co 30 s): X min (ustawienie „kalendarz”, domyślnie 10)
  przed lekcją, nauką i (opcjonalnie) zadaniem z godziną wiadomość „📅/📚/📝 Za 10 min (HH:MM): …” (Linphone, zapas Telegram).
  Druga z rzędu lekcja tego samego przedmiotu bez przypomnienia; odwołane i treningi (godzina przybliżona) pomijane;
  wysłane w `stan["kal_wyslane"]`. Ustawienia na dole strony Kalendarz i na Automatycznych.

## Oceny: okresy i symulacja (od 2026-10-26)
- `mobi.py` czyta `oceny/?semestr=1` i `=2`: `oceny_okresy`, `okres` (II, gdy ma oceny), `oceny_rok` (oba razem),
  `srednia` (ze średnich przedmiotów), `srednia_ocen` (ze wszystkich ocen). Strona Mobidziennik: zakładki I / II / cały rok,
  symulacja „co jeśli” (dotknięcie oceny = zmiana/usunięcie na próbę, „＋ ocena” = dodanie), tylko w przeglądarce.

## Lista zakupów łazika (inna sesja, przywrócona 2026-10-26)
- `/strony/lazik/zakupy.html` (repo `lazik/`), dane `~/portal/data/zakupy.json`, API `/api/zakupy`, `/api/zakupy/<id>`,
  `/api/zakupy/dodaj` w `app.py`; `site.json` „podstrony” → przyciski na stronie startowej. Inna sesja wgrała 26.10 rano
  starszą wersję `app.py` z tym API; moje wdrożenie o 10:28 je usunęło, scalone 21:20. **Przed wgraniem app.py porównaj
  z wersją na Pi** (`diff ~/portal/app.py`), bo zmienia go więcej niż jedna sesja.

## Głośnik AirPlay 2 (od 2026-10-28)
- shairport-sync 4.3.7 zbudowany ze źródeł z AirPlay 2 (`~/airplay/buduj_airplay.sh`, repo `pi/airplay/`; Debian ma tylko
  AirPlay 1) + `nqptp` 1.2.4 (usługa systemowa, porty UDP 319/320) = multiroom, widoczny też w aplikacji Dom jako
  „Serwerek”. Działa jako usługa użytkownika `airplay.service` (`~/.config/systemd/user/`, linger włączony) przez
  PipeWire (backend pa, gra na domyślne wyjście). TCP 7000 + porty dynamiczne, tylko sieć domowa (mDNS/avahi).
- `~/airplay/airplay.py`: `stan`, `wlacz/wylacz`, `tryb aux|bt`, `skanuj`, `wybierz MAC` (parowanie raz + trust),
  `start/stop` (hooki shairport-sync: przed graniem łączy głośnik BT i ustawia go jako wyjście `wpctl set-default`;
  `active_state_timeout` 20 s po końcu sesji rozłącza BT i wraca na AUX). Gdy BT niedostępny: gra przez AUX z uwagą.
  Ustawienia `~/airplay/ustawienia.json` (wlaczony, tryb, bt_mac, bt_nazwa, nazwa, opoznienie_bt =
  `audio_backend_latency_offset_in_seconds` w trybie BT), konfiguracja generowana `~/airplay/shairport-sync.conf`.
- Portal: `GET/POST /api/glosnik` ({wlaczony}, {tryb}, {wybierz: MAC}, {opoznienie_bt}), `POST /api/glosnik/skanuj`;
  strona `/strony/glosnik/` (repo `glosnik/`), karta 🔊 na Automatycznych.
- **Bluetooth włączony 2026-10-28** (za zgodą Antka): w `/boot/firmware/config.txt` zakomentowane `dtoverlay=disable-bt`
  (kopia `config.txt.bak_2026-10-28_bt`), UART na GPIO to teraz `ttyS0` (`serial0`). BT był też zablokowany przez rfkill
  (zapis w `/var/lib/systemd/rfkill/*bluetooth` = 0); `airplay.py` sam robi `bluetoothctl power on`, gdy radio jest wyłączone.
- Uwaga: połączenia AirPlay (port 7000 i dynamiczne) trafiają do logu jako SERWEREK-SKAN; zmiana reguły nft
  (wyjątek dla AirPlay) czeka na decyzję Antka (zmiana logowania bezpieczeństwa).

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
