"""Strażnik magistrali I2C (piny 3/5): gdy jakieś urządzenie zawiśnie w połowie transmisji (wyrwany albo luźny przewód,
zakłócenia od silników), trzyma linię SDA w stanie niskim i cała magistrala przestaje działać (Errno 5: żyroskop,
BME280 i wyświetlacz naraz). Standardowe odblokowanie: kilka impulsów zegara na SCL, aż urządzenie puści SDA,
potem warunek STOP. Robimy to przez `pinctrl` (Raspberry Pi 5) i oddajemy piny z powrotem do I2C (funkcja a3).
"""

import subprocess
import threading
import time


def _p(*arg):
    return subprocess.run(["pinctrl", *map(str, arg)], capture_output=True, text=True, timeout=2).stdout.strip()


def sda_nisko():
    return _p("lev", 2) == "0"


def odblokuj():
    """Zwraca True, gdy po odblokowaniu SDA jest wysoko."""
    try:
        _p("set", 3, "op", "dh")
        for _ in range(9):
            _p("set", 3, "dl")
            _p("set", 3, "dh")
            if not sda_nisko():
                break
        _p("set", 2, "op", "dl")      # STOP: SDA z niskiego na wysoki przy wysokim SCL
        _p("set", 3, "dh")
        _p("set", 2, "dh")
    finally:
        _p("set", 2, "ip", "pu")
        _p("set", 2, "a3")
        _p("set", 3, "a3")
    return not sda_nisko()


class StrazI2C(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.odblokowania = 0
        self.ostatnie = None   # czas ostatniego odblokowania (tekst)

    def run(self):
        nisko = 0
        while True:
            time.sleep(0.2)
            try:
                nisko = nisko + 1 if sda_nisko() else 0
            except Exception:
                continue
            if nisko >= 3:    # 0,6 s bez przerwy: to nie zwykła transmisja, tylko zawieszona magistrala
                ok = odblokuj()
                self.odblokowania += 1
                self.ostatnie = time.strftime("%H:%M:%S")
                print(f"I2C: SDA zawieszone w stanie niskim, odblokowuję ({'udało się' if ok else 'nadal nisko: sprawdź przewody'}).",
                      flush=True)
                nisko = 0
