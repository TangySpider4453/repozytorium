import glob
import json
from pathlib import Path

import pytest

from rtg.builder import buduj, nasz, nazwa_treningu

FIX = Path(__file__).parent / "fixtures"
CFG = {"rep_target": "max", "rest_mode": "timed", "przerwy_s": {"main": 180, "accessory": 90, "core": 60, "warmup": 90}}


def zrodlo_dol_b():
    return {"workoutId": 123, "title": "Dół B — martwy ciąg, suwnica i brzuch - 90 min",
            "description": (FIX / "restortrain_dol_b.txt").read_text(encoding="utf-8")}


def kroki_plaskie(kroki):
    for k in kroki:
        yield k
        yield from kroki_plaskie(k.get("workoutSteps", []))


def test_dol_b_kryteria_akceptacji():
    w = buduj(zrodlo_dol_b(), CFG)
    assert w["workoutName"] == "Siłka Dół B"
    assert "auto: restortrain-garmin, src=123" in w["description"] and nasz(w)
    k = w["workoutSegments"][0]["workoutSteps"]
    assert k[0]["stepType"]["stepTypeKey"] == "warmup" and k[0]["endConditionValue"] == 600
    rozgrz = k[2]
    assert rozgrz["type"] == "RepeatGroupDTO" and rozgrz["numberOfIterations"] == 4
    assert rozgrz["workoutSteps"][0]["endCondition"]["conditionTypeKey"] == "lap.button"
    assert rozgrz["workoutSteps"][0]["exerciseName"] == "BARBELL_DEADLIFT"
    przej = [x for x in k if x["type"] == "ExecutableStepDTO" and (x.get("description") or "").startswith("Przygotuj:")]
    assert len(przej) == 9 and przej[1]["description"] == "Przygotuj: Martwy ciąg (4×4–6)"
    assert all(x["endCondition"]["conditionTypeKey"] == "lap.button" and x["stepType"]["stepTypeKey"] == "rest" for x in przej)
    grupy = [x for x in k[3:] if x["type"] == "RepeatGroupDTO"]
    assert len(grupy) == 8
    assert [g["numberOfIterations"] for g in grupy] == [4, 4, 3, 3, 3, 3, 3, 3]
    cw = [g["workoutSteps"][0] for g in grupy]
    assert [c["endConditionValue"] for c in cw] == [6, 10, 10, 12, 12, 15, 12, 12]
    assert all(c["endCondition"]["conditionTypeKey"] == "reps" and c["category"] for c in cw)
    assert [g["workoutSteps"][1]["endConditionValue"] for g in grupy] == [180, 180, 180, 90, 90, 90, 60, 60]
    assert cw[0]["description"] == "4–6 powt., 1-2 powtórzenia w zapasie"
    assert k[-1]["stepType"]["stepTypeKey"] == "cooldown" and k[-1]["endConditionValue"] == 300
    nr = [x["stepOrder"] for x in kroki_plaskie(k)]
    assert len(nr) == len(set(nr))                   # numery kroków unikalne


def test_opcje_min_i_przycisk():
    w = buduj(zrodlo_dol_b(), {**CFG, "rep_target": "min", "rest_mode": "lap_button"})
    g = [x for x in w["workoutSegments"][0]["workoutSteps"] if x["type"] == "RepeatGroupDTO"][1]
    assert not [x for x in buduj(zrodlo_dol_b(), {**CFG, "przejscie": False})["workoutSegments"][0]["workoutSteps"]
                if (x.get("description") or "").startswith("Przygotuj")]
    assert g["workoutSteps"][0]["endConditionValue"] == 4
    assert g["workoutSteps"][1]["endCondition"]["conditionTypeKey"] == "lap.button"


def test_nieznane_cwiczenie_trafia_do_opisu_i_listy():
    nz = []
    w = buduj({"workoutId": 1, "title": "X", "description": "Główne\n- Żonglowanie kettlem 3x10"}, CFG, nieznane=nz)
    c = w["workoutSegments"][0]["workoutSteps"][1]["workoutSteps"][0]
    assert nz == ["Żonglowanie kettlem"] and c["category"] is None and c["description"].startswith("Żonglowanie kettlem")


def test_nazwa():
    assert nazwa_treningu("Push — skos - 80 min") == "Siłka Push"
    assert nazwa_treningu("Full upper — większa objętość i brzuch") == "Siłka Full upper"
    assert nazwa_treningu("Trening") == "Siłka Trening"


@pytest.mark.parametrize("plik", sorted(glob.glob(str(FIX / "restortrain_*.json"))))
def test_ksztalt_krokow_jak_w_garmin(plik):
    """każde pole naszego kroku istnieje w prawdziwym kroku Garmina (ten sam typ wartości albo null)"""
    d = json.loads(Path(plik).read_text(encoding="utf-8"))["workout"]
    wzor = d["workoutSegments"][0]["workoutSteps"][0]
    w = buduj({"workoutId": d["workoutId"], "title": d["workoutName"], "description": d["description"]}, CFG)
    assert set(w) <= set(d) and w["sportType"] == d["sportType"]
    for k in kroki_plaskie(w["workoutSegments"][0]["workoutSteps"]):
        if k["type"] != "ExecutableStepDTO":
            continue
        assert set(k) <= set(wzor), set(k) - set(wzor)
        for pole in ("stepType", "endCondition", "targetType"):
            assert set(k[pole]) <= set(wzor[pole]) | {"displayable"}


def test_ksztalt_jak_trening_referencyjny():
    ref = FIX / "reference_strength_workout.json"
    if not ref.exists():
        pytest.skip("brak treningu referencyjnego (./rtg.sh pobierz-wzorce \"nazwa\")")
    r = json.loads(ref.read_text(encoding="utf-8"))
    rk = list(kroki_plaskie(r["workoutSegments"][0]["workoutSteps"]))
    w = buduj(zrodlo_dol_b(), CFG)
    for typ in ("ExecutableStepDTO", "RepeatGroupDTO"):
        wz = next((x for x in rk if x["type"] == typ), None)
        if wz is None:
            continue
        for k in kroki_plaskie(w["workoutSegments"][0]["workoutSteps"]):
            if k["type"] == typ:
                assert set(k) <= set(wz), (typ, set(k) - set(wz))


def test_rundy_jedna_grupa_przerwa_po_rundzie():
    w = buduj({"workoutId": 5, "title": "Full upper — x", "description": (
        "Barki — 3 rundy naprzemiennie\n- Wyciskanie hantli nad głowę 1x8-10\n- Unoszenie bokiem 1x12-15\n"
        "- 90s odpoczynku po obu ćwiczeniach\n")}, CFG)
    k = w["workoutSegments"][0]["workoutSteps"]
    assert k[0]["description"].startswith("Przygotuj: Wyciskanie hantli nad głowę + Unoszenie bokiem (3 rundy")
    g = k[1]
    assert g["type"] == "RepeatGroupDTO" and g["numberOfIterations"] == 3 and len(k) == 2
    typy = [(x["stepType"]["stepTypeKey"], x["endConditionValue"]) for x in g["workoutSteps"]]
    assert typy == [("interval", 10), ("interval", 15), ("rest", 90)]
