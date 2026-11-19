"""Szacunek zaplanowanego treningu: czas, kcal, średnie tętno, moc, dystans, TSS.
Skalowany na danych Antka: tętno względem intensywności z jego jazd/biegów, kcal/min siłki z jego siłek."""
import json
import time
from datetime import date, timedelta
from statistics import median

from . import baza, budowa, kontekst

STREFA = [.5, .68, .83, .97, 1.12]          # środek strefy 1–5 jako ułamek progu (FTP / tempa progowego)
DOMYSLNIE = {"rozgrzewka": .55, "schlodzenie": .5, "odpoczynek": .48, "przerwa": .4}
_cache = {"t": 0, "d": None}


def progi(db):
    s = baza.kv(db, "strefy", {}) or {}
    lt = (s.get("prog_mleczanowy") or {}).get("speed_and_heart_rate") or {}
    return {"ftp": (s.get("ftp") or {}).get("functionalThresholdPower"),
            "hr_rower": lt.get("heartRateCycling"), "hr_bieg": lt.get("heartRate"),
            "v_bieg": lt["speed"] * 10 if lt.get("speed") else None}        # m/s (Garmin trzyma prędkość /10)


def _fit(pary):
    """prosta regresja y = a + b·x; None gdy za mało punktów"""
    if len(pary) < 5:
        return None
    n = len(pary)
    sx = sum(x for x, _ in pary); sy = sum(y for _, y in pary)
    sxx = sum(x * x for x, _ in pary); sxy = sum(x * y for x, y in pary)
    m = n * sxx - sx * sx
    if abs(m) < 1e-9:
        return None
    b = (n * sxy - sx * sy) / m
    return (sy - b * sx) / n, b


def kalibracja(db):
    """z ostatnich ~120 dni: tętno vs intensywność (rower, bieg), siłka: kcal/min i tętno; BMR na minutę"""
    if _cache["d"] and time.time() - _cache["t"] < 3600:
        return _cache["d"]
    p = progi(db)
    od = (date.today() - timedelta(days=120)).isoformat()
    rower, bieg, silka, bmr = [], [], [], []
    for typ, dane in db.execute("SELECT typ, dane FROM aktywnosci WHERE dzien >= ?", (od,)):
        j = baza.rozpakuj(dane) or {}
        mn = (j.get("duration") or 0) / 60
        if mn < 15:
            continue
        if j.get("bmrCalories"):
            bmr.append(j["bmrCalories"] / mn)
        k, hr = kontekst.kategoria(typ), j.get("averageHR")
        if k == "rower" and hr and j.get("avgPower") and p["ftp"]:
            rower.append((j["avgPower"] / p["ftp"], hr))
        elif k == "bieg" and hr and j.get("averageSpeed") and p["v_bieg"]:
            bieg.append((j["averageSpeed"] / p["v_bieg"], hr))
        elif k == "silka" and j.get("calories"):
            silka.append(((j["calories"] - (j.get("bmrCalories") or 0)) / mn, hr))
    d = {"progi": p, "hr_rower": _fit(rower), "hr_bieg": _fit(bieg),
         "silka_kcal_min": median([x for x, _ in silka]) if silka else 4.5,
         "silka_hr": median([h for _, h in silka if h]) if any(h for _, h in silka) else None,
         "bmr_min": median(bmr) if bmr else 1.4}
    _cache.update(t=time.time(), d=d)
    return d


def _intens(k, sport, p, fit):
    sr = (k["od"] + k["do"]) / 2 if k.get("od") is not None and k.get("do") is not None else None
    if k.get("cel") in ("strefa_tetna", "strefa_mocy") and k.get("strefa"):
        return STREFA[min(5, max(1, k["strefa"])) - 1]
    if k.get("cel") == "moc" and sr and p["ftp"]:
        return sr / p["ftp"]
    if k.get("cel") == "tetno" and sr:
        if fit and fit[1] > 0:
            return max(.35, min(1.2, (sr - fit[0]) / fit[1]))
        hrp = p["hr_bieg"] if sport == "bieg" else p["hr_rower"]
        if hrp:
            return min(1.15, .5 + (sr / hrp - .55) * 1.4)
    if k.get("cel") == "tempo" and sr and p["v_bieg"]:
        return (1000 / sr) / p["v_bieg"]
    return DOMYSLNIE.get(k.get("rodzaj"), .75)


def _hr(i, k, sport, p, fit):
    if k.get("cel") == "tetno" and k.get("od") is not None and k.get("do") is not None:
        return (k["od"] + k["do"]) / 2
    if fit:
        return fit[0] + fit[1] * i
    hrp = p["hr_bieg"] if sport == "bieg" else p["hr_rower"]
    return hrp * (.55 + (i - .5) / 1.4) if hrp else None


def trening(db, t, masa=None):
    """-> {min, kcal (jak pokaże Garmin), kcal_akt (ponad spoczynkowe), tetno, moc, moc_np, km, tss, ...}"""
    if isinstance(t.get("kroki"), str):
        t = {**t, "kroki": json.loads(t["kroki"] or "[]")}
    sport = t.get("sport")
    if sport == "odpoczynek":
        return {}
    k_ = kalibracja(db)
    p = k_["progi"]
    mn = budowa.czas_min(t) or 0
    if not mn:
        return {}
    w = {"min": mn}
    if sport == "silka":
        w["kcal_akt"] = round(k_["silka_kcal_min"] * mn)
        if k_["silka_hr"]:
            w["tetno"] = round(k_["silka_hr"])
    else:
        fit = k_["hr_rower" if sport == "rower" else "hr_bieg"]
        bl = []                                       # (sekundy, intensywność, tętno)

        def dodaj(k):
            m = k.get("czas_min") or ((k.get("dystans_km") or 0) * (5.5 if sport == "bieg" else 2.2)) or 3
            i = _intens(k, sport, p, fit)
            bl.append((m * 60, i, _hr(i, k, sport, p, fit)))
        for k in t.get("kroki") or []:
            if k.get("rodzaj") == "powtorz":
                for _ in range(k.get("razy") or 1):
                    for x in k.get("kroki") or []:
                        dodaj(x)
            else:
                dodaj(k)
        s = sum(b[0] for b in bl) or 1
        i_sr = sum(b[0] * b[1] for b in bl) / s
        hr = [b for b in bl if b[2]]
        if hr:
            w["tetno"] = round(sum(b[0] * b[2] for b in hr) / sum(b[0] for b in hr))
            w["tetno_max"] = round(max(b[2] for b in hr))
        if sport == "rower" and p["ftp"]:
            w["moc"] = round(i_sr * p["ftp"])
            np_ = (sum(b[0] * (b[1] * p["ftp"]) ** 4 for b in bl) / s) ** .25
            w["moc_np"] = round(np_)
            w["tss"] = round(s * np_ * (np_ / p["ftp"]) / (p["ftp"] * 3600) * 100)
            w["kcal_akt"] = round(sum(b[0] * b[1] * p["ftp"] for b in bl) / 1000)       # kJ ≈ kcal (sprawność ~24%)
            w["km"] = round(s / 3600 * (22 + 10 * (i_sr - .6)), 1)                         # luźno: ~22 km/h w Z2
        elif sport == "bieg" and p["v_bieg"]:
            km = sum(b[0] * b[1] * p["v_bieg"] for b in bl) / 1000
            w["km"] = round(km, 1)
            w["tempo"] = f"{int(s / km // 60)}:{int(s / km % 60):02d}/km" if km else None
            w["kcal_akt"] = round((masa or 65) * km * .95)
        else:
            w["kcal_akt"] = round(mn * (9 if sport == "rower" else 11) * i_sr / .7)
    w["kcal"] = round(w.get("kcal_akt", 0) + k_["bmr_min"] * mn)
    return {k: v for k, v in w.items() if v is not None}
