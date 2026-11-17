"""Czat z trenerem (Claude) z pełnym kontekstem danych. Odpowiedź może: zmienić plan (automatycznie), zapamiętać
ustalenia, zmienić cele/dostępność/sprzęt, poprosić o dane z dowolnego okresu historii (jedna dodatkowa runda)."""
import json
import logging

from . import ai, baza, cel, config, kontekst

log = logging.getLogger(__name__)

SCHEMAT = {"type": "object", "properties": {
    "odpowiedz": {"type": "string"},
    "potrzebne_dane": {"type": "object", "description": "gdy do odpowiedzi potrzebujesz szczegółów z historii",
                       "properties": {"od": {"type": "string"}, "do": {"type": "string"}}},
    "zmienic_plan": {"type": "boolean"},
    "przebuduj_makrocykl": {"type": "boolean", "description": "nowy/zmieniony cel, termin zawodów albo duża zmiana sytuacji"},
    "prosba_do_planu": {"type": "string"},
    "zapamietaj": {"type": "array", "items": {"type": "string"}, "description": "trwałe ustalenia (np. kontuzja, preferencje)"},
    "ustawienia": {"type": "object", "properties": {"cele": {"type": "string"}, "dostepnosc": {"type": "string"},
                                                   "sprzet": {"type": "string"}}}},
    "required": ["odpowiedz", "zmienic_plan"]}

INSTRUKCJA = """Rozmawiasz z Antkiem w apce Trener. Odpowiadaj konkretnie (zwykle do ~150 słów, dłużej gdy prosi o analizę).
- Gdy Antek prosi o zmianę treningów albo z rozmowy wynika, że plan trzeba zmienić: zmienic_plan=true i opisz zmianę
  w prosba_do_planu — apka sama przeplanuje i wyśle na zegarek (powiedz mu, że to się dzieje).
- Gdy poda cele / kiedy może trenować / sprzęt — wpisz w ustawienia (pełny nowy tekst pola).
- Nowy cel / termin zawodów / duża zmiana (kontuzja, wyjazd na miesiąc) → przebuduj_makrocykl=true (periodyzacja od nowa).
- Opieraj się na BAZIE WIEDZY; na pytanie „dlaczego tak” odpowiadaj zasadą i źródłem.
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
    """zapisuje wiadomość Antka, pyta Claude, stosuje akcje; -> dict odpowiedzi"""
    db = baza.polacz()
    db.execute("INSERT INTO czat (kto, tresc, czas, analiza_id) VALUES ('ja',?,?,?)", (tresc, baza.teraz(), analiza_id))
    db.commit()
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
    nowy_makro = w.get("przebuduj_makrocykl") or cel.potrzebny(db)
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
