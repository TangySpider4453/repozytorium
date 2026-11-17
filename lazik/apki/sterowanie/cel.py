"""Śledzenie JEDNEGO wybranego obiektu (tryb Śledź).

Samo YOLO + numerowanie ramek gubi cel: gdy wykrycie mignie albo dwie osoby się miną, numer przeskakuje na kogoś
innego. Tu cel jest „zablokowany”:
- zapamiętujemy jego wygląd (histogram kolorów w ramce, wolno douczany) i ruch (przewidywane miejsce),
- równolegle działa szybki tracker KCF z OpenCV (~10–20 ms na 320×240), który prowadzi cel, gdy YOLO go nie widzi
  (zasłonięty, rozmazany, pod złym kątem) i co chwilę jest poprawiany ramką z YOLO, żeby nie odpływał,
- inną ramkę tej samej klasy przyjmujemy tylko, gdy pasuje miejscem ORAZ wyglądem; po dłuższej utracie tylko wyglądem
  (ponowne rozpoznanie), nigdy „pierwszą lepszą osobę w kadrze”.
"""

import time

import cv2
import numpy as np

SKALA = (320, 240)          # tracker KCF liczy na zmniejszonej klatce
KCF_MAKS_S = 2.5            # tyle sekund sam KCF może prowadzić cel bez potwierdzenia z YOLO
PONOWNE_MAKS_S = 10.0       # tyle sekund po utracie szukamy celu po wyglądzie


def iou(a, b):
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    p = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - p
    return p / u if u > 0 else 0.0


def histogram(klatka, ramka):
    """Histogram barwy i nasycenia ze środka ramki (brzegi to zwykle tło)."""
    h, w = klatka.shape[:2]
    x0, y0, x1, y1 = ramka
    dx, dy = (x1 - x0) * 0.2, (y1 - y0) * 0.15
    a, b = int((x0 + dx) * w), int((y0 + dy) * h)
    c, d = max(a + 2, int((x1 - dx) * w)), max(b + 2, int((y1 - dy) * h))
    wyc = klatka[max(0, b):min(h, d), max(0, a):min(w, c)]
    if wyc.size == 0:
        return None
    hsv = cv2.cvtColor(wyc, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [18, 8], [0, 180, 0, 256])
    return cv2.normalize(hist, hist).flatten()


def podobienstwo(h1, h2):
    """0 = zupełnie inny wygląd, 1 = taki sam."""
    if h1 is None or h2 is None:
        return 0.0
    return float(1.0 - cv2.compareHist(h1, h2, cv2.HISTCMP_BHATTACHARYYA))


class Cel:
    def __init__(self):
        self.aktywny = False
        self.ramka = None           # (x0, y0, x1, y1) 0..1
        self.id = None              # numer ramki YOLO, która teraz jest celem (do zaznaczenia na stronie)
        self.klasa = None
        self.zrodlo = None          # "yolo" / "tracker" / None (zgubiony)
        self.pewnosc = 0.0          # podobieństwo wyglądu ostatniego potwierdzenia
        self._hist = None
        self._kcf = None
        self._t_yolo = 0.0          # ostatnie potwierdzenie przez YOLO
        self._t_kcf_init = 0.0
        self._predkosc = (0.0, 0.0)

    def zacznij(self, klatka, obiekt, teraz=None):
        teraz = time.monotonic() if teraz is None else teraz
        self.aktywny, self.klasa, self.id = True, obiekt["klasa"], obiekt["id"]
        self.ramka = tuple(obiekt["ramka"])
        self._hist = histogram(klatka, self.ramka)
        self._t_yolo, self.zrodlo, self.pewnosc, self._predkosc = teraz, "yolo", 1.0, (0.0, 0.0)
        self._kcf_init(klatka, teraz)

    def porzuc(self):
        self.__init__()

    def _kcf_init(self, klatka, teraz):
        try:
            male = cv2.resize(klatka, SKALA, interpolation=cv2.INTER_AREA)
            x0, y0, x1, y1 = self.ramka
            r = (int(x0 * SKALA[0]), int(y0 * SKALA[1]), max(4, int((x1 - x0) * SKALA[0])), max(4, int((y1 - y0) * SKALA[1])))
            self._kcf = cv2.TrackerKCF_create()
            self._kcf.init(male, r)
            self._t_kcf_init = teraz
        except Exception:
            self._kcf = None

    def _kcf_krok(self, klatka):
        if self._kcf is None:
            return None
        try:
            ok, (x, y, w, h) = self._kcf.update(cv2.resize(klatka, SKALA, interpolation=cv2.INTER_AREA))
        except Exception:
            return None
        if not ok or w <= 0 or h <= 0:
            return None
        return (x / SKALA[0], y / SKALA[1], (x + w) / SKALA[0], (y + h) / SKALA[1])

    def aktualizuj(self, klatka, obiekty, teraz=None):
        """Zwraca ramkę celu w tej klatce albo None (zgubiony)."""
        if not self.aktywny:
            return None
        teraz = time.monotonic() if teraz is None else teraz
        kcf = self._kcf_krok(klatka)
        od_yolo = teraz - self._t_yolo
        # przewidywane miejsce: ostatnia ramka przesunięta o średni ruch
        x0, y0, x1, y1 = self.ramka
        vx, vy = self._predkosc
        dt = min(od_yolo, 0.5)
        przew = (x0 + vx * dt, y0 + vy * dt, x1 + vx * dt, y1 + vy * dt)
        szer = max(0.05, x1 - x0)

        najl, najl_wynik = None, 0.0
        for o in obiekty:
            if o["klasa"] != self.klasa:
                continue
            r = o["ramka"]
            wyg = podobienstwo(self._hist, histogram(klatka, r))
            miejsce = max(iou(r, przew), iou(r, kcf) if kcf else 0.0)
            odl = abs((r[0] + r[2]) / 2 - (przew[0] + przew[2]) / 2) / szer
            ten_sam_numer = o["id"] == self.id
            if od_yolo < 1.0:
                # świeżo widziany: musi pasować miejscem (albo to ten sam numer) i nie może wyglądać zupełnie inaczej
                pasuje = (ten_sam_numer and wyg > 0.25) or (miejsce > 0.2 and wyg > 0.35) or (odl < 0.8 and wyg > 0.5)
            elif od_yolo < PONOWNE_MAKS_S:
                # dłużej niewidziany: wracamy tylko do kogoś, kto WYGLĄDA jak cel
                pasuje = wyg > 0.55 or (miejsce > 0.3 and wyg > 0.4)
            else:
                pasuje = False
            if not pasuje:
                continue
            wynik = 0.5 * wyg + 0.3 * miejsce + 0.2 * max(0.0, 1 - odl / 2) + (0.15 if ten_sam_numer else 0.0)
            if wynik > najl_wynik:
                najl, najl_wynik = o, wynik

        if najl is not None:
            r = tuple(najl["ramka"])
            if od_yolo > 0:
                a = 0.5   # wygładzona prędkość ramki (na przewidywanie po chwilowej utracie)
                self._predkosc = (a * ((r[0] - x0) / max(od_yolo, 0.05)) + (1 - a) * vx,
                                  a * ((r[1] - y0) / max(od_yolo, 0.05)) + (1 - a) * vy)
            self.ramka, self.id, self.zrodlo, self._t_yolo = r, najl["id"], "yolo", teraz
            h = histogram(klatka, r)
            self.pewnosc = podobienstwo(self._hist, h)
            if h is not None and self.pewnosc > 0.4:   # wolne douczanie wyglądu (światło, obrót osoby)
                self._hist = 0.9 * self._hist + 0.1 * h
            if kcf is None or iou(kcf, r) < 0.5 or teraz - self._t_kcf_init > 1.0:
                self._kcf_init(klatka, teraz)       # poprawka trackera ramką z YOLO
            return self.ramka
        if kcf is not None and od_yolo < KCF_MAKS_S:
            self.ramka, self.zrodlo = kcf, "tracker"     # YOLO chwilowo nie widzi: prowadzi KCF
            return self.ramka
        self.zrodlo = None
        if od_yolo > PONOWNE_MAKS_S:
            self.aktywny = False
        return None
