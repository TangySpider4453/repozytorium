"""Tryby jazdy łazika (pętla 10 razy na sekundę). Każdy tryb patrzy na percepcję (obiekty + sektory głębi),
decyduje o ruchu i opisuje słowami, co robi (pole `opis`, widoczne na stronie).

stop · reczny · przetrwaj (oceń zagrożenie i uciekaj) · zwiedzaj (jeździ i nagrywa do skanu 3D) ·
fotograf (szuka różnych ciekawych rzeczy i je fotografuje) · sledz (jedzie za wybranym obiektem albo klasą)

Bez enkoderów ruch jest „na czas” (bez pomiaru przejechanej drogi), więc tryby działają odruchowo:
patrzą, skręcają, jadą krótko i znów patrzą.
"""

import json
import os
import random
import sys
import threading
import time

import cv2

KATALOG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(KATALOG), "wizja"))
import przestrzen as P  # noqa: E402
from wizja import ZDJECIA, nazwa, slug  # noqa: E402

TRYBY = {
    "stop": "Stop",
    "reczny": "Ręczny",
    "przetrwaj": "Przetrwaj",
    "zwiedzaj": "Zwiedzaj i skanuj",
    "fotograf": "Fotograf",
    "sledz": "Śledź",
}
ZAGROZENIA = {0: "osoba", 1: "rower", 2: "samochód", 3: "motocykl", 5: "autobus", 7: "ciężarówka",
              15: "kot", 16: "pies", 17: "koń", 19: "krowa", 21: "niedźwiedź"}
DO_SLEDZENIA = {0: "człowiek", 1: "rower", 2: "auto", 3: "motocykl", 15: "kot", 16: "pies", 32: "piłka",
                24: "plecak", 39: "butelka", 41: "kubek", 56: "krzesło", 67: "telefon"}
NUDNE = {56, 57, 59, 60, 62, 72, 73, 74}  # krzesło, kanapa, łóżko, stół, telewizor, lodówka… (fotograf ich unika)


def gdzie(cx):
    return "z lewej" if cx < 0.4 else "z prawej" if cx > 0.6 else "na wprost"


class Sterownik(threading.Thread):
    def __init__(self, naped, percepcja, konf):
        super().__init__(daemon=True)
        self.naped, self.per, self.konf = naped, percepcja, konf
        self.tryb, self.opis = "stop", "Stoję. Wybierz tryb."
        self.lock = threading.Lock()
        self._reczny = (0.0, 0.0, 0.0)          # (prędkość, skręt, ważne do)
        self.cel_id, self.cel_klasa = None, 0     # śledzenie: konkretny obiekt albo klasa
        self._cel_ostatnio = None                 # (czas, cx, klasa) do odnalezienia zgubionego celu
        self._akcja = None                        # (nazwa, do kiedy, prędkość, skręt): krótki manewr
        self._hist = {}                           # przetrwaj: id → [(czas, pole, cx)]
        self._t_rozgladania = 0.0
        self._t_losowego = 0.0
        self.zdjecia_klas = {}                    # fotograf: klasa → czas ostatniego zdjęcia
        self.ile_zdjec = {}                       # fotograf: klasa → ile zdjęć (różnorodność)
        self.nagrywanie = P.Nagrywanie()
        self.ostatnia_wyprawa = None
        self.liczba_zdjec = 0

    # --- sterowanie z zewnątrz ---
    def ustaw_tryb(self, tryb):
        if tryb not in TRYBY:
            return
        with self.lock:
            if self.tryb == "zwiedzaj" and tryb != "zwiedzaj":
                self._koniec_nagrywania()
            self.tryb = tryb
            self._akcja = None
            self._hist.clear()
            self.naped.stop()
            self.per.potrzebna_glebia = tryb in ("przetrwaj", "zwiedzaj", "fotograf", "sledz")
            if tryb == "zwiedzaj":
                if self.per.kamera is not None:
                    self.per.kamera.odbiorcy.append(self.nagrywanie.dodaj)
                self.nagrywanie.zacznij()
            self.opis = {"stop": "Stoję.", "reczny": "Czekam na polecenia (przyciski / klawiatura)."}.get(tryb, "Zaczynam…")

    def _koniec_nagrywania(self):
        kat = self.nagrywanie.zakoncz()
        if self.per.kamera is not None and self.nagrywanie.dodaj in self.per.kamera.odbiorcy:
            self.per.kamera.odbiorcy.remove(self.nagrywanie.dodaj)
        if kat and self.nagrywanie.klatki > 30:
            self.ostatnia_wyprawa = kat

    def reczny(self, v, s):
        self._reczny = (float(v), float(s), time.monotonic() + 0.5)

    def wybierz_cel(self, id_=None, klasa=None):
        self.cel_id = id_
        if klasa is not None:
            self.cel_klasa = int(klasa)
        self._cel_ostatnio = None

    # --- pętla ---
    def run(self):
        while True:
            t0 = time.monotonic()
            try:
                with self.lock:
                    self._krok()
            except Exception as e:
                self.naped.stop()
                self.opis = f"Błąd trybu: {e}"
            time.sleep(max(0.0, 0.1 - (time.monotonic() - t0)))

    def _krok(self):
        t = self.tryb
        if t == "stop":
            return
        self.per.potrzebna()
        if self.nagrywanie.aktywne and self.per.kamera is not None and self.nagrywanie.dodaj not in self.per.kamera.odbiorcy:
            self.per.kamera.odbiorcy.append(self.nagrywanie.dodaj)  # kamera mogła ruszyć dopiero teraz
        if t == "reczny":
            v, s, do = self._reczny
            if time.monotonic() < do:
                self.naped.jedz(v, s)
                self.opis = "Jadę ręcznie." if (v or s) else "Czekam na polecenia."
            return
        klatka, nr, obiekty, sektory = self.per.najnowsze()
        if klatka is None:
            self.opis = "Czekam na obraz z kamery…"
            return
        if self._akcja and time.monotonic() < self._akcja[1]:  # trwa krótki manewr
            self.naped.jedz(self._akcja[2], self._akcja[3])
            return
        self._akcja = None
        getattr(self, "_" + t)(klatka, obiekty, sektory)

    def _manewr(self, nazwa_, sekundy, v, s):
        self._akcja = (nazwa_, time.monotonic() + sekundy, v, s)
        self.naped.jedz(v, s)

    # --- unikanie przeszkód ---
    def _przeszkoda(self, obiekty, sektory):
        """(czy na wprost jest przeszkoda, w którą stronę jest więcej miejsca: -1 lewo / +1 prawo)"""
        prog = self.konf["prog_przeszkody"]
        blisko = False
        if sektory:
            blisko = min(sektory[1:4]) < prog
        for o in obiekty:  # duży obiekt na środku, na dole kadru = tuż przed łazikiem
            x0, y0, x1, y1 = o["ramka"]
            if (x1 - x0) * (y1 - y0) > 0.35 and 0.25 < (x0 + x1) / 2 < 0.75 and y1 > 0.8:
                blisko = True
        strona = 1
        if sektory:
            strona = -1 if sum(sektory[:2]) > sum(sektory[3:]) else 1
        return blisko, strona

    def _wedruj(self, obiekty, sektory, predkosc=0.55):
        blisko, strona = self._przeszkoda(obiekty, sektory)
        if blisko:
            kier = "w lewo" if strona < 0 else "w prawo"
            self.opis = f"Przeszkoda przed sobą: skręcam {kier}."
            self._manewr("omijam", 0.6, 0.0, 0.8 * strona)
            return
        if time.monotonic() - self._t_losowego > random.uniform(12, 20):  # czasem zmień kierunek, żeby zwiedzać
            self._t_losowego = time.monotonic()
            self.opis = "Zmieniam kierunek, żeby zobaczyć coś nowego."
            self._manewr("zwrot", random.uniform(0.5, 1.2), 0.0, random.choice((-0.8, 0.8)))
            return
        lekko = 0.0
        if sektory:
            lekko = max(-0.25, min(0.25, (sum(sektory[3:]) - sum(sektory[:2])) * 0.15))
        self.naped.jedz(predkosc, lekko)

    # --- przetrwaj ---
    def _przetrwaj(self, klatka, obiekty, sektory):
        teraz = time.monotonic()
        zagr = None
        for o in obiekty:
            if o["klasa"] not in ZAGROZENIA:
                continue
            x0, y0, x1, y1 = o["ramka"]
            pole, cx = (x1 - x0) * (y1 - y0), (x0 + x1) / 2
            h = self._hist.setdefault(o["id"], [])
            h.append((teraz, pole, cx))
            while h and teraz - h[0][0] > 1.5:
                h.pop(0)
            rosnie = len(h) > 3 and h[-1][1] > h[0][1] * 1.3     # w 1,5 s urosło o 30% = zbliża się
            groznosc = pole * (3 if rosnie else 1) * (2 if o["klasa"] in (2, 5, 7, 16, 21) else 1)
            if (rosnie or pole > 0.2) and (zagr is None or groznosc > zagr[0]):
                zagr = (groznosc, o, cx, rosnie)
        if zagr:
            _, o, cx, rosnie = zagr
            kier = 1 if cx < 0.5 else -1  # uciekaj w stronę przeciwną do zagrożenia
            co = ZAGROZENIA[o["klasa"]]
            self.opis = (f"Zagrożenie: {co} {'zbliża się' if rosnie else 'blisko'} {gdzie(cx)} → uciekam "
                         f"{'w prawo' if kier > 0 else 'w lewo'}.")
            blisko, _ = self._przeszkoda(obiekty, sektory)
            self._manewr("ucieczka", 1.0, 0.0 if blisko else 0.4, 0.9 * kier)
            return
        if teraz - self._t_rozgladania > 8:  # co jakiś czas rozejrzyj się, bo kamera widzi tylko przed siebie
            self._t_rozgladania = teraz
            self.opis = "Czuwam: obracam się, żeby rozejrzeć się dookoła."
            self._manewr("rozgladanie", 0.7, 0.0, random.choice((-0.7, 0.7)))
            return
        self.naped.stop()
        widac = ", ".join(sorted({o["nazwa"] for o in obiekty})) or "nic"
        self.opis = f"Czuwam, nie widzę zagrożenia (w kadrze: {widac})."

    # --- zwiedzaj ---
    def _zwiedzaj(self, klatka, obiekty, sektory):
        self._wedruj(obiekty, sektory)
        if self._akcja is None:
            self.opis = f"Zwiedzam i nagrywam do skanu 3D ({self.nagrywanie.klatki} klatek)."

    # --- fotograf ---
    def _fotograf(self, klatka, obiekty, sektory):
        teraz = time.monotonic()
        kandydaci = [o for o in obiekty if o["pew"] > 0.55 and o["klasa"] not in NUDNE
                     and teraz - self.zdjecia_klas.get(o["klasa"], -1e9) > 180]
        if not kandydaci:
            self._wedruj(obiekty, sektory, 0.45)
            if self._akcja is None:
                self.opis = f"Szukam czegoś ciekawego do zdjęcia (zrobione: {self.liczba_zdjec})."
            return
        # najrzadziej fotografowana klasa, a wśród nich najbardziej pewna
        o = min(kandydaci, key=lambda x: (self.ile_zdjec.get(x["klasa"], 0), -x["pew"]))
        x0, y0, x1, y1 = o["ramka"]
        cx, wys = (x0 + x1) / 2, y1 - y0
        blisko, _ = self._przeszkoda([x for x in obiekty if x is not o], sektory)
        if wys < 0.45 and not blisko:
            self.opis = f"Podjeżdżam do: {o['nazwa']} ({gdzie(cx)})."
            self.naped.jedz(0.45, max(-0.6, min(0.6, (cx - 0.5) * 1.6)))
            return
        self.naped.stop()
        self._zdjecie(klatka, obiekty, o)
        self.zdjecia_klas[o["klasa"]] = teraz
        self.ile_zdjec[o["klasa"]] = self.ile_zdjec.get(o["klasa"], 0) + 1
        self.opis = f"Zrobiłem zdjęcie: {o['nazwa']}. Szukam czegoś innego."
        self._manewr("odwrot", 1.2, 0.0, random.choice((-0.8, 0.8)))

    def _zdjecie(self, klatka, obiekty, glowny):
        """Zapis jak w „Łazik: wizja” (zdjecia/*.jpg + .json), więc zdjęcia widać też w jej galerii."""
        os.makedirs(ZDJECIA, exist_ok=True)
        baza = time.strftime("%Y-%m-%d_%H%M%S") + "_lazik_" + slug(glowny["nazwa"])
        cv2.imwrite(os.path.join(ZDJECIA, baza + ".jpg"), klatka, [cv2.IMWRITE_JPEG_QUALITY, 92])
        h, w = klatka.shape[:2]
        json.dump(dict(czas=time.strftime("%Y-%m-%d %H:%M:%S"), obraz=baza + ".jpg", szer=w, wys=h, zrodlo="łazik: fotograf",
                       obiekty=[dict(id=x["id"], klasa=x["klasa"], nazwa=nazwa(x["klasa"]), pewnosc=round(x["pew"], 3),
                                     ramka=[round(v, 4) for v in x["ramka"]]) for x in obiekty]),
                  open(os.path.join(ZDJECIA, baza + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        self.liczba_zdjec += 1

    # --- śledź ---
    def _sledz(self, klatka, obiekty, sektory):
        teraz = time.monotonic()
        cel = None
        if self.cel_id is not None:
            cel = next((o for o in obiekty if o["id"] == self.cel_id), None)
            if cel is None and self._cel_ostatnio and teraz - self._cel_ostatnio[0] < 2.0:
                # zgubiony numer (np. chwilowo zasłonięty): ta sama klasa najbliżej ostatniego miejsca
                _, cx_o, kl = self._cel_ostatnio
                pas = [o for o in obiekty if o["klasa"] == kl]
                if pas:
                    cel = min(pas, key=lambda o: abs((o["ramka"][0] + o["ramka"][2]) / 2 - cx_o))
                    self.cel_id = cel["id"]
        else:
            pas = [o for o in obiekty if o["klasa"] == self.cel_klasa]
            if pas:
                cel = max(pas, key=lambda o: (o["ramka"][3] - o["ramka"][1]))
        if cel is None:
            if self._cel_ostatnio and teraz - self._cel_ostatnio[0] < 4:
                strona = 1 if self._cel_ostatnio[1] > 0.5 else -1
                self.opis = f"Zgubiłem cel: szukam {'w prawo' if strona > 0 else 'w lewo'}."
                self.naped.jedz(0.0, 0.55 * strona)
            else:
                self.naped.stop()
                kogo = f"#{self.cel_id}" if self.cel_id is not None else DO_SLEDZENIA.get(self.cel_klasa, nazwa(self.cel_klasa))
                self.opis = f"Nie widzę celu ({kogo}). Dotknij obiektu na podglądzie albo wybierz klasę."
            return
        x0, y0, x1, y1 = cel["ramka"]
        cx, wys = (x0 + x1) / 2, y1 - y0
        self._cel_ostatnio = (teraz, cx, cel["klasa"])
        dystans = self.konf["sledzenie_wysokosc"]  # docelowa wysokość ramki (ułamek kadru) = odległość
        skret = max(-0.7, min(0.7, (cx - 0.5) * 1.8))
        v = max(-0.35, min(0.75, (dystans - wys) * 2.5))
        blisko, _ = self._przeszkoda([o for o in obiekty if o is not cel], sektory)
        if v > 0 and blisko:
            v = 0.0
            self.opis = f"Śledzę #{cel['id']} {cel['nazwa']}, ale przede mną przeszkoda: tylko się obracam."
        elif abs(v) < 0.08:
            v = 0.0
            self.opis = f"Śledzę #{cel['id']} {cel['nazwa']}: jestem w dobrej odległości."
        else:
            self.opis = f"Śledzę #{cel['id']} {cel['nazwa']} ({gdzie(cx)}): {'jadę za nim' if v > 0 else 'cofam się, za blisko'}."
        self.naped.jedz(v, skret)
