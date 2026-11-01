# Łazik: projekt i strony na Pi (opis dla kolejnych sesji)

Szkolny projekt autonomicznego łazika z łącznością LoRa. Pisz z użytkownikiem po polsku. **Nie używamy nazwiska
nauczyciela** w żadnym materiale. Repozytorium jest **publiczne**: nie wpisuj tu publicznego IP domu, adresu tunelu
Minecrafta, haseł ani kluczy.

Pełny obraz projektu jest w **mapie projektu** (`strona/mapa.html`): architektura (łazik Pi 5 – satelita a2 – stacja
a1), radio (A = 868 MHz w podpasmie 869,4–869,65 MHz, B = 433 MHz na DX-LR03), protokół DTN P0–P5 z HMAC,
autonomia (OAK-D Lite, slam_toolbox, Nav2, Hailo-8), etapy E0–E11, sprzęt, historia koncepcji, ryzyka, otwarte decyzje.
**Stan: przed E0/E1**, nowego kodu jeszcze nie ma.

## Trzy strony projektu na Pi 4B (rozwijamy je razem z projektem)

| Strona | Adres (tylko Tailscale) | Plik na Pi | Kopia w repo |
|---|---|---|---|
| Koncepcja | http://100.108.241.58/strony/lazik/ | `~/portal/sites/lazik/index.html` | `strona/index.html` (**jeszcze nie pobrana**) |
| Lista zakupów | http://100.108.241.58/strony/lazik/zakupy.html | `~/portal/sites/lazik/zakupy.html` | `strona/zakupy.html` (**jeszcze nie pobrana**) |
| Mapa projektu | http://100.108.241.58/strony/lazik/mapa.html | `~/portal/sites/lazik/mapa.html` | `strona/mapa.html` (**jeszcze nie wgrana na Pi**) |

- Lista zakupów zapisuje stan (do kupienia / zamówione / mam, notatki) przez `/api/zakupy` w `~/portal/app.py`, dane
  w `~/portal/data/zakupy.json`. **Użytkownik sam odhacza pozycje**, więc danych nie nadpisuj i nie trzymaj w repo.
- Kopia `pi/app.py` w repo jest **starsza** niż na Pi (nie ma `/api/zakupy`, dodane 2026-10-26 z PC). Przed zmianą
  portalu pobierz aktualny `app.py` z Pi. Zasady pracy z portalem i usługami: `SERWER.md` (nie ruszać Minecrafta).
- Nowe pliki w `sites/lazik/` działają od razu, bez restartu portalu. Dioda zdrowia dokleja się sama przed `</body>`.

## Jak pracować ze stronami

1. Na początku sesji (Tailscale musi działać, patrz `PLAN.md` sekcja 4): pobierz aktualne strony z Pi, bo użytkownik
   lub sesja na PC mogły je zmienić:
   `scp pi:/home/tonyg/portal/sites/lazik/{index.html,zakupy.html,mapa.html} lazik/strona/`
2. Zmień pliki w `lazik/strona/`, wgraj na Pi (`scp lazik/strona/<plik> pi:/home/tonyg/portal/sites/lazik/`),
   sprawdź `curl -s -o /dev/null -w '%{http_code}' http://raspberrypi/strony/lazik/<plik>` (ma być 200).
3. Każdą nową decyzję wpisz w mapę (sekcja, której dotyczy, plus „Historia koncepcji”), zaktualizuj „Stan”
   poniżej i dopisz wiersz do dziennika. Commit + push.

Bez Tailscale: przygotuj pliki w repo i powiedz użytkownikowi, że trzeba je wgrać na Pi. Sam może to zrobić przez
udział Samba `\\100.108.241.58\tonyg` do `portal\sites\lazik\`.

## Do zrobienia przy pierwszym dostępie do Pi

- [ ] wgrać `strona/mapa.html` na Pi i sprawdzić w przeglądarce,
- [ ] pobrać `index.html` i `zakupy.html` do `strona/` (sprawdzić, czy nie ma w nich publicznego IP ani nazwiska),
- [ ] na stronie koncepcji i liście zakupów dodać linki do mapy (i odwrotnie są już w mapie),
- [ ] pobrać aktualny `app.py` do `pi/app.py`.

## Malinki projektu

| | Rola (propozycja) | Tailscale | LAN | Kod |
|---|---|---|---|---|
| a1 `rpi-zero2w-a1` | stacja domowa | 100.124.7.125 | 172.23.0.27 | `/home/rpi/Documents/lora_field/` |
| a2 `rpi-zero2w-a2` | satelita | 100.89.71.96 | 172.23.0.21 | jw., usługa `lora_field.service` |

| **Pi 5 (łazik)** `rpi-5-1` | komputer łazika | 100.64.96.61 | 172.23.0.15 | `/home/rpi/lazik/` |

Pi 5: 8 GB, Debian 13 (trixie), jądro 6.18, użytkownik `rpi` (sudo bez hasła), Tailscale zainstalowany przez użytkownika.
**AI HAT+ Hailo-8 (26 TOPS)** działa: `hailo-all` 5.1.1, HailoRT i firmware 4.23.0, modele w `/usr/share/hailo-models/`.
Kamera USB Logitech C170 = `/dev/video0` (1024×768, ~12 kl/s). Ekran testowy HDMI 1024×600 (Lenovo L1950wD) z dotykiem
D-WAV, pulpit Wayland (labwc). Logowanie z chmury na razie hasłem (klucza nie dopisujemy bez zgody użytkownika).
⚠️ Zasilanie: `get_throttled=0x50000` (spadki napięcia od startu), EXT5V ≈ 4,86 V: potrzebny zasilacz 27 W 5 V/5 A.

**Aplikacja „Łazik: wizja”** (`apki/wizja/`, na Pi `~/lazik/wizja/`, ikony na pulpicie „Łazik: wizja” i „Łazik: skany 3D”):
- **Kamera:** Logitech C170 w 640×480 MJPG, `exposure_dynamic_framerate=0` (w słabym świetle 20 → 25 kl/s;
  25 kl/s to praktyczny limit tej kamery, ręczna ekspozycja tylko pogarsza). Więcej klatek = lepsza kamera (np. CSI).
- **Tryb Obiekty:** model do wyboru przyciskiem: YOLOv8s (100 kl/s na Hailo), **YOLOv8m** (domyślny, 32 kl/s, przy
  kamerze 25 kl/s Hailo ~80%), YOLOv8x (14 kl/s, Hailo 100%); m i x z Hailo Model Zoo v2.17 w `modele/`. Każdy obiekt
  ma numer (śledzenie po IoU), lista, opis sceny. Dotknięcie = tylko ten obiekt (lupa, położenie), „cała klasa”.
  „Zdjęcie” = stop-klatka z adnotacjami (zoom 2 palcami / kółkiem / + −, podpisy w stałym rozmiarze poza obiektem),
  zapis do `zdjecia/` (`.jpg`, `_ramki.png`, `.json`), „Galeria”, „Pauza”.
- **Tryb Przestrzeń:** na żywo dwa widoki obok siebie (obraz | głębia scdepthv3 na Hailo) i opis (blisko/daleko).
  „● Nagrywaj” zapisuje każdą klatkę do `nagrania/RRRR-MM-DD_GGMMSS_nagranie/` (`wideo.avi` MJPG, `czasy.txt`, `info.json`).
  **„Analiza”** (ekran na całość): wybór nagrania, analiza na pełnych obrotach (Hailo seriami po 8 klatek, ORB na
  3 wątkach, ruch kamery PnP z głębią + zapas z homografii), postęp, tempo, czas do końca, CPU/RAM/Hailo z temperaturami,
  werdykt (obrót w miejscu czy chodzenie, % zgubionych klatek). Na czas analizy podgląd przestaje używać Hailo.
  Wynik: `skany/RRRR-MM-DD_GGMM_skan/` (`skan.html` + `three.min.js`, `chmura.ply`, `info.json`), woksel 2 cm.
  Zmierzone: analiza ~38 kl/s (≈1,5× szybciej niż nagranie), głębia 5 ms/klatkę.
- **Ruch w nagraniu:** analiza liczy obrót i przesunięcie (PnP), więc można iść wolno i płynnie; obrót w miejscu jest
  najpewniejszy. Test syntetyczny (pokój, 1 m drogi + 90° obrotu, idealna głębia): obrót 86°, mediana odchyłki punktów
  od ścian 0,9 cm, droga zawyżona ~20%. Na prawdziwej kamerze głębia jest zgadywana, więc skala i kształt orientacyjne.
- **Podgląd 3D:** przyciski przytrzymywane (▲▼◀▶ chodzenie, ↺↻ obrót, patrz ↑↓, w górę/w dół), przeciąganie po obrazie,
  klawiatura WASD/QE. Joystick dotykowy usunięty (na ekranie D-WAV dotyk przychodzi jak mysz).
  `./skany.sh <folder_skanu>` otwiera jeden skan od razu.
- **Hailo:** modele wczytują się raz i zostają na chipie (zwalnianie w trakcie pracy = crash w HailoRT 4.23 + picamera2),
  wyjście przez `os._exit`. Temperatura: stały uchwyt `get_physical_devices()[0]`. Przegrzanie > 85 °C wyłącza liczenie.
- Instalacja: `./instaluj.sh` (pakiety + v4l-utils, modele głębi i YOLOv8m/x, three.js, ikony; po pierwszej instalacji
  `hailo-all` reboot). Testy: `./uruchom.sh --rozpoznawanie [--przestrzen]`. Z SSH na ekranie:
  `XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 ./uruchom.sh &`, zrzut `grim /tmp/ekran.png`, zamykanie
  `pkill -f "^python3 wizja\.py"` (wzorzec bez `^` zabija też własną powłokę SSH).
- VNC włączony (wayvnc, port 5900, logowanie kontem `rpi`).

Zero 2W: użytkownik `rpi`, Debian 13, Python 3.13. Klucz SSH z chmury na nich nie działa; do ustalenia: Tailscale SSH
(`sudo tailscale set --ssh`) albo skok przez Pi 4B.

Dokumentacja źródłowa jest u użytkownika na PC (`C:\Users\tonyg\Documents\claude kopia\`): plik główny projektu
(części 1–3), dziennik kodu (tylko kod sprawdzony na sprzęcie, wpisy z datą i godziną `RRRR-MM-DD GG:MM`, zdjęcia
`RRRR-MM-DD_GGMM_opis.jpg`) i kopia sprzed 2026-10-18. Mapa projektu jest ich streszczeniem.

## Stan

| Data | Co |
|---|---|
| 2026-11-01 | Wizja v3: 25 kl/s (ustawienie kamery), YOLOv8m/x do wyboru, nagrywanie z dwoma widokami, analiza nagrań na pełnych obrotach (PnP z głębią, ekran postępu z obciążeniem i temperaturami), strzałki w podglądzie 3D. Pi zrestartował się raz (zasilanie). |
| 2026-11-01 | Wizja v2: śledzenie i wybór obiektów, zdjęcia z adnotacjami (zoom, galeria), opis sceny, tryb Przestrzeń (głębia Hailo, skan 3D, przeglądarka „gra”). VNC włączony. Zasilacz za słaby (spadki napięcia). |
| 2026-11-01 | Pi 5 + AI HAT+ (Hailo-8) uruchomione; aplikacja „Łazik: wizja” na pulpicie Pi 5, sprawdzona na sprzęcie (YOLOv8s ~12 ms/klatkę, Hailo ~41 °C). |
| 2026-10-26 | Mapa projektu zrobiona z trzech plików dokumentacji i historii czatu; zapisana w `strona/mapa.html`. Na Pi jeszcze jej nie ma (brak `TS_AUTHKEY` w środowisku chmury). |
