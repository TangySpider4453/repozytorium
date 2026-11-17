# Przekazanie projektu „Łazik” do nowej rozmowy z Claude

> Wklej ten plik na początku nowej rozmowy. Piszemy po polsku. Szczegóły techniczne są w repozytorium
> `TangySpider4453/repozytorium`, gałąź **`lazik-mapa`** (niepołączona jeszcze z główną), plik `lazik/LAZIK.md`.
> **Hasła i kody dostępu NIE są w tym pliku** (repo jest publiczne): podaję je osobno w czacie.

## 1. Zasady pracy (ważne)
- Rozmowa po polsku. Użytkownik to uczeń; projekt szkolny.
- Repozytorium jest **publiczne**: nigdy nie zapisuj w nim haseł, kluczy, kodów dostępu, publicznego IP domu ani adresu
  tunelu Minecrafta. Nie używaj nazwiska nauczyciela.
- **Pi 4 (serwer domowy)**: działa na nim dużo usług (Minecraft: powernukkitx, playit, pi-dashboard, portal). Nic tam
  nie psuć, nie restartować bez pytania; dodawać tylko to, o co poproszono. Przed zmianami w portalu przeczytaj `SERWER.md`.
- Inne projekty w tym samym repo: „Nauka z Claude” (`PLAN.md`, kartkówki na stronie), „Progres sylwetki” (`PROGRES.md`,
  zdjęcia prywatne: tylko na Pi, nigdy w repo). `CLAUDE.md` mówi, co czytać przy którym projekcie.
- Każdą zmianę: wgrać na Pi, sprawdzić, dopisać do `lazik/LAZIK.md` (opis + tabela „Stan”), commit i push na `lazik-mapa`.
- Przed ruszaniem silnikami z daleka: zapytaj (łazik może stać na stole / w terenie).

## 2. Sprzęt
| Urządzenie | Rola | Dostęp |
|---|---|---|
| **Raspberry Pi 5 8 GB** + AI HAT+ **Hailo-8** (26 TOPS) | mózg łazika | Tailscale `rpi-5-1` (100.64.96.61), LAN dom 172.23.0.15, w terenie hotspot; użytkownik `rpi` |
| Raspberry Pi Zero 2W **a1** | stacja (LoRa) | Tailscale `rpi-zero2w-a1`, użytkownik `rpi` |
| Raspberry Pi Zero 2W **a2** | satelita | Tailscale `rpi-zero2w-a2`, użytkownik `rpi` |
| Raspberry Pi 4B | serwer domowy z NAS, portal ze stronami | `tonyg@raspberrypi` (172.23.0.20), Tailscale SSH w trybie „check” (wymaga zatwierdzenia linkiem) |

- Pi 5: Debian 13 trixie, Wayland labwc, ekran HDMI 1024×600 z dotykiem, VNC włączony. HailoRT 4.23 (`hailo-all`).
- Kamera: **Logitech C170** USB (640×480 MJPG, ~25 kl/s; obraz słaby, użytkownik niezadowolony).
- Napęd: **HW-094 (L298N)**, 2 silniki, bez enkoderów. Piny: lewy IN1/IN2 = GPIO17/27, PWM GPIO12; prawy IN3/IN4 = GPIO22/23,
  PWM GPIO13. W konfiguracji: `zamien_strony` = true, `odwroc_prawy` = true.
- I2C (piny 3/5, 3,3 V): **BME280** 0x76 (wilgotność podejrzanie wysoka), **MPU6050** żyroskop 0x68 (stoi pionowo).
  Wyświetlacz OLED 128×64 SSD1306 (0x3C) był podpięty, przyjmował komendy, ale matryca nie świeciła: **odłączony**,
  kupiony nowy (podłączyć VCC do 5 V). Magistrala I2C zawiesza się od zakłóceń silników (patrz §6).
- Bateria łazika: Li-Ion 7,4 V 850 mAh (mała). Radio DX-LR03 (UART, 433 MHz) jeszcze niepodłączone.
- Kamera łazika na wysokości ~10 cm.

## 3. Oprogramowanie na Pi 5 (wszystko w repo w `lazik/apki/…`, na Pi w `~/lazik/…`)
- **„Łazik: sterowanie”** (`apki/sterowanie/`, usługa systemd `lazik-sterowanie`, port 8000, autostart, ikona na pulpicie).
  Strona: `https://rpi-5-1.tail52831c.ts.net/` (HTTPS przez `tailscale serve`, potrzebne do pada Xbox) albo
  `http://<IP>:8000/`; pierwsze wejście z `?t=<kod>` (kod w `~/lazik/sterowanie/kod_dostepu.txt` na Pi, ciasteczko na rok).
  Pliki: `lazik_serwer.py` (Flask, API), `naped.py` (silniki, trzymanie toru, regulator obrotu), `tryby.py` (Stop,
  Ręczny, Przetrwaj, Zwiedzaj i skanuj, Fotograf, Śledź), `percepcja.py` (kamera, YOLO na Hailo, głębia scdepthv3,
  przepływ optyczny), `przeszkody.py` (koniec podłogi z głębi w cm, obiekty, czas do zderzenia), `cel.py` (śledzenie
  jednego celu: wygląd + tracker KCF), `zyroskop.py` (MPU6050, kurs względny, przechył), `bme280.py`,
  `wyswietlacz.py` (OLED/LCD stanu, wykrywany sam), `i2c_straz.py` (samo odblokowanie zawieszonego I2C),
  `ustawienia.py` (wszystkie ustawienia z zakresami → zakładki ⚙ na stronie), `strona.html` (cała strona).
- **„Łazik: wizja”** (`apki/wizja/`, Qt, ikona): podgląd z Hailo, zdjęcia z adnotacjami, opis sceny, tryb Przestrzeń
  (skan 3D), przeglądarka 3D. Modele: yolov8s/m/x_h8, scdepthv3 (głębia względna).
- **„Łazik: analiza wideo”** (`apki/analiza/`, Qt + usługa `lazik-wideo`, port 8080): wysyłanie filmów z telefonu (QR),
  osoby i twarze, przedmioty, opis AI (Ollama gemma3:4b na CPU, ~2 min/klatkę), skan 3D z filmu.
- **Kopie zapasowe** (`lazik/kopie/`): Pi 5, a1, a2 → przez most na Pi 4 (forced-command SSH) na NAS
  `/mnt/nas/Raspberry/Kopie-lazika/<pi>/`, co tydzień (timer co godzinę sprawdza zaległość), 3 ostatnie. Stan na stronie
  Pi 4 `strony/lazik/kopie.html` (z `lazik-stan.service` na Pi 4).
- Strony projektu na Pi 4 (`~/portal/sites/lazik/`, kopia w `lazik/strona/`): `index.html`, `zakupy.html`, `mapa.html`
  (mapa projektu), `kopie.html`.

## 4. Sterowanie: co już działa (stan na 2026-11-03/16)
- Widoki: zwykły / kokpit (przyciski gazu i skrętu, wielodotyk) / pełny ekran (pad Xbox albo klawiatura). Pełny ekran:
  przezroczysty zwijany panel z prawej, telemetria jako napisy na dole obrazu (silniki L/P z kierunkiem i mocą, kurs,
  temperatury CPU/Hailo/otoczenie w kolorach, obciążenie, odległość z przodu, kl/s).
- Szybkie przełączniki: analiza na Hailo (Obiekty, Głębia; w trybach jazdy wymuszone) i nakładki (Ramki, Podpisy,
  Przeszkody, Horyzont, Napisy).
- Pad: Start = Ręczny, B = STOP, X = tryb mocy (z ustawień / spusty / wychylenie gałki / pełna), Y = zeruj kurs.
  Spusty działają w każdym trybie (RT przód, LT tył, liniowo). Zapas gałki 20° od pionu = jazda prosto.
  Wysyłka poleceń ograniczona (~10/s, jedno w drodze). Strona sama się przeładowuje po aktualizacji (pole `wersja`).
  `/api/pad` pokazuje, co przeglądarka widzi z pada (diagnoza spustów na iPadzie Safari, jeszcze niepotwierdzona).
- Żyroskop: trzymanie toru (PID, P 0,09 / D 0,008 / maks. 0,9, zwalnianie przy odchyleniu > 5°), skręt ze stałą
  prędkością obrotu (gałka = °/s, maks. 90), bezpiecznik odwróconego żyroskopu, STOP przy przechyle > 40°.
  Powrót na linię toru po wyboju: zrobiony, ale **wyłączony** (użytkownik chce natychmiastowego powrotu do kąta).
- Przeszkody: koniec podłogi z głębi → cm (wysokość kamery 10 cm, horyzont 0,5, FOV 48°), obiekty YOLO na podłodze,
  czas do zderzenia z przepływu, uderzenie z akcelerometru, utknięcie. Omijanie: cofnij + obrót o kąt żyroskopem;
  4 omijania w 12 s = zawróć. Kamera nie widzi podłogi bliżej niż ~30 cm (pokazuje „≤ 30 cm”). Nie wykrywa krawędzi stołu.
- Śledź: zablokowany cel (wygląd + KCF), zawsze YOLOv8s, podjeżdża na 60 cm (odległość z dolnej krawędzi ramki).
- Obroty we wszystkich trybach wolniejsze (moc obrotu 0,5).
- Bezpieczeństwo: polecenie ważne 0,6 s; brak strony 3 s = STOP; STOP trybów przy temperaturze > 82 °C; po 120 s
  bezczynności proces kończy się (zwalnia Hailo), systemd go wznawia.

## 5. Jak poprzednia sesja łączyła się z Pi (środowisko chmurowe Claude Code)
- Tailscale w kontenerze w trybie userspace (`tailscaled --tun=userspace-networking`), stan zapisany w scratchpadzie,
  SSH przez `ProxyCommand tailscale nc %h %p`; logowanie hasłem przez `sshpass` (klucza nie wolno było dopisywać na stałe).
  **W nowym koncie trzeba od nowa dodać kontener do Tailscale** (link logowania albo klucz od użytkownika).
- Pi 4 przez Tailscale SSH w trybie check: każde połączenie wymaga zatwierdzenia linkiem; linki podawać dopiero, gdy
  użytkownik jest gotowy (wygasają).

## 6. Otwarte sprawy / do zrobienia
- **I2C zawiesza się podczas jazdy** (zakłócenia od silników; strażnik odblokowuje po 0,6 s). Zalecone: przewody I2C z dala
  od silników, krótkie i skręcone, **kondensatory 100 nF na silnikach**, ewentualnie zwolnić I2C do 50 kHz
  (`dtparam=i2c_arm_baudrate=50000` w `/boot/firmware/config.txt` + restart, zrobić dopiero za zgodą).
- Potwierdzić na iPadzie (Safari), że spusty działają po przeładowaniu strony (`/api/pad`).
- Sprawdzić na sprzęcie: kierunek żyroskopu (obrót w prawo = kurs rośnie), nastawy toru (kiwanie?), prędkość przy pełnej
  mocy (`predkosc_pelna_ms`), odległości przeszkód i Śledź w praktyce.
- Nowy wyświetlacz OLED: podłączyć (VCC 5 V, SDA pin 3, SCL pin 5), program wykryje sam.
- Radio DX-LR03 na UART (piny 8/10) do podłączenia i włączenia UART.
- Gałąź `lazik-mapa` niepołączona z główną (pytano użytkownika, brak decyzji).
- Pomysły: laserowy czujnik odległości VL53L1X (pewne przeszkody z bliska), BNO085 (prawdziwy kompas).
- **Następny duży temat: iPhone 14 Pro (LiDAR) jako kamera głębi** zamiast C170 na próbę: najpierw darmowa apka do
  skanowania (3D Scanner App / Scaniverse / Polycam) dla oceny jakości, potem **Record3D** (strumień RGB + głębia +
  pozycja ARKit przez USB/Wi-Fi, biblioteka Python na Linuksie) jako dodatkowe źródło w `percepcja.py`: przeszkody
  z metrycznej głębi, prawdziwa mapa 3D, odometria z pozycji ARKit. Ograniczenia: zasięg ~5 m, słońce, zasilanie
  i grzanie telefonu, uchwyt. Jeśli test wyjdzie dobrze: kupić kamerę głębi (OAK-D Lite na zewnątrz, RealSense D435,
  ewentualnie ToF Arducam do wnętrz).

## 7. Najważniejsze liczby z testów
- Kamera 25 kl/s; YOLOv8s ~10 ms, v8m ~32 ms, v8x ~74 ms na Hailo; głębia scdepthv3 ~5–9 ms.
- Koszulka z ~20 cm: stara metoda „wolne”, nowa 30–40 cm (dolna granica pomiaru).
- Pad: przed poprawką ~70 poleceń/s, po ~10/s.
- Żyroskop (symulacja): szturchnięcie 45° → z powrotem w 0,34 s; wybój pchający koło 1,2 s → odchylenie najwyżej 6°.
- Śledzenie: zamiana numerów przy mijaniu się dwóch osób → zostaje na właściwej (test na Pi, 7 ms/klatkę).
- Kopia Pi 5: 2,3 GB w 4 min.
