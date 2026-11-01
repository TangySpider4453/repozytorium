#!/usr/bin/env python3
"""Łazik: wizja. Kamera USB + rozpoznawanie obiektów na Hailo, pełny ekran.

- Przełącznik „Rozpoznawanie”: Hailo pracuje tylko, gdy jest włączony (wyłączenie zwalnia chip).
- Każdy obiekt dostaje numer (proste śledzenie po nakładaniu ramek) i jest na liście w panelu.
- Dotknięcie obiektu (na obrazie albo na liście) pokazuje tylko jego; przycisk „cała klasa” pokazuje wszystkie
  obiekty tej klasy. Dotknięcie pustego miejsca czyści wybór.
- „Zdjęcie” otwiera stop-klatkę z adnotacjami: przybliżanie dwoma palcami / kółkiem / przyciskami, przesuwanie,
  podpisy w stałym rozmiarze ustawiane poza ramką obiektu. „Zapisz” zapisuje do ~/lazik/wizja/zdjecia/
  (surowe .jpg, _ramki.png i .json). „Galeria” przegląda zapisane zdjęcia.
- Panel: CPU, RAM, Hailo (obciążenie ≈ część sekundy spędzona na inferencji), temperatury, zasilanie.
- Krzyżyk w rogu albo Esc zamyka. `--rozpoznawanie` startuje z włączonym Hailo (do testów).
"""

import glob
import json
import os
import subprocess
import sys
import threading
import time

import cv2
import przestrzen as P
from PyQt5.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (QAbstractButton, QApplication, QButtonGroup, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QProgressBar, QPushButton, QScroller, QSlider, QStackedWidget,
                             QVBoxLayout, QWidget)

KATALOG = os.path.dirname(os.path.abspath(__file__))
ZDJECIA = os.path.join(KATALOG, "zdjecia")

MODELE = [  # pierwszy, który się wczyta na tym chipie (Hailo-8 albo Hailo-8L)
    "/usr/share/hailo-models/yolov8s_h8.hef",
    "/usr/share/hailo-models/yolov8s_h8l.hef",
    "/usr/share/hailo-models/yolov6n_h8.hef",
    "/usr/share/hailo-models/yolov6n_h8l.hef",
]
HAILO_MAKS_TEMP = 85  # powyżej rozpoznawanie samo się wyłącza

KLASY = [  # COCO 80, po polsku
    "osoba", "rower", "samochód", "motocykl", "samolot", "autobus", "pociąg", "ciężarówka", "łódź",
    "sygnalizator", "hydrant", "znak stop", "parkometr", "ławka", "ptak", "kot", "pies", "koń", "owca",
    "krowa", "słoń", "niedźwiedź", "zebra", "żyrafa", "plecak", "parasol", "torebka", "krawat", "walizka",
    "frisbee", "narty", "snowboard", "piłka", "latawiec", "kij baseballowy", "rękawica baseballowa",
    "deskorolka", "deska surfingowa", "rakieta tenisowa", "butelka", "kieliszek", "kubek", "widelec", "nóż",
    "łyżka", "miska", "banan", "jabłko", "kanapka", "pomarańcza", "brokuł", "marchewka", "hot dog", "pizza",
    "pączek", "ciasto", "krzesło", "kanapa", "roślina", "łóżko", "stół", "toaleta", "telewizor", "laptop",
    "myszka", "pilot", "klawiatura", "telefon", "mikrofalówka", "piekarnik", "toster", "zlew", "lodówka",
    "książka", "zegar", "wazon", "nożyczki", "miś", "suszarka", "szczoteczka",
]


def nazwa(klasa):
    return KLASY[klasa] if 0 <= klasa < len(KLASY) else str(klasa)


def kolor_klasy(klasa):
    return QColor.fromHsv((klasa * 47) % 360, 190, 255)


def slug(tekst):
    tab = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ ", "acelnoszzACELNOSZZ-")
    return "".join(c for c in tekst.translate(tab).lower() if c.isalnum() or c == "-")


# ---------- kamera ----------

def znajdz_kamere_usb():
    """Na Pi 5 /dev/video0.. bywają węzłami kamery CSI i ISP; szukamy pierwszego węzła przechwytywania z USB."""
    def nr(p):
        return int(p.rsplit("video", 1)[1])
    for p in sorted(glob.glob("/sys/class/video4linux/video*"), key=nr):
        try:
            usb = "/usb" in os.path.realpath(p + "/device")
            idx = open(p + "/index").read().strip()
        except OSError:
            continue
        if usb and idx == "0":
            return nr(p)
    return 0


class Kamera(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.lock = threading.Lock()
        self.klatka, self.nr_klatki = None, 0
        self.stan, self.fps = "szukam kamery…", 0.0
        self.dziala = True

    def najnowsza(self):
        with self.lock:
            return self.klatka, self.nr_klatki

    def run(self):
        while self.dziala:
            dev = znajdz_kamere_usb()
            cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
            if not cap.isOpened():
                self.stan = f"brak kamery USB (/dev/video{dev})"
                time.sleep(2)
                continue
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_FPS, 30)
            w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.stan = f"/dev/video{dev} · {w}×{h}"
            t0, n = time.monotonic(), 0
            while self.dziala:
                ok, f = cap.read()
                if not ok:
                    self.stan = "kamera przestała odpowiadać"
                    break
                with self.lock:
                    self.klatka, self.nr_klatki = f, self.nr_klatki + 1
                n += 1
                if time.monotonic() - t0 >= 1:
                    self.fps, t0, n = n / (time.monotonic() - t0), time.monotonic(), 0
            cap.release()
            time.sleep(1)


# ---------- śledzenie ----------

def iou(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    wsp = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    suma = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - wsp
    return wsp / suma if suma > 0 else 0.0


class Sledzenie:
    """Łączy wykrycia z kolejnych klatek po nakładaniu się ramek tej samej klasy; obiekt znika po 1 s bez wykrycia."""

    def __init__(self):
        self.obiekty, self.nastepny = {}, 1

    def aktualizuj(self, wykrycia, teraz):
        pary = sorted(((iou(o["ramka"], w[1:5]), oid, i)
                       for oid, o in self.obiekty.items()
                       for i, w in enumerate(wykrycia) if o["klasa"] == w[0]), reverse=True)
        uzyte_o, uzyte_w, wynik = set(), set(), []
        for wsp, oid, i in pary:
            if wsp < 0.25 or oid in uzyte_o or i in uzyte_w:
                continue
            uzyte_o.add(oid)
            uzyte_w.add(i)
            self.obiekty[oid].update(ramka=wykrycia[i][1:5], pew=wykrycia[i][5], ostatnio=teraz)
            wynik.append(oid)
        for i, w in enumerate(wykrycia):
            if i not in uzyte_w:
                self.obiekty[self.nastepny] = dict(klasa=w[0], ramka=w[1:5], pew=w[5], od=teraz, ostatnio=teraz)
                wynik.append(self.nastepny)
                self.nastepny += 1
        for oid in [k for k, o in self.obiekty.items() if teraz - o["ostatnio"] > 1.0]:
            del self.obiekty[oid]
        return [dict(id=oid, klasa=self.obiekty[oid]["klasa"], ramka=self.obiekty[oid]["ramka"],
                     pew=self.obiekty[oid]["pew"], od=self.obiekty[oid]["od"]) for oid in sorted(wynik)]


# ---------- Hailo ----------

class Detektor(threading.Thread):
    """Modele wczytują się przy pierwszym włączeniu i zostają na chipie (oba mieszczą się naraz). Wyłączenie
    przełącznika przestaje wysyłać klatki, więc Hailo stoi bezczynnie. Zwalnianie urządzenia w trakcie pracy
    jest w HailoRT 4.23 + picamera2 zawodne (crash przy sprzątaniu), dlatego go nie robimy."""

    def __init__(self, kamera):
        super().__init__(daemon=True)
        self.kamera = kamera
        self.wlaczony = threading.Event()
        self.lock = threading.Lock()
        self.wyniki, self.klatka_wynikow = [], None
        self.stan, self.model = "wyłączone", None
        self.fps = self.ms = self.obciazenie = 0.0
        self.temp = None
        self.prog = 0.5
        self.dziala = True
        self.hailo = None
        self.sledzenie = Sledzenie()
        self.tryb = "obiekty"          # albo "przestrzen" (głębia i skan 3D)
        self.zaladowany = None         # tryb, który teraz liczy (None = bezczynnie)
        self._dev_temp = None          # stały uchwyt do chipu do odczytu temperatury
        self.glebia = P.Glebia()
        self.skaner = P.Skaner()
        self.skanuj = False
        self.lock_skan = threading.Lock()
        self.glebia_wynik = None       # (klatka, mapa głębi)

    def _zaladuj(self):
        if self.tryb == "obiekty" and self.hailo is not None:
            self.zaladowany = "obiekty"
            return
        if self.tryb == "przestrzen":
            self.glebia.zaladuj()
            self.model = self.glebia.nazwa
            self.skaner.metryczna = self.glebia.metryczna
            self.zaladowany = "przestrzen"
            return
        try:
            from picamera2.devices import Hailo
        except Exception as e:  # brak hailo-all / picamera2
            raise RuntimeError(f"brak biblioteki Hailo ({e.__class__.__name__})")
        bledy = []
        for sciezka in MODELE:
            if not os.path.exists(sciezka):
                continue
            try:
                self.hailo = Hailo(sciezka)
                self.model = os.path.basename(sciezka)
                self.zaladowany = "obiekty"
                return
            except Exception as e:
                bledy.append(f"{os.path.basename(sciezka)}: {e}")
        raise RuntimeError("nie wczytano modelu; " + ("; ".join(bledy) or "brak plików w /usr/share/hailo-models"))

    def _zwolnij(self):
        """Wstrzymuje liczenie (modele zostają wczytane, chip jest bezczynny)."""
        self.model, self.zaladowany = None, None
        with self.lock:
            self.wyniki, self.klatka_wynikow, self.glebia_wynik = [], None, None
        self.sledzenie = Sledzenie()
        self.fps = self.ms = self.obciazenie = 0.0
        with self.lock:
            self.wyniki, self.klatka_wynikow, self.glebia_wynik = [], None, None
        self.sledzenie = Sledzenie()
        self.fps = self.ms = self.obciazenie = 0.0

    def _odczytaj_temp(self):
        try:
            if self._dev_temp is None:
                self._dev_temp = (self.hailo or self.glebia.hailo).target.get_physical_devices()[0]
            t = self._dev_temp.control.get_chip_temperature()
            self.temp = max(t.ts0_temperature, t.ts1_temperature)
        except Exception:
            self.temp = None

    def najnowsze(self):
        """(wyniki, klatka, na której je policzono)"""
        with self.lock:
            return list(self.wyniki), self.klatka_wynikow

    def run(self):
        ostatnia, okno_t0, zajety, n, temp_t = -1, time.monotonic(), 0.0, 0, 0.0
        while self.dziala:
            if self.zaladowany is not None and (not self.wlaczony.is_set() or self.zaladowany != self.tryb):
                self._zwolnij()
            if not self.wlaczony.is_set():
                if not self.stan.startswith("błąd"):
                    self.stan = "wyłączone"
                if self._dev_temp is not None and time.monotonic() - temp_t >= 2:
                    self._odczytaj_temp()
                    temp_t = time.monotonic()
                time.sleep(0.1)
                continue
            if self.zaladowany is None:
                self.stan = "ładuję model…"
                try:
                    self._zaladuj()
                except Exception as e:
                    self.stan = f"błąd: {e}"
                    self.wlaczony.clear()
                    continue
                self.stan = f"działa · {self.model}"
            klatka, nr = self.kamera.najnowsza()
            if klatka is None or nr == ostatnia:
                time.sleep(0.005)
                continue
            ostatnia = nr
            t0 = time.monotonic()
            try:
                if self.zaladowany == "przestrzen":
                    glebia = self.glebia.licz(klatka)
                else:
                    mh, mw, _ = self.hailo.get_input_shape()
                    wynik = self.hailo.run(cv2.resize(cv2.cvtColor(klatka, cv2.COLOR_BGR2RGB), (mw, mh)))
            except Exception as e:
                self.stan = f"błąd: {e}"
                self.wlaczony.clear()
                continue
            dt = time.monotonic() - t0
            teraz = time.monotonic()
            if self.zaladowany == "przestrzen":
                if self.skanuj:
                    with self.lock_skan:
                        self.skaner.krok(klatka, glebia)
                with self.lock:
                    self.glebia_wynik = (klatka, glebia)
            else:
                wykryte = []
                for klasa, dets in enumerate(wynik):  # model z NMS: lista na klasę, [y0, x0, y1, x1, pewność]
                    for d in dets:
                        if d[4] >= self.prog:
                            wykryte.append((klasa, float(d[1]), float(d[0]), float(d[3]), float(d[2]), float(d[4])))
                sledzone = self.sledzenie.aktualizuj(wykryte, teraz)
                with self.lock:
                    self.wyniki, self.klatka_wynikow = sledzone, klatka
            zajety += dt
            n += 1
            if teraz - okno_t0 >= 1:
                okres = teraz - okno_t0
                self.obciazenie = min(100.0, 100 * zajety / okres)
                self.fps, self.ms = n / okres, 1000 * zajety / max(n, 1)
                okno_t0, zajety, n = teraz, 0.0, 0
            if teraz - temp_t >= 2 and (self.hailo or self.glebia.hailo) is not None:
                self._odczytaj_temp()
                temp_t = teraz
                if self.temp is not None and self.temp >= HAILO_MAKS_TEMP:
                    self.stan = f"błąd: Hailo {self.temp:.0f} °C, wyłączam (przegrzanie)"
                    self.wlaczony.clear()
        self._zwolnij()


# ---------- system ----------

class System:
    def __init__(self):
        self._cpu = self._czytaj_cpu()
        self.cpu = self.ram_proc = self.ram_uzyte = self.ram_razem = 0.0
        self.temp = None
        self.zasilanie = "?"
        self._zas_t = 0.0

    @staticmethod
    def _czytaj_cpu():
        v = [int(x) for x in open("/proc/stat").readline().split()[1:]]
        return sum(v), v[3] + v[4]

    def odswiez(self):
        razem, bezczyn = self._czytaj_cpu()
        dr, db = razem - self._cpu[0], bezczyn - self._cpu[1]
        self._cpu = (razem, bezczyn)
        self.cpu = 100.0 * (1 - db / dr) if dr else 0.0
        mem = {}
        for linia in open("/proc/meminfo"):
            k, v = linia.split(":")
            mem[k] = int(v.split()[0])
        self.ram_razem = mem["MemTotal"] / 1048576
        self.ram_uzyte = (mem["MemTotal"] - mem["MemAvailable"]) / 1048576
        self.ram_proc = 100 * self.ram_uzyte / self.ram_razem
        try:
            self.temp = int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000
        except OSError:
            self.temp = None
        if time.monotonic() - self._zas_t > 5:
            self._zas_t = time.monotonic()
            try:
                out = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=2).stdout
                bity = int(out.strip().split("=")[1], 16)
                if bity & 0x1:
                    self.zasilanie = "ZA NISKIE napięcie teraz"
                elif bity & 0x4:
                    self.zasilanie = "dławienie teraz"
                elif bity & 0x50000:
                    self.zasilanie = "były spadki od startu"
                else:
                    self.zasilanie = "OK"
            except Exception:
                self.zasilanie = "?"


# ---------- rysowanie adnotacji (wspólne dla podglądu na żywo, przeglądarki i zapisu) ----------

TLO, PANEL, TEKST, SZARY, ZIELONY, ZOLTY, CZERWONY = (
    "#0d1114", "#161c21", "#e6ebee", "#8b979f", "#3fbf6a", "#e0a640", "#e5534b")


def etykieta(o):
    return f"#{o['id']} {nazwa(o['klasa'])} {o['pew'] * 100:.0f}%"


def _wspolne(a, b):
    w = min(a.right(), b.right()) - max(a.left(), b.left())
    h = min(a.bottom(), b.bottom()) - max(a.top(), b.top())
    return w * h if w > 0 and h > 0 else 0.0


def _wsun(r, widok):
    """Przesuwa prostokąt etykiety do środka widocznego obszaru."""
    x = min(max(r.left(), widok.left()), widok.right() - r.width())
    y = min(max(r.top(), widok.top()), widok.bottom() - r.height())
    return QRectF(x, y, r.width(), r.height())


def ramka_na_ekranie(o, obraz):
    x0, y0, x1, y1 = o["ramka"]
    return QRectF(obraz.left() + x0 * obraz.width(), obraz.top() + y0 * obraz.height(),
                  (x1 - x0) * obraz.width(), (y1 - y0) * obraz.height())


def rysuj_adnotacje(p, obraz, obiekty, widok, px, wybrany=None):
    """obraz: prostokąt, w którym leży cały obraz (po przybliżeniu może wychodzić poza widok);
    px: wysokość czcionki w pikselach ekranu, niezależna od przybliżenia, więc podpis zawsze jest czytelny.
    Etykieta trafia w miejsce, które najmniej zasłania własny obiekt, inne ramki i inne etykiety."""
    f = QFont("Sans")
    f.setPixelSize(int(px))
    f.setBold(True)
    p.setFont(f)
    fm = p.fontMetrics()
    p.setRenderHint(QPainter.Antialiasing)
    ramki = [(o, ramka_na_ekranie(o, obraz)) for o in obiekty]
    ramki = [(o, r) for o, r in ramki if r.intersects(widok)]
    gr = max(2.0, px / 7)
    for o, r in ramki:
        kol = kolor_klasy(o["klasa"])
        if wybrany is not None and o["id"] == wybrany:
            p.setPen(QPen(QColor("#ffffff"), gr * 2.4))
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
        p.setPen(QPen(kol, gr))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)
    pole_widoku = widok.width() * widok.height()

    def tlo_duze(rr):  # ramka zajmująca dużą część widoku (np. autobus) to tło, nie przeszkoda dla podpisu
        return _wspolne(rr, widok) > 0.35 * pole_widoku

    postawione = []
    m = px * 0.15
    for o, r in sorted(ramki, key=lambda x: (x[0]["id"] != wybrany, x[1].width() * x[1].height())):
        tekst = etykieta(o)
        tw, th = fm.horizontalAdvance(tekst) + px * 0.7, fm.height() + px * 0.3
        pelna, r = r, r.intersected(widok)  # po przybliżeniu podpis trzyma się widocznej części obiektu
        kandydaci = [
            QRectF(r.left(), r.top() - th - m, tw, th), QRectF(r.right() - tw, r.top() - th - m, tw, th),
            QRectF(r.left(), r.bottom() + m, tw, th), QRectF(r.right() - tw, r.bottom() + m, tw, th),
            QRectF(r.left() - tw - m, r.top(), tw, th), QRectF(r.right() + m, r.top(), tw, th),
            QRectF(r.left() + m, r.top() + m, tw, th)]
        najlepszy, koszt_min = None, None
        for k in kandydaci:
            kw = _wsun(k, widok)
            koszt = (6 * _wspolne(kw, pelna) + 12 * sum(_wspolne(kw, e) for e in postawione)
                     + 2 * sum(_wspolne(kw, r2) for o2, r2 in ramki if o2 is not o and not tlo_duze(r2))
                     + 0.5 * (abs(kw.left() - k.left()) + abs(kw.top() - k.top())) * th)
            if koszt_min is None or koszt < koszt_min:
                najlepszy, koszt_min = kw, koszt
        postawione.append(najlepszy)
        kol = kolor_klasy(o["klasa"])
        # linia prowadząca, gdy etykieta nie przylega do ramki
        cx = min(max(najlepszy.center().x(), r.left()), r.right())
        cy = min(max(najlepszy.center().y(), r.top()), r.bottom())
        lx = min(max(cx, najlepszy.left()), najlepszy.right())
        ly = min(max(cy, najlepszy.top()), najlepszy.bottom())
        if abs(lx - cx) + abs(ly - cy) > px * 0.6:
            p.setPen(QPen(kol, max(1.5, gr * 0.7)))
            p.drawLine(QPointF(lx, ly), QPointF(cx, cy))
        tlo = QColor(kol)
        tlo.setAlpha(235)
        p.setPen(Qt.NoPen)
        p.setBrush(tlo)
        p.drawRoundedRect(najlepszy, px * 0.25, px * 0.25)
        p.setPen(QColor("#0b0b0b"))
        p.drawText(najlepszy, Qt.AlignCenter, tekst)


def bgr_na_qimage(klatka):
    rgb = cv2.cvtColor(klatka, cv2.COLOR_BGR2RGB)
    h, w, _ = rgb.shape
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


def kafelek_obiektu(klatka, o, w=112, h=84):
    """Powiększony wycinek obiektu do panelu."""
    H, W = klatka.shape[:2]
    x0, y0, x1, y1 = o["ramka"]
    dx, dy = (x1 - x0) * 0.12, (y1 - y0) * 0.12
    a, b = int(max(0, (x0 - dx) * W)), int(max(0, (y0 - dy) * H))
    c, d = int(min(W, (x1 + dx) * W)), int(min(H, (y1 + dy) * H))
    if c - a < 2 or d - b < 2:
        return None
    return QPixmap.fromImage(bgr_na_qimage(klatka[b:d, a:c])).scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def gdzie(o):
    sx = (o["ramka"][0] + o["ramka"][2]) / 2
    return "po lewej" if sx < 0.38 else "po prawej" if sx > 0.62 else "na środku"


def opisz_obiekty(obiekty):
    """Słowny opis sceny z wykrytych obiektów."""
    if not obiekty:
        return "Nic nie rozpoznaję."
    grupy = {}
    for o in obiekty:
        grupy.setdefault(o["klasa"], []).append(o)
    kolejnosc = {"po lewej": 0, "na środku": 1, "po prawej": 2}
    czesci = []
    for klasa, lst in sorted(grupy.items(), key=lambda x: -len(x[1])):
        miejsca = sorted({gdzie(o) for o in lst}, key=kolejnosc.get)
        czesci.append(f"{nazwa(klasa)}{f' ×{len(lst)}' if len(lst) > 1 else ''} ({', '.join(miejsca)})")
    najw = max(obiekty, key=lambda o: (o["ramka"][2] - o["ramka"][0]) * (o["ramka"][3] - o["ramka"][1]))
    return "Widzę: " + "; ".join(czesci) + f".\nNajwiększe w kadrze: {nazwa(najw['klasa'])} {gdzie(najw)}."


def opis_polozenia(o):
    x0, y0, x1, y1 = o["ramka"]
    return f"{gdzie(o)} · zajmuje {100 * (x1 - x0) * (y1 - y0):.0f}% kadru"


# ---------- interfejs ----------

def kolor_temp(t, ostrz=65, alarm=80):
    if t is None:
        return SZARY
    return ZIELONY if t < ostrz else ZOLTY if t < alarm else CZERWONY


def przycisk(tekst, szer=None, wys=44, rozmiar=16):
    b = QPushButton(tekst)
    b.setFixedHeight(wys)
    if szer:
        b.setFixedWidth(szer)
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.NoFocus)
    b.setStyleSheet(
        f"QPushButton{{background:#2a333a;color:{TEKST};font-size:{rozmiar}px;font-weight:600;border:none;"
        f"border-radius:8px;padding:0 10px}}QPushButton:pressed{{background:#3e4a53}}"
        f"QPushButton:checked{{background:{ZOLTY};color:#111}}QPushButton:disabled{{color:#59636b}}")
    return b


class Przelacznik(QAbstractButton):
    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(84, 44)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(ZIELONY if self.isChecked() else "#3a444c"))
        p.drawRoundedRect(QRectF(0, 0, 84, 44), 22, 22)
        p.setBrush(QColor("#ffffff"))
        x = 44 if self.isChecked() else 4
        p.drawEllipse(QRectF(x, 4, 36, 36))


def trafiony(obiekty, nx, ny):
    """Najmniejszy obiekt, którego ramka zawiera punkt (współrzędne 0..1)."""
    pasujace = [o for o in obiekty if o["ramka"][0] <= nx <= o["ramka"][2] and o["ramka"][1] <= ny <= o["ramka"][3]]
    if not pasujace:
        return None
    return min(pasujace, key=lambda o: (o["ramka"][2] - o["ramka"][0]) * (o["ramka"][3] - o["ramka"][1]))


class Obraz(QWidget):
    """Podgląd na żywo; dotknięcie wybiera obiekt."""

    def __init__(self, okno):
        super().__init__()
        self.okno = okno
        self.img, self.obiekty, self.komunikat = None, [], ""
        self.nakladka = ""
        self.obszar = QRectF()
        self.setMinimumSize(320, 240)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(TLO))
        if self.img is None:
            p.setPen(QColor(SZARY))
            f = QFont("Sans")
            f.setPixelSize(20)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter, self.komunikat)
            return
        iw, ih = self.img.width(), self.img.height()
        s = min(self.width() / iw, self.height() / ih)
        w, h = iw * s, ih * s
        self.obszar = QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(self.obszar, self.img)
        rysuj_adnotacje(p, self.obszar, self.obiekty, QRectF(self.rect()), 15, self.okno.wybrany)
        if self.nakladka:
            f = QFont("Sans")
            f.setPixelSize(16)
            f.setBold(True)
            p.setFont(f)
            tw = p.fontMetrics().horizontalAdvance(self.nakladka) + 24
            r = QRectF(12, self.height() - 46, tw, 34)
            tlo = QColor("#000000")
            tlo.setAlpha(170)
            p.setPen(Qt.NoPen)
            p.setBrush(tlo)
            p.drawRoundedRect(r, 6, 6)
            p.setPen(QColor(TEKST))
            p.drawText(r, Qt.AlignCenter, self.nakladka)
        if self.okno.pauza.isChecked():
            f = QFont("Sans")
            f.setPixelSize(18)
            f.setBold(True)
            p.setFont(f)
            r = QRectF(12, 12, 110, 32)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(ZOLTY))
            p.drawRoundedRect(r, 6, 6)
            p.setPen(QColor("#111"))
            p.drawText(r, Qt.AlignCenter, "PAUZA")

    def mouseReleaseEvent(self, e):
        if self.obszar.width() <= 0 or self.okno.detektor.tryb != "obiekty":
            return
        nx = (e.pos().x() - self.obszar.left()) / self.obszar.width()
        ny = (e.pos().y() - self.obszar.top()) / self.obszar.height()
        o = trafiony(self.obiekty, nx, ny)
        self.okno.wybierz(o["id"] if o else None, o["klasa"] if o else None)


class Przegladarka(QWidget):
    """Stop-klatka z adnotacjami na cały ekran: przybliżanie, przesuwanie, zapis, galeria."""

    def __init__(self, okno):
        super().__init__(okno)
        self.okno = okno
        self.setAttribute(Qt.WA_AcceptTouchEvents)
        self.setAutoFillBackground(False)
        self.img, self.obiekty, self.klatka = None, [], None
        self.plik, self.indeks, self.wybrany = None, None, None
        self.s, self.ox, self.oy = 1.0, 0.0, 0.0
        self._dotyk = None
        self._mysz = None
        self.info = ""

        pasek = QHBoxLayout()
        pasek.setContentsMargins(10, 10, 10, 0)
        pasek.setSpacing(8)
        self.b_pop, self.b_nast = przycisk("◀", 52), przycisk("▶", 52)
        self.b_minus, self.b_plus, self.b_dopasuj = przycisk("−", 52, rozmiar=24), przycisk("+", 52, rozmiar=24), przycisk("Dopasuj")
        self.b_zapisz, self.b_zamknij = przycisk("Zapisz"), przycisk("✕", 52, rozmiar=22)
        self.b_pop.clicked.connect(lambda: self.przewin(-1))
        self.b_nast.clicked.connect(lambda: self.przewin(1))
        self.b_minus.clicked.connect(lambda: self.przybliz(1 / 1.4))
        self.b_plus.clicked.connect(lambda: self.przybliz(1.4))
        self.b_dopasuj.clicked.connect(self.dopasuj)
        self.b_zapisz.clicked.connect(self.zapisz)
        self.b_zamknij.clicked.connect(self.zamknij)
        for b in (self.b_pop, self.b_nast):
            pasek.addWidget(b)
        pasek.addStretch()
        for b in (self.b_minus, self.b_plus, self.b_dopasuj, self.b_zapisz, self.b_zamknij):
            pasek.addWidget(b)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(pasek)
        lay.addStretch()
        self.hide()

    # --- otwieranie ---
    def pokaz_nowe(self, klatka, obiekty):
        self.klatka, self.obiekty = klatka.copy(), [dict(o) for o in obiekty]
        self.img = bgr_na_qimage(self.klatka)
        self.plik, self.indeks, self.wybrany = None, None, None
        self.czas = time.strftime("%Y-%m-%d %H:%M:%S")
        self.info = f"{self.czas} · {len(self.obiekty)} obiektów · niezapisane"
        self._otworz()

    def pokaz_galerie(self):
        pliki = self.lista_plikow()
        if not pliki:
            self.okno.komunikat("Galeria jest pusta: zrób zdjęcie i zapisz je.")
            return
        self.wczytaj(len(pliki) - 1)
        self._otworz()

    def _otworz(self):
        self.setGeometry(self.okno.rect())
        self.show()
        self.raise_()
        self.dopasuj()
        self._odswiez_przyciski()

    @staticmethod
    def lista_plikow():
        return sorted(glob.glob(os.path.join(ZDJECIA, "*.json")))

    def wczytaj(self, indeks):
        pliki = self.lista_plikow()
        if not pliki:
            return
        indeks = max(0, min(indeks, len(pliki) - 1))
        dane = json.load(open(pliki[indeks], encoding="utf-8"))
        self.klatka = cv2.imread(os.path.join(ZDJECIA, dane["obraz"]))
        self.img = bgr_na_qimage(self.klatka)
        self.obiekty = [dict(id=o["id"], klasa=o["klasa"], ramka=o["ramka"], pew=o["pewnosc"]) for o in dane["obiekty"]]
        self.plik, self.indeks, self.wybrany = pliki[indeks], indeks, None
        self.czas = dane.get("czas", "")
        self.info = f"{self.czas} · {len(self.obiekty)} obiektów · {indeks + 1}/{len(pliki)} · {os.path.basename(dane['obraz'])}"
        self.dopasuj()
        self._odswiez_przyciski()

    def przewin(self, krok):
        pliki = self.lista_plikow()
        if not pliki:
            return
        if self.indeks is None:
            self.wczytaj(len(pliki) - 1 if krok < 0 else 0)
        else:
            self.wczytaj(self.indeks + krok)

    def _odswiez_przyciski(self):
        n = len(self.lista_plikow())
        self.b_zapisz.setEnabled(self.plik is None)
        self.b_zapisz.setText("Zapisz" if self.plik is None else "Zapisane")
        self.b_pop.setEnabled(n > 0 and (self.indeks is None or self.indeks > 0))
        self.b_nast.setEnabled(self.indeks is not None and self.indeks < n - 1)

    def zamknij(self):
        self.hide()
        self.okno.setFocus()

    # --- zapis ---
    def zapisz(self):
        if self.klatka is None or self.plik is not None:
            return
        os.makedirs(ZDJECIA, exist_ok=True)
        klasy = []
        for o in self.obiekty:
            if nazwa(o["klasa"]) not in klasy:
                klasy.append(nazwa(o["klasa"]))
        opis = slug("-".join(klasy[:3])) or "pusto"
        baza = time.strftime("%Y-%m-%d_%H%M") + "_" + opis  # konwencja projektu: RRRR-MM-DD_GGMM_opis
        nr = 1
        while os.path.exists(os.path.join(ZDJECIA, baza + ("" if nr == 1 else f"_{nr}") + ".jpg")):
            nr += 1
        baza += "" if nr == 1 else f"_{nr}"
        cv2.imwrite(os.path.join(ZDJECIA, baza + ".jpg"), self.klatka, [cv2.IMWRITE_JPEG_QUALITY, 92])
        z_ramkami = self.img.convertToFormat(QImage.Format_RGB32)
        p = QPainter(z_ramkami)
        cale = QRectF(0, 0, z_ramkami.width(), z_ramkami.height())
        rysuj_adnotacje(p, cale, self.obiekty, cale, max(16, z_ramkami.width() / 48))
        p.end()
        z_ramkami.save(os.path.join(ZDJECIA, baza + "_ramki.png"))
        dane = dict(czas=self.czas, obraz=baza + ".jpg", obraz_z_ramkami=baza + "_ramki.png",
                    szer=self.img.width(), wys=self.img.height(),
                    obiekty=[dict(id=o["id"], klasa=o["klasa"], nazwa=nazwa(o["klasa"]), pewnosc=round(o["pew"], 3),
                                  ramka=[round(v, 4) for v in o["ramka"]]) for o in self.obiekty])
        sciezka = os.path.join(ZDJECIA, baza + ".json")
        json.dump(dane, open(sciezka, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        pliki = self.lista_plikow()
        self.plik, self.indeks = sciezka, pliki.index(sciezka)
        self.info = f"{self.czas} · {len(self.obiekty)} obiektów · zapisano {baza}.jpg (+ _ramki.png, .json)"
        self._odswiez_przyciski()
        self.update()

    # --- przybliżanie i przesuwanie ---
    def _dopasowanie(self):
        return min(self.width() / self.img.width(), self.height() / self.img.height())

    def _ogranicz(self):
        w, h = self.img.width() * self.s, self.img.height() * self.s
        self.ox = (self.width() - w) / 2 if w <= self.width() else min(0, max(self.width() - w, self.ox))
        self.oy = (self.height() - h) / 2 if h <= self.height() else min(0, max(self.height() - h, self.oy))

    def dopasuj(self):
        if self.img is None:
            return
        self.s = self._dopasowanie()
        self._ogranicz()
        self.update()

    def przybliz(self, mnoznik, punkt=None):
        if self.img is None:
            return
        punkt = punkt or QPointF(self.width() / 2, self.height() / 2)
        s0 = self._dopasowanie()
        nowe = min(max(self.s * mnoznik, s0), s0 * 10)
        ux, uy = (punkt.x() - self.ox) / self.s, (punkt.y() - self.oy) / self.s
        self.s = nowe
        self.ox, self.oy = punkt.x() - ux * self.s, punkt.y() - uy * self.s
        self._ogranicz()
        self.update()

    def przesun(self, dx, dy):
        self.ox += dx
        self.oy += dy
        self._ogranicz()
        self.update()

    def dotkniecie(self, pkt):
        if self.img is None:
            return
        nx = (pkt.x() - self.ox) / (self.img.width() * self.s)
        ny = (pkt.y() - self.oy) / (self.img.height() * self.s)
        o = trafiony(self.obiekty, nx, ny)
        self.wybrany = o["id"] if o else None
        self.update()

    def resizeEvent(self, e):
        if self.img is not None:
            self._ogranicz()
        super().resizeEvent(e)

    def wheelEvent(self, e):
        self.przybliz(1.15 if e.angleDelta().y() > 0 else 1 / 1.15, QPointF(e.pos()))

    def mousePressEvent(self, e):
        self._mysz = (QPointF(e.pos()), QPointF(e.pos()))

    def mouseMoveEvent(self, e):
        if self._mysz:
            start, ostatni = self._mysz
            self.przesun(e.pos().x() - ostatni.x(), e.pos().y() - ostatni.y())
            self._mysz = (start, QPointF(e.pos()))

    def mouseReleaseEvent(self, e):
        if self._mysz and (QPointF(e.pos()) - self._mysz[0]).manhattanLength() < 12:
            self.dotkniecie(QPointF(e.pos()))
        self._mysz = None

    def mouseDoubleClickEvent(self, e):
        if self.s > self._dopasowanie() * 1.05:
            self.dopasuj()
        else:
            self.przybliz(2.5, QPointF(e.pos()))

    def event(self, e):
        if e.type() in (QEvent.TouchBegin, QEvent.TouchUpdate, QEvent.TouchEnd):
            pkt = [t.pos() for t in e.touchPoints()
                   if t.state() != Qt.TouchPointReleased or e.type() == QEvent.TouchEnd]
            if e.type() == QEvent.TouchBegin:
                self._dotyk = dict(start=pkt[0], ostatni=pkt[0], ruch=0.0, palce=len(pkt))
            elif self._dotyk is not None:
                if len(pkt) >= 2 and e.type() != QEvent.TouchEnd:
                    a, b = pkt[0], pkt[1]
                    odl = max(1.0, ((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2) ** 0.5)
                    srodek = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
                    if self._dotyk.get("odl") is None:
                        self._dotyk.update(odl=odl, srodek=srodek)
                    else:
                        self.przybliz(odl / self._dotyk["odl"], srodek)
                        self.przesun(srodek.x() - self._dotyk["srodek"].x(), srodek.y() - self._dotyk["srodek"].y())
                        self._dotyk.update(odl=odl, srodek=srodek)
                    self._dotyk["palce"] = 2
                    self._dotyk["ruch"] += 100
                elif len(pkt) == 1 and e.type() != QEvent.TouchEnd:
                    p = pkt[0]
                    if self._dotyk.get("palce", 1) == 1:
                        d = p - self._dotyk["ostatni"]
                        self._dotyk["ruch"] += abs(d.x()) + abs(d.y())
                        self.przesun(d.x(), d.y())
                    self._dotyk["ostatni"] = p
                    self._dotyk["odl"] = None
                if e.type() == QEvent.TouchEnd:
                    if self._dotyk["ruch"] < 12 and self._dotyk.get("palce", 1) == 1:
                        self.dotkniecie(self._dotyk["start"])
                    self._dotyk = None
            e.accept()
            return True
        return super().event(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.zamknij()
        elif e.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self.przybliz(1.4)
        elif e.key() == Qt.Key_Minus:
            self.przybliz(1 / 1.4)
        elif e.key() == Qt.Key_Left:
            self.przewin(-1)
        elif e.key() == Qt.Key_Right:
            self.przewin(1)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#000000"))
        if self.img is None:
            return
        obraz = QRectF(self.ox, self.oy, self.img.width() * self.s, self.img.height() * self.s)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(obraz, self.img)
        widok = QRectF(self.rect()).adjusted(4, 62, -4, -40)
        rysuj_adnotacje(p, obraz, self.obiekty, widok, 16, self.wybrany)
        # pasek informacji na dole
        f = QFont("Sans")
        f.setPixelSize(15)
        p.setFont(f)
        tekst = self.info + f" · powiększenie ×{self.s / self._dopasowanie():.1f}"
        if self.wybrany is not None:
            o = next((x for x in self.obiekty if x["id"] == self.wybrany), None)
            if o:
                x0, y0, x1, y1 = o["ramka"]
                tekst = (f"Wybrano {etykieta(o)} · {(x1 - x0) * self.img.width():.0f}×{(y1 - y0) * self.img.height():.0f} px"
                         f" · {opis_polozenia(o)}")
        pas = QRectF(0, self.height() - 34, self.width(), 34)
        tlo = QColor("#000000")
        tlo.setAlpha(170)
        p.fillRect(pas, tlo)
        p.setPen(QColor(TEKST))
        p.drawText(pas.adjusted(12, 0, -12, 0), Qt.AlignVCenter | Qt.AlignLeft, tekst)


class Wiersz(QWidget):
    """Etykieta, wartość i opcjonalny pasek."""

    def __init__(self, nazwa_w, pasek=True):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        gora = QHBoxLayout()
        self.nazwa, self.wartosc = QLabel(nazwa_w), QLabel("—")
        self.nazwa.setStyleSheet(f"color:{SZARY};font-size:14px")
        self.wartosc.setStyleSheet(f"color:{TEKST};font-size:15px;font-weight:600")
        gora.addWidget(self.nazwa)
        gora.addStretch()
        gora.addWidget(self.wartosc)
        lay.addLayout(gora)
        self.pasek = None
        if pasek:
            self.pasek = QProgressBar()
            self.pasek.setRange(0, 100)
            self.pasek.setTextVisible(False)
            self.pasek.setFixedHeight(6)
            lay.addWidget(self.pasek)
            self.ustaw_kolor(ZIELONY)

    def ustaw_kolor(self, kolor):
        if self.pasek:
            self.pasek.setStyleSheet(
                f"QProgressBar{{background:#2a333a;border:none;border-radius:3px}}"
                f"QProgressBar::chunk{{background:{kolor};border-radius:3px}}")

    def ustaw(self, tekst, proc=None, kolor=None):
        self.wartosc.setText(tekst)
        if kolor:
            self.wartosc.setStyleSheet(f"color:{kolor};font-size:15px;font-weight:600")
        if self.pasek is not None and proc is not None:
            self.pasek.setValue(int(proc))
            self.ustaw_kolor(ZIELONY if proc < 70 else ZOLTY if proc < 90 else CZERWONY)


class Okno(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Łazik: wizja")
        self.setStyleSheet(f"background:{TLO};color:{TEKST}")
        self.kamera = Kamera()
        self.detektor = Detektor(self.kamera)
        self.system = System()
        self.wybrany = None          # id obiektu albo None
        self.tryb_klasy = None       # klasa, gdy pokazujemy całą klasę
        self.zamrozone = None        # (klatka, obiekty) w czasie pauzy
        self._lista_klucz = None
        self._komunikat_do = 0.0

        self.obraz = Obraz(self)
        panel = QWidget()
        panel.setFixedWidth(330)
        panel.setStyleSheet(f"background:{PANEL}")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(16, 14, 16, 12)
        pl.setSpacing(7)

        tytul = QLabel("Łazik · wizja")  # krzyżyk zamykania leży po prawej, na wysokości tytułu
        tytul.setStyleSheet("font-size:21px;font-weight:700")
        tytul.setFixedHeight(40)
        pl.addWidget(tytul)

        rt = QHBoxLayout()
        rt.setSpacing(6)
        self.b_obiekty, self.b_przestrzen = przycisk("Obiekty", wys=38), przycisk("Przestrzeń", wys=38)
        self.grupa_trybu = QButtonGroup(self)
        for b in (self.b_obiekty, self.b_przestrzen):
            b.setCheckable(True)
            self.grupa_trybu.addButton(b)
            rt.addWidget(b)
        self.b_obiekty.setChecked(True)
        self.b_przestrzen.toggled.connect(self.zmien_tryb)
        pl.addLayout(rt)

        rz = QHBoxLayout()
        etyk = QLabel("Rozpoznawanie")
        etyk.setStyleSheet("font-size:18px;font-weight:600")
        self.przelacznik = Przelacznik()
        self.przelacznik.toggled.connect(self.przelacz)
        rz.addWidget(etyk)
        rz.addStretch()
        rz.addWidget(self.przelacznik)
        pl.addLayout(rz)
        self.stan_hailo = QLabel("wyłączone")
        self.stan_hailo.setWordWrap(True)
        self.stan_hailo.setStyleSheet(f"color:{SZARY};font-size:13px")
        pl.addWidget(self.stan_hailo)

        self.wiersz_progu = QWidget()
        rp = QHBoxLayout(self.wiersz_progu)
        rp.setContentsMargins(0, 0, 0, 0)
        self.prog_lbl = QLabel()
        self.prog_lbl.setFixedWidth(86)
        self.prog_lbl.setStyleSheet(f"color:{SZARY};font-size:14px")
        self.prog = QSlider(Qt.Horizontal)
        self.prog.setRange(20, 90)
        self.prog.setValue(50)
        self.prog.setStyleSheet(
            "QSlider::groove:horizontal{height:8px;background:#2a333a;border-radius:4px}"
            "QSlider::handle:horizontal{width:26px;margin:-10px 0;background:#ffffff;border-radius:13px}")
        self.prog.valueChanged.connect(self.zmien_prog)
        self.zmien_prog(50)
        rp.addWidget(self.prog_lbl)
        rp.addWidget(self.prog)
        pl.addWidget(self.wiersz_progu)

        self.w_cpu = Wiersz("Procesor")
        self.w_ram = Wiersz("RAM")
        self.w_hailo = Wiersz("Hailo")
        self.w_kam = Wiersz("Kamera / Hailo", pasek=False)
        self.w_zas = Wiersz("Zasilanie", pasek=False)
        for w in (self.w_cpu, self.w_ram, self.w_hailo, self.w_kam, self.w_zas):
            pl.addWidget(w)

        self.strony = QStackedWidget()
        str_ob = QWidget()
        so = QVBoxLayout(str_ob)
        so.setContentsMargins(0, 0, 0, 0)
        so.setSpacing(7)
        rb = QHBoxLayout()
        rb.setSpacing(6)
        self.b_zdjecie, self.pauza, self.b_galeria = przycisk("Zdjęcie"), przycisk("Pauza"), przycisk("Galeria")
        self.pauza.setCheckable(True)
        self.b_zdjecie.clicked.connect(self.zrob_zdjecie)
        self.pauza.toggled.connect(self.przelacz_pauze)
        self.b_galeria.clicked.connect(lambda: self.przegladarka.pokaz_galerie())
        for b in (self.b_zdjecie, self.pauza, self.b_galeria):
            rb.addWidget(b)
        so.addLayout(rb)

        # wybrany obiekt: lupa + opis + przyciski
        self.wybor = QWidget()
        self.wybor.setStyleSheet("background:#1f272d;border-radius:8px")
        wl = QHBoxLayout(self.wybor)
        wl.setContentsMargins(6, 6, 6, 6)
        wl.setSpacing(8)
        self.lupa = QLabel()
        self.lupa.setFixedSize(112, 84)
        self.lupa.setAlignment(Qt.AlignCenter)
        self.lupa.setStyleSheet("background:#000;border-radius:4px")
        prawa = QVBoxLayout()
        prawa.setSpacing(4)
        self.wybor_opis = QLabel()
        self.wybor_opis.setWordWrap(True)
        self.wybor_opis.setStyleSheet("font-size:13px;background:transparent")
        rw = QHBoxLayout()
        rw.setSpacing(4)
        self.b_klasa = przycisk("cała klasa", wys=30, rozmiar=13)
        self.b_klasa.setCheckable(True)
        self.b_klasa.toggled.connect(self.przelacz_klase)
        self.b_odznacz = przycisk("✕", 34, wys=30, rozmiar=14)
        self.b_odznacz.clicked.connect(lambda: self.wybierz(None, None))
        rw.addWidget(self.b_klasa)
        rw.addWidget(self.b_odznacz)
        prawa.addWidget(self.wybor_opis, 1)
        prawa.addLayout(rw)
        wl.addWidget(self.lupa)
        wl.addLayout(prawa, 1)
        self.wybor.hide()
        so.addWidget(self.wybor)

        self.opis_ob = QLabel()
        self.opis_ob.setWordWrap(True)
        self.opis_ob.setStyleSheet(f"color:{TEKST};font-size:13px;background:#1f272d;border-radius:8px;padding:6px 8px")
        so.addWidget(self.opis_ob)

        self.lista = QListWidget()
        self.lista.setStyleSheet(
            "QListWidget{background:transparent;border:none;font-size:16px}"
            "QListWidget::item{padding:5px 4px;border-bottom:1px solid #232b31}"
            "QListWidget::item:selected{background:#2e3a42}")
        self.lista.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.lista.setFocusPolicy(Qt.NoFocus)
        QScroller.grabGesture(self.lista.viewport(), QScroller.LeftMouseButtonGesture)
        self.lista.itemClicked.connect(self.klik_listy)
        so.addWidget(self.lista, 1)

        str_pr = QWidget()
        sp = QVBoxLayout(str_pr)
        sp.setContentsMargins(0, 0, 0, 0)
        sp.setSpacing(8)
        self.opis_pr = QLabel("Włącz rozpoznawanie, żeby liczyć głębię.")
        self.opis_pr.setWordWrap(True)
        self.opis_pr.setStyleSheet(f"color:{TEKST};font-size:14px;background:#1f272d;border-radius:8px;padding:8px")
        sp.addWidget(self.opis_pr)
        rs = QHBoxLayout()
        rs.setSpacing(6)
        self.b_skan = przycisk("Start skanu")
        self.b_skan.setCheckable(True)
        self.b_skan.toggled.connect(self.przelacz_skan)
        self.b_wyczysc = przycisk("Wyczyść")
        self.b_wyczysc.clicked.connect(self.wyczysc_skan)
        rs.addWidget(self.b_skan, 1)
        rs.addWidget(self.b_wyczysc)
        sp.addLayout(rs)
        rs2 = QHBoxLayout()
        rs2.setSpacing(6)
        self.b_zapisz_skan, self.b_skany = przycisk("Zapisz skan"), przycisk("Skany 3D")
        self.b_zapisz_skan.clicked.connect(self.zapisz_skan)
        self.b_skany.clicked.connect(self.otworz_skany)
        rs2.addWidget(self.b_zapisz_skan)
        rs2.addWidget(self.b_skany)
        sp.addLayout(rs2)
        self.info_skan = QLabel()
        self.info_skan.setWordWrap(True)
        self.info_skan.setStyleSheet(f"color:{SZARY};font-size:13px")
        sp.addWidget(self.info_skan)
        sp.addStretch()

        self.strony.addWidget(str_ob)
        self.strony.addWidget(str_pr)
        pl.addWidget(self.strony, 1)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.obraz, 1)
        lay.addWidget(panel)

        self.dymek = QLabel(self)
        self.dymek.setStyleSheet(f"background:{ZOLTY};color:#111;font-size:16px;font-weight:600;"
                                 "border-radius:8px;padding:8px 14px")
        self.dymek.hide()

        self.zamknij = QPushButton("✕", self)
        self.zamknij.setFixedSize(52, 52)
        self.zamknij.setCursor(Qt.PointingHandCursor)
        self.zamknij.setFocusPolicy(Qt.NoFocus)
        self.zamknij.setStyleSheet(
            f"QPushButton{{background:#2a333a;color:{TEKST};font-size:26px;border:none;border-radius:26px}}"
            f"QPushButton:pressed{{background:{CZERWONY}}}")
        self.zamknij.clicked.connect(self.close)

        self.przegladarka = Przegladarka(self)

        self.kamera.start()
        self.detektor.start()
        self.t_obraz = QTimer(self, timeout=self.rysuj)
        self.t_obraz.start(33)
        self.t_lista = QTimer(self, timeout=self.odswiez_liste)
        self.t_lista.start(300)
        self.t_stat = QTimer(self, timeout=self.statystyki)
        self.t_stat.start(1000)
        self.statystyki()
        self.setFocusPolicy(Qt.StrongFocus)

        if "--przestrzen" in sys.argv:  # start w trybie przestrzeni (do testów)
            self.b_przestrzen.setChecked(True)
        if "--rozpoznawanie" in sys.argv:  # start z włączonym Hailo (do testów)
            self.przelacznik.setChecked(True)

    # --- układ ---
    def resizeEvent(self, e):
        self.zamknij.move(self.width() - 64, 8)
        self.zamknij.raise_()
        if self.przegladarka.isVisible():
            self.przegladarka.setGeometry(self.rect())
            self.przegladarka.raise_()
        super().resizeEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Escape, Qt.Key_Q):
            self.close()
        elif e.key() == Qt.Key_Space:
            self.pauza.toggle()

    def komunikat(self, tekst, sekundy=3.0):
        self.dymek.setText(tekst)
        self.dymek.adjustSize()
        self.dymek.move(16, self.height() - self.dymek.height() - 16)
        self.dymek.show()
        self.dymek.raise_()
        self._komunikat_do = time.monotonic() + sekundy

    # --- sterowanie ---
    def przelacz(self, wl):
        if wl:
            self.detektor.stan = "ładuję model…"
            self.detektor.wlaczony.set()
        else:
            self.detektor.wlaczony.clear()
            self.wybierz(None, None)

    def zmien_tryb(self, przestrzen):
        self.detektor.tryb = "przestrzen" if przestrzen else "obiekty"
        self.strony.setCurrentIndex(1 if przestrzen else 0)
        self.wiersz_progu.setVisible(not przestrzen)  # próg dotyczy tylko rozpoznawania obiektów
        if self.pauza.isChecked():
            self.pauza.setChecked(False)
        if not przestrzen and self.b_skan.isChecked():
            self.b_skan.setChecked(False)
        self.wybierz(None, None)

    def przelacz_skan(self, wl):
        if wl and not self.przelacznik.isChecked():
            self.przelacznik.setChecked(True)
        self.detektor.skanuj = wl
        self.b_skan.setText("Stop skanu" if wl else "Start skanu")

    def wyczysc_skan(self):
        with self.detektor.lock_skan:
            self.detektor.skaner.wyczysc()

    def zapisz_skan(self):
        self.b_skan.setChecked(False)
        try:
            with self.detektor.lock_skan:
                katalog = self.detektor.skaner.zapisz(opis=self.opis_pr.text())
        except Exception as e:
            self.komunikat(f"Nie zapisano: {e}")
            return
        self.komunikat(f"Zapisano skan: skany/{os.path.basename(katalog)}", 5)

    def otworz_skany(self):
        try:
            subprocess.Popen([os.path.join(KATALOG, "skany.sh")], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.komunikat("Otwieram przeglądarkę skanów…")
        except Exception as e:
            self.komunikat(f"Nie otworzono: {e}")

    def zmien_prog(self, v):
        self.detektor.prog = v / 100
        self.prog_lbl.setText(f"Próg {v}%")

    def przelacz_pauze(self, wl):
        if wl:
            obiekty, klatka_det = self.detektor.najnowsze()
            klatka = klatka_det if (self.przelacznik.isChecked() and klatka_det is not None) else self.kamera.najnowsza()[0]
            self.zamrozone = (klatka, obiekty if klatka is klatka_det else [])
        else:
            self.zamrozone = None

    def biezace(self):
        """(klatka do pokazania, obiekty) — z pauzy albo na żywo."""
        if self.zamrozone is not None:
            return self.zamrozone
        klatka = self.kamera.najnowsza()[0]
        obiekty = self.detektor.najnowsze()[0] if self.przelacznik.isChecked() else []
        return klatka, obiekty

    def widoczne(self, obiekty):
        if self.tryb_klasy is not None:
            return [o for o in obiekty if o["klasa"] == self.tryb_klasy]
        if self.wybrany is not None:
            return [o for o in obiekty if o["id"] == self.wybrany]
        return obiekty

    def wybierz(self, oid, klasa):
        self.wybrany = oid
        self.tryb_klasy = None
        self._klasa_wybranego = klasa
        self.b_klasa.blockSignals(True)
        self.b_klasa.setChecked(False)
        self.b_klasa.blockSignals(False)
        self.wybor.setVisible(oid is not None)
        self._lista_klucz = None
        self.odswiez_liste()

    def przelacz_klase(self, wl):
        self.tryb_klasy = self._klasa_wybranego if wl else None
        self._lista_klucz = None

    def klik_listy(self, item):
        oid, klasa = item.data(Qt.UserRole)
        if oid == self.wybrany and self.tryb_klasy is None:
            self.wybierz(None, None)
        else:
            self.wybierz(oid, klasa)

    def zrob_zdjecie(self):
        if self.zamrozone is not None:
            klatka, obiekty = self.zamrozone
        else:
            obiekty, klatka = self.detektor.najnowsze()
            if not self.przelacznik.isChecked() or klatka is None:
                klatka, obiekty = self.kamera.najnowsza()[0], []
        if klatka is None:
            self.komunikat("Brak obrazu z kamery.")
            return
        self.przegladarka.pokaz_nowe(klatka, self.widoczne(obiekty))

    # --- odświeżanie ---
    def rysuj(self):
        if self.detektor.tryb == "przestrzen":
            wynik = self.detektor.glebia_wynik if self.przelacznik.isChecked() else None
            if wynik is not None:
                klatka, glebia = wynik
                mapa = P.mapa_kolorow(glebia, klatka.shape)
                self.obraz.img = bgr_na_qimage(cv2.addWeighted(klatka, 0.4, mapa, 0.6, 0))
            else:
                klatka = self.kamera.najnowsza()[0]
                self.obraz.img = bgr_na_qimage(klatka) if klatka is not None else None
                self.obraz.komunikat = self.kamera.stan
            sk = self.detektor.skaner
            self.obraz.nakladka = (f"● SKAN · {len(sk.pkt):,} pkt · obrót {sk.obrot:.0f}°".replace(",", " ")
                                   if self.detektor.skanuj else "")
            self.obraz.obiekty = []
            self.obraz.update()
            if self.dymek.isVisible() and time.monotonic() > self._komunikat_do:
                self.dymek.hide()
            return
        self.obraz.nakladka = ""
        klatka, obiekty = self.biezace()
        if klatka is None:
            self.obraz.img, self.obraz.komunikat = None, self.kamera.stan
        else:
            self.obraz.img = bgr_na_qimage(klatka)
        self.obraz.obiekty = self.widoczne(obiekty)
        self.obraz.update()
        if self.dymek.isVisible() and time.monotonic() > self._komunikat_do:
            self.dymek.hide()

    def odswiez_liste(self):
        if self.detektor.tryb == "przestrzen":
            wynik = self.detektor.glebia_wynik
            if self.przelacznik.isChecked() and wynik is not None:
                self.opis_pr.setText(P.opisz_glebie(wynik[1], self.detektor.glebia.metryczna))
            elif not self.przelacznik.isChecked():
                self.opis_pr.setText("Włącz rozpoznawanie, żeby liczyć głębię.")
            sk = self.detektor.skaner
            odch, poch = sk.katy()
            self.info_skan.setText(
                f"Punkty: {len(sk.pkt):,} · kierunek {odch:+.0f}° / {poch:+.0f}°\n".replace(",", " ") +
                f"{sk.stan[0].upper() + sk.stan[1:]}")
            return
        klatka, obiekty = self.biezace()
        widoczne = self.widoczne(obiekty)
        self.opis_ob.setText(opisz_obiekty(widoczne) if self.przelacznik.isChecked() else "Rozpoznawanie wyłączone.")
        if self.wybrany is not None:
            o = next((x for x in obiekty if x["id"] == self.wybrany), None)
            if o is not None and klatka is not None:
                kaf = kafelek_obiektu(klatka, o)
                if kaf is not None:
                    self.lupa.setPixmap(kaf)
                czas = time.monotonic() - o["od"]
                dop = f"\ncała klasa: {len(widoczne)} szt." if self.tryb_klasy is not None else ""
                self.wybor_opis.setText(f"{etykieta(o)}\n{opis_polozenia(o)}\nśledzony {czas:.0f} s{dop}")
            elif self.przelacznik.isChecked():
                self.wybor_opis.setText(f"#{self.wybrany} zniknął z kadru\n(dotknij ✕, aby wrócić do wszystkich)")
        if not self.przelacznik.isChecked():
            klucz = ("wyl",)
        else:
            klucz = tuple((o["id"], o["klasa"], round(o["pew"], 2)) for o in widoczne) + (self.wybrany,)
        if klucz == self._lista_klucz:
            return
        self._lista_klucz = klucz
        self.lista.clear()
        if not self.przelacznik.isChecked():
            it = QListWidgetItem("Rozpoznawanie wyłączone")
            it.setForeground(QColor(SZARY))
            it.setFlags(Qt.NoItemFlags)
            self.lista.addItem(it)
            return
        if not widoczne:
            it = QListWidgetItem("Nic nie widać")
            it.setForeground(QColor(SZARY))
            it.setFlags(Qt.NoItemFlags)
            self.lista.addItem(it)
            return
        for o in sorted(widoczne, key=lambda x: -x["pew"]):
            it = QListWidgetItem(f"■  {etykieta(o)}")
            it.setForeground(kolor_klasy(o["klasa"]))
            it.setData(Qt.UserRole, (o["id"], o["klasa"]))
            self.lista.addItem(it)
            if o["id"] == self.wybrany:
                it.setSelected(True)

    def statystyki(self):
        s, d = self.system, self.detektor
        s.odswiez()
        t_cpu = f" · {s.temp:.0f} °C" if s.temp is not None else ""
        self.w_cpu.ustaw(f"{s.cpu:.0f}%{t_cpu}", s.cpu, kolor=kolor_temp(s.temp, 70, 80))
        self.w_ram.ustaw(f"{s.ram_uzyte:.1f} / {s.ram_razem:.1f} GB", s.ram_proc)
        if d.zaladowany is not None:
            t_h = f" · {d.temp:.0f} °C" if d.temp is not None else ""
            self.w_hailo.ustaw(f"{d.obciazenie:.0f}%{t_h}", d.obciazenie, kolor=kolor_temp(d.temp))
            det = f"{d.fps:.0f} kl/s · {d.ms:.0f} ms"
        else:
            t_h = f" · {d.temp:.0f} °C" if d.temp is not None else ""
            self.w_hailo.ustaw(f"bezczynne{t_h}", 0, kolor=SZARY)
            det = "wył."
        kam = f"{self.kamera.fps:.0f}" if self.kamera.fps else "brak"
        self.w_kam.ustaw(f"{kam} / {det}")
        self.w_kam.setToolTip(self.kamera.stan)
        self.w_zas.ustaw(s.zasilanie, kolor=ZIELONY if s.zasilanie == "OK" else ZOLTY)
        blad = d.stan.startswith("błąd")
        self.stan_hailo.setText(d.stan)
        self.stan_hailo.setStyleSheet(f"color:{CZERWONY if blad else SZARY};font-size:13px")
        if blad and self.przelacznik.isChecked():
            self.przelacznik.blockSignals(True)
            self.przelacznik.setChecked(False)
            self.przelacznik.blockSignals(False)
            self.wybierz(None, None)

    def closeEvent(self, e):
        self.detektor.wlaczony.clear()
        self.detektor.dziala = False
        self.kamera.dziala = False
        self.detektor.join(timeout=3)
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    okno = Okno()
    okno.showFullScreen()
    kod = app.exec_()
    os._exit(kod)  # bez sprzątania HailoRT przy wyjściu (w tej wersji potrafi się wysypać)


if __name__ == "__main__":
    main()
