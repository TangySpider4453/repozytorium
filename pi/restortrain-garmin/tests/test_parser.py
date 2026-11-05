from pathlib import Path

from rtg.parser import Exercise, TimedBlock, Unparsed, WarmupSets, normalizuj, parsuj, wyglada_na_silowy

FIX = Path(__file__).parent / "fixtures" / "restortrain_dol_b.txt"


def test_fixture_dol_b():
    s = parsuj(FIX.read_text(encoding="utf-8"))
    assert [x.name for x in s] == ["Rozgrzewka", "Główne ćwiczenia", "Akcesoria nóg", "Brzuch", "Schłodzenie"]
    assert [x.kind for x in s] == ["warmup", "main", "main", "main", "cooldown"]
    assert [x.rest_class for x in s] == ["warmup", "main", "accessory", "core", "cooldown"]
    rozgrz = s[0].items
    assert rozgrz[0] == TimedBlock(raw="10m mobilizacji bioder i stawów skokowych", seconds=600, kind="warmup",
                                   text="mobilizacji bioder i stawów skokowych")
    assert rozgrz[1] == WarmupSets(raw="3-4 serie wstępne martwego ciągu", sets_min=3, sets_max=4, exercise_ref="martwego ciągu")
    mc = s[1].items[0]
    assert mc == Exercise(raw="Martwy ciąg 4x4-6, 1-2 powtórzenia w zapasie", name_pl="Martwy ciąg", sets=4, reps_min=4,
                          reps_max=6, per_side=False, note="1-2 powtórzenia w zapasie")
    suwnica = s[1].items[1]
    assert (suwnica.name_pl, suwnica.sets, suwnica.reps_min, suwnica.reps_max, suwnica.per_side) == ("Suwnica jednonóż", 4, 8, 10, True)
    cw = [i for x in s for i in x.items if isinstance(i, Exercise)]
    assert len(cw) == 8
    assert [c.sets for c in cw] == [4, 4, 3, 3, 3, 3, 3, 3]
    assert s[4].items[0].seconds == 300 and s[4].items[0].kind == "cooldown"
    assert not any(isinstance(i, Unparsed) for x in s for i in x.items)


def test_formaty_serii():
    s = parsuj("Trening\n- Wyciskanie leżąc 4x8\n- Przysiad 3 x 10\n- Wiosłowanie 4×8 na rękę\n- Plank 3x30s\n- Wznosy 2x1min")
    e = s[0].items
    assert (e[0].sets, e[0].reps_min, e[0].reps_max) == (4, 8, 8)
    assert (e[1].name_pl, e[1].sets, e[1].reps_max) == ("Przysiad", 3, 10)
    assert (e[2].sets, e[2].reps_max, e[2].per_side) == (4, 8, True)
    assert (e[3].name_pl, e[3].sets, e[3].duration_s, e[3].reps_max) == ("Plank", 3, 30, None)
    assert e[4].duration_s == 60


def test_minuty_nie_metry_i_sekundy():
    s = parsuj("Rozgrzewka\n- 10 min rowerka\n- 45s pajacyków\nCool down\n- 5m rozciągania")
    assert s[0].items[0].seconds == 600 and s[0].items[1].seconds == 45
    assert s[1].kind == "cooldown" and s[1].items[0].seconds == 300


def test_linia_nieczytelna_nie_psuje_reszty(caplog):
    s = parsuj("Główne\n- coś dziwnego bez serii\n- Martwy ciąg 3x5")
    assert isinstance(s[0].items[0], Unparsed)
    assert isinstance(s[0].items[1], Exercise)
    assert "nie rozumiem" in caplog.text


def test_bez_naglowka_i_rozpoznanie():
    assert parsuj("- Podciąganie 4x6")[0].name == "Trening"
    assert wyglada_na_silowy(FIX.read_text(encoding="utf-8"))
    assert not wyglada_na_silowy("Bieg spokojny 45 min w strefie 2")


def test_normalizacja():
    assert normalizuj("  Spięcia  BRZUCHA na wyciągu ") == "spiecia brzucha na wyciagu"
    assert normalizuj("Martwy ciąg, łydki") == "martwy ciag, lydki"


def test_formy_z_prawdziwych_treningow():
    s = parsuj("Rozgrzewka\n- 8-10m mobilizacji barków i łopatek\n- 2 lekkie serie wyciskania hantli\n- Lekkie serie wstępne przysiadu\n"
               "- 2 lekkie serie pierwszego ćwiczenia\nGłówne\n- Wyciskanie hantli na skosie dodatnim 5x6-8")
    r = s[0].items
    assert isinstance(r[0], TimedBlock) and r[0].seconds == 600
    assert isinstance(r[1], WarmupSets) and (r[1].sets_max, r[1].exercise_ref) == (2, "Wyciskanie hantli na skosie dodatnim")
    assert isinstance(r[2], WarmupSets) and (r[2].sets_max, r[2].exercise_ref) == (2, "przysiadu")
    assert isinstance(r[3], WarmupSets) and r[3].exercise_ref == "Wyciskanie hantli na skosie dodatnim"
