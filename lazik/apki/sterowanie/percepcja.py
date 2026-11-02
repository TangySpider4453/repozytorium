"""Percepcja łazika: kamera USB (włączana na żądanie), obiekty YOLOv8s na Hailo ze śledzeniem i głębia scdepthv3
z podziałem na 5 sektorów (lewo … prawo), z których tryby jazdy wiedzą, gdzie jest wolno, a gdzie przeszkoda.

Kamera i Hailo pracują tylko, gdy ktoś ogląda stronę albo działa tryb jazdy; po 10 s bez potrzeby kamera się zamyka.
"""

import os
import sys
import threading
import time

import numpy as np

KATALOG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(KATALOG), "wizja"))
import przestrzen as P  # noqa: E402
from wizja import MODELE, Kamera, Sledzenie, nazwa  # noqa: E402

SEKTORY = 5


def sektory_glebi(glebia):
    """Względna odległość w 5 pionowych pasach (środkowa część kadru, bez podłogi tuż przed kołami).
    1.0 = typowa odległość w kadrze, < 0.45 = coś blisko. Głębia z jednej kamery jest względna."""
    h, w = glebia.shape
    pas = glebia[int(h * 0.35):int(h * 0.80)]
    odn = max(float(np.percentile(glebia, 60)), 1e-6)
    return [float(np.percentile(pas[:, int(i * w / SEKTORY):int((i + 1) * w / SEKTORY)], 20)) / odn
            for i in range(SEKTORY)]


class Percepcja(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.lock = threading.Lock()
        self.kamera = None
        self.hailo = None
        self.glebia = P.Glebia()
        self.sled = Sledzenie()
        self.potrzebna_glebia = False
        self.glebia_wstrzymana = False   # na czas analizy skanu 3D (głębia potrzebna analizie)
        self._uzycie = 0.0
        self._dev_temp = None
        self.klatka, self.nr = None, 0
        self.obiekty, self.sektory = [], None
        self.fps = self.ms = 0.0
        self.temp_hailo = None
        self.blad = None
        self.stan_kamery = "wyłączona"

    def potrzebna(self):
        """Wołane przez stronę (podgląd) i tryby jazdy; podtrzymuje kamerę i Hailo."""
        self._uzycie = time.monotonic()

    def hailo_wczytane(self):
        return self.hailo is not None or self.glebia.hailo is not None

    def najnowsze(self):
        with self.lock:
            return self.klatka, self.nr, list(self.obiekty), self.sektory

    def _kamera(self, wlacz):
        if wlacz and self.kamera is None:
            self.kamera = Kamera()
            self.kamera.start()
        elif not wlacz and self.kamera is not None:
            self.kamera.dziala = False
            self.kamera = None
            with self.lock:
                self.klatka, self.obiekty, self.sektory = None, [], None
            self.stan_kamery = "wyłączona"

    def run(self):
        ostatni, okno, n, t_temp = -1, time.monotonic(), 0, 0.0
        while True:
            if time.monotonic() - self._uzycie > 10:
                self._kamera(False)
                time.sleep(0.2)
                continue
            self._kamera(True)
            self.stan_kamery = self.kamera.stan
            klatka, nr = self.kamera.najnowsza()
            if klatka is None or nr == ostatni:
                time.sleep(0.005)
                continue
            ostatni = nr
            t0 = time.monotonic()
            obiekty, sektory = [], None
            try:
                if self.hailo is None:
                    from picamera2.devices import Hailo
                    self.hailo = Hailo(next(p for p in MODELE[0][1] if os.path.exists(p)))
                import cv2
                mh, mw, _ = self.hailo.get_input_shape()
                out = self.hailo.run(cv2.resize(cv2.cvtColor(klatka, cv2.COLOR_BGR2RGB), (mw, mh)))
                wyk = [(k, float(d[1]), float(d[0]), float(d[3]), float(d[2]), float(d[4]))
                       for k, ds in enumerate(out) for d in ds if d[4] >= 0.45]
                obiekty = self.sled.aktualizuj(wyk, time.monotonic())
                for o in obiekty:
                    o["nazwa"] = nazwa(o["klasa"])
                if self.potrzebna_glebia and not self.glebia_wstrzymana:
                    self.glebia.zaladuj()
                    sektory = sektory_glebi(self.glebia.licz(klatka))
                self.blad = None
            except Exception as e:
                msg = str(e)
                if "physical devices" in msg.lower() or "OUT_OF_PHYSICAL" in msg:
                    msg = "Hailo zajęte przez inną aplikację (zamknij „Łazik: wizja” / „analiza wideo”)"
                self.blad = msg
                time.sleep(1)
            with self.lock:
                self.klatka, self.nr, self.obiekty, self.sektory = klatka, nr, obiekty, sektory
            n += 1
            teraz = time.monotonic()
            self.ms = 1000 * (teraz - t0)
            if teraz - okno >= 1:
                self.fps, okno, n = n / (teraz - okno), teraz, 0
            if teraz - t_temp > 2 and self.hailo_wczytane():
                t_temp = teraz
                try:
                    if self._dev_temp is None:
                        self._dev_temp = (self.hailo or self.glebia.hailo).target.get_physical_devices()[0]
                    t = self._dev_temp.control.get_chip_temperature()
                    self.temp_hailo = max(t.ts0_temperature, t.ts1_temperature)
                except Exception:
                    pass
