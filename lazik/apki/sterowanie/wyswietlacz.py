"""Mały wyświetlacz na I2C: pokazuje, czy wszystko działa (Wi-Fi, Tailscale, kamera, Hailo, czujniki, silniki,
zasilanie, temperatury), a jeśli nie, to co jest nie tak.

Obsługiwane (wykrywane same, co 5 s, więc można podłączyć w trakcie pracy):
- OLED 128×64 SSD1306 albo SH1106 (adres 0x3C/0x3D), rysowany przez Pillow,
- LCD 16×2 / 20×4 (HD44780) z modułem I2C PCF8574 (adres 0x27 albo 0x3F).
Bez zewnętrznych bibliotek poza smbus2 i Pillow.
"""

import os
import shutil
import subprocess
import threading
import time

from smbus2 import SMBus, i2c_msg

ADRESY_OLED = (0x3C, 0x3D)
ADRESY_LCD = (0x27, 0x3F, 0x20, 0x26)
CZCIONKA = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
CZCIONKA_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _jest(bus, adres):
    try:
        bus.read_byte(adres)
        return True
    except OSError:
        return False


# ---------- OLED ----------
class Oled:
    W, H = 128, 64

    def __init__(self, bus, adres, konf):
        from PIL import ImageFont
        self.bus, self.adres, self.konf = bus, adres, konf
        self.f = ImageFont.truetype(CZCIONKA, 11)
        self.fb = ImageFont.truetype(CZCIONKA_B, 11)
        for c in (0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 0x8D, 0x14, 0x20, 0x02, 0xDA, 0x12,
                  0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6, 0xAF):
            self._kom(c)
        self._obrot = None
        self._kontrast = None
        self.nazwa = f"OLED 128×64 (0x{adres:02X})"

    def _kom(self, *c):
        self.bus.i2c_rdwr(i2c_msg.write(self.adres, bytes([0x00, *c])))

    def _ustawienia(self):
        obrot = self.konf.get("wyswietlacz_obrot", 0)
        if obrot != self._obrot:
            self._kom(*((0xA0, 0xC0) if obrot == 180 else (0xA1, 0xC8)))
            self._obrot = obrot
        k = int(self.konf.get("wyswietlacz_jasnosc", 128))
        if k != self._kontrast:
            self._kom(0x81, k)
            self._kontrast = k

    def obraz(self, stan):
        from PIL import Image, ImageDraw
        img = Image.new("1", (self.W, self.H))
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, self.W - 1, 14), fill=1)          # pasek tytułu w negatywie
        d.text((3, 0), stan["tytul"], font=self.fb, fill=0)
        if stan["puls"]:
            d.rectangle((self.W - 5, 5, self.W - 3, 7), fill=0)  # mrugający punkt = program działa
        szer = lambda t: d.textlength(t, font=self.f)
        linie = []
        for t in stan["linie"]:
            if stan.get("zawijaj"):   # problemy: zawijane po słowach, żeby było widać całość
                biezaca = ""
                for slowo in t.split():
                    proba = (biezaca + " " + slowo).strip()
                    if szer(proba) <= self.W - 2 or not biezaca:
                        biezaca = proba
                    else:
                        linie.append(biezaca)
                        biezaca = "  " + slowo
                linie.append(biezaca)
            else:                     # stan: przycięte do szerokości
                while szer(t) > self.W - 2 and len(t) > 1:
                    t = t[:-2] + "…"
                linie.append(t)
        for i, linia in enumerate(linie[:4]):
            d.text((1, 16 + i * 12), linia, font=self.f, fill=1)
        return img

    def pokaz(self, stan):
        self._ustawienia()
        dane = self.obraz(stan).tobytes()                                   # 1 bit/piksel, wierszami
        przes = 2 if self.konf.get("wyswietlacz_typ") == "sh1106" else 0
        for strona in range(8):
            bajty = bytearray(self.W)
            for x in range(self.W):
                b = 0
                for bit in range(8):
                    y = strona * 8 + bit
                    if dane[y * (self.W // 8) + x // 8] & (0x80 >> (x % 8)):
                        b |= 1 << bit
                bajty[x] = b
            self._kom(0xB0 + strona, 0x00 | (przes & 0x0F), 0x10 | (przes >> 4))
            self.bus.i2c_rdwr(i2c_msg.write(self.adres, bytes([0x40]) + bytes(bajty)))

    def wylacz(self):
        self._kom(0xAE)


# ---------- LCD HD44780 + PCF8574 ----------
class Lcd:
    PODSWIETLENIE, EN, RS = 0x08, 0x04, 0x01
    # LCD ma tylko ASCII i kilka znaków (0xDF = stopień w ROM A00): polskie litery bez ogonków
    ZAMIANY = str.maketrans({**dict(zip("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")), "°": "\xdf", "✓": "+", "⚠": "!",
                             "·": "-", "—": "-", "×": "x"})

    def __init__(self, bus, adres, konf):
        self.bus, self.adres, self.konf = bus, adres, konf
        self.kolumny = int(konf.get("wyswietlacz_lcd_kolumny", 16))
        self.wiersze = 4 if self.kolumny >= 20 else 2
        for n in (0x03, 0x03, 0x03, 0x02):
            self._polbajt(n << 4, 0)
            time.sleep(0.005)
        for c in (0x28, 0x0C, 0x06, 0x01):
            self._bajt(c, 0)
        time.sleep(0.003)
        self.nazwa = f"LCD {self.kolumny}×{self.wiersze} (0x{adres:02X})"

    def _zapis(self, b):
        self.bus.write_byte(self.adres, b | self.PODSWIETLENIE)

    def _polbajt(self, dane, tryb):
        self._zapis(dane | tryb | self.EN)
        self._zapis((dane | tryb) & ~self.EN)

    def _bajt(self, b, tryb):
        self._polbajt(b & 0xF0, tryb)
        self._polbajt((b << 4) & 0xF0, tryb)

    def pokaz(self, stan):
        linie = [stan["tytul"]]
        for t in stan["linie"]:
            while len(t) > self.kolumny and stan.get("zawijaj"):
                linie.append(t[:self.kolumny])
                t = " " + t[self.kolumny:]
            linie.append(t)
        for w in range(self.wiersze):
            self._bajt(0x80 | (0x00, 0x40, 0x14, 0x54)[w], 0)
            t = (linie[w] if w < len(linie) else "").translate(self.ZAMIANY)
            for ch in t[:self.kolumny].ljust(self.kolumny):
                self._bajt(ord(ch) if ord(ch) < 256 else ord("?"), self.RS)

    def wylacz(self):
        self._bajt(0x01, 0)


# ---------- co pokazać ----------
class Wyswietlacz(threading.Thread):
    def __init__(self, konf, zbierz_stan):
        """`zbierz_stan()` zwraca słownik ze stanem usługi (z lazik_serwer)."""
        super().__init__(daemon=True)
        self.konf, self.zbierz_stan = konf, zbierz_stan
        self.urz = None
        self.nazwa = None            # wykryty wyświetlacz (na stronę)
        self.problemy = []           # ostatnia lista problemów (na stronę)
        self._wifi, self._t_wifi = None, 0.0
        self._strona = 0

    def _wykryj(self, bus):
        if not self.konf.get("wyswietlacz", True):
            return None
        for a in ADRESY_OLED:
            if _jest(bus, a):
                return Oled(bus, a, self.konf)
        for a in ADRESY_LCD:
            if _jest(bus, a):
                return Lcd(bus, a, self.konf)
        return None

    def wifi(self):
        """(nazwa sieci, sygnał dBm) albo (None, None); odświeżane co 10 s."""
        if time.monotonic() - self._t_wifi > 10:
            self._t_wifi = time.monotonic()
            try:
                ssid = subprocess.run(["nmcli", "-t", "-g", "GENERAL.CONNECTION", "dev", "show", "wlan0"],
                                      capture_output=True, text=True, timeout=3).stdout.strip() or None
            except Exception:
                ssid = None
            sygnal = None
            try:
                for l in open("/proc/net/wireless").read().splitlines()[2:]:
                    sygnal = int(float(l.split()[3]))
            except Exception:
                pass
            self._wifi = (ssid, sygnal)
        return self._wifi

    @staticmethod
    def tailscale():
        try:
            out = subprocess.run(["ip", "-4", "-br", "addr", "show", "tailscale0"], capture_output=True, text=True, timeout=2).stdout
            return next((p.split("/")[0] for p in out.split() if p.startswith("100.")), None)
        except Exception:
            return None

    def ocen(self):
        """(lista problemów, linie stanu, gdy wszystko OK)"""
        s = self.zbierz_stan()
        problemy = []
        ssid, sygnal = self.wifi()
        ts = self.tailscale()
        if not ssid:
            problemy.append("Brak Wi-Fi")
        elif sygnal is not None and sygnal < -78:
            problemy.append(f"Słabe Wi-Fi {sygnal} dBm")
        if not ts:
            problemy.append("Tailscale nie działa")
        if "brak" in (s["kamera"] or "") or "przestała" in (s["kamera"] or ""):
            problemy.append("Kamera: " + s["kamera"])
        for co, b in (("Wizja", s["blad_wizji"]), ("Silniki", s["blad_napedu"]), ("BME280", s["blad_czujnika"]),
                      ("Żyroskop", s["blad_zyroskopu"])):
            if b:
                problemy.append(f"{co}: {b}")
        if s["zasilanie"] != "OK":
            problemy.append(f"Zasilanie: {s['zasilanie']}")
        for co, t, prog in (("CPU", s["temp_cpu"], 80), ("Hailo", s["temp_hailo"], 80)):
            if t is not None and t >= prog:
                problemy.append(f"Gorąco: {co} {t:.0f}°C")
        wolne = shutil.disk_usage("/").free / 1e9
        if wolne < 1.0:
            problemy.append(f"Mało miejsca: {wolne:.1f} GB")
        t = lambda x: "—" if x is None else f"{x:.0f}°"
        linie = [
            "Wi-Fi " + (f"{sygnal}dBm " if sygnal is not None else "") + (ssid or "—"),
            f"TS {ts}" if ts else "TS —",
            f"CPU {t(s['temp_cpu'])} Hailo {t(s['temp_hailo'])}" + (f" {s['otoczenie']:.0f}°" if s.get("otoczenie") is not None else ""),
            f"{s['tryb']} · {s['fps']:.0f} kl/s" + (f" · {s['kurs']:.0f}°" if s.get("kurs") is not None else ""),
        ]
        return problemy, linie

    def run(self):
        bus = SMBus(1)
        t_wykr = 0.0
        while True:
            if self.urz is None and time.monotonic() - t_wykr > 5:
                t_wykr = time.monotonic()
                try:
                    self.urz = self._wykryj(bus)
                    self.nazwa = self.urz.nazwa if self.urz else None
                except OSError:
                    self.urz = None
            try:
                problemy, linie = self.ocen()
            except Exception as e:  # zbieranie stanu nie może zatrzymać wyświetlacza
                problemy, linie = [f"Błąd: {e}"], []
            self.problemy = problemy
            puls = int(time.monotonic()) % 2 == 0
            if problemy:
                self._strona = (self._strona + 1) % (len(problemy) * 2)  # każdy problem ~2 s, gdy jest ich więcej niż mieści się
                od = self._strona // 2
                widok = dict(tytul=f"⚠ PROBLEMY: {len(problemy)}", puls=puls, zawijaj=True,
                             linie=problemy[od:] + problemy[:od])
            else:
                widok = dict(tytul="✓ WSZYSTKO OK", puls=puls, linie=linie)
            if self.urz is not None:
                if not self.konf.get("wyswietlacz", True):
                    try:
                        self.urz.wylacz()
                    except OSError:
                        pass
                    self.urz, self.nazwa = None, None
                else:
                    try:
                        self.urz.pokaz(widok)
                    except OSError:  # odłączony albo zakłócenia: spróbujemy wykryć od nowa
                        self.urz, self.nazwa = None, None
            time.sleep(1)

