"""
Komunikacja miejska ZTM Poznań na Pi (moduł portalu, kopia w repo: pi/ztm.py).

  rozklad()                       rozkład GTFS z ztm.poznan.pl (pobierany raz na dobę, przetworzony do dane/ztm/rozklad.npz)
  opoznienia()                    opóźnienia na żywo (GTFS-RT trip_updates, co najwyżej co 20 s)
  odjazdy(przystanek | lat, lon)  najbliższe odjazdy z przystanku (wszystkie słupki o tej nazwie) albo z przystanków obok
  trasa(skad, dokad)              najszybsze połączenie: Connection Scan Algorithm + dojścia piesze (do 1 km na początku
                                  i na końcu, przesiadki pieszo do 400 m)
  szukaj_przystanku(tekst)        dopasowanie nazwy (bez polskich znaków, wielkości liter)

Miejsca („dom”, „szkoła”…) i lokalizację trzyma portal (dane/miejsca.json, dane/lokalizacja.json); tu przychodzą
już jako współrzędne. Wszystko lokalnie poza pobraniem rozkładu, opóźnień i (rzadko) wyszukaniem adresu w OSM Nominatim.
"""
import csv
import io
import json
import math
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

KAT = Path(__file__).resolve().parent / "dane" / "ztm"
GTFS_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGTFSFile"
RT_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGtfsRtFile?file=trip_updates.pb"
UA = {"User-Agent": "serwerek-raspberry (prywatny serwer domowy)"}
PIESZO = 1.25           # m/s po prostej (ok. 4,5 km/h z zapasem na zakręty: odległość x 1,3 / 1,35 m/s)
DOJSCIE_MAX = 1000      # m: do przystanków na początku i końcu trasy
PRZESIADKA_MAX = 400    # m: przesiadka pieszo między przystankami
OKNO = 3 * 3600         # s: ile rozkładu przeszukiwać przy trasie
TYPY = {0: "tramwaj", 3: "autobus", 2: "pociąg"}

_LOCK = threading.Lock()
_R = {}                 # wczytany rozkład
_RT = {"t": 0, "d": {}}


def norm(t):
    t = unicodedata.normalize("NFKD", (t or "").lower().replace("ł", "l"))
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).replace("/", " ").replace("-", " ").split())


def odleglosc(lat1, lon1, lat2, lon2):
    """metry (przybliżenie równoprostokątne, wystarczy w obrębie miasta); działa też na tablicach numpy"""
    x = np.radians(lon2 - lon1) * math.cos(math.radians(52.4))
    y = np.radians(lat2 - lat1)
    return 6371000 * np.sqrt(x * x + y * y)


def sek(hhmmss):
    h, m, s = hhmmss.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def hhmm(s):
    s = int(s) % 86400
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}"


# ---------------------------------------------------------------- rozkład (GTFS)
def pobierz():
    """pobiera GTFS i przetwarza go do rozklad.npz + rozklad.json (ok. 30 s na Pi)"""
    KAT.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(GTFS_URL, headers=UA), timeout=120) as r:
        dane = r.read()
    z = zipfile.ZipFile(io.BytesIO(dane))
    czytaj = lambda n: csv.DictReader(io.TextIOWrapper(z.open(n), encoding="utf-8-sig"))

    przyst = list(czytaj("stops.txt"))
    sid = {p["stop_id"]: i for i, p in enumerate(przyst)}
    linie = {l["route_id"]: (l["route_short_name"], int(l["route_type"])) for l in czytaj("routes.txt")}
    kursy = list(czytaj("trips.txt"))
    tid = {k["trip_id"]: i for i, k in enumerate(kursy)}
    uslugi = sorted({k["service_id"] for k in kursy})
    uid = {u: i for i, u in enumerate(uslugi)}
    kal = {u: {"dni": None, "od": None, "do": None, "plus": [], "minus": []} for u in uslugi}
    for c in czytaj("calendar.txt"):
        if c["service_id"] in kal:
            kal[c["service_id"]].update(dni=[int(c[d]) for d in ("monday", "tuesday", "wednesday", "thursday", "friday",
                                                                    "saturday", "sunday")], od=c["start_date"], do=c["end_date"])
    for c in czytaj("calendar_dates.txt"):
        if c["service_id"] in kal:
            kal[c["service_id"]]["plus" if c["exception_type"] == "1" else "minus"].append(c["date"])

    # stop_times: posortowane po kursie i kolejności; połączenia = kolejne pary przystanków jednego kursu
    wiersze = []
    for w in czytaj("stop_times.txt"):
        if w["trip_id"] in tid and w["stop_id"] in sid:
            wiersze.append((tid[w["trip_id"]], int(w["stop_sequence"]), sid[w["stop_id"]], sek(w["arrival_time"]),
                            sek(w["departure_time"]), w["pickup_type"] == "1", w["drop_off_type"] == "1"))
    wiersze.sort()
    a = np.array([w[:5] for w in wiersze], dtype=np.int32)
    wsiadanie = np.array([not w[5] for w in wiersze])
    wysiadanie = np.array([not w[6] for w in wiersze])
    ten_sam = a[1:, 0] == a[:-1, 0]
    i = np.nonzero(ten_sam)[0]
    pol = np.stack([a[i, 2], a[i + 1, 2], a[i, 4], a[i + 1, 3], a[i, 0], a[i, 1], a[i + 1, 1],
                    wsiadanie[i].astype(np.int32), wysiadanie[i + 1].astype(np.int32)], axis=1)
    pol = pol[np.argsort(pol[:, 2], kind="stable")]
    odj = a[wsiadanie]                                       # odjazdy: (kurs, seq, przystanek, przyjazd, odjazd)
    odj = odj[np.lexsort((odj[:, 4], odj[:, 2]))]
    ostatni = {}                                             # kierunek kursu = ostatni przystanek
    for w in wiersze:
        ostatni[w[0]] = w[2]

    lat = np.array([float(p["stop_lat"]) for p in przyst])
    lon = np.array([float(p["stop_lon"]) for p in przyst])
    piesze = []                                              # przesiadki pieszo (sąsiedzi do PRZESIADKA_MAX)
    for k in range(len(przyst)):
        d = odleglosc(lat[k], lon[k], lat, lon)
        j = np.nonzero((d <= PRZESIADKA_MAX) & (np.arange(len(przyst)) != k))[0]
        piesze.append([[int(x), int(d[x] / PIESZO)] for x in j])

    np.savez_compressed(KAT / "rozklad.tmp.npz", pol=pol, odj=odj, lat=lat, lon=lon,
                        kurs_usluga=np.array([uid[k["service_id"]] for k in kursy], dtype=np.int32))
    meta = {"pobrano": time.strftime("%Y-%m-%dT%H:%M"), "uslugi": uslugi, "kalendarz": kal,
            "przystanki": [[p["stop_name"], p["stop_code"]] for p in przyst],
            "kursy": [[k["trip_id"], linie.get(k["route_id"], (k["route_id"], 3))[0], linie.get(k["route_id"], ("", 3))[1],
                       k["trip_headsign"], przyst[ostatni.get(i, 0)]["stop_name"]] for i, k in enumerate(kursy)],
            "piesze": piesze}
    (KAT / "rozklad.tmp.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    (KAT / "rozklad.tmp.npz").replace(KAT / "rozklad.npz")
    (KAT / "rozklad.tmp.json").replace(KAT / "rozklad.json")
    with _LOCK:
        _R.clear()


def rozklad():
    with _LOCK:
        if _R:
            return _R
        if not (KAT / "rozklad.npz").exists():
            raise RuntimeError("rozkład ZTM jeszcze się pobiera, spróbuj za minutę")
        n = np.load(KAT / "rozklad.npz")
        m = json.loads((KAT / "rozklad.json").read_text(encoding="utf-8"))
        _R.update({k: n[k] for k in n.files}, **m)
        _R["norm"] = [norm(p[0]) for p in m["przystanki"]]
        _R["tid"] = {k[0]: i for i, k in enumerate(m["kursy"])}
        odj = _R["odj"]
        _R["odj_od"] = np.searchsorted(odj[:, 2], np.arange(len(m["przystanki"]) + 1))
        return _R


def aktywne_uslugi(dzien):
    """tablica bool: które usługi (service_id) jeżdżą danego dnia"""
    R = rozklad()
    ds, wd = dzien.strftime("%Y%m%d"), dzien.weekday()
    akt = []
    for u in R["uslugi"]:
        k = R["kalendarz"][u]
        ok = bool(k["dni"] and k["od"] <= ds <= k["do"] and k["dni"][wd])
        ok = (ok or ds in k["plus"]) and ds not in k["minus"]
        akt.append(ok)
    return np.array(akt)


def petla_aktualizacji():
    """wątek portalu: rozkład przy starcie (gdy brak albo starszy niż doba) i codziennie o 3:40"""
    while True:
        try:
            p = KAT / "rozklad.npz"
            if not p.exists() or time.time() - p.stat().st_mtime > 86400:
                pobierz()
        except Exception as ex:          # brak internetu itp.: spróbuje za godzinę
            print(f"ztm: {type(ex).__name__}: {ex}", flush=True)
            time.sleep(3600)
            continue
        jutro = datetime.combine(date.today() + timedelta(days=1), datetime.min.time()) + timedelta(hours=3, minutes=40)
        time.sleep(max(60, (jutro - datetime.now()).total_seconds()))


# ---------------------------------------------------------------- opóźnienia (GTFS-RT, minimalny dekoder protobuf)
def _varint(b, i):
    r = s = 0
    while True:
        x = b[i]
        i += 1
        r |= (x & 0x7F) << s
        s += 7
        if x < 0x80:
            return r, i


def _pola(b):
    i, n = 0, len(b)
    while i < n:
        k, i = _varint(b, i)
        f, t = k >> 3, k & 7
        if t == 0:
            v, i = _varint(b, i)
        elif t == 2:
            ln, i = _varint(b, i)
            v, i = b[i:i + ln], i + ln
        elif t == 1:
            v, i = b[i:i + 8], i + 8
        elif t == 5:
            v, i = b[i:i + 4], i + 4
        else:
            return
        yield f, v


def _int(v):
    return v - (1 << 64) if v >= 1 << 63 else v


def opoznienia():
    """{trip_id: (stop_sequence, opóźnienie w s)}; pamięć 20 s; bez internetu: pusto"""
    if time.time() - _RT["t"] < 20:
        return _RT["d"]
    d = {}
    try:
        with urllib.request.urlopen(urllib.request.Request(RT_URL, headers=UA), timeout=8) as r:
            b = r.read()
        for f, ent in _pola(b):
            if f != 2:
                continue
            for f2, tu in _pola(ent):
                if f2 != 3:
                    continue
                trip, seq, op = None, 0, None
                for f3, v in _pola(tu):
                    if f3 == 1:
                        trip = dict(_pola(v)).get(1, b"").decode()
                    elif f3 == 2:
                        stu = dict(_pola(v))
                        seq = stu.get(1, 0)
                        ev = dict(_pola(stu[3] if 3 in stu else stu.get(2, b"")))
                        if 1 in ev:
                            op = _int(ev[1])
                if trip and op is not None:
                    # na pierwszym przystanku (kurs jeszcze nie ruszył) ZTM podaje „przed czasem” o czas postoju na pętli:
                    # to nie jest prawdziwe wyprzedzenie, więc wtedy tylko opóźnienia; poza tym najwyżej 2 min przed czasem
                    d[trip] = (seq, max(0, op) if seq == 0 else max(-120, op))
    except Exception:
        d = _RT["d"] if time.time() - _RT["t"] < 300 else {}
    _RT.update(t=time.time(), d=d)
    return d


# ---------------------------------------------------------------- przystanki
def szukaj_przystanku(tekst):
    """indeksy słupków pasujących do nazwy: najpierw dokładna nazwa, potem początek, potem fragment"""
    R, q = rozklad(), norm(tekst)
    if not q:
        return []
    rdzen = q[:-1] if len(q) > 4 else q                     # odmiana: „Junikowa” -> „Junikow…”
    for warunek in (lambda n: n == q, lambda n: n.startswith(q), lambda n: len(q) >= 4 and q in n,
                    lambda n: len(rdzen) >= 4 and n.startswith(rdzen)):
        w = [i for i, n in enumerate(R["norm"]) if warunek(n)]
        if w:
            nazwa = min((R["przystanki"][i][0] for i in w), key=len)    # jedna nazwa, najkrótsza („Junikowo”, nie „Junikowo PKM”)
            return [i for i in w if R["przystanki"][i][0] == nazwa]
    return []


def najblizsze(lat, lon, promien=DOJSCIE_MAX):
    R = rozklad()
    d = odleglosc(lat, lon, R["lat"], R["lon"])
    i = np.nonzero(d <= promien)[0]
    return [(int(x), int(d[x])) for x in i[np.argsort(d[i])]]


def geokoduj(tekst):
    """adres -> (lat, lon, opis) przez OSM Nominatim (rzadko, z pamięcią podręczną)"""
    plik = KAT / "adresy.json"
    try:
        pam = json.loads(plik.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pam = {}
    k = norm(tekst)
    if k not in pam:
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
            {"q": tekst if "pozna" in k else tekst + ", Poznań", "format": "json", "limit": 1, "countrycodes": "pl"})
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=10) as r:
            w = json.load(r)
        pam[k] = [float(w[0]["lat"]), float(w[0]["lon"]), w[0]["display_name"].split(",")[0]] if w else None
        KAT.mkdir(parents=True, exist_ok=True)
        plik.write_text(json.dumps(pam, ensure_ascii=False), encoding="utf-8")
    return pam[k]


# ---------------------------------------------------------------- odjazdy
def odjazdy(slupki, ile=12, od=None, dojscie=None):
    """slupki: lista indeksów przystanków; dojscie: {indeks: metry} (gdy liczone od lokalizacji)"""
    R = rozklad()
    teraz = od or datetime.now()
    t0 = teraz.hour * 3600 + teraz.minute * 60 + teraz.second
    rt = opoznienia()
    wyn = []
    for dzien, przes in ((teraz.date(), 0), (teraz.date() - timedelta(days=1), 86400)):
        akt = aktywne_uslugi(dzien)
        for s in slupki:
            o = R["odj"][R["odj_od"][s]:R["odj_od"][s + 1]]
            o = o[(o[:, 4] - przes >= t0 - 300) & (o[:, 4] - przes <= t0 + 3 * 3600)]
            o = o[akt[R["kurs_usluga"][o[:, 0]]]]
            for kurs, seq, _, _, odj in o.tolist():
                k = R["kursy"][kurs]
                op = rt.get(k[0])
                opz = op[1] if op else None                          # opóźnienie z ostatniego mijanego przystanku
                przewid = odj - przes + (opz or 0)
                if przewid < t0 - 30 or k[4] == R["przystanki"][s][0]:         # odjechał albo tu kończy
                    continue
                wyn.append({"linia": k[1], "typ": TYPY.get(k[2], ""), "kierunek": k[4].upper() if k[4] else k[3],
                            "planowo": hhmm(odj - przes), "za_min": max(0, round((przewid - t0) / 60)),
                            "opoznienie_min": round(opz / 60) if opz is not None else None,
                            "slupek": R["przystanki"][s][1], "przystanek": R["przystanki"][s][0],
                            "dojscie_m": (dojscie or {}).get(s), "t": przewid})
    wyn.sort(key=lambda x: x["t"])
    if dojscie:                                              # odjazdy, na które da się zdążyć dojść
        wyn = [x for x in wyn if x["t"] - t0 >= (x["dojscie_m"] or 0) / PIESZO - 30]
    return wyn[:ile]


def tekst_odjazdow(wyn, naglowek=""):
    if not wyn:
        return (naglowek + "\n" if naglowek else "") + "Brak odjazdów w najbliższych 3 godzinach."
    linie = [naglowek] if naglowek else []
    for x in wyn:
        op = x["opoznienie_min"]
        opt = "" if op is None else " (na czas)" if op == 0 else f" (+{op} min)" if op > 0 else f" ({op} min)"
        gdzie = f" · {x['przystanek']}" + (f", {x['dojscie_m']} m" if x.get("dojscie_m") is not None else "") \
            if naglowek.startswith("Najbliżej") else ""
        linie.append(f"{x['linia']} → {x['kierunek'].title()}: {'teraz' if x['za_min'] == 0 else 'za ' + str(x['za_min']) + ' min'}"
                     f" ({x['planowo']}){opt}{gdzie}")
    return "\n".join(linie)


# ---------------------------------------------------------------- trasa (Connection Scan Algorithm)
def _csa(start, cel, t0, dzien):
    """start, cel: {przystanek: sekundy dojścia}; -> (przyjazd, lista odcinków) albo None"""
    R = rozklad()
    pol = R["pol"]
    kalejki = []
    for d, przes in ((dzien, 0), (dzien - timedelta(days=1), 86400)):
        akt = aktywne_uslugi(d)
        p = pol[(pol[:, 2] - przes >= t0) & (pol[:, 2] - przes <= t0 + OKNO)]
        p = p[akt[R["kurs_usluga"][p[:, 4]]]].copy()
        p[:, 2] -= przes
        p[:, 3] -= przes
        if przes:
            p[:, 4] = -1 - p[:, 4]                           # kurs z wczorajszej doby: osobny klucz
        kalejki.append(p)
    pol = np.concatenate(kalejki)
    pol = pol[np.argsort(pol[:, 2], kind="stable")].tolist()
    INF = 1 << 30
    T, J, wsiadl = {}, {}, {}
    for s, w in start.items():
        if t0 + w < T.get(s, INF):
            T[s], J[s] = t0 + w, ("start", w)
    piesze = R["piesze"]
    najlepszy, cel_s = INF, None
    for ds, as_, dep, arr, kurs, _, _, wsiada, wysiada in pol:
        if dep >= najlepszy:
            break
        if kurs not in wsiadl:
            if not wsiada or T.get(ds, INF) > dep - (0 if J.get(ds, ("start",))[0] == "start" else 30):
                continue
            wsiadl[kurs] = (ds, dep)
        if not wysiada or arr >= T.get(as_, INF):
            continue
        T[as_], J[as_] = arr, ("jazda", kurs, wsiadl[kurs][0], wsiadl[kurs][1], arr)
        if as_ in cel and arr + cel[as_] < najlepszy:
            najlepszy, cel_s = arr + cel[as_], as_
        for n, w in piesze[as_]:
            if arr + w < T.get(n, INF):
                T[n], J[n] = arr + w, ("pieszo", as_, w)
                if n in cel and arr + w + cel[n] < najlepszy:
                    najlepszy, cel_s = arr + w + cel[n], n
    if cel_s is None:
        return None
    odc, s = [], cel_s
    while J[s][0] != "start":
        j = J[s]
        if j[0] == "jazda":
            odc.append({"rodzaj": "jazda", "kurs": j[1], "z": j[2], "do": s, "odjazd": j[3], "przyjazd": j[4]})
            s = j[2]
        else:
            odc.append({"rodzaj": "pieszo", "z": j[1], "do": s, "sek": j[2]})
            s = j[1]
    odc.reverse()
    return najlepszy, odc, s, cel_s


def trasa(start, cel, od=None, warianty=2):
    """start/cel: {"lat", "lon"} albo {"slupki": [...]}; -> lista wariantów"""
    R = rozklad()
    teraz = od or datetime.now()
    t0 = teraz.hour * 3600 + teraz.minute * 60

    def punkty(x):
        if "slupki" in x:
            return {s: 0 for s in x["slupki"]}
        return {s: int(m / PIESZO) for s, m in najblizsze(x["lat"], x["lon"])}
    a, b = punkty(start), punkty(cel)
    if not a or not b:
        return []
    if "lat" in start and "lat" in cel and odleglosc(start["lat"], start["lon"], cel["lat"], cel["lon"]) < 700:
        m = int(odleglosc(start["lat"], start["lon"], cel["lat"], cel["lon"]))
        return [{"pieszo_calosc": True, "min": round(m / PIESZO / 60), "metry": m}]
    rt = opoznienia()
    wyn = []
    for _ in range(warianty):
        w = _csa(a, b, t0, teraz.date())
        if not w:
            break
        przyjazd, odc, s0, s1 = w
        jazdy = [o for o in odc if o["rodzaj"] == "jazda"]
        if not jazdy:
            break
        kroki = []
        if "lat" in start:
            kroki.append({"rodzaj": "pieszo", "do": R["przystanki"][s0][0], "min": round(a[s0] / 60)})
        for o in odc:
            if o["rodzaj"] == "pieszo":
                if R["przystanki"][o["z"]][0] != R["przystanki"][o["do"]][0]:
                    kroki.append({"rodzaj": "pieszo", "do": R["przystanki"][o["do"]][0], "min": max(1, round(o["sek"] / 60))})
                continue
            k = R["kursy"][o["kurs"] if o["kurs"] >= 0 else -1 - o["kurs"]]
            op = rt.get(k[0])
            kroki.append({"rodzaj": "jazda", "linia": k[1], "typ": TYPY.get(k[2], ""), "kierunek": k[4].title(),
                          "z": R["przystanki"][o["z"]][0], "slupek": R["przystanki"][o["z"]][1], "odjazd": hhmm(o["odjazd"]),
                          "do": R["przystanki"][o["do"]][0], "przyjazd": hhmm(o["przyjazd"]),
                          "opoznienie_min": round(op[1] / 60) if op else None})
        if "lat" in cel:
            kroki.append({"rodzaj": "pieszo", "do": "cel", "min": round(b[s1] / 60)})
        wyjscie = jazdy[0]["odjazd"] - a[s0]
        wyn.append({"wyjdz": hhmm(wyjscie), "za_min": max(0, round((wyjscie - t0) / 60)), "na_miejscu": hhmm(przyjazd),
                    "czas_min": round((przyjazd - max(t0, wyjscie)) / 60), "przesiadki": len(jazdy) - 1, "kroki": kroki})
        t0 = jazdy[0]["odjazd"] - a[s0] + 60                 # następny wariant: późniejszy odjazd
    return wyn


def trasa_na(start, cel, przyjazd, zapas_min=5):
    """połączenie, które dowozi najpóźniej na `przyjazd - zapas` (datetime): najpóźniejsze wyjście (szukanie
    połówkowe po godzinie wyjścia, ok. 7 przeliczeń po 0,2 s) -> wariant (dict) albo None"""
    from datetime import timedelta
    cel_t = przyjazd - timedelta(minutes=zapas_min)
    lo, hi, najlepszy = 5, 180, None                     # ile minut przed przyjazdem wyjść
    while lo <= hi:
        mid = (lo + hi) // 2
        w = trasa(start, cel, od=przyjazd - timedelta(minutes=mid), warianty=1)
        ok = w and not w[0].get("pieszo_calosc") and w[0].get("na_miejscu") and w[0]["na_miejscu"] <= cel_t.strftime("%H:%M")
        if w and w[0].get("pieszo_calosc"):
            return w[0]
        if ok:
            najlepszy, hi = w[0], mid - 1                 # zdąży: spróbuj wyjść później
        else:
            lo = mid + 1
    return najlepszy


def tekst_trasy(warianty, dokad=""):
    if not warianty:
        return f"Nie znalazłem połączenia{' do ' + dokad if dokad else ''} w najbliższych 3 godzinach."
    if warianty[0].get("pieszo_calosc"):
        return f"Najlepiej pieszo: ok. {warianty[0]['min']} min ({warianty[0]['metry']} m)."
    linie = []
    for n, w in enumerate(warianty):
        linie.append(("" if n == 0 else "\nAlbo: ") + f"wyjdź {'teraz' if w['za_min'] == 0 else 'za ' + str(w['za_min']) + ' min'}"
                     f" ({w['wyjdz']}), na miejscu {w['na_miejscu']} ({w['czas_min']} min"
                     f"{', ' + str(w['przesiadki']) + ' przesiadki' if w['przesiadki'] > 1 else ', 1 przesiadka' if w['przesiadki'] == 1 else ''})")
        for k in w["kroki"]:
            if k["rodzaj"] == "pieszo":
                if k["min"]:
                    linie.append(f"  🚶 {k['min']} min pieszo" + (f" do {k['do']}" if k["do"] != "cel" else " do celu"))
            else:
                op = k["opoznienie_min"]
                linie.append(f"  {'🚋' if k['typ'] == 'tramwaj' else '🚌'} {k['linia']} → {k['kierunek']}: {k['z']} {k['odjazd']}"
                             f"{f' (+{op} min)' if op and op > 0 else ''} → {k['do']} {k['przyjazd']}")
    return "\n".join(linie)
