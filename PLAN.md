# Uczę się z Claude: plan projektu i przekazanie sesji

> **Dla nowej sesji Claude:** przeczytaj cały ten plik, zanim cokolwiek zrobisz. Masz tu cel, stan na dziś,
> wszystkie ścieżki na Raspberry Pi, format danych i procedurę dodawania kartkówki krok po kroku.
> Ostatnia aktualizacja: **2026-10-19**.

---

## 1. O co chodzi

Uczeń (użytkownik, pisze po polsku) przygotowuje się z Claude do **sprawdzianów i kartkówek**. Do każdego
sprawdzianu powstaje **jedna strona HTML** z notatką, fiszkami, quizem i pytaniami otwartymi. Strony są hostowane
na jego **Raspberry Pi** i dostępne przez **Tailscale**, żeby mógł powtarzać przed lekcją (telefon i komputer).

Zasady od użytkownika:
- **Na górze listy ma być NAJBLIŻSZY termin** (zmiana 2026-10-21; wcześniej „najnowsza notatka”). Kolejność liczy się sama
  przy każdym wyświetleniu, także po zmianie daty. Bez daty → na końcu nadchodzących.
- Po wejściu w kartę widać notatkę i quiz do **tego konkretnego** sprawdzianu lub kartkówki.
- Materiały przygotowujemy **razem z użytkownikiem**, na podstawie tego, co poda (temat, strony w podręczniku,
  zdjęcia zeszytu lub podręcznika, data).
- Nowe kartkówki dodajemy **na bieżąco**, jak użytkownik dostanie je zadane.

---

## 2. Stan na 2026-10-20

| Co | Stan |
|---|---|
| Strona z listą `/strony/nauka/` | ✅ działa, sprawdzona w przeglądarce |
| Link „Nauka” w menu portalu (obok „Łazik”) | ✅ działa |
| Kafelek „Nauka: notatki i quizy” na stronie startowej portalu | ✅ pojawia się automatycznie |
| Historia: *Od kongresu wiedeńskiego do Wiosny Ludów* (Ślady czasu 3, dział 1, tematy 1–6) | ✅ na Pi, 58 fiszek, 58 pytań quizu, 14 pytań otwartych |
| Zapis postępów, archiwum, zmiana daty, wznawianie quizu | ✅ na Pi od 2026-10-20 (szczegóły w sekcji 4a) |
| Niemiecki: *Czasowniki nieregularne 1–23* (kartkówka **2026-10-28**, podręcznik s. 130, bez Präteritum) | ✅ na Pi, `niemiecki-czasowniki-nieregularne-1-23`, budowana skryptem `narzedzia/buduj_niemiecki_czasowniki.py` (dane ze zdjęcia strony); Tabela z zasłanianiem, „Wpisz” (Licz z odpowiedziami tekstowymi), 48 fiszek, 81 pytań. Typ „kartkówka” przyjęty bez potwierdzenia |
| Zakładka „Najważniejsze” | ✅ na wszystkich 4 stronach, pierwsza i domyślnie otwarta |
| Data sprawdzianu z historii | ✅ **2026-10-20**, cały dział: tematy 1–6 (użytkownik potwierdził, że temat 4 też obowiązuje, mimo że dziennik podawał 1, 2, 3, 5, 6) |
| Fizyka: *Siły, pole i napięcie elektryczne* (kartkówka **2026-10-23**) | ✅ na Pi, 34 fiszki, 35 pytań quizu, 11 zadań, zakładka „Wzory” zamiast osi czasu. Treść z typowego programu liceum (bez zdjęć od użytkownika) |
| Matematyka: *Wielomiany* (sprawdzian **2026-10-23**) | ✅ na Pi, `matematyka-wielomiany`, 33 fiszki, 40 pytań, 13 zadań, rachunki sprawdzone w sympy |
| Montaż urządzeń mechatronicznych: *Pomiary w układach elektropneumatycznych i elektrohydraulicznych* (kartkówka **2026-10-26**, grupa 3 KL-1/2) | ✅ na Pi, `montaz-pomiary-pneumatyka-hydraulika`, 38 fiszek, 38 pytań, 14 zadań. Wiedza podręcznikowa, bez notatek nauczyciela |
| Angielski: *Impulse 3 Unit 3 „Mysteries”* (sprawdzian **2026-10-22**) | ✅ na Pi, `angielski-impulse3-unit3`, z PDF podręcznika (s. 39–53, wordlist z tłumaczeniami): 142 fiszki z przełącznikiem EN↔PL, 66 pytań, 22 ćwiczenia |
| Polski: wiersz na pamięć, Tetmajer *„Lubię, kiedy kobieta…”* (**2026-10-27**) | ✅ na Pi, `polski-tetmajer-lubie-kiedy-kobieta`: nauka na pamięć (5 poziomów), wpisywanie wersów, quiz 28. ⚠️ Tekst z pamięci Claude, **niesprawdzony z podręcznikiem (str. 90)** — poproś o zdjęcie i porównaj |
| Edukacja obywatelska: *Masz wpływ 1*, dział 5 „Prawo i prawa człowieka”, tematy 1–5 (sprawdzian **2026-11-12**) | ✅ na Pi, `edukacja-obywatelska-dzial-5`, z PDF podręcznika (s. 187–218): 45 fiszek, 57 pytań, 20 pytań otwartych. Temat 4 oznaczony w podręczniku „F” (fakultatywny) — uwzględniony, do potwierdzenia u nauczyciela |
| Zawodowe: ASTORINO Web Lab od nauczyciela (`/strony/zawodowe/`) | ✅ od 2026-10-22, plik z NAS `Raspberry/Zawodowe/` (nowa wersja: podmień plik, bez Claude) |
| Budziki z porannym przeglądem, Mobidziennik (odczyt co 10 min), poczta (czeka na hasła) | ✅ od 2026-10-22 (`SERWER.md`) |
| Claude w bocie: pełny terminal, sudo tylko po „Tak” Antka | ✅ od 2026-10-22 (`SERWER.md`, sekcja bota) |
| Strona „⚙️ Automatyczne” (zadania, sprawdziany, budziki, Mobidziennik, poczta, komunikacja ZTM) | ✅ od 2026-10-22, `/strony/automatyczne/` |
| Zadania (todo) w bocie Telegram i w czacie Linphone | ✅ od 2026-10-22 (przypomnienia z terminem domyślnie dzwonią, „napisz” = tylko wiadomość; numer/szczegóły wysyłane w chwili, gdy Pi o nich mówi): dodawanie, lista, przypomnienia w obu, archiwum po 24 h, „📞 Bardzo ważne” = telefon, „zrobione / +15 / +1h / +jutro” w Linphone (szczegóły w `SERWER.md`) |
| Kopie zapasowe na NAS (172.23.0.28, `Tony-Folder/Raspberry/`) | ✅ od 2026-10-22: logi i zdjęcia Progres od razu na NAS, cały system co noc o 02:00 (szczegóły w `SERWER.md`). Postępy nauki (`dane/nauka/`) i strony są w nocnej kopii |

Kalendarz sprawdzianów użytkownik wkleja jako zrzut z dziennika (Librus: „najbliższe sprawdziany”). Klasa 3 KL, technikum, zawód technik robotyk.

Oryginał strony z historii to artefakt claude.ai (własność użytkownika):
https://claude.ai/artifact/MsSRDaCEaYUd7QgTyvJuqA
Kopia na Pi różni się od oryginału tylko dwiema rzeczami: ma link „← Wszystkie notatki” i używa klucza localStorage
`nauka:historia-3-dzial-1:best_…`.

---

## 3. Następne kroki (kolejka)

1. Zapytaj o **datę sprawdzianu z historii** i wpisz ją do `sprawdziany.json` (`"data": "RRRR-MM-DD"`).
2. Zapytaj, **jakie kartkówki/sprawdziany czekają** użytkownika. Dla każdego zbierz:
   przedmiot, typ (sprawdzian/kartkówka), zakres (tematy, strony w podręczniku), datę, materiały (zdjęcia, notatki).
3. Dla każdej pozycji: przygotuj stronę (sekcja 6), pokaż użytkownikowi, popraw razem z nim, wrzuć na Pi.
4. Po każdej zmianie zaktualizuj **sekcję 2** tego pliku (stan) i dopisz wpis do **sekcji 9** (dziennik).

Pomysły na później (tylko jeśli użytkownik zechce): tryb „powtórka błędnych” zapamiętany między wizytami,
wspólna strona z ostatnimi wynikami, wydruk notatki do PDF.

---

## 4. Raspberry Pi: dostęp i ścieżki

| Co | Wartość |
|---|---|
| Adres Tailscale | `100.108.241.58` (MagicDNS: `raspberrypi.tail52831c.ts.net`) |
| SSH | `ssh tonyg@100.108.241.58`, sudo bez hasła. Port 22 na Tailscale to **Tailscale SSH w trybie „check”**: czasem trzeba, żeby użytkownik zatwierdził link `login.tailscale.com/a/...` |
| Portal (strona główna) | http://100.108.241.58/ , tylko przez Tailscale, z LAN celowo niedostępny |
| **Strona Nauka** | **http://100.108.241.58/strony/nauka/** |
| Folder strony na Pi | `/home/tonyg/portal/sites/nauka/` |
| Lista (strona) | `/home/tonyg/portal/sites/nauka/index.html` |
| **Spis sprawdzianów** | `/home/tonyg/portal/sites/nauka/sprawdziany.json` |
| Kafelek na portalu | `/home/tonyg/portal/sites/nauka/site.json` |
| Jeden sprawdzian | `/home/tonyg/portal/sites/nauka/<id>/index.html` |
| Aplikacja portalu | `/home/tonyg/portal/app.py` (Flask, usługa `home-portal.service`, port 80) |
| Backup portalu sprzed zmian | `/home/tonyg/portal/app.py.bak_2026-10-19_nauka` |
| Pełny dokument o Pi (lokalnie na PC) | `C:\Users\tonyg\Documents\claude kopia\serwer-minecraft-bedrock-raspberry-pi.md`, sekcja 9 |
| Kopia strony w tym folderze | `nauka-z-claude/strona/` (stan z 2026-10-19, ten sam co na Pi) |

**Nowe pliki w `sites/nauka/` działają od razu, bez restartu portalu.** Restart (`sudo systemctl restart home-portal`)
jest potrzebny tylko po zmianie `app.py`.

Co zmieniono w `app.py` dla tego projektu:
- w `<nav>` linki `/strony/lazik/` „Łazik” i `/strony/nauka/` „Nauka”,
- w `site_files()` obsługa podfolderów: `/strony/x/sub/` podaje `sub/index.html`, a `/strony/x/sub` przekierowuje 302
  na wersję z ukośnikiem. `..` dalej daje 404 (sprawdzone).
- (2026-10-20) API nauki: `/api/nauka/postep` (GET wszystkie), `/api/nauka/postep/<id>` (GET, POST z `op`:
  `fiszka`, `zeruj_fiszki`, `quiz`, `ile`), `/api/nauka/data/<id>` (POST `{"data":"RRRR-MM-DD"|null}`, zapisuje
  `sprawdziany.json` w miejscu). Limit 64 KB, walidacja id/daty, zapis atomowy z blokadą.
  Kopia aktualnego `app.py` jest w repo: `pi/app.py` (poprzednia: `pi/app.py.przed_postepami`).
  Backup na Pi: `app.py.bak_2026-10-20_postep`, strona: `~/portal/nauka.bak_2026-10-20_postep.tgz`.

### 4a. Postępy, archiwum i zmiana daty (od 2026-10-20)
- **Postępy na Pi:** `~/portal/dane/nauka/<id>.json` (`fiszki` klucz `"nrTematu|przód"` → 1 umiem / 0 jeszcze nie,
  `quizy` lista wyników, `bledne` tekst pytania → licznik, `ile` liczba fiszek i pytań). Wspólne dla wszystkich urządzeń.
- **`strona/postep.js`** (wspólny skrypt, ładowany `../postep.js`) + każda strona ma `<html data-nauka="<id>">`.
- **Nowa strona MUSI być podłączona:** `python3 narzedzia/dodaj_postep.py <id>` (z katalogu repo). Dodaje zapis fiszek,
  historię wyników, „Powtórz pytania, w których się myliłeś” oraz **wznawianie** przerwanego quizu i ostatniej zakładki
  po przeładowaniu (localStorage, na danym urządzeniu). Wymaga standardowego kodu fiszek/quizu z szablonu.
- **Lista:** zakładki „Nadchodzące” / „Archiwalne” (data < dzisiaj → archiwum, sort malejąco po dacie), przy karcie
  postępy i przycisk „📅 zmień datę”.
- **Ważne i przełącznik „Najpierw ważne”** (od 2026-10-21): gwiazdka na karcie → `POST /api/nauka/wazne/<id>`
  `{"wazne":bool}` (pole `"wazne": true` w `sprawdziany.json`, usuwane przy false). Przełącznik (styl iOS, zielony/szary)
  → `/api/nauka/ustawienia` `{"najpierw_wazne":bool}`, plik `~/portal/dane/nauka-ustawienia.json`. Włączony: ważne na
  górze wg daty, potem reszta wg daty; wyłączony: sama data. Dotyczy zakładki „Nadchodzące”.
- **Zakładka „Licz”** (zadania rachunkowe z losowymi liczbami): silnik `strona/licz.js`, generatory
  `narzedzia/licz/<id>.js` → instalacja `python3 narzedzia/dodaj_licz.py <id>` (kopiuje do `strona/<id>/licz-zadania.js`,
  dodaje zakładkę po „Wzory”). Generator: `{id, temat, nazwa, gen()}` → `{tresc, pola:[{etykieta, jednostka, odp, tol,
  rodzaj}], rozw:[kroki]}`. Seria 10 zadań → `Postep.quiz` z filtrem „Licz: …”; przerwana seria wraca po przeładowaniu.
  Na razie: fizyka (12 typów) i matematyka (10 typów). **Przy nowych przedmiotach ścisłych dodawaj „Licz”** i sprawdzaj
  generatory testem (np. 2000 losowań na typ, odpowiedź przeliczona niezależnie).
- ⚠️ **Użytkownik sam zmienia daty na Pi.** Przed każdą edycją `sprawdziany.json` najpierw pobierz go z Pi
  (`scp pi:/home/tonyg/portal/sites/nauka/sprawdziany.json strona/`), dopiero potem dopisuj i wgrywaj. Inaczej nadpiszesz
  jego zmiany dat.

### ⚠️ Czego NIE ruszać
Na tym Pi działa **serwer Minecraft, na którym grają znajomi** (`powernukkitx`, `playit`, `pi-dashboard`).
Ten projekt dotyczy **tylko** `~/portal/sites/nauka/` i ewentualnie `app.py` portalu. Nie restartuj innych usług
i nie rób rebootu. Po zmianie sprawdź: `systemctl is-active home-portal powernukkitx playit pi-dashboard`.

### Sesja w chmurze a Pi
Projekt mieszka w repozytorium GitHub `TangySpider4453/repozytorium` (`PLAN.md` + `strona/`), żeby można było pracować
z iPada przez Claude Code w chmurze. Kopia w `strona/` ma być zawsze taka sama jak na Pi.

**Automatycznie:** hook `.claude/hooks/session-start.sh` (zgoda użytkownika 2026-10-19) na starcie sesji instaluje
Tailscale + SSH, ustawia alias `ssh pi` i łączy kluczem z sekretu środowiska `TS_AUTHKEY`. Sprawdź: `tailscale status`,
`ssh pi hostname`. Jeśli nie ma klucza albo SSH wypisze link „check”, zrób to ręcznie jak niżej.

Sesja w chmurze **może** dosięgnąć Pi, jeśli dołączy do tailnetu (sprawdzone 2026-10-19):
1. Pobierz statyczne binarki `https://pkgs.tailscale.com/stable/tailscale_latest_amd64.tgz`, uruchom
   `tailscaled --tun=userspace-networking --state=mem:` i `tailscale up --authkey=… --hostname=claude-cloud`.
   Klucz podaje użytkownik (najlepiej jako sekret środowiska `TS_AUTHKEY`). **Nigdy nie zapisuj klucza w repo.**
2. SSH przez `ProxyCommand tailscale nc %h %p` jako `tonyg@raspberrypi`, z `ControlMaster`/`ControlPersist`.
3. Jeśli ACL ma tryb „check”, SSH wypisze link `login.tailscale.com/a/...`; podaj go użytkownikowi (wygasa po kilku
   minutach). Po zatwierdzeniu połączenie z ControlPersist trzyma się godzinami.

Gdy nie ma klucza albo Tailscale nie działa, w chmurze przygotuj i popraw pliki w `strona/`. Wrzucenie na Pi zrobi:
- sesja Claude na komputerze użytkownika (ma SSH przez Tailscale), poleceniami z sekcji 7, albo
- sam użytkownik: skopiuje folder przez udział Samba `\\100.108.241.58\tonyg` do `portal\sites\nauka\`.

Gdy pliki są gotowe, powiedz użytkownikowi wprost, że trzeba je jeszcze wgrać na Pi i jak to zrobić.

---

## 5. Format `sprawdziany.json`

Tablica obiektów. Przykład (stan obecny):

```json
[
  {
    "id": "historia-3-dzial-1",
    "folder": "historia-3-dzial-1",
    "przedmiot": "Historia",
    "typ": "sprawdzian",
    "tytul": "Od kongresu wiedeńskiego do Wiosny Ludów",
    "opis": "Ślady czasu 3, dział 1, tematy 1–6: ...",
    "data": null,
    "dodano": "2026-10-19",
    "zawiera": ["notatka", "oś czasu", "58 fiszek", "58 pytań quizu", "14 pytań otwartych"]
  }
]
```

| Pole | Znaczenie |
|---|---|
| `id` | unikalny, małe litery, cyfry, `-`; używany w kluczu localStorage |
| `folder` | nazwa podfolderu (`[a-z0-9_-]`, najlepiej taka sama jak `id`) |
| `przedmiot` | np. „Historia”, „Biologia”. Kolor karty i filtr są liczone z przedmiotu automatycznie |
| `typ` | `sprawdzian` albo `kartkówka` |
| `data` | dzień sprawdzianu `RRRR-MM-DD` albo `null` („data jeszcze nieznana”) |
| `dodano` | data dodania notatki `RRRR-MM-DD`. Lista sortuje się po `data` (najbliższy na górze); `dodano` rozstrzyga tylko remis i kolejność wpisów bez daty. Daje też etykietę „nowe” przez 3 dni |
| `zawiera` | krótkie etykiety pod kartą |

Lista sama pokazuje odliczanie (dzisiaj, jutro, za N dni), wyszarza minione sprawdziany, daje etykietę „nowe” przez
3 dni po `dodano` i pokazuje najlepszy wynik quizu z localStorage.

Sprawdź JSON przed wgraniem: `python -c "import json;json.load(open('sprawdziany.json',encoding='utf-8'))"`.

---

## 6. Jak przygotować stronę sprawdzianu

**Szablon:** najlepiej `strona/fizyka-pole-elektryczne/index.html` (ma już zakładkę „Najważniejsze”, wzory, `COL`, `lining-nums`; historia też działa). Skopiuj go i podmień treść. Jeden plik HTML, bez zewnętrznych
skryptów, jedynie fonty z Google Fonts. Działa na telefonie, ma tryb jasny i ciemny.

Zakładki i dane w skrypcie:
- **Notatka**: HTML w `<section id="notatka">`, artykuł na temat (`<article class="topic" style="--c:var(--t1)">`),
  klasy `.box`, `.grid2`, `.tablewrap`, `dl.terms`, `.warn` („Uważaj:” na typowe pomyłki).
- **Oś czasu**: tablica `TL` = `[nrTematu, "data", "wydarzenie", "dopisek?"]`. Dla przedmiotów bez dat usuń zakładkę
  (przycisk w `nav.tabs` i sekcję) albo zamień ją na np. „Wzory”.
- **Fiszki**: `FC` = `[nrTematu, "przód", "tył"]`.
- **Quiz**: `Q` = `[nrTematu, "pytanie", ["poprawna", "zła", "zła", "zła"], 0, "wyjaśnienie"]`. Poprawna jest zawsze
  na indeksie 0, kolejność odpowiedzi tasuje skrypt.
- **Pytania otwarte**: `OQ` = `[nrTematu, "polecenie", ["punkt odpowiedzi", ...]]`.
- `T` = nazwy tematów (maks. 6, kolory `--t1`…`--t6`). Przy innej liczbie tematów popraw też pętlę w `makeFilters`
  (`for(let i=1;i<=6;i++)`) i paski w „ribbon” (sekcja na górze notatki).

**⭐ Zakładka „Najważniejsze” — OBOWIĄZKOWA w każdej stronie (prośba użytkownika, „to najważniejsze”).**
Pierwsza w `nav.tabs`, otwarta domyślnie (`notatka` ma wtedy `hidden`). Zawiera: ramkę „Jeśli zapamiętasz tylko tyle”
(3 najważniejsze rzeczy z całego zagadnienia) i po jednej karcie `.key` na temat z 4–5 kluczowymi punktami.
Wszystko musi się zgadzać z notatką. Gotowe narzędzie: `narzedzia/dodaj_najwazniejsze.py <tresc.json> <id>...`
(wzór treści: `narzedzia/najwazniejsze_tresc.json`); jeśli kopiujesz stronę, która ma już tę zakładkę, tylko podmień treść.

**Pozostałe rzeczy obowiązkowe w każdej nowej stronie:**
1. Link powrotu zaraz po `<header class="top"><div class="wrap">`:
   `<a href="../" style="display:inline-block;font-size:14px;opacity:.75;text-decoration:none;margin-bottom:8px">← Wszystkie notatki</a>`
2. Klucz wyniku quizu: `"nauka:<id>:best_"+qFilter` (w `getItem` i `setItem`). Lista czyta `nauka:<id>:best_all`.
   Bez tego wyniki różnych sprawdzianów nadpisywałyby się nawzajem.

**Jakość treści:**
- Opieraj się na materiałach użytkownika (zdjęcia zeszytu i podręcznika, zakres od nauczyciela). Niczego nie zmyślaj.
  Gdy czegoś nie widać na zdjęciu, zapytaj.
- Pisz prostym polskim. W notatce sekcja „Uważaj” z typowymi pomyłkami, w quizie złe odpowiedzi wiarygodne, a nie absurdalne.
- Po napisaniu przeklikaj quiz i sprawdź, czy poprawne odpowiedzi są prawdziwe.
- Pokaż użytkownikowi gotową stronę (np. jako artefakt claude.ai) i popraw, zanim pójdzie na Pi.

---

## 7. Procedura: dodanie nowej kartkówki (lokalnie, z SSH)

> **Strony dodane przez bota Telegram (od 2026-10-22):** Claude na Pi może sam dodać zagadnienie (ze zdjęć/PDF
> przysłanych w Telegramie). Zapisuje je wtedy w `~/portal/sites/nauka/DODANE_PRZEZ_BOTA.txt`. **Na początku każdej
> sesji** sprawdź ten plik i skopiuj nowe foldery oraz `sprawdziany.json` z Pi do `strona/` (żeby repo było jak Pi).

```bash
# 0. pobierz aktualny spis z Pi (użytkownik mógł zmienić daty): scp pi:/home/tonyg/portal/sites/nauka/sprawdziany.json strona/
# 0b. po zbudowaniu strony: python3 narzedzia/dodaj_postep.py <id>
# 1. przygotuj lokalnie: nauka-z-claude/strona/<id>/index.html + nowy wpis w strona/sprawdziany.json
# 2. wgraj na Pi (z folderu nauka-z-claude)
scp -r strona/<id> tonyg@100.108.241.58:/home/tonyg/portal/sites/nauka/
scp strona/sprawdziany.json tonyg@100.108.241.58:/home/tonyg/portal/sites/nauka/
# 3. sprawdź (oba muszą dać 200)
ssh tonyg@100.108.241.58 'for u in /strony/nauka/ /strony/nauka/<id>/; do curl -s -o /dev/null -w "%{http_code} $u\n" http://100.108.241.58$u; done'
```

4. Otwórz http://100.108.241.58/strony/nauka/ w przeglądarce: nowa karta ma być na górze, a po kliknięciu ma działać.
5. Zaktualizuj sekcję 2 i 9 tego pliku oraz sekcję 9 dokumentu o Pi.

Pułapki na Windows: PowerShell psuje cudzysłowy w złożonych poleceniach `ssh '...'`. Używaj narzędzia Bash (Git Bash)
albo wgraj skrypt przez `scp` i uruchom go na Pi. Nie przesyłaj plików przez potok w PowerShell, bo dokleja BOM.

---

## 8. Szybka ściąga dla użytkownika

- Nauka: **http://100.108.241.58/strony/nauka/** (Tailscale musi być włączony na telefonie lub komputerze)
- Albo: portal http://100.108.241.58/ → zakładka **Nauka**
- Nowa kartkówka: napisz Claude przedmiot, zakres, datę i wrzuć zdjęcia notatek lub podręcznika.

---

## 9. Dziennik zmian

- **2026-10-19**: Utworzono stronę Nauka na Pi (`~/portal/sites/nauka/`), lista z sortowaniem po `dodano`, odliczaniem
  i wynikami quizu. Dodano pierwszy materiał: Historia, dział 1 (kopia artefaktu). W portalu: linki Łazik/Nauka
  w menu i obsługa `index.html` w podfolderach. Wszystko sprawdzone (HTTP 200, przeglądarka). Usługi Minecraft
  działały bez przerwy. Utworzono ten plik i kopię strony w `nauka-z-claude/strona/`.
- **2026-10-19 (chmura)**: Projekt przeniesiony do repozytorium GitHub; sesja w chmurze połączona z Pi przez Tailscale
  (userspace + SSH z zatwierdzeniem „check”). Dodano kartkówkę z fizyki `fizyka-pole-elektryczne` (data 2026-10-23):
  notatka (3 tematy), wzory, 34 fiszki, 35 pytań quizu, 11 zadań. Przetestowano w przeglądarce (quiz, zapis wyniku,
  lista), wgrano na Pi, HTTP 200 dla listy i strony. Backup: `sprawdziany.json.bak_2026-10-19_fizyka` na Pi.
  Usługi Minecraft bez zmian.
- **2026-10-19 (chmura, 2)**: Z kalendarza: historia ma datę 2026-10-20 i zakres bez tematu 4 (ramka + filtr „spr”).
  Dodano matematykę (wielomiany) i montaż (pomiary pneumatyka/hydraulika). W nowych stronach `font-variant-numeric:
  lining-nums`, bo Alegreya ma cyfry nautyczne (0 wyglądało jak „o”). Wszystko na Pi, HTTP 200, usługi Minecraft bez zmian.
- **2026-10-19 (chmura, 3)**: Na prośbę użytkownika dodano zakładkę „Najważniejsze” (pierwsza, domyślna) do wszystkich
  stron i wpisano ją jako obowiązkową w sekcji 6. Narzędzie w `narzedzia/`. Backup na Pi: `*/index.html.bak_przed_najwazniejsze`.
  Uwaga techniczna: `tailscaled` w kontenerze potrafi się wyłączyć; restart z tym samym `--state` przywraca połączenie bez klucza.
- **2026-10-19 (chmura, 4)**: Z PDF-ów od użytkownika dodano angielski (Impulse 3 Unit 3) i edukację obywatelską
  (Masz wpływ 1, dział 5), plus polski: wiersz Tetmajera do nauki na pamięć (tekst z pamięci, do weryfikacji).
  Wszystkie 7 stron na Pi z zakładką „Najważniejsze”, HTTP 200, usługi Minecraft bez zmian.
  Backup: `sprawdziany.json.bak_2026-10-19_ang-pol-edo`. PDF-y podręczników nie są w repo (tylko w uploadach sesji).
- **2026-10-20**: Historia: temat 4 jednak obowiązuje — usunięto ramkę zakresu, wyszarzenie i filtr „spr”, dodano kartę
  tematu 4 w „Najważniejsze”. Wgrane na Pi po ponownym zatwierdzeniu „check” (minęło 12 h). Backup `*.bak_2026-10-20`.
- **2026-10-20 (2)**: Zapis postępów na Pi (fiszki umiem/jeszcze nie, wyniki quizów, błędne pytania), zakładka
  „Archiwalne”, zmiana daty z listy, wznawianie przerwanego quizu i ostatniej zakładki. Nowe API w `app.py` (za zgodą
  użytkownika), restart tylko `home-portal`; portal i usługi Minecraft `active`. Test end-to-end na kopii portalu
  (2 „urządzenia”, archiwum, zmiana daty) i test API na Pi. Format `sprawdziany.json` po zapisie przez API bez zmian.
- **2026-10-20 (3)**: Fiszki zapisywały się poprawnie, ale licznik „umiesz” liczył tylko bieżące podejście, więc po
  odświeżeniu wyglądało to jak reset. Dodano panel „Zapamiętane na stałe” (umiesz / do powtórki / nowe, pasek) i etykietę
  stanu na karcie. Postępy w `dane/nauka/` zostają na zawsze, także dla sprawdzianów w archiwum.
- **2026-10-20 (4)**: Zakładka „Licz” w fizyce i matematyce: zadania z losowymi liczbami, sprawdzanie wyniku (przecinek,
  10ⁿ, e-notacja, ułamki, zbiory pierwiastków), rozwiązanie krok po kroku (w matmie z tabelą Hornera), serie po 10
  zapisywane w wynikach, wznawianie po przeładowaniu. 22 generatory × 2000 losowań sprawdzone automatycznie.
- **2026-10-21**: Niemiecki: czasowniki nieregularne 1–23 ze zdjęcia s. 130. `licz.js` obsługuje odpowiedzi tekstowe
  (`rodzaj:"tekst"`), `dodaj_licz.py` bierze nazwę zakładki z generatora. Wgrane po zatwierdzeniu „check”; spis pobrany
  z Pi i tylko uzupełniony (daty użytkownika bez zmian). Backup `*.bak_2026-10-21*`.
- **2026-10-21 (2)**: Lista „Nadchodzące” sortuje się po dacie (najbliższy termin na górze, bez daty na końcu), liczone
  przy każdym rysowaniu, więc zmiana daty od razu przestawia kartę. Archiwum: najświeższy termin na górze.
- **2026-10-21 (3)**: Gwiazdka „ważne” na kartach i przełącznik „Najpierw ważne” (nowe API w `app.py`, restart tylko
  `home-portal`, wszystko `active`). Backup `app.py.bak_2026-10-21_wazne`, poprzednia wersja w repo `pi/app.py.przed_waznymi`.
- **2026-10-22 (NAS)**: Pi połączone z NAS (Synology 172.23.0.28, udział Tony-Folder, poświadczenia tylko na Pi w
  `/etc/nas-credentials`). Folder `Raspberry/` z `Logi/` (zdrowie, kopia, dziennik systemu co minutę),
  `Progres-zdjecia/`, `Progres-filmy/`, `Kopia-systemu/` (cały system co noc o 02:00 + instrukcja przywracania).
  Gdy NAS niedostępny: dioda czerwona. Skrypty w `pi/nas/`, opis w `SERWER.md`. Backup `app.py.bak_2026-10-22_nas`.
- **2026-10-22 (wyłączanie)**: Komenda `raspiproszewylaczsie` do bezpiecznego wyłączenia Pi (zapis świata Minecraft,
  czekanie na kopię, logi na NAS, poweroff). Sprawdzone: wszystkie usługi i timery startują same po zaniku prądu.
- **2026-10-22 (panel)**: Panel „Kopie zapasowe i zadania w tle” (strona główna portalu i Zdrowie): stan i procenty
  kopii systemu, renderu, zdjęć na NAS, logów i aktualizacji. Pierwsza kopia systemu zrobiona (17 GB, 8,5 min),
  przyrostowa 31 s, sprawdzona: właściciele i uprawnienia zachowane. Backup `app.py.bak_2026-10-22_zadania`.
- **2026-10-22 (obciążenie)**: Raport obciążenia: przedziały CPU > 60 %, temperatura > 55 °C, RAM > 60 % z maksimum
  i głównymi procesami, logi `cpu.log`/`temperatura.log`/`ram.log` na NAS, wysuwany panel z „!” na stronie głównej
  i Zdrowie. Test na Pi (25 s obciążenia) zapisany poprawnie. Backup `app.py.bak_2026-10-22_obciazenie`.
- **2026-10-22 (zwijane)**: Panel „Kopie zapasowe i zadania w tle” też wysuwany (zwinięty: „!” przy błędzie lub braku
  NAS, niebieskie znaczniki z procentem tego, co trwa, data ostatniej kopii). Kafelki raportu poprawione w trybie ciemnym.
- **2026-10-22 (komendy)**: Na NAS `Tony-Folder/Raspberry/komendy.txt`: komendy projektu (wyłączanie, kopia, NAS, logi,
  usługi), aktualizowany automatycznie z Pi. Nowe komendy dopisywać w `pi/nas/komendy.txt`.
- **2026-10-22 (hasło)**: Portal dostępny też z sieci domowej (`http://172.23.0.20`) po zalogowaniu hasłem; ciasteczko
  na rok, Tailscale bez hasła. Komenda `portal-haslo` (zmiana hasła). Sprawdzone curl z Pi: bez hasła 302/401,
  złe hasło 401, dobre → strony, API i zdjęcia 200. Backup `app.py.bak_2026-10-22_haslo`.
- **2026-10-22 (pokaż hasło)**: Na stronie logowania przycisk „Pokaż”/„Ukryj” hasło. Wdrożone, backup `app.py.bak_2026-10-22_pokaz`.
- **2026-10-22 (hasło, poprawka)**: Hasło z iPada nie przechodziło, choć na serwerze było poprawne. Pole hasła ma teraz
  wyłączoną autokorektę i wielką literę iOS, spacje na końcu są ignorowane, a dziennik przy złym haśle podaje długość
  i podpowiedź o wielkości liter (bez samego hasła).
- **2026-10-22 (emotki)**: Menu portalu z emotkami: 🏠 Start, 🌐 Sieć, 💻 Terminal, 🚙 Łazik, 📚 Nauka, 💪 Progres,
  🩺 Zdrowie, 🚪 Wyloguj. Backup `app.py.bak_2026-10-22_emotki`.
- **2026-10-22 (bot)**: Bot Telegram @SerwerekAntek_bot (usługa `serwerek-bot`, repo `pi/bot/`): alarmy z monitora
  zdrowia, przypomnienia o sprawdzianach, przyciski (stan, kopia, restart z potwierdzeniem) i rozmowa z Claude Code
  zalogowanym subskrypcją (ograniczone narzędzia). Tokeny tylko na Pi. Szczegóły w `SERWER.md`.
- **2026-10-22 (bot 2)**: Bot: 🟡 od razu poza ciszą nocną, powiadomienia o każdym wejściu z sieci domowej (portal,
  SSH, Samba, VNC, panel MC) z IP, zdjęcia/PDF → Claude robi nową stronę w Nauce (kontrola `sprawdz_strone.js`).
- **2026-10-22 (wizyty)**: Bot śledzi wizyty z sieci domowej: od razu nowe wejście, panel logowania, przejście
  zabezpieczeń, nieudane próby i oznaki ataku; po 10 min podsumowanie ścieżki. Pełny zapis na NAS `Logi/wejscia/`
  (30 dni). Samba: zapis logowań i operacji na plikach. Naprawiony błąd, przez który powiadomienia o wejściach nie szły.
- **2026-10-22 (ścieżka)**: Bot nie wysyła podsumowań wizyt; ścieżka zapisuje się na Pi i NAS, a przycisk 🧭 Ścieżka
  pokazuje wizyty z dnia. 📊 Stan z maksimum temperatury, CPU i RAM z dziś i z 7 dni.
- **2026-10-22 (progres kg)**: Progres: tłuszcz i mięśnie przeliczane na kg, przełącznik wykresu %/kg, historia z obiema wartościami.
- **2026-10-22 (progres film)**: Film: odstęp „co miesiąc”, zdjęcie najbliższe planowanemu dniowi z tego samego miesiąca.
- **2026-10-22 (zaufane)**: Wejścia przez Tailscale i z zaufanych urządzeń (MAC) tylko zapisywane w ścieżce, bez
  powiadomień; przycisk „To moje urządzenie” i komenda `zaufane` w bocie.
- **2026-10-22 (zadania)**: Zadania z przypomnieniami: strona `/strony/todo/` (📝 w menu), API `/api/todo`, bot dodaje
  z polskiego tekstu („todo jutro 17:00 trening”), wysyła przypomnienia z przyciskami zrobione/odłóż. Repo `todo/`.
- **2026-10-22 (głos)**: Wspólna pamięć rozmów bota (SQLite), wiadomości głosowe (whisper + Piper na Pi), usługa
  telefonu SIP przez Linphone (czeka na konta Linphone), dzwonienie przy 🔴 bez reakcji i przy zadaniach „zadzwoń”.
- **2026-10-22 (Minecraft ręcznie)**: Serwer Minecraft nie startuje sam; włączanie: komenda `minecraft start`, przycisk
  na stronie głównej, 🎮 w bocie. Monitor nie traktuje wyłączenia jako awarii. Auto-aktualizacja zostawia stan.
- **2026-10-22 (MC auto)**: Minecraft wyłącza się sam po 30 min bez graczy (bot), test z limitem 2 min udany.
- **2026-10-22 (MC powiadomienia)**: Bot pisze o każdej zmianie stanu Minecrafta (włączony, wyłączony, restart, awaria,
  ktoś gra, serwer opustoszał), także gdy zmianę zrobiono na stronie albo komendą.
- **2026-10-22 (Linphone)**: Konto SIP Pi `antekserwerrpi4b@sip.linphone.org` zalogowane (rejestracja 200 OK); hasło tylko
  w `/etc/serwerek-bot/sip.env`. Czeka na adres Linphone właściciela (`SIP_WLASCICIEL`); do tego czasu Pi odrzuca
  połączenia i bot podaje adres dzwoniącego.
- **2026-10-22 (Linphone 2)**: Właściciel `sip:za_kolaz@sip.linphone.org` wpisany do `sip.env`, telefon zarejestrowany.
- **2026-10-22 (czat Linphone)**: Pisanie z Pi w aplikacji Linphone jak w Telegramie (komendy + Claude, wspólna pamięć);
  test lokalny udany. Poprawione rozpoznawanie właściciela po nazwie SIP.
- **2026-10-22 (głos/tekst)**: Bot sam wybiera głos albo tekst („przeczytaj” → głosówka, „wypisz” → tekst, inaczej jak
  pytanie). Głosówki działają też w czacie Linphone (rozpoznanie na Pi, odpowiedź głosem przez serwer plików Linphone).
- **2026-10-22 (telefon SRTP)**: Połączenia z Linphone kończyły się 488 (Linphone wymaga szyfrowania dźwięku): włączone
  SRTP opcjonalne (`srtpUse` OPTIONAL, `srtpSecureSignaling` 0). Połączenie od Pi dochodzi już do iPhone'a (push),
  test w toku. Zabezpieczone czytanie kolejki połączeń. Tymczasowo log SIP (`serwerek-telefon.service.d/diagnostyka.conf`).
- **2026-10-22 (telefon działa)**: Pierwsza prawdziwa rozmowa przez Linphone (opus, SRTP): pytanie rozpoznane, Claude
  odpowiedział po 7 s. Log diagnostyczny SIP wyłączony.
- **2026-10-22 (pomoc)**: Komenda `pomoc` / `help` w Telegramie i Linphone; w czacie Linphone komendy jak przyciski
  w Telegramie, z potwierdzeniem „tak”.
- **2026-10-22 (poprawki czatu)**: „Napisz” zawsze daje tekst; w Linphone odpowiedzi tekstem (głosówka tylko na prośbę);
  bez echa rozpoznanego tekstu; Claude może listować usługi i czytać /proc/meminfo (pojedyncze polecenia, bez potoków).
- **2026-10-22 (głosówki Linphone)**: Błąd przy pustej głosówce z Linphone (sam nagłówek .mka) obsłużony komunikatem;
  głosówki od Pi w formacie Linphone (.mka/Opus); wysłana głosówka testowa do sprawdzenia na iPhonie.
- **2026-10-22 (krótko)**: Claude w bocie/Linphone/telefonie odpowiada krótko (1–2 zdania, bez wstępów i dodatków),
  dłużej tylko na wyraźną prośbę (`instrukcja.md`).
- **2026-10-22 (czytanie)**: Wyjątek od krótkich odpowiedzi: „przeczytaj / powiedz / nagraj …” → pełna treść (`CZYTAJ_PODPOWIEDZ`).
- **2026-10-23 (szczegóły na czat)**: Głosem Pi mówi krótko, a adresy, maile, numery, kody i instrukcje krok po kroku
  wysyła na czat (na prośbę czyta szczegóły). Test: reset hasła → krótko + kroki na czacie.
- **2026-10-23 (numery w przypomnieniach)**: Zadanie z numerem telefonu: Pi dzwoni, mówi „zadzwoń na numer z czatu”
  i wysyła numer osobną wiadomością.
- **2026-10-23 (szybkie odpowiedzi o serwerze)**: Temperatura, procesor, RAM, miejsce, uptime, zasilanie, NAS, kopia,
  usługi, co obciąża, internet, lokalizacja, „czy jutro szkoła”, „za ile dni sprawdzian”, jutrzejszy dzień: bez Claude,
  0–0,4 s, we wszystkich kanałach (też przez telefon, także z przekręconą mową). Test 412/412.
- **2026-10-23 (wiedza o całym serwerze)**: `wiedza_serwer.md` obejmuje wszystkie usługi (portal, bot, telefon, Minecraft, playit,
  Tailscale, SSH/terminal/VNC, Samba, NAS, kopia, Mobidziennik, poczta, lokalizacja, ZTM, budziki, Progres) i system (karta,
  RAM, temperatura, zasilanie, aktualizacje); więcej słów kieruje do Sonneta.
- **2026-10-23 (szybszy i mądrzejszy Claude)**: Dwa stałe procesy Claude (Haiku low do prostych, Sonnet medium do
  trudnych i awarii; Haiku sam przekazuje trudne), ściąga diagnozy i napraw serwera, potwierdzanie akcji głosem w rozmowie,
  szybsze rozpoznawanie mowy. Test na Pi: proste odpowiedzi 1–2 s, przekręcona mowa („do nas” = NAS) rozumiana.
- **2026-10-23 (zdalne)**: W menu „🖥️ Zdalne” = terminal + pulpit VNC w przeglądarce, oba za hasłem Linuksa
  (sprawdzone: złe hasło odrzucone, bez biletu brak połączenia, z biletem pulpit 1920x1080). Progres: kadr na ręce
  działa zawsze dla zdjęć biceps / tył+biceps (wcześniej tylko z przełącznikiem „same ręce”).
- **2026-10-23 (pauzy w rozmowie)**: W rozmowie telefonicznej koniec wypowiedzi dopiero po 3 s ciszy (`PAUZA_KONIEC`,
  było 0,9 s), wypowiedź do 60 s; końcowa cisza obcinana przed rozpoznaniem. Progres: kadr na ręce w trybie „Same ręce”.
- **2026-10-23 (szybkie odpowiedzi)**: Typowe pytania (o której zaczynam, sprawdziany, zastępstwa, zadania, budzik,
  serwer, autobus…) bot odpowiada sam z danych w ułamku sekundy, bez Claude; Claude oznacza rozpoznane pytania, a bot uczy
  się nowych sformułowań. Test 308/308. Budzik 6:15 zadziałał (603 → ponowienie, potem 486 i kolejna próba po 5 min).
- **2026-10-22 (zadania w planie)**: Zadania domowe widać też w planie lekcji (przy lekcji, na którą są), z pełną treścią.
- **2026-10-22 (strony Mobidziennik i Budziki)**: `/strony/mobi/` pokazuje wszystko odczytane z dziennika (cały plan
  z zastępstwami, sprawdziany, zadania, „Sprawdź teraz”); `/strony/budziki/` do ustawiania budzików klikając
  (sprawdzone w przeglądarce: dodanie, wyłączenie, usunięcie).
- **2026-10-22 (budziki, Mobidziennik, poczta)**: Budziki (Pi dzwoni z porannym przeglądem, 3 próby; pierwszy na
  23.10 6:15), Mobidziennik co 10 min tylko do odczytu (plan, zastępstwa, odwołane, sprawdziany, zadania domowe; nowy
  sprawdzian → strona w Nauce i sesje nauki albo prośba o materiały), poczta (kod gotowy, czeka na 4 hasła do aplikacji),
  2,5 s ciszy po odebraniu, karty na „Automatyczne”. Sprawdzone na Pi: logowanie i odczyt Mobidziennika, poranny
  przegląd przez Claude (ok. 6 s), Claude do maili naprawdę bez narzędzi.
- **2026-10-22 (lokalizacja jednorazowa)**: Na razie lokalizacja jednorazowo z Telegrama (📍); żółty alarm o braku
  lokalizacji włącza się dopiero, gdy będą ciasteczka Google.
- **2026-10-22 (lokalizacja z Google Maps)**: Pi samo co 15 min odczytuje lokalizację udostępnioną w Google Maps
  drugiemu kontu Google (bez VPN i bez Telegrama na iPhonie); czeka na ciasteczka tego konta (NAS Raspberry/Google).
- **2026-10-22 (jeden kanał)**: Bot odpowiada tylko tam, gdzie Antek napisał; powiadomienia idą na Linphone (albo do
  Telegrama, gdy tam ostatnio pisał lub gdy Linphone nie działa), bez dublowania.
- **2026-10-22 (miejsca słowami)**: „ustaw tu jako dom/szkoła/…” w Telegramie, Linphone i przez telefon zapisuje
  obecną lokalizację jako miejsce (też z adresem i usuwanie).
- **2026-10-22 (pilnowanie lokalizacji)**: 🟡 w monitorze, gdy w dzień lokalizacja starsza niż 30 min (poza
  lokalizacją „na żywo” z Telegrama).
- **2026-10-22 (komunikacja ZTM)**: Odjazdy i trasy ZTM Poznań z opóźnieniami na żywo (`ztm.py` w portalu), lokalizacja
  z Telegrama (📍), OwnTracks albo skrótu iOS, miejsca („dom”); bot, Linphone, Claude i strona `/strony/komunikacja/`.
  Sprawdzone na Pi: odjazdy z Junikowa, trasy, zapis miejsca z adresu.
- **2026-10-22 (automatyczne)**: Nowa strona „⚙️ Automatyczne” (zamiast „Zadania” w menu): zadania, sprawdziany, miejsca
  na pocztę i komunikację miejską (wkrótce).
- **2026-10-22 (5 s ciszy)**: Gdy Pi dzwoni, po odebraniu czeka 5 s (`CZEKAJ_PO_ODEBRANIU`), żeby zdążyć włączyć głośnomówiący.
- **2026-10-22 (odhaczanie głosem)**: Na stronie Zadania: „do archiwum za …” przy zrobionych i karta sprawdzianów
  i kartkówek; sprawdziany też w liście „zadania” bota i w przypomnieniach na Linphone; w rozmowie z przypomnienia
  „odhaczone / zrobione” odhacza zadanie.
- **2026-10-22 (bez formułki)**: Pi nie kończy wypowiedzi przez telefon formułką „jeśli chcesz coś powiedzieć…”; po niej po prostu słucha.
- **2026-10-22 (głos w przypomnieniach)**: Naprawiona cisza w połączeniach od Pi (nowy port mediów po UPDATE). Claude
  przygotowuje wypowiedź ok. 4 min przed terminem, synteza zaczyna się przy dzwonieniu; po powitaniu można rozmawiać.
- **2026-10-22 (minuta dzwonienia)**: Pi dzwoni do 60 s; gdy iPhone od razu odrzuca (603, gdy Linphone jest otwarty),
  ponawia co ok. 5 s do minuty. Test: połączenie odebrane.
- **2026-10-22 (todo: archiwum i ważne)**: Zrobione zadania po 24 h przechodzą do „Archiwum” na stronie; „📞 Bardzo
  ważne: zadzwoń” (strona, Telegram, Linphone „ważne [nr]”, słowa „ważne/pilne” w „todo …”) = Pi dzwoni o terminie.
- **2026-10-22 (zawodowe)**: Strona „🤖 Zawodowe” z programem nauczyciela (ASTORINO Web Lab); portal pokazuje najnowszy
  `.html` z NAS `Raspberry/Zawodowe/` i trzyma kopię na Pi. Sprawdzone: podmiana pliku na NAS od razu zmienia stronę.
- **2026-10-22 (dzwonienie od Pi)**: Przypomnienie z telefonem nie dzwoniło (iPhone: „Anonymous”, odrzucone po 4 s,
  603 Decline). Poprawka: SRTP wymagane przy połączeniach (RTP/SAVP) i nazwa „Serwer Rpi” w nadawcy; test: połączenie
  od Pi odebrane (CONFIRMED).
- **2026-10-22 (pełny terminal bota)**: Claude w bocie ma pełny Bash (potoki, skrypty, edycja plików); sudo tylko za
  zgodą Antka: znacznik `[[SUDO: …]]` → przycisk „Tak” / „tak” w Linphone (Claude sam sudo nie uruchomi: `setpriv
  --no-new-privs` + strażnik `~/bot/straznik.py`). Sprawdzone na Pi: potok działa, bezpośrednie sudo zablokowane,
  zatwierdzone polecenie uruchamia się raz.
- **2026-10-22 (todo w Linphone)**: Zadania działają w czacie Linphone jak w Telegramie: przypomnienia przychodzą też na
  Linphone (`do_linphone`), odpowiedź „zrobione”, „+15”, „+1h”, „+jutro” (opcjonalnie z numerem z listy), „usuń <nr>”,
  „cofnij”; „todo … zadzwoń” działa też tutaj (`nowe_zadanie` wspólne dla obu kanałów). Sprawdzone na Pi.
- **2026-10-23 (wiadomość w chwili mówienia, domyślne dzwonienie)**: Pi wysyła numer/szczegóły na czat w momencie, gdy
  mówi „wysyłam Ci teraz wiadomość…”, a przy nieodebranym połączeniu dołącza je do „Dzwoniłem, ale nie odebrałeś”.
  Przypomnienia z terminem domyślnie dzwonią; same wiadomości tylko po „napisz / wiadomością / bez dzwonienia”.
  Wdrożenie przerwało rozmowę o 20:56, więc restarty idą teraz przez `~/bot/bez_rozmowy.sh` (czeka na koniec rozmowy).
- **2026-10-23 (diagnoza ciszy w rozmowie)**: Trzy połączenia od Pi (20:56, 21:00, 21:05) bez dźwięku w słuchawce, choć
  synteza działa. Telefon loguje teraz stan mediów, odtwarzanie i brak mediów (`mówię …`, `media …`, `graj: …`). Czeka na
  połączenie testowe.
- **2026-10-23 („dzwoń” od razu)**: „dzwoń / zadzwoń / dzwoń asap / możesz zadzwonić?” w Linphone i Telegramie dzwonią od
  razu bez Claude (wcześniej „Dzwoń” szło przez Claude i połączenie przyszło po minucie). Cisza w rozmowach: w obie strony
  nie płynie dźwięk (nagranie same zera), włączony pełny zapis SIP, czeka na połączenie testowe.
- **2026-10-23 (przyczyna ciszy)**: Pi wysyła dźwięk, iPhone go odbiera (raporty RTCP bez strat), ale nie gra i nie
  wysyła mikrofonu. Zaczęło się po restarcie telefonu w trakcie rozmowy o 20:57 (brak rozłączenia). Telefon.py rozłącza
  teraz rozmowy przy zatrzymaniu usługi.
- **2026-10-23 (Hasła Apple)**: logowanie do portalu z sieci domowej i hasło pulpitu VNC mają pola użytkownik + hasło
  rozpoznawane przez Hasła Apple (zapis i autouzupełnianie). Wdrożone, strona sprawdzona curl.
- **2026-10-26 (Progres: średnie)**: Wykresy Progresu: „Na żywo” albo średnie z tygodnia / miesiąca / roku w słupkach
  (opcje zależą od zakresu). Sprawdzone w Playwright na danych testowych (bez błędów konsoli). Szczegóły w `PROGRES.md`.
- **2026-10-26 (intervals.icu)**: Bot czyta intervals.icu co 5 min (tylko odczyt): treningi na dziś/jutro (komenda
  „trening”, w budziku sama nazwa), po porannym biegu telefon „weź kreatynę” 10 min po końcu (wyłącznik na stronie
  Automatyczne). Klucz tylko na Pi (`/etc/serwerek-bot/intervals.env`). Odczyt API sprawdzony (aktywności widoczne,
  kalendarz treningów na razie pusty).
- **2026-10-26 (intervals wdrożone)**: Wgrane na Pi razem ze średnimi w Progresie. Klucz w `/etc/serwerek-bot/intervals.env`,
  usługa bota z `EnvironmentFile=-…/intervals.env`. Treningi widoczne (np. 27.10 „Poranny bieg — lekki rozruch”);
  dzisiejszy bieg (8:14) za stary na przypomnienie, więc bez telefonu.
- **2026-10-26 (wejścia: IPv4 i Tailscale)**: Powiadomienie o nowym wejściu z sieci domowej pokazuje adres IPv4
  (także gdy wejście było z IPv6 fe80::) i nazwę Tailscale urządzenia (np. 172.23.0.33 = PC-Antek 100.77.150.92).
- **2026-10-26 (ustawienia, oceny, zakupy)**: Panel „⚙️ Ustawienia” na dole stron automatyzacji (włączniki, godziny,
  częstotliwość; Mobidziennik może dzwonić rano/wieczorem ze zmianami). Oceny i średnie zwykłe (bez wag) z Mobidziennika.
  Przywrócone `/api/zakupy` (lista zakupów łazika), które moje wdrożenie przez pomyłkę usunęło. Wszystko na Pi, sprawdzone.
- **2026-10-26 (kalendarz, semestry, symulacja ocen)**: Kalendarz `/strony/kalendarz/` (wszystko razem albo osobno:
  nauka, lekcje, treningi, zadania, budziki). Oceny z obu okresów + cały rok, średnia ze średnich i ze wszystkich ocen,
  symulacja „co jeśli” na stronie Mobidziennik. Sprawdzone na Pi w przeglądarce (Playwright, bez błędów).
- **2026-10-26 (nauka współpracuje z kalendarzem)**: Sesje nauki nie nachodzą na lekcje (z dojazdem), treningi i inne
  zadania: wolne okienka z `/api/kalendarz/wolne`, bot przesuwa kolidujące sesje i pisze o tym; godziny planowanych
  treningów szacowane ze zwykłych pór i omijają szkołę. Sprawdzone na Pi (27.10: sesja 18:00 w czasie lekcji do 19:20,
  dzień pełny → wiadomość z prośbą o decyzję).
- **2026-10-27 (spam „brak okienka”)**: `pilnuj_nauki` przy braku wolnego okienka pisało co 5 min (ponad 100 wiadomości).
  Teraz raz na zadanie i termin (`stan["nauka_zgloszone"]`). Wgrane 7:41, po 6 min brak nowych wiadomości i błędów.
- **2026-10-28 (przypomnienia z kalendarza)**: 10 min przed lekcją / nauką (opcjonalnie zadaniem) wiadomość na Linphone;
  ustawienia (minuty, kategorie) na stronie Kalendarz. Wgrane, bot bez błędów.
- **2026-10-28 (głośnik AirPlay 2)**: Pi jako głośnik AirPlay 2 z multiroomem (shairport-sync z AirPlay 2 + nqptp),
  strona `/strony/glosnik/`: włącznik, wyjście AUX/Bluetooth, wybór głośnika BT (raz), BT łączony tylko na czas grania.
  Działa przez AUX; Bluetooth czeka na zgodę na restart Pi (BT wyłączony w config.txt).
- **2026-10-28 (Bluetooth)**: Bluetooth włączony (config.txt + rfkill), restart Pi 20:05, wszystkie usługi wróciły. Skan BT
  działa (widać głośnik TP-Link_Music).
- **2026-10-28 (AirPlay: nazwa i wyjątek)**: Głośnik nazywa się „Antek Pokój rpi”. Za zgodą Antka reguła logowania wejść
  pomija port 7000 i porty >= 32768 (AirPlay), żeby granie nie było brane za skanowanie portów.
- **2026-10-28 (AirPlay: opóźnienie)**: Mniejszy bufor wyjścia (0,1 s), przesunięcie BT domyślnie wyłączone (przełącznik
  na stronie), stan „gra” zerowany przy starcie usługi.
- **2026-10-28 (AirPlay: karta USB)**: Trzeci tryb wyjścia: karta dźwiękowa USB (wykrywana na stronie, przycisk aktywny po
  podłączeniu; bez karty gra przez AUX).
- **2026-10-28 (AirPlay: cisza przez BT)**: Bufor wyjścia 0,1 s psuł dźwięk przez Bluetooth; wycofany (domyślny), usługa
  zrestartowana. Wyjście PipeWire było poprawne (AirPlay → TP-Link_Music).
- **2026-10-28 (telefon: cisza przy długiej wiadomości)**: Telefon o zmianach w dzienniku milczał ~30 s (synteza 44 s mowy
  naraz). Teraz synteza i odtwarzanie zdaniami: start po 1–2 s. AirPlay nieruszany (prośba Antka: bez zgody nie zmieniać).

