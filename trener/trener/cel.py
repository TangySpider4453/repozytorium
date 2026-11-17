"""Makrocykl: z celów Antka + danych + bazy wiedzy Claude układa fazy do celu (baza → budowanie → szczyt/taper …).
Tygodniowe plany trzymają się bieżącej fazy. Przebudowa: zmiana celów/dostępności, koniec makrocyklu, prośba w czacie."""
import hashlib
import json
import logging
from datetime import date
from pathlib import Path

from . import ai, baza, config, kontekst

log = logging.getLogger(__name__)
WIEDZA = Path(__file__).resolve().parent / "wiedza"

SCHEMAT = {"type": "object", "properties": {
    "cel_glowny": {"type": "string"}, "data_docelowa": {"type": "string", "description": "RRRR-MM-DD albo pusty"},
    "ocena_wyjsciowa": {"type": "string", "description": "obecna forma i mocne/słabe strony na podstawie danych"},
    "fazy": {"type": "array", "items": {"type": "object", "properties": {
        "nazwa": {"type": "string"}, "od": {"type": "string"}, "do": {"type": "string"}, "cel": {"type": "string"},
        "godziny_tyg_od": {"type": "number"}, "godziny_tyg_do": {"type": "number"},
        "intensywnosc": {"type": "string", "description": "rozkład intensywności i liczba akcentów w tygodniu"},
        "sesje_kluczowe": {"type": "array", "items": {"type": "string"}},
        "silka_tyg": {"type": "number"}, "bieg_tyg": {"type": "number"},
        "rytm": {"type": "string", "description": "np. 3+1 z tygodniem lżejszym"},
        "testy": {"type": "array", "items": {"type": "string"}}},
        "required": ["nazwa", "od", "do", "cel", "godziny_tyg_od", "godziny_tyg_do", "intensywnosc", "sesje_kluczowe"]}},
    "zasady_indywidualne": {"type": "array", "items": {"type": "string"}},
    "uzasadnienie": {"type": "string", "description": "dlaczego tak — odwołania do zasad z bazy wiedzy"}},
    "required": ["cel_glowny", "ocena_wyjsciowa", "fazy", "zasady_indywidualne", "uzasadnienie"]}


def wiedza(sporty=None):
    """baza wiedzy (pliki .md); bez sportów spoza planu"""
    pomin = set()
    if sporty is not None:
        if "bieg" not in sporty:
            pomin.add("04_bieg.md")
        if "silka" not in sporty:
            pomin.add("03_silka.md")
    ogolna = "\n\n".join(p.read_text(encoding="utf-8") for p in sorted(WIEDZA.glob("*.md")) if p.name not in pomin)
    from .badania import wiedza_celu
    cel = wiedza_celu()
    return ogolna + ("\n\n=== WIEDZA POD CEL ANTKA (wyszukana w źródłach dla jego celu — ma pierwszeństwo przy "
                     "specyfice dyscypliny) ===\n\n" + cel if cel else "")


def progi(db):
    """FTP, tętno progowe, strefy tętna — czytelnie dla Claude"""
    s = baza.kv(db, "strefy", {}) or {}
    w = []
    ftp = (s.get("ftp") or {}).get("functionalThresholdPower")
    if ftp:
        w.append(f"FTP rower: {ftp} W (z Garmina, {str((s.get('ftp') or {}).get('calendarDate', ''))[:10]})")
    lt = (s.get("prog_mleczanowy") or {}).get("speed_and_heart_rate") or {}
    if lt.get("heartRateCycling") or lt.get("heartRate"):
        w.append(f"Tętno progowe: rower {lt.get('heartRateCycling')}, bieg {lt.get('heartRate')}"
                 + (f", tempo progowe bieg {kontekst.dane.tempo(lt['speed'] * 10)}" if lt.get("speed") else ""))
    for z in s.get("tetno") or []:
        if z.get("zone1Floor"):
            w.append(f"Strefy tętna ({z.get('sport')}): Z1 {z['zone1Floor']}+, Z2 {z['zone2Floor']}+, Z3 {z['zone3Floor']}+, "
                     f"Z4 {z['zone4Floor']}+, Z5 {z['zone5Floor']}+ (max {z.get('maxHeartRateUsed')})")
    return "\n".join(w) or "(brak progów — prowadź po strefach tętna, zaplanuj test FTP)"


def ftp(db):
    return ((baza.kv(db, "strefy", {}) or {}).get("ftp") or {}).get("functionalThresholdPower")


def odcisk_celow():
    u = config.ustawienia()
    return hashlib.sha1(json.dumps([u["cele"], u["dostepnosc"], u["sprzet"], u["sporty"], u.get("ankieta")],
                                   ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def makrocykl(db=None):
    db = db or baza.polacz()
    return baza.kv(db, "makrocykl")


def faza_teraz(m, d=None):
    d = d or date.today().isoformat()
    for f in (m or {}).get("fazy", []):
        if f["od"] <= d <= f["do"]:
            return f
    return None


def potrzebny(db):
    """makrocykl do (prze)budowy: brak, inne cele, skończył się"""
    u = config.ustawienia()
    if not u["cele"] or not u.get("start_gotowy"):
        return False
    m = makrocykl(db)
    if not m or m.get("_odcisk") != odcisk_celow():
        return True
    return not m.get("fazy") or m["fazy"][-1]["do"] < date.today().isoformat()


def zbuduj(prosba="", db=None):
    db = db or baza.polacz()
    from . import badania
    if badania.potrzebne(db):                 # nowy cel → najpierw ocena bazy i wyszukanie źródeł
        badania.zbadaj(db, prosba)
    badania.postep(db, "Układam periodyzację do celu")
    u = config.ustawienia()
    b = baza.kv(db, "badania") or {}
    oc = b.get("ocena") or {}
    prompt = "\n\n".join([
        "BAZA WIEDZY (zasady treningu ze źródeł — trzymaj się ich, odstępstwa uzasadnij):\n" + wiedza(u["sporty"]),
        "PROGI:\n" + progi(db),
        "OCENA BAZY WIEDZY POD CEL: " + oc.get("dopasowanie", "") + "\nBraki: " + "; ".join(oc.get("braki", []))
        + "\nWątpliwości: " + "; ".join(oc.get("watpliwosci", [])),
        kontekst.pelny(db, tygodnie=26),
        "ZADANIE: Ułóż makrocykl (periodyzację) do celu Antka: fazy z datami od dziś do celu (albo na ~12–16 tygodni, "
        "gdy brak daty), w każdej: cel fazy, widełki godzin tygodniowo (realne względem jego obecnej objętości "
        "z ostatnich tygodni i dostępności — bez skoków), rozkład intensywności, sesje kluczowe (konkretne, z biblioteki),"
        " ile siłowni i biegu tygodniowo, rytm tygodni lżejszych, testy (np. FTP). Zasady indywidualne = wnioski z jego "
        "danych (np. słabszy sen w tygodniu szkolnym, reakcja HRV na ciężkie bloki)."
        + (f"\nDODATKOWO: {prosba}" if prosba else "")])
    w = ai.zapytaj(prompt, SCHEMAT, effort="high", limit_s=600, ciezki=True)
    w["_odcisk"] = odcisk_celow()
    w["_utworzono"] = baza.teraz()
    baza.ustaw_kv(db, "makrocykl", w)
    badania.postep(db, "Układam plan tygodnia i sprawdzam go z zasadami")
    log.info("makrocykl: %s, %d faz", w.get("cel_glowny"), len(w.get("fazy", [])))
    return w


def tekst(m):
    """makrocykl skrótowo do promptów planu/analiz/czatu"""
    if not m:
        return "(brak makrocyklu — Antek nie podał jeszcze celów)"
    f = faza_teraz(m)
    linie = [f"CEL: {m.get('cel_glowny')} (do {m.get('data_docelowa') or 'bez daty'})"]
    for x in m.get("fazy", []):
        znak = "▶ " if x is f else "  "
        linie.append(f"{znak}{x['nazwa']} {x['od']}..{x['do']}: {x['cel']} | {x['godziny_tyg_od']}-{x['godziny_tyg_do']} h/tydz | "
                     f"{x['intensywnosc']} | kluczowe: {'; '.join(x.get('sesje_kluczowe', []))} | siłka {x.get('silka_tyg', '-')}/tydz, "
                     f"bieg {x.get('bieg_tyg', '-')}/tydz | {x.get('rytm', '')} | testy: {', '.join(x.get('testy', []) or ['-'])}")
    if m.get("zasady_indywidualne"):
        linie.append("ZASADY INDYWIDUALNE: " + " | ".join(m["zasady_indywidualne"]))
    return "\n".join(linie)
