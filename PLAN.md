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
- **Najnowsza notatka ma być na górze listy.**
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
| Zakładka „Najważniejsze” | ✅ na wszystkich 4 stronach, pierwsza i domyślnie otwarta |
| Data sprawdzianu z historii | ✅ **2026-10-20**, cały dział: tematy 1–6 (użytkownik potwierdził, że temat 4 też obowiązuje, mimo że dziennik podawał 1, 2, 3, 5, 6) |
| Fizyka: *Siły, pole i napięcie elektryczne* (kartkówka **2026-10-23**) | ✅ na Pi, 34 fiszki, 35 pytań quizu, 11 zadań, zakładka „Wzory” zamiast osi czasu. Treść z typowego programu liceum (bez zdjęć od użytkownika) |
| Matematyka: *Wielomiany* (sprawdzian **2026-10-23**) | ✅ na Pi, `matematyka-wielomiany`, 33 fiszki, 40 pytań, 13 zadań, rachunki sprawdzone w sympy |
| Montaż urządzeń mechatronicznych: *Pomiary w układach elektropneumatycznych i elektrohydraulicznych* (kartkówka **2026-10-26**, grupa 3 KL-1/2) | ✅ na Pi, `montaz-pomiary-pneumatyka-hydraulika`, 38 fiszek, 38 pytań, 14 zadań. Wiedza podręcznikowa, bez notatek nauczyciela |
| Angielski: *Impulse 3 Unit 3 „Mysteries”* (sprawdzian **2026-10-22**) | ✅ na Pi, `angielski-impulse3-unit3`, z PDF podręcznika (s. 39–53, wordlist z tłumaczeniami): 142 fiszki z przełącznikiem EN↔PL, 66 pytań, 22 ćwiczenia |
| Polski: wiersz na pamięć, Tetmajer *„Lubię, kiedy kobieta…”* (**2026-10-27**) | ✅ na Pi, `polski-tetmajer-lubie-kiedy-kobieta`: nauka na pamięć (5 poziomów), wpisywanie wersów, quiz 28. ⚠️ Tekst z pamięci Claude, **niesprawdzony z podręcznikiem (str. 90)** — poproś o zdjęcie i porównaj |
| Edukacja obywatelska: *Masz wpływ 1*, dział 5 „Prawo i prawa człowieka”, tematy 1–5 (sprawdzian **2026-11-12**) | ✅ na Pi, `edukacja-obywatelska-dzial-5`, z PDF podręcznika (s. 187–218): 45 fiszek, 57 pytań, 20 pytań otwartych. Temat 4 oznaczony w podręczniku „F” (fakultatywny) — uwzględniony, do potwierdzenia u nauczyciela |

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
| `dodano` | data dodania notatki `RRRR-MM-DD`. **Po tym sortuje się lista, najnowsze na górze.** Przy tej samej dacie wyżej jest bliższy sprawdzian |
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
