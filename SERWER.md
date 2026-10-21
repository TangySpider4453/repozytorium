# Serwer domowy (Raspberry Pi 4B): opis dla kolejnych sesji

Portal: **http://100.108.241.58/** (tylko Tailscale), `~/portal/app.py` (kopia w repo: `pi/app.py`), usługa
`home-portal`. Na Pi działa też **serwer Minecraft, na którym grają znajomi** (`powernukkitx`, `playit`,
`pi-dashboard`): nie restartuj ich i nie rób rebootu bez pytania. Po każdej zmianie portalu sprawdź
`systemctl is-active home-portal powernukkitx playit pi-dashboard`.

Pi jest w tej samej sieci lokalnej co serwer NAS użytkownika (eth0 172.23.0.20, wlan0 172.23.0.24). NAS ma służyć
do kopii zapasowych (szczegóły: do ustalenia z użytkownikiem).

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
  `uslugi`/`uslugi_kryt` albo `zadania` (dla usług uruchamianych timerem).

## Dziennik
- **2026-10-22**: Monitor zdrowia, dioda na wszystkich stronach, strona „Zdrowie serwera”, link w menu portalu.
  Backup `app.py.bak_2026-10-22_zdrowie`. Pierwszy pomiar: wszystko OK (46,7 °C, throttled 0x0, 10 usług aktywnych).
