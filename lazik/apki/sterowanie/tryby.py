"""Tryby jazdy łazika (pętla 10 razy na sekundę). Każdy tryb patrzy na percepcję (obiekty + sektory głębi),
decyduje o ruchu i opisuje słowami, co robi (pole `opis`, widoczne na stronie).

stop · reczny · przetrwaj (oceń zagrożenie i uciekaj) · zwiedzaj (jeździ i nagrywa do skanu 3D) ·
fotograf (szuka różnych ciekawych rzeczy i je fotografuje) · sledz (jedzie za wybranym obiektem albo klasą)

Bez enkoderów nie wiemy, ile łazik przejechał, ale żyroskop mówi, o ile się obrócił: manewry omijania to
„cofnij się trochę i obróć o zadany kąt” (bez żyroskopu: obrót na czas). Przeszkody ocenia `_ocen` z kilku źródeł
naraz (podłoga z głębi, obiekty YOLO, czas do zderzenia z przepływu, uderzenie z akcelerometru, „utknąłem”),
a prędkość maleje, im bliżej przeszkody.
"""

import json
import math
import os
import random
import sys
import threading
import time

import cv2

import przeszkody as Z
from cel import Cel

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
        self._reczny = (0.0, 0.0, 0.0, None, False)  # (prędkość, skręt, ważne do, maks. moc / None, liniowo)
        self.cel_id, self.cel_klasa = None, 0     # śledzenie: konkretny obiekt albo klasa
        self._cel_ostatnio = None                 # (czas, cx, klasa) do odnalezienia zgubionego celu
        self.cel = Cel()                          # zablokowany cel (wygląd + tracker KCF), patrz cel.py
        self._zadanie_celu = None                 # numer obiektu dotkniętego na stronie, do zablokowania w trybie
        self._plan = []                           # kroki manewru: {nazwa, typ: czas|obrot, …}
        self._jade_od = None                      # od kiedy tryb każe jechać do przodu (dla „utknąłem” i czasu do zderzenia)
        self._blokady = []                        # czasy ostatnich omijań (kilka naraz = kąt, zawracamy)
        self._strona_omijania, self._t_omijania = 1, -1e9
        self.ocena = None                         # ostatnia ocena przeszkód (na stronę)
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
            self._plan = []
            self._jade_od = None
            self._hist.clear()
            self._t_losowego = self._t_rozgladania = time.monotonic()
            self.naped.stop()
            self.per.potrzebna_glebia = tryb in ("przetrwaj", "zwiedzaj", "fotograf", "sledz")
            # w Śledź szybki model: więcej klatek na sekundę = cel ginie rzadziej (Hailo nie dobija do 100%)
            self.per.model_wymuszony = 0 if tryb == "sledz" and self.konf.get("sledz_szybki_model", True) else None
            if tryb == "sledz" and self.cel_id is not None:
                self._zadanie_celu = self.cel_id
            if tryb != "sledz":
                self.cel.porzuc()
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

    def reczny(self, v, s, maks=None, liniowo=False):
        self._reczny = (float(v), float(s), time.monotonic() + 0.5, maks, bool(liniowo))

    def wybierz_cel(self, id_=None, klasa=None):
        """id_ = konkretny obiekt (dotknięty na podglądzie), inaczej rodzaj `klasa` (blokujemy najbliższy tego rodzaju)."""
        with self.lock:
            self.cel_id = id_
            if klasa is not None:
                self.cel_klasa = int(klasa)
            self._cel_ostatnio = None
            self.cel.porzuc()
            self._zadanie_celu = id_

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
            v, s, do, maks, liniowo = self._reczny
            if time.monotonic() < do:
                self.naped.jedz(v, s, maks, liniowo)
                self.opis = "Jadę ręcznie." if (v or s) else "Czekam na polecenia."
            return
        klatka, nr, obiekty, sektory = self.per.najnowsze()
        if klatka is None:
            self.opis = "Czekam na obraz z kamery…"
            return
        if self._plan and self._krok_planu():  # trwa manewr (cofanie, obrót o kąt)
            return
        getattr(self, "_" + t)(klatka, obiekty, sektory)

    @property
    def _akcja(self):
        return self._plan[0] if self._plan else None

    def _jedz(self, v, s):
        """Jazda z trybów: zapamiętuje, od kiedy jedziemy do przodu (do wykrywania utknięcia)."""
        if v > 0.15:
            self._jade_od = self._jade_od or time.monotonic()
        else:
            self._jade_od = None
        self.naped.jedz(v, s)

    def _obr(self):
        """Moc obrotu w miejscu z ustawień (wolniej = łagodniej, kamera mniej rozmazuje obraz)."""
        return self.konf.get("predkosc_obrotu", 0.5)

    def _stoj(self):
        self._jade_od = None
        self.naped.stop()

    def _manewr(self, nazwa_, sekundy, v, s):
        self._plan = [dict(nazwa=nazwa_, typ="czas", sek=sekundy, v=v, s=s)]
        self._krok_planu()

    def _obrot(self, nazwa_, kat):
        return dict(nazwa=nazwa_, typ="obrot", kat=kat)

    def _krok_planu(self):
        """Wykonuje bieżący krok planu; False, gdy plan się skończył."""
        teraz, k, imu = time.monotonic(), self._plan[0], self.naped.imu
        self._jade_od = None
        if "start" not in k:
            k["start"] = teraz
            if k["typ"] == "obrot":
                if imu is not None and imu.ok:
                    k["cel"], k["do"] = imu.kurs_ciagly + k["kat"], teraz + 2.0 + abs(k["kat"]) / (40 * self._obr())
                else:  # bez żyroskopu: na czas (~110°/s przy pełnej mocy obrotu; zależy od podłoża)
                    k["do"] = teraz + abs(k["kat"]) / (110 * self._obr())
            else:
                k["do"] = teraz + k["sek"]
        if k["typ"] == "obrot" and "cel" in k and imu is not None and imu.ok:
            zostalo = k["cel"] - imu.kurs_ciagly
            if abs(zostalo) > 6 and teraz < k["do"]:
                moc = self._obr() * (0.75 if abs(zostalo) < 25 else 1.0)   # przy końcu obrotu jeszcze wolniej
                self.naped.jedz(0.0, math.copysign(moc, zostalo))
                return True
        elif teraz < k["do"]:
            if k["typ"] == "obrot":
                self.naped.jedz(0.0, math.copysign(self._obr(), k["kat"]))
            else:
                self.naped.jedz(k["v"], k["s"])
            return True
        self._plan.pop(0)
        if self._plan:
            return self._krok_planu()
        self.naped.stop()
        return False

    # --- unikanie przeszkód ---
    def _ocen(self, obiekty, sektory):
        """Odległości w 5 pasach (z głębi i obiektów YOLO) oraz powód, żeby natychmiast omijać (albo None)."""
        k, teraz, imu = self.konf, time.monotonic(), self.naped.imu
        odl = list(sektory) if sektory else [Z.DALEKO] * Z.SEKTORY
        odl = [min(a, b) for a, b in zip(odl, Z.obiekty_na_podlodze(obiekty, k))]
        przod, lewo, prawo = min(odl[1:4]), min(odl[:2]), min(odl[3:])
        stop = k["odleglosc_stop_cm"] / 100
        jade = self._jade_od is not None and teraz - self._jade_od > 0.5
        powod, mocno = None, False
        if przod < stop:
            pod = self.per.podstawy or []
            na_dole = any(y is not None and y >= 0.97 for y in pod[1:4])
            powod = f"przeszkoda {'tuż' if na_dole else '~' + format(przod * 100, '.0f') + ' cm'} przed sobą"
        ttc = [t for t in (self.per.ttc or [None] * 5)[1:4] if t]
        if not powod and jade and k["czas_do_zderzenia_s"] > 0 and ttc and min(ttc) < k["czas_do_zderzenia_s"]:
            powod = f"coś szybko rośnie w kadrze (zderzenie za ~{min(ttc):.1f} s)"
        if imu is not None and imu.ok:
            uderzenie = imu.szczyt()
            if jade and uderzenie > k["prog_uderzenia_g"]:
                powod, mocno = f"uderzenie ({uderzenie:.1f} g z akcelerometru)", True
        if (not powod and jade and teraz - self._jade_od > 2.0 and self.per.ruch_obrazu < k["prog_utkniecia"]
                and (imu is None or not imu.ok or abs(imu.obrot) < 3)):
            powod, mocno = "utknąłem: silniki pracują, a obraz stoi", True
        if abs(lewo - prawo) < 0.05:
            strona = self._strona_omijania
        else:
            strona = -1 if lewo > prawo else 1
        self.ocena = dict(odl=[round(x, 2) for x in odl], przod=round(przod, 2), powod=powod)
        return dict(odl=odl, przod=przod, lewo=lewo, prawo=prawo, powod=powod, mocno=mocno, strona=strona,
                    bez_glebi=not sektory)

    def _przeszkoda(self, obiekty, sektory):
        """(czy przed łazikiem jest przeszkoda albo coś za blisko, w którą stronę jest więcej miejsca)"""
        oc = self._ocen(obiekty, sektory)
        return oc["powod"] is not None or oc["przod"] < self.konf["odleglosc_zwolnij_cm"] / 100 * 0.6, oc["strona"]

    def _omin(self, oc):
        """Cofnij się trochę i obróć o kąt w stronę, gdzie jest więcej miejsca. Kilka omijań w krótkim czasie = kąt:
        zawracamy. Strona zostaje ta sama przez kilka sekund, żeby nie bujać się lewo-prawo przed przeszkodą."""
        teraz = time.monotonic()
        self._blokady = [t for t in self._blokady if teraz - t < 12] + [teraz]
        strona = self._strona_omijania if teraz - self._t_omijania < 6 else oc["strona"]
        self._strona_omijania, self._t_omijania = strona, teraz
        if len(self._blokady) >= 4:
            kat, co = 160, "zawracam (chyba jestem w kącie)"
            self._blokady.clear()
        else:
            kat, co = random.uniform(45, 70), f"skręcam {'w prawo' if strona > 0 else 'w lewo'}"
        cofanie = 0.7 if oc["mocno"] else 0.4 if oc["przod"] < self.konf["odleglosc_stop_cm"] / 100 * 0.7 else 0.2
        self.opis = f"{oc['powod'][0].upper() + oc['powod'][1:]}: cofam się i {co}."
        self._plan = [dict(nazwa="cofam", typ="czas", sek=cofanie, v=-0.55, s=0.0), self._obrot("omijam", strona * kat)]
        self._krok_planu()

    def _wedruj(self, obiekty, sektory, predkosc=0.55):
        oc = self._ocen(obiekty, sektory)
        if oc["powod"]:
            self._omin(oc)
            return
        teraz = time.monotonic()
        if teraz - self._t_losowego > random.uniform(15, 25):  # czasem zmień kierunek, żeby zwiedzać
            self._t_losowego = teraz
            self.opis = "Zmieniam kierunek, żeby zobaczyć coś nowego."
            self._plan = [self._obrot("zwrot", random.choice((-1, 1)) * random.uniform(60, 140))]
            self._krok_planu()
            return
        k = self.konf
        stop, zw = k["odleglosc_stop_cm"] / 100, k["odleglosc_zwolnij_cm"] / 100
        mnoznik = max(0.45, min(1.0, (oc["przod"] - stop) / max(0.05, zw - stop)))   # im bliżej, tym wolniej
        if oc["bez_glebi"]:
            mnoznik = min(mnoznik, 0.6)   # bez głębi widzę tylko obiekty YOLO: ostrożnie
        skret = 0.0
        if min(oc["lewo"], oc["prawo"]) < zw * 1.5:  # coś z boku: lekko odbij w stronę, gdzie więcej miejsca
            skret = max(-0.3, min(0.3, 0.25 * (math.log(oc["prawo"]) - math.log(oc["lewo"]))))
        self._jedz(predkosc * mnoznik, skret)
        if oc["przod"] < zw:
            self.opis = f"Coś przede mną (~{oc['przod'] * 100:.0f} cm): zwalniam."
            return True
        return False
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
            self._plan = [self._obrot("ucieczka", kier * 120)] + ([] if blisko else [dict(nazwa="ucieczka", typ="czas", sek=1.0, v=0.6, s=0.0)])
            self._krok_planu()
            return
        if teraz - self._t_rozgladania > self.konf.get("rozgladanie_co_s", 8):  # co jakiś czas rozejrzyj się, bo kamera widzi tylko przed siebie
            self._t_rozgladania = teraz
            self.opis = "Czuwam: obracam się, żeby rozejrzeć się dookoła."
            self._plan = [self._obrot("rozgladanie", random.choice((-1, 1)) * random.uniform(60, 100))]
            self._krok_planu()
            return
        self._stoj()
        widac = ", ".join(sorted({o["nazwa"] for o in obiekty})) or "nic"
        self.opis = f"Czuwam, nie widzę zagrożenia (w kadrze: {widac})."

    # --- zwiedzaj ---
    def _zwiedzaj(self, klatka, obiekty, sektory):
        if not self._wedruj(obiekty, sektory, self.konf.get("predkosc_zwiedzania", 0.55)) and self._akcja is None:
            self.opis = f"Zwiedzam i nagrywam do skanu 3D ({self.nagrywanie.klatki} klatek)."

    # --- fotograf ---
    def _fotograf(self, klatka, obiekty, sektory):
        teraz = time.monotonic()
        kandydaci = [o for o in obiekty if o["pew"] > 0.55 and o["klasa"] not in NUDNE
                     and teraz - self.zdjecia_klas.get(o["klasa"], -1e9) > self.konf.get("fotograf_co_ile_s", 180)]
        if not kandydaci:
            if not self._wedruj(obiekty, sektory, 0.45) and self._akcja is None:
                self.opis = f"Szukam czegoś ciekawego do zdjęcia (zrobione: {self.liczba_zdjec})."
            return
        # najrzadziej fotografowana klasa, a wśród nich najbardziej pewna
        o = min(kandydaci, key=lambda x: (self.ile_zdjec.get(x["klasa"], 0), -x["pew"]))
        x0, y0, x1, y1 = o["ramka"]
        cx, wys = (x0 + x1) / 2, y1 - y0
        blisko, _ = self._przeszkoda([x for x in obiekty if x is not o], sektory)
        if wys < 0.45 and not blisko:
            self.opis = f"Podjeżdżam do: {o['nazwa']} ({gdzie(cx)})."
            m = 0.8 * self._obr()
            self._jedz(0.45, max(-m, min(m, (cx - 0.5) * 1.2)))
            return
        self._stoj()
        self._zdjecie(klatka, obiekty, o)
        self.zdjecia_klas[o["klasa"]] = teraz
        self.ile_zdjec[o["klasa"]] = self.ile_zdjec.get(o["klasa"], 0) + 1
        self.opis = f"Zrobiłem zdjęcie: {o['nazwa']}. Szukam czegoś innego."
        self._plan = [self._obrot("odwrot", random.choice((-1, 1)) * random.uniform(90, 150))]
        self._krok_planu()

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
        teraz, k = time.monotonic(), self.konf
        # 1. blokada celu: dotknięty obiekt albo najbliższy (najniżej stojący) obiekt wybranego rodzaju
        if self._zadanie_celu is not None:
            o = next((o for o in obiekty if o["id"] == self._zadanie_celu), None)
            if o is not None:
                self.cel.zacznij(klatka, o, teraz)
                self._zadanie_celu = None
        if not self.cel.aktywny and self.cel_id is None and self._zadanie_celu is None:
            pas = [o for o in obiekty if o["klasa"] == self.cel_klasa and o["pew"] > 0.4]
            if pas:
                self.cel.zacznij(klatka, max(pas, key=lambda o: o["ramka"][3]), teraz)
        ramka = self.cel.aktualizuj(klatka, obiekty, teraz) if self.cel.aktywny else None
        if self.cel.aktywny and self.cel_id is not None:
            self.cel_id = self.cel.id   # numer ramki YOLO mógł się zmienić, a to wciąż ten sam cel
        kogo = DO_SLEDZENIA.get(self.cel.klasa if self.cel.klasa is not None else self.cel_klasa, nazwa(self.cel_klasa))
        m_obr = self._obr()
        if ramka is None:
            if self._cel_ostatnio and teraz - self._cel_ostatnio[0] < 4:
                strona = 1 if self._cel_ostatnio[1] > 0.5 else -1
                self.opis = f"Zgubiłem cel ({kogo}): powoli szukam {'w prawo' if strona > 0 else 'w lewo'}."
                self._jedz(0.0, 0.8 * m_obr * strona)
            else:
                self._stoj()
                if self.cel.aktywny:
                    self.opis = f"Nie widzę celu ({kogo}): czekam, aż wróci (rozpoznam go po wyglądzie)."
                elif self._zadanie_celu is not None or self.cel_id is not None:
                    self.opis = "Wybrany obiekt zniknął. Dotknij go jeszcze raz na podglądzie albo wybierz rodzaj."
                else:
                    self.opis = f"Nie widzę: {kogo}. Dotknij obiektu na podglądzie albo wybierz rodzaj."
            return
        x0, y0, x1, y1 = ramka
        cx = (x0 + x1) / 2
        self._cel_ostatnio = (teraz, cx, self.cel.klasa)
        # 2. odległość do celu w metrach z miejsca, gdzie dotyka podłogi (dolna krawędź ramki)
        if y1 >= 0.97:
            odl = Z.odleglosc_z_wiersza(1.0, k)          # stopy poza kadrem: bliżej niż dół kadru
        elif y1 > k.get("horyzont", 0.5) + 0.03:
            odl = Z.odleglosc_z_wiersza(y1, k)
        else:                                            # wisi w powietrzu: zgrubnie z wysokości ramki
            odl = 0.5 / max(0.05, y1 - y0)
        cel_odl = k.get("sledzenie_odleglosc_cm", 60) / 100
        # 3. skręt łagodny, z martwą strefą (nie kręci się przy każdym drgnięciu celu)
        blad = cx - 0.5
        skret = 0.0 if abs(blad) < 0.07 else max(-0.8 * m_obr, min(0.8 * m_obr, blad * 1.4))
        # 4. prędkość: proporcjonalnie do tego, ile brakuje do zadanej odległości
        roznica = odl - cel_odl
        v = 0.0 if abs(roznica) < 0.12 else max(-0.35, min(k.get("predkosc_sledzenia", 0.6), roznica * 0.9))
        if v > 0 and abs(blad) > 0.3:
            v *= 0.5                                     # cel mocno z boku: najpierw się obróć
        oc = self._ocen([o for o in obiekty if o["id"] != self.cel.id], sektory)
        przeszkoda = oc["przod"] < min(k["odleglosc_stop_cm"] / 100, odl - 0.2) or (oc["powod"] and oc["mocno"])
        zr = " (prowadzi tracker)" if self.cel.zrodlo == "tracker" else ""
        if v > 0 and przeszkoda:
            v = 0.0
            self.opis = f"Śledzę {kogo}{zr}, ale między nami jest przeszkoda: tylko się obracam."
        elif v == 0:
            self.opis = f"Śledzę {kogo}{zr}: jestem w dobrej odległości (~{odl * 100:.0f} cm)."
        else:
            self.opis = f"Śledzę {kogo}{zr} (~{odl * 100:.0f} cm, {gdzie(cx)}): {'jadę za nim' if v > 0 else 'cofam się, za blisko'}."
        self._jedz(v, skret)
