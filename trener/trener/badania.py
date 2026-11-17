"""Badania pod cel: (1) ocena, czy baza wiedzy pasuje do celu Antka i czego brakuje, (2) ZAWSZE wyszukanie źródeł
w internecie (Claude + WebSearch/WebFetch) na 2–5 tematów pod cel → pliki wiedzy w dane/wiedza_cel/, (3) sprawdzenie
linków kodem. Pliki bez źródeł są odrzucane. Planer i makrocykl czytają je razem z bazą ogólną."""
import json
import logging
import re
import urllib.request
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import ai, baza, config

log = logging.getLogger(__name__)
KATALOG = config.DANE / "wiedza_cel"
WIEDZA_OGOLNA = Path(__file__).resolve().parent / "wiedza"
URL = re.compile(r"https?://[^\s)\]>\"'`]+")

SCHEMAT_OCENY = {"type": "object", "properties": {
    "dopasowanie": {"type": "string", "description": "na ile obecna baza wiedzy pasuje do celu Antka (2-4 zdania)"},
    "pokryte": {"type": "array", "items": {"type": "string"}},
    "braki": {"type": "array", "items": {"type": "string"}, "description": "czego brakuje albo co jest za ogólne pod ten cel"},
    "watpliwosci": {"type": "array", "items": {"type": "string"}, "description": "zasady z bazy, które mogą nie pasować do celu/wieku"},
    "tematy": {"type": "array", "minItems": 2, "maxItems": 5, "items": {"type": "object", "properties": {
        "tytul": {"type": "string"}, "po_co": {"type": "string"},
        "pytania": {"type": "array", "items": {"type": "string"}, "description": "konkretne pytania do sprawdzenia w źródłach"}},
        "required": ["tytul", "po_co", "pytania"]}}},
    "required": ["dopasowanie", "pokryte", "braki", "watpliwosci", "tematy"]}

ZADANIE_BADANIA = """Jesteś trenerem-badaczem. Zbadaj temat w internecie (WebSearch, WebFetch) dla planu treningowego Antka.
TEMAT: {tytul}
PO CO: {po_co}
PYTANIA: {pytania}
CEL ANTKA: {cel}
JEGO DANE (ostatnie dni i tygodnie z Garmina):
{dane}

Zasady:
- Szukaj najpierw: przeglądy systematyczne / meta-analizy, badania (PubMed, PMC, czasopisma), stanowiska federacji
  i organizacji (UCI, PZKol, ACSM, NSCA, IOC), przepisy (np. regulaminy wyścigów); dopiero potem uznani trenerzy/serwisy
  jako uzupełnienie. Otwórz (WebFetch) każde źródło, które cytujesz.
- NIE wymyślaj URL-i ani liczb. Gdy dowody są słabe lub sprzeczne — napisz to.
- Uwzględnij, że Antek jest nastolatkiem (młody sportowiec).
- Nie powtarzaj tego, co już jest w bazie ogólnej (spis niżej) — uzupełniaj i doprecyzowuj pod cel.

SPIS BAZY OGÓLNEJ:
{spis}

Wynik: TYLKO treść pliku Markdown po polsku (bez wstępu), max ~3500 znaków:
# {tytul}
(zwięzłe zasady z liczbami, punktami)
## Jak zastosować u Antka
(konkretnie: co w planie, jak często, ile)
## Pewność
(mocne / średnie / słabe dowody — 1-2 zdania)
## Źródła
- tytuł — URL (tylko źródła faktycznie otwarte)
"""


def spis_ogolnej():
    w = []
    for p in sorted(WIEDZA_OGOLNA.glob("*.md")):
        nag = [l.strip("# ").strip() for l in p.read_text(encoding="utf-8").splitlines() if l.startswith("#")]
        w.append(f"{p.name}: " + " / ".join(nag[:12]))
    return "\n".join(w)


def pliki_celu():
    return sorted(KATALOG.glob("*.md")) if KATALOG.exists() else []


def wiedza_celu():
    return "\n\n".join(p.read_text(encoding="utf-8") for p in pliki_celu())


def _dziala(url):
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "Mozilla/5.0 (trener)"})
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.status < 400
    except urllib.error.HTTPError as ex:
        return ex.code in (401, 403, 405, 429)      # strona istnieje, tylko blokuje automaty
    except Exception:
        return False


def sprawdz_zrodla(tresc):
    """-> (treść z oznaczeniem linków, lista (url, ok))"""
    urle = list(dict.fromkeys(u.rstrip(".,;") for u in URL.findall(tresc)))
    with ThreadPoolExecutor(6) as ex:
        wyn = list(zip(urle, ex.map(_dziala, urle)))
    for u, ok in wyn:
        if not ok:
            tresc = tresc.replace(u, u + " (⚠️ link nie otworzył się przy sprawdzaniu)")
    return tresc, wyn


def _slug(t):
    t = t.lower()
    for a, b in zip("ąćęłńóśźż", "acelnoszz"):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:40] or "temat"


def zbadaj_temat(temat, cel, nr):
    from . import kontekst
    db = baza.polacz()
    dane = "\n".join(kontekst.ostatnie_dni(db, 7)) + "\n" + "\n".join(kontekst.agregaty(db, "tydzien", (date.today() - timedelta(weeks=8)).isoformat()))
    prompt = ZADANIE_BADANIA.format(tytul=temat["tytul"], po_co=temat["po_co"], pytania="; ".join(temat["pytania"]),
                                    cel=cel, spis=spis_ogolnej(), dane=dane)
    tresc = ai.zapytaj(prompt, narzedzia=["WebSearch", "WebFetch"], effort="medium", limit_s=900).strip()
    tresc = re.sub(r"^```(?:markdown|md)?\s*|\s*```$", "", tresc)
    if not tresc.startswith("# ") and "\n# " in tresc:    # zdanie-wstęp przed nagłówkiem
        tresc = tresc[tresc.index("\n# ") + 1:]
    tresc, zrodla = sprawdz_zrodla(tresc)
    dobre = [u for u, ok in zrodla if ok]
    if not dobre:
        log.warning("temat %s odrzucony: brak działających źródeł (%d linków)", temat["tytul"], len(zrodla))
        return {"tytul": temat["tytul"], "odrzucony": True, "zrodla": len(zrodla)}
    KATALOG.mkdir(parents=True, exist_ok=True)
    p = KATALOG / f"c{nr:02d}_{_slug(temat['tytul'])}.md"
    p.write_text(tresc + "\n", encoding="utf-8")
    return {"tytul": temat["tytul"], "plik": p.name, "zrodla": len(zrodla), "dzialajace": len(dobre)}


def postep(db, tekst):
    baza.ustaw_kv(db, "postep", {"tekst": tekst, "kiedy": baza.teraz()})


def zbadaj(db=None, prosba=""):
    """ocena bazy pod cel + wyszukanie źródeł; zastępuje poprzednie pliki celu. -> podsumowanie (też w kv 'badania')"""
    from .cel import odcisk_celow
    from .kontekst import pelny
    db = db or baza.polacz()
    u = config.ustawienia()
    from .start import tekst_ankiety
    cel = (u["cele"] + ("\n" + tekst_ankiety(u.get("ankieta")) if u.get("ankieta") else "")).strip()
    postep(db, "Sprawdzam, czy baza wiedzy pasuje do Twojego celu")
    ogolna = "\n\n".join(p.read_text(encoding="utf-8") for p in sorted(WIEDZA_OGOLNA.glob("*.md")))
    ocena = ai.zapytaj(
        "BAZA WIEDZY OGÓLNEJ:\n" + ogolna + "\n\n" + pelny(db, akt_dni=14, tygodnie=12) + f"\n\nCEL I ANKIETA:\n{cel}\n"
        + (f"\nDODATKOWO: {prosba}\n" if prosba else "")
        + "\nZADANIE: Oceń, czy baza wiedzy pasuje do tego celu (sport, dyscyplina, wiek, termin), co pokrywa, czego "
          "brakuje albo co jest za ogólne, co może nie pasować. Wybierz 2–5 tematów do zbadania w źródłach — ZAWSZE "
          "co najmniej 2, nawet gdy baza wygląda na kompletną (np. specyfika dyscypliny/wyścigu, przepisy i kategorie "
          "wiekowe, typowe obciążenia zawodników w tym wieku, testy specyficzne, taktyka/żywienie startowe).",
        SCHEMAT_OCENY, effort="medium")
    for p in pliki_celu():                         # nowe badania zastępują stare (cel mógł się zmienić)
        p.unlink()
    wyniki = []
    tematy = ocena["tematy"][:5]
    gotowe = [0]

    def jeden(a):
        nr, t = a
        try:
            w = zbadaj_temat(t, cel, nr)
        except Exception as ex:
            log.exception("badanie %s", t["tytul"])
            w = {"tytul": t["tytul"], "odrzucony": True, "blad": str(ex)[:200]}
        gotowe[0] += 1
        postep(baza.polacz(), f"Szukam źródeł: {gotowe[0]}/{len(tematy)} tematów gotowe")
        return w
    postep(db, f"Szukam źródeł w internecie: 0/{len(tematy)} tematów")
    with ThreadPoolExecutor(2) as ex:
        wyniki = list(ex.map(jeden, enumerate(tematy, 1)))
    wyn = {"kiedy": baza.teraz(), "_odcisk": odcisk_celow(), "ocena": ocena, "pliki": wyniki}
    baza.ustaw_kv(db, "badania", wyn)
    postep(db, "")
    log.info("badania: %s", [(w["tytul"], w.get("dzialajace", 0)) for w in wyniki])
    return wyn


def potrzebne(db):
    from .cel import odcisk_celow
    b = baza.kv(db, "badania")
    return not b or b.get("_odcisk") != odcisk_celow()
