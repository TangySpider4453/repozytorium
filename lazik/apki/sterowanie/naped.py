"""Napęd łazika: dwa silniki przez sterownik HW-094 (L298N), bez enkoderów (sterowanie bez sprzężenia zwrotnego).

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
        l = max(-1.0, min(1.0, predkosc + skret))
        r = max(-1.0, min(1.0, predkosc - skret))
        self.ustaw(l, r, maks, liniowo)

    def ustaw(self, lewy, prawy, maks=None, liniowo=False):
        k = self.konf
        if k.get("zamien_strony"):
            lewy, prawy = prawy, lewy
        lewy = -lewy if k.get("odwroc_lewy") else lewy
        prawy = -prawy if k.get("odwroc_prawy") else prawy
        with self.lock:
            self.lewy, self.prawy = self._moc(lewy, maks, liniowo), self._moc(prawy, maks, liniowo)
            self._do = time.monotonic() + WAZNOSC
            self._zastosuj()

    def stop(self):
        with self.lock:
            self.lewy = self.prawy = 0.0
            self._do = 0.0
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

    def _straznik(self):
        while True:
            time.sleep(0.1)
            with self.lock:
                if (self.lewy or self.prawy) and time.monotonic() > self._do:
                    self.lewy = self.prawy = 0.0
                    self._zastosuj()
