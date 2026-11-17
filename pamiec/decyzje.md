# Decyzje i stałe ustalenia

| Data | Ustalenie | Powód / źródło |
|---|---|---|
| 2026-10-19 | Projekt w repo GitHub, praca także z chmury (iPad) | prośba użytkownika |
| 2026-10-19 | Hook startowy łączy chmurę z Pi przez Tailscale | zgoda użytkownika |
| 2026-10-19 | Zakładka „Najważniejsze” obowiązkowa i pierwsza w każdej stronie nauki | prośba użytkownika |
| 2026-10-21 | Lista nauki: najbliższy termin na górze | prośba użytkownika |
| 2026-10-21 | Przed edycją `sprawdziany.json` zawsze pobierz go z Pi (użytkownik sam zmienia daty) | ochrona jego zmian |
| 2026-11-17 | Folder `pamiec/` = wspólna pamięć sesji; czytana na starcie, uzupełniana na końcu | prośba użytkownika |
| 2026-11-16 | Claude nie dotyka Garmina; Garmin = parser regułowy + lokalny qwen2.5:3b | Antek; model 21 min i błędy |
| 2026-11-16 | Bez lokalnego modelu do rozmów i planowania (za wolny: 79–164 s) | pomiar na Pi |
| 2026-11-17 | Zmiana konta Claude; kopie starych rozmów na Pi w `~/Desktop/dla claude kopie zapasowe/` | Antek |
| 2026-11-17 | `pamiec/MAPA.md` = punkt startowy mózgu; węzły tematyczne zamiast jednego wielkiego pliku | prośba Antka |
| 2026-11-17 | **Trener** (własny RestOrTrain, webapka): Claude analizuje i planuje (zasada z 16.11 zniesiona dla tej apki); powiadomienia push w apce + Linphone; apka **zastępuje** RestOrTrain (stary most do czasu przełączenia); treningi idą na zegarek **automatycznie** z powiadomieniem o zmianach | Antek |

## Token Claude na Pi (2026-11-17)
- Bot i telefon używają `CLAUDE_CODE_OAUTH_TOKEN` z `/etc/serwerek-bot/claude.env` (token z `claude setup-token`, ważny rok).
- Odnawianie z chmury: `tmux new -d -x 400 claude setup-token` na Pi → link Antkowi → jego jednorazowy kod przez
  `tmux send-keys` → token wyciągnięty z `capture-pane` do pliku 600 i **nigdy nie wypisany** (sed maskuje `sk-ant-…`)
  → test `claude -p` → zapis do env → `bez_rozmowy.sh`. Albo Antek sam: `bash ~/bot/nowy_token.sh` w terminalu portalu.
