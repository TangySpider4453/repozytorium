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
