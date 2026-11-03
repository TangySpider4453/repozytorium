"""Napęd łazika: dwa silniki przez sterownik HW-094 (L298N), bez enkoderów (sterowanie bez sprzężenia zwrotnego).

Trzymanie toru (gdy podłączony żyroskop i włączone w ustawieniach): przy jeździe bez skrętu napęd zapamiętuje kurs
i 50 razy na sekundę dodaje różnicę mocy między stronami (regulator PID), żeby łazik nie zbaczał, mimo że silniki
mają różną siłę. Każdy świadomy skręt przestawia zapamiętany kurs na nowy.

Bezpieczeństwo: każde polecenie ważne jest tylko `WAZNOSC` sekund; strażnik zatrzymuje silniki, gdy nikt
nie odświeża polecenia (zawieszony tryb, utracone połączenie). Piny i odwrócenia w konfiguracja.json.
"""

import math
import threading
import time

WAZNOSC = 0.6  # s


class Naped:
    def __init__(self, konf):
        self.konf = konf
        self.lock = threading.Lock()
        self.lewy = self.prawy = 0.0          # na piny (po odwróceniach i zamianie stron)
        self.logiczne = (0.0, 0.0)            # lewa / prawa strona łazika, + = do przodu (do telemetrii)
        self._do = 0.0
        self.blad = None
        self.imu = None                 # Zyroskop (ustawiany przez serwer, gdy czujnik jest)
        self._polecenie = None          # (predkosc, skret, maks, liniowo) ostatniego jedz()
        self._kurs_cel = None
        self._calka = 0.0
        self.korekta = 0.0
        self.trzyma_tor = False
        self._calka_obr = 0.0               # regulator prędkości obrotu (skręt ze stałą liczbą °/s)
        self.obrot_zadany = None            # °/s, gdy działa regulator obrotu (do telemetrii)
        self._zly_znak = 0.0                # ile sekund żyroskop pokazuje obrót w przeciwną stronę niż polecenie
        self.blad_zyro = None               # podejrzenie odwróconego żyroskopu (wtedy korekty wyłączone)
        self._byl_skret = False
        self.boczne = 0.0                   # szacowane zejście z linii toru [m], > 0 = w prawo
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
        skret = self._obrot_staly(skret, dt)
        skret = self._trzymaj_tor(predkosc, skret, dt)
        l = max(-1.0, min(1.0, predkosc + skret))
        r = max(-1.0, min(1.0, predkosc - skret))
        self.ustaw(l, r, maks, liniowo, przedluz)

    def _imu_ok(self):
        return self.imu is not None and self.imu.ok and self.blad_zyro is None

    def _obrot_staly(self, s, dt):
        """Skręt jako zadana prędkość obrotu: gałka w bok = tyle °/s (pełne wychylenie = `obrot_maks_dps`), a żyroskop
        dokłada albo ujmuje mocy, żeby łazik kręcił się równo (na trawie, na płytkach, przy słabszej baterii)."""
        k, imu = self.konf, self.imu
        if not (k.get("obrot_staly", True) and self._imu_ok()) or abs(s) < 0.04:
            self._calka_obr, self.obrot_zadany = 0.0, None
            self._zly_znak = 0.0
            return s
        zadany = s * k.get("obrot_maks_dps", 90)
        blad = zadany - imu.obrot
        self._calka_obr = max(-1.2, min(1.2, self._calka_obr + k.get("obrot_ki", 0.008) * blad * dt))
        wynik = max(-1.0, min(1.0, s + k.get("obrot_kp", 0.004) * blad + self._calka_obr))
        if wynik * s <= 0 or abs(wynik) < 0.05:
            # nie schodzimy do zera ani na drugą stronę: silnik poniżej progu ruszania staje i obrót by szarpał;
            # wolniej niż przy progu ruszania łazik po prostu nie umie, wtedy kręci się równo najwolniej, jak może
            wynik = math.copysign(0.05, s)
        self.obrot_zadany = round(zadany)
        # bezpiecznik: wyraźnie kręcimy w jedną stronę, a żyroskop pokazuje drugą = zły znak, wyłączamy korekty
        if abs(s) > 0.3 and imu.obrot * s < 0 and abs(imu.obrot) > 20:
            self._zly_znak += dt
            if self._zly_znak > 0.6:
                self.blad_zyro = ("żyroskop pokazuje obrót w przeciwną stronę niż silniki: korekty wyłączone. "
                                  "Włącz „Odwróć kierunek obrotu” (⚙ → Żyroskop) albo sprawdź „Zamień strony”.")
        else:
            self._zly_znak = max(0.0, self._zly_znak - dt)
        return wynik

    def _trzymaj_tor(self, v, s, dt):
        k, imu = self.konf, self.imu
        if not (k.get("trzymaj_tor") and self._imu_ok() and abs(v) > 0.05 and abs(s) < 0.04):
            self._kurs_cel, self._calka, self.korekta, self.trzyma_tor = None, 0.0, 0.0, False
            self._byl_skret = abs(s) >= 0.04
            return s
        if self._kurs_cel is None:
            # po skręcie łazik jeszcze chwilę się obraca: cel z małym wyprzedzeniem, żeby nie cofał się do starego kursu
            wyprzedzenie = imu.obrot * 0.15 if self._byl_skret else 0.0
            self._kurs_cel, self._calka, self._byl_skret = imu.kurs_ciagly + wyprzedzenie, 0.0, False
            self.boczne = 0.0
        odch = imu.kurs_ciagly - self._kurs_cel        # > 0 = obrócony w prawo od toru
        if abs(odch) > 150:                            # ktoś go zawrócił (nie wybój): przyjmujemy nowy kierunek
            self._kurs_cel, odch, self._calka, self.boczne = imu.kurs_ciagly, 0.0, 0.0, 0.0
        # powrót NA LINIĘ toru, nie tylko na kierunek: wybój obraca łazik, ten jedzie chwilę skosem i ląduje obok
        # dawnej linii. Bez enkoderów zejście w bok szacujemy z kąta i mocy (prędkość przy pełnej mocy z ustawień).
        if k.get("wracaj_na_tor", True):
            predkosc = v * k.get("predkosc_pelna_ms", 0.5)                      # m/s, < 0 = do tyłu
            self.boczne += math.sin(math.radians(odch)) * predkosc * dt
            self.boczne = max(-1.0, min(1.0, self.boczne))
            # kąt dojazdu do linii: im dalej od niej, tym ostrzej (do 25°); jadąc do tyłu skręt odwrotny
            dojazd = max(-25.0, min(25.0, -self.boczne * k.get("tor_powrot_st_na_m", 80))) * (1 if v > 0 else -1)
        else:
            self.boczne, dojazd = 0.0, 0.0
        blad = odch - dojazd
        self._calka = max(-30.0, min(30.0, self._calka + blad * dt))
        kor = -(k.get("tor_kp", 0.03) * blad + k.get("tor_ki", 0.02) * self._calka + k.get("tor_kd", 0.004) * imu.obrot)
        m = k.get("tor_maks_korekta", 0.35)
        self.korekta = max(-m, min(m, kor))
        self.trzyma_tor = True
        return s + self.korekta

    def ustaw(self, lewy, prawy, maks=None, liniowo=False, przedluz=True):
        k = self.konf
        self.logiczne = (self._moc(lewy, maks, liniowo), self._moc(prawy, maks, liniowo))
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
            self.logiczne = (0.0, 0.0)
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
                    self.logiczne = (0.0, 0.0)
                    self._polecenie = None
                    self._zastosuj()
                    continue
                pol = self._polecenie if teraz <= self._do else None
            if pol is not None and (self.konf.get("trzymaj_tor") or self.konf.get("obrot_staly", True)) and self.imu is not None:
                self._jedz(*pol, dt, przedluz=False)
