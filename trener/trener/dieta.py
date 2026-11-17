"""Dziennik jedzenia: produkty (kod kreskowy -> Open Food Facts, cache w bazie), wpisy dnia, cel kcal/makro.

Cel liczy się dwuetapowo: najpierw wzór (zawsze dostępny, bezpieczny), potem raz dziennie Claude (lekki model)
koryguje go pod plan treningowy i cel. Korekta jest przycinana do bezpiecznych granic (młody sportowiec:
umiarkowany deficyt, dostępność energii >= 35 kcal/kg FFM, białko 1,6–2,4 g/kg) — zob. wiedza/07_odzywianie.md.
Masa i % tłuszczu pochodzą z dziennika Progres na portalu (http://127.0.0.1/api/progres, samo Pi = bez hasła)."""
import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from . import baza, config

log = logging.getLogger(__name__)

SCHEMAT = """
CREATE TABLE IF NOT EXISTS produkty (kod TEXT PRIMARY KEY, nazwa TEXT, marka TEXT, kcal REAL, b REAL, w REAL, t REAL,
    porcja_g REAL, zrodlo TEXT, dodano TEXT, uzyto TEXT, ile INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS jedzenie (id INTEGER PRIMARY KEY AUTOINCREMENT, dzien TEXT, czas TEXT, posilek TEXT,
    nazwa TEXT, kod TEXT, gram REAL, kcal REAL, b REAL, w REAL, t REAL);
CREATE INDEX IF NOT EXISTS jedzenie_dzien ON jedzenie (dzien);
"""
POSILKI = ["sniadanie", "drugie", "obiad", "przekaska", "kolacja"]
OFF = "https://world.openfoodfacts.org"
UA = "Trener/1.0 (prywatny dziennik jedzenia)"      # bez danych osobowych


def polacz():
    d = baza.polacz()
    d.executescript(SCHEMAT)
    return d


# ---------------------------------------------------------------- produkty
def _liczba(x):
    try:
        v = float(x)
        return v if v >= 0 else None
    except (TypeError, ValueError):
        return None


def _z_off(p, kod=None):
    n = p.get("nutriments") or {}
    kcal = _liczba(n.get("energy-kcal_100g"))
    if kcal is None and _liczba(n.get("energy_100g")) is not None:
        kcal = round(float(n["energy_100g"]) / 4.184, 1)          # kJ -> kcal
    nazwa = (p.get("product_name_pl") or p.get("product_name") or "").strip()
    if not nazwa or kcal is None:
        return None
    return {"kod": kod or p.get("code"), "nazwa": nazwa[:120], "marka": _marka(p.get("brands")),
            "kcal": round(kcal, 1), "b": round(_liczba(n.get("proteins_100g")) or 0, 1),
            "w": round(_liczba(n.get("carbohydrates_100g")) or 0, 1), "t": round(_liczba(n.get("fat_100g")) or 0, 1),
            "porcja_g": _liczba(p.get("serving_quantity")), "zrodlo": "off"}


def _pobierz(url, limit=8):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=limit) as r:
        return json.loads(r.read().decode("utf-8"))


def _marka(b):
    b = b[0] if isinstance(b, list) and b else b if isinstance(b, str) else ""
    return b.split(",")[0].strip()[:60]


POLA = "code,product_name,product_name_pl,brands,nutriments,serving_quantity"


def produkt(kod):
    """z bazy, a jak nie ma — z Open Food Facts (i zapamiętaj). None = nie znaleziono."""
    d = polacz()
    r = d.execute("SELECT * FROM produkty WHERE kod=?", ("".join(c for c in str(kod) if c.isalnum())[:20],)).fetchone()
    if r:                                                     # też ręczne (kod "r…")
        return dict(r)
    kod = "".join(c for c in str(kod) if c.isdigit())[:20]
    if not kod:
        return None
    r = d.execute("SELECT * FROM produkty WHERE kod=?", (kod,)).fetchone()
    if r:
        return dict(r)
    try:
        j = _pobierz(f"{OFF}/api/v2/product/{kod}.json?fields={POLA}")
    except urllib.error.HTTPError as ex:
        if ex.code == 404:                                    # OFF: nieznany kod
            return None
        log.warning("OFF %s: %s", kod, ex)
        raise RuntimeError("Open Food Facts nie odpowiada — wpisz produkt ręcznie") from ex
    except Exception as ex:                                   # brak sieci / OFF leży
        log.warning("OFF %s: %s", kod, ex)
        raise RuntimeError("Open Food Facts nie odpowiada — wpisz produkt ręcznie") from ex
    p = _z_off(j.get("product") or {}, kod) if j.get("status") == 1 else None
    if p:
        zapisz_produkt(d, p)
    return p


def szukaj(tekst):
    """najpierw moje produkty (ostatnio jedzone), potem Open Food Facts"""
    tekst = (tekst or "").strip()[:60]
    d = polacz()
    if not tekst:
        return [dict(r) for r in d.execute("SELECT * FROM produkty ORDER BY uzyto DESC LIMIT 25")]
    moje = [dict(r) for r in d.execute("SELECT * FROM produkty WHERE nazwa LIKE ? OR marka LIKE ? ORDER BY ile DESC LIMIT 15",
                                       (f"%{tekst}%", f"%{tekst}%"))]
    obce = []
    try:
        # search-a-licious (stare cgi/search.pl zwraca 503); tylko produkty sprzedawane w Polsce
        czyste = "".join(c if c.isalnum() or c in " -" else " " for c in tekst)
        q = urllib.parse.urlencode({"q": f'{czyste} countries_tags:"en:poland"', "page_size": 20, "fields": POLA,
                                    "sort_by": "-unique_scans_n", "langs": "pl"})
        j = _pobierz(f"https://search.openfoodfacts.org/search?{q}", limit=10)
        kody = {m["kod"] for m in moje}
        obce = [p for p in (_z_off(x) for x in j.get("hits") or []) if p and p["kod"] not in kody]
    except Exception as ex:
        log.warning("OFF szukaj: %s", ex)
    return moje + obce[:20]


def zapisz_produkt(d, p):
    kod = p.get("kod") or f"r{int(time.time() * 1000)}"     # ręczny bez kodu kreskowego
    d.execute("INSERT OR REPLACE INTO produkty (kod, nazwa, marka, kcal, b, w, t, porcja_g, zrodlo, dodano, uzyto, ile) "
              "VALUES (?,?,?,?,?,?,?,?,?,?, (SELECT uzyto FROM produkty WHERE kod=?), "
              "COALESCE((SELECT ile FROM produkty WHERE kod=?), 0))",
              (kod, p["nazwa"], p.get("marka") or "", p["kcal"], p.get("b") or 0, p.get("w") or 0, p.get("t") or 0,
               p.get("porcja_g"), p.get("zrodlo") or "reczny", baza.teraz(), kod, kod))
    d.commit()
    return kod


# ---------------------------------------------------------------- wpisy
def dodaj(b):
    """b: {dzien, posilek, gram, kod?} albo ręcznie {nazwa, kcal, b, w, t, gram?}; produkt z kodem -> makro z 100 g"""
    d = polacz()
    dzien = b.get("dzien") or date.today().isoformat()
    date.fromisoformat(dzien)
    posilek = b.get("posilek") if b.get("posilek") in POSILKI else "przekaska"
    gram = _liczba(b.get("gram"))
    if b.get("kod"):
        p = d.execute("SELECT * FROM produkty WHERE kod=?", (str(b["kod"]),)).fetchone()
        if not p or not gram or gram > 5000:
            raise ValueError("brak produktu albo zła gramatura")
        k = gram / 100
        wpis = (p["nazwa"], p["kod"], gram, p["kcal"] * k, p["b"] * k, p["w"] * k, p["t"] * k)
        d.execute("UPDATE produkty SET uzyto=?, ile=ile+1 WHERE kod=?", (baza.teraz(), p["kod"]))
    else:
        nazwa = str(b.get("nazwa") or "").strip()[:120]
        kcal = _liczba(b.get("kcal"))
        if not nazwa or kcal is None or kcal > 10000:
            raise ValueError("podaj nazwę i kcal")
        wpis = (nazwa, None, gram, kcal, _liczba(b.get("b")) or 0, _liczba(b.get("w")) or 0, _liczba(b.get("t")) or 0)
    nid = d.execute("INSERT INTO jedzenie (dzien, czas, posilek, nazwa, kod, gram, kcal, b, w, t) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (dzien, baza.teraz(), posilek, *(round(x, 1) if isinstance(x, float) else x for x in wpis))).lastrowid
    d.commit()
    return nid


def usun(nid):
    d = polacz()
    d.execute("DELETE FROM jedzenie WHERE id=?", (int(nid),))
    d.commit()


def zmien(nid, gram):
    d = polacz()
    r = d.execute("SELECT * FROM jedzenie WHERE id=?", (int(nid),)).fetchone()
    gram = _liczba(gram)
    if not r or not gram or not r["gram"]:
        raise ValueError("nie da się zmienić")
    k = gram / r["gram"]
    d.execute("UPDATE jedzenie SET gram=?, kcal=?, b=?, w=?, t=? WHERE id=?",
              (gram, round(r["kcal"] * k, 1), round(r["b"] * k, 1), round(r["w"] * k, 1), round(r["t"] * k, 1), r["id"]))
    d.commit()


def popraw_produkt(kod, p):
    """poprawka wartości na 100 g (zła baza / OFF); wpisy z tym produktem i gramaturą liczone od nowa"""
    d = polacz()
    r = d.execute("SELECT * FROM produkty WHERE kod=?", (str(kod),)).fetchone()
    if not r:
        raise ValueError("nie ma takiego produktu")
    kcal = _liczba(p.get("kcal"))
    if kcal is None or kcal > 1000:
        raise ValueError("kcal na 100 g: 0–1000")
    nowy = {"nazwa": str(p.get("nazwa") or r["nazwa"]).strip()[:120] or r["nazwa"], "kcal": kcal,
            **{k: min(_liczba(p.get(k)) or 0, 100) for k in ("b", "w", "t")},
            "porcja_g": _liczba(p.get("porcja_g")) or None}
    d.execute("UPDATE produkty SET nazwa=?, kcal=?, b=?, w=?, t=?, porcja_g=?, zrodlo='poprawiony' WHERE kod=?",
              (nowy["nazwa"], nowy["kcal"], nowy["b"], nowy["w"], nowy["t"], nowy["porcja_g"], r["kod"]))
    n = 0
    for w in d.execute("SELECT id, gram FROM jedzenie WHERE kod=? AND gram > 0", (r["kod"],)).fetchall():
        k = w["gram"] / 100
        d.execute("UPDATE jedzenie SET nazwa=?, kcal=?, b=?, w=?, t=? WHERE id=?",
                  (nowy["nazwa"], *(round(nowy[x] * k, 1) for x in ("kcal", "b", "w", "t")), w["id"]))
        n += 1
    d.commit()
    return {**dict(d.execute("SELECT * FROM produkty WHERE kod=?", (r["kod"],)).fetchone()), "przeliczone": n}


# ---------------------------------------------------------------- zdjęcia (Claude czyta obraz)
_LICZBA = {"type": "number", "minimum": 0}
ETYKIETA = {"type": "object", "additionalProperties": False, "required": ["czytelne", "nazwa", "kcal", "b", "w", "t"],
            "properties": {"czytelne": {"type": "boolean"}, "nazwa": {"type": "string"}, "kcal": _LICZBA,
                           "b": _LICZBA, "w": _LICZBA, "t": _LICZBA, "porcja_g": _LICZBA, "uwagi": {"type": "string"}}}


def z_etykiety(jpg):
    """zdjęcie tabeli wartości odżywczych -> wartości na 100 g (do sprawdzenia w formularzu)"""
    from . import ai
    w = ai.zapytaj(
        "Przeczytaj plik etykieta.jpg: zdjęcie tabeli wartości odżywczych produktu spożywczego. Podaj wartości "
        "NA 100 g (albo 100 ml): kcal (jeśli jest tylko kJ, przelicz /4,184), białko b, węglowodany w (ogółem, nie "
        "„w tym cukry”), tłuszcz t (ogółem, nie „w tym nasycone”), w gramach. Jeśli tabela podaje tylko porcję, "
        "przelicz na 100 g i wpisz porcja_g. nazwa: nazwa produktu, jeśli widać na zdjęciu, inaczej pusty tekst. "
        "Nie zgaduj: gdy tabela jest nieczytelna albo to nie tabela wartości odżywczych, czytelne=false i opisz w "
        "uwagi. uwagi: krótko po polsku, tylko jeśli coś niepewne.",
        schemat=ETYKIETA, effort="low", limit_s=120, pliki={"etykieta.jpg": jpg})
    if not w.get("czytelne"):
        raise ValueError(w.get("uwagi") or "nie widzę tabeli wartości odżywczych — zrób ostrzejsze zdjęcie")
    return {k: round(float(w.get(k) or 0), 1) for k in ("kcal", "b", "w", "t")} | {
        "nazwa": (w.get("nazwa") or "").strip()[:120], "porcja_g": w.get("porcja_g") or None, "uwagi": w.get("uwagi") or ""}


POSILEK = {"type": "object", "additionalProperties": False, "required": ["pozycje", "komentarz", "pewnosc"],
           "properties": {
               "pozycje": {"type": "array", "maxItems": 15, "items": {
                   "type": "object", "additionalProperties": False, "required": ["nazwa", "gram", "kcal", "b", "w", "t"],
                   "properties": {"nazwa": {"type": "string"}, "gram": _LICZBA, "kcal": _LICZBA,
                                  "b": _LICZBA, "w": _LICZBA, "t": _LICZBA}}},
               "komentarz": {"type": "string"},
               "pewnosc": {"type": "string", "enum": ["niska", "srednia", "wysoka"]}}}


def szacuj_posilek(jpg, opis):
    """zdjęcie gotowego posiłku i/lub opis -> lista składników z gramami i makro; AI sprawdza opis ze zdjęciem"""
    from . import ai
    opis = (opis or "").strip()[:800]
    if not jpg and not opis:
        raise ValueError("dodaj zdjęcie albo opis")
    d = polacz()
    moje = [f"{r['nazwa']}: {r['kcal']:g} kcal, B {r['b']:g}, W {r['w']:g}, T {r['t']:g} /100 g"
            for r in d.execute("SELECT * FROM produkty ORDER BY ile DESC LIMIT 40")]
    prompt = (
        ("Plik posilek.jpg to zdjęcie gotowego posiłku Antka. Przeczytaj go. " if jpg else "Nie ma zdjęcia, tylko opis. ")
        + f"Opis od Antka (wie tylko mniej więcej, co tam jest): «{opis or 'brak opisu'}».\n\n"
        "Oszacuj, z czego składa się posiłek: rozbij na składniki (z tłuszczem do smażenia, sosami, dodatkami), "
        "dla każdego gramaturę porcji i kcal, białko b, węgle w, tłuszcz t w gramach DLA TEJ PORCJI (nie na 100 g). "
        "Gramaturę oceniaj po wielkości talerza, sztućców, dłoni i typowych porcji. Liczby mają się zgadzać: "
        "kcal ≈ 4·b + 4·w + 9·t.\n"
        + ("SPRAWDŹ opis ze zdjęciem: jeśli coś z opisu nie pasuje do zdjęcia (inna ilość, czegoś nie widać, widać "
           "coś, czego nie wymienił, np. sos, olej, panierka), oprzyj się na zdjęciu i napisz to wprost w komentarzu. "
           if jpg else "")
        + "komentarz: 1–3 krótkie zdania po polsku: co jest najmniej pewne i co sprawdzić/zważyć; bez oceniania "
        "jedzenia. pewnosc: jak dokładne jest oszacowanie.\n"
        + ("Produkty, które Antek ma w bazie (wartości na 100 g, użyj ich, gdy pasują):\n" + "\n".join(moje) if moje else ""))
    w = ai.zapytaj(prompt, schemat=POSILEK, ciezki=True, effort="medium", limit_s=240,
                   pliki={"posilek.jpg": jpg} if jpg else None)
    poz = []
    for p in w.get("pozycje") or []:
        x = {k: round(float(p.get(k) or 0), 1) for k in ("gram", "kcal", "b", "w", "t")}
        if str(p.get("nazwa") or "").strip() and x["kcal"] <= 5000:
            poz.append({"nazwa": str(p["nazwa"]).strip()[:120], **x})
    return {"pozycje": poz, "komentarz": (w.get("komentarz") or "")[:600], "pewnosc": w.get("pewnosc") or "srednia"}


def suma(d, dzien):
    r = d.execute("SELECT COUNT(*) n, SUM(kcal) kcal, SUM(b) b, SUM(w) w, SUM(t) t FROM jedzenie WHERE dzien=?", (dzien,)).fetchone()
    return {k: round(r[k] or 0) for k in ("kcal", "b", "w", "t")} | {"n": r["n"]}


def dzien(dzien_):
    d = polacz()
    wpisy = [dict(r) for r in d.execute("SELECT * FROM jedzenie WHERE dzien=? ORDER BY id", (dzien_,))]
    return {"dzien": dzien_, "wpisy": wpisy, "suma": suma(d, dzien_), "cel": cel(d, dzien_), "posilki": POSILKI}


def historia(dni=30):
    d = polacz()
    od = (date.today() - timedelta(days=dni - 1)).isoformat()
    sumy = {r["dzien"]: dict(r) for r in d.execute(
        "SELECT dzien, ROUND(SUM(kcal)) kcal, ROUND(SUM(b)) b, ROUND(SUM(w)) w, ROUND(SUM(t)) t FROM jedzenie "
        "WHERE dzien >= ? GROUP BY dzien", (od,))}
    cele = {}
    for r in d.execute("SELECT klucz, wartosc FROM kv WHERE klucz >= ? AND klucz LIKE 'makro_cel_%'", ("makro_cel_" + od,)):
        try:
            cele[r[0][10:]] = json.loads(r[1]).get("kcal")
        except (ValueError, AttributeError):
            pass
    return [{**sumy[k], "cel": cele.get(k)} for k in sorted(sumy)]


# ---------------------------------------------------------------- masa ciała (Progres na portalu)
_progres = {"t": 0, "d": None}


def progres(swiezy=False):
    """dane.json Progresu z portalu (cache 5 min); None gdy portal nie odpowiada"""
    if swiezy or time.time() - _progres["t"] > 300:
        try:
            with urllib.request.urlopen("http://127.0.0.1/api/progres", timeout=5) as r:
                _progres.update(d=json.loads(r.read().decode()), t=time.time())
        except Exception as ex:
            log.warning("progres: %s", ex)
    return _progres["d"]


def sklad_ciala():
    """ostatnia masa i % tłuszczu (każde z najnowszego wpisu, który je ma) + trend masy z 4 tygodni"""
    p = progres() or {}
    wpisy = sorted((p.get("wpisy") or {}).items())
    masa = next(((k, v["masa"]) for k, v in reversed(wpisy) if v.get("masa")), None)
    fat = next(((k, v["fat"]) for k, v in reversed(wpisy) if v.get("fat")), None)
    trend = None
    if masa:
        od = (date.fromisoformat(masa[0]) - timedelta(days=28)).isoformat()
        stare = [(k, v["masa"]) for k, v in wpisy if v.get("masa") and od <= k <= (date.fromisoformat(masa[0]) - timedelta(days=10)).isoformat()]
        if stare:
            k0, m0 = stare[0]
            tyg = (date.fromisoformat(masa[0]) - date.fromisoformat(k0)).days / 7
            trend = round((masa[1] - m0) / tyg, 2) if tyg else None
    return {"masa": masa[1] if masa else None, "masa_dzien": masa[0] if masa else None,
            "fat": fat[1] if fat else None, "fat_dzien": fat[0] if fat else None, "trend_kg_tydz": trend}


# ---------------------------------------------------------------- cel dnia
KCAL_MIN = {"rower": 9.0, "bieg": 11.0, "silka": 6.0, "inne": 7.0}


def _trening_kcal(d, dzien_, masa):
    """wydatek na trening: zrobione (Garmin) + zaplanowane, jeszcze niezrobione (szacunek)"""
    from . import budowa, kontekst
    zrobione, kat_zrob = 0, set()
    for r in d.execute("SELECT typ, dane FROM aktywnosci WHERE dzien=?", (dzien_,)):
        j = baza.rozpakuj(r[1]) or {}
        zrobione += j.get("calories") or 0
        kat_zrob.add(kontekst.kategoria(r[0]))
    plan, opis = 0, []
    ftp = ((baza.kv(d, "strefy", {}) or {}).get("ftp") or {}).get("functionalThresholdPower")
    for r in d.execute("SELECT * FROM plan WHERE dzien=? AND stan NOT IN ('usuniety','do_usuniecia')", (dzien_,)):
        t = dict(r)
        if t["sport"] == "odpoczynek":
            continue
        t["kroki"] = json.loads(t["kroki"] or "[]")
        mn = budowa.czas_min(t) or 0
        opis.append(f"{t['sport']} {mn} min: {t['tytul']}")
        if t["sport"] in kat_zrob:
            continue
        if t["sport"] == "rower" and ftp:
            plan += mn * 60 * ftp * 0.62 / 1000                 # ~kJ ≈ kcal przy sprawności ~24%
        elif t["sport"] == "bieg" and masa:
            plan += mn * masa * 0.16
        else:
            plan += mn * KCAL_MIN.get(t["sport"], 7)
    return round(zrobione + plan), opis, round(zrobione)


NEAT = 0.45          # ruch poza treningiem w modelu: RMR × 1,45


def ruch_garmin(d, dzien_, rmr, zrobione):
    """aktywne kcal z Garmina ponad to, co model już zakłada (ruch poza treningiem + zrobione treningi); tylko w górę"""
    kcal_akt = (baza.dzien(d, dzien_) or {}).get("kcal_akt") or 0
    nad = kcal_akt - NEAT * rmr - zrobione
    return round(nad) if nad >= 100 else 0, round(kcal_akt)


def wzor(d, dzien_):
    """bezpieczny cel z wzoru (Cunningham + NEAT ucznia + trening; deficyt ≤ 500 kcal i ≤ 20%, EA ≥ 35 kcal/kg FFM)"""
    s = sklad_ciala()
    masa = s["masa"] or 70.0
    fat = s["fat"] if s["fat"] and 5 <= s["fat"] <= 50 else None
    ffm = masa * (1 - (fat if fat else 18) / 100)
    rmr = 500 + 22 * ffm
    trening, opis, zrobione = _trening_kcal(d, dzien_, masa)
    ekstra, kcal_akt = ruch_garmin(d, dzien_, rmr, zrobione)
    tdee = rmr * (1 + NEAT) + trening + ekstra
    deficyt = min(500, 0.2 * tdee)
    kcal = tdee - deficyt
    kcal = max(kcal, 35 * ffm + trening + ekstra)              # dostępność energii — RED-S
    b = min(2.0 * masa, 2.6 * ffm)
    t = max(0.9 * masa, 0.25 * kcal / 9)
    w = max((kcal - 4 * b - 9 * t) / 4, 3 * masa if trening > 300 else 2.5 * masa)
    kcal = 4 * b + 4 * w + 9 * t
    return {"kcal": round(kcal, -1), "b": round(b), "w": round(w), "t": round(t), "tdee": round(tdee, -1),
            "trening_kcal": trening, "trening": opis, "ruch_ekstra": ekstra, "kcal_akt_garmin": kcal_akt, "masa": s["masa"], "fat": s["fat"], "ffm": round(ffm, 1),
            "trend_kg_tydz": s["trend_kg_tydz"], "zrodlo": "wzor"}


def _przytnij(x, w):
    """korekta Claude w granicach bezpieczeństwa wokół wzoru"""
    masa, ffm = w["masa"] or 70.0, w["ffm"]
    kcal = max(min(x["kcal"], w["tdee"] - 150), w["kcal"] * 0.88, 35 * ffm + w["trening_kcal"] + w.get("ruch_ekstra", 0))
    b = min(max(x["b"], 1.6 * masa), 2.4 * masa)
    t = max(x["t"], 0.8 * masa)
    wg = max((kcal - 4 * b - 9 * t) / 4, 2.5 * masa)
    return {"kcal": round(4 * b + 4 * wg + 9 * t, -1), "b": round(b), "w": round(wg), "t": round(t)}


SCHEMAT_AI = {"type": "object", "properties": {
    "kcal": {"type": "number"}, "b": {"type": "number", "description": "białko g"},
    "w": {"type": "number", "description": "węglowodany g"}, "t": {"type": "number", "description": "tłuszcz g"},
    "komentarz": {"type": "string", "description": "1–3 zdania do Antka: dlaczego tyle dziś i na co uważać"},
    "pory": {"type": "string", "description": "krótko: kiedy węgle/białko względem treningu"}},
    "required": ["kcal", "b", "w", "t", "komentarz"]}
_liczy = set()
_lock = threading.Lock()


def przelicz(dzien_=None):
    """cel dnia z Claude (lekki model), zapis w kv makro_cel_<dzien>"""
    from . import ai, cel as celm
    dzien_ = dzien_ or date.today().isoformat()
    with _lock:
        if dzien_ in _liczy:
            return {"stan": "już liczę"}
        _liczy.add(dzien_)
    try:
        d = polacz()
        w = wzor(d, dzien_)
        u = config.ustawienia()
        ost = historia(8)
        prompt = "\n".join([
            "Jesteś trenerem i dietetykiem sportowym Antka (nastolatek, uczeń technikum, kolarz). Ustal jego cel "
            "jedzenia na dzień " + dzien_ + ": kcal i makro (g). Zwięźle, po polsku.",
            "ZASADY ŻYWIENIA (trzymaj się ich):\n" + (celm.WIEDZA / "07_odzywianie.md").read_text(encoding="utf-8"),
            "MŁODY SPORTOWIEC:\n" + (celm.WIEDZA / "06_mlody_sportowiec.md").read_text(encoding="utf-8"),
            f"CELE ANTKA: {u.get('cele') or '-'}",
            f"MAKROCYKL:\n{celm.tekst(celm.makrocykl(d))}",
            "SKŁAD CIAŁA: " + json.dumps({k: w[k] for k in ("masa", "fat", "ffm", "trend_kg_tydz")}, ensure_ascii=False),
            "TRENING TEGO DNIA: " + ("; ".join(w["trening"]) or "wolne") + f" (szac. wydatek {w['trening_kcal']} kcal)",
            f"GARMIN DZIŚ: aktywne kcal {w['kcal_akt_garmin']}, ponad założony ruch i treningi: {w['ruch_ekstra']} kcal "
            "(już doliczone do wydatku i wzoru)",
            "JEDZENIE OSTATNICH DNI (suma z dziennika / cel): " + json.dumps(ost, ensure_ascii=False),
            "PROPOZYCJA ZE WZORU (bezpieczna baza; możesz korygować pod trening i trend masy, ale nie schodź poniżej "
            "progów z zasad): " + json.dumps({k: w[k] for k in ("kcal", "b", "w", "t", "tdee")}, ensure_ascii=False)])
        x = ai.zapytaj(prompt, SCHEMAT_AI, effort="low", limit_s=180)
        wyn = {**w, **_przytnij(x, w), "komentarz": x.get("komentarz", ""), "pory": x.get("pory", ""), "zrodlo": "trener",
               "policzono": baza.teraz()}
        baza.ustaw_kv(d, "makro_cel_" + dzien_, wyn)
        return wyn
    finally:
        with _lock:
            _liczy.discard(dzien_)


def aktualizuj(d, nowe_aktywnosci=()):
    """z cyklu (co 20 min): nowy trening dziś → trener liczy cel od nowa; co godzinę dolicza nowe aktywne kcal z Garmina"""
    dzis = date.today().isoformat()
    c = baza.kv(d, "makro_cel_" + dzis)
    if not c or dzis in _liczy:
        return None                      # celu jeszcze nie ma — policzy się przy otwarciu
    if any((a.get("startTimeLocal") or "")[:10] == dzis for a in nowe_aktywnosci):
        log.info("dieta: nowy trening — przeliczam cel")
        return przelicz(dzis)
    ost = baza.kv(d, "makro_garmin_spr") or ""
    if ost > (datetime.now() - timedelta(minutes=55)).isoformat(timespec="seconds"):
        return None
    baza.ustaw_kv(d, "makro_garmin_spr", baza.teraz())
    w = wzor(d, dzis)
    roznica = w["ruch_ekstra"] - (c.get("ruch_ekstra") or 0)
    if roznica < 50:
        return None
    # dodatkowy ruch → głównie węgle (paliwo), białko i tłuszcz bez zmian
    nowy = {**c, "kcal": round(c["kcal"] + roznica, -1), "w": round(c["w"] + roznica / 4),
            "tdee": round(c.get("tdee", 0) + roznica, -1), "ruch_ekstra": w["ruch_ekstra"],
            "kcal_akt_garmin": w["kcal_akt_garmin"], "garmin_dodano": (c.get("garmin_dodano") or 0) + roznica,
            "garmin_czas": baza.teraz()}
    baza.ustaw_kv(d, "makro_cel_" + dzis, nowy)
    log.info("dieta: +%d kcal z Garmina", roznica)
    return nowy


def cel(d, dzien_):
    """cel z trenera (kv), a do tego czasu ze wzoru; liczy=True gdy trener jeszcze liczy"""
    c = baza.kv(d, "makro_cel_" + dzien_)
    if c:
        return c
    return {**wzor(d, dzien_), "liczy": dzien_ in _liczy}


def potrzebny_przelicz(d, dzien_):
    return not baza.kv(d, "makro_cel_" + dzien_) and dzien_ not in _liczy and dzien_ >= date.today().isoformat()


def tekst(db, dni=7):
    """do kontekstu trenera: cel dziś, ostatnie dni jedzenia, skład ciała"""
    s = sklad_ciala()
    try:
        d = polacz()
        h = historia(dni)
        c = baza.kv(d, "makro_cel_" + date.today().isoformat()) or wzor(d, date.today().isoformat())
    except Exception as ex:                                      # nie psuj kontekstu przez dietę
        log.warning("dieta.tekst: %s", ex)
        return ""
    w = [f"SKŁAD CIAŁA (Progres): masa {s['masa']} kg ({s['masa_dzien']}), tłuszcz {s['fat']}% ({s['fat_dzien']}), "
         f"trend {s['trend_kg_tydz']} kg/tydz",
         f"CEL JEDZENIA DZIŚ: {c['kcal']} kcal, B {c['b']} g, W {c['w']} g, T {c['t']} g"]
    w += [f"{x['dzien']}: zjadł {x['kcal']:.0f} kcal (B {x['b']:.0f} W {x['w']:.0f} T {x['t']:.0f})"
          + (f" / cel {x['cel']}" if x.get("cel") else "") for x in h]
    if not h:
        w.append("(dziennik jedzenia pusty — Antek jeszcze nie wpisuje)")
    return "\n".join(w)
