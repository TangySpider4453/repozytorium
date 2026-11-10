from pathlib import Path

from rtg.mapping import Mapa, bledy_walidacji, oficjalne, wczytaj
from rtg.parser import Exercise, WarmupSets, parsuj

FIX = Path(__file__).parent / "fixtures" / "restortrain_dol_b.txt"


def test_kazdy_wpis_istnieje_na_oficjalnej_liscie():
    assert bledy_walidacji(wczytaj(), oficjalne()) == []


def test_brak_zdublowanych_aliasow():
    widziane = {}
    for w in wczytaj():
        for n in [w["nazwa"], *w.get("aliasy", [])]:
            k = n.lower()
            assert k not in widziane or widziane[k] is w, f"alias {n!r} w dwóch wpisach"
            widziane[k] = w


def test_fixture_wszystkie_cwiczenia_znane():
    m = Mapa()
    s = parsuj(FIX.read_text(encoding="utf-8"))
    cw = [i for x in s for i in x.items if isinstance(i, Exercise)]
    wyniki = {c.name_pl: m.znajdz(c.name_pl) for c in cw}
    assert all(d.sposob != "nieznane" for d in wyniki.values()), wyniki
    assert (wyniki["Martwy ciąg"].category, wyniki["Martwy ciąg"].exerciseName) == ("DEADLIFT", "BARBELL_DEADLIFT")
    assert wyniki["Suwnica jednonóż"].exerciseName == "LEG_PRESS"
    assert wyniki["Unoszenie nóg w zwisie"].exerciseName == "HANGING_LEG_RAISE"
    ws = next(i for x in s for i in x.items if isinstance(i, WarmupSets))
    assert m.znajdz(ws.exercise_ref).exerciseName == "BARBELL_DEADLIFT"      # „martwego ciągu”


def test_nieznane_i_rozmyte():
    m = Mapa()
    assert m.znajdz("Żonglowanie kettlem na jednej ręce").sposob == "nieznane"
    assert m.znajdz("Wyciskanie lezac").sposob in ("dokladne", "rdzen", "rozmyte")
    assert m.znajdz("Przyciąganie drążka z góry").exerciseName == "LAT_PULLDOWN"


def test_wpis_bez_odpowiednika_garmin():
    from rtg.builder import buduj
    from rtg.mapping import bledy_walidacji, oficjalne, wczytaj
    mapa = Mapa([{"nazwa": "prostowanie nóg", "category": None, "exerciseName": None}])   # wpis „brak odpowiednika”
    assert mapa.znajdz("Prostowanie nóg").sposob == "brak"
    assert not bledy_walidacji(wczytaj(), oficjalne()) and not bledy_walidacji(mapa.wpisy, oficjalne())
    w = buduj({"workoutId": 1, "title": "X", "description": "Nogi\n- Prostowanie nóg 3x10-12"}, {"przejscie": False}, mapa, nieznane=(nz := []))
    c = w["workoutSegments"][0]["workoutSteps"][0]["workoutSteps"][0]
    assert c["category"] is None and c["description"].startswith("Prostowanie nóg: 10–12") and nz == []
