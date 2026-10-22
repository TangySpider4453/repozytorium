#!/usr/bin/env python3
"""
Bot Telegram serwerka (@SerwerekAntek_bot): powiadomienia, przyciski i rozmowa z Claude na Pi.

  - Powiadomienia: czerwone problemy z monitora zdrowia od razu (o kazdej porze) i ich koniec; zolte od razu poza
    cisza nocna (22-7; z nocy przychodza rano); nauka: dzien przed sprawdzianem/kartkowka (18:00), 3 dni przed
    sprawdzianem (18:00) i rano w dniu (7:00).
  - Wejscia z sieci domowej (sekcja „wejscia”): od razu nowe wejscie, panel logowania, przejscie zabezpieczen,
    nieudane proby i oznaki ataku; po 10 min ciszy podsumowanie calej wizyty; pelny zapis na NAS (30 dni).
  - Zdjecia i PDF-y (np. strony podrecznika) ida do Claude razem z podpisem: z nich robi nowe zagadnienie w Nauce.
  - Przyciski: Stan, Sprawdziany, Kopia, Przejrzane, Restart, Nowa rozmowa. Akcje zmieniajace cos: zawsze z „Tak”.
  - Inny tekst idzie do Claude Code na Pi (zalogowany subskrypcja wlasciciela), z ograniczonymi narzedziami
    (instrukcja.md). Claude moze poprosic o akcje znacznikiem [[AKCJA: nazwa]] - bot pokazuje przycisk „Tak”.
    Kontekst rozmowy: nowy po 250 tys. tokenow albo po godzinie ciszy (albo przyciskiem „Nowa rozmowa”).
  - Odpowiada tylko wlascicielowi: pierwsza osoba, ktora wysle /start <kod parowania> (kod w stan.json).

Tokeny tylko w /etc/serwerek-bot/*.env (root, 600), podawane przez systemd (serwerek-bot.service).
"""
import html
import json
import os
import random
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

KATALOG = Path(__file__).resolve().parent
STAN = KATALOG / "stan.json"
INSTRUKCJA = KATALOG / "instrukcja.md"
CLAUDE = Path.home() / ".local" / "bin" / "claude"
PORTAL = "http://127.0.0.1"
LINK_TS, LINK_DOM = "http://100.108.241.58", "http://172.23.0.20"
TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
API = f"https://api.telegram.org/bot{TOKEN}/"

KONTEKST_MAX = 250_000          # tokenow: potem nowa rozmowa
KONTEKST_CISZA = 3600           # s bez wiadomosci: potem nowa rozmowa
WEJSCIA = Path("/home/tonyg/portal/dane/wejscia.jsonl")
PLIKI = KATALOG / "pliki"
WEJSCIE_PRZERWA = 600           # s: to samo IP i port nie czesciej niz co 10 min (polaczenia sieciowe)
PORTY = {22: "SSH", 139: "Samba (udział sieciowy)", 445: "Samba (udział sieciowy)", 5900: "VNC (pulpit)",
         8090: "panel Minecrafta", 80: "portal"}
USTAWIENIA = {"nauka_wieczor": "18:00", "nauka_rano": "07:00", "cisza_od": 22, "cisza_do": 7}

AKCJE = {   # nazwa: (opis dla przycisku, polecenie)
    "kopia": ("Zrobić kopię systemu na NAS teraz", ["sudo", "systemctl", "start", "--no-block", "kopia-pi"]),
    "restart_portalu": ("Zrestartować portal (strony, diodę)", ["sudo", "systemctl", "restart", "home-portal"]),
    "restart_minecrafta": ("Zrestartować serwer Minecraft (rozłączy graczy)", None),
    "przejrzane": ("Oznaczyć wszystkie problemy jako przejrzane", None),
}
KLAWIATURA = {"keyboard": [["📊 Stan", "📚 Sprawdziany", "🧭 Ścieżka"], ["💾 Kopia", "✅ Przejrzane", "🔄 Restart"], ["🆕 Nowa rozmowa"]],
              "resize_keyboard": True, "is_persistent": True}

LOCK = threading.RLock()


# ---------------------------------------------------------------- stan i Telegram
def stan():
    try:
        s = json.loads(STAN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        s = {}
    s.setdefault("wlasciciel", None)
    s.setdefault("kod", f"{random.SystemRandom().randrange(10**6):06d}")
    s.setdefault("wyslane", {})
    s.setdefault("sesja", {})
    s.setdefault("ustawienia", dict(USTAWIENIA))
    return s


def zapisz(s):
    tmp = STAN.with_name(STAN.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STAN)


def tg(metoda, timeout=70, **dane):
    req = urllib.request.Request(API + metoda, data=json.dumps(dane).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()).get("result")
    except urllib.error.HTTPError as e:
        print(f"Telegram {metoda}: {e.code} {e.read()[:200]!r}", flush=True)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        print(f"Telegram {metoda}: {e}", flush=True)
    return None


def wyslij(tekst, html_=False, przyciski=None, chat=None):
    chat = chat or stan()["wlasciciel"]
    if not chat:
        return
    tekst = tekst.strip() or "(pusto)"
    czesci = [tekst[i:i + 4000] for i in range(0, len(tekst), 4000)]
    for n, c in enumerate(czesci):
        dane = {"chat_id": chat, "text": c, "disable_web_page_preview": True}
        if html_:
            dane["parse_mode"] = "HTML"
        if n == len(czesci) - 1:
            dane["reply_markup"] = przyciski or KLAWIATURA
        wynik = tg("sendMessage", **dane)
        if wynik is None and html_:         # zly HTML: wyslij jako zwykly tekst
            dane.pop("parse_mode")
            wynik = tg("sendMessage", **dane)
        print(("wysłano: " if wynik else "NIE wysłano: ") + c[:80].replace("\n", " "), flush=True)


def portal(sciezka, dane=None):
    req = urllib.request.Request(PORTAL + sciezka, data=json.dumps(dane).encode() if dane is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def e(t):
    return html.escape(str(t), quote=False)


def cisza_nocna(s):
    g = datetime.now().hour
    od, do = s["ustawienia"]["cisza_od"], s["ustawienia"]["cisza_do"]
    return g >= od or g < do if od > do else od <= g < do


# ---------------------------------------------------------------- przyciski i komendy
def tekst_stanu():
    z, zad = portal("/api/zdrowie"), portal("/api/zadania")
    p = z.get("pomiary", {})
    kolor = {"ok": "🟢 wszystko działa", "warn": "🟡 coś do sprawdzenia", "crit": "🔴 wymaga uwagi"}[z["stan"]]
    linie = [f"<b>Serwerek: {kolor}</b>",
             f"🌡 {p.get('temp', '?')} °C · CPU {round(p.get('cpu') or 0)}% · RAM {round(p.get('ram') or 0)}% · karta {round(p.get('dysk') or 0)}%"]
    us = p.get("uslugi", {})
    if us:
        linie.append("🎮 Minecraft: " + ("działa" if us.get("powernukkitx") == "active" else "❌ " + str(us.get("powernukkitx"))))
    linie.append("💽 NAS: " + ("połączony" if zad["nas"].get("ok") else "❌ niedostępny"))
    kopia = next((x for x in zad["zadania"] if x["id"] == "kopia-pi"), None)
    if kopia:
        if kopia.get("trwa"):
            linie.append(f"💾 Kopia: trwa {kopia.get('procent') or 0}%")
        elif kopia.get("udana"):
            linie.append(f"💾 Ostatnia kopia: {kopia['udana']['czas'].replace('T', ' ')[:16]}")
    try:
        mk = portal("/api/obciazenie").get("maks", {})
        for etyk, k in (("Dziś max", "dzis"), ("7 dni max", "tydzien")):
            d = mk.get(k) or {}
            if d:
                cz = lambda t: f" ({d[t][1][-5:] if k == 'dzis' else d[t][1][8:10] + '.' + d[t][1][5:7] + ' ' + d[t][1][-5:]})" if t in d else ""
                linie.append(f"📈 {etyk}: 🌡 {d.get('temp', ['?'])[0]} °C{cz('temp')} · CPU {round(d['cpu'][0]) if 'cpu' in d else '?'}%{cz('cpu')}"
                             f" · RAM {round(d['ram'][0]) if 'ram' in d else '?'}%{cz('ram')}")
    except (OSError, ValueError):
        pass
    for i in z["aktywne"]:
        linie.append(f"{'🔴' if i.get('teraz', i['poziom']) == 'crit' else '🟡'} {e(i['tytul'])}: {e(i['opis'])}")
    if z["do_przejrzenia"]:
        linie.append(f"🕓 Do przejrzenia: {len(z['do_przejrzenia'])} (przycisk ✅ Przejrzane)")
    return "\n".join(linie)


def sprawdziany():
    try:
        return json.loads(Path("/home/tonyg/portal/sites/nauka/sprawdziany.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def link_sprawdzianu(x):
    return f"{LINK_DOM}/strony/nauka/{x['folder']}/"


def tekst_sprawdzianow(dni=14):
    dzis = date.today()
    lista = sorted((x for x in sprawdziany() if x.get("data") and 0 <= (date.fromisoformat(x["data"]) - dzis).days <= dni),
                   key=lambda x: x["data"])
    if not lista:
        return f"📚 W ciągu {dni} dni nie ma żadnych sprawdzianów ani kartkówek."
    linie = [f"<b>📚 Najbliższe {dni} dni</b>"]
    for x in lista:
        d = (date.fromisoformat(x["data"]) - dzis).days
        kiedy = "dziś" if d == 0 else "jutro" if d == 1 else f"za {d} dni"
        linie.append(f"• <b>{kiedy}</b> ({x['data'][8:]}.{x['data'][5:7]}): {e(x['typ'])} z {e(x['przedmiot'].lower())}: "
                     f"<a href=\"{link_sprawdzianu(x)}\">{e(x['tytul'])}</a>")
    return "\n".join(linie)


def zapytaj(akcja, dodatek=""):
    opis = AKCJE[akcja][0]
    wyslij(f"❓ {opis}?{dodatek}", przyciski={"inline_keyboard": [[{"text": "✅ Tak", "callback_data": f"tak:{akcja}"},
                                                                    {"text": "✖ Nie", "callback_data": "nie"}]]})


def wykonaj(akcja):
    if akcja == "przejrzane":
        d = portal("/api/zdrowie/przejrzane", {"wszystkie": True})
        return f"✅ Gotowe. Dioda: {d['stan']}, do sprawdzenia: {d['liczba']}."
    if akcja == "restart_minecrafta":
        fifo = Path("/home/tonyg/powernukkitx/console.fifo")
        if fifo.exists():
            try:
                fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
                os.write(fd, b"save-all\n")
                os.close(fd)
                time.sleep(5)
            except OSError:
                pass
        cmd = ["sudo", "systemctl", "restart", "powernukkitx"]
    else:
        cmd = AKCJE[akcja][1]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return f"❌ Nie udało się: {(r.stderr or r.stdout)[-300:]}"
    return {"kopia": "💾 Kopia ruszyła. Postęp: 📊 Stan albo panel na stronie.",
            "restart_portalu": "🔄 Portal zrestartowany.",
            "restart_minecrafta": "🎮 Serwer Minecraft zrestartowany (świat zapisany przed restartem)."}[akcja]


# ---------------------------------------------------------------- Claude
def nowa_sesja(s, powod=None):
    s["sesja"] = {}
    zapisz(s)
    if powod:
        wyslij(f"🧹 Nowa rozmowa z Claude ({powod}).")


def kontekst_sesji(sid):
    """rozmiar kontekstu = tokeny ostatniego wywolania modelu w zapisie sesji (usage w raporcie -p sumuje wszystkie wywolania)"""
    for plik in (Path.home() / ".claude" / "projects").glob(f"*/{sid}.jsonl"):
        try:
            for linia in reversed(plik.read_text(encoding="utf-8").splitlines()):
                u = ((json.loads(linia).get("message") or {}).get("usage")) if '"usage"' in linia else None
                if u:
                    return sum(u.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens"))
        except (OSError, ValueError):
            pass
    return 0


def claude(tekst):
    with LOCK:
        s = stan()
        ses = s["sesja"]
        if ses.get("id") and time.time() - ses.get("ostatnio", 0) > KONTEKST_CISZA:
            nowa_sesja(s, "godzina bez wiadomości")
            ses = s["sesja"]
        if ses.get("id") and ses.get("kontekst", 0) >= KONTEKST_MAX:
            nowa_sesja(s, f"kontekst przekroczył {KONTEKST_MAX // 1000} tys. tokenów")
            ses = s["sesja"]
    cmd = [str(CLAUDE), "-p", tekst, "--output-format", "json", "--permission-mode", "dontAsk",
           "--append-system-prompt", INSTRUKCJA.read_text(encoding="utf-8"),
           "--allowedTools", *json.loads((KATALOG / "uprawnienia.json").read_text())["allow"],
           "--disallowedTools", *json.loads((KATALOG / "uprawnienia.json").read_text())["deny"]]
    if ses.get("id"):
        cmd += ["--resume", ses["id"]]
    env = {k: v for k, v in os.environ.items() if k not in ("TELEGRAM_TOKEN", "ANTHROPIC_API_KEY")}
    stop = threading.Event()

    def pisze():
        while not stop.is_set():
            tg("sendChatAction", timeout=10, chat_id=stan()["wlasciciel"], action="typing")
            stop.wait(5)
    threading.Thread(target=pisze, daemon=True).start()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd="/home/tonyg", env=env)
        d = json.loads(r.stdout or "{}")
    except subprocess.TimeoutExpired:
        d = {"is_error": True, "result": "Przekroczony czas (30 min)."}
    except ValueError:
        d = {"is_error": True, "result": (r.stderr or r.stdout or "brak odpowiedzi")[-500:]}
    finally:
        stop.set()
    odp = d.get("result") or ""
    if d.get("is_error") or not d.get("session_id"):
        if ses.get("id"):           # np. sesja wygasla po stronie Claude: zacznij od nowa przy nastepnej wiadomosci
            with LOCK:
                nowa_sesja(stan())
        wyslij("⚠️ Claude: " + (odp or "błąd") + "\nSpróbuj jeszcze raz.")
        return
    kontekst = kontekst_sesji(d["session_id"])
    with LOCK:
        s = stan()
        s["sesja"] = {"id": d["session_id"], "ostatnio": time.time(), "kontekst": kontekst}
        zapisz(s)
    akcje = [a for a in AKCJE if f"[[AKCJA: {a}]]" in odp]
    for a in AKCJE:
        odp = odp.replace(f"[[AKCJA: {a}]]", "")
    wyslij(odp)
    for a in akcje:
        zapytaj(a, " (proponuje Claude)")


# ---------------------------------------------------------------- powiadomienia
def czas_minal(hhmm):
    g, m = map(int, hhmm.split(":"))
    return datetime.now() >= datetime.now().replace(hour=g, minute=m, second=0, microsecond=0)


def powiadomienia():
    s = stan()
    if not s["wlasciciel"]:
        return
    w = s["wyslane"]
    try:
        z = portal("/api/zdrowie")
    except (OSError, ValueError):
        z = None
    if z:
        wszystkie = z["aktywne"] + z["do_przejrzenia"]
        zolte = []
        for i in wszystkie:
            k, poziom = "inc:" + i["id"], i.get("teraz", i["poziom"]) if not i.get("do") else i["poziom"]
            if not i.get("do") and poziom == "crit" and w.get(k) != "crit":
                wyslij(f"🔴 <b>{e(i['tytul'])}</b>\n{e(i['opis'])}\n\n{LINK_DOM}/strony/zdrowie/", html_=True)
                w[k] = "crit"
            elif i.get("do") and w.get(k) == "crit":
                wyslij(f"✅ Minęło: <b>{e(i['tytul'])}</b> (od {i['od'][11:16]} do {i['do'][11:16]})", html_=True)
                w[k] = "koniec"
            elif k not in w and poziom == "warn":
                zolte.append(i)
        if zolte and not cisza_nocna(s):       # w nocy czekaja do rana (wtedy jedna wiadomosc z lista)
            naglowek = "🟡 <b>Do sprawdzenia</b>" if len(zolte) == 1 else f"🟡 <b>Do sprawdzenia ({len(zolte)})</b>"
            wyslij(naglowek + "\n" + "\n".join(f"• {e(i['tytul'])}: {e(i['opis'])}" + (" (już minęło)" if i.get("do") else "")
                                                for i in zolte) + "\n\nPo przejrzeniu: ✅ Przejrzane", html_=True)
            for i in zolte:
                w["inc:" + i["id"]] = "warn"
        aktualne = {"inc:" + i["id"] for i in wszystkie}
        for k in [k for k in w if k.startswith("inc:") and k not in aktualne]:
            del w[k]
    dzis, us = date.today(), s["ustawienia"]
    for x in sprawdziany():
        if not x.get("data"):
            continue
        d = (date.fromisoformat(x["data"]) - dzis).days
        co = None
        if d == 1 and czas_minal(us["nauka_wieczor"]):
            co, tekst = "jutro", f"📚 <b>Jutro {e(x['typ'])} z {e(x['przedmiot'].lower())}</b>"
        elif d == 3 and x["typ"] == "sprawdzian" and czas_minal(us["nauka_wieczor"]):
            co, tekst = "za3", f"📚 <b>Za 3 dni sprawdzian z {e(x['przedmiot'].lower())}</b>"
        elif d == 0 and czas_minal(us["nauka_rano"]) and datetime.now().hour < 12:
            co, tekst = "dzis", f"☀️ <b>Dziś {e(x['typ'])} z {e(x['przedmiot'].lower())}</b>. Powodzenia!"
        if co and w.get(f"nauka:{x['id']}:{x['data']}:{co}") is None:
            wyslij(f"{tekst}\n{e(x['tytul'])}\nPowtórz zakładkę „Najważniejsze”: {link_sprawdzianu(x)}", html_=True)
            w[f"nauka:{x['id']}:{x['data']}:{co}"] = time.time()
    for k in [k for k in w if k.startswith("nauka:") and k.split(":")[-2] < (dzis - timedelta(days=7)).isoformat()]:
        del w[k]
    with LOCK:
        s2 = stan()
        s2["wyslane"] = w
        zapisz(s2)


def petla_powiadomien():
    while True:
        try:
            powiadomienia()
        except Exception as ex:         # powiadomienia nie moga zatrzymac bota
            print(f"powiadomienia: {type(ex).__name__}: {ex}", flush=True)
        time.sleep(60)


# ---------------------------------------------------------------- wejscia z sieci domowej
# Kazde zdarzenie z IP spoza Tailscale trafia do wizyty (WIZYTY[ip]) i od razu do logu na Pi (~/bot/wejscia/) i na NAS
# (Logi/wejscia/RRRR-MM-DD.log; pliki starsze niz 30 dni sa usuwane). Od razu na Telegram tylko: nowe wejscie, otwarcie
# panelu logowania, przejscie zabezpieczen (haslo portalu, SSH, Samba, VNC, panel MC), nieudane proby i oznaki ataku
# (zgadywanie hasla, skanowanie portow, szukanie dziur w portalu). Cala sciezka: komenda „ścieżka [wczoraj|RRRR-MM-DD]”.
import re

NAS_WEJSCIA = Path("/mnt/nas/Raspberry/Logi/wejscia")
LOK_WEJSCIA = KATALOG / "wejscia"          # ta sama kopia na Pi (komenda „ścieżka” czyta stad), 30 dni
BUFOR = KATALOG / "wejscia-bufor.log"
WIZYTA_KONIEC = 600
WIZYTY = {}
WIZYTY_LOCK = threading.Lock()
PODEJRZANE = re.compile(r"wp-|wordpress|\.env|\.git|phpmyadmin|/admin|cgi-bin|\.php|/etc/passwd|\.\./|shell|/boaform|/HNAP|/actuator|/console|/manager", re.I)
OPIS_API = [(r"^POST /api/nauka/postep", "Nauka: zapis postępu"), (r"^POST /api/nauka/data", "Nauka: zmiana daty sprawdzianu"),
            (r"^POST /api/nauka/wazne", "Nauka: oznaczenie „ważne”"), (r"^POST /api/nauka/ustawienia", "Nauka: ustawienia listy"),
            (r"^POST /api/progres/zdjecie/", "Progres: zmiana lub usunięcie zdjęcia"), (r"^POST /api/progres/zdjecie", "Progres: dodanie zdjęcia"),
            (r"^POST /api/progres/wpis", "Progres: zapis pomiaru"), (r"^POST /api/progres/render", "Progres: zlecenie filmu"),
            (r"^POST /api/progres/film/", "Progres: usunięcie filmu"), (r"^POST /api/progres/ustawienia", "Progres: ustawienia"),
            (r"^POST /api/zdrowie/przejrzane", "Zdrowie: „przejrzane”"), (r"^GET /api/progres/plik/", "Progres: oglądanie zdjęć"),
            (r"^GET /api/progres/film/", "Progres: oglądanie filmu"), (r"^GET /wyloguj", "wylogowanie"),
            (r"^POST /logowanie", None), (r"^GET /logowanie", None)]
STRONY = [(r"^/$", "🏠 Start"), (r"^/siec", "🌐 Sieć"), (r"^/terminal", "💻 Terminal"), (r"^/strony/nauka/([a-z0-9_-]+)/", "📚 Nauka: {0}"),
          (r"^/strony/nauka/", "📚 Nauka"), (r"^/strony/progres/", "💪 Progres"), (r"^/strony/zdrowie/", "🩺 Zdrowie"),
          (r"^/strony/lazik/", "🚙 Łazik"), (r"^/strony/([a-z0-9_-]+)/", "strona {0}")]


def log_nas(linia):
    dzien = date.today().isoformat()
    tekst = f"{dzien} {linia}\n"
    try:
        LOK_WEJSCIA.mkdir(exist_ok=True)
        with open(LOK_WEJSCIA / f"{dzien}.log", "a", encoding="utf-8") as f:
            f.write(tekst)
    except OSError:
        pass
    try:
        if Path("/mnt/nas/Raspberry/.nas").exists():
            NAS_WEJSCIA.mkdir(exist_ok=True)
            if BUFOR.exists() and BUFOR.stat().st_size:
                with open(NAS_WEJSCIA / f"{dzien}.log", "a", encoding="utf-8") as f:
                    f.write("[zaległe, NAS był niedostępny]\n" + BUFOR.read_text(encoding="utf-8"))
                BUFOR.unlink()
            with open(NAS_WEJSCIA / f"{dzien}.log", "a", encoding="utf-8") as f:
                f.write(tekst)
            return
    except OSError:
        pass
    with open(BUFOR, "a", encoding="utf-8") as f:
        f.write(tekst)


def sprzataj_nas():
    granica = (date.today() - timedelta(days=30)).isoformat()
    for katalog in (NAS_WEJSCIA, LOK_WEJSCIA):
        try:
            for p in katalog.glob("*.log"):
                if p.stem < granica:
                    p.unlink()
        except OSError:
            pass


def urzadzenie(ip):
    """MAC z tablicy ARP i nazwa z DNS routera (jesli jest)"""
    import socket
    mac = ""
    try:
        out = subprocess.run(["ip", "neigh", "show", ip], capture_output=True, text=True, timeout=5).stdout
        if "lladdr" in out:
            mac = out.split("lladdr")[1].split()[0]
    except (OSError, subprocess.TimeoutExpired):
        pass
    wynik = []

    def szukaj():
        try:
            wynik.append(socket.gethostbyaddr(ip)[0])
        except OSError:
            pass
    t = threading.Thread(target=szukaj, daemon=True)
    t.start()
    t.join(2)
    return ", ".join(x for x in (wynik[0] if wynik else "", f"MAC {mac}" if mac else "") if x)


def system_z_ua(ua):
    ua = ua or ""
    for klucz, nazwa in (("iPad", "iPad"), ("iPhone", "iPhone"), ("Android", "Android"), ("Windows", "Windows"),
                         ("Macintosh", "Mac/iPad"), ("Linux", "Linux"), ("curl", "curl"), ("python", "skrypt Python"), ("Wget", "wget")):
        if klucz in ua:
            return nazwa
    return ua[:40] or "?"


def zdarzenie(ip, krok, alarm=None, rodzaj_alarmu=None, przerwa=0):
    """krok: opis do sladu wizyty i logu NAS; alarm: (ikona, tytul, dodatek) do wyslania od razu"""
    if not ip or ip.startswith("100.") or ip in ("127.0.0.1", "172.23.0.20", "172.23.0.24"):
        return
    teraz = time.time()
    urz_nowe = urzadzenie(ip) if ip not in WIZYTY else None
    with WIZYTY_LOCK:
        w = WIZYTY.get(ip)
        nowa = w is None
        if nowa:
            w = WIZYTY[ip] = {"od": teraz, "ostatnio": teraz, "kroki": [], "alarmy": {}, "urz": urz_nowe or "", "liczniki": {}}
        w["ostatnio"] = teraz
        if not w["kroki"] or w["kroki"][-1][1] != krok:
            w["kroki"].append((time.strftime("%H:%M:%S"), krok))
        else:
            w["liczniki"][krok] = w["liczniki"].get(krok, 1) + 1
        wyslac = alarm and (not rodzaj_alarmu or teraz - w["alarmy"].get(rodzaj_alarmu, 0) > przerwa)
        if wyslac and rodzaj_alarmu:
            w["alarmy"][rodzaj_alarmu] = teraz
        urz = w["urz"]
    if nowa:
        log_nas(f"{time.strftime('%H:%M:%S')} {ip} NOWA WIZYTA" + (f" ({urz})" if urz else ""))
    log_nas(f"{time.strftime('%H:%M:%S')} {ip} {krok}")
    if not stan()["wlasciciel"]:
        return
    kto = f"IP: <code>{e(ip)}</code>" + (f" ({e(urz)})" if urz else "")
    if nowa:
        wyslij(f"🚪 <b>Nowe wejście na Pi z sieci domowej</b>\n{kto}\nPierwszy krok: {e(krok)}", html_=True)
    if wyslac:
        ikona, tytul, dodatek = alarm
        wyslij(f"{ikona} <b>{e(tytul)}</b>\n{kto}" + (f"\n{e(dodatek)}" if dodatek else ""), html_=True)


def petla_wizyt():
    ostatnie_sprzatanie = None
    while True:
        time.sleep(30)
        teraz = time.time()
        with WIZYTY_LOCK:
            koniec = [(ip, w) for ip, w in WIZYTY.items() if teraz - w["ostatnio"] > WIZYTA_KONIEC]
            for ip, _ in koniec:
                del WIZYTY[ip]
        for ip, w in koniec:
            log_nas(f"{time.strftime('%H:%M:%S', time.localtime(w['ostatnio']))} {ip} KONIEC WIZYTY")
        if ostatnie_sprzatanie != date.today():
            ostatnie_sprzatanie = date.today()
            sprzataj_nas()


def krok_portalu(z):
    """zdarzenie portalu -> (krok, alarm, rodzaj alarmu, przerwa)"""
    sys_ = system_z_ua(z.get("ua"))
    sys_ = None if sys_ == "?" else sys_
    r = z["rodzaj"]
    if r == "panel_logowania":
        return "🔑 otworzył panel logowania portalu", ("🔑", "Ktoś otworzył panel logowania portalu", sys_), "panel", 60
    if r == "logowanie_ok":
        return "🔓 zalogował się hasłem do portalu", ("🔓", "Przeszedł zabezpieczenie: zalogował się hasłem do portalu", sys_), None, 0
    if r == "zle_haslo":
        p = z.get("proba", 1)
        if p >= 3:
            return f"⛔ złe hasło (próba {p})", ("🕵️", f"Możliwy atak: zgadywanie hasła ({p} złe próby)", sys_), None, 0
        return f"⛔ złe hasło (próba {p})", ("⛔", f"Złe hasło do portalu (próba {p} z 5)", sys_), None, 0
    if r == "blokada":
        return "🚫 zablokowany na 5 min", ("🚫", "Zablokowano logowanie na 5 min (5 złych haseł)", sys_), None, 0
    if r == "zapytanie":
        met, sc, wyn = z.get("metoda", "GET"), z.get("sciezka", ""), z.get("wynik", 0)
        sciezka = sc.split("?")[0]
        if PODEJRZANE.search(sc):
            return f"🕵️ szukał dziur: {met} {sc[:80]} ({wyn})", ("🕵️", "Możliwy atak: ktoś szuka dziur w portalu", f"{met} {sc[:120]}"), "dziury", 300
        for wzor, opis in OPIS_API:
            if re.search(wzor, f"{met} {sciezka}"):
                return (opis + ("" if wyn < 400 else f" (odmowa {wyn})")) if opis else None, None, None, 0
        if sciezka.startswith("/api/") or re.search(r"\.(js|css|png|jpg|ico|json|svg|woff2?|task|mp4)$", sciezka):
            return (f"odmowa {wyn}: {met} {sciezka[:60]}" if wyn in (401, 403) else None), None, None, 0
        for wzor, opis in STRONY:
            m = re.search(wzor, sciezka)
            if m:
                return opis.format(*m.groups()) + ("" if z.get("zalogowany") else " → strona logowania (bez hasła)"), None, None, 0
        return f"{met} {sciezka[:80]} ({wyn})", None, None, 0
    return None, None, None, 0


def petla_portalu():
    """zdarzenia portalu (app.py dopisuje linie JSON do dane/wejscia.jsonl)"""
    poz = WEJSCIA.stat().st_size if WEJSCIA.exists() else 0
    while True:
        time.sleep(1)
        try:
            rozm = WEJSCIA.stat().st_size if WEJSCIA.exists() else 0
            if rozm < poz:
                poz = 0
            if rozm == poz:
                if rozm > 5 * 1024 * 1024:          # wszystko przeczytane: zacznij plik od nowa
                    WEJSCIA.write_text("")
                    poz = 0
                continue
            with open(WEJSCIA, encoding="utf-8") as f:
                f.seek(poz)
                linie = f.read().splitlines()
                poz = f.tell()
            for l in linie:
                z = json.loads(l)
                krok, alarm, rodz, przerwa = krok_portalu(z)
                if krok:
                    zdarzenie(z.get("ip"), "portal: " + krok, alarm, rodz, przerwa)
        except (OSError, ValueError, KeyError) as ex:
            print(f"wejscia portalu: {ex}", flush=True)


def petla_dziennika():
    """SSH (sshd), Samba (auth_audit i full_audit) i log nftables (SERWEREK-WEJSCIE, SERWEREK-SKAN) z dziennika systemu"""
    porty_ip = {}
    zle_ssh = {}
    while True:
        try:
            p = subprocess.Popen(["journalctl", "-f", "-n0", "-o", "cat", "_TRANSPORT=kernel", "+", "SYSLOG_IDENTIFIER=sshd",
                                  "+", "SYSLOG_IDENTIFIER=sshd-session", "+", "SYSLOG_IDENTIFIER=smbd_audit", "+", "SYSLOG_IDENTIFIER=smbd"],
                                 stdout=subprocess.PIPE, text=True)
            for l in p.stdout:
                if m := re.search(r"SERWEREK-WEJSCIE .*SRC=(\S+) .*DPT=(\d+)", l):
                    ip, port = m.group(1), int(m.group(2))
                    nazwa = PORTY.get(port, f"port {port}")
                    alarm = None
                    if port == 5900:
                        alarm = ("🖥️", "Połączenie z pulpitem VNC", "VNC daje pełny dostęp do pulpitu Pi")
                    elif port == 8090:
                        alarm = ("🎮", "Wejście na panel Minecrafta (bez hasła)", "konsola serwera Minecraft")
                    zdarzenie(ip, f"połączenie: {nazwa}", alarm, f"port{port}", WEJSCIE_PRZERWA)
                elif m := re.search(r"SERWEREK-SKAN .*SRC=(\S+) .*DPT=(\d+)", l):
                    ip, port, teraz = m.group(1), m.group(2), time.time()
                    lista = [(t, pp) for t, pp in porty_ip.get(ip, []) if t > teraz - 60] + [(teraz, port)]
                    porty_ip[ip] = lista
                    rozne = sorted({pp for _, pp in lista}, key=int)
                    if len(rozne) >= 5:
                        zdarzenie(ip, f"🕵️ skanowanie portów ({len(rozne)} portów w minutę)",
                                  ("🕵️", "Możliwy atak: skanowanie portów", "porty: " + ", ".join(rozne[:15])), "skan", 600)
                    else:
                        zdarzenie(ip, f"połączenie na zamknięty port {port}")
                elif m := re.search(r"Accepted (\S+) for (\S+) from (\S+)", l):
                    zdarzenie(m.group(3), f"🔓 SSH: zalogował się jako {m.group(2)} ({m.group(1)})",
                              ("🔓", f"Przeszedł zabezpieczenie: zalogował się przez SSH jako {m.group(2)}", f"metoda: {m.group(1)}"))
                elif m := re.search(r"Failed (\S+) for (invalid user )?(\S+) from (\S+)", l):
                    ip, teraz = m.group(4), time.time()
                    zle_ssh[ip] = [t for t in zle_ssh.get(ip, []) if t > teraz - 300] + [teraz]
                    n = len(zle_ssh[ip])
                    tytul = (f"Możliwy atak: zgadywanie hasła SSH ({n} prób w 5 min)" if n >= 3
                             else f"Nieudane logowanie SSH jako {m.group(3)}" + (" (nie ma takiego użytkownika)" if m.group(2) else ""))
                    zdarzenie(ip, f"⛔ SSH: złe hasło dla {m.group(3)}", ("🕵️" if n >= 3 else "⛔", tytul, None),
                              "ssh_atak" if n >= 3 else None, 300 if n >= 3 else 0)
                elif m := re.search(r"Invalid user (\S+) from (\S+)", l):
                    zdarzenie(m.group(2), f"⛔ SSH: nieistniejący użytkownik {m.group(1)}",
                              ("⛔", f"Próba SSH na nieistniejącego użytkownika {m.group(1)}", None), "ssh_inv", 60)
                elif m := re.search(r"Disconnected from user (\S+) (\S+) port", l):
                    zdarzenie(m.group(2), f"SSH: wylogował się ({m.group(1)})")
                elif m := re.search(r"Auth: .*user \[([^\]]*)\]\\?\[?([^\]]*)\]? .*status \[(NT_STATUS_\w+)\].*remote host \[ipv\d:([^\]]+):\d+\]", l):
                    uz, status, ip = m.group(2) or m.group(1), m.group(3), m.group(4)
                    if status == "NT_STATUS_OK":
                        zdarzenie(ip, f"🔓 Samba: zalogował się jako {uz}", ("🔓", f"Przeszedł zabezpieczenie: udział sieciowy Samba jako {uz}", None), "smb_ok", 600)
                    else:
                        zdarzenie(ip, f"⛔ Samba: odmowa dla {uz} ({status})", ("⛔", f"Nieudane logowanie do udziału Samba jako {uz}", status), "smb_zle", 60)
                elif m := re.search(r"([^|\s]*)\|([\d.:a-f]+)\|([^|]*)\|(\w+)\|(ok|fail)\|?(.*)", l):
                    uz, ip, udzial, op, wynik, reszta = m.groups()
                    sciezka = reszta.split("|")[-1][:150]
                    if op == "connect":
                        alarm = ("🔓", f"Połączył się z udziałem „{udzial}” jako {uz}",
                                 "UWAGA: ten udział to cały dysk Pi z prawami roota" if udzial == "Pelny_System" else None) if wynik == "ok" else None
                        zdarzenie(ip, f"Samba: {'połączył się z' if wynik == 'ok' else 'odmowa dostępu do'} „{udzial}” jako {uz}", alarm, f"smb_{udzial}", 600)
                    elif op == "disconnect":
                        zdarzenie(ip, f"Samba: rozłączył się z „{udzial}”")
                    else:
                        co = {"openat": "otworzył", "unlinkat": "🗑 usunął", "renameat": "zmienił nazwę", "mkdirat": "utworzył folder"}.get(op, op)
                        zdarzenie(ip, f"Samba: {co} {sciezka}" + ("" if wynik == "ok" else " (nie udało się)"))
        except Exception as ex:
            print(f"dziennik: {type(ex).__name__}: {ex}", flush=True)
        time.sleep(10)


def tekst_sciezki(arg=""):
    import re as re_
    arg = arg.strip().lower()
    dzien = date.today() - timedelta(days=1) if arg == "wczoraj" else date.today()
    if re_.fullmatch(r"\d{4}-\d{2}-\d{2}", arg):
        dzien = date.fromisoformat(arg)
    plik = LOK_WEJSCIA / f"{dzien.isoformat()}.log"
    if not plik.exists():
        return f"🧭 {dzien.strftime('%d.%m.%Y')}: nikt nie wchodził na Pi z sieci domowej."
    wizyty = []             # [{ip, urz, od, do, kroki: [[czas, krok, ile]]}]
    otwarte = {}
    for l in plik.read_text(encoding="utf-8").splitlines():
        cz = l.split(" ", 3)
        if len(cz) < 4:
            continue
        _, godz, ip, krok = cz
        if krok.startswith("NOWA WIZYTA") or ip not in otwarte:
            w = {"ip": ip, "urz": krok[13:-1] if krok.startswith("NOWA WIZYTA (") else "", "od": godz, "do": godz, "kroki": []}
            wizyty.append(w)
            otwarte[ip] = w
            if krok.startswith("NOWA WIZYTA"):
                continue
        w = otwarte[ip]
        if krok == "KONIEC WIZYTY":
            otwarte.pop(ip, None)
            continue
        w["do"] = godz
        if w["kroki"] and w["kroki"][-1][1] == krok:
            w["kroki"][-1][2] += 1
        else:
            w["kroki"].append([godz, krok, 1])
    n = len(wizyty)
    slowo = "wizyta" if n == 1 else "wizyty" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "wizyt"
    linie = [f"<b>🧭 Ścieżka {dzien.strftime('%d.%m.%Y')}: {n} {slowo}</b>"]
    for w in wizyty:
        linie.append(f"\n<b>{e(w['ip'])}</b>" + (f" ({e(w['urz'])})" if w["urz"] else "") + f" · {w['od'][:5]}–{w['do'][:5]}")
        kroki = w["kroki"]
        if len(kroki) > 30:
            kroki = kroki[:15] + [["", f"… {len(kroki) - 25} kroków pominiętych (pełna lista na NAS) …", 1]] + kroki[-10:]
        for g, k, n in kroki:
            linie.append(f"{g[:5]} {e(k.removeprefix('portal: '))}" + (f" ×{n}" if n > 1 else ""))
    linie.append(f"\nPełny zapis: NAS → Raspberry/Logi/wejscia/{dzien.isoformat()}.log")
    return "\n".join(linie)


# ---------------------------------------------------------------- odbieranie wiadomosci
KOLEJKA = []
KOLEJKA_BUDZIK = threading.Event()


def petla_claude():
    while True:
        KOLEJKA_BUDZIK.wait()
        KOLEJKA_BUDZIK.clear()
        while KOLEJKA:
            tekst = KOLEJKA.pop(0)
            try:
                claude(tekst)
            except Exception as ex:
                wyslij(f"⚠️ Błąd: {type(ex).__name__}: {ex}")


GRUPY = {}          # media_group_id -> {"pliki": [...], "podpis": str}
GRUPY_LOCK = threading.Lock()


def pobierz_plik(file_id, nazwa):
    info = tg("getFile", file_id=file_id)
    if not info or not info.get("file_path"):
        return None
    dzien = PLIKI / date.today().isoformat()
    dzien.mkdir(parents=True, exist_ok=True)
    cel = dzien / f"{datetime.now().strftime('%H%M%S')}_{random.randrange(1000):03d}_{nazwa}"
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/file/bot{TOKEN}/{info['file_path']}", timeout=120) as r:
            cel.write_bytes(r.read())
    except (urllib.error.URLError, OSError):
        return None
    return cel


def do_claude(pliki, podpis):
    tekst = podpis or "Przysłałem materiały."
    if pliki:
        tekst += "\n\n[Załączone pliki (otwórz narzędziem Read): " + ", ".join(str(p) for p in pliki) + "]"
    KOLEJKA.append(tekst)
    KOLEJKA_BUDZIK.set()
    if len(KOLEJKA) > 1:
        wyslij("⏳ Claude jeszcze pracuje nad poprzednią wiadomością, ta poczeka w kolejce.")


def plik_z_wiadomosci(m):
    if m.get("photo"):
        return pobierz_plik(m["photo"][-1]["file_id"], "zdjecie.jpg")
    d = m.get("document")
    if d:
        nazwa = "".join(c for c in (d.get("file_name") or "plik") if c.isalnum() or c in "._-")[-60:] or "plik"
        if (d.get("file_size") or 0) > 20 * 1024 * 1024:
            wyslij("⚠️ Plik jest większy niż 20 MB (limit Telegrama dla botów). Podziel go albo wyślij zdjęcia stron.")
            return None
        return pobierz_plik(d["file_id"], nazwa)
    return None


def zamknij_grupe(gid):
    time.sleep(4)               # zdjecia z jednej wiadomosci przychodza osobno: zbierz je razem
    with GRUPY_LOCK:
        g = GRUPY.pop(gid, None)
    if g:
        wyslij(f"📎 Mam {len(g['pliki'])} plików, przekazuję do Claude.")
        do_claude(g["pliki"], g["podpis"])


def obsluz(u):
    s = stan()
    if "callback_query" in u:
        q = u["callback_query"]
        tg("answerCallbackQuery", callback_query_id=q["id"])
        if q["message"]["chat"]["id"] != s["wlasciciel"]:
            return
        tg("editMessageReplyMarkup", chat_id=s["wlasciciel"], message_id=q["message"]["message_id"], reply_markup={"inline_keyboard": []})
        dane = q.get("data", "")
        if dane.startswith("tak:") and dane[4:] in AKCJE:
            wyslij(wykonaj(dane[4:]))
        elif dane == "nie":
            wyslij("Nic nie zrobiłem.")
        return
    m = u.get("message") or {}
    chat, tekst = (m.get("chat") or {}).get("id"), (m.get("text") or "").strip()
    if chat and chat == s["wlasciciel"] and (m.get("photo") or m.get("document")):
        plik = plik_z_wiadomosci(m)
        if plik is None:
            wyslij("⚠️ Nie udało się pobrać pliku.")
            return
        gid = m.get("media_group_id")
        if gid:
            with GRUPY_LOCK:
                nowa = gid not in GRUPY
                g = GRUPY.setdefault(gid, {"pliki": [], "podpis": ""})
                g["pliki"].append(plik)
                g["podpis"] = g["podpis"] or (m.get("caption") or "")
            if nowa:
                threading.Thread(target=zamknij_grupe, args=(gid,), daemon=True).start()
        else:
            do_claude([plik], m.get("caption") or "")
        return
    if not chat or not tekst:
        return
    if s["wlasciciel"] is None:
        if tekst in (f"/start {s['kod']}", s["kod"]):
            with LOCK:
                s["wlasciciel"] = chat
                zapisz(s)
            wyslij("👋 Cześć! Jestem botem Twojego serwerka. Będę wysyłał alarmy (🔴 od razu, 🟡 zbiorczo, w nocy tylko 🔴) "
                   "i przypomnienia o sprawdzianach. Przyciski są na dole, a o wszystko inne możesz po prostu zapytać: "
                   "przekażę to Claude na Raspberry Pi.")
        return
    if chat != s["wlasciciel"]:
        return
    if tekst in ("📊 Stan", "/stan"):
        wyslij(tekst_stanu(), html_=True)
    elif tekst.split()[0].lower() in ("🧭", "ścieżka", "sciezka", "/sciezka"):
        slowa = tekst.split()
        while slowa and slowa[0].lower() in ("🧭", "ścieżka", "sciezka", "/sciezka"):
            slowa.pop(0)
        wyslij(tekst_sciezki(" ".join(slowa)), html_=True)
    elif tekst in ("📚 Sprawdziany", "/sprawdziany", "/jutro"):
        wyslij(tekst_sprawdzianow(), html_=True)
    elif tekst in ("💾 Kopia", "/kopia"):
        zapytaj("kopia")
    elif tekst in ("✅ Przejrzane", "/przejrzane"):
        zapytaj("przejrzane")
    elif tekst in ("🔄 Restart", "/restart"):
        wyslij("Co zrestartować?", przyciski={"inline_keyboard": [
            [{"text": "🌐 Portal", "callback_data": "tak:restart_portalu"}],
            [{"text": "🎮 Minecraft (rozłączy graczy)", "callback_data": "tak:restart_minecrafta"}],
            [{"text": "✖ Nic", "callback_data": "nie"}]]})
    elif tekst in ("🆕 Nowa rozmowa", "/nowa"):
        with LOCK:
            nowa_sesja(stan())
        wyslij("🧹 Zaczynamy nową rozmowę z Claude.")
    elif tekst in ("/start", "/pomoc"):
        wyslij("Przyciski na dole. Każdą inną wiadomość przekazuję do Claude na Pi.")
    else:
        do_claude([], tekst)


def main():
    if not TOKEN:
        raise SystemExit("Brak TELEGRAM_TOKEN")
    with LOCK:
        s = stan()
        zapisz(s)
    tg("setMyCommands", commands=[{"command": c, "description": d} for c, d in (
        ("stan", "Stan serwera"), ("sprawdziany", "Najbliższe sprawdziany"), ("sciezka", "Kto i gdzie wchodził dziś (albo: /sciezka wczoraj)"), ("kopia", "Kopia systemu teraz"),
        ("przejrzane", "Zgaś żółtą diodę"), ("restart", "Restart portalu lub Minecrafta"), ("nowa", "Nowa rozmowa z Claude"))])
    threading.Thread(target=petla_powiadomien, daemon=True).start()
    threading.Thread(target=petla_claude, daemon=True).start()
    threading.Thread(target=petla_portalu, daemon=True).start()
    threading.Thread(target=petla_dziennika, daemon=True).start()
    threading.Thread(target=petla_wizyt, daemon=True).start()
    offset = None
    while True:
        wyn = tg_updates(offset)
        if wyn is None:
            time.sleep(5)
            continue
        for u in wyn:
            offset = u["update_id"] + 1
            try:
                obsluz(u)
            except Exception as ex:
                print(f"obsluz: {type(ex).__name__}: {ex}", flush=True)


def tg_updates(offset):
    dane = {"timeout": 50, "allowed_updates": ["message", "callback_query"]}
    if offset:
        dane["offset"] = offset
    req = urllib.request.Request(API + "getUpdates", data=json.dumps(dane).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=70) as r:
            return json.loads(r.read()).get("result")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as ex:
        print(f"getUpdates: {ex}", flush=True)
        return None


if __name__ == "__main__":
    main()
