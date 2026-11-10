"""prawdziwe treningi RestOrTrain pobrane z Garmin Connect (./rtg.sh pobierz-wzorce): wszystko rozpoznane"""
import glob
import json
from pathlib import Path

import pytest

from rtg.mapping import Mapa
from rtg.parser import Exercise, Unparsed, WarmupSets, parsuj

PLIKI = sorted(glob.glob(str(Path(__file__).parent / "fixtures" / "restortrain_*.json")))


@pytest.mark.parametrize("plik", PLIKI)
def test_realny_trening(plik):
    d = json.loads(Path(plik).read_text(encoding="utf-8"))
    assert d["workout"]["consumerName"] == "RestOrTrain"
    s = parsuj(d["workout"]["description"])
    assert not [i.raw for x in s for i in x.items if isinstance(i, Unparsed)]
    m = Mapa()
    nazwy = [i.name_pl for x in s for i in x.items if isinstance(i, Exercise)] + \
            [i.exercise_ref for x in s for i in x.items if isinstance(i, WarmupSets)]
    assert [n for n in nazwy if m.znajdz(n).sposob == "nieznane"] == []
