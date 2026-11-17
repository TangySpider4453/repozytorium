"""Tryb „Przestrzeń”: głębia z jednej kamery, nagrywanie i analiza nagrania do skanu 3D (podgląd jak prosta gra).

Głębia z jednej kamery jest WZGLĘDNA (model zgaduje ją z wyglądu obrazu), więc skala i odległości są orientacyjne.
scdepthv3 jest jednak „scale-consistent”: skala jest podobna między kolejnymi klatkami, dlatego analiza może liczyć
pełny ruch kamery (obrót i przesunięcie) metodą PnP: punkty ORB z poprzedniej klatki dostają głębokość z mapy głębi,
a ich położenie w następnej klatce wyznacza ruch. Przy zbyt małej liczbie dopasowań zostaje sam obrót (homografia).

Tor: nagranie (wideo MJPG + czasy) → analiza na pełnych obrotach (Hailo seriami, ORB na kilku rdzeniach) →
chmura punktów → skan.html. Docelowo głębię da OAK-D Lite, a ruch odometria łazika; format i podgląd zostają.
"""

import base64
import json
import math
import os
import queue
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

HFOV = 60.0           # kąt widzenia kamery w poziomie [°] (Logitech C170, przybliżenie)
WOKSEL = 0.02         # rozdzielczość chmury [m w skali skanu]
MAKS_PUNKTOW = 900_000
SKALA_STARTU = 2.0    # mediana głębi pierwszej klatki przyjmowana jako 2 m
KATALOG = os.path.dirname(os.path.abspath(__file__))
MODELE = os.path.join(KATALOG, "modele")
SKANY = os.path.join(KATALOG, "skany")
NAGRANIA = os.path.join(KATALOG, "nagrania")


# ---------- głębia ----------

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

    def _wejscie(self, bgr):
        h, w, _ = self.hailo.get_input_shape()
        return cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), (w, h))

    @staticmethod
    def _z_wyjscia(out):
        out = np.squeeze(np.asarray(out, dtype=np.float32))
        return 1.0 / (1.0 / (1.0 + np.exp(-out)) * 10.0 + 0.009)  # jak w post-processingu Hailo TAPPAS

    def licz(self, bgr):
        """Mapa głębi (większa liczba = dalej), względna: kształt sceny się zgadza, skala nie."""
        if self.hailo is not None:
            return self._z_wyjscia(self.hailo.run(self._wejscie(bgr)))
        blob = cv2.dnn.blobFromImage(bgr, 1 / (0.226 * 255), (256, 256), (123.675, 116.28, 103.53), swapRB=True)
        self.net.setInput(blob)
        odwr = np.squeeze(self.net.forward()).astype(np.float32)  # MiDaS daje odwrotność głębi (względną)
        odwr = np.maximum(odwr, np.percentile(odwr, 99) * 0.02)
        return np.percentile(odwr, 50) / odwr * 2.0

    def licz_serie(self, klatki):
        """Głębia dla kilku klatek naraz: na Hailo wszystkie zlecenia idą od razu, więc chip nie czeka na procesor."""
        if self.hailo is None:
            return [self.licz(k) for k in klatki]
        zlecenia = [self.hailo.run_async(self._wejscie(k)) for k in klatki]
        return [self._z_wyjscia(z.result()) for z in zlecenia]


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


# ---------- nagrywanie ----------

class Nagrywanie:
    """Zapisuje każdą klatkę z kamery (wideo MJPG + czasy) w osobnym wątku, żeby nie spowalniać podglądu."""

    def __init__(self):
        self.aktywne = False
        self.kolejka = queue.Queue(maxsize=240)
        self.katalog, self.klatki, self.pominiete, self.start = None, 0, 0, 0.0

    def zacznij(self):
        os.makedirs(NAGRANIA, exist_ok=True)
        baza = time.strftime("%Y-%m-%d_%H%M%S") + "_nagranie"
        self.katalog = os.path.join(NAGRANIA, baza)
        os.makedirs(self.katalog)
        self.klatki, self.pominiete, self.start = 0, 0, time.time()
        self.aktywne = True
        self._watek = threading.Thread(target=self._zapisuj, daemon=True)
        self._watek.start()

    def dodaj(self, klatka, czas):
        """Wołane z wątku kamery dla każdej klatki."""
        if not self.aktywne:
            return
        try:
            self.kolejka.put_nowait((klatka, czas))
        except queue.Full:
            self.pominiete += 1

    def zakoncz(self):
        if not self.aktywne:
            return None
        self.aktywne = False
        self.kolejka.put(None)
        self._watek.join(timeout=30)
        return self.katalog

    def _zapisuj(self):
        pisarz, czasy = None, []
        while True:
            el = self.kolejka.get()
            if el is None:
                break
            klatka, czas = el
            if pisarz is None:
                h, w = klatka.shape[:2]
                pisarz = cv2.VideoWriter(os.path.join(self.katalog, "wideo.avi"),
                                         cv2.VideoWriter_fourcc(*"MJPG"), 30, (w, h))
            pisarz.write(klatka)
            czasy.append(czas)
            self.klatki += 1
        if pisarz is not None:
            pisarz.release()
        with open(os.path.join(self.katalog, "czasy.txt"), "w") as f:
            f.write("\n".join(f"{c:.4f}" for c in czasy))
        dl = (czasy[-1] - czasy[0]) if len(czasy) > 1 else 0.0
        json.dump(dict(klatki=self.klatki, pominiete=self.pominiete, sekundy=round(dl, 1),
                       kl_s=round(self.klatki / dl, 1) if dl else 0, czas=time.strftime("%Y-%m-%d %H:%M:%S")),
                  open(os.path.join(self.katalog, "info.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def lista_nagran():
    wynik = []
    for kat in sorted((os.path.join(NAGRANIA, d) for d in os.listdir(NAGRANIA)) if os.path.isdir(NAGRANIA) else [],
                      reverse=True):
        try:
            info = json.load(open(os.path.join(kat, "info.json"), encoding="utf-8"))
        except Exception:
            continue
        wynik.append(dict(info, katalog=kat, nazwa=os.path.basename(kat),
                          skan=info.get("skan"), werdykt=info.get("werdykt")))
    return wynik


# ---------- analiza nagrania ----------

def _macierz_k(w, h):
    f = (w / 2) / math.tan(math.radians(HFOV) / 2)
    return np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], dtype=np.float64)


def _kat(R):
    return math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(R) - 1) / 2))))


class Analiza(threading.Thread):
    """Przerabia nagranie na chmurę punktów. Hailo liczy głębię seriami po 8 klatek, ORB idzie równolegle
    na 3 rdzeniach, a ruch kamery (PnP z głębią) liczony jest po kolei. Postęp w self.stan (czyta interfejs)."""

    SERIA = 8

    def __init__(self, katalog, glebia, wideo=None):
        super().__init__(daemon=True)
        self.katalog, self.glebia = katalog, glebia
        self.wideo = wideo or os.path.join(katalog, "wideo.avi")  # także dowolny film (np. z telefonu)
        self.przerwij = False
        self.lock = threading.Lock()
        self.podglad = None  # (klatka, mapa głębi) ostatnio przetworzonej klatki
        self.stan = dict(etap="start", gotowe=0, razem=0, kl_s=0.0, zostalo=None, punkty=0, kluczowe=0,
                         zgubione=0, droga=0.0, obrot=0.0, hailo_ms=0.0, wynik=None, blad=None, werdykt=None)

    def _ustaw(self, **kw):
        with self.lock:
            self.stan.update(kw)

    def odczyt(self):
        with self.lock:
            return dict(self.stan)

    def run(self):
        try:
            self._analizuj()
        except Exception as e:
            self._ustaw(etap="błąd", blad=str(e))

    def _analizuj(self):
        cv2.setNumThreads(2)
        self.glebia.zaladuj()
        cap = cv2.VideoCapture(self.wideo)
        razem = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._ustaw(etap="analiza", razem=razem)
        orb = cv2.ORB_create(2000)
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        pula = ThreadPoolExecutor(3)

        def cechy(klatka):
            szary = cv2.cvtColor(klatka, cv2.COLOR_BGR2GRAY)
            return orb.detectAndCompute(szary, None)

        R, t = np.eye(3), np.zeros(3)              # świat → kamera (świat = pierwsza klatka)
        poprz = None                               # (kp, des, głębia w skali skanu, wymiary)
        skala = None
        R_kl, C_kl = None, None
        pkt, kol = [], []
        n_pkt = 0
        gotowe, zgubione, droga, obrot, kluczowe = 0, 0, 0.0, 0.0, 0
        t0 = time.monotonic()
        czas_hailo = 0.0
        while not self.przerwij:
            seria = []
            for _ in range(self.SERIA):
                ok, k = cap.read()
                if not ok:
                    break
                if k.shape[1] > 960:  # filmy z telefonu (1080p/4K): ruch i chmura nie potrzebują więcej
                    k = cv2.resize(k, (960, int(k.shape[0] * 960 / k.shape[1])), interpolation=cv2.INTER_AREA)
                seria.append(k)
            if not seria:
                break
            zl_cech = [pula.submit(cechy, k) for k in seria]   # procesor: ORB równolegle
            th = time.monotonic()
            glebie = self.glebia.licz_serie(seria)               # Hailo: cała seria naraz
            czas_hailo += time.monotonic() - th
            for klatka, glebia, zc in zip(seria, glebie, zl_cech):
                kp, des = zc.result()
                h, w = klatka.shape[:2]
                K = _macierz_k(w, h)
                if skala is None:
                    skala = SKALA_STARTU / max(float(np.median(glebia)), 1e-6)
                g = glebia * skala
                ruch_ok = False
                if poprz is not None and des is not None and poprz[1] is not None and len(kp) >= 30:
                    dop = bf.match(poprz[1], des)
                    if len(dop) >= 30:
                        gh, gw = poprz[2].shape
                        obj, img = [], []
                        for m in dop:
                            u, v = poprz[0][m.queryIdx].pt
                            z = poprz[2][min(gh - 1, int(v * gh / h)), min(gw - 1, int(u * gw / w))]
                            if 0.2 < z < 8.0:
                                obj.append(((u - K[0, 2]) / K[0, 0] * z, (v - K[1, 2]) / K[1, 1] * z, z))
                                img.append(kp[m.trainIdx].pt)
                        if len(obj) >= 25:
                            obj, img = np.float64(obj), np.float64(img)
                            ok, rv, tv, inl = cv2.solvePnPRansac(obj, img, K, None, iterationsCount=150,
                                                                 reprojectionError=3.0, confidence=0.99,
                                                                 flags=cv2.SOLVEPNP_EPNP)
                            if ok and inl is not None and len(inl) >= 20:
                                ok, rv, tv = cv2.solvePnP(obj[inl[:, 0]], img[inl[:, 0]], K, None, rv, tv, True,
                                                          cv2.SOLVEPNP_ITERATIVE)
                                Rw, _ = cv2.Rodrigues(rv)
                                tw = tv.reshape(3)
                                if ok and _kat(Rw) < 20 and np.linalg.norm(tw) < 0.4:
                                    R, t = Rw @ R, Rw @ t + tw
                                    ruch_ok = True
                        if not ruch_ok:  # zapas: sam obrót z homografii
                            a = np.float32([poprz[0][m.queryIdx].pt for m in dop])
                            b = np.float32([kp[m.trainIdx].pt for m in dop])
                            H, maska = cv2.findHomography(a, b, cv2.RANSAC, 3.0)
                            if H is not None and int(maska.sum()) >= 20:
                                Rh = np.linalg.inv(K) @ H @ K
                                U, _, Vt = np.linalg.svd(Rh)
                                Rh = U @ Vt
                                if np.linalg.det(Rh) < 0:
                                    Rh = -Rh
                                if _kat(Rh) < 20:
                                    R, t = Rh @ R, Rh @ t
                                    ruch_ok = True
                    if not ruch_ok:
                        zgubione += 1
                if poprz is None or ruch_ok:
                    poprz = (kp, des, g)
                C = -R.T @ t
                if R_kl is not None and ruch_ok:
                    obrot_kl = _kat(R @ R_kl.T)
                else:
                    obrot_kl = 999
                if poprz is not None and (R_kl is None or (ruch_ok and (obrot_kl > 2 or np.linalg.norm(C - C_kl) > 0.05))):
                    if R_kl is not None:  # droga i obrót liczone między klatkami kluczowymi (mniej szumu)
                        obrot += obrot_kl
                        droga += float(np.linalg.norm(C - C_kl))
                    P, c = self._punkty(klatka, g, K, R, t)
                    pkt.append(P)
                    kol.append(c)
                    n_pkt += len(P)
                    R_kl, C_kl = R.copy(), C.copy()
                    kluczowe += 1
                    if kluczowe % 15 == 0:
                        pkt, kol = self._woksel(pkt, kol)
                        n_pkt = len(pkt[0])
                gotowe += 1
            dt = time.monotonic() - t0
            kl_s = gotowe / dt if dt > 0 else 0.0
            with self.lock:
                self.podglad = (seria[-1], glebie[-1])
            self._ustaw(gotowe=gotowe, kl_s=kl_s, zostalo=(razem - gotowe) / kl_s if kl_s else None,
                        punkty=n_pkt, kluczowe=kluczowe, zgubione=zgubione, droga=droga, obrot=obrot,
                        hailo_ms=1000 * czas_hailo / max(gotowe, 1), hailo_proc=min(100.0, 100 * czas_hailo / dt))
        cap.release()
        pula.shutdown()
        if self.przerwij:
            self._ustaw(etap="przerwano")
            return
        if not pkt:
            raise RuntimeError("nie powstał żaden punkt (za mało szczegółów w nagraniu?)")
        self._ustaw(etap="zapis")
        pkt, kol = self._woksel(pkt, kol)
        werdykt = self._werdykt(gotowe, zgubione, droga, obrot)
        katalog = zapisz_skan(pkt[0], kol[0], dict(
            opis=werdykt, klatki=gotowe, klatki_kluczowe=kluczowe, obrot_stopnie=round(obrot),
            droga_m=round(droga, 2), zgubione=zgubione, nagranie=os.path.basename(self.wideo)))
        info_p = os.path.join(self.katalog, "info.json")
        if self.wideo.endswith("wideo.avi") and os.path.exists(info_p):  # nagranie z aplikacji: zapamiętaj skan
            info = json.load(open(info_p, encoding="utf-8"))
            info.update(skan=os.path.basename(katalog), werdykt=werdykt)
            json.dump(info, open(info_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        self._ustaw(etap="gotowe", wynik=katalog, werdykt=werdykt, punkty=len(pkt[0]))

    @staticmethod
    def _punkty(klatka, g, K, R, t):
        W, H = 200, 150
        h, w = klatka.shape[:2]
        d = cv2.resize(g, (W, H), interpolation=cv2.INTER_AREA)
        c = cv2.cvtColor(cv2.resize(klatka, (W, H), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
        mx = cv2.dilate(d, np.ones((3, 3), np.uint8))
        mn = cv2.erode(d, np.ones((3, 3), np.uint8))
        ok = (d > 0.2) & (d < 6.0) & (mx / np.maximum(mn, 1e-6) < 1.08)  # bez „latających” punktów na krawędziach
        u, v = np.meshgrid((np.arange(W) + 0.5) * w / W, (np.arange(H) + 0.5) * h / H)
        z = d[ok]
        Pc = np.stack([(u[ok] - K[0, 2]) / K[0, 0] * z, (v[ok] - K[1, 2]) / K[1, 1] * z, z], axis=1)
        Pw = (R.T @ (Pc - t).T).T
        return Pw.astype(np.float32), c[ok]

    @staticmethod
    def _woksel(pkt, kol):
        P, C = np.concatenate(pkt), np.concatenate(kol)
        _, idx = np.unique(np.floor(P / WOKSEL).astype(np.int32), axis=0, return_index=True)
        idx = np.sort(idx)[-MAKS_PUNKTOW:]
        return [P[idx]], [C[idx]]

    @staticmethod
    def _werdykt(klatki, zgubione, droga, obrot):
        procent = 100 * zgubione / max(klatki, 1)
        dr = f"{droga:.1f}".replace(".", ",")
        if droga < 0.3:
            ruch = (f"Kamera głównie obracała się w miejscu (obrót {obrot:.0f}°, przesunięcie ≈{dr} m). "
                    "To najpewniejszy sposób skanowania.")
        else:
            ruch = (f"Kamera przemieszczała się (droga ≈{dr} m w skali skanu, obrót {obrot:.0f}°). "
                    "Analiza liczy ruch kamery z głębią, więc chodzenie jest dozwolone, jeśli jest wolne i płynne.")
        if procent > 20:
            jakosc = f"Śledzenie gubiło się w {procent:.0f}% klatek: ruszaj kamerą wolniej i celuj w miejsca z detalami."
        else:
            jakosc = f"Śledzenie stabilne (zgubione {procent:.0f}% klatek)."
        return ruch + " " + jakosc


# ---------- zapis skanu ----------

def zapisz_skan(pkt, kol, info):
    """Zapisuje skan do skany/RRRR-MM-DD_GGMM_skan/: skan.html (przeglądarka), chmura.ply, info.json."""
    baza = time.strftime("%Y-%m-%d_%H%M") + "_skan"
    katalog, nr = os.path.join(SKANY, baza), 2
    while os.path.exists(katalog):
        katalog, nr = os.path.join(SKANY, f"{baza}_{nr}"), nr + 1
    os.makedirs(katalog)
    nazwa = os.path.basename(katalog)
    # układ przeglądarki (three.js): y w górę, patrzymy wzdłuż -z
    pkt3 = np.stack([pkt[:, 0], -pkt[:, 1], -pkt[:, 2]], axis=1).astype("<f4")
    with open(os.path.join(katalog, "chmura.ply"), "wb") as f:
        f.write((f"ply\nformat binary_little_endian 1.0\ncomment Lazik: skan {nazwa}\nelement vertex {len(pkt3)}\n"
                 "property float x\nproperty float y\nproperty float z\n"
                 "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n").encode())
        rek = np.zeros(len(pkt3), dtype=[("p", "<f4", 3), ("c", "u1", 3)])
        rek["p"], rek["c"] = pkt3, kol
        f.write(rek.tobytes())
    info = dict(info, nazwa=nazwa, czas=time.strftime("%Y-%m-%d %H:%M:%S"), punkty=int(len(pkt3)),
                uwaga="głębia z jednej kamery: skala i odległości orientacyjne")
    json.dump(info, open(os.path.join(katalog, "info.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    dane = dict(info, pos=base64.b64encode(pkt3.tobytes()).decode(), kol=base64.b64encode(np.ascontiguousarray(kol).tobytes()).decode())
    szablon = open(os.path.join(KATALOG, "podglad3d.html"), encoding="utf-8").read()
    open(os.path.join(katalog, "skan.html"), "w", encoding="utf-8").write(
        szablon.replace("/*__DANE__*/null", json.dumps(dane, ensure_ascii=False)))
    three = os.path.join(KATALOG, "three.min.js")
    if os.path.exists(three):
        shutil.copy(three, katalog)
    return katalog
