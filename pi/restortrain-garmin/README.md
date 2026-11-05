# restortrain-garmin

Treningi siłowe z **RestOrTrain** przychodzą do Garmin Connect jako jeden blok czasowy (np. 90 min), a ćwiczenia są tylko
w opisie. Ta usługa na Raspberry Pi co 10 minut czyta kalendarz Garmin Connect i robi z takiego opisu **natywny trening
siłowy Garmina**: rozgrzewka, serie rozgrzewkowe, ćwiczenia jako „serie × powtórzenia” z przerwami, schłodzenie. Zegarek
pokazuje kolejne ćwiczenie, a po treningu Garmin zapisuje poszczególne ćwiczenia.

## Jak działa
- `rtg-garmin.timer` co 10 min uruchamia `./rtg.sh sync` (jako tonyg, nie root). Co ile minut naprawdę sprawdza:
  ustawienie „Sprawdzanie zmian co ile minut” na stronie portalu **Automatyczne** (karta „Treningi siłowe na zegarek”).
- Bierze tylko **treningi siłowe** z kalendarza (`sportTypeKey == strength_training`; bieg, rower itd. odpadają bez
  pobierania szczegółów), z **RestOrTrain** (`workout.consumerName == "RestOrTrain"`) i z opisem w formacie `NxM`.
- **Pomija dni minione i dni ze zrobionym treningiem siłowym** (aktywność `activityTypeId == 13` w kalendarzu).
- Stan w `data/state.db` (SQLite). Nowy trening → utwórz i zaplanuj; zmieniony opis → usuń nasz stary i utwórz nowy;
  oryginał zniknął / przeniesiony → usuń nasz z tego dnia; bez zmian → nic (bez duplikatów).
- Usuwa **wyłącznie** treningi z dopiskiem `auto: restortrain-garmin` w opisie (sprawdza to w Garmin przed usunięciem).
- Nazwa: „Siłka” + początek tytułu oryginału (przed „—”), np. „Dół B — martwy ciąg…” → „Siłka Dół B”. Ciężaru nie ustawia (wpisujesz go na zegarku).

## Komendy
```
./rtg.sh parse plik.txt        # parser + mapowanie, bez sieci
./rtg.sh login                 # logowanie (MFA), zapis tylko tokenu w tokens/
./rtg.sh sync --dry-run        # plan zmian + wygenerowany JSON, nic nie zapisuje
./rtg.sh sync --teraz          # przebieg od razu (to samo robi przycisk „Synchronizuj teraz”)
./rtg.sh status                # ostatnie przebiegi i treningi
.venv/bin/python -m pytest -q  # testy
```

## Ustawienia
- Strona **Automatyczne** → Ustawienia → „Treningi siłowe na zegarek”: włącznik, co ile minut, okno dni, powtórzenia
  z zakresu (`max`/`min`), przerwy (odliczanie albo przycisk) i ich długości, zdejmowanie oryginału.
- `config.yaml`: wartości domyślne oraz `zapis_dozwolony` (dopóki `false`, usługa tylko pokazuje plan zmian) i
  `llm_fallback`.

## Dopisanie ćwiczenia
`exercises.yaml`: dopisz alias do istniejącego wpisu albo nowy wpis (`nazwa`, `aliasy`, `category`, `exerciseName`
z `data/garmin_exercises.json`). Sprawdź: `./rtg.sh parse plik.txt` i `.venv/bin/python -m pytest -q` (test odrzuci
parę, której nie ma na oficjalnej liście Garmina).

**Nieznane ćwiczenia** dopisuje sam Claude Code (`llm_fallback: true`): dwa krótkie pytania do `claude -p` (Haiku, bez
narzędzi) — kategoria, potem ćwiczenie z tej kategorii; wynik zawsze sprawdzany z oficjalną listą i dopisywany do
`exercises.yaml` z `auto: true`, a Ty dostajesz powiadomienie. **Ta opcja wysyła nazwy ćwiczeń do Anthropic.**
Wyłączenie: `llm_fallback: false` (wtedy tylko powiadomienie z prośbą o alias).

## Odnowienie logowania
Gdy przyjdzie powiadomienie „logowanie wygasło”: portal → Zdalne → Terminal →
`cd ~/restortrain-garmin && ./rtg.sh login`. Hasło nie jest nigdzie zapisywane; token: `tokens/` (700/600, poza gitem).

## replace_original
Gdy włączone, usługa zdejmuje oryginał RestOrTrain z kalendarza (definicji nie usuwa). Jeśli RestOrTrain wypchnie go
ponownie, nie powstaje duplikat (stan po `source_workout_id` + data). Domyślnie wyłączone.

## Powiadomienia
Przez bota serwerka (Linphone, zapasowo Telegram): plik w `~/bot/powiadomienia/`. Wysyłane przy: nieznanym ćwiczeniu,
dopisaniu ćwiczenia przez Claude, wygasłym logowaniu, 3 nieudanych synchronizacjach z rzędu.

## Wyłączenie i odinstalowanie
```
sudo systemctl disable --now rtg-garmin.timer rtg-garmin-teraz.path
sudo rm /etc/systemd/system/rtg-garmin*.{service,timer,path} && sudo systemctl daemon-reload
rm -rf ~/restortrain-garmin        # usuwa też token
```
Treningi „Siłka …” w Garmin Connect zostają; usuniesz je w aplikacji.
