"""Plan treningów od Claude na najbliższe dni → tabela plan → (automatycznie) Garmin. Niezmienione treningi zostają
(Claude zwraca `zostaw_id`), więc na zegarku nic nie miga bez powodu."""
import fcntl
import json
import logging
from datetime import date, timedelta

from . import ai, baza, budowa, cel, config, kontekst, tierlista

log = logging.getLogger(__name__)

PROSTY = {"type": "object", "properties": {
    "rodzaj": {"type": "string", "enum": ["rozgrzewka", "praca", "odpoczynek", "schlodzenie", "przerwa", "cwiczenie"]},
    "czas_min": {"type": "number"}, "dystans_km": {"type": "number"},
    "cel": {"type": "string", "enum": ["brak", "strefa_tetna", "tetno", "moc", "strefa_mocy", "tempo", "kadencja"]},
    "od": {"type": "number"}, "do": {"type": "number"}, "strefa": {"type": "integer"},
    "nazwa": {"type": "string"}, "garmin": {"type": "string"}, "serie": {"type": "integer"}, "powt": {"type": "integer"},
    "czas_s": {"type": "integer"}, "kg": {"type": "number"}, "przerwa_s": {"type": "integer"}, "opis": {"type": "string"}},
    "required": ["rodzaj"]}
KROK = {"type": "object", "properties": {**PROSTY["properties"],
                                         "rodzaj": {"type": "string", "enum": PROSTY["properties"]["rodzaj"]["enum"] + ["powtorz"]},
                                         "razy": {"type": "integer"}, "kroki": {"type": "array", "items": PROSTY}},
        "required": ["rodzaj"]}
SCHEMAT = {"type": "object", "properties": {
    "komentarz": {"type": "string", "description": "2-4 zdania: co i dlaczego (to idzie w powiadomieniu)"},
    "treningi": {"type": "array", "items": {"type": "object", "properties": {
        "zostaw_id": {"type": "integer", "description": "id istniejącego treningu, który zostaje bez zmian"},
        "dzien": {"type": "string"}, "sport": {"type": "string", "enum": ["rower", "bieg", "silka", "odpoczynek"]},
        "tytul": {"type": "string"}, "opis": {"type": "string"},
        "opcjonalny": {"type": "boolean", "description": "trening do wyboru (np. lekki bieg w dzień wolny)"},
        "cel": {"type": "string", "description": "po co ta jednostka (adaptacja) i jak ją wykonać — 1-2 zdania"},
        "kroki": {"type": "array", "items": KROK}}, "required": ["dzien", "sport", "tytul"]}},
    "uzasadnienie": {"type": "string", "description": "jak plan realizuje fazę makrocyklu i zasady z bazy wiedzy"}},
    "required": ["komentarz", "treningi", "uzasadnienie"]}

ZASADY = """ZASADY FORMATU PLANU:
- Każdy dzień w zakresie dostaje wpis: trening(i) albo {"sport":"odpoczynek"} (z krótkim opisem, np. regeneracja).
- Istniejący trening bez zmian: zwróć {"zostaw_id": <id>, "dzien", "sport", "tytul"} (bez kroków). Zmieniaj tylko,
  gdy dane (sen, HRV, gotowość, zmęczenie, wykonanie) albo prośba Antka tego wymagają.
- Trening OPCJONALNY (np. „jak masz ochotę, lekki bieg 15–20 min” w dzień wolny) to OSOBNY wpis z krokami
  i "opcjonalny": true (idzie na zegarek z nazwą „Opcjonalny: …”), a nie tylko wzmianka w opisie. Dzień wolny dalej ma
  wpis {"sport":"odpoczynek"}. Do obciążenia tygodnia liczy się go jako „może być”, więc ma być lekki.
- tytul ≤ 40 znaków, czytelny na zegarku (np. "Rower Z2 2h", "Bieg 6×400 m", "Siłka Dół A"). opis: cel treningu +
  wskazówki (≤ 600 znaków).
- Rower/bieg: kroki rozgrzewka / praca / odpoczynek / schlodzenie z czas_min albo dystans_km; pętla
  {"rodzaj":"powtorz","razy":N,"kroki":[...]}. Cel: "strefa_tetna"+"strefa" (1-5, strefy z Garmina) — domyślnie,
  ALE gdy STAŁE WYMAGANIA podają własne strefy Antka — "tetno" od/do w bpm i "moc" od/do w W z JEGO stref;
  "moc" od/do w W (rower, gdy znane FTP); "tempo" od/do w SEKUNDACH na km (bieg); "kadencja" od/do; "brak".
- Siłka: rozgrzewka (czas_min), potem {"rodzaj":"cwiczenie","nazwa": polska nazwa (najlepiej z listy Antka),
  "garmin":"KATEGORIA/NAZWA" z listy Garmina, "serie","powt" albo "czas_s","kg" (gdy znasz z historii),
  "przerwa_s"}. Superserie/obwody: "powtorz" z ćwiczeniami w środku (bez "serie" w środku). Na koniec schlodzenie.
- Ciężary dobieraj z historii siłowni (serie z ostatnich treningów). Gdy brak historii — bez kg.
- Rower z mocą: własne strefy mocy Antka w STAŁYCH WYMAGANIACH → bierz W z nich; inaczej (znane FTP) % FTP wg stref
  Coggana z bazy wiedzy (Z2 = 56–75% FTP itd.).
- STAŁE WYMAGANIA ANTKA są ważniejsze niż faza makrocyklu: siłka GÓRA tyle razy w tygodniu, ile podał — zawsze
  jako Push / Pull / Full Upper (tytuły „Siłka Push…”, „Siłka Pull…”, „Siłka Full Upper…”); brzuch na końcu KAŻDEJ
  siłki (także nóg), skośne/boczne max 1 w tygodniu; nogi dokładasz wg bazy wiedzy, nie kosztem góry.
- Trzymaj się BIEŻĄCEJ FAZY makrocyklu (godziny, akcenty, siłka/bieg w tygodniu, rytm tygodni lżejszych) i zasad
  z bazy wiedzy (rozkład intensywności, progresja bez skoków, 48 h po ciężkich nogach, sen/HRV). "cel" każdej jednostki
  = jaką adaptację buduje. Brak wiarygodnego FTP/progów → zaplanuj test zgodnie z protokołem z bazy.
"""


def _lista_cwiczen():
    antka = "\n".join(f"- {e['nazwa']}: {e.get('category')}/{e.get('exerciseName')}" for e in
                      json.loads((budowa.ZASOBY / "cwiczenia_antka.json").read_text(encoding="utf-8")) if e.get("category"))
    garmin = "\n".join(f"{k}: {', '.join(v)}" for k, v in budowa.garmin_cwiczenia().items())
    return f"ĆWICZENIA ANTKA (polska nazwa: Garmin):\n{antka}\n\nWSZYSTKIE ĆWICZENIA GARMIN (KATEGORIA: nazwy):\n{garmin}"


def _istniejace(db, od, do):
    return [dict(r) for r in db.execute(
        "SELECT * FROM plan WHERE dzien BETWEEN ? AND ? AND stan NOT IN ('usuniety','do_usuniecia') ORDER BY dzien, id",
        (od, do))]


def zrobione_dzis(db):
    return [r[0] for r in db.execute("SELECT typ FROM aktywnosci WHERE dzien=?", (date.today().isoformat(),))]


def zaplanuj(powod="", prosba="", dni=None, pytaj=False):
    """-> dict(komentarz, zmiany) albo None (plan już się liczy)"""
    config.DANE.mkdir(parents=True, exist_ok=True)
    f = open(config.DANE / "plan.lock", "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return None
    db = baza.polacz()
    u = config.ustawienia()
    dni = dni or int(u["plan_dni"])
    dzis = date.today()
    od = dzis.isoformat()
    if zrobione_dzis(db):                     # dziś już trenował: dzisiejszego nie ruszamy
        od = (dzis + timedelta(days=1)).isoformat()
    do = (dzis + timedelta(days=dni - 1)).isoformat()
    ist = _istniejace(db, od, do)
    ist_txt = "\n".join(json.dumps({"id": r["id"], "dzien": r["dzien"], "sport": r["sport"], "tytul": r["tytul"],
                                    "opis": r["opis"], "kroki": json.loads(r["kroki"] or "[]")}, ensure_ascii=False)
                        for r in ist) or "(brak)"
    m = cel.makrocykl(db)
    prompt = "\n\n".join(x for x in [
        "BAZA WIEDZY (zasady treningu ze źródeł):\n" + cel.wiedza(u["sporty"]),
        kontekst.pelny(db),
        _lista_cwiczen() if "silka" in u["sporty"] else "",
        tierlista.tekst_do_planu(u) if "silka" in u["sporty"] else "",
        f"OBECNY PLAN W ZAKRESIE {od}..{do}:\n{ist_txt}",
        ZASADY,
        f"ZADANIE: ułóż plan na dni {od} .. {do} (sporty: {', '.join(u['sporty'])}). Powód: {powod or 'aktualizacja'}."
        + (f"\nPROŚBA ANTKA: {prosba}" if prosba else "")
        + ("\nDziś już był trening — dzisiejszego dnia nie planuj." if od != dzis.isoformat() else "")
        + "\nW 'komentarz' i 'uzasadnienie' mów o dniach słowami względem dziś (dziś / jutro / w piątek), bez dat, "
          "i pilnuj, którego dnia dotyczy dany trening — nie pisz „dziś” o treningu zaplanowanym na jutro."
        + ("\nTRYB KOREKTY: zmieniaj tylko to, co wynika z dzisiejszej oceny (sen, HRV, regeneracja, ostatnie treningi); "
           "resztę zostaw przez zostaw_id. Drobne zmiany (krócej, lżej, inna strefa, mniej serii) wchodzą od razu. "
           "Usunięcie albo dodanie jednostki wymaga zgody Antka — wtedy w 'komentarz' napisz wprost dlaczego "
           "(np. słaby sen, niski HRV) i co proponujesz zamiast. Nie usuwaj z ostrożności, gdy dane są w normie."
           if pytaj else "")] if x)
    w = ai.zapytaj(prompt, SCHEMAT, effort="high", limit_s=600, ciezki=True)
    problemy = kontrola(db, w.get("treningi") or [], ist, cel.faza_teraz(m), cel.ftp(db))
    if problemy:                              # jedna poprawka: Claude dostaje konkretne zarzuty
        log.info("kontrola planu: %s", problemy)
        w = ai.zapytaj(prompt + "\n\nTWÓJ PIERWSZY PLAN:\n" + json.dumps(w, ensure_ascii=False) +
                       "\n\nKONTROLA WYKRYŁA PROBLEMY:\n- " + "\n- ".join(problemy) +
                       "\nPopraw plan (albo uzasadnij w 'uzasadnienie', dlaczego to celowe).", SCHEMAT, effort="high", limit_s=600, ciezki=True)
        problemy = kontrola(db, w.get("treningi") or [], ist, cel.faza_teraz(m), cel.ftp(db))
    wstrzymaj = dni_duzych_zmian(w.get("treningi") or [], ist) if pytaj else set()
    zmiany, prop = zastosuj(db, w.get("treningi") or [], od, do, ist, powod, wstrzymaj)
    if prop:
        prop.update(powod=powod, komentarz=w.get("komentarz", ""), kiedy=baza.teraz(), do=max(wstrzymaj))
        baza.ustaw_kv(db, "propozycja_planu", prop)
    baza.ustaw_kv(db, "plan_uzasadnienie", {"tekst": w.get("uzasadnienie", ""), "uwagi": problemy, "kiedy": baza.teraz()})
    log.info("plan: %s", zmiany)
    return {"komentarz": w.get("komentarz", ""), "zmiany": zmiany, "od": od, "do": do, "propozycja": prop,
            "uzasadnienie": w.get("uzasadnienie", ""), "uwagi": problemy}


def _usun(db, r):
    db.execute("UPDATE plan SET stan=?, zmieniono=? WHERE id=?",
               ("do_usuniecia" if r["workout_id"] else "usuniety", baza.teraz(), r["id"]))
    return f"− {kontekst.slownie(r['dzien'])}: {r['tytul']}"


def _dodaj(db, t, zrodlo):
    if t.get("opcjonalny") and t["sport"] != "odpoczynek" and not t["tytul"].lower().startswith("opcjonal"):
        t["tytul"] = "Opcjonalny: " + t["tytul"]       # tak go widać w Garminie i w apce
    if t["sport"] != "odpoczynek":
        try:
            budowa.buduj(t)                            # walidacja przed zapisem
        except Exception as ex:
            log.warning("odrzucony trening %s: %s", t.get("tytul"), ex)
            return f"⚠️ {kontekst.slownie(t.get('dzien') or '')} {t.get('tytul')}: błąd planu ({ex})"
    opis = t.get("opis", "") + (f"\nCel: {t['cel']}" if t.get("cel") else "")
    db.execute("INSERT INTO plan (dzien, sport, tytul, opis, kroki, hash, stan, utworzono, zmieniono, zrodlo) "
               "VALUES (?,?,?,?,?,?,?,?,?,?)",
               (t["dzien"], t["sport"], t["tytul"][:60], opis, json.dumps(t.get("kroki") or [], ensure_ascii=False),
                budowa.hash_treningu(t), "nowy" if t["sport"] != "odpoczynek" else "w_apce", baza.teraz(), baza.teraz(),
                zrodlo[:200]))
    return f"+ {kontekst.slownie(t['dzien'])}: {t['tytul']}" + (f" (~{budowa.czas_min(t)} min)" if t["sport"] != "odpoczynek" else "")


def dni_duzych_zmian(treningi, ist):
    """dni z usunięciem albo dodaniem jednostki (dzień+sport). Zmiana treści/długości/intensywności tej samej
    jednostki = mała. Uzupełnianie pustego dnia i trening opcjonalny = małe."""
    po_id = {r["id"]: r for r in ist}
    zostaja = {t["zostaw_id"] for t in treningi if t.get("zostaw_id") in po_id}
    nowe = [t for t in treningi if t.get("zostaw_id") not in po_id]
    ist_ds = {(r["dzien"], r["sport"]) for r in ist if r["sport"] != "odpoczynek"}
    nowe_ds = {(t.get("dzien"), t.get("sport")) for t in nowe if t.get("sport") != "odpoczynek"}
    dni_ist = {r["dzien"] for r in ist}
    dni = {r["dzien"] for r in ist if r["id"] not in zostaja and r["sport"] != "odpoczynek"
           and (r["dzien"], r["sport"]) not in nowe_ds}
    dni |= {t["dzien"] for t in nowe if t.get("sport") != "odpoczynek" and not t.get("opcjonalny")
            and t.get("dzien") in dni_ist and (t["dzien"], t["sport"]) not in ist_ds}
    return dni


def zastosuj(db, treningi, od, do, ist, zrodlo, wstrzymaj_dni=()):
    """wprowadza plan; zmiany w dniach z wstrzymaj_dni nie są wprowadzane -> (zmiany, propozycja albo None)"""
    zostaja = {t["zostaw_id"] for t in treningi if t.get("zostaw_id")}
    po_id = {r["id"]: r for r in ist}
    zmiany, prop = [], {"usun": [], "dodaj": [], "zmiany": []}
    for r in ist:
        if r["id"] not in zostaja:
            if r["dzien"] in wstrzymaj_dni:
                prop["usun"].append(r["id"])
                prop["zmiany"].append(f"− {kontekst.slownie(r['dzien'])}: {r['tytul']}")
            else:
                zmiany.append(_usun(db, r))
    for t in treningi:
        if t.get("zostaw_id") in po_id or not (od <= (t.get("dzien") or "") <= do):
            continue
        if t["dzien"] in wstrzymaj_dni:
            prop["dodaj"].append(t)
            prop["zmiany"].append(f"+ {kontekst.slownie(t['dzien'])}: {t['tytul']}" + (f" (~{budowa.czas_min(t)} min)" if t["sport"] != "odpoczynek" else ""))
        else:
            zmiany.append(_dodaj(db, t, zrodlo))
    db.commit()
    return zmiany, (prop if prop["zmiany"] else None)


def propozycja(db):
    """czekająca duża zmiana planu (do decyzji Antka); przeterminowana znika"""
    p = baza.kv(db, "propozycja_planu")
    if p and p.get("do", "") < date.today().isoformat():
        baza.ustaw_kv(db, "propozycja_planu", None)
        return None
    return p


def zdecyduj(db, zmienic, dlaczego=""):
    """Antek zatwierdza (zmienic=True) albo odrzuca dużą zmianę -> lista wprowadzonych zmian"""
    p = propozycja(db)
    if not p:
        return []
    baza.ustaw_kv(db, "propozycja_planu", None)
    zmiany = []
    dzis = date.today().isoformat()
    if zmienic:
        for rid in p["usun"]:
            r = db.execute("SELECT * FROM plan WHERE id=? AND stan NOT IN ('usuniety','do_usuniecia')", (rid,)).fetchone()
            if r and r["dzien"] >= dzis:
                zmiany.append(_usun(db, dict(r)))
        for t in p["dodaj"]:
            if t.get("dzien", "") >= dzis:
                zmiany.append(_dodaj(db, t, "decyzja Antka: " + p.get("powod", "")))
        db.commit()
    pm = baza.kv(db, "pamiec_trenera", []) or []
    pm.append(f"{dzis}: propozycja po ocenie snu ({'; '.join(p['zmiany'][:4])}) — Antek "
              + ("ZGODZIŁ SIĘ" if zmienic else "ODRZUCIŁ, plan bez zmian") + (f" ({dlaczego})" if dlaczego else ""))
    baza.ustaw_kv(db, "pamiec_trenera", pm[-60:])
    return zmiany


def braki(db, dni=None):
    """dni w najbliższym zakresie bez żadnego wpisu planu"""
    dni = dni or int(config.ustawienia()["plan_dni"])
    dzis = date.today()
    zakres = [(dzis + timedelta(days=i)).isoformat() for i in range(1, dni)]
    jest = {r[0] for r in db.execute("SELECT DISTINCT dzien FROM plan WHERE dzien BETWEEN ? AND ? AND stan NOT IN "
                                     "('usuniety','do_usuniecia')", (zakres[0], zakres[-1]))} if zakres else set()
    return [d for d in zakres if d not in jest]


def _ciezki(t, ftp):
    """jednostka intensywna: strefa ≥ 4, moc ≥ 90% FTP, tempo biegowe, sprinty/VO2; siłka z kg = ciężka dla nóg"""
    def kroki(ks):
        for k in ks or []:
            yield k
            yield from kroki(k.get("kroki"))
    prog_hr = config.ustawienia().get("tetno_ciezkie")     # bpm od którego jednostka jest intensywna (np. Z4 Antka)
    for k in kroki(t.get("kroki")):
        if k.get("cel") in ("strefa_tetna", "strefa_mocy") and (k.get("strefa") or 0) >= 4:
            return True
        if k.get("cel") == "tetno" and prog_hr and (k.get("od") or 0) >= prog_hr:
            return True
        if k.get("cel") == "moc" and ftp and (k.get("od") or 0) >= 0.9 * ftp:
            return True
        if k.get("cel") == "tempo" and k.get("rodzaj") == "praca" and t.get("sport") == "bieg" and (k.get("czas_min") or 99) < 15:
            return True
    return False


def _godz_tyg_ostatnie(db, tygodnie=4):
    od = (date.today() - timedelta(weeks=tygodnie)).isoformat()
    s = sum((baza.rozpakuj(r[0]) or {}).get("duration") or 0 for r in
            db.execute("SELECT dane FROM aktywnosci WHERE dzien >= ? AND dzien < ?", (od, date.today().isoformat())))
    return s / 3600 / tygodnie


GORA = {"BENCH_PRESS", "SHOULDER_PRESS", "ROW", "PULL_UP", "TRICEPS_EXTENSION", "CURL", "LATERAL_RAISE", "SHRUG",
        "FLYE", "PUSH_UP", "CHEST_PRESS", "REVERSE_FLY", "SHOULDER_STABILITY"}
NOGI = {"SQUAT", "DEADLIFT", "LUNGE", "LEG_CURL", "CALF_RAISE", "HIP_RAISE", "LEG_PRESS", "HIP_STABILITY", "HIP_SWING",
        "OLYMPIC_LIFT", "PLYO"}


BRZUCH = {"CRUNCH", "LEG_RAISE", "CORE", "PLANK", "SIT_UP", "CHOP"}


def _kroki(ks):
    for k in ks or []:
        yield k
        yield from _kroki(k.get("kroki"))


def partia(t):
    """'gora' / 'nogi' / None dla siłki — po kategoriach Garmina ćwiczeń (i tytule)"""
    if t.get("sport") != "silka":
        return None
    g = n = 0
    def kroki(ks):
        for k in ks or []:
            yield k
            yield from kroki(k.get("kroki"))
    for k in kroki(t.get("kroki")):
        kat = (k.get("garmin") or "").split("/")[0].upper()
        g += kat in GORA
        n += kat in NOGI
    tyt = (t.get("tytul") or "").lower()
    if g == n:
        return "gora" if any(x in tyt for x in ("góra", "gora", "upper", "push", "pull", "plecy", "barki", "klat")) \
            else "nogi" if any(x in tyt for x in ("nogi", "dół", "dol", "lower", "legs")) else None
    return "gora" if g > n else "nogi"


def kontrola(db, treningi, ist, faza, ftp):
    """twarde reguły z bazy wiedzy sprawdzane kodem -> lista problemów (pusta = OK)"""
    po_id = {r["id"]: r for r in ist}
    pelne = []
    for t in treningi:
        if t.get("zostaw_id") in po_id:
            r = po_id[t["zostaw_id"]]
            t = {"dzien": r["dzien"], "sport": r["sport"], "tytul": r["tytul"], "kroki": json.loads(r["kroki"] or "[]")}
        pelne.append(t)
    pelne.sort(key=lambda t: t.get("dzien", ""))
    tren = [t for t in pelne if t.get("sport") != "odpoczynek"]
    p = []
    godz = sum(budowa.czas_min(t) for t in tren) / 60
    sr = _godz_tyg_ostatnie(db)
    if sr > 1 and godz > sr * 1.3 and godz - sr > 1.5:
        p.append(f"objętość planu {godz:.1f} h vs średnio {sr:.1f} h/tydz. z 4 tygodni (+{(godz / sr - 1) * 100:.0f}%) — za duży skok")
    if faza:
        if godz > faza["godziny_tyg_do"] * 1.15:
            p.append(f"{godz:.1f} h powyżej widełek fazy {faza['nazwa']} ({faza['godziny_tyg_od']}-{faza['godziny_tyg_do']} h)")
    ciezkie = [t for t in tren if _ciezki(t, ftp)]
    if len(ciezkie) > 3:
        p.append(f"{len(ciezkie)} jednostek intensywnych w tygodniu ({', '.join(t['tytul'] for t in ciezkie)}) — zwykle max 2-3")
    dni_ciezkie = sorted({t["dzien"] for t in ciezkie})
    for a, b in zip(dni_ciezkie, dni_ciezkie[1:]):
        if (date.fromisoformat(b) - date.fromisoformat(a)).days == 1:
            p.append(f"intensywne dzień po dniu: {a} i {b}")
    nogi = sorted({t["dzien"] for t in tren if t["sport"] == "silka" and any(
        (k.get("kg") and any(x in (k.get("nazwa") or "").lower() for x in ("przysiad", "martwy", "suwnica", "wykrok", "bułgar", "rdl")))
        for k in t.get("kroki") or [])})
    for d in nogi:
        nast = (date.fromisoformat(d) + timedelta(days=1)).isoformat()
        if nast in dni_ciezkie:
            p.append(f"ciężkie nogi na siłowni {d}, a następnego dnia ({nast}) intensywny trening — potrzebne ~48 h")
    gora_tyg = int(config.ustawienia().get("gora_tyg") or 0)
    dni = {t.get("dzien") for t in pelne if t.get("dzien")}
    if gora_tyg and len(dni) >= 5:            # STAŁE WYMAGANIE Antka: góra N× w tygodniu (opcjonalne się nie liczą)
        chce = round(gora_tyg * len(dni) / 7)
        gora = [t for t in tren if partia(t) == "gora" and not t.get("opcjonalny")
                and not (t.get("tytul") or "").lower().startswith("opcjonal")]
        if len(gora) < chce:
            p.append(f"siłka GÓRA {len(gora)}× na {len(dni)} dni, a Antek wymaga {gora_tyg}× w tygodniu (tu min. {chce}×) "
                     "— to stałe wymaganie, dodaj sesje góry")
        if gora_tyg >= 3 and len(dni) >= 6:
            tyt = " ".join((t.get("tytul") or "").lower() for t in gora)
            brak = [n for n, x in (("Push", "push"), ("Pull", "pull"), ("Full Upper", "full")) if x not in tyt]
            if brak:
                p.append("góra ma być jako Push, Pull i Full Upper — brakuje: " + ", ".join(brak))
    u = config.ustawienia()
    nogi_tyg = int(u.get("nogi_tyg") or 0)
    if nogi_tyg and len(dni) >= 6:
        dol = [t for t in tren if partia(t) == "nogi" and not t.get("opcjonalny")]
        if len(dol) < nogi_tyg:
            p.append(f"siłka NOGI {len(dol)}×, a Antek ma {nogi_tyg}× w tygodniu (Dół A i Dół B)")
    for wd in u.get("dni_tylko_nogi") or []:     # np. wtorek: tylko Dół A (plan lekcji)
        dzien_t = [t for t in tren if date.fromisoformat(t["dzien"]).weekday() == wd]
        if dzien_t and any(partia(t) != "nogi" for t in dzien_t):
            p.append(f"{['pon', 'wt', 'śr', 'czw', 'pt', 'sob', 'ndz'][wd]}: Antek ma wtedy czas TYLKO na siłkę nóg "
                     "(bez roweru/biegu/góry) — " + ", ".join(t["tytul"] for t in dzien_t))
    dn = ['pon', 'wt', 'śr', 'czw', 'pt', 'sob', 'ndz']
    for wd in u.get("dni_jedna_sesja") or []:    # np. śr i pt: jedna sesja dziennie (decyzja Antka 18.11)
        dzien_t = {}
        for t in tren:
            if date.fromisoformat(t["dzien"]).weekday() == wd:
                dzien_t.setdefault(t["dzien"], []).append(t)
        for d, ts in dzien_t.items():
            if len(ts) > 1:
                p.append(f"{dn[wd]} {d}: Antek chce wtedy TYLKO JEDNĄ sesję (bez dokładania roweru/biegu do siłki) — "
                         + ", ".join(t["tytul"] for t in ts) + "; przenieś drugą na inny dzień albo pomiń")
    wkd = int(u.get("weekend_dwie_max", 2))     # ile dni weekendu może mieć 2+ sesje (Antek 18.11: jeden)
    tyg = {}
    for t in tren:
        d = date.fromisoformat(t["dzien"])
        if d.weekday() >= 5:
            tyg.setdefault(d.isocalendar()[:2], {}).setdefault(t["dzien"], []).append(t)
    for dni_w in tyg.values():
        podw = sorted(d for d, ts in dni_w.items() if len(ts) > 1)
        if len(podw) > wkd:
            p.append(f"weekend: dwie sesje w {len(podw)} dni ({', '.join(podw)}), a Antek pozwala tylko w {wkd} dzień weekendu")
    silki = [t for t in tren if t["sport"] == "silka"]
    min_s = int(u.get("silka_min_min") or 0)
    for t in silki:                              # „porządne” siłki: nie skracać do 30–40 min (decyzja Antka 18.11)
        lzej = any(x in ((t.get("tytul") or "") + " " + (t.get("opis") or "")).lower() for x in ("deload", "techniczn"))
        prog = round(min_s * 0.8) if lzej else min_s
        if prog and not t.get("opcjonalny") and budowa.czas_min(t) < prog:
            p.append(f"{t['dzien']} {t['tytul']}: siłka ~{budowa.czas_min(t)} min, a Antek chce pełnych treningów "
                     f"(min. {prog} min z rozgrzewką: więcej ćwiczeń/serii; lżej = wyższy RIR albo ciężar, nie 2 serie)")
    for t in silki:
        ks = [k for k in _kroki(t.get("kroki")) if k.get("garmin") or k.get("nazwa")]
        kat = [(k.get("garmin") or "").split("/")[0].upper() for k in ks]
        for k in ks:
            if k.get("nazwa") and tierlista.tier_cwiczenia(k["nazwa"], u.get("tierlista") or {}) == "X":
                p.append(f"{t['dzien']} {t['tytul']}: {k['nazwa']} jest w tierliście Antka jako WYKLUCZONE — zamień")
        if "SHRUG" in kat or any("szrug" in (k.get("nazwa") or "").lower() for k in ks):
            p.append(f"{t['dzien']} {t['tytul']}: szrugsy — Antek ich nie robi (bez celowej pracy na kaptury)")
        if any(a == b == "TRICEPS_EXTENSION" for a, b in zip(kat, kat[1:])):
            p.append(f"{t['dzien']} {t['tytul']}: dwa ćwiczenia na triceps bezpośrednio po sobie — rozdziel je")
        if partia(t) == "nogi":
            nz = " ".join((k.get("nazwa") or "").lower() for k in ks)
            if not ("odwodz" in nz and "przywodz" in nz):
                p.append(f"{t['dzien']} {t['tytul']}: na końcu dnia nóg ma być odwodzenie i przywodzenie bioder 2×12–20")
    bez_brzucha = [f"{t['dzien']} {t['tytul']}" for t in silki if not any(
        (k.get("garmin") or "").split("/")[0].upper() in BRZUCH and "prostowanie nóg" not in (k.get("nazwa") or "").lower()
        for k in _kroki(t.get("kroki")))]   # „prostowanie nóg” Antka siedzi w Garminie pod CRUNCH
    if bez_brzucha:
        p.append("brak brzucha na końcu siłki (wymaganie Antka: na każdej): " + "; ".join(bez_brzucha))
    def _skosne(k):                              # tylko ćwiczenia brzucha (unoszenie hantli „bokiem” to barki, nie skośne)
        kat = (k.get("garmin") or "").split("/")[0].upper()
        return kat == "CHOP" or ((kat in BRZUCH or kat == "PLANK") and any(
            x in ((k.get("nazwa") or "") + " " + (k.get("garmin") or "")).lower()
            for x in ("bokiem", "skośn", "skosn", "woodchop", "boczn", "side", "oblique", "twist")))
    skosne = sum(1 for t in silki for k in _kroki(t.get("kroki")) if _skosne(k))
    if skosne > 1:
        p.append(f"{skosne} ćwiczeń na skośne/boczne brzucha — Antek chce max 1 w tygodniu (poszerzają talię)")
    return p
