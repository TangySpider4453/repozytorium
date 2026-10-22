"""
Mobidziennik (ckziupoznan.mobidziennik.pl) w bocie: co 10 min (6–22) logowanie i TYLKO odczyt stron:
plan lekcji (planlekcji?typ=podstawowy), zastępstwa, sprawdziany, zadania domowe. Nic nie jest wysyłane ani
zmieniane w dzienniku (jedyny POST to formularz logowania). Zmiany -> powiadomienie (Linphone/Telegram):
nowe zastępstwo / odwołana lekcja, zmiana planu, nowy albo przesunięty sprawdzian, nowe zadanie domowe.
Nowy sprawdzian/kartkówka -> Claude robi stronę w Nauce i sesje nauki (gdy opis wystarcza) albo prosi o materiały.

Dane logowania: MOBI_ADRES, MOBI_LOGIN, MOBI_HASLO w /etc/serwerek-bot/mobi.env (root 600, EnvironmentFile bota).
Stan: ~/bot/mobi/*.json.
"""
import html
import http.cookiejar
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

KAT = Path(__file__).resolve().parent / "mobi"
UA = "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
DNI = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
MIES = {"sty": 1, "lut": 2, "mar": 3, "kwi": 4, "maj": 5, "cze": 6, "lip": 7, "sie": 8, "wrz": 9, "paź": 10, "paz": 10,
        "lis": 11, "gru": 12}
MIES_PELNE = {"stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5, "czerwca": 6, "lipca": 7, "sierpnia": 8,
              "września": 9, "października": 10, "listopada": 11, "grudnia": 12}
LOCK = threading.Lock()
OSTATNIO = {"t": 0.0}


def skonfigurowany():
    return all(os.environ.get(k) for k in ("MOBI_ADRES", "MOBI_LOGIN", "MOBI_HASLO"))


def czysty(t):
    t = re.sub(r"<br\s*/?>", "\n", t or "")
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"[ \t]+", " ", re.sub(r"\s*\n\s*", "\n", t)).strip()


def pobierz(strony):
    """logowanie + GET podanych stron -> {strona: html}; błąd logowania = wyjątek"""
    a = os.environ["MOBI_ADRES"].rstrip("/")
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.addheaders = [("User-Agent", UA)]
    op.open(a + "/dziennik", timeout=30).read()
    r = op.open(a + "/dziennik", urllib.parse.urlencode({"login": os.environ["MOBI_LOGIN"],
                                                         "haslo": os.environ["MOBI_HASLO"]}).encode(), timeout=30)
    po = r.read().decode("utf-8", "replace")
    if 'name="haslo"' in po and "wyloguj" not in po:
        raise RuntimeError("logowanie do Mobidziennika nie udało się (złe hasło albo zmiana strony)")
    return {s: op.open(f"{a}/dziennik/{s}", timeout=30).read().decode("utf-8", "replace") for s in strony}


# ---------------------------------------------------------------- odczyt stron
def plan(h, poniedzialek):
    """plan tygodnia (z zastępstwami i odwołaniami): [{data, dzien 0-4, od, do, przedmiot, grupa, nauczyciel, sala,
    status: lekcja|zastępstwo|odwołana, info}]"""
    wyn = []
    for klasa, left, title in re.findall(r'class="bx (\w+)[^"]*"[^>]*style="[^"]*left:([\d.]+)%[^"]*"[^>]*title="([^"]*)"', h):
        cz = [c.strip() for c in re.split(r"<br\s*/?>", html.unescape(title).strip())]
        info = ""
        if cz and cz[0].startswith("<small>"):
            info = czysty(cz.pop(0))
        if len(cz) < 2 or not re.match(r"\d\d:\d\d - \d\d:\d\d", cz[0]):
            continue
        m = re.match(r"(.*?)(?: - (.*?))?(?: \((.*)\))?$", cz[2] if len(cz) > 2 else "")
        d = round(float(left) / 20)
        wyn.append({"data": (poniedzialek + timedelta(days=d)).isoformat(), "dzien": d, "od": cz[0][:5], "do": cz[0][-5:],
                    "przedmiot": cz[1], "grupa": (m.group(1) or "") if m else "", "nauczyciel": (m.group(2) or "") if m else "",
                    "sala": (m.group(3) or "") if m else "",
                    "status": {"lo": "odwołana", "lz": "zastępstwo"}.get(klasa, "lekcja"), "info": info})
    wyn.sort(key=lambda x: (x["data"], x["od"], x["przedmiot"]))
    return wyn


def zastepstwa(h):
    """[{data, od, do, lekcja (w planie), zmiana, sala}]"""
    wyn = []
    for wiersz in re.findall(r"(?s)<tr class=\"komorka_[^\"]*\">\s*<td>(\d\d:\d\d - \d\d:\d\d)</td>(.*?)</tr>", h):
        td = [czysty(x) for x in re.findall(r"(?s)<td[^>]*>(.*?)</td>", wiersz[1])]
        if len(td) >= 4:
            wyn.append({"data": td[3], "od": wiersz[0][:5], "do": wiersz[0][-5:], "lekcja": td[0], "zmiana": td[1], "sala": td[2]})
    return wyn


def sprawdziany(h):
    """[{data RRRR-MM-DD, godzina, grupa, przedmiot, rodzaj, tematyka, nauczyciel}]"""
    wyn = []
    for w in re.findall(r"(?s)<tr class=\"komorka_[^\"]*\">(.*?)</tr>", h):
        td = re.findall(r"(?s)<td[^>]*>(.*?)</td>", w)
        if len(td) < 6:
            continue
        m = re.search(r"(\d{1,2}) (\w+) (\d{4})", czysty(td[0]))
        g = re.search(r"(\d\d:\d\d)", td[0])
        if not m or m.group(2)[:3] not in MIES:
            continue
        tytul = lambda x: html.unescape(re.search(r'title="([^"]*)"', x).group(1)) if 'title="' in x else czysty(x)
        naucz = re.search(r"Wpisał\(a\): <strong>([^<]*)", td[5])
        wyn.append({"data": f"{m.group(3)}-{MIES[m.group(2)[:3]]:02d}-{int(m.group(1)):02d}", "godzina": g.group(1) if g else "",
                    "grupa": tytul(td[1]), "przedmiot": tytul(td[2]), "rodzaj": tytul(td[3]), "tematyka": czysty(td[4]),
                    "nauczyciel": naucz.group(1) if naucz else czysty(td[5]).split("Wpisał")[0].strip()})
    return wyn


def zadania_domowe(h):
    wyn = []
    for idz, w in re.findall(r'(?s)<tr class="podswietl[^"]*"[^>]*id_zadania="(\d+)"[^>]*>(.*?)</tr>', h):
        td = re.findall(r"(?s)<td[^>]*>(.*?)</td>", w)
        if len(td) < 4:
            continue
        m = re.search(r"(\d{1,2}) (\w+) (\d{4})", czysty(td[0]))
        termin = f"{m.group(3)}-{MIES_PELNE.get(m.group(2), 0):02d}-{int(m.group(1)):02d}" if m else ""
        naucz = re.search(r"Wpisał\(a\): <strong>([^<]*)", td[2])
        wyn.append({"id": idz, "termin": termin, "przedmiot": czysty(td[1]), "nauczyciel": naucz.group(1) if naucz else "",
                    "tresc": czysty(td[3]), "zrobione": "alt=\"tak\"" in (td[5] if len(td) > 5 else "")})
    return wyn


# ---------------------------------------------------------------- stan i zmiany
def wczytaj(nazwa, domyslne):
    try:
        return json.loads((KAT / f"{nazwa}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return domyslne


def zapisz(nazwa, dane):
    KAT.mkdir(parents=True, exist_ok=True)
    tmp = KAT / f"{nazwa}.tmp"
    tmp.write_text(json.dumps(dane, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(KAT / f"{nazwa}.json")


def klucz_spr(x):
    return f"{x['przedmiot']}|{x['rodzaj']}|{x['tematyka'][:60]}"


def klucz_lekcji(x):
    return f"{x['data']}|{x['od']}|{x['przedmiot']}|{x['status']}|{x['info']}|{x['sala']}"


def dzien_txt(d):
    d = date.fromisoformat(d)
    dz = (d - date.today()).days
    return {0: "dziś", 1: "jutro"}.get(dz, f"{DNI[d.weekday()][:3]} {d.day:02d}.{d.month:02d}")


def opis_zmiany(x):
    if x["status"] == "odwołana":
        return f"{dzien_txt(x['data'])} {x['od']} {x['przedmiot']}: ODWOŁANA" + (f" ({x['info'].split(':', 1)[-1].strip()})" if x["info"] else "")
    if x["status"] == "zastępstwo":
        return (f"{dzien_txt(x['data'])} {x['od']}: " + (f"{x['zamiast']} → " if x.get("zamiast") else "zastępstwo: ") + x["przedmiot"]
                + (f" ({x['nauczyciel']}, sala {x['sala']})" if x["sala"] else ""))
    return f"{dzien_txt(x['data'])} {x['od']}: nowa lekcja {x['przedmiot']}" + (f" (sala {x['sala']})" if x["sala"] else "")


def opis_lekcji(x):
    return f"{x['od']} {x['przedmiot']}" + (f" ({x['sala']})" if x.get("sala") else "")


def sprawdz(powiadom, nowy_sprawdzian):
    """jeden przebieg: pobranie, porównanie z poprzednim, powiadomienia; zwraca stan"""
    pon = date.today() - timedelta(days=date.today().weekday())
    if date.today().weekday() >= 5:                         # w weekend „ten tydzień” = następny
        pon += timedelta(days=7)
    tyg = [f"planlekcji?typ=podstawowy&tydzien={(pon + timedelta(days=7 * n)).isoformat()}" for n in (0, 1)]
    strony = pobierz(tyg + ["zastepstwa", "sprawdziany", "zadaniadomowe"])
    p = plan(strony[tyg[0]], pon) + plan(strony[tyg[1]], pon + timedelta(days=7))
    z = zastepstwa(strony["zastepstwa"])
    for x in p:                                             # przy zastępstwie: jaka lekcja była w planie
        if x["status"] == "zastępstwo":
            zz = next((y for y in z if y["data"] == x["data"] and y["od"] == x["od"]), None)
            x["zamiast"] = zz["lekcja"].split(" - ", 1)[-1] if zz else ""
    s, zd = sprawdziany(strony["sprawdziany"]), zadania_domowe(strony["zadaniadomowe"])
    with LOCK:
        stary = wczytaj("stan", None)
        pierwszy = stary is None
        stary = stary or {"plan": p, "zastepstwa": [], "sprawdziany": {}, "zadania": []}
        wiadomosci = []
        # zmiany planu: odwołania, zastępstwa, nowe i zniknięte lekcje (porównanie tych samych dni; od dziś)
        dzis_ = date.today().isoformat()
        znane_dni = {x["data"] for x in stary["plan"]}
        stare_p = {klucz_lekcji(x) for x in stary["plan"]}
        nowe_p = {klucz_lekcji(x) for x in p}
        zmiany = [x for x in p if x["data"] >= dzis_ and (
            (klucz_lekcji(x) not in stare_p and (x["data"] in znane_dni or x["status"] != "lekcja")) if not pierwszy else x["status"] != "lekcja")]
        zniknely = [x for x in stary["plan"] if x["data"] >= dzis_ and klucz_lekcji(x) not in nowe_p and x["status"] == "lekcja"
                    and not any(y["data"] == x["data"] and y["od"] == x["od"] for y in zmiany)] if not pierwszy else []
        if zmiany or zniknely:
            wiadomosci.append(("📅 Mobidziennik podłączony. Zmiany w planie:\n" if pierwszy else "📅 Zmiana planu:\n") + "\n".join(
                [opis_zmiany(x) for x in zmiany] + [f"{dzien_txt(x['data'])} {x['od']} {x['przedmiot']}: nie ma jej już w planie" for x in zniknely]))
        spr_stare = stary["sprawdziany"]
        spr_nowe = {}
        for x in s:
            k = klucz_spr(x)
            spr_nowe[k] = x
            if k in spr_stare and spr_stare[k]["data"] != x["data"]:
                wiadomosci.append(f"📆 Przesunięty termin: {x['przedmiot']} ({x['rodzaj']}) z {spr_stare[k]['data']} na {x['data']}"
                                  f" {x['godzina']}.")
            elif k not in spr_stare and not pierwszy:
                nowy_sprawdzian(x)
        stare_zd = {x["id"] for x in stary["zadania"]}
        nowe_zd = [x for x in zd if x["id"] not in stare_zd]
        if nowe_zd and not pierwszy:
            wiadomosci.append("📝 Nowe zadanie domowe:\n" + "\n".join(f"{x['przedmiot']} na {x['termin']}: {x['tresc']}" for x in nowe_zd))
        zapisz("stan", {"plan": p, "zastepstwa": z, "sprawdziany": spr_nowe, "zadania": zd, "czas": time.strftime("%Y-%m-%dT%H:%M:%S")})
        OSTATNIO["t"] = time.time()
    for w in wiadomosci:
        powiadom(w)
    return pierwszy, s


def dzis(dzien=None):
    """lekcje danego dnia (z zastępstwami i odwołaniami), sprawdziany i zadania domowe (do porannego przeglądu)"""
    st = wczytaj("stan", None)
    if not st:
        return ""
    d = (dzien or date.today()).isoformat()
    lekcje = [x for x in st["plan"] if x["data"] == d]
    if not lekcje:
        return "brak lekcji" + (" (weekend)" if date.fromisoformat(d).weekday() > 4 else "")
    odbywa = [x for x in lekcje if x["status"] != "odwołana"]
    opisy = []
    for x in lekcje:
        if x["status"] == "odwołana":
            opisy.append(f"{x['od']} {x['przedmiot']} ODWOŁANA")
        elif x["status"] == "zastępstwo":
            opisy.append(f"{x['od']} zastępstwo" + (f" za {x['zamiast']}" if x.get("zamiast") else "") + f": {x['przedmiot']} (sala {x['sala']})")
        else:
            opisy.append(f"{x['od']} {x['przedmiot']} (sala {x['sala']})")
    spr = [x for x in st["sprawdziany"].values() if x["data"] == d]
    zd = [x for x in st["zadania"] if x["termin"] == d and not x["zrobione"]]
    return ((f"{len(odbywa)} lekcji, pierwsza o {odbywa[0]['od']}, ostatnia kończy się o {odbywa[-1]['do']}. " if odbywa else "wszystkie lekcje odwołane. ")
            + "Plan: " + "; ".join(opisy)
            + ("" if not spr else ". Zapowiedziane: " + "; ".join(f"{x['rodzaj']} z {x['przedmiot']} o {x['godzina']} ({x['tematyka'][:80]})" for x in spr))
            + ("" if not zd else ". Zadanie domowe na dziś: " + "; ".join(f"{x['przedmiot']}: {x['tresc']}" for x in zd)))
