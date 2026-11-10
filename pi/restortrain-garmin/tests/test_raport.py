import json
from pathlib import Path

from rtg.raport import indeksy_fit, plan_z_treningu, raport

D = json.loads((Path(__file__).parent / "fixtures" / "garmin_zrobiony_dol_b.json").read_text(encoding="utf-8"))


def test_indeksy_jak_na_zegarku():
    """wktStepIndex z aktywności: martwy ciąg roboczy = 6, suwnica L/P = 10/11, prostowanie = 20, łydki = 28"""
    p = {x["nazwa"]: x["indeksy"] for x in plan_z_treningu(D["trening"])}
    assert p["Martwy ciąg – rozgrzewka"] == [2] and p["Martwy ciąg"] == [6]
    assert p["Suwnica jednonóż"] == [10, 11] and p["Prostowanie nóg"] == [20] and p["Wspięcia na palce"] == [28]


def test_raport_zrobione_i_niezrobione():
    t, _, minuty = raport(D["aktywnosc"], D["sety"], D["trening"], {})
    assert minuty == 77
    assert "- Martwy ciąg: 6×80 kg, 6×70 kg, 6×70 kg, 6×70 kg (plan: 4×4–6)" in t
    assert "- Bułgary (na nogę): L 10 / P 10 × 30 kg" in t
    assert "- Prostowanie nóg: 12×60 kg, 12×60 kg, 12×60 kg (plan: 3×10–12, 60 kg)" in t
    nz = t.split("Niezrobione:")[1]
    assert "Uginanie nóg" in nz and "Spięcia brzucha na wyciągu" in nz and "Martwy ciąg" not in nz


def test_bez_planu_po_nazwach():
    t, _, _ = raport(D["aktywnosc"], D["sety"], None, {"BARBELL_DEADLIFT": "Martwy ciąg"})
    assert "- Martwy ciąg: 10×50 kg, 15×50 kg, 9×60 kg, 6×80 kg" in t and "Niezrobione" not in t


def test_jednostronne_x2_dzielone():
    from rtg.builder import buduj
    w = buduj({"workoutId": 1, "title": "Dół — x", "description": "Nogi\n- Bułgary 3x8-10 na nogę — 12,5 kg na hantel"}, {})
    w["workoutName"] = "Siłka Dół"
    akt = {"activityName": "Siłka Dół", "startTimeLocal": "2026-11-10 15:00:00", "duration": 600}
    sety = [{"setType": "ACTIVE", "wktStepIndex": 1, "repetitionCount": r, "weight": 12500.0,
             "exercises": [{"name": "DUMBBELL_BULGARIAN_SPLIT_SQUAT"}]} for r in (20, 19)]
    t, _, _ = raport(akt, sety, w, {})
    assert "- Bułgary (na nogę): 10×12,5 kg, 9,5×12,5 kg (plan: 3×8–10, 12,5 kg) — 2 z 3 serii" in t


def test_lista_x2_dzielona_reka_nie():
    from rtg.builder import buduj
    w = buduj({"workoutId": 1, "title": "X", "description": "Brzuch\n- Woodchop 3x12 na stronę\nPlecy\n- Wiosłowanie hantlem 3x8 na stronę"}, {})
    akt = {"activityName": "X", "startTimeLocal": "2026-11-10 15:00:00", "duration": 600}
    sety = [{"setType": "ACTIVE", "wktStepIndex": 1, "repetitionCount": 24, "weight": 10000.0, "exercises": [{"name": "CABLE_WOODCHOP"}]},
            {"setType": "ACTIVE", "wktStepIndex": 5, "repetitionCount": 8, "weight": 12500.0, "exercises": [{"name": "X"}]}]
    t, _, _ = raport(akt, sety, w, {})
    assert "- Woodchop (na stronę): 12×10 kg (plan: 3×12" in t
    assert "- Wiosłowanie hantlem (na rękę): 8×12,5 kg (plan: 3×8" in t       # x2: false -> bez dzielenia
