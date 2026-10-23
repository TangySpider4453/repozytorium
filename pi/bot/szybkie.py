"""
Szybkie odpowiedzi bez AI: typowe pytania (plan lekcji, sprawdziany, zadania, budziki, serwer, godzina…) rozpoznane
lokalnie i odpowiedziane od razu z danych na Pi (ułamek sekundy zamiast kilkunastu sekund z Claude).

  odpowiedz(tekst, dane) -> (intencja, odpowiedź) albo None     dane: słownik funkcji z bota (patrz serwerek_bot.py)
  naucz(tekst, intencja)                                        Claude oznaczył pytanie znacznikiem [[INTENCJA: …]]:
                                                                to sformułowanie trafia do ~/bot/szybkie_nauczone.json
                                                                i następnym razem (albo podobne) obejdzie się bez AI
Rozpoznanie: 1) wzorce (setki sformułowań, test: pi/bot/test_szybkie.py), 2) nauczone zdania (podobieństwo słów
i trigramów >= PROG). Odpowiedzi krótkie, bez emotek na początku (dobre też do czytania przez telefon).
"""
import json
import re
import threading
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

NAUCZONE = Path(__file__).resolve().parent / "szybkie_nauczone.json"
PROG = 0.82
LOCK = threading.Lock()
DNI = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
DNI_N = {"poniedzialek": 0, "wtorek": 1, "sroda": 2, "srode": 2, "czwartek": 3, "piatek": 4, "sobota": 5, "sobote": 5,
         "niedziela": 6, "niedziele": 6}
PRZEDMIOTY = {   # skróty i odmiany -> fragment nazwy w planie
    "matma": "matematyka", "matematyk": "matematyka", "matematyka": "matematyka", "matematyki": "matematyka", "matme": "matematyka",
    "polski": "polski", "polskiego": "polski", "polak": "polski", "polaka": "polski",
    "angielski": "angielski", "angielskiego": "angielski", "angol": "angielski", "angola": "angielski", "ang": "angielski",
    "niemiecki": "niemiecki", "niemieckiego": "niemiecki", "niemiec": "niemiecki", "niemca": "niemiecki",
    "fizyka": "fizyka", "fizyki": "fizyka", "fiza": "fizyka", "fizy": "fizyka", "fize": "fizyka",
    "chemia": "chemia", "chemii": "chemia", "chemie": "chemia", "chema": "chemia",
    "biologia": "biologia", "biologii": "biologia", "biola": "biologia", "bioli": "biologia",
    "historia": "historia", "historii": "historia", "historie": "historia", "hista": "historia", "histy": "historia",
    "geografia": "geografia", "geografii": "geografia", "geografie": "geografia", "gegra": "geografia", "geo": "geografia",
    "wf": "wychowanie fizyczne", "wfu": "wychowanie fizyczne", "wuef": "wychowanie fizyczne", "wfy": "wychowanie fizyczne",
    "informatyka": "informatyka", "infa": "informatyka", "informatyki": "informatyka",
    "religia": "religia", "religii": "religia", "religie": "religia",
    "robotyka": "robotyk", "robotyki": "robotyk", "programowanie": "programowanie", "programowania": "programowanie",
    "montaz": "montaż", "montazu": "montaż", "edukacja obywatelska": "obywatelska", "eob": "obywatelska", "wos": "obywatelska",
    "edukacja zdrowotna": "zdrowotna", "zdrowotna": "zdrowotna", "zdrowotnej": "zdrowotna", "edb": "bezpieczeństwa",
    "matematyke": "matematyka", "matematyce": "matematyka", "fizyke": "fizyka", "fizyce": "fizyka", "biologie": "biologia",
    "geografie": "geografia", "informatyke": "informatyka", "polskim": "polski", "angielskim": "angielski",
    "niemieckim": "niemiecki", "wfie": "wychowanie fizyczne", "wf ie": "wychowanie fizyczne", "chemii ": "chemia",
    "diagnostyka": "diagnostyka", "diagnostyki": "diagnostyka", "elektronika": "elektron", "mechanika": "mechani",
}


def norm(t):
    t = unicodedata.normalize("NFKD", (t or "").lower().replace("ł", "l"))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9: ]+", " ", t)
    t = re.sub(r"\b(prosze|pls|plis|hej|siema|czesc|serwerku|serwerek|claude|a|no|to|powiedz mi|powiedz|sprawdz|ej|"
               r"daj znac|mi|moze|wiesz|czy wiesz|prosze cie|szybko|tylko|w ogole)\b", " ", t)
    return " ".join(t.split())


# ---------------------------------------------------------------- dzień w pytaniu
def dzien_z(t, domyslny):
    """„dziś/jutro/pojutrze/w piątek/w przyszły poniedziałek” -> date; brak -> domyslny()"""
    d = date.today()
    if re.search(r"\b(dzis|dzisiaj|teraz)\b", t):
        return d
    if re.search(r"\bpojutrze\b", t):
        return d + timedelta(days=2)
    if re.search(r"\bjutr\w*\b", t):
        return d + timedelta(days=1)
    m = re.search(r"\b(poniedzialek|wtorek|sroda|srode|czwartek|piatek|sobota|sobote|niedziela|niedziele)\b", t)
    if m:
        dni = (DNI_N[m.group(1)] - d.weekday()) % 7
        if re.search(r"\b(przyszl\w*|nastepn\w*)\b", t) and dni < 7:
            dni += 7 if dni else 7
        return d + timedelta(days=dni)
    return domyslny()


def nazwa_dnia(d):
    dz = (d - date.today()).days
    return {0: "dziś", 1: "jutro", 2: "pojutrze"}.get(dz) or f"w {DNI[d.weekday()]} {d.day}.{d.month:02d}".replace("w środa", "w środę") \
        .replace("w sobota", "w sobotę").replace("w niedziela", "w niedzielę")


def przedmiot_z(t):
    for k in sorted(PRZEDMIOTY, key=len, reverse=True):
        if re.search(rf"\b{k}\b", t):
            return PRZEDMIOTY[k]
    return None


# ---------------------------------------------------------------- odpowiedzi (każda: (t, dane) -> tekst)
def _lekcje(dane, d):
    return [x for x in dane["plan"]() if x["data"] == d.isoformat()]


def _odbywa(lek):
    return [x for x in lek if x["status"] != "odwołana"]


def _nastepny_dzien_szkolny(dane):
    """dziś, jeśli lekcje jeszcze trwają; inaczej najbliższy dzień z lekcjami"""
    teraz = datetime.now()
    for i in range(0, 10):
        d = date.today() + timedelta(days=i)
        lek = _odbywa(_lekcje(dane, d))
        if lek and (i > 0 or lek[-1]["do"] > teraz.strftime("%H:%M")):
            return d
    return date.today() + timedelta(days=1)


def pierwsza_lekcja(t, dane):
    d = dzien_z(t, lambda: _nastepny_dzien_szkolny(dane))
    lek = _odbywa(_lekcje(dane, d))
    if not lek:
        return f"{nazwa_dnia(d).capitalize()} nie masz lekcji."
    x = lek[0]
    odw = [y for y in _lekcje(dane, d) if y["status"] == "odwołana" and y["od"] < x["od"]]
    return (f"{nazwa_dnia(d).capitalize()} zaczynasz o {x['od']}: {x['przedmiot']}, sala {x['sala']}."
            + (f" Wcześniejsze odwołane: {', '.join(y['przedmiot'] for y in odw)}." if odw else ""))


def ostatnia_lekcja(t, dane):
    d = dzien_z(t, lambda: _nastepny_dzien_szkolny(dane))
    lek = _odbywa(_lekcje(dane, d))
    if not lek:
        return f"{nazwa_dnia(d).capitalize()} nie masz lekcji."
    return f"{nazwa_dnia(d).capitalize()} kończysz o {lek[-1]['do']} ({lek[-1]['przedmiot']})."


def ile_lekcji(t, dane):
    d = dzien_z(t, lambda: _nastepny_dzien_szkolny(dane))
    lek = _odbywa(_lekcje(dane, d))
    if not lek:
        return f"{nazwa_dnia(d).capitalize()} nie masz lekcji."
    n = len(lek)
    slowo = "lekcja" if n == 1 else "lekcje" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "lekcji"
    return f"{nazwa_dnia(d).capitalize()} {n} {slowo}, {lek[0]['od']}–{lek[-1]['do']}."


def plan_dnia(t, dane):
    d = dzien_z(t, lambda: _nastepny_dzien_szkolny(dane))
    lek = _lekcje(dane, d)
    if not lek:
        return f"{nazwa_dnia(d).capitalize()} nie masz lekcji."
    return f"{nazwa_dnia(d).capitalize()}: " + "; ".join(
        f"{x['od']} {x['przedmiot']}" + (" (odwołana)" if x["status"] == "odwołana" else f" (zastępstwo, sala {x['sala']})"
                                         if x["status"] == "zastępstwo" else f" ({x['sala']})") for x in lek) + "."


def teraz_lekcja(t, dane):
    teraz = datetime.now().strftime("%H:%M")
    lek = _odbywa(_lekcje(dane, date.today()))
    trwa = [x for x in lek if x["od"] <= teraz < x["do"]]
    nast = [x for x in lek if x["od"] > teraz]
    if re.search(r"\b(nastepn\w*|potem|zaraz|kolejn\w*)\b", t) or not trwa:
        if not nast:
            return "Dziś nie masz już lekcji." if lek else "Dziś nie masz lekcji."
        x = nast[0]
        return f"Następna: {x['przedmiot']} o {x['od']}, sala {x['sala']}" + (" (zastępstwo)." if x["status"] == "zastępstwo" else ".")
    x = trwa[0]
    return f"Teraz {x['przedmiot']} do {x['do']}, sala {x['sala']}." + (f" Potem {nast[0]['przedmiot']} o {nast[0]['od']} ({nast[0]['sala']})." if nast else " To ostatnia.")


def sala(t, dane):
    p = przedmiot_z(t)
    if not p:
        return teraz_lekcja("nastepna", dane)
    d = dzien_z(t, lambda: date.today())
    for dd in [d] + [date.today() + timedelta(days=i) for i in range(1, 8)]:
        x = next((x for x in _odbywa(_lekcje(dane, dd)) if p in x["przedmiot"].lower()), None)
        if x:
            return f"{x['przedmiot'].capitalize()} {nazwa_dnia(dd)} o {x['od']}: sala {x['sala']}."
    return f"Nie widzę {p} w planie na najbliższy tydzień."


def kiedy_przedmiot(t, dane):
    p = przedmiot_z(t)
    if not p:
        return None
    if re.search(r"\b(dzis|dzisiaj|jutr\w*|pojutrze|poniedzialek|wtorek|sroda|srode|czwartek|piatek)\b", t):
        d = dzien_z(t, lambda: date.today())
        lek = [x for x in _odbywa(_lekcje(dane, d)) if p in x["przedmiot"].lower()]
        return (f"Tak, {nazwa_dnia(d)} {lek[0]['przedmiot']} o " + ", ".join(x["od"] for x in lek) + f" (sala {lek[0]['sala']}).") if lek \
            else f"Nie, {nazwa_dnia(d)} nie ma w planie: {p}."
    for i in range(0, 14):
        dd = date.today() + timedelta(days=i)
        lek = [x for x in _odbywa(_lekcje(dane, dd)) if p in x["przedmiot"].lower() and (i or x["od"] > datetime.now().strftime("%H:%M"))]
        if lek:
            return f"Najbliższa {lek[0]['przedmiot']}: {nazwa_dnia(dd)} o {lek[0]['od']}, sala {lek[0]['sala']}."
    return f"Nie widzę {p} w planie na najbliższe 2 tygodnie."


def zmiany(t, dane):
    zm = [x for x in dane["plan"]() if x["status"] != "lekcja" and x["data"] >= date.today().isoformat()]
    if re.search(r"\b(dzis|dzisiaj|jutr\w*|pojutrze|poniedzialek|wtorek|sroda|srode|czwartek|piatek)\b", t):
        d = dzien_z(t, lambda: date.today())
        zm = [x for x in zm if x["data"] == d.isoformat()]
    if not zm:
        return "Nie ma zastępstw ani odwołanych lekcji."
    return "; ".join(f"{nazwa_dnia(date.fromisoformat(x['data']))} {x['od']} " +
                     (f"{x['przedmiot']} odwołana" if x["status"] == "odwołana" else
                      f"{x.get('zamiast') or 'lekcja'} → {x['przedmiot']} ({x['sala']})") for x in zm[:8]) + "."


def sprawdziany_odp(t, dane):
    spr = [x for x in dane["sprawdziany"]() if x["data"] >= date.today().isoformat()]
    p = przedmiot_z(t)
    if p:
        spr = [x for x in spr if p in x["przedmiot"].lower()]
    if re.search(r"\b(dzis|dzisiaj|jutr\w*|pojutrze|poniedzialek|wtorek|sroda|srode|czwartek|piatek|tydzien|tygodniu)\b", t):
        if re.search(r"\btydz", t):
            spr = [x for x in spr if x["data"] <= (date.today() + timedelta(days=7)).isoformat()]
        else:
            d = dzien_z(t, lambda: date.today())
            spr = [x for x in spr if x["data"] == d.isoformat()]
            if not spr:
                return f"{nazwa_dnia(d).capitalize()} nic nie piszesz" + (f" z {p}." if p else ".")
    if not spr:
        return "Nie ma zapowiedzianych sprawdzianów" + (f" z {p}." if p else ".")
    if re.search(r"\b(najblizsz\w*|nastepn\w*|kolejn\w*)\b", t) or p:
        spr = spr[:1]
    krotko = lambda t: t if len(t) <= 70 else t[:70].rsplit(" ", 1)[0] + "…"
    return "; ".join(f"{x['rodzaj'].capitalize()}: {x['przedmiot']}, {nazwa_dnia(date.fromisoformat(x['data']))}"
                     + (f" o {x['godzina']}" if x.get("godzina") else "") + (f" ({krotko(x['tematyka'].split(chr(10))[0])})" if x.get("tematyka") else "")
                     for x in spr[:6]) + "."


def zadania_domowe_odp(t, dane):
    zd = [x for x in dane["zadania_domowe"]() if not x.get("zrobione") and (x.get("termin") or "9") >= date.today().isoformat()]
    if re.search(r"\b(dzis|dzisiaj|jutr\w*|pojutrze|poniedzialek|wtorek|sroda|srode|czwartek|piatek)\b", t):
        d = dzien_z(t, lambda: date.today())
        zd = [x for x in zd if x.get("termin") == d.isoformat()]
    if not zd:
        return "Nie masz zadań domowych do zrobienia."
    return "; ".join(f"{x['przedmiot']} na {nazwa_dnia(date.fromisoformat(x['termin']))}: {x['tresc']}" for x in zd[:6]) + "."


def todo_odp(t, dane):
    zad = dane["todo"]()
    if re.search(r"\b(dzis|dzisiaj)\b", t):
        zad = [z for z in zad if not z.get("termin") or z["termin"][:10] <= date.today().isoformat()]
    if not zad:
        return "Nic nie czeka na liście zadań."
    return f"Do zrobienia ({len(zad)}): " + "; ".join(z["tekst"] + (f" ({z['termin'][11:16]})" if z.get("termin") and z["termin"][:10] == date.today().isoformat() else "")
                                                     for z in zad[:8]) + "."


def budzik_odp(t, dane):
    b = dane["budziki"]()
    if not b:
        return "Nie masz ustawionego budzika."
    return "Budzik: " + "; ".join(b[:4]) + "."


def godzina(t, dane):
    n = datetime.now()
    return f"Jest {n.strftime('%H:%M')}."


def data_dzis(t, dane):
    n = datetime.now()
    return f"Dziś {DNI[n.weekday()]}, {n.day}.{n.month:02d}.{n.year}."


def serwer(t, dane):
    return dane["serwer"]()


def minecraft(t, dane):
    return dane["minecraft"]()


def poczta_odp(t, dane):
    return dane["poczta"]()


def autobus(t, dane):
    m = re.search(r"\b(?:z|ze|spod|od)\s+([a-z0-9 ]{3,40}?)(?:\s+(?:jedzie|odjezdza|bedzie|najblizszy|najblizsza))?$", t)
    return dane["odjazdy"](m.group(1) if m else "tu")


def do_domu(t, dane):
    return dane["trasa"]("dom")


INTENCJE = {
    "pierwsza_lekcja": pierwsza_lekcja, "ostatnia_lekcja": ostatnia_lekcja, "ile_lekcji": ile_lekcji, "plan_dnia": plan_dnia,
    "teraz_lekcja": teraz_lekcja, "sala": sala, "kiedy_przedmiot": kiedy_przedmiot, "zmiany": zmiany,
    "sprawdziany": sprawdziany_odp, "zadania_domowe": zadania_domowe_odp, "todo": todo_odp, "budzik": budzik_odp,
    "godzina": godzina, "data": data_dzis, "serwer": serwer, "minecraft": minecraft, "poczta": poczta_odp,
    "autobus": autobus, "do_domu": do_domu,
}

# ---------------------------------------------------------------- wzorce
# Dopasowanie na tekście po norm() (bez polskich znaków) i BEZ określeń dnia („jutro”, „w piątek”…): dzień odczytuje
# potem odpowiedź z pełnego tekstu, więc „o której jutro zaczynam” = „o której zaczynam” + jutro.
DZIEN_RE = re.compile(r"\b(?:na|w|we|od|do|z)?\s*(?:dzis|dzisiaj|teraz rano|jutro|jutra|pojutrze|(?:przyszl\w+|nastepn\w+)\s+(?:poniedzialek|wtorek|srode|sroda|czwartek|piatek)|"
                      r"poniedzialek|wtorek|srode|sroda|czwartek|piatek|sobote|sobota|niedziele|niedziela)\b")
L = r"(?:lekcj\w*|zajeci\w*|szkol\w*|budy|budzie)"
P = r"(?:\w+\s*){1,3}"            # przedmiot (sprawdzany potem słownikiem PRZEDMIOTY)
WZORCE = [
    ("pierwsza_lekcja", [
        rf"(?:o\s+|od\s+)?(?:ktorej|jakiej godzinie|ktora|na ktora|na jaka godzine|kiedy)\s+(?:ja\s+)?(?:zaczynam|zaczynamy|zaczyna sie|mam zaczac|mam byc|musze byc|ide|idziemy|mam isc|mam)(?:\s+(?:do|w|na)\s+{L}|\s+{L})?",
        rf"(?:o\s+|od\s+)?(?:ktorej|kiedy|na ktora)\s+(?:mam\s+|jest\s+)?(?:pierwsz\w+|1)\s+{L}",
        rf"(?:jaka|co)\s+(?:jest\s+|mam\s+)?(?:na\s+)?pierwsz\w+(?:\s+{L})?", rf"pierwsz\w+\s+{L}",
        rf"(?:o\s+)?(?:ktorej|kiedy)\s+(?:mam\s+)?(?:wyjsc|wstac|wyjsc z domu)(?:\s+do\s+{L})?",
        rf"(?:na|o)\s+(?:ktora|ktorej)(?:\s+(?:do\s+{L}|mam))?", rf"(?:od|o)\s+ktorej\s+(?:mam\s+)?{L}",
        rf"(?:kiedy|o ktorej)\s+{L}", rf"(?:start|poczatek)\s+{L}", rf"(?:o\s+ktorej|kiedy)\s+(?:zaczyna sie|startuje)\s+{L}",
    ]),
    ("ostatnia_lekcja", [
        rf"(?:o\s+)?(?:ktorej|jakiej godzinie|kiedy)\s+(?:ja\s+)?(?:koncze|konczymy|konczy sie|wychodze|wracam|mam koniec|jest koniec|bede w domu|skoncze)(?:\s+(?:z|ze)?\s*{L})?",
        rf"(?:jaka|kiedy|o ktorej)\s+(?:jest\s+|mam\s+)?ostatni\w*(?:\s+{L})?", rf"ostatni\w*\s+{L}", rf"koniec\s+{L}",
        rf"do\s+ktorej(?:\s+mam)?(?:\s+{L})?", rf"(?:do ktorej|o ktorej)\s+(?:jestem|siedze)\s+w\s+{L}", rf"(?:o\s+)?ktorej\s+(?:koniec|wolne)",
    ]),
    ("ile_lekcji", [rf"ile\s+(?:mam\s+)?(?:godzin\s+)?{L}(?:\s+mam)?", rf"ile\s+mam\s+{L}", rf"ile\s+{L}\s+mam"]),
    ("plan_dnia", [
        rf"(?:jaki|co)\s+(?:mam\s+)?(?:za\s+)?(?:plan|planie)(?:\s+lekcji)?", rf"plan\w*(?:\s+lekcji)?",
        rf"co\s+(?:mam|bede miec|bede mial|jest)(?:\s+w\s+szkole|(?:\s+na)?\s+lekcjach)?", rf"(?:jakie|co za)\s+(?:mam\s+)?{L}",
        rf"(?:lekcje|zajecia)", rf"rozklad\s+{L}", rf"co\s+w\s+szkole",
    ]),
    ("teraz_lekcja", [
        rf"(?:jaka|co)\s+(?:mam\s+|jest\s+)?(?:teraz|zaraz|potem|nastepn\w*|kolejn\w*)(?:\s+{L})?", rf"(?:co|jaka)\s+(?:mam\s+)?(?:po\s+tej|po\s+przerwie|na\s+nastepnej)(?:\s+{L})?",
        rf"(?:nastepna|kolejna)\s+{L}", rf"co\s+(?:teraz|zaraz|potem)\s+mam", rf"(?:jaka|jaka mam)\s+teraz(?:\s+{L})?", rf"co\s+mam\s+nastepn\w*",
    ]),
    ("sala", [rf"(?:w\s+)?(?:jakiej|ktorej)\s+sali\s+(?:mam\s+|jest\s+)?{P}", rf"(?:jaka|ktora)\s+sala(?:\s+(?:na|dla))?(?:\s+{P})?", rf"gdzie\s+(?:mam|jest)\s+{P}"]),
    ("kiedy_przedmiot", [rf"(?:kiedy|o ktorej)\s+(?:mam\s+|jest\s+|bedzie\s+)?(?:najblizsz\w+\s+|nastepn\w+\s+)?{P}",
                         rf"czy\s+(?:mam|jest|bedzie)\s+{P}", rf"(?:mam|jest)\s+{P}"]),
    ("zmiany", [rf"(?:czy\s+)?(?:sa|mam|beda)?\s*(?:jakies\s+)?(?:zastepstw\w*|odwolan\w*(?:\s+{L})?|zmiany\s+w\s+planie|zmian\w*\s+planu|zmiany)",
                rf"(?:co|czy)\s+(?:jest\s+|cos\s+)?(?:jest\s+)?odwolan\w*", rf"czy\s+(?:cos\s+)?(?:sie\s+)?zmienil\w*\s+w\s+planie",
                rf"czy\s+(?:mam\s+)?(?:wolne|okienko|okienka)", rf"(?:odwolan\w*|zastepstw\w*)\s+{L}"]),
    ("sprawdziany", [
        rf"(?:czy\s+)?(?:co\s+|jakie\s+)?(?:mam\s+|pisze\s+|bede pisac\s+|beda\s+)?(?:jakies\s+)?(?:sprawdzian\w*|kartkow\w*|testy|test|klasowk\w*)(?:\s+z\s+\w+)?(?:\s+w\s+tym\s+tygodniu)?",
        rf"co\s+(?:pisze|piszemy|bede pisac|mam pisac)", rf"(?:kiedy|na kiedy)\s+(?:mam\s+|jest\s+)?(?:sprawdzian\w*|kartkow\w*|test)\s*(?:z\s+\w+)?",
        rf"(?:najblizsz\w+|nastepn\w+|kolejn\w+)\s+(?:sprawdzian\w*|kartkow\w*|test)(?:\s+z\s+\w+)?",
        rf"z\s+czego\s+(?:mam\s+)?(?:sprawdzian|kartkowke|test)", rf"czego\s+(?:mam\s+)?(?:sie\s+)?(?:mam\s+)?uczyc", rf"(?:co|czego)\s+(?:sie\s+)?(?:musze\s+)?(?:nauczyc|powtorzyc)",
    ]),
    ("zadania_domowe", [rf"(?:co|czy|jakie)\s+(?:mam\s+)?(?:cos\s+)?(?:jakies\s+)?(?:zadane|zadan\w*\s+domow\w*|prace\s+domow\w*|zadanie\s+domowe|lekcje\s+do\s+odrobienia|do\s+odrobienia)",
                        rf"(?:zadania|zadanie|prace|praca)\s+domow\w*", rf"(?:czy\s+)?(?:cos|co)\s+(?:mam\s+)?zadane", rf"co\s+(?:jest\s+)?zadane(?:\s+z\s+\w+)?"]),
    ("todo", [rf"co\s+(?:mam|jest|zostalo)\s+(?:do\s+zrobienia|na\s+liscie|w\s+todo|zrobic)", rf"(?:moje\s+)?(?:zadania|todo|lista zadan|lista)",
              rf"(?:ile|jakie)\s+(?:mam\s+)?zadan\w*(?:\s+na\s+liscie)?", rf"o\s+czym\s+(?:mam\s+)?pamietac", rf"co\s+(?:musze|powinienem)\s+zrobic"]),
    ("budzik", [r"(?:na\s+)?(?:ktora|kiedy|o ktorej)\s+(?:mam\s+)?(?:budzik|alarm|nastawiony budzik|ustawiony budzik)",
                r"(?:czy\s+)?(?:mam\s+)?(?:ustawiony|nastawiony)\s+(?:budzik|alarm)", r"(?:o\s+ktorej|kiedy)\s+(?:mnie\s+)?(?:obudzisz|budzisz|zadzwonisz rano)",
                r"(?:moje\s+)?(?:budziki|alarmy)"]),
    ("godzina", [r"(?:ktora|jaka)\s+(?:jest\s+)?(?:godzina|godz)(?:\s+teraz)?", r"ktora\s+(?:jest|teraz)", r"(?:ile\s+jest\s+)?godzina", r"jaki\s+(?:jest\s+)?czas"]),
    ("data", [r"(?:jaki|ktory)\s+(?:jest\s+)?(?:dzien|data|dzien tygodnia)", r"(?:ktorego|jaki)\s+(?:mamy|jest)", r"(?:jaka|ktora)\s+(?:jest\s+)?data",
              r"jaki\s+mamy\s+dzien", r"ktorego"]),
    ("serwer", [r"(?:jak\s+)?(?:sie\s+)?(?:ma|czuje|dziala)\s+(?:serwer|serwerek|raspberry|raspi|pi|malinka)", r"(?:stan|status)(?:\s+(?:serwera|pi|raspberry))?",
                r"(?:czy\s+)?(?:wszystko|serwer)\s+(?:dziala|ok|w porzadku)(?:\s+na\s+(?:pi|serwerze))?", r"(?:jaka|ile)\s+(?:jest\s+)?(?:temperatura|temp)(?:\s+(?:procesora|cpu|pi|serwera))?",
                r"(?:ile|jakie)\s+(?:jest\s+)?(?:zuzyci\w+\s+)?(?:ram|ramu|pamieci|procesora|cpu)(?:\s+(?:na\s+)?(?:pi|serwerze))?", r"(?:jak|co)\s+tam\s+(?:na\s+)?(?:serwerze|pi)"]),
    ("minecraft", [r"(?:czy\s+)?(?:minecraft|serwer minecraft|mc)\s+(?:dziala|jest wlaczony|chodzi)", r"(?:ile|kto)\s+(?:osob\s+|graczy\s+)?(?:gra|jest)(?:\s+na\s+(?:minecraft\w*|serwerze minecraft|mc|serwerze))?",
                   r"(?:stan|status)\s+(?:minecraft\w*|mc)"]),
    ("poczta", [r"(?:czy\s+)?(?:mam\s+)?(?:jakies\s+)?(?:nowe\s+|wazne\s+)?(?:maile|maila|wiadomosci mailowe|poczte)", r"co\s+(?:nowego\s+)?(?:w\s+)?(?:poczcie|mailach|na mailu)",
                r"(?:sprawdz\s+)?(?:poczte|maile)"]),
    ("autobus", [r"(?:kiedy|o ktorej)\s+(?:mam\s+|jest\s+|jedzie\s+|bedzie\s+)?(?:najblizszy\s+|nastepny\s+)?(?:autobus|tramwaj|bus|pociag)(?:\s+(?:z|ze|spod)\s+[a-z ]{3,30})?",
                 r"(?:najblizszy|nastepny)\s+(?:autobus|tramwaj|odjazd)(?:\s+(?:z|ze|spod)\s+[a-z ]{3,30})?", r"(?:co|czym)\s+(?:jedzie|odjezdza|pojade)(?:\s+(?:z|ze|spod)\s+[a-z ]{3,30})?"]),
    ("do_domu", [r"jak\s+(?:dojade|wroce|dostane sie|dojechac|wrocic)\s+do\s+domu", r"(?:czym|kiedy|o ktorej)\s+(?:mam\s+|moge\s+)?(?:wrocic|pojechac|jechac)\s+do\s+domu",
                 r"(?:trasa|droga)\s+do\s+domu", r"kiedy\s+(?:mam\s+)?(?:wyjsc|wyjechac)\s+(?:zeby|by)\s+(?:wrocic|byc)\s+(?:do\s+domu|w\s+domu)"]),
]
SKOMPILOWANE = [(i, [re.compile(w) for w in ws]) for i, ws in WZORCE]
BEZ_DNIA = {"pierwsza_lekcja", "ostatnia_lekcja", "ile_lekcji", "plan_dnia", "sala", "kiedy_przedmiot", "zmiany", "sprawdziany",
            "zadania_domowe", "todo", "teraz_lekcja", "budzik", "data"}
WYMAGA_DNIA = {"co jest", "co mam", "o ktorej", "na ktora", "na ktorej", "do ktorej", "ktora", "jest", "mam"}
# ogólne wzorce z przedmiotem na końcu: najpierw wszystkie konkretne (np. „kiedy sprawdzian z fizyki” to sprawdziany)
SKOMPILOWANE.sort(key=lambda x: x[0] in ("kiedy_przedmiot", "sala"))


def rozpoznaj(tekst):
    t = norm(tekst)
    if not t or len(t) > 90:                     # długie, złożone prośby -> Claude
        return None, t
    bez = " ".join(DZIEN_RE.sub(" ", t).replace(" na ", " ").split()) if DZIEN_RE.search(t) else t
    bez = re.sub(r"\s+na$", "", bez)
    if bez in WYMAGA_DNIA and bez == t:              # „co mam”, „o której” bez dnia: za mało, żeby zgadywać
        return _nauczone(t), t
    for intencja, wz in SKOMPILOWANE:
        if any(w.fullmatch(t) or (intencja in BEZ_DNIA and bez and w.fullmatch(bez)) for w in wz):
            if intencja == "kiedy_przedmiot" and not przedmiot_z(t):
                continue
            if intencja == "sala" and not przedmiot_z(t) and "sal" not in t:
                continue
            return intencja, t
    return _nauczone(t), t


# ---------------------------------------------------------------- uczenie (sformułowania oznaczone przez Claude)
def _trigramy(t):
    t = f"  {t} "
    return {t[i:i + 3] for i in range(len(t) - 2)}


def _podobienstwo(a, b):
    sa, sb = set(a.split()), set(b.split())
    slowa = len(sa & sb) / max(1, len(sa | sb))
    ta, tb = _trigramy(a), _trigramy(b)
    return 0.4 * slowa + 0.6 * len(ta & tb) / max(1, len(ta | tb))


def _wczytaj():
    try:
        return json.loads(NAUCZONE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _nauczone(t):
    najl, wyn = 0.0, None
    for zdanie, intencja in _wczytaj().items():
        p = 1.0 if zdanie == t else _podobienstwo(zdanie, t)
        if p > najl:
            najl, wyn = p, intencja
    return wyn if najl >= PROG and wyn in INTENCJE else None


def naucz(tekst, intencja):
    t = norm(tekst)
    if intencja not in INTENCJE or not t or len(t) > 90 or len(t.split()) > 12 or \
            re.search(r"\b(i|oraz|a potem|potem|nastepnie|zrob|napisz|przypomnij|ustaw|dodaj|wyslij|porownaj|wytlumacz|dlaczego|jesli|gdyby)\b", t):
        return                                      # zapamiętujemy tylko krótkie, proste pytania o jedną rzecz
    with LOCK:
        d = _wczytaj()
        d[t] = intencja
        NAUCZONE.write_text(json.dumps(d, ensure_ascii=False, indent=0), encoding="utf-8")


def odpowiedz(tekst, dane):
    """-> (intencja, odpowiedź) albo None (wtedy Claude)"""
    intencja, t = rozpoznaj(tekst)
    if not intencja:
        return None
    try:
        odp = INTENCJE[intencja](t, dane)
    except Exception as ex:                        # brak danych itp.: niech odpowie Claude
        print(f"szybkie {intencja}: {type(ex).__name__}: {ex}", flush=True)
        return None
    return (intencja, odp) if odp else None


OPIS_DLA_CLAUDE = ("Szybkie odpowiedzi (bez AI) mają intencje: " + ", ".join(INTENCJE) + ". Jeśli pytanie Antka (całe, bez "
                   "dodatkowych próśb) to jedna z nich, dopisz na końcu odpowiedzi znacznik [[INTENCJA: nazwa]]: następnym "
                   "razem takie pytanie obsłuży bot bez Ciebie.")
