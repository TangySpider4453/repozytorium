# Dziennik sesji

Najnowsze na górze. Format: `RRRR-MM-DD (gdzie)`: co zrobiono; co zostało.

- **2026-11-19 (chmura, Trener — skan tabelki nie działał)**: przyczyny: auto-aktualizacja przeładowała apkę przy
  powrocie z aparatu (teraz otwarty arkusz = „zajęta”) i iOS gubi `change` z pola pliku spoza DOM (teraz wpięte w body,
  `capture` przez atrybut). Formularz: przełącznik „na 100 g / na całe opakowanie” (przelicza z masy opakowania).
  Test na Pi: tabelka → 468 kcal, B 10, W 62, T 19 (Haiku). Test z logowaniem Claude: `sudo systemd-run --uid=tonyg
  -p EnvironmentFile=/etc/serwerek-bot/claude.env …` (unit `trener-test`, potem stop).
- **2026-11-19 (chmura, Trener — menu w połowie ekranu, znowu)**: łatka z „lekkim przewinięciem” nie wystarczała. Teraz
  okno się nie przewija (`html` overflow hidden, przewija się `body` = `SKR` w app.js), a gdy iOS przesunie okno
  (klawiatura, aparat), app.js cofa je do 0. Do sprawdzenia na iPhonie.
- **2026-11-19 (chmura, Trener — produkty: zwykła ilość, całe opakowanie, skan tabelki)**: przy wyborze produktu apka
  podpowiada najczęściej wpisywaną ilość, a chipy to „zwykle”, „całe” i porcja. Nieznany kod (też znany w OFF, ale bez
  makro) otwiera formularz z „📷 Zeskanuj tabelkę”, który włącza aparat i wypełnia makro. Nowa kolumna `masa_g`
  uzupełniona z OFF dla 7 produktów.
- **2026-11-19 (chmura, Trener — kcal, szacunek planu, pełne statystyki)**: nowy wzór wydatku (BMR Garmina 1998 + ruch
  dnia 390 + treningi; dziś 3180 zamiast 3650, cel przeliczony: 2940 kcal). Zaplanowane treningi: ~kcal, ♥, W, NP, TSS,
  km (`szacunek.py`). Zrobione: wszystkie statystyki w grupach, krzywa mocy, strefy mocy, przebieg z przybliżaniem
  (szczypanie / − + ‹ › cały) i celownikiem na wszystkich kanałach. Szczypania nie sprawdziłem na prawdziwym iPhonie.
- **2026-11-19 (chmura, Trener — fałszywe „zrobione”)**: ekran Dziś oznaczał wszystkie treningi dnia jako zrobione,
  gdy była jakakolwiek aktywność (MTB → siłka też ✓). Teraz `/api/dzis` zwraca `zrobione_sporty` i liczy się rodzaj.
- **2026-11-19 (chmura, Trener — przybliżanie wykresów)**: trener sam przybliża wykres w czacie (`od_s`/`do_s`) na
  moment, o którym mówi (np. strzał mocy ±2 min); oś wtedy w m:ss, nad wykresem „🔍 55:00–59:00”, znaczniki spoza
  zakresu ukryte, przycisk „cały przebieg” / „🔍 przybliżenie”. Zakres < 30 s poszerzany do 30 s.
- **2026-11-19 (chmura, Trener — ekran treningu i wykresy w czacie)**: czas wszędzie jako h:mm (sen 7:34, nie 7,57; też
  w kontekście dla Claude i w regule SYSTEM). Każdy trening klikalny: zrobiony → `#trening/<id>` (statystyki, strefy,
  wykres na kanał: tętno, moc ze średnią i max, prędkość, kadencja, wysokość, linia FTP, okrążenia, ćwiczenia siłki);
  zaplanowany → `#zaplanowany/<id>`. Przebieg sekundowy z Garmina (`przebieg.py`, cache w tabeli `przebiegi`).
  „💬 Omów trening” wysyła od razu wiadomość z `aktywnosc_id` i `omow` → trener daje krótkie podsumowanie i wykres ze
  znacznikami (numerki + lista pod wykresem). Czat może dołączać wykresy: przebieg treningu albo metryki dni
  (HRV, sen, RHR…), sam prosi o przebieg (`przebieg_id`). Test: omówienie dzisiejszego MTB pokazało strzały 833 W i 707 W.
- **2026-11-19 (chmura, Trener — powiadomienie po treningu)**: `trener-szybki.timer` co minutę pobiera 5 ostatnich aktywności (ok. 2 s); nowa → od razu pełny cykl (analiza + push). Pełny cykl co 15 min (było 20). Blokada `cykl.lock`, przy błędzie Garmina 10 min przerwy (kv `szybki_pauza`). Spóźnienie wynika już tylko z wgrywania do Garmina.
- **2026-11-18 (chmura, Trener — plan)**: śr i pt tylko jedna sesja, siłki pełne (min. 55 min, zwykle 60–75):
  nowe reguły w kontroli planu (`dni_jedna_sesja`, `silka_min_min`) i w `wymagania`; makrocykl i plan przebudowane.
  Potem: dwie sesje dozwolone tylko w czw i w jeden dzień weekendu (`weekend_dwie_max`).
  Potem: wyłączona kopia powiadomień na Linphone (`linphone`: false na Pi i w domyślnych), restart trener-web.
  Potem: iOS — po schowaniu klawiatury dolne menu i tło zostawały w połowie ekranu; `app.js` wymusza przeliczenie
  (visualViewport resize, focusout, powrót do apki). Do sprawdzenia przez Antka, czy już się nie zdarza.
  Potem: Jedzenie — można wpisywać na jutro (strzałka › do jutra); cel jutra wstępnie ze wzoru, trener liczy go
  dopiero w tym dniu (`potrzebny_przelicz` tylko dla dziś), Przelicz ukryty dla jutra.
  Potem: trener nazywa dni słowami (zasada w `ai.SYSTEM`, dzień tygodnia przy datach w kontekście).
  Potem: kontekst ma godzinę i znaczniki DZIŚ/JUTRO przy dniach, lista zmian planu pokazuje dni słowami
  (`kontekst.slownie`), poprawiony błąd czatu `#mysli` null. Wgrane na Pi, restart trener-web.
  Potem: cel kalorii przelicza się po zmianie planu na dziś (`dieta.plan_inny` w cyklu + `po_zmianie_planu` po
  przeplanowaniu). Dziś: 3170 → 2530 kcal (rower + Push → wolne).

- **2026-11-18 (chmura, usunięcie mostu RestOrTrain)**: skasowane z Garmina 8 treningów „Siłka …” ze znacznikiem
  `auto: restortrain-garmin` (odplanowane + usunięte; oryginały RestOrTrain i treningi Trenera zostały). Token Garmina
  przeniesiony do `~/trener/dane/garmin_tokens/`, Trener ma `python -m trener login`. Jednostki `rtg-garmin*` i projekt
  usunięte (archiwum `~/kopie/restortrain-garmin-20261118.tar.gz`), kopia `pi/restortrain-garmin/` usunięta z repo.
  Zostało: martwe resztki w portalu (wymaga restartu portalu).

- **2026-11-17 (chmura, Trener — wygląd)**: Rebranding Trenera: nowa ciemna paleta, logo i ikony SVG, wykresy SVG
  z dymkiem po dotknięciu (linie, słupki, fazy snu). Kafelki (sen, HRV, tętno, BB, obciążenie, stres…) prowadzą do
  `#metryka/<klucz>`: historia w zakresach 7/30/90/365/całość, średnia, dni tygodnia, porównanie z rokiem temu i rekordem.
  Sen: fazy z 14 nocy, szczegóły nocy vs 30 dni i najlepsza noc, pora snu. Wgrane na Pi (md5 zgodne), bez restartu.
  Potem: iPhone pokazywał starą wersję → `/` wstawia `?v=<mtime>` do CSS/JS i ma `no-store`; przy pisaniu w czacie
  dolne menu się chowa (pole przy klawiaturze). Restart `trener-web`.
  Push nie działał (pywebpush nie czyta klucza PEM z tekstu) → `Vapid.from_pem`; test doszedł do 1 urządzenia. Przycisk Test wysyła z Pi po 10 s (żeby zablokować telefon).
- **2026-11-17 (chmura, 4c)**: Claude Code na Pi: `~/.claude/settings.json` = `autoCompactWindow` 200000 + env `CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS=100000` (kompakt po ~1 h bezczynności, przed wygaśnięciem cache). Interaktywny `claude` na Pi nie jest zalogowany (token tylko w env usług). W chmurze tę zmienną Antek musi dodać sam w Settings środowiska (sesja nie może).
  Funnel włączony za zgodą Antka (`--https=443 http://127.0.0.1:8095`); test z internetu: strona 200, `/api/*` bez klucza 401.
  iPhone z Tailscale i tak szedł przez Funnel → dodano kod parowania (`python -m trener kod`) i poprawiono dolny pasek.
- **2026-11-17 (chmura, 4b)**: Zbudowano apkę **Trener** (`trener/`, Pi `~/trener/`): sync Garmina (pełna historia
  od 2021 w tle), analizy/plan/czat przez Claude (`--json-schema`), generator treningów rower/bieg/siłka (test: Garmin
  przyjął i usunął 3 treningi próbne), push VAPID + Linphone, PWA przez `tailscale serve` HTTPS. Testy: plan 44 s,
  analiza 22 s, czat 13 s. Timer działa, pierwsza poranna analiza wysłana. Czeka na cele Antka.
  Potem: baza wiedzy z badań (6 plików), makrocykl (`cel.py`), kontrola planu kodem; test na celu próbnym OK, usunięty.
  Potem: ankieta startowa + dopytanie przez Claude (`start.py`); planowanie dopiero po niej. Test OK, wyczyszczony.
  Potem: dostęp z internetu: klucz urządzenia (ciasteczko) dla żądań z Funnel — gotowe; włączenie Funnel zablokowane
  przez klasyfikator → czeka na Antka.
  Potem: badania pod cel (`badania.py`, Claude z WebSearch na Pi): test XCO 5 tematów, 25 źródeł działających, 5,5 min; wyczyszczony.
- **2026-11-17 (chmura, 4)**: Start z mózgu. Hook połączył Tailscale sam (`TS_AUTHKEY`), `ssh pi` wymagał linku
  „check” (podany, zatwierdzony). Przegląd Pi 4 09:23: wszystko zgodne z `uslugi.md` (45 °C, 0x0, RAM 1,8 GB, dysk 61%,
  kopia 02:00 OK). Na prośbę Antka oznaczono incydent `rtg-garmin-teraz` (05.11) jako przejrzany przez
  `POST /api/zdrowie/przejrzane` z `{"id": …}` → zdrowie: 0/0. Usunięto testowe modele Ollamy
  `qwen3:4b`, `qwen3:1.7b`, `llama3.2:3b` (nieużywane w kodzie ani w env) → dysk 61% → 51%; zostały qwen2.5:1.5b/3b i moondream.
  Stary token Claude przestał działać („organization has disabled Claude subscription access”) → nowy token:
  `claude setup-token` w tmux na Pi, Antek dał link→kod na czacie, token zapisany prosto do `claude.env` (kopia
  `.bak_2026-11-17`), test OK, restart przez `bez_rozmowy.sh` 09:29:54. Zapasowo jest `pi/bot/nowy_token.sh` (w `~/bot/`).
- **2026-11-17 (chmura)**: Podłączono repo do sesji. Tailscale nie działa: brak `TS_AUTHKEY` i sieć „Limited”
  blokuje hosty Tailscale; podano użytkownikowi instrukcję (angielskie nazwy w aplikacji). Utworzono `pamiec/` i
  wpisano do `CLAUDE.md`, że sesje mają z niej korzystać. Użytkownik ustawił sieć i klucz; połączono przez link
  logowania, `ssh pi` działa. Uwaga: `powernukkitx` (Minecraft) był `inactive` — zgłoszone użytkownikowi, nieruszane.
- **2026-11-17 (chmura, 3)**: Scalono `claude/nauka-z-claude`, `lazik-mapa` i `claude/pamiec` w gałąź domyślną
  (konflikt tylko w dzienniku `PLAN.md`). Nowy `CLAUDE.md` = start od mózgu. Hook startowy wypisuje stan Tailscale
  albo link logowania.
- **2026-11-17 (chmura, 2)**: Przegląd Pi 4 (wszystko zdrowe, Minecraft wyłączony celowo) i kopii ze starego konta
  (`Serwerek`, `Łazik`). Odkryto, że prawdziwy stan jest na gałęziach `claude/nauka-z-claude` i `lazik-mapa`.
  Zbudowano mózg: `MAPA.md` + węzły (zasady, urządzenia, usługi, repo, projekty). Hasła z kopii nieczytane.
- **2026-10-19 – 2026-11-16 (stare konto)**: serwer, nauka, bot, telefon, Garmin — `Serwerek/PRZEKAZANIE.md`;
  łazik — `Łazik…/PRZEKAZANIE.md` (kopie na Pi).
- **2026-10-19 – 2026-10-22**: historia wcześniejszych prac w dziennikach `PLAN.md` (sekcja 9), `PROGRES.md`, `SERWER.md`.
- Modele Trenera: `model`=Haiku (czat, analiza, ankieta, ocena bazy), `model_ciezki`=Sonnet (`ciezki=True`: plan, cel, badania); `ai.zapytaj` zamienia Opus na Sonnet. `dane/ustawienia.json` na Pi poprawiony.
- Limit Claude w czacie Trenera: `ai.BrakTokenow` (z godziną resetu) → pytanie czeka w kv `czat_czeka`, w czacie notka ⏳; po resecie odpowiada timer w trener-web, a zapasowo cykl co 20 min; potem push „💬 Trener odpowiedział”. Analizy i plan i tak ponawia cykl.
- Plan: treningi opcjonalne jako osobne wpisy (`opcjonalny: true`) — idą na zegarek z nazwą „Opcjonalny: …” (decyzja Antka).
- Stałe wymagania Trenera: `wymagania` w kontekście jako nadrzędne, `plan.partia()` liczy górę po kategoriach Garmina, zmiana wymagań przebudowuje makrocykl (`odcisk_makro`, bez nowych badań). Wiedza: sekcja „Nogi” w `wiedza/03_silka.md`. Stara notka 2+2 usunięta z `pamiec_trenera`.
- Kontrola planu sprawdza też: Push/Pull/Full Upper w tytułach, brzuch (kategorie CRUNCH/LEG_RAISE/CORE/PLANK) na każdej siłce, max 1 ćwiczenie skośne/tydz. Uwaga: „prostowanie nóg” Antka jest w Garminie pod CRUNCH.
- 2026-11-17: ustalenia z RestOrTrain przeniesione do Trenera (wymagania na Pi, nowe kontrole planu, cel rekompozycji).
- 2026-11-17: karta Periodyzacja w zakładce Plan zwijana (pamięta stan), szczegóły rozwijane przy każdej fazie.
- 2026-11-17: codzienna korekta planu po ocenie snu; duże zmiany (usunięcie/dodanie jednostki) czekają na decyzję Antka (push + przyciski + czat).
- 2026-11-17: apka Trener — wygląd Liquid Glass (pływający szklany pasek kart z przesuwaną soczewką, szklane karty, przejścia ze sprężyną i rozmyciem), auto-aktualizacja (`/wersja` + przeładowanie, gdy apka nie jest zajęta), poprawka wyścigu przy szybkim klikaniu zakładek (numer nawigacji w `api()`), nagłówek znów przyklejony (body `overflow-x: clip`). Potem: rogi squircle (sq.svg) i blokada powiększania.
- 2026-11-17: zakładka Plan otwiera się przewinięta do dzisiaj (wyżej: periodyzacja, prośba, poprzednie dni), duży nagłówek „Dziś”, wykres bloczkowy treningu roweru i biegu (jak w interwałach).
- 2026-11-17: dziennik kalorii w Trenerze (skaner kodów, Open Food Facts, cel kcal/makro liczony przez trenera na każdy dzień
  pod trening) i ekran Waga (Progres w stylu Liquid Glass); kafelki Kalorie i Waga na Dziś. Do celów dopisany priorytet
  „spalić jak najwięcej tłuszczu” w bezpiecznym tempie (0,5–0,7%/tydz.). Wiedza: `07_odzywianie.md`, poprawiona `06`.
- 2026-11-17: Jedzenie: zdjęcie tabelki (AI czyta wartości na 100 g), poprawianie produktu z bazy/OFF (przelicza wpisy),
  zdjęcie posiłku + opis (Sonnet szacuje składniki i gramy, sprawdza opis ze zdjęciem; lista do edycji).
- 2026-11-17: cel kalorii sam się przelicza po nowym treningu z Garmina i co godzinę dolicza nadwyżkę aktywnych kcal;
  poprawione pole daty w Wadze na iOS.
- 2026-11-19: Jedzenie: przy nazwie posiłku suma B/W/T jako kolorowe liczby (kolory jak paski makro: niebieski B,
  żółty W, fioletowy T) obok kcal.
- 2026-11-19: czarny pasek na dole w PWA (body height:100% w trybie standalone było niższe o pasek statusu) → body position:fixed; inset:0.
- 2026-11-19: czarny pas na dole to błąd iOS 26 w apce z ekranu głównego: innerHeight 793 z 852 (krótsze o pasek statusu 59).
  Poprawka: JS mierzy 100lvh − innerHeight → --brak; body, nav, .pisz, .arkusz-tlo schodzą o --brak. Potwierdzone pomiarem z telefonu.
- 2026-11-19: Dziś i Plan: zrobiony trening z planu (✓ zrobione) po kliknięciu otwiera dane aktywności z Garmina (#trening/<id>),
  /api/dzis zwraca zrobione_id (dzień → kategoria → id). Niezrobione dalej otwierają plan treningu.
- 2026-11-19: --brak nie pomógł (pas to obszar poza oknem, menu się w nim chowało). Prawdziwa przyczyna: WebKit 301108,
  okno krótsze, gdy dokument niższy niż ekran. Poprawka: min-height html w trybie standalone; pomiar z telefonu: 852/852.
- 2026-11-19: nowe menu: Dziś · Plan · Jedzenie (środek, szybki dostęp do kalorii) · Dane · Czat. Treningi to podzakładka w Dane
  (Podsumowanie | Treningi). Dane ładują dni i agregaty równolegle (~2× szybciej).
- 2026-11-19: tierlista ćwiczeń siłowych od Antka (S/A/B/C/wykluczone + 10 zasad układania siłki) w Ustawieniach.
  Plan układa siłkę głównie z S/A, kontrola odrzuca wykluczone. Po siłce z nowym ćwiczeniem: push + karta na Dziś
  z ocenami S/A/B/C/✕/pomiń, ocena dopisuje się do tierlisty.
- 2026-11-19: apka bez „Ładuję…”: dane wszystkich zakładek pobierane z góry i trzymane w pamięci, a odświeżane w tle.
  Animacje: zmiana zakładki przesuwa ekran w stronę zakładki (karuzela); otwarcie karty rośnie z niej na cały ekran;
  wyjście (‹ w nagłówku albo gest wstecz) kurczy ekran do karty.
