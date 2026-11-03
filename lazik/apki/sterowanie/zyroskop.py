"""Żyroskop i akcelerometr MPU6050 (GY-521) po I2C (adres 0x68 albo 0x69), bez dodatkowych bibliotek poza smbus2.

Kurs liczony jest z prędkości obrotu wokół osi pionowej. Oś pionową wyznacza grawitacja zmierzona przy starcie,
więc czujnik może być przykręcony w dowolnej pozycji (płasko, pionowo, bokiem). MPU6050 nie ma magnetometru, więc
kurs jest WZGLĘDNY: 0° to kierunek przy starcie usługi albo po „zeruj”, a nie północ. Kurs powoli dryfuje (zwykle
kilka stopni na minutę), dlatego przesunięcie zera żyroskopu jest stale douczane, gdy łazik stoi z wyłączonymi silnikami.

Kierunki: kurs i obrót > 0 oznaczają obrót W PRAWO (zgodnie z ruchem wskazówek zegara, patrząc z góry).
"""

import math
import struct
import threading
import time

from smbus2 import SMBus

CZESTOTLIWOSC = 100  # Hz
SKALA_ZYRO = 131.0   # LSB na °/s przy zakresie ±250 °/s
SKALA_AKC = 16384.0  # LSB na g przy zakresie ±2 g


def _norm(v):
    d = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / d for x in v]


class Zyroskop(threading.Thread):
    def __init__(self, konf, spoczynek=lambda: True, magistrala=1):
        """`spoczynek()` mówi, czy silniki są wyłączone (wtedy wolno douczać zero żyroskopu)."""
        super().__init__(daemon=True)
        self.konf, self.spoczynek = konf, spoczynek
        self.lock = threading.Lock()
        self.ok, self.blad = False, None
        self.kurs_ciagly = 0.0      # bez zawijania (np. 370° po pełnym obrocie i trochę), wygodny dla regulatora
        self.obrot = 0.0            # °/s, > 0 = w prawo
        self.przechyl = 0.0         # ° od pozycji przy starcie (pochylenie albo przechył w bok)
        self.temp = None
        self.przyspieszenie = 0.0   # g ponad grawitację (uderzenie, podskok)
        self.stan = "uruchamiam…"
        self._zero = [0.0, 0.0, 0.0]
        self._gora = [0.0, 0.0, 1.0]
        self._grawitacja = [0.0, 0.0, 1.0]  # bieżący kierunek „do góry” (wolno filtrowany)
        self._kalibruj = True
        self.bus = SMBus(magistrala)
        self.adres = None
        for a in (0x68, 0x69):
            try:
                if self.bus.read_byte_data(a, 0x75) in (0x68, 0x70, 0x71, 0x73, 0x98):
                    self.adres = a
                    break
            except OSError:
                pass
        if self.adres is None:
            raise RuntimeError("brak MPU6050 na I2C (0x68/0x69)")
        b, a = self.bus, self.adres
        b.write_byte_data(a, 0x6B, 0x80)   # reset
        time.sleep(0.1)
        b.write_byte_data(a, 0x6B, 0x01)   # wybudzenie, zegar z żyroskopu X (stabilniejszy)
        b.write_byte_data(a, 0x1A, 0x03)   # filtr dolnoprzepustowy ~44 Hz (drgania silników)
        b.write_byte_data(a, 0x19, 0x09)   # próbkowanie 100 Hz
        b.write_byte_data(a, 0x1B, 0x00)   # żyroskop ±250 °/s
        b.write_byte_data(a, 0x1C, 0x00)   # akcelerometr ±2 g
        time.sleep(0.1)

    @property
    def kurs(self):
        """Kurs 0–360° względem zera (0 = kierunek przy starcie albo po zerowaniu)."""
        return self.kurs_ciagly % 360.0

    def zeruj(self):
        with self.lock:
            self.kurs_ciagly = 0.0

    def kalibruj(self):
        """Ponowna kalibracja (łazik musi stać nieruchomo ~2 s): zero żyroskopu i kierunek pionu."""
        self._kalibruj = True

    def _czytaj(self):
        d = bytes(self.bus.read_i2c_block_data(self.adres, 0x3B, 14))
        v = struct.unpack(">7h", d)
        return [x / SKALA_AKC for x in v[:3]], v[3] / 340.0 + 36.53, [x / SKALA_ZYRO for x in v[4:]]

    def _kalibracja(self):
        self.stan = "kalibruję (nie ruszaj łazika)…"
        while True:
            probki, akc = [], [0.0] * 3
            for _ in range(int(1.5 * CZESTOTLIWOSC)):
                a, _, g = self._czytaj()
                probki.append(g)
                akc = [s + x for s, x in zip(akc, a)]
                time.sleep(1 / CZESTOTLIWOSC)
            n = len(probki)
            sr = [sum(p[i] for p in probki) / n for i in range(3)]
            if max(abs(p[i] - sr[i]) for p in probki for i in range(3)) < 4:
                break  # w czasie pomiaru łazik stał (wahania < 4 °/s)
            self.stan = "kalibracja: łazik się rusza, czekam…"
        self._zero = sr
        self._gora = self._grawitacja = _norm([x / n for x in akc])
        self._kalibruj = False
        self.stan = "gotowy"

    def run(self):
        try:
            self._kalibracja()
        except OSError as e:
            self.blad = f"błąd I2C żyroskopu: {e}"
            return
        self.ok = True
        t_pop = time.monotonic()
        bledy = 0
        while True:
            if self._kalibruj:
                self.ok = False
                try:
                    self._kalibracja()
                except OSError:
                    pass
                self.ok = True
                t_pop = time.monotonic()
            try:
                a, temp, g = self._czytaj()
                bledy = 0
            except OSError as e:
                bledy += 1
                if bledy > 20:
                    self.ok, self.blad = False, f"żyroskop nie odpowiada: {e}"
                time.sleep(0.05)
                continue
            self.ok, self.blad = True, None
            teraz = time.monotonic()
            dt, t_pop = min(0.1, teraz - t_pop), teraz
            g = [x - z for x, z in zip(g, self._zero)]
            # pion: wolny filtr akcelerometru (przyspieszanie i hamowanie go nie przestawia)
            dl = math.sqrt(sum(x * x for x in a)) or 1.0
            if abs(dl - 1.0) < 0.15:
                self._grawitacja = _norm([0.98 * p + 0.02 * x / dl for p, x in zip(self._grawitacja, a)])
            gora = self._grawitacja
            obrot = -sum(x * y for x, y in zip(g, gora))      # w prawo patrząc z góry = ujemnie wokół osi „w górę”
            if self.konf.get("zyro_odwroc"):
                obrot = -obrot
            if abs(obrot) < 0.08:                              # szum stojącego czujnika
                obrot = 0.0
            # douczanie zera, gdy silniki stoją i czujnik się nie kręci
            if self.spoczynek() and all(abs(x) < 1.5 for x in g):
                surowe = [x + z for x, z in zip(g, self._zero)]
                self._zero = [0.998 * z + 0.002 * s for z, s in zip(self._zero, surowe)]
            cos_p = max(-1.0, min(1.0, sum(x * y for x, y in zip(gora, self._gora))))
            with self.lock:
                self.kurs_ciagly += obrot * dt
                self.obrot = obrot
                self.przechyl = math.degrees(math.acos(cos_p))
                self.przyspieszenie = abs(dl - 1.0)
                self.temp = round(temp, 1)
            time.sleep(max(0.0, 1 / CZESTOTLIWOSC - (time.monotonic() - teraz)))

    def odczyt(self):
        with self.lock:
            return dict(kurs=round(self.kurs, 1), obrot=round(self.obrot, 1), przechyl=round(self.przechyl, 1),
                        temp=self.temp, stan=self.stan)
