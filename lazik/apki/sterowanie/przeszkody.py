"""Wykrywanie przeszkód z jednej kamery: kilka niezależnych sposobów, bo każdy z osobna zawodzi.

1. Podłoga z głębi: na podłodze głębia rośnie ku górze kadru tak, jak wynika z geometrii (punkt na podłodze wyżej w kadrze
   = dalej). Na przeszkodzie (ścianie, nodze krzesła, człowieku) głębia przestaje rosnąć. Szukamy od dołu wiersza, gdzie
   „podłoga się kończy”, i z jego wysokości w kadrze liczymy odległość w metrach (wysokość kamery + pole widzenia).
   Działa na głębi względnej (porównujemy tylko stosunki), więc nie przeszkadza to, że scdepthv3 nie podaje metrów.
   Stara metoda (głębia vs typowa w kadrze) mówiła „wolne”, gdy przeszkoda zasłaniała cały kadr; ta mówi wtedy „tuż przed”.
2. Obiekty YOLO stojące na podłodze: dolna krawędź ramki = punkt styku z podłogą = odległość z tej samej geometrii.
3. Czas do zderzenia z przepływu optycznego: gdy łazik jedzie, zbliżająca się przeszkoda „puchnie” w kadrze.
   Tempo puchnięcia daje czas do zderzenia (bez znajomości odległości); działa też na gładkich ścianach z odrobiną faktury.
4. Ruch obrazu (do wykrycia, że łazik utknął: silniki pracują, a obraz stoi).
"""

import math

import cv2
import numpy as np

SEKTORY = 5
DALEKO = 9.99  # m: „nie widać końca podłogi”


def ogniskowa(konf, szer=640):
    return 0.5 * szer / math.tan(math.radians(konf.get("kamera_fov", 48)) / 2)


def odleglosc_z_wiersza(yn, konf):
    """Odległość [m] do punktu na podłodze widocznego w wierszu yn (0 = góra kadru, 1 = dół)."""
    hor = konf.get("horyzont", 0.5)
    pod = (yn - hor) * 480  # piksele poniżej horyzontu w kadrze 640×480 (kamera 4:3)
    if pod <= 4:
        return DALEKO
    return min(DALEKO, konf.get("wysokosc_kamery_cm", 10) / 100 * ogniskowa(konf) / pod)


def profil_sektorow(mapa, konf):
    """Dla 5 pionowych pasów: (odległość [m] do miejsca, gdzie kończy się podłoga, wiersz tego miejsca 0..1)."""
    h, w = mapa.shape
    hor = int(konf.get("horyzont", 0.5) * h)
    prog = konf.get("prog_przeszkody", 0.45) * 0.6     # jaka część „podłogowego” wzrostu głębi jeszcze jest podłogą
    krok = max(2, h // 32)
    wynik = []
    for i in range(SEKTORY):
        pas = mapa[:, int(i * w / SEKTORY):int((i + 1) * w / SEKTORY)]
        p = np.median(pas, axis=1)
        p = np.convolve(np.pad(p, krok, mode="edge"), np.ones(krok) / krok, mode="same")[krok:-krok]
        p = np.maximum(p, 1e-6)
        podstawa, seria = None, 0
        y = h - 1 - krok // 2
        while y - krok - hor > krok:
            zmierzony = math.log(p[y - krok] / p[y])                       # wzrost głębi o krok wierszy w górę
            oczekiwany = math.log((y - hor) / (y - krok - hor))             # tyle rośnie na płaskiej podłodze
            if zmierzony < prog * oczekiwany:
                seria += 1
                if seria == 1:
                    podstawa = y
                if seria >= 3:                                              # 3 kroki z rzędu „nie podłoga” = przeszkoda
                    break
            else:
                seria, podstawa = 0, None
            y -= krok
        if seria >= 3 and podstawa is not None:
            yn = min(1.0, (podstawa + krok) / h)
            wynik.append((round(odleglosc_z_wiersza(yn, konf), 2), round(yn, 3)))
        else:
            wynik.append((DALEKO, None))
    return wynik


def obiekty_na_podlodze(obiekty, konf):
    """Odległość [m] w każdym sektorze od obiektów YOLO (dolna krawędź ramki = styk z podłogą)."""
    odl = [DALEKO] * SEKTORY
    for o in obiekty:
        x0, y0, x1, y1 = o["ramka"]
        if y1 < konf.get("horyzont", 0.5) + 0.03:   # wisi w powietrzu (np. lampa, obraz na ścianie)
            continue
        d = odleglosc_z_wiersza(min(1.0, y1), konf)
        if (x1 - x0) * (y1 - y0) > 0.45:            # zasłania prawie cały kadr = tuż przed kamerą
            d = min(d, 0.15)
        for s in range(int(x0 * SEKTORY), min(SEKTORY, int(x1 * SEKTORY - 1e-6) + 1)):
            odl[s] = min(odl[s], d)
    return odl


class Przeplyw:
    """Przepływ optyczny na małym obrazie: czas do zderzenia w sektorach i ogólny ruch obrazu."""

    def __init__(self):
        self.pop, self.t_pop = None, 0.0
        self.ttc = [None] * SEKTORY   # s, None = nic się nie zbliża
        self.ruch = 0.0               # mediana przesunięcia [px małego obrazu na sekundę]

    def aktualizuj(self, klatka, t, hor=0.5):
        szary = cv2.cvtColor(cv2.resize(klatka, (160, 120), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        pop, t_pop = self.pop, self.t_pop
        self.pop, self.t_pop = szary, t
        dt = t - t_pop
        if pop is None or not 0.01 < dt < 0.5:
            return
        f = cv2.calcOpticalFlowFarneback(pop, szary, None, 0.5, 2, 9, 2, 5, 1.1, 0)
        u, v = f[..., 0], f[..., 1]
        self.ruch = float(np.median(np.hypot(u, v))) / dt
        u = u - np.median(u)   # obrót łazika i kołysanie przesuwają cały obraz: to nie zbliżanie
        v = v - np.median(v)
        h, w = szary.shape
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        dx, dy = xs - w / 2, ys - hor * h
        r2 = dx * dx + dy * dy
        maska = (r2 > 64) & (ys > h * 0.15)
        rozbieg = np.where(maska, (u * dx + v * dy) / np.maximum(r2, 1), 0)   # „puchnięcie” na klatkę
        for i in range(SEKTORY):
            sl = slice(int(i * w / SEKTORY), int((i + 1) * w / SEKTORY))
            m = maska[:, sl]
            if m.sum() < 50:
                self.ttc[i] = None
                continue
            e = float(np.median(rozbieg[:, sl][m])) / dt   # 1/s
            self.ttc[i] = round(1 / e, 2) if e > 0.08 else None
