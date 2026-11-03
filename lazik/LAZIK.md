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

## Aplikacja „Łazik: analiza wideo” (`apki/analiza/`, na Pi 5 `~/lazik/analiza/`, ikona na pulpicie)
- **Przesyłanie:** usługa `lazik-wideo.service` (Flask, port 8080, zawsze włączona). Dostęp tylko z kodem
  (`kod_dostepu.txt`, w aplikacji jako QR i adresy LAN/Tailscale; przeglądarka zapamiętuje go w ciasteczku).
  Plik idzie strumieniem PUT prosto do `filmy/` (bez `/tmp` w RAM-ie), strona pokazuje postęp i listę raportów.
  Można też „Dodaj z pliku / pendrive’a” w aplikacji. Lista obejmuje też nagrania z „Łazik: wizja”.
- **Notatki:** YOLOv8m na Hailo (seriami po 8 klatek), ~10 klatek filmu na sekundę analizy; twarze YuNet + SFace
  (OpenCV, procesor) grupowane w obrębie filmu (próg cosinus 0,363, scalanie na końcu): „różne twarze (pewne)” =
  widziane ≥ 2 razy. Bez nazwisk i bez bazy osób. Przedmioty: maks. naraz, czas widoczności, pierwszy raz, miniatura;
  oś czasu; do 12 klatek kluczowych (zmiana sceny). Test: film z 2 osobami → 2 pewne twarze; ~14 kl/s, CPU ~80 %.
- **Opis AI:** Ollama 0.40 (usługa `ollama`, zainstalowana 2026-11-01) + `gemma3:4b` (3,4 GB) **na procesorze Pi 5,
  nie na Hailo** (Hailo-8 nie uruchamia modeli językowych; potrafi to Hailo-10H w AI HAT+ 2). Zmierzone: ~2 min na
  klatkę, opis po polsku sensowny, ale z drobnymi zmyśleniami. Do 8 klatek kluczowych + podsumowanie (~17 min na film).
  Pod pełnym obciążeniem procesor doszedł do 86 °C i zwalniał (`throttled=0xe0006`): potrzebny Active Cooler.
- **Skan 3D:** `przestrzen.Analiza(..., wideo=plik)`, filmy > 960 px zmniejszane; skan w `raporty/<film>/skan/`.
- **Wynik:** `raporty/<film>/raport.html` (+ `miniatury/`, `dane.json`, `notatki.txt`), widoczny też na telefonie.
- Hailo naraz obsługuje jeden proces: przy włączonej „Łazik: wizja” analiza pokaże „Hailo zajęte”.

## Kopie zapasowe na NAS (`kopie/`)
- **Most na Pi 4:** `/usr/local/sbin/lazik-kopia-odbierz` (jedyna zmiana na Pi 4 + folder
  `/mnt/nas/Raspberry/Kopie-lazika/<pi>/` + linie w `~tonyg/.ssh/authorized_keys`). Każdy Pi ma własny klucz z
  `command="… <pi>",restrict`: może tylko `stan`, `zapisz` (strumień), `zatwierdz <sha256>`, i tylko do swojego
  folderu. Sprawdza znacznik `/mnt/nas/Raspberry/.nas`. Zostawia 3 najnowsze kopie. Log: `Raspberry/Logi/kopie-lazika.log`.
- **Na każdym Pi łazika:** `/usr/local/sbin/lazik-kopia` + `lazik-kopia.timer` (co godzinę, `OnBootSec=5min`):
  kopia, gdy od ostatniej udanej minęło 7 dni (zaległa rusza zaraz po włączeniu i dostępie do sieci domowej).
  `tar` całego systemu (uprawnienia, ACL, xattr, `/boot/firmware`), `zstd`, SHA-256 sprawdzana na Pi 4. Pomija modele
  do pobrania i cache. Łączy się po LAN z `tonyg@172.23.0.20` (Tailscale SSH na Pi 4 wymaga zatwierdzania).
  Stan: `/var/lib/lazik-kopia/kopia.log`, wymuszenie: `sudo lazik-kopia --teraz`.
- Instalacja: na Pi 4 `instaluj-most.sh`, na Pi łazika `instaluj-na-pi.sh` (wypisze klucz) i na Pi 4
  `dodaj-klucz.sh <pi> "<klucz>"`. **Zero 2W a1/a2 czekają** (offline od połowy października).
- Przywracanie: `zstd -dc PLIK.tar.zst | sudo tar -xpf - --xattrs --acls --numeric-owner -C /mnt/nowa-karta`
  (na świeżo sformatowaną kartę z partycjami jak w Raspberry Pi OS; potem sprawdzić PARTUUID w `cmdline.txt` i `fstab`).

## Aplikacja „Łazik: sterowanie” (`apki/sterowanie/`, na Pi 5 `~/lazik/sterowanie/`)
- **Adres HTTPS (pad Xbox działa zdalnie):** https://rpi-5-1.tail52831c.ts.net/ (`tailscale serve --bg 8000`, tylko w tailnecie,
  włączone 2026-11-02). Gamepad API wymaga HTTPS albo localhost; zwykłe http://IP:8000 działa bez pada.
- Usługa `lazik-sterowanie.service` (startuje z Pi, port 8000, kod dostępu w `kod_dostepu.txt`, ciasteczko).
  Ikona „Łazik: sterowanie” otwiera stronę w Chromium. Strona: podgląd MJPEG + ramki (płótno), dotknięcie obiektu =
  zaznaczenie („▶ Jedź za zaznaczonym”), tryby, pad do jazdy ręcznej (przytrzymanie, klawisze WASD/strzałki, spacja = STOP),
  paski wolnego miejsca z głębi, ustawienia napędu (maks./min. moc, odwracanie silników, zamiana stron).
- Tryby (`tryby.py`, 10 Hz, opis decyzji słowami): Ręczny; Przetrwaj (zagrożenie = osoba/zwierzę/pojazd, który rośnie
  w kadrze lub jest blisko → ucieczka w przeciwną stronę, co 8 s rozglądanie); Zwiedzaj i skanuj (jazda z omijaniem
  przeszkód + nagrywanie, po STOP „Zrób skan 3D z ostatniej wyprawy”); Fotograf (różne klasy, max raz na 3 min, podjazd
  i zdjęcie do `wizja/zdjecia/` w formacie galerii); Śledź (konkretny obiekt albo klasa; odległość = wysokość ramki).
- Bezpieczeństwo: po starcie STOP; polecenie silnika ważne 0,6 s (strażnik w `naped.py`); brak pulsu strony 3 s = STOP.
  Kamera i Hailo tylko gdy ktoś ogląda/tryb działa; po 120 s bezczynności proces się kończy i systemd go wznawia
  (zwalnia Hailo dla „wizji”/„analizy”). Przetestowane w symulacji (gpiozero mock) i na Pi: 25 kl/s, Hailo ~43 °C.
- Napęd: HW-094 przez gpiozero `Motor` (piny w `konfiguracja.json`: 17/27 + PWM 12 lewy, 22/23 + PWM 13 prawy), bez enkoderów.
  **2026-11-02: silniki nie ruszyły w teście** (impulsy 0,4–0,8 s, 50–70%, kamera bez zmiany). Do sprawdzenia: zasilanie
  silników, połączenia, typ płytki. Piny kierunku jako wejścia czytały stan wysoki: płytka podciąga wejścia (do jakiego
  napięcia? jeśli 5 V, to ryzyko dla GPIO 3,3 V).
- **Pad Xbox:** Start = tryb ręczny, B = STOP, Y = zeruj kurs żyroskopu, X = tryb mocy w kółko:
  „z ustawień” (gałka, do maks. mocy, małe wychylenie podbite do progu ruszania), „spusty” (RT przód / LT tył, moc
  **liniowo od zera** 0–100%, gałka = skręt), „wychylenie gałki” (gałka, moc liniowo od zera 0–100%), „PEŁNA” (gałka do 100%,
  z podbiciem). `/api/reczny` przyjmuje `pelna` (pomija maks. moc) i `liniowo` (bez progu ruszania). Martwa strefa gałki 12%,
  potem płynnie od zera. Zmierzone symulowanym padem (wychylenie → moc): spusty 20→20%, 40→40%, 70→70%, 100→100%;
  gałka liniowo 20→9%, 40→32%, 70→66%, 100→100%; z ustawień 20→38% … 100→70%; pełna 20→41% … 100→100%.
  Spusty: standardowe mapowanie (przyciski 6/7) albo osie 2/5; HUD pokazuje paski RT/LT i czy są płynne.
- **Ustawienia (⚙, `ustawienia.py`)**: zakładki Kamera (rozdzielczość, kl/s, stała liczba klatek, obrót 180°, lustro + wszystkie
  regulacje kamery z `v4l2-ctl`, zapamiętywane w `kamera_v4l2` i nakładane przy otwarciu), Wizja i Hailo (model YOLOv8s/m/x,
  próg, głębia zawsze, podgląd obraz+głębia, limit kl/s, jakość i szerokość podglądu, zwalnianie Hailo), Napęd, Tryby,
  Bezpieczeństwo (STOP bez strony, STOP trybów powyżej temperatury), System (restart usługi). Pola opisane w `POLA`
  (zakres, podpis, podpowiedź); strona buduje z nich formularze, serwer sprawdza wartości. „Przywróć domyślne” na zakładkę.
- Strona skaluje się: czcionka `clamp`, obraz dopasowany do wysokości ekranu, telefon w poziomie (panel obok obrazu),
  kokpit z przyciskami rosnącymi z ekranem. Sprawdzone zrzutami 360×740, 740×360, 1024×600, 1920×1080 (bez przewijania w bok).
- **Podgląd klatka po klatce** (`/klatka.jpg?po=<nr>`, od 2026-11-03): strona pobiera pojedyncze JPEG-i (dwa pobierania na
  zmianę, dekodowanie przez `Image.decode()` z limitem 3 s) zamiast MJPEG, bo Safari na iPadzie gubił strumień MJPEG bez
  błędu (ikona „?”, trzeba było przeładować). Po restarcie usługi albo zerwaniu WiFi obraz wraca sam (sprawdzone: restart
  w trakcie oglądania, obraz wrócił po kilku sekundach). `/strumien.mjpg` zostaje dla innych programów. Etykiety ramek
  nie nachodzą już na siebie (kolejna przesuwa się niżej). Adres przez IP Tailscale `http://100.64.96.61:8000/` też działa,
  ale pad wymaga HTTPS, czyli linku `https://rpi-5-1.tail52831c.ts.net/`.
- **Przeszkody (`przeszkody.py`, od 2026-11-03).** Stara metoda (głębia vs „typowa” w kadrze) mówiła „wolne”, gdy przeszkoda
  zasłaniała cały kadr: na prawdziwej klatce koszulka z ~20 cm miała głębię ~24, a ściana w tle ~20–36. Teraz łączymy:
  (1) **koniec podłogi z głębi**: w każdym z 5 pasów od dołu kadru sprawdzamy, czy głębia rośnie tak, jak na płaskiej
  podłodze (porównujemy tylko stosunki, więc skala modelu nie ma znaczenia). Wiersz, gdzie przestaje, daje odległość
  w metrach z wysokości kamery (10 cm), horyzontu (0,5) i pola widzenia (C170 ~48°). Koszulka z bliska: 30–40 cm;
  syntetyczna ściana w 0,6 m: 0,51 m; pusta podłoga: wolne; na stole w klasie krawędź blatu z rzeczami: 65 cm.
  (2) **obiekty YOLO**: dolna krawędź ramki = styk z podłogą = odległość. (3) **czas do zderzenia** z przepływu optycznego
  (Farneback 160×120, 3 ms): puchnięcie obrazu przy jeździe; sam obrót nie daje alarmu. (4) **uderzenie** (skok
  przyspieszenia z MPU6050). (5) **utknięcie**: silniki ponad 2 s, a obraz stoi. Reakcja (`tryby._omin`): cofnięcie
  0,2–0,7 s i obrót o 45–70° mierzony żyroskopem w stronę, gdzie więcej miejsca. Strona trzymana kilka sekund, a 4 omijania
  w ciągu 12 s = kąt, więc zawraca o 160°. Prędkość maleje od 90 cm do 35 cm (do 45%), łazik lekko odbija od rzeczy z boku.
  Zakładka ⚙ Przeszkody; kreski z odległościami na podglądzie i w paskach pod obrazem. **Nie wykrywa krawędzi stołu
  (spadku)**, więc autonomii nie testować na stole.
- **Pełny ekran**: nic nie leży na obrazie. Z prawej przezroczysty panel (STOP, tryb, moc, kurs, temperatury, opis),
  zwijany przyciskiem ›/‹ (po zwinięciu tylko mały STOP w rogu); obraz zajmuje resztę ekranu.
  **Telemetria jako napisy na dole podglądu** (sam tekst z cieniem): silniki L/P z kierunkiem i mocą (▲ przód / ▼ tył /
  ■ stoi, kolor zielony/pomarańczowy), kierunek jazdy (prosto, skręt, obrót w miejscu), korekta toru, kurs i obrót,
  odległość z przodu, CPU i Hailo (obciążenie i temperatura), BME280, kl/s, zasilanie gdy nie OK. `/api/stan.naped`
  podaje teraz moc stron łazika (`Naped.logiczne`: przed odwróceniami i zamianą stron), a nie stan pinów.
- **Szybkie przełączniki** (panel z prawej i panel pełnego ekranu, zapis w `konfiguracja.json`): *Analiza na Hailo*:
  Obiekty (`analiza_obiekty`), Głębia (`glebia_zawsze`). W Stop i Ręcznym liczy się tylko to, co włączone: po wyłączeniu
  obiektów Hailo spada z ~26% do 0% (sprawdzone). Tryby jazdy włączają obie analizy same (przycisk z dopiskiem „(tryb)”).
  *Na obrazie*: Ramki, Podpisy (wyłączone = same ramki), Przeszkody (kreski z cm), Horyzont (domyślnie wyłączony),
  Napisy (telemetria: tylko pełny ekran / każdy widok / wyłączone; zakładka ⚙ Nakładki). Zaznaczony obiekt i cel
  śledzenia są widoczne zawsze. Napisy mają temperatury w kolorach (CPU, Hailo, otoczenie z BME280) i obciążenie.
- **Wyświetlacz stanu na I2C** (`wyswietlacz.py`, od 2026-11-03): wykrywany sam co 5 s. OLED 128×64 SSD1306/SH1106
  (0x3C/0x3D, Pillow) albo LCD 16×2/20×4 z PCF8574 (0x27/0x3F). Tytuł „✓ WSZYSTKO OK” z Wi-Fi (sygnał, sieć), Tailscale,
  temperaturami, trybem i kursem albo „⚠ PROBLEMY: n” z listą (Wi-Fi, Tailscale, kamera, Hailo/wizja, silniki, BME280,
  żyroskop, zasilanie, temperatury ≥ 80 °C, mało miejsca); mrugający punkt = program działa. Ta sama lista jest w panelu
  stanu na stronie (`/api/stan.problemy`). Zakładka ⚙ Wyświetlacz (typ OLED, obrót, jasność, rozmiar LCD).
  **2026-11-03: wyświetlacz nie odpowiada na I2C**, a od jego podłączenia magistrala gubi transmisje (0x68 odpowiadał
  raz 50/50, raz 1/30; zapisy do MPU6050 odrzucane). Typowa przyczyna: wyświetlacz bez zasilania albo z zamienionym
  VCC/GND, podpięty do SDA/SCL, obciąża linie. Żyroskop jest wykrywany ponownie co 10 s, a zapisy są ponawiane.
- **Śledź od 2026-11-03** (`cel.py`): cel jest *zablokowany*: wygląd (histogram barwy i nasycenia, wolno douczany),
  przewidywany ruch i tracker KCF z OpenCV (prowadzi cel do 2,5 s, gdy YOLO go nie widzi; poprawiany ramką z YOLO).
  Inna ramka tej samej klasy przechodzi tylko, gdy pasuje miejscem i wyglądem; po dłuższej utracie (do 10 s) tylko
  wyglądem. Test na łaziku: dwie osoby mijają się, YOLO zamienia im numery, cel znika na 6 klatek → śledzenie zostaje
  na właściwej osobie (54/60 klatek, KCF 4 klatki, 7 ms/klatkę). W Śledź zawsze YOLOv8s (`model_wymuszony`, mniej
  obciążony Hailo). Odległość do celu w cm z dolnej krawędzi ramki (styk z podłogą), cel: `sledzenie_odleglosc_cm`
  = 60 (wcześniej wysokość ramki 0,5 = kilka metrów przy kamerze na 10 cm). Skręt z martwą strefą 7%, przy celu mocno
  z boku najpierw obrót. Przerywana zielona ramka = cel prowadzi tracker.
- **Wolniejsze obroty** we wszystkich trybach: `predkosc_obrotu` = 0,5 (było 0,6–0,9), przy końcu obrotu 75%.
- **2026-11-03, naprawy po jeździe w terenie.** (1) Magistrala I2C zawisła (SDA na stałe nisko, Errno 5: żyroskop
  i BME280 naraz), prawdopodobnie przy odłączaniu wyświetlacza albo przez luźny przewód. Nowy `i2c_straz.py`: gdy SDA jest
  nisko przez 1,5 s, robi 9 impulsów SCL + STOP przez `pinctrl` i oddaje piny do I2C (a3). Sprawdzone: wymuszone SDA nisko
  → po ~1,5 s odblokowane, żyroskop i BME280 działają dalej. Licznik odblokowań w panelu stanu. (2) **Zacinanie
  sterowania**: strona wysyłała ~70 poleceń/s z pada (wysyłka w każdej klatce animacji) i po puszczeniu gałki STOP 60/s
  bez końca. Teraz najwyżej jedno polecenie w drodze, nie częściej niż co 50 ms, odświeżanie co 120 ms: ~10/s, po
  puszczeniu jeden STOP. (3) **Spusty działają w każdym trybie mocy** (RT przód, LT tył, liniowo); gałka Y tylko przy
  puszczonych spustach. Sprawdzone symulowanym padem z przechwyceniem poleceń (bez ruszania silnikami).
- **Gałka i obroty z żyroskopem (2026-11-03).** Zapas kąta gałki `galka_kat_martwy` = 10°: wychylenie do 10° od pionu
  (przód albo tył) = jazda prosto, a tor trzyma żyroskop; przy jeździe spustami skręt poniżej 15% pomijany.
  Trzymanie toru działa też do tyłu (symulacja ze słabszym prawym silnikiem: 3 s przód 0,9°, tył 1,7°).
  **Skręt ze stałą prędkością obrotu** (`naped._obrot_staly`, `obrot_staly`, `obrot_maks_dps` = 90): wychylenie w bok
  = zadane °/s, regulator PI na odczycie żyroskopu, także obroty w trybach. Nie schodzi poniżej progu ruszania (bez szarpania).
  Symulacja z silnikami stojącymi poniżej 30% mocy i bezwładnością: zadane 68/90 °/s → płytki 69/92, trawa 65/92,
  wahanie ≤ 4 °/s (bez regulatora 230–410 °/s zależnie od podłoża). Bezpiecznik: gdy żyroskop pokazuje obrót w przeciwną
  stronę niż silniki przez 0,6 s, korekty się wyłączają i pojawia się problem „Odwróć kierunek obrotu” (resetowany zmianą
  kierunków w ustawieniach).
- **Powrót na linię toru po wyboju** (`wracaj_na_tor`, 2026-11-03): poza prostowaniem kursu łazik szacuje zejście w bok
  (całka sin(odchylenia) × prędkość z mocy, `predkosc_pelna_ms` = 0,5 m/s do zmierzenia) i jedzie skosem do linii
  (`tor_powrot_st_na_m` = 80°/m, najwyżej 25°, do tyłu skręt odwrotny). Kierunek jest przywracany przy obrocie do 150°
  (było 60°). Symulacja: wybój spycha koło przez 1,2 s; do przodu bez powrotu łazik kończy 11 cm obok linii, z powrotem
  −1 cm. Szacunek jest zgrubny: przesunięcia w bok bez obrotu (poślizg całego łazika) nie widać bez enkoderów.
- **Żyroskop MPU6050 (GY-521) na I2C 0x68** (`zyroskop.py`, 100 Hz, od 2026-11-03): kurs względny (0° = start albo „Zeruj”,
  bez magnetometru, więc to nie jest północ), prędkość obrotu i przechył. Oś pionu bierze z grawitacji przy kalibracji
  (czujnik może być przykręcony w dowolnej pozycji; ten stoi pionowo, oś X w górę). Zero żyroskopu douczane, gdy silniki
  stoją; na postoju dryf ~0° przez minutę. **Trzymanie toru** (`naped.py`, regulator PID 50 Hz): przy jeździe bez skrętu
  zapamiętuje kurs i dodaje różnicę mocy stron, a świadomy skręt ustawia nowy kurs. Działa w trybie ręcznym i w trybach
  automatycznych. Zakładka ⚙ Żyroskop (P/I/D, maks. korekta, odwrócenie, zeruj, kalibruj). STOP przy przechyle > 40°
  (Bezpieczeństwo). Symulacja z prawym silnikiem słabszym o 20%: bez korekty 66° zboczenia w 3 s, z korektą ~1°.
  Na sprzęcie do sprawdzenia: kierunek (obrót w prawo ręką ma zwiększać kurs) i strojenie P/I/D w jeździe.
- BME280 na I2C 0x76 działa (`bme280.py`, I2C włączone 2026-11-02): 22,2 °C, 1020,9 hPa, 97,8 % (wilgotność do sprawdzenia).

## Stan

| Data | Co |
|---|---|
| 2026-11-03 | Powrót na linię toru po wyboju (szacunek zejścia w bok z żyroskopu i mocy). |
| 2026-11-03 | Gałka: 10° zapasu do jazdy prosto; skręt ze stałą prędkością obrotu (regulator na żyroskopie); bezpiecznik odwróconego żyroskopu. |
| 2026-11-03 | Strażnik I2C (samo odblokowanie zawieszonej magistrali), pad bez zalewania poleceniami (~10/s zamiast ~70/s), spusty w każdym trybie mocy. |
| 2026-11-03 | Śledź: zablokowany cel (wygląd + KCF), YOLOv8s, odległość w cm (60 cm); wolniejsze obroty. Wyświetlacz odłączony (nowy w drodze). |
| 2026-11-03 | Wyświetlacz stanu I2C (OLED/LCD, wykrywany sam), lista problemów na stronie; żyroskop ponawia wykrywanie. Magistrala I2C niestabilna od podłączenia wyświetlacza. |
| 2026-11-03 | Przeszkody od nowa (koniec podłogi z głębi w cm, obiekty, czas do zderzenia, uderzenie, utknięcie; omijanie z obrotem o kąt żyroskopem). Pełny ekran z przezroczystym panelem z boku. |
| 2026-11-03 | Podgląd bez MJPEG (Safari/iPad gubił obraz), sam wraca po zerwaniu; etykiety bez nakładania. |
| 2026-11-03 | Żyroskop MPU6050 w sterowaniu: kurs, trzymanie toru (PID), STOP przy przewróceniu, Y na padzie = zeruj. |
| 2026-11-01 | Analiza wideo (przesyłanie z telefonu, osoby i twarze, przedmioty, opis AI, skan 3D) i kopie zapasowe przez most na Pi 4 (Pi 5 skonfigurowany; Zero 2W czekają). |
| 2026-11-01 | Wizja v3: 25 kl/s (ustawienie kamery), YOLOv8m/x do wyboru, nagrywanie z dwoma widokami, analiza nagrań na pełnych obrotach (PnP z głębią, ekran postępu z obciążeniem i temperaturami), strzałki w podglądzie 3D. Pi zrestartował się raz (zasilanie). |
| 2026-11-01 | Wizja v2: śledzenie i wybór obiektów, zdjęcia z adnotacjami (zoom, galeria), opis sceny, tryb Przestrzeń (głębia Hailo, skan 3D, przeglądarka „gra”). VNC włączony. Zasilacz za słaby (spadki napięcia). |
| 2026-11-01 | Pi 5 + AI HAT+ (Hailo-8) uruchomione; aplikacja „Łazik: wizja” na pulpicie Pi 5, sprawdzona na sprzęcie (YOLOv8s ~12 ms/klatkę, Hailo ~41 °C). |
| 2026-10-26 | Mapa projektu zrobiona z trzech plików dokumentacji i historii czatu; zapisana w `strona/mapa.html`. Na Pi jeszcze jej nie ma (brak `TS_AUTHKEY` w środowisku chmury). |
