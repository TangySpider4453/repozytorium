"""Plan treningów od Claude na najbliższe dni → tabela plan → (automatycznie) Garmin. Niezmienione treningi zostają
(Claude zwraca `zostaw_id`), więc na zegarku nic nie miga bez powodu."""
import fcntl
import json
import logging
from datetime import date, timedelta

from . import ai, baza, budowa, config, kontekst

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
        "kroki": {"type": "array", "items": KROK}}, "required": ["dzien", "sport", "tytul"]}}},
    "required": ["komentarz", "treningi"]}

ZASADY = """ZASADY FORMATU PLANU:
- Każdy dzień w zakresie dostaje wpis: trening(i) albo {"sport":"odpoczynek"} (z krótkim opisem, np. regeneracja).
- Istniejący trening bez zmian: zwróć {"zostaw_id": <id>, "dzien", "sport", "tytul"} (bez kroków). Zmieniaj tylko,
  gdy dane (sen, HRV, gotowość, zmęczenie, wykonanie) albo prośba Antka tego wymagają.
- tytul ≤ 40 znaków, czytelny na zegarku (np. "Rower Z2 2h", "Bieg 6×400 m", "Siłka Dół A"). opis: cel treningu +
  wskazówki (≤ 600 znaków).
- Rower/bieg: kroki rozgrzewka / praca / odpoczynek / schlodzenie z czas_min albo dystans_km; pętla
  {"rodzaj":"powtorz","razy":N,"kroki":[...]}. Cel: "strefa_tetna"+"strefa" (1-5, strefy z Garmina) — domyślnie;
  "moc" od/do w W (rower, gdy znane FTP); "tempo" od/do w SEKUNDACH na km (bieg); "kadencja" od/do; "brak".
- Siłka: rozgrzewka (czas_min), potem {"rodzaj":"cwiczenie","nazwa": polska nazwa (najlepiej z listy Antka),
  "garmin":"KATEGORIA/NAZWA" z listy Garmina, "serie","powt" albo "czas_s","kg" (gdy znasz z historii),
  "przerwa_s"}. Superserie/obwody: "powtorz" z ćwiczeniami w środku (bez "serie" w środku). Na koniec schlodzenie.
- Ciężary dobieraj z historii siłowni (serie z ostatnich treningów). Gdy brak historii — bez kg.
"""


def _strefy(db):
    s = baza.kv(db, "strefy", {})
    return json.dumps(s, ensure_ascii=False)[:3000] if s else "(brak — używaj stref tętna 1-5 z Garmina)"


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


def zaplanuj(powod="", prosba="", dni=None):
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
    prompt = "\n\n".join(x for x in [
        kontekst.pelny(db),
        f"STREFY / PROGI Z GARMINA:\n{_strefy(db)}",
        _lista_cwiczen() if "silka" in u["sporty"] else "",
        f"OBECNY PLAN W ZAKRESIE {od}..{do}:\n{ist_txt}",
        ZASADY,
        f"ZADANIE: ułóż plan na dni {od} .. {do} (sporty: {', '.join(u['sporty'])}). Powód: {powod or 'aktualizacja'}."
        + (f"\nPROŚBA ANTKA: {prosba}" if prosba else "")
        + ("\nDziś już był trening — dzisiejszego dnia nie planuj." if od != dzis.isoformat() else "")] if x)
    w = ai.zapytaj(prompt, SCHEMAT, effort="high", limit_s=600)
    zmiany = zastosuj(db, w.get("treningi") or [], od, do, ist, powod)
    log.info("plan: %s", zmiany)
    return {"komentarz": w.get("komentarz", ""), "zmiany": zmiany, "od": od, "do": do}


def zastosuj(db, treningi, od, do, ist, zrodlo):
    zostaja = {t["zostaw_id"] for t in treningi if t.get("zostaw_id")}
    po_id = {r["id"]: r for r in ist}
    zmiany = []
    for r in ist:
        if r["id"] not in zostaja:
            db.execute("UPDATE plan SET stan=?, zmieniono=? WHERE id=?",
                       ("do_usuniecia" if r["workout_id"] else "usuniety", baza.teraz(), r["id"]))
            zmiany.append(f"− {r['dzien']} {r['tytul']}")
    for t in treningi:
        if t.get("zostaw_id") in po_id:
            continue
        if not (od <= (t.get("dzien") or "") <= do):
            continue
        if t["sport"] != "odpoczynek":
            try:
                budowa.buduj(t)                        # walidacja przed zapisem
            except Exception as ex:
                log.warning("odrzucony trening %s: %s", t.get("tytul"), ex)
                zmiany.append(f"⚠️ {t.get('dzien')} {t.get('tytul')}: błąd planu ({ex})")
                continue
        db.execute("INSERT INTO plan (dzien, sport, tytul, opis, kroki, hash, stan, utworzono, zmieniono, zrodlo) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (t["dzien"], t["sport"], t["tytul"][:60], t.get("opis", ""), json.dumps(t.get("kroki") or [], ensure_ascii=False),
                    budowa.hash_treningu(t), "nowy" if t["sport"] != "odpoczynek" else "w_apce", baza.teraz(), baza.teraz(),
                    zrodlo[:200]))
        zmiany.append(f"+ {t['dzien']} {t['tytul']}" + (f" (~{budowa.czas_min(t)} min)" if t["sport"] != "odpoczynek" else ""))
    db.commit()
    return zmiany


def braki(db, dni=None):
    """dni w najbliższym zakresie bez żadnego wpisu planu"""
    dni = dni or int(config.ustawienia()["plan_dni"])
    dzis = date.today()
    zakres = [(dzis + timedelta(days=i)).isoformat() for i in range(1, dni)]
    jest = {r[0] for r in db.execute("SELECT DISTINCT dzien FROM plan WHERE dzien BETWEEN ? AND ? AND stan NOT IN "
                                     "('usuniety','do_usuniecia')", (zakres[0], zakres[-1]))} if zakres else set()
    return [d for d in zakres if d not in jest]
