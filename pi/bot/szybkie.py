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
    return {0: "dziś", 1: "jutro", 2: "pojutrze"}.get(dz) or f"w {DNI[d.weekday()]} {d.day}.{d.month:02d}".replace("w środa", "w środę").replace("w wtorek", "we wtorek") \
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
    za = lambda x: (lambda n: "" if n < 2 else f" (za {n} dni)")((date.fromisoformat(x["data"]) - date.today()).days)
    return "; ".join(f"{x['rodzaj'].capitalize()}: {x['przedmiot']}, {nazwa_dnia(date.fromisoformat(x['data']))}{za(x)}"
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
    d = dzien_z(t, lambda: date.today())
    return f"{nazwa_dnia(d).capitalize()} {DNI[d.weekday()]}, {d.day}.{d.month:02d}.{d.year}." if (d - date.today()).days > 2 \
        else f"{nazwa_dnia(d).capitalize()} jest {DNI[d.weekday()]}, {d.day}.{d.month:02d}.{d.year}."


def serwer(t, dane):
    return dane["serwer"]()


# ---------- serwer: odczyt prosto z systemu (bez portalu i bez AI)
def _cmd(*a, timeout=3):
    import subprocess
    try:
        return subprocess.run(a, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""


def _temp():
    try:
        return int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
    except (OSError, ValueError):
        return None


def _cpu():
    def stat():
        v = [int(x) for x in Path("/proc/stat").read_text().split("\n")[0].split()[1:]]
        return sum(v), v[3] + v[4]
    c1, i1 = stat()
    time.sleep(0.4)
    c2, i2 = stat()
    return 100 * (1 - (i2 - i1) / max(1, c2 - c1))


def _mem():
    m = {l.split(":")[0]: int(l.split()[1]) for l in Path("/proc/meminfo").read_text().splitlines() if ":" in l}
    tot, dost = m["MemTotal"] / 1024, m["MemAvailable"] / 1024
    return tot, tot - dost


def _liczba(x, n=1):
    return f"{x:.{n}f}".replace(".", ",")


def temperatura(t, dane):
    c = _temp()
    if c is None:
        return "Nie udało się odczytać temperatury."
    ocena = "w normie" if c < 65 else "podwyższona, ale bezpieczna" if c < 75 else "wysoka, warto sprawdzić, co obciąża Pi"
    return f"Procesor ma {_liczba(c)} °C, {ocena}."


def cpu(t, dane):
    u = _cpu()
    l1, l5, l15 = Path("/proc/loadavg").read_text().split()[:3]
    return f"Procesor zajęty w {round(u)}% (średnie obciążenie {l1.replace('.', ',')} na 4 rdzenie)."


def ram(t, dane):
    tot, uz = _mem()
    return f"RAM: zajęte {_liczba(uz / 1024)} z {_liczba(tot / 1024)} GB ({round(100 * uz / tot)}%), wolne {_liczba((tot - uz) / 1024)} GB."


def dysk(t, dane):
    import os
    st = os.statvfs("/")
    tot, wol = st.f_blocks * st.f_frsize / 1e9, st.f_bavail * st.f_frsize / 1e9
    wyn = f"Na karcie wolne {_liczba(wol)} z {_liczba(tot, 0)} GB (zajęte {round(100 * (1 - wol / tot))}%)."
    if os.path.ismount("/mnt/nas"):
        sn = os.statvfs("/mnt/nas")
        wyn += f" Na NAS wolne {_liczba(sn.f_bavail * sn.f_frsize / 1e12, 2)} TB."
    return wyn


def uptime(t, dane):
    s_ = float(Path("/proc/uptime").read_text().split()[0])
    d, g, m = int(s_ // 86400), int(s_ % 86400 // 3600), int(s_ % 3600 // 60)
    start = datetime.now() - timedelta(seconds=s_)
    return (f"Pi działa bez przerwy {f'{d} dni ' if d else ''}{g} h {m} min, od {start.strftime('%d.%m %H:%M')}.")


def zasilanie(t, dane):
    v = _cmd("vcgencmd", "get_throttled").split("=")[-1]
    try:
        x = int(v, 16)
    except ValueError:
        return "Nie udało się odczytać stanu zasilania."
    if x == 0:
        return "Zasilanie i taktowanie w porządku, bez spadków napięcia."
    teraz = [n for b, n in ((0, "za niskie napięcie"), (1, "ograniczone taktowanie"), (2, "throttling"), (3, "limit temperatury")) if x >> b & 1]
    kiedys = [n for b, n in ((16, "za niskie napięcie"), (17, "ograniczone taktowanie"), (18, "throttling"), (19, "limit temperatury")) if x >> b & 1]
    return ("Teraz: " + ", ".join(teraz) + ". " if teraz else "Teraz w porządku. ") + \
        ("Od uruchomienia było: " + ", ".join(kiedys) + ". Sprawdź zasilacz (5 V, 3 A)." if kiedys else "")


def nas(t, dane):
    import os
    if not os.path.ismount("/mnt/nas"):
        ping = _cmd("ping", "-c1", "-W1", "172.23.0.28")
        return ("NAS nie jest podłączony, ale odpowiada w sieci: Pi połączy się samo w ciągu 2 minut (albo każ mi to naprawić)."
                if " 0% packet loss" in ping else "NAS nie odpowiada w sieci: pewnie jest wyłączony albo uśpiony.")
    ok = Path("/mnt/nas/Raspberry/.nas").exists()
    return "NAS jest podłączony i działa." if ok else "NAS jest zamontowany, ale nie widzę folderu Raspberry: sprawdź udział."


def kopia(t, dane):
    return dane["kopia"]()


USLUGI = {"portal": "home-portal", "strona": "home-portal", "bot": "serwerek-bot", "telegram": "serwerek-bot",
          "telefon": "serwerek-telefon", "linphone": "serwerek-telefon", "tailscale": "tailscaled", "vnc": "wayvnc",
          "pulpit": "serwerek-vnc-ws", "terminal": "home-terminal", "samba": "smbd", "playit": "playit", "tunel": "playit",
          "dashboard": "pi-dashboard", "panel": "pi-dashboard", "ollama": "ollama", "ssh": "ssh"}


def usluga(t, dane):
    k = next((k for k in USLUGI if re.search(rf"\b{k}\w*", t)), None)
    if not k:
        bledy = _cmd("systemctl", "--failed", "--no-legend", "--plain")
        return "Wszystkie usługi działają." if not bledy else "Z błędem: " + ", ".join(l.split()[0] for l in bledy.splitlines()) + "."
    stan = _cmd("systemctl", "is-active", USLUGI[k])
    return f"{k.capitalize()} ({USLUGI[k]}): " + {"active": "działa.", "inactive": "wyłączony.", "failed": "ma błąd (failed)."}.get(stan, stan + ".")


def co_obciaza(t, dane):
    """chwilowe zużycie (druga próbka top), procesy o tej samej nazwie zsumowane"""
    out = _cmd("top", "-b", "-n2", "-d0.5", "-w", "200", timeout=5).split("\n\n")
    linie = [l.split() for l in out[-1].splitlines() if l.strip() and l.split()[0].isdigit()] if out else []
    suma = {}
    for l in linie:
        try:
            cpu_, mem_, nazwa = float(l[8].replace(",", ".")), float(l[9].replace(",", ".")), l[11]
        except (IndexError, ValueError):
            continue
        if nazwa in ("top", "ps"):
            continue
        c, m = suma.get(nazwa, (0, 0))
        suma[nazwa] = (c + cpu_, m + mem_)
    naj = sorted(suma.items(), key=lambda x: -(x[1][0] * 3 + x[1][1]))[:4]
    if not naj:
        return "Nie udało się sprawdzić procesów."
    tot, _ = _mem()
    return "Najwięcej zajmuje: " + "; ".join(f"{n} {round(c)}% procesora, {round(m * tot / 100)} MB RAM" for n, (c, m) in naj) + "."


def siec(t, dane):
    ip = _cmd("hostname", "-I").split()
    net = " 0% packet loss" in _cmd("ping", "-c1", "-W1", "1.1.1.1")
    lan = [a for a in ip if a.startswith("172.") or a.startswith("192.")]
    return f"Internet {'działa' if net else 'NIE działa'}. Adres w domu: {', '.join(lan) or 'brak'}, Tailscale: 100.108.241.58."


def lokalizacja(t, dane):
    return dane["lokalizacja"]()


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
    "temperatura": temperatura, "cpu": cpu, "ram": ram, "dysk": dysk, "uptime": uptime, "zasilanie": zasilanie, "nas": nas,
    "kopia": kopia, "usluga": usluga, "co_obciaza": co_obciaza, "siec": siec, "lokalizacja": lokalizacja,
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
    ("ile_lekcji", [rf"ile\s+(?:mam\s+)?(?:godzin\s+)?{L}(?:\s+mam)?", rf"ile\s+mam\s+{L}", rf"ile\s+{L}\s+mam",
                    rf"czy\s+(?:mam|jest|ide do|idziemy do)\s+{L}", rf"czy\s+{L}", rf"(?:mam|jest)\s+{L}"]),
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
        rf"(?:za\s+)?ile\s+dni\s+(?:do|mam do|zostalo do)?\s*(?:sprawdzian\w*|kartkow\w*|testu)(?:\s+z\s+\w+)?", rf"(?:za\s+ile|kiedy)\s+(?:jest\s+|mam\s+)?(?:sprawdzian\w*|kartkow\w*)(?:\s+z\s+\w+)?",
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
    ("data", [r"(?:jaki|ktory)\s+(?:jest\s+|bedzie\s+)?(?:dzien|data|dzien tygodnia)(?:\s+(?:jest|bedzie))?", r"(?:ktorego|jaki)\s+(?:mamy|jest)", r"(?:jaka|ktora)\s+(?:jest\s+)?data",
              r"jaki\s+mamy\s+dzien", r"ktorego"]),
    ("serwer", [r"(?:jak\s+)?(?:sie\s+)?(?:ma|czuje|dziala)\s+(?:serwer|serwerek|raspberry|raspi|pi|malinka)", r"(?:stan|status)(?:\s+(?:serwera|pi|raspberry))?",
                r"(?:czy\s+)?(?:wszystko|serwer)\s+(?:dziala|ok|w porzadku)(?:\s+na\s+(?:pi|serwerze))?", r"(?:jak|co)\s+tam\s+(?:na\s+)?(?:serwerze|pi)",
                r"(?:stan|status|parametry|statystyki)\s+(?:serwera|pi|raspberry)", r"(?:jak|co)\s+(?:z|u)\s+(?:serwerem|pi|raspberry)"]),
    ("temperatura", [r"(?:jaka|ile)\s+(?:jest\s+|ma\s+)?(?:teraz\s+)?(?:temperatur\w*|temp|stopni)(?:\s+(?:ma\s+)?(?:procesor\w*|cpu|pi|raspberry|raspi|serwer\w*|malink\w*))?",
                     r"(?:temperatur\w*|temp)(?:\s+(?:procesor\w*|cpu|pi|raspberry|serwer\w*))?", r"ile\s+stopni(?:\s+ma)?(?:\s+\w+)?",
                     r"czy\s+(?:pi|raspberry|serwer|procesor)\s+(?:sie\s+)?(?:grzeje|przegrzewa|jest goracy|nie jest za goracy)",
                     r"(?:jak|czy)\s+(?:goracy|cieply)\s+(?:jest\s+)?(?:procesor|pi|serwer)"]),
    ("cpu", [r"(?:jakie|ile)\s+(?:jest\s+)?(?:zuzyci\w+|obciazeni\w+)(?:\s+(?:procesora|cpu))?(?:\s+na\s+(?:pi|serwerze))?", r"(?:ile|jak)\s+(?:zuzywa|zajety|obciazony)\s+(?:procesor|cpu)",
             r"(?:zuzyci\w+|obciazeni\w+)\s+(?:procesora|cpu)", r"ile\s+(?:procent\s+)?(?:procesora|cpu)", r"(?:procesor|cpu)"]),
    ("ram", [r"(?:ile|jakie)\s+(?:jest\s+)?(?:zuzyci\w+\s+|wolnego\s+|wolnej\s+|zajetego\s+|zajetej\s+)?(?:ram\w*|pamieci)(?:\s+(?:jest\s+)?(?:zajete|wolne|zajetej|wolnej))?(?:\s+na\s+(?:pi|serwerze))?",
             r"(?:zuzyci\w+\s+)?(?:ram\w*|pamieci ram|pamiec)", r"(?:ile|jak)\s+(?:jest\s+)?zajet\w+\s+(?:ramu|pamieci)"]),
    ("dysk", [r"(?:ile|jak duzo)\s+(?:jest\s+|mam\s+)?(?:wolnego\s+)?miejsca(?:\s+(?:na|w)\s+(?:karcie|dysku|pi|raspberry|serwerze|nas\w*|karcie sd))?",
              r"(?:wolne|zajete)\s+miejsce(?:\s+na\s+\w+)?", r"(?:czy\s+)?(?:karta|dysk)\s+(?:jest\s+)?(?:pelna|pelny|zapchana)", r"(?:stan|zajetosc)\s+(?:dysku|karty)",
              r"ile\s+(?:zostalo\s+)?(?:gb|miejsca)(?:\s+zostalo)?(?:\s+na\s+\w+)?"]),
    ("uptime", [r"(?:od\s+kiedy|jak dlugo|ile\s+(?:czasu|dni))\s+(?:dziala|chodzi|jest wlaczony)\s*(?:pi|raspberry|serwer\w*|raspi)?(?:\s+bez\s+przerwy)?",
                r"kiedy\s+(?:byl\s+)?(?:ostatni\s+)?(?:restart|reboot|wlaczony)(?:\s+(?:pi|serwera|raspberry))?", r"uptime"]),
    ("zasilanie", [r"(?:czy\s+)?(?:zasilanie|zasilacz|napiecie)\s*(?:jest\s+)?(?:ok|w porzadku|dziala|wystarcza)?", r"(?:czy\s+)?(?:jest\s+|sa\s+|byly\s+)?(?:throttling|undervoltage|spadki napiecia)",
                   r"czy\s+(?:pi|procesor)\s+(?:zwalnia|sie dlawi|jest dlawiony)"]),
    ("nas", [r"(?:czy\s+)?(?:nas|dysk sieciowy|synology)\s+(?:dziala|jest podlaczony|jest wlaczony|odpowiada|jest)?\s*(?:podlaczony)?", r"(?:jak|co)\s+(?:tam\s+)?(?:z|tam)\s+(?:nasem|nas)",
             r"(?:stan|status)\s+(?:nasa|nas)", r"czy\s+(?:pi\s+)?(?:widzi|ma)\s+(?:nas|nasa)"]),
    ("kopia", [r"(?:kiedy|czy)\s+(?:byla\s+|jest\s+|zrobila sie\s+|sie zrobila\s+)?(?:ostatnia\s+)?kopi\w*(?:\s+(?:zapasowa|systemu))?(?:\s+sie\s+(?:zrobila|udala))?",
               r"(?:stan|status)\s+kopii", r"(?:ostatnia\s+)?kopia(?:\s+(?:zapasowa|systemu))?"]),
    ("usluga", [r"(?:czy\s+)?(?:dziala|chodzi|jest wlaczony|jest wlaczona)\s+(?:portal|strona|bot|telegram|telefon|linphone|tailscale|vnc|pulpit|terminal|samba|playit|tunel|dashboard|panel|ollama|ssh)\w*",
                r"(?:czy\s+)?(?:portal|strona|bot|telefon|linphone|tailscale|vnc|pulpit|terminal|samba|playit|tunel|dashboard|panel|ollama|ssh)\w*\s+(?:dziala|chodzi|jest wlaczony|jest wlaczona|jest ok)",
                r"(?:czy\s+)?(?:wszystkie\s+)?uslugi\s+(?:dzialaja|ok)", r"(?:czy\s+)?(?:jakas|cos)\s+(?:usluga\s+)?(?:nie dziala|ma blad|padlo)"]),
    ("co_obciaza", [r"co\s+(?:najbardziej\s+)?(?:obciaza|zuzywa|zjada|zzera|zajmuje)\s*(?:procesor|cpu|ram|pamiec|pi|serwer)?", r"(?:jakie|ktore)\s+procesy(?:\s+\w+){0,3}",
                    r"(?:top|najwieksze procesy)"]),
    ("siec", [r"(?:czy\s+)?(?:jest|dziala)\s+internet(?:\s+na\s+(?:pi|serwerze))?", r"(?:jaki|jakie)\s+(?:jest\s+|ma\s+)?(?:adres|ip|adresy)(?:\s+ip)?(?:\s+(?:ma\s+)?(?:pi|raspberry|serwera|serwer))?",
              r"(?:adres\s+)?ip(?:\s+(?:pi|raspberry|serwera))?", r"czy\s+(?:pi|serwer)\s+ma\s+internet"]),
    ("lokalizacja", [r"gdzie\s+(?:teraz\s+)?jestem", r"(?:jaka\s+jest\s+)?moja\s+lokalizacja", r"gdzie\s+mnie\s+widzisz"]),
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
            "zadania_domowe", "todo", "teraz_lekcja", "budzik", "data", "temperatura", "cpu", "ram", "dysk"}
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
    return _nauczone(t) or _luzno(t), t


LUZNE = [  # (słowa kluczowe po norm, intencja): krótkie pytania z przekręconej mowy („sprawcie go jest te paratura na procesorza”)
    (r"temperat|paratur|\btemp\b|stopni|przegrz|grzeje", "temperatura"),
    (r"\bram\w*|pamie[cn]", "ram"),
    (r"wolne\w* miejsc|ile miejsc|\bdysk|karc\w* sd|zapchan", "dysk"),
    (r"obciaz|zuzyc\w* procesor|procesor\w* zuzy", "cpu"),
    (r"(?:\bnas\b|nasa\b|nasem\b|synology).*(?:dzial|polacz|podlacz|widz|odpowiad|stan|jest|wlacz)|(?:dzial|polacz|podlacz|widz|odpowiad|stan|wlacz).*(?:\bnas\b|nasa\b|nasem\b|synology)", "nas"),
]
NIE_LUZNIE = re.compile(r"\b(napraw|zrob|dlaczego|czemu|wylacz|wlacz|restart|usun|dodaj|ustaw|zmien|napisz|przypomnij|zadzwon|jak\s+to|co\s+zrobic|problem|nie\s+dziala|blad)")


def _luzno(t):
    if len(t.split()) > 9 or NIE_LUZNIE.search(t):
        return None
    for wz, intencja in LUZNE:
        if re.search(wz, t):
            return intencja
    return None


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
