"""Napęd łazika: dwa silniki przez sterownik HW-094 (L298N), bez enkoderów (sterowanie bez sprzężenia zwrotnego).

Trzymanie toru (gdy podłączony żyroskop i włączone w ustawieniach): przy jeździe bez skrętu napęd zapamiętuje kurs
i 50 razy na sekundę dodaje różnicę mocy między stronami (regulator PID), żeby łazik nie zbaczał, mimo że silniki
mają różną siłę. Każdy świadomy skręt przestawia zapamiętany kurs na nowy.

Bezpieczeństwo: każde polecenie ważne jest tylko `WAZNOSC` sekund; strażnik zatrzymuje silniki, gdy nikt
nie odświeża polecenia (zawieszony tryb, utracone połączenie). Piny i odwrócenia w konfiguracja.json.
"""

import threading
import time

WAZNOSC = 0.6  # s


class Naped:
    def __init__(self, konf):
        self.konf = konf
        self.lock = threading.Lock()
        self.lewy = self.prawy = 0.0
        self._do = 0.0
        self.blad = None
        self.imu = None                 # Zyroskop (ustawiany przez serwer, gdy czujnik jest)
        self._polecenie = None          # (predkosc, skret, maks, liniowo) ostatniego jedz()
        self._kurs_cel = None
        self._calka = 0.0
        self.korekta = 0.0
        self.trzyma_tor = False
        try:
            from gpiozero import Motor
            p = konf["piny"]
            self._l = Motor(forward=p["lewy_przod"], backward=p["lewy_tyl"], enable=p["lewy_pwm"], pwm=True)
            self._r = Motor(forward=p["prawy_przod"], backward=p["prawy_tyl"], enable=p["prawy_pwm"], pwm=True)
        except Exception as e:  # brak GPIO (np. test na komputerze) albo zajęte piny
            self._l = self._r = None
            self.blad = f"silniki niedostępne: {e}"
        threading.Thread(target=self._straznik, daemon=True).start()

    def _moc(self, x, maks=None, liniowo=False):
        """Strefa martwa L298N: poniżej ~30–40% PWM silnik tylko buczy, więc małe wartości przesuwamy w górę.
        `maks` zastępuje ustawienie „maks. moc”; `liniowo` = moc dokładnie proporcjonalna od zera (bez podbijania:
        delikatne wychylenie daje naprawdę mało mocy, nawet jeśli koła jeszcze nie ruszą)."""
        if abs(x) < 0.03:
            return 0.0
        mn, mx = (0.0 if liniowo else self.konf["min_moc"]), (self.konf["maks_moc"] if maks is None else maks)
        return (1 if x > 0 else -1) * (mn + (mx - mn) * min(1.0, abs(x)))

    def jedz(self, predkosc, skret=0.0, maks=None, liniowo=False):
        """predkosc i skret w zakresie -1..1 (skret > 0 = w prawo). Ważne przez WAZNOSC s."""
        self._polecenie = (predkosc, skret, maks, liniowo)
        self._jedz(predkosc, skret, maks, liniowo, 0.0)

    def _jedz(self, predkosc, skret, maks, liniowo, dt, przedluz=True):
        skret = self._trzymaj_tor(predkosc, skret, dt)
        l = max(-1.0, min(1.0, predkosc + skret))
        r = max(-1.0, min(1.0, predkosc - skret))
        self.ustaw(l, r, maks, liniowo, przedluz)

    def _trzymaj_tor(self, v, s, dt):
        k, imu = self.konf, self.imu
        if not (k.get("trzymaj_tor") and imu is not None and imu.ok and abs(v) > 0.05 and abs(s) < 0.04):
            self._kurs_cel, self._calka, self.korekta, self.trzyma_tor = None, 0.0, 0.0, False
            return s
        if self._kurs_cel is None:
            self._kurs_cel, self._calka = imu.kurs_ciagly, 0.0
        blad = imu.kurs_ciagly - self._kurs_cel        # > 0 = zboczył w prawo
        if abs(blad) > 60:                             # ktoś go obrócił albo w coś uderzył: nowy kierunek
            self._kurs_cel, blad, self._calka = imu.kurs_ciagly, 0.0, 0.0
        self._calka = max(-30.0, min(30.0, self._calka + blad * dt))
        kor = -(k.get("tor_kp", 0.03) * blad + k.get("tor_ki", 0.02) * self._calka + k.get("tor_kd", 0.004) * imu.obrot)
        m = k.get("tor_maks_korekta", 0.35)
        self.korekta = max(-m, min(m, kor))
        self.trzyma_tor = True
        return s + self.korekta

    def ustaw(self, lewy, prawy, maks=None, liniowo=False, przedluz=True):
        k = self.konf
        if k.get("zamien_strony"):
            lewy, prawy = prawy, lewy
        lewy = -lewy if k.get("odwroc_lewy") else lewy
        prawy = -prawy if k.get("odwroc_prawy") else prawy
        with self.lock:
            self.lewy, self.prawy = self._moc(lewy, maks, liniowo), self._moc(prawy, maks, liniowo)
            if przedluz:
                self._do = time.monotonic() + WAZNOSC
            self._zastosuj()

    def stop(self):
        with self.lock:
            self.lewy = self.prawy = 0.0
            self._do = 0.0
            self._polecenie = None
            self._zastosuj()

    def _zastosuj(self):
        if self._l is None:
            return
        for m, v in ((self._l, self.lewy), (self._r, self.prawy)):
            if v > 0:
                m.forward(v)
            elif v < 0:
                m.backward(-v)
            else:
                m.stop()

    def spoczynek(self):
        return not (self.lewy or self.prawy)

    def _straznik(self):
        """Co 20 ms: STOP przeterminowanych poleceń, a w trakcie jazdy prosto ponowne liczenie korekty toru."""
        t_pop = time.monotonic()
        while True:
            time.sleep(0.02)
            teraz = time.monotonic()
            dt, t_pop = teraz - t_pop, teraz
            with self.lock:
                if (self.lewy or self.prawy) and teraz > self._do:
                    self.lewy = self.prawy = 0.0
                    self._polecenie = None
                    self._zastosuj()
                    continue
                pol = self._polecenie if teraz <= self._do else None
            if pol is not None and self.konf.get("trzymaj_tor") and self.imu is not None:
                self._jedz(*pol, dt, przedluz=False)
