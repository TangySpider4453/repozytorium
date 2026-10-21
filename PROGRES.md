# Progres sylwetki: opis projektu

Podstrona portalu na Raspberry Pi: **http://100.108.241.58/strony/progres/** (kafelek „Progres sylwetki” na stronie
głównej i link „Progres” w menu portalu). Uruchomiona 2026-10-21.

## Co robi
- **Dodaj:** data (domyślnie dzisiaj, można wybrać wcześniejszą), masa [kg], tłuszcz [%], mięśnie [%], notatka;
  zdjęcia z typem: `przod`, `bok`, `biceps` (przód z napięciem bicepsa), `tyl`, `inne`. Przy starszych zdjęciach strona
  podpowiada datę z EXIF (DateTimeOriginal) albo z daty pliku. Zdjęcia są zmniejszane w przeglądarce do 1800 px
  (JPEG 0,88) + miniatura 480 px, ponowne kodowanie usuwa EXIF (np. GPS).
- **Rozpoznawanie sylwetki:** MediaPipe Pose Landmarker (full) w przeglądarce, pliki hostowane na Pi w
  `~/portal/sites/progres/mp/` (pobiera je `narzedzia/progres_pobierz_mediapipe.sh`, nie są w repo).
  Z barków (11, 12) i bioder (23, 24) liczone jest `pose = {cx, cy, s, ok}`: środek tułowia (ułamek szer./wys.)
  i długość tułowia (ułamek wysokości).
- **Wyrównanie w filmie:** każda klatka jest skalowana tak, by tułów miał 26% wysokości kadru, a jego środek był
  w poziomie na środku i na 44% wysokości (`CEL` w `app.js`). Ręczna korekta per zdjęcie: `reczne = {dx, dy, z}`
  (przesunięcie w długościach tułowia i zoom), ustawiana w oknie „Kadrowanie” z półprzezroczystym poprzednim
  zdjęciem tego samego typu.
- **Historia:** wykres masy (kg) i osobno składu ciała (%), lista dni z miniaturami, edycja typu/daty, kosz.
- **Film:** typ zdjęcia, zakres dat, „co ile dni” (z każdego okna N dni pierwsze zdjęcie), sekundy na zdjęcie,
  format 4:5 / 9:16 / 1:1, przejście płynne/cięcie, napis z datą i wynikami. Podgląd na canvasie, nagrywanie przez
  MediaRecorder (MP4 w Safari/Chrome, inaczej WebM). Ustawienia zapisują się na Pi.

## Pliki
| Gdzie | Co |
|---|---|
| repo `progres/` | `index.html`, `app.js`, `site.json` (kopiowane do `~/portal/sites/progres/`) |
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
Pozostałe `/api/*` mają limit 64 KB (hook `limit_malych_zapytan`).

## Dziennik
- **2026-10-21**: Pierwsza wersja. Test: 4 zdjęcia (3 różne kadry tego samego zdjęcia + bok) rozpoznane, wyrównanie
  zgodne do ~3%, nagranie MP4 2,1 s, wykresy z dymkiem. Wdrożone z kopią `app.py.bak_2026-10-21_progres`;
  restart tylko `home-portal`, usługi Minecraft `active`.
