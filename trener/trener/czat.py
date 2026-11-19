"""Czat z trenerem (Claude) z pełnym kontekstem danych. Odpowiedź może: zmienić plan (automatycznie), zapamiętać
ustalenia, zmienić cele/dostępność/sprzęt, poprosić o dane z dowolnego okresu historii (jedna dodatkowa runda)."""
import json
import logging
import threading
from datetime import datetime, timedelta

from . import ai, baza, cel, config, kontekst, przebieg

log = logging.getLogger(__name__)

METRYKI = {"hrv": "HRV", "sen_h": "sen", "sen_wynik": "wynik snu", "tetno_spocz": "tętno spocz.", "bb_rano": "Body Battery rano",
           "gotowosc": "gotowość", "stres": "stres", "obc_ostre": "obciążenie ostre", "acwr": "stosunek obciążeń",
           "kroki": "kroki", "vo2_rower": "VO2max rower", "sen_gleboki_h": "sen głęboki", "sen_tetno": "tętno w nocy",
           "kcal_akt": "kcal aktywne"}

SCHEMAT = {"type": "object", "properties": {
    "odpowiedz": {"type": "string"},
    "potrzebne_dane": {"type": "object", "description": "gdy do odpowiedzi potrzebujesz szczegółów z historii",
                       "properties": {"od": {"type": "string"}, "do": {"type": "string"}}},
    "przebieg_id": {"type": "integer", "description": "id aktywności, której przebiegu (sekunda po sekundzie) potrzebujesz,"
                    " a nie ma go w kontekście — dostaniesz go w drugiej rundzie"},
    "wykresy": {"type": "array", "description": "0–3 wykresy pod odpowiedzią", "items": {"type": "object", "properties": {
        "tytul": {"type": "string"},
        "rodzaj": {"type": "string", "enum": ["trening", "dni"]},
        "aktywnosc_id": {"type": "integer"},
        "kanaly": {"type": "array", "items": {"type": "string", "enum": ["tetno", "moc", "predkosc", "kadencja", "wysokosc"]}},
        "od_s": {"type": "number"}, "do_s": {"type": "number"},
        "metryki": {"type": "array", "items": {"type": "string", "enum": list(METRYKI)}},
        "od": {"type": "string"}, "do": {"type": "string"},
        "znaczniki": {"type": "array", "items": {"type": "object", "properties": {
            "s": {"type": "number"}, "dzien": {"type": "string"}, "tekst": {"type": "string"}}, "required": ["tekst"]}},
        "linie": {"type": "array", "items": {"type": "object", "properties": {
            "kanal": {"type": "string"}, "wartosc": {"type": "number"}, "tekst": {"type": "string"}},
            "required": ["kanal", "wartosc"]}}},
        "required": ["rodzaj"]}},
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
- CO JEST W PLANIE: mówiąc, co jest zaplanowane (np. „bieg jest w niedzielę”), opieraj się WYŁĄCZNIE na sekcji PLAN.
  Wzór tygodnia, opisy faz i zasady to szablony — nie twierdź na ich podstawie, że coś jest w planie. Gdy Antek mówi,
  że czegoś nie ma, sprawdź PLAN; jeśli ma rację, przyznaj to w jednym zdaniu i idź dalej.
- ANTEK DECYDUJE O SWOIM CZASIE. Gdy mówi, że nie ma czasu, nie chce czegoś robić albo prosi o zamianę/przesunięcie —
  nie odmawiaj i nie przekonuj, że „ma zrobić”. Zrób zmianę (zmienic_plan=true) albo, gdy prośba gryzie się z celami,
  zaproponuj 1–2 konkretne układy tygodnia pod jego dostępność (np. „Full Upper przesuwam na sobotę”) i daj wybrać.
  Koszt zmiany możesz podać w jednym krótkim zdaniu, bez wykładu. Stałe ustalenia (np. góra 3× w tygodniu) to cele
  tygodnia do ułożenia na nowo, nie powód do odmowy.
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
- WYKRESY: gdy coś łatwiej pokazać, niż opisać (albo Antek prosi), dodaj wykresy (max 3, zwykle 1):
  • rodzaj "trening": aktywnosc_id, kanaly (tetno/moc/predkosc/kadencja/wysokosc; każdy kanał to osobny wykres
    z tą samą osią czasu), opcjonalnie od_s/do_s (sekundy od startu — przybliż fragment, o którym mówisz),
    znaczniki [{s, tekst}] w miejscach, o których piszesz (np. {s: 3422, tekst: "833 W"}), linie [{kanal, wartosc,
    tekst}] np. górna granica Z2 mocy. Czas w PRZEBIEGU jest m:ss / h:mm:ss — przelicz na sekundy (57:02 → 3422).
    PRZYBLIŻANIE: gdy mówisz o konkretnym momencie (strzał mocy, interwał, podjazd, skok tętna), ustaw od_s/do_s
    tak, żeby ten fragment wypełniał wykres — zwykle 1–3 min przed i po (strzał 833 W @ 57:02 → od_s 3300, do_s 3540;
    interwał 5 min → cały interwał + 2 min zapasu). Cały trening tylko, gdy chodzi o ogólny przebieg (dryf, strefy).
    Możesz dać dwa wykresy: cały trening + przybliżenie. Znaczniki spoza zakresu nie będą widoczne. Antek może
    w apce przełączyć na cały przebieg.
  • rodzaj "dni": metryki (np. hrv, sen_h, tetno_spocz), od/do RRRR-MM-DD, znaczniki [{dzien, tekst}].
  W tekście odwołuj się do wykresu („na wykresie widać…”). Nie wymyślaj aktywnosc_id — tylko id z kontekstu.
- Gdy pytanie dotyczy przebiegu treningu (tętno/moc w danym momencie, interwały, strzały mocy), a nie masz jego
  PRZEBIEGU w kontekście — podaj przebieg_id (id aktywności), odpowiedz krótko „sprawdzam”; dostaniesz przebieg.
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


OMOW = """TRYB „OMÓW TRENING”: Antek kliknął Omów przy treningu (OMAWIANY TRENING). Daj KRÓTKIE podsumowanie (do ~90 słów,
3–5 punktów): co widać w danych — jak poszło względem planu/celu, przebieg tętna i mocy, coś ciekawego (strzały,
dryf, strefy), jedna rada. Dołącz 1 wykres przebiegu z znacznikami najważniejszych miejsc. Nie zmieniaj planu, nie
zadawaj listy pytań — Antek sam dopyta. Jeśli najciekawsza rzecz to krótki moment (np. strzał mocy), przybliż
wykres na nią (od_s/do_s)."""


def odpowiedz(tresc, analiza_id=None, aktywnosc_id=None, omow=False):
    """zapisuje wiadomość Antka, pyta Claude, stosuje akcje; -> dict odpowiedzi.
    Gdy skończył się limit Claude: pytanie czeka i trener odpowiada sam po odnowieniu (timer + cykl co 20 min)."""
    db = baza.polacz()
    db.execute("INSERT INTO czat (kto, tresc, czas, analiza_id, aktywnosc_id) VALUES ('ja',?,?,?,?)",
               (tresc, baza.teraz(), analiza_id, aktywnosc_id))
    db.commit()
    try:
        return _odpowiedz(db, tresc, analiza_id, aktywnosc_id, omow)
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


def _omawiany(db, aktywnosc_id):
    """trening z przycisku Omów albo z niedawnej rozmowy (ostatnie 10 wiadomości, max 12 h)"""
    if aktywnosc_id:
        return aktywnosc_id
    od = (datetime.now() - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S")
    for r in db.execute("SELECT aktywnosc_id, czas FROM czat ORDER BY id DESC LIMIT 10"):
        if r[0] and r[1] >= od:
            return r[0]
    return None


def _trening_tekst(db, aid):
    r = db.execute("SELECT dane, szczegoly, typ FROM aktywnosci WHERE id=?", (aid,)).fetchone()
    if not r:
        return None
    s = kontekst.dane.streszczenie_aktywnosci(baza.rozpakuj(r[0]))
    if r[2] == "strength_training" and r[1]:
        s["cwiczenia"] = kontekst.cwiczenia_silki(baza.rozpakuj(r[1]))
    try:
        p = przebieg.dla_ai(przebieg.pobierz(db, aid))
    except Exception as ex:
        log.exception("przebieg %s", aid)
        p = f"przebieg niedostępny ({type(ex).__name__})"
    return f"(id {aid}, {kontekst.slownie(s.get('start', '')[:10])}) " + json.dumps(s, ensure_ascii=False) + "\n" + p


def _wykresy(db, w):
    """zostaw tylko poprawne wykresy (istniejące aktywności, znane kanały/metryki)"""
    wyn = []
    for x in (w.get("wykresy") or [])[:3]:
        if x.get("rodzaj") == "trening":
            if not x.get("aktywnosc_id") or not db.execute("SELECT 1 FROM aktywnosci WHERE id=?", (x["aktywnosc_id"],)).fetchone():
                continue
            x["kanaly"] = [k for k in x.get("kanaly") or ["tetno"] if k in przebieg.NAZWY] or ["tetno"]
            od, do = x.get("od_s"), x.get("do_s")
            od = max(0, od) if isinstance(od, (int, float)) else None
            do = do if isinstance(do, (int, float)) and do > 0 else None
            if od is not None and do is not None and do - od < 30:      # za wąsko → co najmniej 30 s wokół środka
                sr = (od + do) / 2
                od, do = max(0, sr - 15), sr + 15
            x["od_s"], x["do_s"] = od, do
        elif x.get("rodzaj") == "dni":
            x["metryki"] = [k for k in x.get("metryki") or [] if k in METRYKI]
            if not x["metryki"]:
                continue
        else:
            continue
        wyn.append(x)
    return wyn


def _odpowiedz(db, tresc, analiza_id, aktywnosc_id=None, omow=False):
    cz = ["BAZA WIEDZY:\n" + cel.wiedza(config.ustawienia()["sporty"]), kontekst.pelny(db)]
    aid = _omawiany(db, aktywnosc_id)
    if aid:
        t = _trening_tekst(db, aid)
        if t:
            cz.append("OMAWIANY TRENING " + t)
    if analiza_id:
        r = db.execute("SELECT * FROM analizy WHERE id=?", (analiza_id,)).fetchone()
        if r:
            cz.append(f"OMAWIANA ANALIZA ({r['rodzaj']}, {r['dzien']}): {r['tytul']}\n{r['tresc']}")
    ostatnie = db.execute("SELECT rodzaj, dzien, tytul FROM analizy ORDER BY id DESC LIMIT 5").fetchall()
    if ostatnie:
        cz.append("OSTATNIE ANALIZY: " + "; ".join(f"{r[1]} {r[0]}: {r[2]}" for r in ostatnie))
    cz += [INSTRUKCJA] + ([OMOW] if omow else []) + ["ROZMOWA:\n" + historia_czatu(db)]
    prompt = "\n\n".join(cz)
    w = ai.zapytaj(prompt, SCHEMAT, effort="medium")
    pd = w.get("potrzebne_dane") or {}
    dod = ""
    if pd.get("od") and pd.get("do"):
        dod += f"\n\nDANE Z OKRESU {pd['od']}..{pd['do']}:\n" + _dane_okresu(db, pd["od"], pd["do"])
    if w.get("przebieg_id") and w["przebieg_id"] != aid:
        t = _trening_tekst(db, w["przebieg_id"])
        dod += f"\n\nTRENING {t}" if t else f"\n\n(brak aktywności o id {w['przebieg_id']})"
        aid = w["przebieg_id"] if t else aid
    if dod:
        w = ai.zapytaj(prompt + dod + "\n\nTeraz odpowiedz pełnie (bez potrzebne_dane i przebieg_id).", SCHEMAT, effort="medium")
    wykresy = _wykresy(db, w)
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
    db.execute("INSERT INTO czat (kto, tresc, czas, analiza_id, akcje, wykresy, aktywnosc_id) VALUES ('trener',?,?,?,?,?,?)",
               (w["odpowiedz"], baza.teraz(), analiza_id, json.dumps(akcje, ensure_ascii=False),
                json.dumps(wykresy, ensure_ascii=False) if wykresy else None, aid))
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
