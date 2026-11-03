"""Percepcja łazika: kamera USB (włączana na żądanie), obiekty YOLO na Hailo ze śledzeniem i głębia scdepthv3
z podziałem na 5 sektorów (lewo … prawo), z których tryby jazdy wiedzą, gdzie jest wolno, a gdzie przeszkoda.

Kamera i Hailo pracują tylko, gdy ktoś ogląda stronę albo działa tryb jazdy; po 10 s bez potrzeby kamera się zamyka.
Wszystko, co da się ustawić (rozdzielczość, obrót, model, próg, głębia, limit klatek), czytane jest z konfiguracji
przy każdej klatce, więc zmiany na stronie działają od razu.
"""

import os
import subprocess
import sys
import threading
import time

import cv2

KATALOG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(KATALOG), "wizja"))
import przestrzen as P  # noqa: E402
import przeszkody as Z  # noqa: E402
import ustawienia as U  # noqa: E402
from wizja import MODELE, Sledzenie, nazwa, znajdz_kamere_usb  # noqa: E402

class Kamera(threading.Thread):
    """Kamera USB według ustawień; `odbiorcy` dostają każdą klatkę (np. nagrywanie w trybie Zwiedzaj)."""

    def __init__(self, konf):
        super().__init__(daemon=True)
        self.konf = konf
        self.lock = threading.Lock()
        self.klatka, self.nr = None, 0
        self.stan, self.fps = "otwieram…", 0.0
        self.dziala = True
        self.odbiorcy = []
        self.urzadzenie = None
        self.otworz_ponownie = False

    def najnowsza(self):
        with self.lock:
            return self.klatka, self.nr

    def run(self):
        while self.dziala:
            dev = znajdz_kamere_usb()
            self.urzadzenie = f"/dev/video{dev}"
            cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
            if not cap.isOpened():
                self.stan = f"brak kamery USB ({self.urzadzenie})"
                time.sleep(2)
                continue
            k = self.konf
            szer, wys = (int(x) for x in str(k["kamera_rozdzielczosc"]).split("x"))
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, szer)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, wys)
            cap.set(cv2.CAP_PROP_FPS, int(k["kamera_fps"]))
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if k["kamera_stale_kl_s"]:
                subprocess.run(["v4l2-ctl", "-d", self.urzadzenie, "-c", "exposure_dynamic_framerate=0"], capture_output=True)
            for nazwa_k, wartosc in k.get("kamera_v4l2", {}).items():  # zapamiętane regulacje (jasność, kontrast…)
                try:
                    U.ustaw_kontrolke(self.urzadzenie, nazwa_k, wartosc)
                except Exception:
                    pass
            w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.stan = f"{self.urzadzenie} · {w}×{h}"
            self.otworz_ponownie = False
            t0, n = time.monotonic(), 0
            while self.dziala and not self.otworz_ponownie:
                ok, f = cap.read()
                if not ok:
                    self.stan = "kamera przestała odpowiadać"
                    break
                if k["obrot"] == 180:
                    f = cv2.rotate(f, cv2.ROTATE_180)
                if k["lustro"]:
                    f = cv2.flip(f, 1)
                with self.lock:
                    self.klatka, self.nr = f, self.nr + 1
                for odb in list(self.odbiorcy):
                    odb(f, time.time())
                n += 1
                if time.monotonic() - t0 >= 1:
                    self.fps, t0, n = n / (time.monotonic() - t0), time.monotonic(), 0
            cap.release()
            if not self.otworz_ponownie:
                time.sleep(1)


class Percepcja(threading.Thread):
    def __init__(self, konf):
        super().__init__(daemon=True)
        self.konf = konf
        self.lock = threading.Lock()
        self.kamera = None
        self.hailo, self._model_nr, self._modele = None, None, {}
        self.glebia = P.Glebia()
        self.sled = Sledzenie()
        self.potrzebna_glebia = False
        self.glebia_wstrzymana = False   # na czas analizy skanu 3D (głębia potrzebna analizie)
        self._uzycie = 0.0
        self._dev_temp = None
        self.klatka, self.nr, self.mapa = None, 0, None
        self.obiekty, self.sektory = [], None   # sektory: odległość [m] do przeszkody w 5 pasach (9.99 = wolne)
        self.podstawy = None                     # wiersz (0..1), gdzie w danym pasie kończy się podłoga
        self.przeplyw = Z.Przeplyw()
        self.ttc, self.ruch_obrazu = [None] * Z.SEKTORY, 0.0
        self.analiza = dict(obiekty=False, glebia=False, przeplyw=False)   # co faktycznie jest liczone
        self.fps = self.ms = 0.0
        self.hailo_proc = 0.0           # część każdej sekundy, którą Hailo spędza na naszych sieciach
        self.temp_hailo = None
        self.blad = None
        self.stan_kamery = "wyłączona"
        self.nazwa_modelu = None

    def potrzebna(self):
        """Wołane przez stronę (podgląd) i tryby jazdy; podtrzymuje kamerę i Hailo."""
        self._uzycie = time.monotonic()

    def hailo_wczytane(self):
        return self.hailo is not None or self.glebia.hailo is not None

    def najnowsze(self):
        with self.lock:
            return self.klatka, self.nr, list(self.obiekty), self.sektory

    def do_podgladu(self):
        """Klatka do strumienia: sam obraz albo obraz + kolorowa mapa głębi."""
        with self.lock:
            k, nr, m = self.klatka, self.nr, self.mapa
        if k is not None and self.konf["strumien_glebia"] and m is not None:
            k = cv2.hconcat([k, P.mapa_kolorow(m, k.shape)])
        return k, nr

    def ponownie_kamera(self):
        if self.kamera is not None:
            self.kamera.otworz_ponownie = True

    def _kamera(self, wlacz):
        if wlacz and self.kamera is None:
            self.kamera = Kamera(self.konf)
            self.kamera.start()
        elif not wlacz and self.kamera is not None:
            self.kamera.dziala = False
            self.kamera = None
            with self.lock:
                self.klatka, self.obiekty, self.sektory, self.mapa = None, [], None, None
            self.stan_kamery = "wyłączona"

    def _model(self):
        """Wczytuje wybrany model (raz; zostaje na chipie, bo zwalnianie Hailo w trakcie pracy jest zawodne)."""
        nr = int(self.konf["model_obiektow"])
        if self._model_nr == nr and self.hailo is not None:
            return
        sciezka = next((p for p in MODELE[nr][1] if os.path.exists(p)), None)
        if sciezka is None:
            self.blad = f"brak pliku modelu {MODELE[nr][0]} (uruchom instaluj.sh w „Łazik: wizja”); używam YOLOv8s"
            nr = 0
            sciezka = next(p for p in MODELE[0][1] if os.path.exists(p))
        if sciezka not in self._modele:
            from picamera2.devices import Hailo
            self._modele[sciezka] = Hailo(sciezka)
        self.hailo, self._model_nr, self.nazwa_modelu = self._modele[sciezka], nr, MODELE[nr][0]
        self.sled = Sledzenie()

    def run(self):
        ostatni, okno, n, t_temp, zajety = -1, time.monotonic(), 0, 0.0, 0.0
        while True:
            if time.monotonic() - self._uzycie > 10:
                self._kamera(False)
                self.fps = self.hailo_proc = 0.0
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
            obiekty, sektory, mapa = [], None, None
            # tryby jazdy wymuszają analizę; w Stop i Ręcznym liczy się tylko to, co włączone (Hailo odpoczywa i chłodnieje)
            chce_obiekty = self.potrzebna_glebia or self.konf["analiza_obiekty"]
            chce_glebie = self.potrzebna_glebia or self.konf["glebia_zawsze"] or self.konf["strumien_glebia"]
            self.analiza = dict(obiekty=chce_obiekty, glebia=chce_glebie and not self.glebia_wstrzymana,
                                przeplyw=self.potrzebna_glebia)
            try:
                if chce_obiekty:
                    self._model()
                    mh, mw, _ = self.hailo.get_input_shape()
                    out = self.hailo.run(cv2.resize(cv2.cvtColor(klatka, cv2.COLOR_BGR2RGB), (mw, mh)))
                    prog = self.konf["prog_pewnosci"]
                    wyk = [(k, float(d[1]), float(d[0]), float(d[3]), float(d[2]), float(d[4]))
                           for k, ds in enumerate(out) for d in ds if d[4] >= prog]
                    obiekty = self.sled.aktualizuj(wyk, time.monotonic())
                    for o in obiekty:
                        o["nazwa"] = nazwa(o["klasa"])
                if not chce_glebie or self.glebia_wstrzymana:
                    self.podstawy = None
                if chce_glebie and not self.glebia_wstrzymana:
                    self.glebia.zaladuj()
                    mapa = self.glebia.licz(klatka)
                    prof = Z.profil_sektorow(mapa, self.konf)
                    sektory, self.podstawy = [d for d, _ in prof], [y for _, y in prof]
                if self.potrzebna_glebia:   # tryby jazdy: czas do zderzenia i ruch obrazu
                    self.przeplyw.aktualizuj(klatka, time.monotonic(), self.konf.get("horyzont", 0.5))
                    self.ttc, self.ruch_obrazu = list(self.przeplyw.ttc), self.przeplyw.ruch
                if self.blad and not self.blad.startswith("brak pliku"):
                    self.blad = None
            except Exception as e:
                msg = str(e)
                if "physical devices" in msg.lower() or "OUT_OF_PHYSICAL" in msg:
                    msg = "Hailo zajęte przez inną aplikację (zamknij „Łazik: wizja” / „analiza wideo”)"
                self.blad = msg
                time.sleep(1)
            with self.lock:
                self.klatka, self.nr, self.obiekty, self.sektory, self.mapa = klatka, nr, obiekty, sektory, mapa
            n += 1
            teraz = time.monotonic()
            self.ms = 1000 * (teraz - t0)
            zajety += teraz - t0
            if teraz - okno >= 1:
                self.hailo_proc = min(100.0, 100 * zajety / (teraz - okno))
                self.fps, okno, n, zajety = n / (teraz - okno), teraz, 0, 0.0
            if teraz - t_temp > 2 and self.hailo_wczytane():
                t_temp = teraz
                try:
                    if self._dev_temp is None:
                        self._dev_temp = (self.hailo or self.glebia.hailo).target.get_physical_devices()[0]
                    t = self._dev_temp.control.get_chip_temperature()
                    self.temp_hailo = max(t.ts0_temperature, t.ts1_temperature)
                except Exception:
                    pass
            przerwa = 1.0 / max(1, self.konf["maks_kl_s"]) - (time.monotonic() - t0)  # limit klatek (chłodzenie, prąd)
            if przerwa > 0:
                time.sleep(przerwa)
