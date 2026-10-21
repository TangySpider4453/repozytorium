# Serwer domowy (Raspberry Pi 4B): opis dla kolejnych sesji

Portal: **http://100.108.241.58/** (tylko Tailscale), `~/portal/app.py` (kopia w repo: `pi/app.py`), usługa
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
  --output=json`). Strona Zdrowie odświeża panel co 5 s, gdy coś trwa. Pierwsza pełna kopia: 17 GB w 511 s, kolejne ~30 s.
- **Bezpieczne wyłączenie**: komenda `raspiproszewylaczsie` (`/usr/local/bin`, repo `pi/nas/`): pyta o potwierdzenie
  (`-t` bez pytania), czeka na trwającą kopię (`--teraz` przerywa ją), Minecraft `save-all` + `stop` przez
  `~/powernukkitx/console.fifo`, zatrzymuje playit i portal, wpis w dzienniku zdrowia, ostatnie logi na NAS, odmontowanie
  NAS, `poweroff`.
- **Po zaniku prądu** wszystko startuje samo: usługi `enabled` (portal, Minecraft, playit, tailscale, dashboard, terminal,
  ollama, smbd, wayvnc), timery NAS/logów/kopii; NAS z fstab (`nofail`) + `nas-montuj` co 2 min; kopia z
  `Persistent=true` nadrabia pominiętą 02:00 zaraz po starcie, a przerwaną naprawia `e2fsck` przy następnym przebiegu.
- **Pliki w repo**: `pi/nas/` (skrypty, jednostki systemd, instrukcje, `instaluj.sh`; instalacja: skopiuj folder na Pi
  i `sudo bash instaluj.sh`).

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
