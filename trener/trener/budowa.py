"""Plan (format od Claude) → JSON treningu Garmin (POST /workout-service/workout). Rower, bieg, siłka.

Krok:  {"rodzaj": rozgrzewka|praca|odpoczynek|schlodzenie, "czas_min"|"dystans_km", "cel": brak|strefa_tetna|tetno|
        moc|strefa_mocy|tempo|kadencja, "od", "do", "strefa", "opis"}
Pętla: {"rodzaj": "powtorz", "razy": N, "kroki": [kroki]}
Siłka: {"rodzaj": "cwiczenie", "nazwa", "garmin": "KATEGORIA/NAZWA", "serie", "powt" | "czas_s", "kg", "przerwa_s",
        "opis"}  (+ rozgrzewka / schlodzenie na czas)
"""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from . import config

ZASOBY = Path(__file__).resolve().parent / "zasoby"
SPORT = {"bieg": {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
         "rower": {"sportTypeId": 2, "sportTypeKey": "cycling", "displayOrder": 2},
         "silka": {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5}}
TYP = {"warmup": (1, 1), "cooldown": (2, 2), "interval": (3, 3), "recovery": (4, 4), "rest": (5, 5), "repeat": (6, 6)}
KONIEC = {"lap.button": (1, 1), "time": (2, 2), "distance": (3, 3), "iterations": (7, 7), "reps": (10, 10)}
CEL = {"brak": (1, "no.target"), "moc": (2, "power.zone"), "strefa_mocy": (2, "power.zone"), "kadencja": (3, "cadence"),
       "strefa_tetna": (4, "heart.rate.zone"), "tetno": (4, "heart.rate.zone"), "tempo": (6, "pace.zone")}
RODZAJ = {"rozgrzewka": "warmup", "praca": "interval", "odpoczynek": "recovery", "schlodzenie": "cooldown",
          "przerwa": "rest"}
KG = {"unitId": 8, "unitKey": "kilogram", "factor": 1000.0}


class BladPlanu(ValueError):
    pass


@lru_cache(1)
def garmin_cwiczenia():
    return json.loads((ZASOBY / "garmin_cwiczenia.json").read_text())


@lru_cache(1)
def cwiczenia_antka():
    """polska nazwa / alias (małe litery) → wpis"""
    m = {}
    for e in json.loads((ZASOBY / "cwiczenia_antka.json").read_text(encoding="utf-8")):
        for n in [e["nazwa"], *(e.get("aliasy") or [])]:
            m[n.lower().strip()] = e
    return m


def dopasuj(nazwa, garmin=""):
    """-> (category, exerciseName) albo (None, None): najpierw lista Antka, potem nazwa Garmin od Claude"""
    e = cwiczenia_antka().get((nazwa or "").lower().strip())
    if e and e.get("category"):
        return e["category"], e["exerciseName"]
    if garmin and "/" in garmin:
        kat, cw = [x.strip().upper() for x in garmin.split("/", 1)]
        if cw in garmin_cwiczenia().get(kat, ()):
            return kat, cw
    return None, None


PRZERWA_W_SERII = 10                                  # s, między ćwiczeniami superserii/obwodu


class Budowniczy:
    def __init__(self, sport):
        self.sport = sport
        self.nr = 0

    def _nr(self):
        self.nr += 1
        return self.nr

    def krok(self, typ, koniec, wartosc=None, opis=None, cel=None, **dod):
        t, k = TYP[typ], KONIEC[koniec]
        c = CEL.get((cel or {}).get("cel") or "brak", CEL["brak"])
        s = {"type": "ExecutableStepDTO", "stepOrder": self._nr(),
             "stepType": {"stepTypeId": t[0], "stepTypeKey": typ, "displayOrder": t[1]},
             "childStepId": None, "description": (opis or None) and str(opis)[:250],
             "endCondition": {"conditionTypeId": k[0], "conditionTypeKey": koniec, "displayOrder": k[1], "displayable": True},
             "endConditionValue": float(wartosc) if wartosc is not None else None,
             "targetType": {"workoutTargetTypeId": c[0], "workoutTargetTypeKey": c[1], "displayOrder": c[0]},
             "targetValueOne": None, "targetValueTwo": None, "zoneNumber": None}
        if cel:
            self._cel(s, cel)
        s.update(dod)
        return s

    @staticmethod
    def _cel(s, k):
        rodzaj = k.get("cel") or "brak"
        od, do = k.get("od"), k.get("do")
        if rodzaj in ("strefa_tetna", "strefa_mocy"):
            if not k.get("strefa"):
                raise BladPlanu(f"brak numeru strefy w {k}")
            s["zoneNumber"] = int(k["strefa"])
        elif rodzaj in ("tetno", "moc", "kadencja"):
            if od is None or do is None:
                raise BladPlanu(f"cel {rodzaj} bez od/do")
            s["targetValueOne"], s["targetValueTwo"] = float(min(od, do)), float(max(od, do))
        elif rodzaj == "tempo":                       # od/do w sekundach na km → m/s (wolniejsze = niższa wartość)
            if not od or not do:
                raise BladPlanu("tempo bez od/do (s/km)")
            s["targetValueOne"], s["targetValueTwo"] = 1000 / max(od, do), 1000 / min(od, do)

    def petla(self, razy, kroki_fn):
        nr = self._nr()
        return {"type": "RepeatGroupDTO", "stepOrder": nr,
                "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
                "childStepId": None, "numberOfIterations": int(razy), "smartRepeat": False, "skipLastRestStep": False,
                "endCondition": {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False},
                "endConditionValue": float(razy), "workoutSteps": kroki_fn()}

    # --- kroki z planu
    def wytrzymalosc(self, k):
        if k.get("rodzaj") == "powtorz":
            if not k.get("kroki") or not k.get("razy"):
                raise BladPlanu("pętla bez kroków/razy")
            return self.petla(k["razy"], lambda: [self.wytrzymalosc(x) for x in k["kroki"]])
        typ = RODZAJ.get(k.get("rodzaj"), "interval")
        if k.get("czas_min"):
            koniec, w = "time", round(float(k["czas_min"]) * 60)
        elif k.get("dystans_km"):
            koniec, w = "distance", round(float(k["dystans_km"]) * 1000)
        else:
            koniec, w = "lap.button", None
        return self.krok(typ, koniec, w, opis=k.get("opis"), cel=k)

    def _seria(self, k):
        """kroki jednej serii ćwiczenia: ćwiczenie (powt. albo czas) + przerwa"""
        kat, cw = dopasuj(k.get("nazwa"), k.get("garmin", ""))
        na_czas = bool(k.get("czas_s"))
        opis = ", ".join(x for x in (
            k.get("nazwa"), f"{k['kg']:g} kg" if k.get("kg") else None, k.get("opis")) if x)
        kroki = [self.krok("interval", "time" if na_czas else "reps", k["czas_s"] if na_czas else (k.get("powt") or 10),
                           opis=opis, category=kat, exerciseName=cw,
                           weightValue=float(k["kg"]) * 1000 if k.get("kg") else None,
                           weightUnit=dict(KG) if k.get("kg") else None)]
        if k.get("przerwa_s"):
            kroki.append(self.krok("rest", "time", k["przerwa_s"]))
        return kroki

    @staticmethod
    def _ile(k):
        return (f"{k.get('serie', 1)}×" if k.get("serie") else "") + (f"{k['czas_s']} s" if k.get("czas_s") else
                                                                    f"{k.get('powt') or 10}") + \
            (f" @{k['kg']:g} kg" if k.get("kg") else "")

    def silowy(self, k):
        """-> lista kroków: „Przygotuj: …” (do LAP) + serie w pętli"""
        r = k.get("rodzaj")
        if r == "cwiczenie":
            przyg = self.krok("rest", "lap.button", opis=f"Przygotuj: {k.get('nazwa')} {self._ile(k)}")
            return [przyg, self.petla(int(k.get("serie") or 1), lambda: self._seria(k))]
        if r == "powtorz":                            # obwód / superseria: ćwiczenia po kolei, `razy` rund
            cw = k.get("kroki") or []
            if not cw:
                raise BladPlanu("obwód bez ćwiczeń")
            przyg = self.krok("rest", "lap.button", opis="Przygotuj: " + " + ".join(
                f"{x.get('nazwa')} {self._ile(dict(x, serie=None))}" for x in cw if x.get("rodzaj") == "cwiczenie")
                + f" ({k.get('razy') or 1} rundy)")
            # ćwiczenie bez przerwy dostaje 10 s: bez kroku przerwy w Garminie nie da się poprawić ciężaru/ćwiczenia
            return [przyg, self.petla(int(k.get("razy") or 1), lambda: [
                s for x in cw for s in (self._seria(x if x.get("przerwa_s") else dict(x, przerwa_s=PRZERWA_W_SERII))
                                        if x.get("rodzaj") == "cwiczenie" else [self.wytrzymalosc(x)])])]
        return [self.wytrzymalosc(k)]


def opis_z_znacznikiem(t, h):
    return f"{(t.get('opis') or '').strip()[:850]}\n\n{config.ZNACZNIK} id={h[:10]}".strip()


def hash_treningu(t):
    s = json.dumps({k: t.get(k) for k in ("dzien", "sport", "tytul", "opis", "kroki")}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(s.encode()).hexdigest()


def buduj(t):
    """t: {"dzien","sport","tytul","opis","kroki"} → JSON treningu Garmin"""
    if t.get("sport") not in SPORT:
        raise BladPlanu(f"nieznany sport {t.get('sport')}")
    if not t.get("kroki"):
        raise BladPlanu("trening bez kroków")
    b = Budowniczy(t["sport"])
    if t["sport"] == "silka":
        kroki = [s for k in t["kroki"] for s in b.silowy(k)]
    else:
        kroki = [b.wytrzymalosc(k) for k in t["kroki"]]
    sport = dict(SPORT[t["sport"]])
    return {"workoutName": (t.get("tytul") or "Trening")[:48], "description": opis_z_znacznikiem(t, hash_treningu(t)),
            "sportType": sport, "workoutSegments": [{"segmentOrder": 1, "sportType": sport, "workoutSteps": kroki}]}


def czas_min(t):
    """szacowany czas treningu (min) — do UI"""
    def k_min(k, mn=1):
        if k.get("rodzaj") == "powtorz":
            return mn * (k.get("razy") or 1) * sum(k_min(x) for x in k.get("kroki") or [])
        if k.get("rodzaj") == "cwiczenie":
            s = k.get("serie") or 1
            return s * ((k.get("czas_s") or (k.get("powt") or 10) * 4) + (k.get("przerwa_s") or 60)) / 60
        return k.get("czas_min") or ((k.get("dystans_km") or 0) * (5.5 if t.get("sport") == "bieg" else 2.2))
    return round(sum(k_min(k) for k in t.get("kroki") or []))
