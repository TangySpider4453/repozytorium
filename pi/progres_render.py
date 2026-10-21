#!/usr/bin/env python3
"""
Render filmu z postepu sylwetki na Raspberry Pi (wywolywany przez portal, app.py, z niskim priorytetem: nice).

  progres_render.py <wejscie.json> <wyjscie.mp4> <plik_postepu>
  progres_render.py <wejscie.json> --klatki 0.5,3.0 <katalog>     (test: zapisuje wybrane chwile jako PNG)

Geometria, przyciecie i os czasu sa przepisane 1:1 z progres/app.js (geom, ramkaAuto/ramkaKoncowa, plan, napis),
wiec film z Pi wyglada tak samo jak podglad w przegladarce.
wejscie.json: {"film": {...ustawienia...}, "kl": [{id, w, h, data, pose?, reczne?}], "wpisy": {...}, "katalog": "<zdjecia>"}
"""
import json
import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FPS = 30
FORMATY = {"4:5": (1080, 1350), "9:16": (1080, 1920), "1:1": (1080, 1080)}
MIES = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"]
CZCIONKI = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]


def krotko(d):
    y, m, dd = d.split("-")
    return f"{int(dd)} {MIES[int(m) - 1]} {y}"


def pl(x, n=1):
    return f"{x:.{n}f}".replace(".", ",")


# ---------- geometria (jak geom / ramkaAuto / ramkaKoncowa w app.js) ----------
def geom(z, W, H, cel):
    iw, ih = z["w"], z["h"]
    r, p = z.get("reczne") or {}, z.get("pose")
    if p and p.get("s", 0) > 0:
        k = (cel["s"] * H) / (p["s"] * ih) * (r.get("z") or 1)
        ox = W / 2 + (r.get("dx") or 0) * cel["s"] * H - p["cx"] * iw * k
        oy = cel["y"] * H + (r.get("dy") or 0) * cel["s"] * H - p["cy"] * ih * k
    else:
        k = H / ih * (r.get("z") or 1)
        ox = (W - iw * k) / 2 + (r.get("dx") or 0) * cel["s"] * H
        oy = (H - ih * k) / 2 + (r.get("dy") or 0) * cel["s"] * H
    return {"k": k, "ox": ox, "oy": oy, "w": iw * k, "h": ih * k}


def ramka_auto(kl, W, H, cel):
    if not kl:
        return None
    x0, y0, x1, y1 = 0, 0, W, H
    for z in kl:
        q = geom(z, W, H, cel)
        x0, y0 = max(x0, q["ox"]), max(y0, q["oy"])
        x1, y1 = min(x1, q["ox"] + q["w"]), min(y1, q["oy"] + q["h"])
    w = min(x1 - x0, (y1 - y0) * W / H)
    h = w * H / W
    if not w > W * 0.2:
        return None
    ax, ay = W / 2, cel["y"] * H
    x, y = ax - ax / W * w, ay - ay / H * h
    x = min(max(x, x0), x1 - w)
    y = min(max(y, y0), y1 - h)
    return {"x": x, "y": y, "w": w, "h": h}


def ramka_koncowa(kl, W, H, cel, film):
    m = film.get("ramka")
    if m and m.get("w", 0) > 0:
        return {"x": m["x"] * W, "y": m["y"] * H, "w": m["w"] * W, "h": m["w"] * H}
    if film.get("przytnij") is not False:
        a = ramka_auto(kl, W, H, cel)
        if a:
            return a
    return {"x": 0, "y": 0, "w": W, "h": H}


# ---------- os czasu (jak plan() w app.js) ----------
def plan(film, n):
    if film.get("tryb") == "pp":
        t = max(0.1, film.get("ppT") or 1.5)
        tr = max(0.0, film.get("ppTr") or 0)

        def stan(s):
            if s < t:
                w = 0
            elif s < t + tr:
                w = 0.5 * (s - t) / tr
            elif s < 2 * t + tr:
                w = 0.5
            elif s < 2 * t + 2 * tr:
                w = 0.5 + 0.5 * (s - 2 * t - tr) / tr
            else:
                w = 1
            return 0, 1, w, ([0] if w < 0.25 else [1] if w > 0.75 else [0, 1])
        return 3 * t + 2 * tr, stan
    sek = max(0.1, film.get("sek") or 0.5)
    fade = min(film.get("przejscie") or 0, sek)

    def stan(s):
        i = min(int(math.floor(s / sek)), n - 1)
        wk = s - i * sek
        if fade > 0 and i + 1 < n and wk > sek - fade:
            return i, i + 1, (wk - (sek - fade)) / fade, [i]
        return i, None, 0, [i]
    return n * sek + 0.6, stan


def tekst_napisu(zs, wpisy):
    wp = [wpisy.get(z["data"]) or {} for z in zs]
    if len(zs) == 2:
        a, b = wp
        cz = [f"{krotko(zs[0]['data'])} → {krotko(zs[1]['data'])}"]
        if a.get("masa") is not None and b.get("masa") is not None:
            cz.append(f"{pl(a['masa'])} → {pl(b['masa'])} kg")
        if a.get("fat") is not None and b.get("fat") is not None:
            cz.append(f"{pl(a['fat'])} → {pl(b['fat'])}% tł.")
        return "  ·  ".join(cz)
    w = wp[0]
    cz = [krotko(zs[0]["data"])]
    if w.get("masa") is not None:
        cz.append(pl(w["masa"]) + " kg")
    if w.get("fat") is not None:
        cz.append(pl(w["fat"]) + "% tł.")
    if w.get("muscle") is not None:
        cz.append(pl(w["muscle"]) + "% mięśni")
    return "  ·  ".join(cz)


class Render:
    def __init__(self, wej):
        self.film = wej["film"]
        self.kl = wej["kl"]
        self.wpisy = wej.get("wpisy") or {}
        self.katalog = Path(wej["katalog"])
        self.W, self.H = FORMATY.get(self.film.get("format"), FORMATY["4:5"])
        self.cel = {"s": self.film.get("celS") or 0.26, "y": self.film.get("celY") or 0.44}
        self.rk = ramka_koncowa(self.kl, self.W, self.H, self.cel, self.film)
        self.dl, self.stan = plan(self.film, len(self.kl))
        self.cache = {}
        self.napisy = {}
        fs = round(self.W * 0.038)
        self.fs = fs
        self.font = next((ImageFont.truetype(f, fs) for f in CZCIONKI if Path(f).exists()), None) or ImageFont.load_default(fs)

    def baza(self, i):
        """zdjecie i wyrownane i przyciete do kadru W x H (jak wRamce + rysujKlatke)"""
        if i in self.cache:
            return self.cache[i]
        if len(self.cache) > 3:
            self.cache.pop(next(iter(self.cache)))
        z = self.kl[i]
        W, H, r = self.W, self.H, self.rk
        q = geom(z, W, H, self.cel)
        with Image.open(self.katalog / f"{z['id']}.jpg") as im:
            im = im.convert("RGB")
            iw, ih = im.size
            sc = W / r["w"]
            s_img = q["w"] / iw * sc              # piksele wyjscia na piksel zdjecia
            dx, dy = (q["ox"] - r["x"]) * sc, (q["oy"] - r["y"]) * sc
            out = im.transform((W, H), Image.Transform.AFFINE, (1 / s_img, 0, -dx / s_img, 0, 1 / s_img, -dy / s_img),
                               resample=Image.Resampling.BICUBIC, fillcolor=(0, 0, 0))
        self.cache[i] = out
        return out

    def napis(self, idx):
        key = tuple(idx)
        if key not in self.napisy:
            t = tekst_napisu([self.kl[i] for i in idx], self.wpisy)
            fs, W, H, font = self.fs, self.W, self.H, self.font
            tw = font.getlength(t)
            while tw > W * 0.88 and hasattr(font, "font_variant"):      # dlugi napis: mniejsza czcionka, zeby sie miescil
                fs = int(fs * 0.92)
                font = font.font_variant(size=fs)
                tw = font.getlength(t)
            bw, bh = int(tw + fs * 1.4), int(fs * 1.7)
            y = H - fs * 1.6
            box = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
            d = ImageDraw.Draw(box)
            d.rounded_rectangle((0, 0, bw - 1, bh - 1), radius=int(fs * 0.5), fill=(0, 0, 0, 140))
            d.text((bw / 2, bh / 2), t, font=font, fill=(255, 255, 255, 255), anchor="mm")
            self.napisy[key] = (box, (int(W / 2 - bw / 2), int(y - bh / 2)))
        return self.napisy[key]

    def klatka(self, s):
        a, b, w, idx = self.stan(min(s, self.dl - 1e-6))
        img = self.baza(a)
        if b is not None and w > 0:
            img = Image.blend(img, self.baza(b), w)
        else:
            img = img.copy()
        if self.film.get("napisy", True):
            box, pos = self.napis(idx)
            img.paste(box, pos, box)
        return img


def main():
    wej = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    R = Render(wej)
    if len(sys.argv) > 2 and sys.argv[2] == "--klatki":
        out = Path(sys.argv[4])
        out.mkdir(parents=True, exist_ok=True)
        for s in [float(x) for x in sys.argv[3].split(",")]:
            R.klatka(s).save(out / f"klatka_{s:.2f}.png")
        return
    wyj, postep = Path(sys.argv[2]), Path(sys.argv[3])
    n = max(1, math.ceil(R.dl * FPS))
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{R.W}x{R.H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
                           "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-threads", "2", str(wyj)],
                          stdin=subprocess.PIPE)
    poprz_klucz, poprz = None, None
    for f in range(n):
        s = f / FPS
        a, b, w, idx = R.stan(min(s, R.dl - 1e-6))
        klucz = (a, b, round(w, 3) if b is not None else 0, tuple(idx))
        if klucz != poprz_klucz:           # ta sama klatka co poprzednio: nie licz jej drugi raz
            poprz, poprz_klucz = R.klatka(s).tobytes(), klucz
        ff.stdin.write(poprz)
        if f % 15 == 0:
            postep.write_text(str(round(f / n * 100)))
    ff.stdin.close()
    if ff.wait() != 0:
        sys.exit("ffmpeg zakonczyl sie bledem")
    postep.write_text("100")


if __name__ == "__main__":
    main()
