"""Ustawienia „Łazik: sterowanie”: opis każdego pola (zakładka, typ, zakres, podpis, podpowiedź) i wartości domyślne.
Strona buduje z tego formularze, a serwer sprawdza nadsyłane wartości. Zapis: konfiguracja.json.
Regulacje kamery (jasność, kontrast, ekspozycja…) czytane są z samej kamery przez v4l2-ctl, bo każda ma inne."""

import json
import os
import re
import subprocess

# (klucz, zakładka, typ, domyślnie, opcje, podpis, podpowiedź); opcje: (min, max, krok) albo [(wartość, opis), …]
POLA = [
    ("kamera_rozdzielczosc", "Kamera", "wybor", "640x480",
     [("320x240", "320×240 (najszybciej)"), ("640x480", "640×480 (zalecane, 25–30 kl/s)"), ("800x480", "800×480"),
      ("1024x768", "1024×768 (ostrzej, ~20 kl/s)")], "Rozdzielczość", "Wyższa = ostrzej, ale mniej klatek i więcej danych."),
    ("kamera_fps", "Kamera", "wybor", 30, [(15, "15 kl/s"), (30, "30 kl/s")], "Klatki kamery", ""),
    ("kamera_stale_kl_s", "Kamera", "tak_nie", True, None, "Stała liczba klatek",
     "Wyłącza wydłużanie naświetlania w słabym świetle (kamera nie zwalnia, za to obraz bywa ciemniejszy)."),
    ("obrot", "Kamera", "wybor", 0, [(0, "bez obrotu"), (180, "180° (kamera do góry nogami)")], "Obrót obrazu", ""),
    ("lustro", "Kamera", "tak_nie", False, None, "Odbicie lustrzane", ""),

    ("model_obiektow", "Wizja i Hailo", "wybor", 0, [(0, "YOLOv8s: szybki (~10 ms)"), (1, "YOLOv8m: dokładniejszy (~32 ms)"),
                                                     (2, "YOLOv8x: najdokładniejszy (~74 ms)")],
     "Model rozpoznawania", "Większy model widzi więcej i pewniej, ale daje mniej klatek i grzeje Hailo."),
    ("prog_pewnosci", "Wizja i Hailo", "suwak", 0.45, (0.2, 0.9, 0.05), "Próg pewności",
     "Poniżej tej pewności obiekt jest pomijany."),
    ("glebia_zawsze", "Wizja i Hailo", "tak_nie", False, None, "Głębia także bez trybu",
     "Liczy głębię i paski wolnego miejsca również w trybie Stop i Ręcznym."),
    ("strumien_glebia", "Wizja i Hailo", "tak_nie", False, None, "Podgląd: obraz + mapa głębi",
     "Strumień pokazuje obok siebie obraz i kolorową mapę głębi (wymaga liczenia głębi)."),
    ("maks_kl_s", "Wizja i Hailo", "suwak", 30, (2, 30, 1), "Limit klatek przetwarzania",
     "Mniej klatek = chłodniejszy Hailo i procesor, mniejszy pobór prądu."),
    ("jakosc_strumienia", "Wizja i Hailo", "suwak", 70, (30, 95, 5), "Jakość podglądu (JPEG)",
     "Niższa = mniej danych przez WiFi/Tailscale."),
    ("szer_strumienia", "Wizja i Hailo", "wybor", 640, [(320, "320 px"), (480, "480 px"), (640, "640 px"), (1024, "1024 px")],
     "Szerokość podglądu", "Podgląd zmniejszany przed wysłaniem (rozpoznawanie liczy na pełnej klatce)."),
    ("zwolnij_hailo_po_s", "Wizja i Hailo", "suwak", 120, (30, 900, 30), "Zwalnianie Hailo i kamery po [s]",
     "Bez strony i w trybie Stop usługa oddaje Hailo i kamerę innym aplikacjom."),

    ("maks_moc", "Napęd", "suwak", 0.7, (0.3, 1.0, 0.05), "Maks. moc silników", ""),
    ("min_moc", "Napęd", "suwak", 0.35, (0.0, 0.6, 0.05), "Min. moc (próg ruszania)",
     "L298N poniżej ~30–40% tylko buczy; małe polecenia są podnoszone do tej wartości."),
    ("odwroc_lewy", "Napęd", "tak_nie", False, None, "Odwróć lewy silnik", "Gdy „▲” kręci lewym kołem do tyłu."),
    ("odwroc_prawy", "Napęd", "tak_nie", False, None, "Odwróć prawy silnik", ""),
    ("zamien_strony", "Napęd", "tak_nie", False, None, "Zamień strony", "Gdy „◀” skręca w prawo."),

    ("trzymaj_tor", "Żyroskop", "tak_nie", True, None, "Trzymaj tor przy jeździe prosto",
     "Żyroskop pilnuje kierunku i sam wyrównuje moc stron, żeby łazik nie zbaczał (ręcznie i w trybach)."),
    ("tor_kp", "Żyroskop", "suwak", 0.03, (0.005, 0.1, 0.005), "Siła korekty (P)",
     "Ile skrętu na 1° odchyłki. Za dużo = łazik się wężykuje, za mało = powoli wraca na kurs."),
    ("tor_ki", "Żyroskop", "suwak", 0.02, (0.0, 0.1, 0.005), "Wyrównywanie stałego znoszenia (I)",
     "Uczy się, że jeden silnik jest słabszy, i stale to wyrównuje."),
    ("tor_kd", "Żyroskop", "suwak", 0.004, (0.0, 0.02, 0.001), "Tłumienie (D)", "Uspokaja wężykowanie."),
    ("tor_maks_korekta", "Żyroskop", "suwak", 0.35, (0.1, 0.6, 0.05), "Maks. korekta", "Największa różnica mocy dodawana przez korektę."),
    ("zyro_odwroc", "Żyroskop", "tak_nie", False, None, "Odwróć kierunek obrotu",
     "Tylko gdy kurs rośnie przy skręcie w LEWO (zwykle wykrywa się samo z grawitacji)."),

    ("prog_przeszkody", "Tryby", "suwak", 0.45, (0.2, 0.8, 0.05), "Czułość na przeszkody",
     "Wyżej = wcześniej uznaje coś za przeszkodę (ostrożniej)."),
    ("sledzenie_wysokosc", "Tryby", "suwak", 0.5, (0.2, 0.8, 0.05), "Odległość przy śledzeniu",
     "Docelowa wysokość celu w kadrze: większa = bliżej."),
    ("predkosc_zwiedzania", "Tryby", "suwak", 0.55, (0.3, 1.0, 0.05), "Prędkość zwiedzania", ""),
    ("fotograf_co_ile_s", "Tryby", "suwak", 180, (30, 900, 30), "Fotograf: ten sam rodzaj co [s]", ""),
    ("rozgladanie_co_s", "Tryby", "suwak", 8, (3, 60, 1), "Przetrwaj: rozglądanie co [s]", ""),

    ("stop_bez_strony_s", "Bezpieczeństwo", "suwak", 3, (1, 15, 1), "STOP bez strony po [s]",
     "Gdy strona przestanie się odzywać (zamknięta, utracone WiFi), łazik staje."),
    ("maks_temp", "Bezpieczeństwo", "suwak", 82, (60, 90, 1), "STOP trybów przy temperaturze [°C]",
     "Gdy procesor albo Hailo przekroczy tę temperaturę, tryby automatyczne się zatrzymują."),
    ("maks_przechyl", "Bezpieczeństwo", "suwak", 40, (15, 80, 5), "STOP przy przechyle [°]",
     "Żyroskop: gdy łazik przechyli się albo przewróci bardziej niż tyle, silniki stają (także w jeździe ręcznej)."),
]
DOMYSLNE = {p[0]: p[3] for p in POLA}
DOMYSLNE.update(port=8000, kamera_v4l2={},
                piny={"lewy_przod": 17, "lewy_tyl": 27, "lewy_pwm": 12, "prawy_przod": 22, "prawy_tyl": 23, "prawy_pwm": 13})


def wczytaj(plik):
    k = dict(DOMYSLNE)
    if os.path.exists(plik):
        k.update(json.load(open(plik, encoding="utf-8")))
    return k


def zapisz(plik, konf):
    tmp = plik + ".tmp"
    json.dump(konf, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, plik)


def schemat():
    return [dict(klucz=k, zakladka=z, typ=t, opcje=o, podpis=p, podpowiedz=h, domyslnie=d) for k, z, t, d, o, p, h in POLA]


def sprawdz(klucz, wartosc):
    """Wartość po sprawdzeniu albo ValueError."""
    pole = next((p for p in POLA if p[0] == klucz), None)
    if pole is None:
        raise ValueError(f"nieznane ustawienie {klucz}")
    _, _, typ, dom, opcje, _, _ = pole
    if typ == "tak_nie":
        return bool(wartosc)
    if typ == "suwak":
        mn, mx, _ = opcje
        v = max(mn, min(mx, float(wartosc)))
        return int(round(v)) if isinstance(dom, int) else round(v, 3)
    if typ == "wybor":
        for v, _ in opcje:
            if str(v) == str(wartosc):
                return v
        raise ValueError(f"niedozwolona wartość {wartosc} dla {klucz}")
    raise ValueError(klucz)


# ---------- regulacje kamery (v4l2) ----------

def kontrolki_kamery(urzadzenie):
    """Lista regulacji z `v4l2-ctl --list-ctrls-menus`: nazwa, typ, min, max, krok, domyślnie, wartość, menu, nieaktywna."""
    try:
        out = subprocess.run(["v4l2-ctl", "-d", urzadzenie, "--list-ctrls-menus"], capture_output=True, text=True,
                             timeout=5).stdout
    except Exception:
        return []
    wynik, ost = [], None
    for linia in out.splitlines():
        m = re.match(r"\s*(\w+)\s+0x[0-9a-f]+\s+\((\w+)\)\s*:\s*(.*)", linia)
        if m:
            nazwa, typ, reszta = m.groups()
            pola = dict(re.findall(r"(\w+)=(-?\w+)", reszta))
            ost = dict(nazwa=nazwa, typ=typ, min=int(pola.get("min", 0)), max=int(pola.get("max", 1)),
                       krok=int(pola.get("step", 1)), domyslnie=int(pola.get("default", 0)),
                       wartosc=int(pola.get("value", 0)), nieaktywna="inactive" in reszta, menu=[])
            wynik.append(ost)
            continue
        m = re.match(r"\s+(\d+):\s*(.+)", linia)
        if m and ost is not None and ost["typ"] == "menu":
            ost["menu"].append((int(m.group(1)), m.group(2).strip()))
    return wynik


def ustaw_kontrolke(urzadzenie, nazwa, wartosc):
    if not re.fullmatch(r"\w+", nazwa):
        raise ValueError("zła nazwa")
    r = subprocess.run(["v4l2-ctl", "-d", urzadzenie, "-c", f"{nazwa}={int(wartosc)}"], capture_output=True, text=True,
                       timeout=5)
    if r.returncode != 0:
        raise ValueError(r.stderr.strip() or "kamera odrzuciła ustawienie")


PODPISY_KAMERY = {
    "brightness": "Jasność", "contrast": "Kontrast", "saturation": "Nasycenie", "hue": "Odcień", "gamma": "Gamma",
    "gain": "Wzmocnienie", "sharpness": "Ostrość", "backlight_compensation": "Kompensacja tła",
    "white_balance_automatic": "Automatyczny balans bieli", "white_balance_temperature": "Temperatura barwowa",
    "power_line_frequency": "Częstotliwość sieci (migotanie)", "auto_exposure": "Ekspozycja",
    "exposure_time_absolute": "Czas naświetlania", "exposure_dynamic_framerate": "Dynamiczna liczba klatek",
    "focus_automatic_continuous": "Autofokus", "focus_absolute": "Ostrość ręczna", "zoom_absolute": "Zoom",
}
