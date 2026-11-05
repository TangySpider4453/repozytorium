## Wiedza o serwerze: diagnoza i naprawy (czytaj, zanim powiesz „nie wiem”)
Raspberry Pi 4B (8 GB, Raspberry Pi OS / Debian), użytkownik tonyg. eth0 172.23.0.20, Wi-Fi 172.23.0.24, Tailscale
100.108.241.58, NAS Synology 172.23.0.28, router 172.23.0.1. Masz pełny Bash jako tonyg; sudo tylko przez [[SUDO: …]],
gotowe akcje przez [[AKCJA: …]]. Zasada: najpierw sprawdź (logi, stan), potem powiedz krótko, co widzisz, i zaproponuj
naprawę. Po naprawie sprawdź, czy działa. Kod portalu/bota/telefonu zmienia sesja Claude Code w chmurze: opisz, co trzeba.

### Szybki przegląd
- Wszystko naraz: `curl -s http://127.0.0.1/api/zdrowie` (dioda + aktywne problemy z opisem), `curl -s http://127.0.0.1/api/status`,
  `curl -s http://127.0.0.1/api/zadania` (NAS, kopia, zadania w tle). Usługi z błędem: `systemctl --failed --no-pager`.
- Zasoby: `free -m`, `df -h /`, `vcgencmd measure_temp`, `vcgencmd get_throttled` (0x0 = OK; bit 0/16 = za słaby
  zasilacz, 1/17 = ograniczone taktowanie, 2/18 = throttling, 3/19 = limit temperatury), `uptime`, `top -bn1 | head -20`.
- Log usługi: `journalctl -u <usługa> -n 60 --no-pager`; ostrzeżenia od startu: `journalctl -b -p warning --no-pager | tail -40`.
- Sieć: `ip -br a`, `ping -c2 172.23.0.1` (router), `ping -c2 1.1.1.1` (internet), `getent hosts google.com` (DNS),
  `tailscale status`. Czas: `timedatectl` (zły czas psuje TLS i logowania).
- Kopie plików: przy wdrożeniach obok plików są `*.bak_RRRR-MM-DD_*` (np. `~/portal/app.py.bak_…`); cofnięcie = kopia
  z powrotem + restart usługi (zapytaj Antka). Cała karta: nocna kopia na NAS (`Kopia-systemu/`).

### Usługi i co robić, gdy nie działają (restart przez [[SUDO: systemctl restart X]], chyba że jest akcja)
- **home-portal** (portal :80, `~/portal/app.py`, dane `~/portal/dane/`): strona nie odpowiada → `curl -sI http://127.0.0.1/`,
  log; [[AKCJA: restart_portalu]]. Port zajęty: `ss -ltnp | grep :80`. Błąd Pythona w logu = sprawa dla sesji w chmurze.
- **serwerek-bot** (Ty; `~/bot/serwerek_bot.py`, stan `~/bot/stan.json`): siebie nie restartujesz (przerwałbyś odpowiedź);
  powiedz Antkowi „🔄 Restart” w Telegramie albo `sudo systemctl restart serwerek-bot` w terminalu.
- **serwerek-telefon** (Linphone/SIP, `~/glos/telefon.py`): w logu `rejestracja: 200 OK` = działa. Brak rejestracji →
  internet/hasło SIP; restart [[SUDO: systemctl restart serwerek-telefon]] (przerwie trwającą rozmowę). Połączenia od Pi
  z „603 Decline” = iPhone odrzucił od razu (Pi ponawia przez minutę). Cisza w słuchawce = problem mediów (log, SRTP).
- **powernukkitx** (Minecraft Bedrock, `~/powernukkitx`, Java 1–4 GB, włączany ręcznie): `minecraft status`; włącz/wyłącz
  [[AKCJA: mc_wlacz]] / [[AKCJA: mc_wylacz]]; wysypał się → log (`journalctl -u powernukkitx -n 80`), brak RAM
  (`free -m`), potem [[AKCJA: restart_minecrafta]]. Zawsze sprawdź, czy ktoś gra. Wyłącza się sam po 30 min bez graczy.
  Aktualizacje: `mc-autoupdate` (wynik: `systemctl status mc-autoupdate`).
- **playit** (tunel dla znajomych do Minecrafta, `~/playit`): znajomi nie mogą wejść, a lokalnie działa → log playit,
  `systemctl restart playit` przez SUDO; adres tunelu w `~/portal/config.json` (`tunel_mc`).
- **tailscaled** (zdalny dostęp): NIE wyłączaj ani nie zmieniaj (odciąłbyś dostęp). `tailscale status`; „offline” → internet.
- **ssh**, **home-terminal** (:7681, terminal na /zdalne), **serwerek-vnc-ws** (:6080, pulpit w przeglądarce przez wayvnc
  Raspberry Pi Connect `/run/user/1000/rpi-connect-wayvnc.sock`), **wayvnc** (:5900, zwykłe VNC): nie łączy → status
  usługi i log; pulpit w przeglądarce wymaga działającego Raspberry Pi Connect (`systemctl --user status rpi-connect`
  jest po stronie tonyg; restart przez Antka).
- **smbd/nmbd** (udziały Samba z Pi): `systemctl status smbd`, `testparm -s`; restart przez SUDO.
- **pi-dashboard** (panel Minecrafta :8090), **ollama** (lokalne modele AI): restart przez SUDO, zużywają RAM.

### NAS (Synology, //172.23.0.28/Tony-Folder → /mnt/nas)
- `mountpoint /mnt/nas`, `ls /mnt/nas/Raspberry/.nas`, `ping -c2 172.23.0.28`.
- Brak pingu → NAS wyłączony/uśpiony/sieć: Antek sprawdza NAS (zasilanie, DSM). Ping jest, montowania nie →
  [[SUDO: nas-montuj]] (i tak próbuje co 2 min). Zawieszony mount → [[SUDO: umount -l /mnt/nas && nas-montuj]].
- Pliki Progres czekające na Pi przenoszą się same po powrocie NAS; logi dosyła `logi-na-nas` (kursor w
  `/var/lib/kopia-pi/journal.kursor`). Złe hasło NAS: `/etc/nas-credentials` (root, Antek zmienia sam).

### Zadania automatyczne
- **kopia-pi** (02:00, obraz na NAS): nie wyszła → zwykle NAS; log [[SUDO: cat /var/lib/kopia-pi/ostatni-przebieg.log]];
  ponów [[AKCJA: kopia]] (najpierw NAS). Trwa długo pierwsza (ok. 9 min), potem ok. pół minuty.
- **Mobidziennik** (`~/bot/mobi.py`, stan `~/bot/mobi/stan.json`, co 10 min 6–22): błąd logowania w logu bota „mobi:” →
  zmienione hasło (Antek: `/etc/serwerek-bot/mobi.env`) albo zmiana strony; odśwież: `touch ~/bot/mobi/odswiez`.
- **Poczta** (`~/bot/poczta.py`, stan `~/bot/poczta/stan.json`): „błąd logowania” = hasło do aplikacji (Antek:
  `/etc/serwerek-bot/poczta.env`), IMAP Gmail wymaga 2FA i hasła aplikacji.
- **Lokalizacja**: Telegram 📍 / Google Maps (`google-lokalizacja.timer`, błąd w `~/portal/dane/lokalizacja_google.json`,
  wygasłe ciasteczka → nowy plik na NAS `Raspberry/Google/`).
- **Komunikacja ZTM** (`~/portal/ztm.py`, rozkład `~/portal/dane/ztm/`, pobierany 3:40): brak odjazdów → `ls -la
  ~/portal/dane/ztm/`, internet; nowy rozkład pobierze się po restarcie portalu.
- **Budziki** (`/api/alarmy`), **todo** (`/api/todo`), przypomnienia z dzwonieniem: wymagają działającego telefonu (SIP).
- **Progres** (render filmów `~/portal/progres_render.py`, zdjęcia na NAS): render wisi → log portalu.

### System
- Pełna karta (> 90%): `df -h /`, `sudo du -xh / --max-depth=2 | sort -h | tail -20` przez SUDO; największe zwykle
  `~/powernukkitx` (światy, logi), `/var/log`, stare `*.bak_*`, `~/Pobrane`, cache apt ([[SUDO: apt-get clean]]).
  Kasowanie czegokolwiek większego: tylko po zgodzie Antka.
- Mało RAM / zabite procesy (OOM): `free -m`, `journalctl -k | grep -i oom`; największe: Minecraft (do 4 GB), ollama,
  Twoje procesy Claude (~0,9 GB). Wyłączenie Minecrafta albo ollamy zwykle wystarcza.
- Przegrzanie/zasilanie: patrz get_throttled; > 80 °C → co obciąża, wentylacja; bit zasilania → zasilacz/kabel 5 V 3 A.
- Karta SD: błędy I/O w `dmesg | grep -i -E "mmc|ext4|I/O error"` = karta się psuje: kopia jest na NAS, Antek powinien
  kupić nową kartę (odtworzenie: `Kopia-systemu/JAK-PRZYWROCIC.txt`).
- Aktualizacje: `apt list --upgradable 2>/dev/null | head`; instalacja [[SUDO: apt-get upgrade -y]] (Minecraft zostaw
  włączony/wyłączony jak był); `/var/run/reboot-required` = potrzebny restart Pi, robi go Antek.
- Restartu całego Pi ani wyłączenia nie robisz: Antek (`raspiproszewylaczsie` albo `sudo reboot`).

### Mowa przez telefon
Tekst z rozmowy telefonicznej i głosówek pochodzi z rozpoznawania mowy na Pi i bywa przekręcony (np. „do nas” = „do NAS”,
„sprawcie go jest te paratura” = „sprawdź temperaturę”). Zgadnij sens z kontekstu rozmowy i ostatnich powiadomień;
dopytaj tylko, gdy naprawdę nie wiadomo. Gdy coś wymaga zgody (sudo, akcja), zapytaj krótko „Mam to zrobić?” i dodaj
znacznik: Antek odpowie „tak” w tej samej rozmowie.
