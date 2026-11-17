# Zasady (czego NIE robić) — czytaj zawsze

| Zasada | Skąd |
|---|---|
| **Nikomu nic nie wysyłaj/nie pisz bez zgody.** Mobidziennik tylko do odczytu, poczta nigdy nie wysyła. | Antek, „nie ma prawa nic pisać do nikogo bez mojej zgody ani ty też nie masz” |
| **Repo jest publiczne:** zero haseł, tokenów, kodów dostępu, publicznego IP domu, adresu tunelu Minecrafta, nazwisk. | przekazania |
| Sekrety tylko na Pi: `/etc/serwerek-bot/*.env`, `/etc/nas-credentials`, `~/restortrain-garmin/tokens/`, `~/bot/google/`, `~/portal/dane/dostep.json`. | SERWER |
| **Nie restartuj Minecrafta (`powernukkitx`), `playit`, `pi-dashboard` i nie rób rebootu Pi bez pytania** — grają znajomi. Minecraft jest włączany ręcznie. | od początku |
| Bot/telefon restartuj tylko przez `bash ~/bot/bez_rozmowy.sh` (nie w trakcie rozmowy). | SERWER |
| **AirPlay: nie ruszaj bez zgody.** | Antek |
| **Garmin** (zmiana 17.11): nowa apka **Trener** może używać Claude do analizy, planów i rozmowy i **sama** zapisuje treningi w Garminie. Usuwa tylko swoje (znacznik w opisie). Claude w sesji tylko czyta dane Garmina, zapis robi kod apki. Stary most RestOrTrain bez Claude do czasu wyłączenia. Nigdy nie proś o hasło Garmina; przed `replace_original` pytaj. | Antek 16.11 → 17.11 |
| Przy wysokiej temperaturze **nie wyłączaj Ollamy** (alerty od Ollamy wyciszone). | Antek |
| Klasyfikator bezpieczeństwa zablokował akcję → **nie obchodź**, zapytaj Antka. | Antek |
| Zdjęcia Progres prywatne: tylko Pi i NAS, nigdy repo. | PROGRES |
| Łazik: przed ruszaniem silnikami z daleka zapytaj (może stać na stole). | LAZIK |
| `sprawdziany.json`: najpierw pobierz z Pi (Antek sam zmienia daty). Przed wgraniem każdego pliku porównaj md5 Pi vs git. | PLAN |
| Linki „check” Tailscale podawaj od razu (wygasają po minutach). | dostęp |
