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
