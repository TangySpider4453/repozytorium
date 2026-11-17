"""Czat z trenerem (Claude) z pełnym kontekstem danych. Odpowiedź może: zmienić plan (automatycznie), zapamiętać
ustalenia, zmienić cele/dostępność/sprzęt, poprosić o dane z dowolnego okresu historii (jedna dodatkowa runda)."""
import json
import logging
import threading
from datetime import datetime, timedelta

from . import ai, baza, cel, config, kontekst

log = logging.getLogger(__name__)

SCHEMAT = {"type": "object", "properties": {
    "odpowiedz": {"type": "string"},
    "potrzebne_dane": {"type": "object", "description": "gdy do odpowiedzi potrzebujesz szczegółów z historii",
                       "properties": {"od": {"type": "string"}, "do": {"type": "string"}}},
    "zmienic_plan": {"type": "boolean"},
    "przebuduj_makrocykl": {"type": "boolean", "description": "nowy/zmieniony cel, termin zawodów albo duża zmiana sytuacji"},
    "prosba_do_planu": {"type": "string"},
    "decyzja_propozycji": {"type": "string", "enum": ["zmien", "zostaw", "brak"],
                           "description": "odpowiedź Antka na propozycję CZEKA NA DECYZJĘ (gdy jest w kontekście)"},
    "zapamietaj": {"type": "array", "items": {"type": "string"}, "description": "trwałe ustalenia (np. kontuzja, preferencje)"},
    "ustawienia": {"type": "object", "properties": {"cele": {"type": "string"}, "dostepnosc": {"type": "string"},
                                                   "sprzet": {"type": "string"}}}},
    "required": ["odpowiedz", "zmienic_plan"]}

INSTRUKCJA = """Rozmawiasz z Antkiem w apce Trener. Odpowiadaj konkretnie (zwykle do ~150 słów, dłużej gdy prosi o analizę).
- Gdy Antek prosi o zmianę treningów albo z rozmowy wynika, że plan trzeba zmienić: zmienic_plan=true i opisz zmianę
  w prosba_do_planu — apka sama przeplanuje i wyśle na zegarek (powiedz mu, że to się dzieje).
- Gdy poda cele / kiedy może trenować / sprzęt — wpisz w ustawienia (pełny nowy tekst pola).
- Jeśli w kontekście nie ma ANKIETY ANTKA: zachęć go do wypełnienia ankiety startowej w apce (karta „Zacznijmy”) —
  plan powstaje dopiero po niej.
- Nowy cel / termin zawodów / duża zmiana (kontuzja, wyjazd na miesiąc) → przebuduj_makrocykl=true (periodyzacja od nowa).
- Opieraj się na BAZIE WIEDZY; na pytanie „dlaczego tak” odpowiadaj zasadą i źródłem.
- Gdy w kontekście jest CZEKA NA DECYZJĘ ANTKA, a Antek odpowiada (np. „słabo się czuję, zmień” / „czuję się
  dobrze, zostaw”) → decyzja_propozycji = zmien / zostaw. Inaczej „brak”.
- Trwałe fakty (kontuzja, nie lubi biegać, ma zawody 12.04) — zapamietaj.
- Gdy pyta o konkretny okres z historii, a nie masz szczegółów — podaj potrzebne_dane {od, do} (RRRR-MM-DD), a
  odpowiedz krótko „sprawdzam”; dostaniesz dane w drugiej rundzie."""


def historia_czatu(db, n=20):
    rows = db.execute("SELECT kto, tresc, czas FROM czat ORDER BY id DESC LIMIT ?", (n,)).fetchall()[::-1]
    return "\n".join(f"[{r['czas'][5:16]}] {'Antek' if r['kto'] == 'ja' else 'Trener'}: {r['tresc']}" for r in rows)


def _dane_okresu(db, od, do):
    dni = [kontekst.wiersz_dnia(d) for d in baza.dni_zakres(db, od, do)]
    akt = kontekst.aktywnosci(db, od, do)
    if len(dni) > 120:
        dni = kontekst.agregaty(db, "tydzien", od)
    return ("DNI:\n" + "\n".join(dni) + "\n\nAKTYWNOŚCI:\n" + "\n".join(json.dumps(a, ensure_ascii=False) for a in akt[:300]))


def odpowiedz(tresc, analiza_id=None):
    """zapisuje wiadomość Antka, pyta Claude, stosuje akcje; -> dict odpowiedzi.
    Gdy skończył się limit Claude: pytanie czeka i trener odpowiada sam po odnowieniu (timer + cykl co 20 min)."""
    db = baza.polacz()
    db.execute("INSERT INTO czat (kto, tresc, czas, analiza_id) VALUES ('ja',?,?,?)", (tresc, baza.teraz(), analiza_id))
    db.commit()
    try:
        return _odpowiedz(db, tresc, analiza_id)
    except ai.BrakTokenow as ex:
        return _odloz(db, tresc, analiza_id, ex.reset)


def _odloz(db, tresc, analiza_id, reset):
    stare = baza.kv(db, "czat_czeka")
    if stare and stare.get("notka"):          # jedna notka „czekam” naraz
        db.execute("DELETE FROM czat WHERE id=?", (stare["notka"],))
    kiedy = f"ok. {reset:%H:%M}" if reset else "za chwilę"
    notka = db.execute("INSERT INTO czat (kto, tresc, czas, akcje) VALUES ('trener',?,?,?)",
                       (f"⏳ Skończył się limit Claude. Odpowiem sam, gdy się odnowi ({kiedy}), i dam znać powiadomieniem.",
                        baza.teraz(), json.dumps(["czeka na limit"], ensure_ascii=False))).lastrowid
    baza.ustaw_kv(db, "czat_czeka", {"tresc": tresc, "analiza_id": analiza_id, "notka": notka,
                                     "reset": reset.isoformat(timespec="minutes") if reset else None})
    db.commit()
    log.warning("czat: brak limitu, odpowiem po %s", reset)
    if reset:                                 # w usłudze webowej: spróbuj zaraz po odnowieniu (cykl co 20 min to zapas)
        za = max(60, (reset - datetime.now()).total_seconds() + 90)
        t = threading.Timer(za, dokoncz_czekajace)
        t.daemon = True
        t.start()
    return {"odpowiedz": "⏳ czeka na limit", "zmienic_plan": False, "czeka": True}


_blokada = threading.Lock()


def dokoncz_czekajace():
    """odpowiada na pytanie odłożone przez limit (wołane z timera i z cyklu); -> True gdy odpowiedział"""
    if not _blokada.acquire(blocking=False):
        return False
    try:
        db = baza.polacz()
        r = db.execute("SELECT wartosc FROM kv WHERE klucz='czat_czeka'").fetchone()
        c = json.loads(r[0]) if r else None
        if not c:
            return False
        if c.get("reset") and datetime.now() < datetime.fromisoformat(c["reset"]) + timedelta(minutes=1):
            return False
        # zajęcie zadania atomowo (timer w usłudze webowej i cykl to dwa procesy)
        if db.execute("DELETE FROM kv WHERE klucz='czat_czeka' AND wartosc=?", (r[0],)).rowcount == 0:
            return False
        if c.get("notka"):
            db.execute("DELETE FROM czat WHERE id=?", (c["notka"],))
        db.commit()
        try:
            w = _odpowiedz(db, c["tresc"], c.get("analiza_id"))
        except ai.BrakTokenow as ex:
            _odloz(db, c["tresc"], c.get("analiza_id"), ex.reset)
            return False
        except Exception:
            if c.get("proby", 0) < 3:         # inny błąd: spróbuje cykl (max 3 razy)
                baza.ustaw_kv(db, "czat_czeka", {**c, "notka": None, "reset": None, "proby": c.get("proby", 0) + 1})
            raise
        from . import powiadom
        powiadom.powiadom("💬 Trener odpowiedział", w["odpowiedz"][:180], "/#czat", db)
        return True
    finally:
        _blokada.release()


def _odpowiedz(db, tresc, analiza_id):
    cz = ["BAZA WIEDZY:\n" + cel.wiedza(config.ustawienia()["sporty"]), kontekst.pelny(db)]
    if analiza_id:
        r = db.execute("SELECT * FROM analizy WHERE id=?", (analiza_id,)).fetchone()
        if r:
            cz.append(f"OMAWIANA ANALIZA ({r['rodzaj']}, {r['dzien']}): {r['tytul']}\n{r['tresc']}")
    ostatnie = db.execute("SELECT rodzaj, dzien, tytul FROM analizy ORDER BY id DESC LIMIT 5").fetchall()
    if ostatnie:
        cz.append("OSTATNIE ANALIZY: " + "; ".join(f"{r[1]} {r[0]}: {r[2]}" for r in ostatnie))
    cz += [INSTRUKCJA, "ROZMOWA:\n" + historia_czatu(db)]
    prompt = "\n\n".join(cz)
    w = ai.zapytaj(prompt, SCHEMAT, effort="medium")
    pd = w.get("potrzebne_dane") or {}
    if pd.get("od") and pd.get("do"):
        w = ai.zapytaj(prompt + f"\n\nDANE Z OKRESU {pd['od']}..{pd['do']}:\n" + _dane_okresu(db, pd["od"], pd["do"])
                       + "\n\nTeraz odpowiedz pełnie (bez potrzebne_dane).", SCHEMAT, effort="medium")
    akcje = []
    if w.get("ustawienia"):
        config.zapisz_ustawienia({k: v for k, v in w["ustawienia"].items() if v})
        akcje.append("ustawienia: " + ", ".join(k for k, v in w["ustawienia"].items() if v))
    if w.get("zapamietaj"):
        p = baza.kv(db, "pamiec_trenera", [])
        baza.ustaw_kv(db, "pamiec_trenera", (p + [f"{baza.teraz()[:10]}: {x}" for x in w["zapamietaj"]])[-60:])
        akcje.append("zapamiętane: " + "; ".join(w["zapamietaj"]))
    if w.get("decyzja_propozycji") in ("zmien", "zostaw"):
        from .plan import zdecyduj
        zm = zdecyduj(db, w["decyzja_propozycji"] == "zmien", tresc[:120])
        akcje.append("propozycja: " + ("zmienione" if w["decyzja_propozycji"] == "zmien" else "plan bez zmian"))
        if zm:
            from . import zegarek
            from .garmin import polacz
            try:
                zegarek.synchronizuj_plan(polacz(), db)
            except Exception:
                log.exception("zegarek po decyzji")
    gotowy = config.ustawienia().get("start_gotowy")
    if not gotowy:                            # przed ankietą startową: rozmowa tak, planowanie nie
        w["zmienic_plan"] = False
    nowy_makro = gotowy and (w.get("przebuduj_makrocykl") or cel.potrzebny(db))
    if nowy_makro:
        akcje.append("nowa periodyzacja")
    if w.get("zmienic_plan") or nowy_makro:
        akcje.append("przeplanowanie")
    db.execute("INSERT INTO czat (kto, tresc, czas, analiza_id, akcje) VALUES ('trener',?,?,?,?)",
               (w["odpowiedz"], baza.teraz(), analiza_id, json.dumps(akcje, ensure_ascii=False)))
    db.commit()
    if nowy_makro:
        m = cel.zbuduj(w.get("prosba_do_planu") or tresc, db)
        db.execute("INSERT INTO czat (kto, tresc, czas, akcje) VALUES ('trener',?,?,?)",
                   (f"🗺️ Periodyzacja: {m['cel_glowny']}\n" + "\n".join(
                       f"• {f['nazwa']} {f['od'][5:]}–{f['do'][5:]}: {f['cel']} ({f['godziny_tyg_od']:g}–{f['godziny_tyg_do']:g} h/tydz.)"
                       for f in m["fazy"]) + f"\n\n{m['uzasadnienie']}", baza.teraz(), "[]"))
        db.commit()
    if w.get("zmienic_plan") or nowy_makro:
        from .cykl import przeplanuj
        wyn = przeplanuj("prośba w czacie", w.get("prosba_do_planu") or tresc, powiadamiaj=False)
        if wyn:
            db.execute("INSERT INTO czat (kto, tresc, czas, akcje) VALUES ('trener',?,?,?)",
                       ("📅 Plan zmieniony. " + wyn["komentarz"] + "\n" + "\n".join(wyn["zmiany"]), baza.teraz(), "[]"))
            db.commit()
    return w
