# Progres sylwetki: opis projektu

Podstrona portalu na Raspberry Pi: **http://100.108.241.58/strony/progres/** (kafelek „Progres sylwetki” na stronie
głównej i link „Progres” w menu portalu). Uruchomiona 2026-10-21.

## Co robi
- **Dodaj:** data (domyślnie dzisiaj, można wybrać wcześniejszą), masa [kg], tłuszcz [%], mięśnie [%], notatka;
  zdjęcia z typem: `przod`, `bok`, `biceps` (przód z napięciem bicepsa), `tyl`, `tylbiceps` (plecy z bicepsem), `inne`. Przy starszych zdjęciach strona
  podpowiada datę z EXIF (DateTimeOriginal) albo z daty pliku. Zdjęcia są zmniejszane w przeglądarce do 1800 px
  (JPEG 0,88) + miniatura 480 px, ponowne kodowanie usuwa EXIF (np. GPS).
- **Rozpoznawanie sylwetki:** MediaPipe Pose Landmarker (full) w przeglądarce, pliki hostowane na Pi w
  `~/portal/sites/progres/mp/` (pobiera je `narzedzia/progres_pobierz_mediapipe.sh`, nie są w repo).
  Z barków (11, 12) i bioder (23, 24) liczone jest `pose = {cx, cy, s, ok}`: środek tułowia (ułamek szer./wys.)
  i długość tułowia (ułamek wysokości).
- **Wzór szkieletu per rodzaj (od 2026-10-21):** każde zdjęcie ma `lm` = 33 punkty MediaPipe `[x, y, widoczność]`
  (`[]` = nie rozpoznano). Wzór rodzaju = średnia punktów ze wszystkich zdjęć tego rodzaju (Prokrustes: skala +
  przesunięcie, 3 iteracje), w jednostkach tułowia. Zdjęcie dopasowane do wzoru ważoną MNK (`WAGI` w `app.js`: barki
  i biodra 3–3,5, głowa/kolana ok. 1, ręce 0,05–0,5; bok najmniej rąk). `FM.rece` (tylko `biceps`/`tylbiceps`):
  dopasowanie tylko do barków, łokci, nadgarstków. Wynik `{s, tx, ty}` liczy przeglądarka i wysyła do renderu jako
  `geo` (Python go tylko stosuje). Starsze zdjęcia bez `lm` są uzupełniane automatycznie w zakładce Film.
- **Wyrównanie w filmie:** każda klatka jest skalowana tak, by tułów miał `celS` wysokości kadru (domyślnie 26%),
  a jego środek był w poziomie na środku i na `celY` wysokości (domyślnie 44%). Oba ustawia się w karcie „Kadr filmu”
  (suwaki „Przybliżenie” i „Wysokość”, podgląd ze szkieletem); zapis w `ustawienia.film`.
- **Przycięcie:** `przytnij` (domyślnie tak) = automatyczna ramka o proporcjach kadru w części wspólnej wszystkich
  klatek (bez krawędzi zdjęć), skalowana wokół punktu tułowia; albo ręczna `ramka {x, y, w}` (ułamki kadru, h = w),
  rysowana i przesuwana palcem na podglądzie. Ramka ręczna ma pierwszeństwo. Ręczna korekta per zdjęcie: `reczne = {dx, dy, z}`
  (przesunięcie w długościach tułowia i zoom), ustawiana w oknie „Kadrowanie” z półprzezroczystym poprzednim
  zdjęciem tego samego typu.
- **Historia:** wykres masy (kg) i osobno składu ciała (%), lista dni z miniaturami, edycja typu/daty, kosz.
- **Film:** typ zdjęcia, zakres dat, „co ile dni” (z każdego okna N dni pierwsze zdjęcie), sekundy na zdjęcie,
  format 4:5 / 9:16 / 1:1, przejście płynne/cięcie, napis z datą i wynikami. Podgląd na canvasie, nagrywanie przez
  MediaRecorder (MP4 w Safari/Chrome, inaczej WebM). Ustawienia zapisują się na Pi.

- **Tryby filmu:** `tryb: "seria"` (zdjęcia co N dni, `sek`, `przejscie`) albo `tryb: "pp"` – przed i po z 2 zdjęć
  (`pp1`, `pp2`, `ppT` = czas zdjęcia, `ppTr` = czas przejścia): zdjęcie 1 → przejście → oba nałożone 50/50 →
  przejście → zdjęcie 2. Oś czasu `plan()` w `app.js` i `plan()` w `pi/progres_render.py` muszą być zgodne.
- **Render na Raspberry:** przycisk „Renderuj na Raspberry” → `POST /api/progres/render {film, ids, opis}` → kolejka
  (jeden film naraz, wątek w `app.py`) uruchamia `nice -n 15 python3 ~/portal/progres_render.py` (Pillow + ffmpeg
  libx264, 30 fps, CRF 20, yuv420p, faststart). Gotowe filmy: `dane/progres/filmy/<id>.mp4` + `<id>.json`, lista
  „Gotowe filmy” (obejrzyj / pobierz / udostępnij / usuń). Test 2026-10-21: 30 zdjęć → 15,6 s filmu w 21 s na Pi.
  Zgodność z podglądem sprawdzona porównaniem klatek (średnia różnica ~1/255).

## Pliki
| Gdzie | Co |
|---|---|
| repo `progres/` | `index.html`, `app.js`, `site.json` (kopiowane do `~/portal/sites/progres/`) |
| repo `pi/progres_render.py` | render filmu na Pi (kopiowany do `~/portal/progres_render.py`) |
| Pi `~/portal/dane/progres/filmy/` | filmy z renderu na Pi (`<id>.mp4`, `<id>.json`) |
| repo `pi/app.py` | portal z API `/api/progres*` (kopia z Pi; poprzednia wersja `pi/app.py.przed_progresem`) |
| Pi `~/portal/dane/progres/dane.json` | `{wpisy: {data: {masa, fat, muscle, notatka}}, zdjecia: [{id, data, typ, w, h, pose?, reczne?, dodano}], ustawienia: {film}}` |
| Pi `~/portal/dane/progres/zdjecia/` | `<id>.jpg` i `<id>_m.jpg` |
| Pi `~/portal/dane/progres/kosz/` | usunięte zdjęcia (nie są kasowane) |

**Zdjęcia NIGDY nie trafiają do repozytorium** (prywatne). Są tylko na karcie SD Raspberry. Warto kiedyś zrobić kopię
zapasową `~/portal/dane/` (np. przez udział Samba na komputer).

## API (portal, tylko Tailscale)
- `GET /api/progres` – całość danych
- `POST /api/progres/wpis` `{data, masa?, fat?, muscle?, notatka?}` (same null → usuwa wpis dnia)
- `POST /api/progres/zdjecie` multipart: `plik`, `miniatura` (JPEG), `data`, `typ`, `pose` (JSON) – limit 25 MB
- `POST /api/progres/zdjecie/<id>` `{data?, typ?, pose?, reczne?}` albo `{usun:true}` (do kosza)
- `GET /api/progres/plik/<id>.jpg` i `<id>_m.jpg`
- `POST /api/progres/ustawienia` `{film:{...}}`
- `POST /api/progres/render` `{film, ids, opis}`, `GET /api/progres/filmy`, `GET /api/progres/film/<id>.mp4` (Range),
  `POST /api/progres/film/<id>` `{usun:true}` (nie w trakcie renderu)
Pozostałe `/api/*` mają limit 64 KB (hook `limit_malych_zapytan`).

## Dziennik
- **2026-10-21**: Pierwsza wersja. Test: 4 zdjęcia (3 różne kadry tego samego zdjęcia + bok) rozpoznane, wyrównanie
  zgodne do ~3%, nagranie MP4 2,1 s, wykresy z dymkiem. Wdrożone z kopią `app.py.bak_2026-10-21_progres`;
  restart tylko `home-portal`, usługi Minecraft `active`.
- **2026-10-21 (2)**: Wyrównanie na iPhonie/iPadzie: formularz w siatce 4 kolumny (telefon 2), jednostki obok nazw pól,
  jednakowa wysokość pól. Na stronie głównej portalu kafelki statystyk: telefon 2+2+1, tablet 3+2, szeroko 5 w rzędzie,
  paski przy dolnej krawędzi (backup `app.py.bak_2026-10-21_kafelki`).
- **2026-10-21 (3)**: „Użyj daty ze zdjęcia” ustawia datę pomiaru i wszystkich wybranych zdjęć (wpisane ręcznie liczby
  zostają, wartości wypełnione automatycznie z innego dnia są podmieniane). Film: przycisk „Cały zapis”, domyślny rodzaj
  zdjęcia = pierwszy, który ma zdjęcia. Safari/iPad: pola daty nie wypychają siatki (`min-width:0`), `app.js?v=3`.
  Portal: JS/CSS stron z `Cache-Control: no-cache` (backup `app.py.bak_2026-10-21_cache`).
  **Przy zmianie `app.js` podbijaj `?v=` w `progres/index.html`.**
- **2026-10-21 (4)**: Film: czas przejścia w sekundach (0 = cięcie, maks. czas klatki), „Eksportuj film” → „Pobierz plik”
  i „Udostępnij / Zapisz w Zdjęciach” (Web Share API z plikiem, iOS/iPadOS). Nazwa pliku z zakresem dat. `app.js?v=4`.
- **2026-10-21 (5)**: Karta „Kadr filmu”: przybliżenie i wysokość sylwetki, szkielet-wzór, krawędzie zdjęć na podglądzie,
  automatyczne przycięcie do części wspólnej (test: czarne brzegi 35–100% → 0%), własna ramka. `app.js?v=5`.
- **2026-10-21 (6)**: Render filmów na Raspberry (kolejka, lista gotowych filmów, udostępnianie), tryb „Przed i po”
  z dwóch zdjęć, wyraźniejsze kolory (wybrane = niebieskie z ✓, kontrast ≥ 4,5:1), aktywna zakładka biała.
  Backup `app.py.bak_2026-10-21_render`. `app.js?v=7`.
- **2026-10-21 (7)**: Rodzaj „Tył + biceps”, wzór szkieletu dla każdego rodzaju (średnia z 33 punktów), dopasowanie
  ważone (tułów/barki najważniejsze, ręce mało), tryb „Samych rąk” dla biceps/tył+biceps, szkielet też w kadrowaniu
  pojedynczego zdjęcia, automatyczne uzupełnianie punktów. Render na Pi zgodny z podglądem (~1/255).
  Backup `app.py.bak_2026-10-21_szkielety`. `app.js?v=8`.
