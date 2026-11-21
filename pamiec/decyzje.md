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
| 2026-11-17 | Po podaniu/zmianie celu Trener sprawdza, czy baza wiedzy pasuje, i **zawsze** szuka źródeł w internecie pod cel (pliki `dane/wiedza_cel/`, linki weryfikowane) — dopiero potem periodyzacja | Antek: „niech sprawdzi, czy źródła pasują… i niech poszuka tak czy siak” |
| 2026-11-17 | Trener nie planuje, dopóki Antek nie przejdzie ankiety startowej (cele + jak ma wyglądać plan) i dopytania | Antek: „musi być pytanie o cele i jak chcę, żeby to wyglądało” |
| 2026-11-17 | Trener planuje wg **bazy wiedzy ze źródeł** (`trener/trener/wiedza/`) + makrocyklu do celu + kontroli reguł kodem; nowe zasady dopisuj do plików wiedzy (z linkiem) | Antek: „treningi zrobione tak jak powinny” |
| 2026-11-17 | **Trener** (własny RestOrTrain, webapka): Claude analizuje i planuje (zasada z 16.11 zniesiona dla tej apki); powiadomienia push w apce + Linphone; apka **zastępuje** RestOrTrain (stary most do czasu przełączenia); treningi idą na zegarek **automatycznie** z powiadomieniem o zmianach | Antek |

## Token Claude na Pi (2026-11-17)
- Bot i telefon używają `CLAUDE_CODE_OAUTH_TOKEN` z `/etc/serwerek-bot/claude.env` (token z `claude setup-token`, ważny rok).
- Odnawianie z chmury: `tmux new -d -x 400 claude setup-token` na Pi → link Antkowi → jego jednorazowy kod przez
  `tmux send-keys` → token wyciągnięty z `capture-pane` do pliku 600 i **nigdy nie wypisany** (sed maskuje `sk-ant-…`)
  → test `claude -p` → zapis do env → `bez_rozmowy.sh`. Albo Antek sam: `bash ~/bot/nowy_token.sh` w terminalu portalu.
| 2026-11-17 | Trener (i każdy Claude na Pi): domyślnie Haiku; Sonnet tylko do cięższych rzeczy (plan, cel, badania); **Opus nigdy** — za drogi | Antek |
| 2026-11-17 | Trener: siłka GÓRA 3× w tygodniu zawsze (`gora_tyg`, `wymagania` w ustawieniach; kontrola planu to sprawdza); nogi wg bazy wiedzy | Antek |
| 2026-11-17 | Trener: góra = Push, Pull, Full Upper (3 różne sesje/tydz.); brzuch na końcu każdej siłki; skośne/boczne max 1/tydz. (V-taper) | Antek |

## 2026-11-17 — Trener przejmuje ustalenia z RestOrTrain
- Pełne ustalenia (profil, strefy, lubiane ćwiczenia, wzór tygodnia, styl prowadzenia) są TYLKO na Pi w `dane/ustawienia.json` → `wymagania` (dane osobowe, nie do repo). Postęp ćwiczeń w kv `pamiec_trenera`.
- Cel dopisany: rekompozycja do 30.04.2027 bez agresywnego deficytu; rower dalej pod cele kolarskie (nie „ogólne spalanie”). Sporty: + bieg.
- Kontrola planu w kodzie: nogi 2×/tydz. (`nogi_tyg`), dni tylko na nogi (`dni_tylko_nogi`, na Pi = wtorek), odwodzenie+przywodzenie na końcu nóg, bez szrugsów, bez 2 tricepsów pod rząd, `tetno_ciezkie` (bpm) do liczenia jednostek intensywnych. Strefy własne → cele „tetno”/„moc” w bpm/W.
- 2026-11-18 (Antek): **trener nazywa dni słowami** (dziś, jutro, w czwartek), nie datami — daty go mylą.
- 2026-11-18 (Antek): **powiadomienia Trenera tylko push z apki**, bez kopii na Linphone (`linphone`: false);
  Linphone tylko zapasowo, gdy push nie dojdzie do żadnego urządzenia, i przy błędzie logowania Garmina.
- 2026-11-18 (Antek, poprawka): **dwie sesje tylko w czwartek i w jeden dzień weekendu**; pon, wt, śr, pt = jedna
  (`dni_jedna_sesja` [0,1,2,4], `weekend_dwie_max` 1).
- 2026-11-18 (Antek): **śr i pt = jedna sesja** (sama siłka, bez roweru/biegu; `dni_jedna_sesja` [2,4]); **siłka zawsze pełna**,
  ok. 60–75 min, min. 55 min w planie (`silka_min_min`, w deloadzie 80%): lżej = RIR/ciężar, nie 2 serie po 35 min.
  Wzór tygodnia w `wymagania` zmieniony (bieg na ndz, rower pon/czw/sob/ndz). Zmiana wymagań przebudowała makrocykl.

## 2026-11-17 — Codzienna korekta planu po ocenie snu
- Po porannej analizie (sen) trener ZAWSZE przegląda najbliższe dni (`korekta_po_snie`, domyślnie włączone). Małe zmiany (krócej/lżej/strefa) wchodzą od razu.
- Usunięcie albo dodanie jednostki (dzień+sport) NIE wchodzi samo: kv `propozycja_planu`, push „❓ Trener pyta”, karta na Dziś i w Plan z przyciskami Zmień / Zostaw. Można też odpowiedzieć w czacie. Decyzja trafia do `pamiec_trenera`. To samo dotyczy przeplanowania po analizie treningu. Prośby z czatu i przebudowa periodyzacji zmieniają plan bez pytania.

## 2026-11-17 — Trener PWA: aktualizacje i wygląd
- Apka sama sprawdza `/wersja` (najnowszy mtime index/styl/app) przy powrocie do niej i co 60 s; przy nowej wersji przeładowuje się, ale nie w trakcie pisania, ankiety ani czekania na zadanie (wtedy przy następnym przejściu). Po wgraniu plików na Pi nie trzeba nic robić w telefonie.
- Styl Liquid Glass na całej apce; zmienne `--szklo`, `--blask`, `--rozmyj`, `--sprezyna` w `styl.css`. `--karta` jest półprzezroczysta, a do obwódek na wykresach jest `--pierscien`.
- Rogi kafelków/kart to squircle (ciągłe zaokrąglenie jak w iOS): maska 9-slice `static/sq.svg` przez `-webkit-mask-box-image`; przyciski i pasek kart zostają kapsułami.
- Apki nie da się powiększać: `user-scalable=no`, `touch-action: pan-x pan-y` (blokuje podwójne stuknięcie) i blokada gestów `gesture*` w JS. Nie blokować `touchend`, bo zjada szybkie drugie kliknięcie.
- Wykres bloczkowy treningu (`wykresTreningu` w app.js): szerokość = czas kroku, wysokość i kolor = strefa liczona z FTP / tętna progowego / tempa progowego (`progi` z `/api/plan` i `/api/dzis`); kroki na dystans liczone ~5,5 min/km bieg, ~2,2 min/km rower.
- 2026-11-17: redukcja tłuszczu „jak najwięcej” znaczy u Antka (nastolatek, sportowiec) maksymalne **bezpieczne** tempo: deficyt
  ≤ 500 kcal i ≤ 20%, dostępność energii ≥ 35 kcal/kg FFM, białko ~2 g/kg, tłuszcz ≥ 0,8 g/kg, bez głodówek i „spalaczy”.
  Progi pilnuje kod (`dieta._przytnij`), nie tylko prompt.
- 2026-11-19: wydatek dnia = średnie spoczynkowe z Garmina + średni ruch w ciągu dnia (mediana, bez treningów) + treningi
  (zrobione z Garmina, zaplanowane z szacunku). Sam BMR + treningi dawałby za mało jedzenia, więc ruch dnia zostaje.
- 2026-11-19: czas trwania (sen, trening) zawsze h:mm, nigdy ułamek godzin — w UI, kontekście i odpowiedziach Claude.
- Wykresy w czacie: Claude zwraca specyfikację (`wykresy` w schemacie czatu), apka sama pobiera dane i rysuje — Claude nie
- Przeplanowanie z czatu (21.11) idzie na effort medium i zmienia tylko to, czego dotyczy prośba (reszta `zostaw_id`): Antek czeka na ekranie. Planowanie automatyczne (rano, po treningu, z Plan) zostaje na high. Apka odświeża dane przez `/api/wersja` co 60 s (co 3 s, gdy trener pracuje), bez websocketów: serwer obsługuje zapytania po kolei, a odcisk kosztuje ~20 ms.
  generuje obrazków. Jeden kanał = jeden wykres (bez dwóch osi Y); znaczniki jako numery z listą opisów pod spodem.
- Trener (PWA): okno strony nigdy się nie przewija, przewija się `body` (`SKR` w app.js). Do przewijania używaj
  `SKR.scrollTo`/`SKR.scrollTop`, nie `window.scrollTo`/`scrollY`. Powód: iOS po klawiaturze zostawiał przesunięte okno
  i fixed menu wisiało w połowie ekranu.
- iOS 26 (apka z ekranu głównego): dokument nie może być niższy niż ekran, bo okno skraca się o pasek statusu (WebKit 301108) → czarny pas. Trzyma to `@media (display-mode: standalone) html { min-height: min(100lvh, calc(100% + env(safe-area-inset-top))) }` w styl.css. Nie usuwać.
- Trener, menu (19.11, Antek): Dziś · Plan · Jedzenie · Dane · Czat; historia treningów w Dane jako podzakładka.
- Tierlista ćwiczeń (19.11): trener wybiera siłkę wg tierlisty Antka z Ustawień (S/A najczęściej, wykluczonych nigdy); nowe ćwiczenia Antek ocenia po treningu.
- Animacje apki (19.11): zakładki = karuzela w stronę klikniętej zakładki, szczegóły rosną z karty i kurczą się do niej. Dane z pamięci + odświeżanie w tle, zamiast „Ładuję…”.
- 2026-11-19: trener w czacie się nie kłóci: Antek decyduje o swoim czasie; przy prośbie o zmianę trener ją robi albo
  proponuje 1–2 układy tygodnia pod dostępność (koszt w jednym zdaniu). O tym, co zaplanowane, mówi tylko na podstawie planu.
