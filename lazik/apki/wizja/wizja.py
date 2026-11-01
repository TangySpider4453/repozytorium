#!/usr/bin/env python3
"""Łazik: wizja. Kamera USB + rozpoznawanie obiektów na Hailo, pełny ekran.

Panel z prawej: przełącznik rozpoznawania (Hailo pracuje tylko, gdy jest włączony), próg pewności,
obciążenie CPU i Hailo, RAM, temperatury, zasilanie i lista wykrytych obiektów. Krzyżyk w rogu (albo Esc)
zamyka aplikację.

Obciążenie Hailo to przybliżenie: jaką część każdej sekundy chip spędza na naszych inferencjach.
"""

import glob
import os
import subprocess
import sys
import threading
import time
from collections import Counter

import cv2
import numpy as np
from PyQt5.QtCore import QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QImage, QPainter, QPen
from PyQt5.QtWidgets import (QAbstractButton, QApplication, QHBoxLayout, QLabel, QProgressBar,
                             QPushButton, QSlider, QVBoxLayout, QWidget)

MODELE = [  # pierwszy, który się wczyta na tym chipie (Hailo-8 albo Hailo-8L)
    "/usr/share/hailo-models/yolov8s_h8.hef",
    "/usr/share/hailo-models/yolov8s_h8l.hef",
    "/usr/share/hailo-models/yolov6n_h8.hef",
    "/usr/share/hailo-models/yolov6n_h8l.hef",
]

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


def kolor_klasy(i):
    return QColor.fromHsv((i * 47) % 360, 200, 255)


# ---------- kamera ----------

def znajdz_kamere_usb():
    """Na Pi 5 /dev/video0.. to węzły kamery CSI i ISP; szukamy pierwszego węzła przechwytywania z USB."""
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


# ---------- Hailo ----------

class Detektor(threading.Thread):
    """Model ładuje się dopiero po włączeniu przełącznika, a po wyłączeniu zwalnia chip."""

    def __init__(self, kamera):
        super().__init__(daemon=True)
        self.kamera = kamera
        self.wlaczony = threading.Event()
        self.lock = threading.Lock()
        self.wyniki, self.nr_wynikow = [], 0
        self.stan, self.model = "wyłączone", None
        self.fps = self.ms = self.obciazenie = 0.0
        self.temp = None
        self.prog = 0.5
        self.dziala = True
        self.hailo = None

    def _zaladuj(self):
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
                return
            except Exception as e:
                bledy.append(f"{os.path.basename(sciezka)}: {e}")
        raise RuntimeError("nie wczytano modelu; " + ("; ".join(bledy) or "brak plików w /usr/share/hailo-models"))

    def _zwolnij(self):
        if self.hailo is not None:
            try:
                self.hailo.close()
            except Exception:
                pass
        self.hailo, self.model, self.temp = None, None, None
        with self.lock:
            self.wyniki = []
        self.fps = self.ms = self.obciazenie = 0.0

    def _odczytaj_temp(self):
        try:
            dev = self.hailo.target.get_physical_devices()[0]
            t = dev.control.get_chip_temperature()
            self.temp = max(t.ts0_temperature, t.ts1_temperature)
        except Exception:
            self.temp = None

    def najnowsze(self):
        with self.lock:
            return list(self.wyniki)

    def run(self):
        ostatnia, okno_t0, zajety, n, temp_t = -1, time.monotonic(), 0.0, 0, 0.0
        while self.dziala:
            if not self.wlaczony.is_set():
                if self.hailo is not None:
                    self._zwolnij()
                if not self.stan.startswith("błąd"):
                    self.stan = "wyłączone"
                time.sleep(0.1)
                continue
            if self.hailo is None:
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
            mh, mw, _ = self.hailo.get_input_shape()
            wejscie = cv2.resize(cv2.cvtColor(klatka, cv2.COLOR_BGR2RGB), (mw, mh))
            t0 = time.monotonic()
            try:
                wynik = self.hailo.run(wejscie)
            except Exception as e:
                self.stan = f"błąd: {e}"
                self.wlaczony.clear()
                continue
            dt = time.monotonic() - t0
            wykryte = []
            for klasa, dets in enumerate(wynik):  # model z NMS: lista na klasę, [y0, x0, y1, x1, pewność]
                for d in dets:
                    if d[4] >= self.prog:
                        wykryte.append((klasa, float(d[1]), float(d[0]), float(d[3]), float(d[2]), float(d[4])))
            with self.lock:
                self.wyniki = wykryte
            zajety += dt
            n += 1
            teraz = time.monotonic()
            if teraz - okno_t0 >= 1:
                okres = teraz - okno_t0
                self.obciazenie = min(100.0, 100 * zajety / okres)
                self.fps, self.ms = n / okres, 1000 * zajety / max(n, 1)
                okno_t0, zajety, n = teraz, 0.0, 0
            if teraz - temp_t >= 2:
                self._odczytaj_temp()
                temp_t = teraz
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


# ---------- interfejs ----------

TLO, PANEL, TEKST, SZARY, ZIELONY, ZOLTY, CZERWONY = (
    "#0d1114", "#161c21", "#e6ebee", "#8b979f", "#3fbf6a", "#e0a640", "#e5534b")


def kolor_temp(t, ostrz=65, alarm=80):
    if t is None:
        return SZARY
    return ZIELONY if t < ostrz else ZOLTY if t < alarm else CZERWONY


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


class Obraz(QWidget):
    def __init__(self):
        super().__init__()
        self.img, self.wyniki, self.komunikat = None, [], ""
        self.setMinimumSize(320, 240)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(TLO))
        if self.img is None:
            p.setPen(QColor(SZARY))
            p.setFont(QFont("Sans", 16))
            p.drawText(self.rect(), Qt.AlignCenter, self.komunikat)
            return
        iw, ih = self.img.width(), self.img.height()
        s = min(self.width() / iw, self.height() / ih)
        w, h = iw * s, ih * s
        x0, y0 = (self.width() - w) / 2, (self.height() - h) / 2
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(QRectF(x0, y0, w, h), self.img)
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont("Sans", 13, QFont.Bold)
        p.setFont(f)
        for klasa, a, b, c, d, pew in self.wyniki:
            kol = kolor_klasy(klasa)
            r = QRectF(x0 + a * w, y0 + b * h, (c - a) * w, (d - b) * h)
            p.setPen(QPen(kol, 3))
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
            napis = f"{KLASY[klasa] if klasa < len(KLASY) else klasa} {pew * 100:.0f}%"
            tw = p.fontMetrics().horizontalAdvance(napis) + 12
            tr = QRectF(r.left(), max(y0, r.top() - 26), tw, 26)
            p.fillRect(tr, kol)
            p.setPen(QColor("#000000"))
            p.drawText(tr, Qt.AlignCenter, napis)


class Wiersz(QWidget):
    """Etykieta, wartość i opcjonalny pasek."""

    def __init__(self, nazwa, pasek=True):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        gora = QHBoxLayout()
        self.nazwa, self.wartosc = QLabel(nazwa), QLabel("—")
        self.nazwa.setStyleSheet(f"color:{SZARY};font-size:15px")
        self.wartosc.setStyleSheet(f"color:{TEKST};font-size:17px;font-weight:600")
        gora.addWidget(self.nazwa)
        gora.addStretch()
        gora.addWidget(self.wartosc)
        lay.addLayout(gora)
        self.pasek = None
        if pasek:
            self.pasek = QProgressBar()
            self.pasek.setRange(0, 100)
            self.pasek.setTextVisible(False)
            self.pasek.setFixedHeight(8)
            lay.addWidget(self.pasek)
            self.ustaw_kolor(ZIELONY)

    def ustaw_kolor(self, kolor):
        if self.pasek:
            self.pasek.setStyleSheet(
                f"QProgressBar{{background:#2a333a;border:none;border-radius:4px}}"
                f"QProgressBar::chunk{{background:{kolor};border-radius:4px}}")

    def ustaw(self, tekst, proc=None, kolor=None):
        self.wartosc.setText(tekst)
        if kolor:
            self.wartosc.setStyleSheet(f"color:{kolor};font-size:17px;font-weight:600")
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

        self.obraz = Obraz()
        panel = QWidget()
        panel.setFixedWidth(320)
        panel.setStyleSheet(f"background:{PANEL}")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(18, 20, 18, 14)
        pl.setSpacing(9)

        tytul = QLabel("Łazik · wizja")  # krzyżyk zamykania leży po prawej, na wysokości tytułu
        tytul.setStyleSheet("font-size:22px;font-weight:700")
        tytul.setFixedHeight(34)
        pl.addWidget(tytul)

        rz = QHBoxLayout()
        etyk = QLabel("Rozpoznawanie")
        etyk.setStyleSheet("font-size:19px;font-weight:600")
        self.przelacznik = Przelacznik()
        self.przelacznik.toggled.connect(self.przelacz)
        rz.addWidget(etyk)
        rz.addStretch()
        rz.addWidget(self.przelacznik)
        pl.addLayout(rz)
        self.stan_hailo = QLabel("wyłączone")
        self.stan_hailo.setWordWrap(True)
        self.stan_hailo.setStyleSheet(f"color:{SZARY};font-size:14px")
        pl.addWidget(self.stan_hailo)

        self.prog_lbl = QLabel()
        self.prog_lbl.setStyleSheet(f"color:{SZARY};font-size:15px")
        self.prog = QSlider(Qt.Horizontal)
        self.prog.setRange(20, 90)
        self.prog.setValue(50)
        self.prog.setStyleSheet(
            "QSlider::groove:horizontal{height:8px;background:#2a333a;border-radius:4px}"
            "QSlider::handle:horizontal{width:26px;margin:-10px 0;background:#ffffff;border-radius:13px}")
        self.prog.valueChanged.connect(self.zmien_prog)
        self.zmien_prog(50)
        pl.addWidget(self.prog_lbl)
        pl.addWidget(self.prog)

        self.w_cpu = Wiersz("Procesor")
        self.w_ram = Wiersz("RAM")
        self.w_hailo = Wiersz("Hailo")
        self.w_kam = Wiersz("Kamera / detekcja", pasek=False)
        self.w_zas = Wiersz("Zasilanie", pasek=False)
        for w in (self.w_cpu, self.w_ram, self.w_hailo, self.w_kam, self.w_zas):
            pl.addWidget(w)

        wl = QLabel("Na obrazie")
        wl.setStyleSheet(f"color:{SZARY};font-size:15px;margin-top:4px")
        pl.addWidget(wl)
        self.lista = QLabel("—")
        self.lista.setWordWrap(True)
        self.lista.setAlignment(Qt.AlignTop)
        self.lista.setStyleSheet("font-size:17px")
        pl.addWidget(self.lista, 1)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.obraz, 1)
        lay.addWidget(panel)

        self.zamknij = QPushButton("✕", self)
        self.zamknij.setFixedSize(52, 52)
        self.zamknij.setCursor(Qt.PointingHandCursor)
        self.zamknij.setStyleSheet(
            f"QPushButton{{background:#2a333a;color:{TEKST};font-size:26px;border:none;border-radius:26px}}"
            f"QPushButton:pressed{{background:{CZERWONY}}}")
        self.zamknij.clicked.connect(self.close)

        self.kamera.start()
        self.detektor.start()
        self.t_obraz = QTimer(self, timeout=self.rysuj)
        self.t_obraz.start(33)
        self.t_stat = QTimer(self, timeout=self.statystyki)
        self.t_stat.start(1000)
        self.statystyki()

        if "--rozpoznawanie" in sys.argv:  # start z włączonym Hailo (do testów)
            self.przelacznik.setChecked(True)

    def resizeEvent(self, e):
        self.zamknij.move(self.width() - 64, 10)
        self.zamknij.raise_()
        super().resizeEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Escape, Qt.Key_Q):
            self.close()

    def przelacz(self, wl):
        if wl:
            self.detektor.stan = "ładuję model…"
            self.detektor.wlaczony.set()
        else:
            self.detektor.wlaczony.clear()

    def zmien_prog(self, v):
        self.detektor.prog = v / 100
        self.prog_lbl.setText(f"Próg pewności: {v}%")

    def rysuj(self):
        klatka, _ = self.kamera.najnowsza()
        if klatka is None:
            self.obraz.img, self.obraz.komunikat = None, self.kamera.stan
        else:
            rgb = cv2.cvtColor(klatka, cv2.COLOR_BGR2RGB)
            h, w, _ = rgb.shape
            self.obraz.img = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        self.obraz.wyniki = self.detektor.najnowsze() if self.przelacznik.isChecked() else []
        self.obraz.update()

    def statystyki(self):
        s, d = self.system, self.detektor
        s.odswiez()
        t_cpu = f" · {s.temp:.0f} °C" if s.temp is not None else ""
        self.w_cpu.ustaw(f"{s.cpu:.0f}%{t_cpu}", s.cpu, kolor=kolor_temp(s.temp, 70, 80))
        self.w_ram.ustaw(f"{s.ram_uzyte:.1f} / {s.ram_razem:.1f} GB", s.ram_proc)
        if d.hailo is not None:
            t_h = f" · {d.temp:.0f} °C" if d.temp is not None else ""
            self.w_hailo.ustaw(f"{d.obciazenie:.0f}%{t_h}", d.obciazenie, kolor=kolor_temp(d.temp))
            det = f"{d.fps:.0f} kl/s, {d.ms:.0f} ms"
        else:
            self.w_hailo.ustaw("bezczynne", 0, kolor=SZARY)
            det = "wył."
        kam = f"{self.kamera.fps:.0f} kl/s" if self.kamera.fps else "brak"
        self.w_kam.ustaw(f"{kam} / {det}")
        self.w_kam.setToolTip(self.kamera.stan)
        self.w_zas.ustaw(s.zasilanie, kolor=ZIELONY if s.zasilanie == "OK" else ZOLTY)
        blad = d.stan.startswith("błąd")
        self.stan_hailo.setText(d.stan)
        self.stan_hailo.setStyleSheet(f"color:{CZERWONY if blad else SZARY};font-size:14px")
        if blad and self.przelacznik.isChecked():
            self.przelacznik.blockSignals(True)
            self.przelacznik.setChecked(False)
            self.przelacznik.blockSignals(False)
        if self.przelacznik.isChecked():
            licz = Counter(KLASY[k] if k < len(KLASY) else str(k) for k, *_ in self.detektor.najnowsze())
            self.lista.setText("\n".join(f"{n} × {k}" if n > 1 else k for k, n in licz.most_common(10)) or "nic")
        else:
            self.lista.setText("— (rozpoznawanie wyłączone)")

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
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
