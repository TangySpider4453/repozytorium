"""Odczyt BME280 / BMP280 po I2C (adres 0x76 albo 0x77), bez dodatkowych bibliotek poza smbus2.
Wzory kompensacji z dokumentacji Boscha (wersja zmiennoprzecinkowa)."""

import struct
import time

from smbus2 import SMBus


class BME280:
    def __init__(self, magistrala=1, adres=0x76):
        self.bus, self.adres = SMBus(magistrala), adres
        self.chip = self.bus.read_byte_data(adres, 0xD0)
        self.wilgotnosc_jest = self.chip == 0x60  # 0x60 = BME280, 0x58 = BMP280 (bez wilgotności)
        c = bytes(self.bus.read_i2c_block_data(adres, 0x88, 24))
        self.T = struct.unpack("<Hhh", c[0:6])
        self.P = struct.unpack("<Hhhhhhhhh", c[6:24])
        if self.wilgotnosc_jest:
            h1 = self.bus.read_byte_data(adres, 0xA1)
            e = bytes(self.bus.read_i2c_block_data(adres, 0xE1, 7))
            h4 = (e[3] << 4) | (e[4] & 0x0F)
            h5 = (e[5] << 4) | (e[4] >> 4)
            self.H = (h1, struct.unpack("<h", e[0:2])[0], e[2], h4 - (1 << 12) * (h4 >> 11),
                      h5 - (1 << 12) * (h5 >> 11), struct.unpack("<b", e[6:7])[0])
            self.bus.write_byte_data(adres, 0xF2, 0x01)   # wilgotność ×1
        self.bus.write_byte_data(adres, 0xF4, 0x27)       # temperatura ×1, ciśnienie ×1, tryb ciągły
        self.bus.write_byte_data(adres, 0xF5, 0xA0)       # odstęp 1 s
        time.sleep(0.05)

    def odczyt(self):
        d = self.bus.read_i2c_block_data(self.adres, 0xF7, 8)
        adc_p = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
        adc_t = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
        adc_h = (d[6] << 8) | d[7]
        t1, t2, t3 = self.T
        v1 = (adc_t / 16384.0 - t1 / 1024.0) * t2
        v2 = (adc_t / 131072.0 - t1 / 8192.0) ** 2 * t3
        t_fine = v1 + v2
        temp = t_fine / 5120.0
        p1, p2, p3, p4, p5, p6, p7, p8, p9 = self.P
        v1 = t_fine / 2.0 - 64000.0
        v2 = v1 * v1 * p6 / 32768.0 + v1 * p5 * 2.0
        v2 = v2 / 4.0 + p4 * 65536.0
        v1 = (p3 * v1 * v1 / 524288.0 + p2 * v1) / 524288.0
        v1 = (1.0 + v1 / 32768.0) * p1
        cisn = None
        if v1:
            p = 1048576.0 - adc_p
            p = (p - v2 / 4096.0) * 6250.0 / v1
            v1 = p9 * p * p / 2147483648.0
            v2 = p * p8 / 32768.0
            cisn = (p + (v1 + v2 + p7) / 16.0) / 100.0  # hPa
        wilg = None
        if self.wilgotnosc_jest:
            h1, h2, h3, h4, h5, h6 = self.H
            h = t_fine - 76800.0
            h = (adc_h - (h4 * 64.0 + h5 / 16384.0 * h)) * (h2 / 65536.0 * (1.0 + h6 / 67108864.0 * h *
                                                                         (1.0 + h3 / 67108864.0 * h)))
            h = h * (1.0 - h1 * h / 524288.0)
            wilg = max(0.0, min(100.0, h))
        return dict(temperatura=round(temp, 1), cisnienie=round(cisn, 1) if cisn else None,
                    wilgotnosc=round(wilg, 1) if wilg is not None else None)


if __name__ == "__main__":
    c = BME280()
    print("układ:", "BME280" if c.chip == 0x60 else "BMP280" if c.chip == 0x58 else hex(c.chip))
    time.sleep(1.2)
    print(c.odczyt())
