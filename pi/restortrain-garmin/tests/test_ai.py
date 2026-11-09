import json

import pytest

from rtg import ai, parser
from rtg.builder import buduj
from rtg.parser import Circuit, Exercise, WarmupSets

ODP = {"sekcje": [
    {"nazwa": "Rozgrzewka", "rodzaj": "warmup", "przerwy": "warmup", "elementy": [
        {"typ": "czas", "sekundy": 480, "tekst": "mobilizacja barków"},
        {"typ": "serie_rozgrzewkowe", "serie": 2, "cwiczenie": "Wyciskanie hantli na skosie dodatnim 30°", "kg": 12.5, "uwagi": ""}]},
    {"nazwa": "Klatka i plecy", "rodzaj": "main", "przerwy": "main", "elementy": [
        {"typ": "rundy", "rundy": 3, "przerwa_s": 90, "cwiczenia": [
            {"typ": "cwiczenie", "nazwa": "Wyciskanie hantli na skosie dodatnim 30°", "serie": 1, "powt_min": 8, "powt_max": 10,
             "jednostronne": False, "kg": 17.5, "uwagi": "17,5 kg na hantel"},
            {"typ": "cwiczenie", "nazwa": "Wiosłowanie hantlem", "serie": 1, "powt_min": 8, "powt_max": 10,
             "jednostronne": True, "strona": "ręka", "kg": None, "uwagi": "dobierz ciężar"}]}]},
    {"nazwa": "Nogi", "rodzaj": "main", "przerwy": "main", "elementy": [
        {"typ": "cwiczenie", "nazwa": "Przysiad ze sztangą", "serie": 4, "powt_min": 6, "powt_max": 8,
         "jednostronne": False, "kg": 70, "uwagi": "25 kg na stronę plus sztanga"}]}]}


def test_na_sekcje():
    s = ai.na_sekcje(ODP)
    assert isinstance(s[0].items[1], WarmupSets) and s[0].items[1].note == "12,5 kg"
    c = s[1].items[0]
    assert isinstance(c, Circuit) and c.rounds == 3 and c.rest_s == 90
    assert c.exercises[1].per_side and c.exercises[1].strona() == "ręka" and c.exercises[1].weight_kg is None
    p = s[2].items[0]
    assert isinstance(p, Exercise) and p.weight_kg == 70 and not p.per_side


def test_zle_odpowiedzi_odrzucone():
    for zle in ({"sekcje": []}, {"sekcje": [{"elementy": [{"typ": "cwiczenie", "nazwa": "", "serie": 3}]}]},
                {"sekcje": [{"elementy": [{"typ": "cwiczenie", "nazwa": "X", "serie": 99, "powt_max": 5}]}]}, {}):
        with pytest.raises(Exception):
            ai.na_sekcje(zle)


def test_pamiec_i_zapas(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "CACHE", tmp_path / "c.json")
    wywolania = []
    assert ai.analizuj("opis", pytaj=lambda o: wywolania.append(o) or ODP) is not None
    assert ai.analizuj("opis", pytaj=lambda o: wywolania.append(o) or ODP) is not None
    assert len(wywolania) == 1                                   # drugi raz z pamięci
    assert ai.analizuj("inny", pytaj=lambda o: {"bzdura": 1}) is None


def test_budowa_z_ai(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "CACHE", tmp_path / "c.json")
    monkeypatch.setattr(ai, "_zapytaj", lambda o: ODP)
    monkeypatch.setitem(parser.AI, "wlaczone", True)
    monkeypatch.setattr(ai.analizuj, "__defaults__", (lambda o: ODP,))
    k = buduj({"workoutId": 1, "title": "X", "description": "cokolwiek"}, {})["workoutSegments"][0]["workoutSteps"]
    opisy = [x.get("description") for x in k]
    assert "Przygotuj: Wyciskanie hantli na skosie dodatnim 30° (2 serie rozgrzewkowe, 12,5 kg)" in opisy
    runda = [x for x in k if x["type"] == "RepeatGroupDTO"][1]["workoutSteps"]
    assert [x.get("description") for x in runda][:3] == ["8–10 powt., ławka 30°, 17,5 kg na hantel",
                                                         "Na rękę: 8–10 powt., dobierz ciężar", None]
    assert [x for x in k if x["type"] == "RepeatGroupDTO"][2]["workoutSteps"][0]["weightValue"] == 70000.0
