"""Tryb „Przestrzeń”: głębia z jednej kamery, opis otoczenia i skan 3D do obejrzenia jak prosta gra.

Głębia z jednej kamery jest WZGLĘDNA (model zgaduje ją z wyglądu obrazu), więc odległości są orientacyjne.
Skan zakłada, że kamera stoi w miejscu i się obraca (obrót liczony z dopasowania punktów ORB między klatkami).
To prototyp toru: kamera → głębia → chmura punktów → podgląd. Docelowo głębię da kamera OAK-D Lite, a położenie
odometria łazika; format skanu i przeglądarka zostają te same.
"""

import base64
import json
import math
import os
import shutil
import time

import cv2
import numpy as np

HFOV = 60.0           # kąt widzenia kamery w poziomie [°] (Logitech C170, przybliżenie)
WOKSEL = 0.04         # rozdzielczość chmury [m]
MAKS_PUNKTOW = 400_000
KATALOG = os.path.dirname(os.path.abspath(__file__))
MODELE = os.path.join(KATALOG, "modele")
SKANY = os.path.join(KATALOG, "skany")


class Glebia:
    """Model głębi: scdepthv3 na Hailo (modele/scdepthv3.hef) albo MiDaS small na procesorze (modele/midas_small.onnx)."""

    def __init__(self):
        self.hailo, self.net, self.nazwa, self.metryczna = None, None, None, False

    def zaladuj(self):
        if self.hailo is not None or self.net is not None:  # już wczytany: zostaje na chipie
            return
        hef = os.path.join(MODELE, "scdepthv3.hef")
        onnx = os.path.join(MODELE, "midas_small.onnx")
        bledy = []
        if os.path.exists(hef):
            try:
                from picamera2.devices import Hailo
                self.hailo = Hailo(hef)
                self.nazwa, self.metryczna = "scdepthv3 (Hailo)", False  # skala modelu nie jest metryczna
                return
            except Exception as e:
                bledy.append(f"scdepthv3: {e}")
        if os.path.exists(onnx):
            try:
                self.net = cv2.dnn.readNet(onnx)
                self.nazwa, self.metryczna = "MiDaS small (procesor)", False
                return
            except Exception as e:
                bledy.append(f"MiDaS: {e}")
        raise RuntimeError("brak modelu głębi (uruchom ./instaluj.sh)" + (": " + "; ".join(bledy) if bledy else ""))

    def zwolnij(self):
        """Nic nie robi: model zostaje wczytany (zwalnianie Hailo w trakcie pracy jest zawodne)."""

    def licz(self, bgr):
        """Mapa głębi (większa liczba = dalej), względna: kształt sceny się zgadza, skala nie."""
        if self.hailo is not None:
            h, w, _ = self.hailo.get_input_shape()
            x = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), (w, h))
            out = np.squeeze(np.asarray(self.hailo.run(x), dtype=np.float32))
            return 1.0 / (1.0 / (1.0 + np.exp(-out)) * 10.0 + 0.009)  # jak w post-processingu Hailo TAPPAS
        blob = cv2.dnn.blobFromImage(bgr, 1 / (0.226 * 255), (256, 256), (123.675, 116.28, 103.53), swapRB=True)
        self.net.setInput(blob)
        odwr = np.squeeze(self.net.forward()).astype(np.float32)  # MiDaS daje odwrotność głębi (względną)
        odwr = np.maximum(odwr, np.percentile(odwr, 99) * 0.02)
        return np.percentile(odwr, 50) / odwr * 2.0


def mapa_kolorow(glebia, ksztalt):
    """Kolorowa mapa głębi (blisko = czerwone, daleko = niebieskie) w rozmiarze klatki."""
    odwr = 1.0 / np.maximum(glebia, 1e-3)
    lo, hi = np.percentile(odwr, 2), np.percentile(odwr, 98)
    n = np.clip((odwr - lo) / max(hi - lo, 1e-6), 0, 1)
    kol = cv2.applyColorMap((n * 255).astype(np.uint8), cv2.COLORMAP_TURBO)
    return cv2.resize(kol, (ksztalt[1], ksztalt[0]))


def opisz_glebie(glebia, metryczna):
    """Słowny opis: co jest blisko, a co daleko, w trzech pasach (lewo, środek, prawo)."""
    h, w = glebia.shape
    pas = glebia[int(h * 0.25):int(h * 0.85)]  # bez sufitu i samego dołu kadru
    med = float(np.median(glebia))
    czesci = []
    najblizej = None
    for nazwa, skrot, a, b in (("po lewej", "L", 0, w // 3), ("na wprost", "Ś", w // 3, 2 * w // 3),
                               ("po prawej", "P", 2 * w // 3, w)):
        d = float(np.percentile(pas[:, a:b], 15))
        if metryczna:
            slowo = f"≈{d:.1f} m".replace(".", ",")
        else:
            r = d / med
            slowo = "blisko" if r < 0.6 else "średnio" if r < 1.2 else "daleko"
        czesci.append(f"{skrot}: {slowo}")
        if najblizej is None or d < najblizej[1]:
            najblizej = (nazwa, d)
    wprost = float(np.percentile(pas[:, w // 3:2 * w // 3], 15))
    wolne = "Na wprost wolno" if wprost > med * 0.9 else "Przeszkoda na wprost"
    return f"{wolne}, najbliżej {najblizej[0]}.\n" + " · ".join(czesci)


def _macierz_k(w, h):
    f = (w / 2) / math.tan(math.radians(HFOV) / 2)
    return np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], dtype=np.float64)


def _kat(R):
    return math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(R) - 1) / 2))))


class Skaner:
    """Składa chmurę punktów z kolejnych map głębi, licząc obrót kamery między klatkami."""

    def __init__(self):
        self.orb = cv2.ORB_create(800)
        self.bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        self.metryczna = False        # True, gdy model głębi daje (w przybliżeniu) metry
        self.wyczysc()

    def wyczysc(self):
        self.R = np.eye(3)            # obrót świat → kamera; świat = pierwsza klatka skanu
        self.R_klucz = None
        self.poprz = None             # (punkty kluczowe, deskryptory) poprzedniej klatki
        self.skala = None
        self.pkt = np.zeros((0, 3), np.float32)
        self.kol = np.zeros((0, 3), np.uint8)
        self.klatki_kluczowe = 0
        self.stan = "gotowy: stań w miejscu i powoli obracaj kamerę"
        self.obrot = 0.0              # suma obrotów w poziomie [°], do pokazania postępu

    def katy(self):
        przod = self.R.T @ np.array([0.0, 0.0, 1.0])
        odchyl = math.degrees(math.atan2(przod[0], przod[2]))
        pochyl = math.degrees(math.atan2(-przod[1], math.hypot(przod[0], przod[2])))
        return odchyl, pochyl

    def krok(self, bgr, glebia):
        maly = cv2.cvtColor(cv2.resize(bgr, (320, 240)), cv2.COLOR_BGR2GRAY)
        kp, des = self.orb.detectAndCompute(maly, None)
        if self.poprz is None:
            if des is None or len(kp) < 30:
                self.stan = "za mało szczegółów w kadrze: skieruj kamerę na coś wyraźnego"
                return
            self.poprz = (kp, des)
            self._dodaj(bgr, glebia)
            return
        if des is None or len(kp) < 30:
            self.stan = "zgubiłem orientację: wróć kamerą wolniej"
            return
        dop = self.bf.match(self.poprz[1], des)
        if len(dop) < 25:
            self.stan = "zgubiłem orientację: wróć kamerą wolniej"
            return
        a = np.float32([self.poprz[0][m.queryIdx].pt for m in dop])
        b = np.float32([kp[m.trainIdx].pt for m in dop])
        H, maska = cv2.findHomography(a, b, cv2.RANSAC, 3.0)
        if H is None or int(maska.sum()) < 20:
            self.stan = "zgubiłem orientację: wróć kamerą wolniej"
            return
        K = _macierz_k(320, 240)
        R_wzg = np.linalg.inv(K) @ H @ K
        U, _, Vt = np.linalg.svd(R_wzg)
        R_wzg = U @ Vt
        if np.linalg.det(R_wzg) < 0:
            R_wzg = -R_wzg
        kat = _kat(R_wzg)
        if kat > 20:  # nierealny skok między klatkami: pomijamy
            return
        self.R = R_wzg @ self.R
        self.poprz = (kp, des)
        self.obrot += abs(math.degrees(math.atan2(R_wzg[0, 2], R_wzg[2, 2])))
        if self.R_klucz is None or _kat(self.R @ self.R_klucz.T) > 5:
            self._dodaj(bgr, glebia)
        self.stan = "skanuję"

    def _dodaj(self, bgr, glebia):
        W, H = 96, 72
        d = cv2.resize(glebia, (W, H), interpolation=cv2.INTER_AREA)
        kol = cv2.cvtColor(cv2.resize(bgr, (W, H), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
        if self.skala is None:
            self.skala = 1.0 if self.metryczna else 2.0 / max(float(np.median(d)), 1e-6)
        z = d * self.skala
        # odrzucamy „latające” punkty na krawędziach obiektów (duży skok głębi wokół piksela)
        mx = cv2.dilate(z, np.ones((3, 3), np.uint8))
        mn = cv2.erode(z, np.ones((3, 3), np.uint8))
        ok = (z > 0.2) & (z < 8.0) & (mx / np.maximum(mn, 1e-6) < 1.12)
        f = (W / 2) / math.tan(math.radians(HFOV) / 2)
        u, v = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
        x, y = (u - W / 2) / f * z, (v - H / 2) / f * z
        Pc = np.stack([x[ok], y[ok], z[ok]], axis=1)
        Pw = (self.R.T @ Pc.T).T.astype(np.float32)
        self.pkt = np.concatenate([self.pkt, Pw])
        self.kol = np.concatenate([self.kol, kol[ok]])
        klucze = np.floor(self.pkt / WOKSEL).astype(np.int32)
        _, idx = np.unique(klucze, axis=0, return_index=True)
        idx = np.sort(idx)[-MAKS_PUNKTOW:]
        self.pkt, self.kol = self.pkt[idx], self.kol[idx]
        self.R_klucz = self.R.copy()
        self.klatki_kluczowe += 1

    def zapisz(self, opis=""):
        """Zapisuje skan do skany/RRRR-MM-DD_GGMM_skan/: skan.html (przeglądarka), chmura.ply, info.json."""
        if len(self.pkt) == 0:
            raise RuntimeError("skan jest pusty")
        baza = time.strftime("%Y-%m-%d_%H%M") + "_skan"
        katalog, nr = os.path.join(SKANY, baza), 2
        while os.path.exists(katalog):
            katalog, nr = os.path.join(SKANY, f"{baza}_{nr}"), nr + 1
        os.makedirs(katalog)
        nazwa = os.path.basename(katalog)
        # układ przeglądarki (three.js): y w górę, patrzymy wzdłuż -z
        pkt3 = np.stack([self.pkt[:, 0], -self.pkt[:, 1], -self.pkt[:, 2]], axis=1).astype("<f4")
        with open(os.path.join(katalog, "chmura.ply"), "wb") as f:
            f.write((f"ply\nformat binary_little_endian 1.0\ncomment Lazik: skan {nazwa}\nelement vertex {len(pkt3)}\n"
                     "property float x\nproperty float y\nproperty float z\n"
                     "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n").encode())
            rek = np.zeros(len(pkt3), dtype=[("p", "<f4", 3), ("c", "u1", 3)])
            rek["p"], rek["c"] = pkt3, self.kol
            f.write(rek.tobytes())
        info = dict(nazwa=nazwa, czas=time.strftime("%Y-%m-%d %H:%M:%S"), punkty=int(len(pkt3)),
                    klatki_kluczowe=self.klatki_kluczowe, obrot_stopnie=round(self.obrot), opis=opis,
                    uwaga="głębia z jednej kamery: skala i odległości orientacyjne")
        json.dump(info, open(os.path.join(katalog, "info.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        dane = dict(info, pos=base64.b64encode(pkt3.tobytes()).decode(), kol=base64.b64encode(self.kol.tobytes()).decode())
        szablon = open(os.path.join(KATALOG, "podglad3d.html"), encoding="utf-8").read()
        open(os.path.join(katalog, "skan.html"), "w", encoding="utf-8").write(
            szablon.replace("/*__DANE__*/null", json.dumps(dane, ensure_ascii=False)))
        three = os.path.join(KATALOG, "three.min.js")
        if os.path.exists(three):
            shutil.copy(three, katalog)
        return katalog
