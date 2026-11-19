"""Przebieg treningu z Garmina (tętno, moc, prędkość, kadencja, wysokość co ~1 s) + okrążenia.
Pobierany przy pierwszym otwarciu treningu / omówieniu w czacie i trzymany w tabeli `przebiegi`."""
import logging
from statistics import mean

from . import baza

log = logging.getLogger(__name__)

# kanał → (klucze Garmina po kolei, mnożnik)
KANALY = {
    "tetno": (("directHeartRate",), 1),
    "moc": (("directPower",), 1),
    "predkosc": (("directSpeed",), 3.6),
    "kadencja": (("directBikeCadence", "directRunCadence", "directDoubleCadence"), 1),
    "wysokosc": (("directElevation",), 1),
    "dystans": (("sumDistance",), 0.001),
}
NAZWY = {"tetno": "tętno", "moc": "moc", "predkosc": "prędkość", "kadencja": "kadencja", "wysokosc": "wysokość"}
JEDN = {"tetno": "bpm", "moc": "W", "predkosc": "km/h", "kadencja": "rpm", "wysokosc": "m"}


def _r(v, n=1):
    return None if v is None else round(v, n)


def pobierz(db, aid, g=None):
    """-> {"t": [s], kanał: [..], "okrazenia": [...]}; None gdy Garmin nie ma przebiegu"""
    r = db.execute("SELECT dane FROM przebiegi WHERE id=?", (aid,)).fetchone()
    if r:
        return baza.rozpakuj(r[0])
    from .garmin import polacz, wywolaj
    g = g or polacz()
    d = wywolaj(g.get_activity_details, aid, 20000) or {}
    opis = {m["key"]: m["metricsIndex"] for m in d.get("metricDescriptors") or []}
    wiersze = [x.get("metrics") or [] for x in d.get("activityDetailMetrics") or []]
    if not wiersze:
        return None
    it = opis.get("sumDuration", opis.get("sumElapsedDuration"))
    ts = opis.get("directTimestamp")
    wyn = {"t": []}
    t0 = wiersze[0][ts] if ts is not None and wiersze[0][ts] else None
    for i, w in enumerate(wiersze):
        if it is not None and w[it] is not None:
            wyn["t"].append(round(w[it]))
        elif t0 and w[ts]:
            wyn["t"].append(round((w[ts] - t0) / 1000))
        else:
            wyn["t"].append(i)
    for k, (klucze, mn) in KANALY.items():
        idx = next((opis[x] for x in klucze if x in opis), None)
        if idx is None:
            continue
        s = [None if w[idx] is None else _r(w[idx] * mn, 3 if k == "dystans" else 1) for w in wiersze]
        if any(v for v in s):
            wyn[k] = s
    try:
        sp = wywolaj(g.get_activity_splits, aid) or {}
        wyn["okrazenia"] = [{"nr": i + 1, "start_s": round(sum(x.get("duration") or 0 for x in sp["lapDTOs"][:i])),
                             "s": round(l.get("duration") or 0), "km": _r((l.get("distance") or 0) / 1000, 2),
                             "tetno": _r(l.get("averageHR"), 0), "tetno_max": _r(l.get("maxHR"), 0),
                             "moc": _r(l.get("averagePower"), 0), "moc_np": _r(l.get("normalizedPower"), 0),
                             "kmh": _r((l.get("averageSpeed") or 0) * 3.6), "kadencja": _r(l.get("averageBikeCadence")
                                                                                            or l.get("averageRunCadence"), 0)}
                            for i, l in enumerate(sp.get("lapDTOs") or [])]
    except Exception:
        log.exception("okrążenia %s", aid)
    db.execute("INSERT OR REPLACE INTO przebiegi VALUES (?,?,?)", (aid, baza.pakuj(wyn), baza.teraz()))
    db.commit()
    return wyn


def wycinek(p, od_s=None, do_s=None, n=900):
    """do wykresu: przedział [od_s, do_s] uśredniony do ~n punktów (moc: średnia, ale szczyty zostają w `moc_max`)"""
    t = p["t"]
    idx = [i for i, x in enumerate(t) if (od_s is None or x >= od_s) and (do_s is None or x <= do_s)]
    if not idx:
        return {"t": []}
    krok = max(1, -(-len(idx) // n))
    wyn = {"t": [t[idx[i]] for i in range(0, len(idx), krok)]}
    for k in NAZWY:
        if k not in p:
            continue
        s = [p[k][i] for i in idx]
        sr, mx = [], []
        for i in range(0, len(s), krok):
            b = [v for v in s[i:i + krok] if v is not None]
            sr.append(_r(mean(b)) if b else None)
            mx.append(max(b) if b else None)
        wyn[k] = sr
        if k == "moc" and krok > 1:
            wyn["moc_max"] = mx
    return wyn


def _najlepsza(t, s, okno):
    """najwyższa średnia z `okno` sekund -> (wartość, start_s)"""
    best, start, j, suma = None, None, 0, 0.0
    pkt = [(a, b or 0) for a, b in zip(t, s)]
    for i in range(len(pkt)):
        suma += pkt[i][1]
        while pkt[i][0] - pkt[j][0] >= okno:
            suma -= pkt[j][1]
            j += 1
        if pkt[i][0] - pkt[j][0] >= okno * 0.8:
            v = suma / (i - j + 1)
            if best is None or v > best:
                best, start = v, pkt[j][0]
    return (round(best), start) if best is not None else (None, None)


def mm_ss(s):
    s = int(s or 0)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def dla_ai(p):
    """tekst dla Claude: przebieg co minutę (lub rzadziej), szczyty, najlepsze średnie, okrążenia"""
    if not p or not p.get("t"):
        return "brak przebiegu"
    t = p["t"]
    kon = t[-1]
    krok = 60 if kon <= 2.5 * 3600 else 120
    linie = [f"PRZEBIEG (czas od startu m:ss, średnie z {krok} s; [max]):"]
    for a in range(0, kon + 1, krok):
        idx = [i for i, x in enumerate(t) if a <= x < a + krok]
        if not idx:
            continue
        cz = []
        for k, sk in (("tetno", "HR"), ("moc", "P"), ("predkosc", "v"), ("kadencja", "kad"), ("wysokosc", "h")):
            if k in p:
                b = [p[k][i] for i in idx if p[k][i] is not None]
                if b:
                    cz.append(f"{sk} {mean(b):.0f}" + (f" [{max(b):.0f}]" if k in ("moc", "tetno") else ""))
        linie.append(f"{mm_ss(a)} " + " ".join(cz))
    if "moc" in p:
        szczyty = sorted(((v, t[i]) for i, v in enumerate(p["moc"]) if v), reverse=True)
        wybrane = []
        for v, s in szczyty:
            if all(abs(s - x) > 30 for _, x in wybrane):
                wybrane.append((v, s))
            if len(wybrane) == 6:
                break
        linie.append("SZCZYTY MOCY: " + ", ".join(f"{v:.0f} W @ {mm_ss(s)}" for v, s in wybrane))
        best = [(o, *_najlepsza(t, p["moc"], o)) for o in (5, 60, 300, 1200)]
        linie.append("NAJLEPSZE ŚREDNIE MOCY: " + ", ".join(f"{o}s {v} W @ {mm_ss(s)}" for o, v, s in best if v))
    if "tetno" in p:
        mx = max(((v, t[i]) for i, v in enumerate(p["tetno"]) if v), default=None)
        if mx:
            linie.append(f"TĘTNO MAX: {mx[0]:.0f} @ {mm_ss(mx[1])}")
    if "moc" in p and "tetno" in p and kon > 1800:   # dryf: moc/tętno w 1. vs 2. połowie
        def ef(a, b):
            m = [p["moc"][i] for i, x in enumerate(t) if a <= x < b and p["moc"][i]]
            h = [p["tetno"][i] for i, x in enumerate(t) if a <= x < b and p["tetno"][i]]
            return mean(m) / mean(h) if m and h else None
        e1, e2 = ef(0, kon / 2), ef(kon / 2, kon + 1)
        if e1 and e2:
            linie.append(f"DRYF (moc/tętno 2. połowa vs 1.): {(e2 / e1 - 1) * 100:+.1f}%")
    if p.get("okrazenia") and len(p["okrazenia"]) > 1:
        linie.append("OKRĄŻENIA: " + "; ".join(
            f"#{o['nr']} od {mm_ss(o['start_s'])} {mm_ss(o['s'])}" + "".join(
                f" {n} {o[k]}" for k, n in (("tetno", "HR"), ("moc", "P"), ("moc_np", "NP"), ("kmh", "km/h")) if o.get(k))
            for o in p["okrazenia"][:40]))
    return "\n".join(linie)
