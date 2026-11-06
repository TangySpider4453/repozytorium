"""
Budowa natywnego treningu siłowego Garmin (JSON dla POST /workout-service/workout) z modelu parsera.
Kształt kroków jak w prawdziwych JSON-ach Garmina (tests/fixtures) i w modelach biblioteki garminconnect:
ExecutableStepDTO (warmup / interval / rest / cooldown, koniec: time | reps | lap.button) i RepeatGroupDTO (serie).
"""
import hashlib
import re

from .mapping import Mapa
from .parser import analizuj, ciezar, wszystkie_cwiczenia, Circuit, Exercise, RoundRest, TimedBlock, Unparsed, WarmupSets, parsuj

SPORT = {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 3}
TYP = {"warmup": (1, "warmup", 1), "cooldown": (2, "cooldown", 2), "interval": (3, "interval", 3), "rest": (5, "rest", 5),
       "repeat": (6, "repeat", 6)}
KONIEC = {"lap.button": (1, 1), "time": (2, 2), "iterations": (7, 7), "reps": (10, 10)}
BEZ_CELU = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
KG = {"unitId": 8, "unitKey": "kilogram", "factor": 1000.0}
ZNACZNIK = "auto: restortrain-garmin"
WERSJA = "12"            # zmiana budowy treningu (np. przejścia) -> istniejące treningi są przebudowywane


def hash_opisu(opis):
    return hashlib.sha256((opis or "").encode("utf-8")).hexdigest()


def nazwa_treningu(tytul):
    """„Dół B — martwy ciąg, suwnica i brzuch - 90 min” -> „Siłka Dół B”: sam początek (przed „—” / „ - ”) z dopiskiem
    „Siłka”, żeby na zegarku było widać różnicę względem oryginału RestOrTrain"""
    t = re.sub(r"\s+-\s+\d+\s*min\s*$", "", (tytul or "").strip())
    poczatek = re.split(r"\s+[—–-]\s+|:", t, maxsplit=1)[0].strip() or t
    return f"Siłka {poczatek}"


class Kroki:
    def __init__(self):
        self.nr = 0

    def _nr(self):
        self.nr += 1
        return self.nr

    def krok(self, typ, koniec, wartosc=None, opis=None, category=None, exercise=None, kg=None):
        t = TYP[typ]
        k = KONIEC[koniec]
        return {"type": "ExecutableStepDTO", "stepOrder": self._nr(),
                "stepType": {"stepTypeId": t[0], "stepTypeKey": t[1], "displayOrder": t[2]},
                "childStepId": None, "description": (opis or None) and opis[:250],
                "endCondition": {"conditionTypeId": k[0], "conditionTypeKey": koniec, "displayOrder": k[1], "displayable": True},
                "endConditionValue": float(wartosc) if wartosc is not None else None,
                "targetType": dict(BEZ_CELU), "category": category, "exerciseName": exercise,
                "weightValue": kg * 1000.0 if kg else None,          # Garmin: gramy z jednostką „kilogram”
                "weightUnit": dict(KG) if kg else None}

    def serie(self, ile, budowniczy):
        """grupa serii: numer grupy przed krokami w środku (jak create_repeat_group w garminconnect)"""
        t = TYP["repeat"]
        nr = self._nr()
        return {"type": "RepeatGroupDTO", "stepOrder": nr,
                "stepType": {"stepTypeId": t[0], "stepTypeKey": t[1], "displayOrder": t[2]},
                "childStepId": None, "numberOfIterations": int(ile), "smartRepeat": False, "skipLastRestStep": False,
                "endCondition": {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False},
                "endConditionValue": float(ile), "workoutSteps": budowniczy()}


def wskazowki(c):
    """wskazówki RestOrTrain do ćwiczenia: kąt ławki z nazwy („… na skosie dodatnim 30°”) + dopisek z planu"""
    czesci = []
    kat = re.search(r"\d+\s*°", c.name_pl)
    if kat and kat.group(0).replace(" ", "") not in (c.note or "").replace(" ", ""):
        czesci.append(f"ławka {kat.group(0).replace(' ', '')}")
    if c.weight_kg and "kg" not in (c.note or ""):
        czesci.append(f"{c.weight_kg:g} kg".replace(".", ","))
    if c.note:
        czesci.append(c.note)
    if c.per_side and not re.search(r"na\s+(nog|stron|rek|ręk)", c.note or "", re.I):
        czesci.append({"noga": "na nogę", "ręka": "na rękę"}.get(c.strona(), "na stronę"))
    return ", ".join(czesci)


def kat_lawki(c):
    """„ławka 30°” z nazwy albo dopisku ćwiczenia (do przygotowania serii rozgrzewkowych)"""
    m = re.search(r"(\d+)\s*°", f"{c.name_pl} {c.note}")
    return f"ławka {m.group(1)}°" if m else ""


def opis_kroku(c):
    czesci = []
    if c.reps_max:
        czesci.append(f"{c.reps_min}–{c.reps_max} powt." if c.reps_min != c.reps_max else f"{c.reps_max} powt.")
    if w := wskazowki(c):
        czesci.append(w)
    return ", ".join(czesci)


def buduj(zrodlo, cfg, mapa=None, nieznane=None):
    """zrodlo: {"workoutId", "workoutName" albo tytuł z kalendarza, "description"} -> JSON treningu Garmin.
    cfg: rep_target (max|min), rest_mode (timed|lap_button), przerwy_s {main, accessory, core, warmup}.
    nieznane: lista, do której trafiają nazwy ćwiczeń bez dopasowania (powiadomienie)."""
    mapa = mapa or Mapa()
    opis = zrodlo.get("description") or ""
    k = Kroki()
    kroki = []
    przerwy = cfg.get("przerwy_s", {})

    def przerwa(klasa, wlasna=None):
        s = wlasna or przerwy.get(klasa) or przerwy.get("main", 120)
        if cfg.get("rest_mode") == "lap_button":
            return k.krok("rest", "lap.button", opis=f"przerwa ok. {s} s")
        return k.krok("rest", "time", s)

    def przejscie(nazwa, szczegol=""):
        """przerwa do przycisku LAP przed ćwiczeniem: czas na przygotowanie stanowiska, w opisie co będzie"""
        if cfg.get("przejscie", True):
            kroki.append(k.krok("rest", "lap.button", opis=f"Przygotuj: {nazwa}" + (f" ({szczegol})" if szczegol else "")))

    def cwiczenie(i):
        """(fabryka kroku ćwiczenia, dopasowanie Garmin, opis ilości „4–6” / „30 s”)"""
        d = mapa.znajdz(i.name_pl)
        if d.sposob == "nieznane" and nieznane is not None:
            nieznane.append(i.name_pl)
        o = opis_kroku(i)
        if d.sposob in ("nieznane", "brak"):       # bez ćwiczenia Garmin: polska nazwa w opisie kroku
            o = f"{i.name_pl}: {o}" if o else i.name_pl
        koniec, ile = ("time", i.duration_s) if i.duration_s else \
            ("reps", i.reps_max if cfg.get("rep_target", "max") == "max" else i.reps_min)

        def cw():
            """lista kroków jednej serii (jeden krok). Ćwiczenie jednostronne: JEDEN krok na obie strony (osobne kroki
            lewa/prawa źle się liczyły), cel = powtórzenia × 2, bo zegarek liczy wszystkie; raport dzieli wynik na 2"""
            if not (i.per_side and cfg.get("strony", True)):
                return [k.krok("interval", koniec, ile, opis=o, category=d.category, exercise=d.exerciseName, kg=i.weight_kg)]
            st = {"noga": "nogę", "ręka": "rękę"}.get(i.strona(), "stronę")
            o2 = re.sub(r",?\s*na\s+(każd\w+\s+)?(nog[eęi]|stron[eęy]|r[eę]k[eęi])\b", "", o).strip(" ,")
            o2 = re.sub(r"\s+[—–]\s+", ", ", o2)          # „8–10 powt. — 80 kg” po wycięciu „na nogę” -> „…, 80 kg”
            razem = f"{i.duration_s * 2} s" if i.duration_s else \
                (f"{i.reps_min * 2}–{i.reps_max * 2}" if i.reps_min != i.reps_max else f"{i.reps_max * 2}")
            return [k.krok("interval", koniec, ile * 2, opis=f"Na {st}: {o2} (razem obie: {razem})",
                           category=d.category, exercise=d.exerciseName, kg=i.weight_kg)]
        ile_txt = f"{i.duration_s} s" if i.duration_s else (f"{i.reps_min}–{i.reps_max}" if i.reps_min != i.reps_max else f"{i.reps_max}")
        return cw, d, ile_txt

    sekcje = analizuj(opis)
    po_nazwie = {c.name_pl: c for c in wszystkie_cwiczenia(sekcje)}

    for sek in sekcje:
        for i in sek.items:
            if isinstance(i, TimedBlock):
                typ = "warmup" if sek.kind == "warmup" else "cooldown" if sek.kind == "cooldown" else "interval"
                kroki.append(k.krok(typ, "time", i.seconds, opis=i.text or i.raw))
            elif isinstance(i, WarmupSets):
                d = mapa.znajdz(i.exercise_ref)
                if d.sposob == "nieznane" and nieznane is not None:
                    nieznane.append(i.exercise_ref)
                kat = kat_lawki(po_nazwie[i.exercise_ref]) if i.exercise_ref in po_nazwie else ""
                kat = "" if kat.split()[-1:] and kat.split()[-1] in i.raw else kat
                przejscie(i.exercise_ref, ", ".join(x for x in (f"{i.sets_max} serie rozgrzewkowe", kat, i.note) if x))
                kroki.append(k.serie(i.sets_max, lambda d=d, i=i: [
                    k.krok("interval", "lap.button", opis=f"seria rozgrzewkowa ({i.raw})", category=d.category, exercise=d.exerciseName,
                           kg=ciezar(i.raw)),
                    przerwa("warmup")]))
            elif isinstance(i, Exercise):
                cw, d, ile_txt = cwiczenie(i)
                przejscie(i.name_pl, f"{i.sets}×{ile_txt}" + (f", {w}" if (w := wskazowki(i)) else ""))
                kroki.append(k.serie(i.sets, lambda cw=cw, d=d, rc=sek.rest_class: [*cw(), przerwa(rc, d.rest_s)]))
            elif isinstance(i, Circuit):              # rundy: A, B (, C…) jedno po drugim, przerwa dopiero po rundzie
                cz = [cwiczenie(c) for c in i.exercises]
                rady = "; ".join(f"{c.name_pl}: {w}" for c in i.exercises if (w := wskazowki(c)))
                przejscie(" + ".join(c.name_pl for c in i.exercises), f"{i.rounds} rundy: " +
                          ", ".join(t for _, _, t in cz) + (f" · {rady}" if rady else ""))
                kroki.append(k.serie(i.rounds, lambda cz=cz, i=i, rc=sek.rest_class: [x for cw, _, _ in cz for x in cw()] +
                                     [przerwa(rc, i.rest_s)]))
            elif isinstance(i, RoundRest):
                pass                                    # przerwa bez pary ćwiczeń: przerwy między seriami już są
            elif isinstance(i, Unparsed):
                kroki.append(k.krok("interval", "lap.button", opis=i.raw))
    tytul = zrodlo.get("workoutName") or zrodlo.get("title") or "Trening siłowy"
    znacznik = f"{ZNACZNIK}, src={zrodlo['workoutId']}, hash={hash_opisu(opis)[:16]}"
    return {"workoutName": nazwa_treningu(tytul)[:80], "description": (opis[:900] + "\n\n" + znacznik).strip(),
            "sportType": dict(SPORT), "workoutSegments": [{"segmentOrder": 1, "sportType": dict(SPORT), "workoutSteps": kroki}]}


def nasz(workout):
    """czy trening utworzyła ta usługa (znacznik w opisie) — tylko takie wolno nam usuwać"""
    return ZNACZNIK in (workout.get("description") or "")
