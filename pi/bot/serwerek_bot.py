#!/usr/bin/env python3
"""
Bot Telegram serwerka (@SerwerekAntek_bot): powiadomienia, przyciski i rozmowa z Claude na Pi.

  - Powiadomienia: czerwone problemy z monitora zdrowia od razu (o kazdej porze) i ich koniec; zolte od razu poza
    cisza nocna (22-7; z nocy przychodza rano); nauka: dzien przed sprawdzianem/kartkowka (18:00), 3 dni przed
    sprawdzianem (18:00) i rano w dniu (7:00).
  - Wejscia z sieci domowej (sekcja „wejscia”): od razu nowe wejscie, panel logowania, przejscie zabezpieczen,
    nieudane proby i oznaki ataku; po 10 min ciszy podsumowanie calej wizyty; pelny zapis na NAS (30 dni).
  - Zadania (todo): „todo jutro 17:00 trening”, „przypomnij za 20 min pranie”, przycisk 📝 Zadania; przypomnienia
    o czasie z przyciskami zrobione / odloz (dane w portalu: /api/todo, strona /strony/todo/).
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
import re
import os
import random
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import pamiec
import poczta
import mobi
import szybkie
import klaud

KATALOG = Path(__file__).resolve().parent
STAN = KATALOG / "stan.json"
INSTRUKCJA = KATALOG / "instrukcja.md"
CLAUDE = Path("/home/tonyg/.local/bin/claude")
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
USTAWIENIA = {"nauka_wieczor": "18:00", "nauka_rano": "07:00", "cisza_od": 22, "cisza_do": 7,
              "mc_auto_min": 30}         # Minecraft: wyłącz po tylu minutach bez graczy (0 = nigdy)

AKCJE = {   # nazwa: (opis dla przycisku, polecenie)
    "kopia": ("Zrobić kopię systemu na NAS teraz", ["sudo", "systemctl", "start", "--no-block", "kopia-pi"]),
    "restart_portalu": ("Zrestartować portal (strony, diodę)", ["sudo", "systemctl", "restart", "home-portal"]),
    "restart_minecrafta": ("Zrestartować serwer Minecraft (rozłączy graczy)", None),
    "mc_wlacz": ("Włączyć serwer Minecraft", ["sudo", "/usr/local/bin/minecraft", "start"]),
    "mc_wylacz": ("Wyłączyć serwer Minecraft (świat zostanie zapisany)", ["sudo", "/usr/local/bin/minecraft", "stop"]),
    "przejrzane": ("Oznaczyć wszystkie problemy jako przejrzane", None),
}
KLAWIATURA = {"keyboard": [["📊 Stan", "📚 Sprawdziany", "📝 Zadania"], ["🎮 Minecraft", "💾 Kopia", "✅ Przejrzane", "🔄 Restart"],
                           ["🧭 Ścieżka", "📞 Zadzwoń", "🆕 Nowa rozmowa"],
                           [{"text": "📍 Odjazdy obok mnie", "request_location": True}, "🏠 Do domu"]],
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


def wyslij(tekst, html_=False, przyciski=None, chat=None, kto="bot"):
    """wiadomosc do wlasciciela; kazda trafia do wspolnej pamieci (kto: bot = sam z siebie, claude = odpowiedz)"""
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
        if wynik:
            try:
                pamiec.zapisz(kto, "telegram", html.unescape(re.sub(r"<[^>]+>", "", c)) if html_ else c, wynik.get("message_id"))
            except Exception as ex:
                print(f"pamiec: {ex}", flush=True)


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
        mc = us.get("powernukkitx")
        linie.append("🎮 Minecraft: " + ("działa" if mc == "active" else "⏸ wyłączony (włączysz: 🎮 Minecraft)" if mc == "recznie" else f"❌ {mc}"))
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


# sudo na prośbę Claude: znacznik [[SUDO: polecenie]] -> przycisk „Tak” (Telegram) albo „tak” (Linphone) -> bot uruchamia
# `sudo bash -c polecenie` i pokazuje wynik. Claude sam sudo nie uruchomi (setpriv --no-new-privs w claude_odpowiedz).
SUDO_PLIK = KATALOG / "sudo_czeka.json"


def _sudo_lista():
    try:
        return json.loads(SUDO_PLIK.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def sudo_zapisz(polecenie):
    import hashlib
    zid = hashlib.sha256(polecenie.encode()).hexdigest()[:12]
    with LOCK:
        d = {k: v for k, v in _sudo_lista().items() if time.time() - v["t"] < 86400}
        d[zid] = {"cmd": polecenie, "t": time.time()}
        SUDO_PLIK.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return "sudo:" + zid


def sudo_polecenie(akcja):
    """polecenie czekające na zgodę; id to skrót polecenia, więc podmiana w pliku nie przejdzie"""
    import hashlib
    cmd = _sudo_lista().get(akcja[5:], {}).get("cmd")
    return cmd if cmd and hashlib.sha256(cmd.encode()).hexdigest()[:12] == akcja[5:] else None


def czy_akcja(akcja):
    return akcja in AKCJE or akcja.startswith("sudo:")


def opis_akcji(akcja):
    if akcja.startswith("sudo:"):
        return f"Uruchomić jako root (sudo):\n{sudo_polecenie(akcja) or '(polecenie wygasło)'}\n"
    return AKCJE[akcja][0]


def wykonaj_sudo(akcja):
    cmd = sudo_polecenie(akcja)
    if not cmd:
        return "To polecenie sudo wygasło albo już było uruchomione. Poproś Claude jeszcze raz."
    with LOCK:
        d = _sudo_lista()
        d.pop(akcja[5:], None)
        SUDO_PLIK.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    try:
        r = subprocess.run(["sudo", "bash", "-c", cmd], capture_output=True, text=True, timeout=600, cwd="/home/tonyg")
        kod, wyj = r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        kod, wyj = "przekroczony czas (10 min)", ""
    wynik = f"{'✅' if kod == 0 else '❌'} sudo {cmd}\nkod: {kod}" + (f"\n{wyj[-1500:]}" if wyj else "")
    pamiec.zapisz("bot", "telegram", f"Antek zatwierdził i bot uruchomił: {wynik}")      # Claude zobaczy wynik
    return wynik + "\n(Napisz „dalej”, jeśli Claude ma kontynuować.)"


# ---------------------------------------------------------------- kanał: Linphone (główny) albo Telegram (zapasowy)
# Odpowiedź idzie tam, skąd przyszło pytanie. Powiadomienia (alarmy, przypomnienia, sprawdziany, telefon, Minecraft,
# wejścia) idą kanałem, którym Antek ostatnio pisał (domyślnie Linphone); gdy Linphone nie działa, do Telegrama.
# Wysłanie lokalizacji w Telegramie nie zmienia kanału.
def ustaw_kanal(k):
    with LOCK:
        s = stan()
        if s.get("kanal") != k:
            s["kanal"] = k
            zapisz(s)


def linphone_dziala():
    """usługa telefonu zapisuje stan co minutę (telefon.py: zapisz_stan)"""
    try:
        st = json.loads((TELEFON / "stan.json").read_text(encoding="utf-8"))
        return st.get("zarejestrowane") and time.time() - st.get("t", 0) < 180
    except (OSError, ValueError):
        return False


def kanal_powiadomien():
    return "linphone" if stan().get("kanal", "linphone") == "linphone" and linphone_dziala() else "telegram"


def powiadom(tekst, html_=False, przyciski=None, linphone=None, **dodatki):
    """powiadomienie od bota (nie odpowiedź): Linphone albo Telegram, patrz wyżej; linphone = inny tekst dla Linphone
    (bez przycisków: podpowiedź, co odpisać)"""
    if kanal_powiadomien() == "linphone":
        t = linphone or (html.unescape(re.sub(r"<[^>]+>", "", tekst)) if html_ else tekst)
        try:
            do_linphone(t, **dodatki)
            pamiec.zapisz("bot", "linphone", t)
            return
        except OSError as ex:
            print(f"powiadom przez Linphone: {ex}", flush=True)
    wyslij(tekst, html_=html_, przyciski=przyciski)


def zaufaj(mac, tak=True):
    """urządzenie z sieci domowej jako „moje” (wejścia tylko zapisywane) albo z powrotem z powiadomieniami"""
    with LOCK:
        s2 = stan()
        z = s2.setdefault("zaufane", {})
        if tak:
            z[mac] = f"urządzenie {len(z) + 1} ({time.strftime('%d.%m')})"
        else:
            z.pop(mac, None)
        zapisz(s2)
    with WIZYTY_LOCK:
        for w in WIZYTY.values():
            if w.get("mac") == mac:
                w["cichy"] = tak
    return (f"✅ Zapamiętane: {mac} to Twoje urządzenie. Jego wejścia będą tylko zapisywane (🧭 Ścieżka), bez powiadomień."
            if tak else f"🔔 {mac} usunięte z zaufanych: znów będą powiadomienia.")


def zaufaj_ostatnie():
    o = stan().get("ostatnie_urzadzenie")
    return zaufaj(o["mac"]) if o else "Nie wiem, o które urządzenie chodzi."


def widze_alarmy():
    """„widzę” (Telegram: przycisk, Linphone: tekst): nie dzwoń w sprawie trwających czerwonych alarmów"""
    with LOCK:
        s2 = stan()
        n = 0
        for k, v in list(s2["wyslane"].items()):
            if k.startswith("dzwon:") and isinstance(v, float):
                s2["wyslane"][k] = "widze"
                n += 1
        zapisz(s2)
    return "👀 OK, nie będę dzwonić w sprawie alarmu." if n else "Nie ma alarmu, w którego sprawie miałbym dzwonić."


def zapytaj(akcja, dodatek=""):
    opis = opis_akcji(akcja)
    wyslij(f"❓ {opis}?{dodatek}", przyciski={"inline_keyboard": [[{"text": "✅ Tak", "callback_data": f"tak:{akcja}"},
                                                                    {"text": "✖ Nie", "callback_data": "nie"}]]})


def wykonaj(akcja):
    if akcja.startswith("sudo:"):
        return wykonaj_sudo(akcja)
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
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    if r.returncode != 0:
        return f"❌ Nie udało się: {(r.stderr or r.stdout)[-300:]}"
    if akcja in ("mc_wlacz", "mc_wylacz", "restart_minecrafta"):
        MC_BOT["t"] = time.time()
    if akcja in ("mc_wlacz", "mc_wylacz"):
        return "🎮 " + (r.stdout.strip().splitlines() or ["Gotowe."])[-1]
    return {"kopia": "💾 Kopia ruszyła. Postęp: 📊 Stan albo panel na stronie.",
            "restart_portalu": "🔄 Portal zrestartowany.",
            "restart_minecrafta": "🎮 Serwer Minecraft zrestartowany (świat zapisany przed restartem)."}[akcja]


# ---------------------------------------------------------------- Claude
def nowa_sesja(s, powod=None):
    s["sesja"] = {}
    s.setdefault("sesje", {}).clear()
    zapisz(s)
    for pr in PROCESY.values():
        pr.nowa_rozmowa()
    if powod:
        wyslij(f"🧹 Nowa rozmowa z Claude ({powod}).")


def kontekst_sesji(sid):
    """rozmiar kontekstu = tokeny ostatniego wywolania modelu w zapisie sesji (usage w raporcie -p sumuje wszystkie wywolania)"""
    for plik in Path("/home/tonyg/.claude/projects").glob(f"*/{sid}.jsonl"):
        try:
            for linia in reversed(plik.read_text(encoding="utf-8").splitlines()):
                u = ((json.loads(linia).get("message") or {}).get("usage")) if '"usage"' in linia else None
                if u:
                    return sum(u.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens"))
        except (OSError, ValueError):
            pass
    return 0


# prośba o głos: czasowniki i „głosówką/głosem”; samo słowo „głosówki” (np. „nie mogę odsłuchać głosówki”) się nie liczy
GLOS_SLOWA = re.compile(r"\b(przeczytaj|odczytaj|powiedz mi|powiedz to|nagraj|głosówką|glosowka|głosowo|glosowo|głosem|glosem|na głos|na glos|"
                        r"wyślij głosówkę|wyslij glosowke|posłucham|poslucham|chcę posłuchać|chce posluchac)\b", re.I)
TEKST_SLOWA = re.compile(r"\b(wypisz|napisz|odpisz|tekstem|na piśmie|na pismie|pisemnie|bez głosu|bez glosu|w punktach|rozpisz|"
                         r"nie mogę odsłuchać|nie moge odsluchac|nie mogę słuchać|nie moge sluchac|nie słyszę|nie slysze)\b", re.I)
GLOS_PODPOWIEDZ = ("[Twoja odpowiedź zostanie zamieniona na WIADOMOŚĆ GŁOSOWĄ i przeczytana na głos: pisz naturalnymi zdaniami, "
                   "bez emotek, tabel, list i Markdown; liczby i skróty tak, żeby dało się je wygodnie przeczytać.]")


CZYTAJ_PODPOWIEDZ = ("[Antek wprost prosi o przeczytanie / opowiedzenie: tu zasada krótkich odpowiedzi NIE obowiązuje. "
                     "Przeczytaj w całości to, o co prosi (np. całą notatkę, wiersz, listę), naturalnymi zdaniami.]")


def prosi_o_czytanie(tekst):
    """wyraźna prośba „przeczytaj / powiedz / nagraj…” (wtedy pełna odpowiedź, nie skrót)"""
    return bool(GLOS_SLOWA.search(tekst or "")) and not TEKST_SLOWA.search(tekst or "")


def tryb_odpowiedzi(tekst, wejscie):
    """„glos” albo „tekst”: prośba w treści („przeczytaj”, „powiedz”, „nagraj” / „wypisz”, „napisz”) wygrywa;
    bez prośby odpowiedź tym samym sposobem, jakim przyszło pytanie"""
    if TEKST_SLOWA.search(tekst or ""):        # prośba o tekst zawsze wygrywa
        return "tekst"
    if GLOS_SLOWA.search(tekst or ""):
        return "glos"
    return "glos" if wejscie == "glos" else "tekst"


TELEFON_PODPOWIEDZ = ("[To rozmowa TELEFONICZNA: Twoja odpowiedź zostanie przeczytana na głos. Mów krótko (1–2 zdania), "
                      "naturalnie, bez emotek, list, Markdown i adresów. Gdy coś sprawdzasz, zrób to szybko. Tekst Antka "
                      "pochodzi z rozpoznawania mowy i bywa przekręcony: zgadnij sens z kontekstu (np. „do nas” = „do NAS”).]")


WIEDZA = KATALOG / "wiedza_serwer.md"


def instrukcja_pelna(dodatek=""):
    """instrukcja bota + wiedza o serwerze (diagnoza i naprawy) + dodatek dla danego modelu"""
    t = INSTRUKCJA.read_text(encoding="utf-8")
    if WIEDZA.exists():
        t += "\n\n" + WIEDZA.read_text(encoding="utf-8")
    return t + ("\n\n" + dodatek if dodatek else "")


def claude_polecenie(prompt=None, dodatek=""):
    """claude -p z uprawnieniami bota (uprawnienia.json, strażnik, bez sudo) -> (cmd, env); prompt=None: tryb stały
    (klaud.py dopisuje --input-format/--output-format stream-json)"""
    u = json.loads((KATALOG / "uprawnienia.json").read_text())
    cmd = ["setpriv", "--no-new-privs", str(CLAUDE), "-p"] + ([prompt, "--output-format", "json"] if prompt is not None else []) + [
           "--permission-mode", "dontAsk",
           "--append-system-prompt", instrukcja_pelna(dodatek), "--allowedTools", *u["allow"], "--disallowedTools", *u["deny"],
           "--settings", json.dumps({"hooks": u.get("hooks", {})})]
    env = {k: v for k, v in os.environ.items() if k not in ("TELEGRAM_TOKEN", "ANTHROPIC_API_KEY", "SIP_HASLO")
           and not k.startswith(("POCZTA_", "MOBI_"))}            # hasła do poczty i dziennika nie trafiają do Claude
    env["HOME"] = "/home/tonyg"
    return cmd, env


def claude_jednorazowo(prompt, limit=180):
    """osobne zapytanie (bez wspólnej sesji, żeby nie mieszać jej z rozmową Antka) -> tekst albo None"""
    cmd, env = claude_polecenie(pamiec.kontekst(nowa_sesja=True) + "\n\n" + prompt)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=limit, cwd="/home/tonyg", env=env)
        d = json.loads(r.stdout or "{}")
    except (subprocess.TimeoutExpired, ValueError):
        return None
    return None if d.get("is_error") else (d.get("result") or "").strip() or None


def claude_bez_narzedzi(prompt, limit=180):
    """Claude BEZ żadnych narzędzi i bez pamięci rozmów: do treści z zewnątrz (maile, strony), które mogą zawierać
    podstępne polecenia; może tylko odpowiedzieć tekstem"""
    cmd = ["setpriv", "--no-new-privs", str(CLAUDE), "-p", prompt, "--output-format", "json", "--permission-mode", "dontAsk",
           "--tools", "", "--strict-mcp-config"]
    env = {k: v for k, v in os.environ.items() if k not in ("TELEGRAM_TOKEN", "ANTHROPIC_API_KEY", "SIP_HASLO")
           and not k.startswith("POCZTA_") and not k.startswith("MOBI_")}
    env["HOME"] = "/home/tonyg"
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=limit, cwd="/tmp", env=env)
        d = json.loads(r.stdout or "{}")
    except (subprocess.TimeoutExpired, ValueError):
        return None
    return None if d.get("is_error") else d.get("result")


# ---------------------------------------------------------------- Claude: dwa stałe procesy (klaud.py)
# „szybki” = Haiku (niski wysiłek): rozmowa, proste pytania i polecenia; „madry” = Sonnet (średni wysiłek): awarie, naprawy,
# kod, strony nauki, pliki, wszystko dłuższe. Haiku sam oddaje trudne sprawy znacznikiem [[TRUDNE]]. Wspólna pamięć:
# przed każdą wiadomością model dostaje to, co od jego ostatniej odpowiedzi powiedział drugi model albo bot (pamiec.od_id).
MODELE = {"szybki": ("claude-haiku-5-5", "low"), "madry": ("claude-sonnet-5-5", "medium")}
DODATEK_SZYBKI = ("[Jesteś szybkim modelem (Haiku) do rozmowy i prostych spraw. Jeśli prośba wymaga diagnozy awarii albo "
                  "naprawy serwera, zmian w plikach lub konfiguracji, pisania kodu albo stron, analizy materiałów, planowania "
                  "kilku kroków albo nie jesteś pewien, jak to dobrze zrobić: odpowiedz WYŁĄCZNIE znacznikiem [[TRUDNE]] "
                  "(przejmie to mądrzejszy model). Proste pytania, rozmowę, sprawdzenie stanu, todo, budziki rób sam.]")
TRUDNE_RE = re.compile(r"napraw|nie dzia|nie odpal|nie łącz|nie lacz|awari|błęd|błąd|bledu|blad|wyłączył|wylaczyl|wysypa|padł|padl|"
                       r"zepsu|problem|dlaczego|czemu|zrób|zrob|napisz|stron|\bkod|skrypt|program|nauk|sprawdzian|kartkówk|"
                       r"kartkowk|materia|zdjęc|zdjec|pdf|analiz|porówn|porown|zaplanuj|konfigur|instal|aktualiz|\bnas\b|dysk|"
                       r"kopi[aęi]|backup|tailscale|\bssh|\bvnc|portal|usług|uslug|\blog|sudo|restart|plik|folder|wytłumacz|"
                       r"wytlumacz|wyjaśnij|wyjasnij|przelicz|oblicz|rozwiąż|rozwiaz|zadani[ea] z |przetłumacz|przetlumacz", re.I)
USLUGA = Path(sys.argv[0]).stem or "bot"      # bot i telefon mają osobne procesy i sesje (nie piszą do jednej sesji naraz)
PROCESY = {n: klaud.Proces(n, m, e, (lambda n=n: claude_polecenie(None, DODATEK_SZYBKI if n == "szybki" else "")))
           for n, (m, e) in MODELE.items()}
PAMIEC_ID = {}          # nazwa procesu -> id ostatniej wiadomości w pamięci, którą już zna


def wybierz_model(tekst, kanal):
    if kanal == "plik" or len(tekst) > 220 or TRUDNE_RE.search(tekst):
        return "madry"
    return "szybki"


def zapytaj_model(nazwa, tekst, kanal, odpowiedz_na=None, glosem=False):
    """wiadomość do stałego procesu: nowa rozmowa po godzinie ciszy albo przy dużym kontekście; kontekst z pamięci"""
    pr = PROCESY[nazwa]
    klucz = f"{USLUGA}-{nazwa}"
    with LOCK:
        s = stan()
        zap = s.setdefault("sesje", {}).get(klucz, {})
    if pr.sesja is None and zap.get("id") and time.time() - zap.get("ostatnio", 0) < KONTEKST_CISZA:
        pr.sesja = zap["id"]                    # po restarcie bota: wznów rozmowę
        PAMIEC_ID.setdefault(nazwa, zap.get("pamiec_id", 0))
    if pr.sesja and (time.time() - (pr.ostatnio or zap.get("ostatnio", 0)) > KONTEKST_CISZA or pr.kontekst >= KONTEKST_MAX):
        pr.nowa_rozmowa()
    nowa = pr.sesja is None
    if nowa:
        pam = pamiec.kontekst(nowa_sesja=True, odpowiedz_na=odpowiedz_na)
    else:
        pam = pamiec.od_id(PAMIEC_ID.get(nazwa, 0))
        pam = ("W międzyczasie (inny kanał, drugi model albo bot):\n" + pam if pam else "") + \
            ("\n\nAntek odpowiada na: " + pamiec._linia(*odpowiedz_na[:2], "", odpowiedz_na[2], 800) if odpowiedz_na else "")
    prompt = (pam.strip() + "\n\nNowa wiadomość od Antka" + {"telefon": " (mówi przez telefon)", "glosowka_zapisana": " (wiadomość głosowa)",
                                                             "linphone": " (pisze na Linphone)"}.get(kanal, "") + ":\n" + tekst) if pam.strip() else tekst
    if kanal == "telefon":
        prompt = TELEFON_PODPOWIEDZ + "\n\n" + prompt
    elif glosem:
        prompt = GLOS_PODPOWIEDZ + "\n\n" + prompt
    if kanal != "telefon" and prosi_o_czytanie(tekst):
        prompt = CZYTAJ_PODPOWIEDZ + "\n\n" + prompt
    t0 = time.time()
    d = pr.zapytaj(prompt, limit=600 if kanal == "telefon" else 1800)
    print(f"klaud {nazwa}: {time.time() - t0:.1f} s ({kanal}): {tekst[:50]}", flush=True)
    if not d.get("is_error") and d.get("session_id"):
        pr.kontekst = kontekst_sesji(d["session_id"]) or pr.kontekst
        PAMIEC_ID[nazwa] = pamiec.ostatnie_id()
        with LOCK:
            s = stan()
            s.setdefault("sesje", {})[klucz] = {"id": d["session_id"], "ostatnio": time.time(), "pamiec_id": PAMIEC_ID[nazwa]}
            zapisz(s)
    return d


def rozgrzej(nazwy=("szybki", "madry")):
    """start procesów zawczasu (pierwsza odpowiedź też szybka)"""
    for n in nazwy:
        pr = PROCESY[n]
        with pr.lock:
            if pr.p is None:
                zap = stan().get("sesje", {}).get(f"{USLUGA}-{n}", {})
                if zap.get("id") and time.time() - zap.get("ostatnio", 0) < KONTEKST_CISZA:
                    pr.sesja = zap["id"]
                    PAMIEC_ID.setdefault(n, zap.get("pamiec_id", 0))
                pr._start(pr.sesja)


# ---------------------------------------------------------------- szybkie odpowiedzi bez AI (szybkie.py)
def _sprawdziany_wszystkie():
    """zapowiedzi z Mobidziennika (z godziną) + strony Nauki, bez powtórzeń"""
    m = list(mobi.wczytaj("stan", {}).get("sprawdziany", {}).values())
    k = lambda x: (x.get("data"), re.sub(r"[^a-z]", "", (x.get("przedmiot") or "").lower())[:5])
    znane = {k(x) for x in m}
    return sorted(m + [{"data": x["data"], "godzina": "", "przedmiot": x.get("przedmiot", ""), "rodzaj": x.get("typ", "sprawdzian"),
                        "tematyka": x.get("tytul", "")} for x in sprawdziany() if x.get("data") and k(x) not in znane], key=lambda x: x["data"])


def _serwer_krotko():
    z = portal("/api/zdrowie")
    p = z.get("pomiary", {})
    return ({"ok": "Serwer działa dobrze", "warn": "Serwer działa, ale jest coś do sprawdzenia", "crit": "Serwer wymaga uwagi"}[z["stan"]]
            + f": {p.get('temp', '?')} °C, procesor {round(p.get('cpu') or 0)}%, RAM {round(p.get('ram') or 0)}%."
            + ("" if not z.get("aktywne") else " Problemy: " + "; ".join(i["tytul"] for i in z["aktywne"][:3]) + "."))


def _mc_krotko():
    m = portal("/api/minecraft")
    return (f"Minecraft działa od {(m.get('od') or '')[11:16]}, gracze: {m.get('gracze')}." if m.get("dziala") else "Minecraft jest wyłączony.")


SZYBKIE_DANE = {
    "plan": lambda: mobi.wczytaj("stan", {}).get("plan", []),
    "sprawdziany": _sprawdziany_wszystkie,
    "zadania_domowe": lambda: mobi.wczytaj("stan", {}).get("zadania", []),
    "todo": lambda: zadania_do_zrobienia(),
    "budziki": lambda: [opis_alarmu(a) for a in sorted(portal("/api/alarmy")["alarmy"], key=lambda a: nastepny_alarm(a) or datetime.max)
                        if nastepny_alarm(a)],
    "serwer": _serwer_krotko,
    "minecraft": _mc_krotko,
    "poczta": lambda: poczta.podsumowanie() if poczta.konta() else "Poczta nie jest jeszcze podłączona.",
    "odjazdy": lambda skad: ztm_api("/api/ztm/odjazdy", skad=skad, ile=4).get("tekst") or "Brak danych o odjazdach.",
    "trasa": lambda dokad: ztm_api("/api/ztm/trasa", skad="tu", dokad=dokad).get("tekst") or "Brak danych o trasie.",
}
SZYBKIE_STAT = KATALOG / "szybkie_statystyka.json"


def szybka_odpowiedz(tekst):
    """pytanie rozpoznane bez AI -> odpowiedź z danych na Pi (albo None)"""
    t0 = time.time()
    w = szybkie.odpowiedz(tekst, SZYBKIE_DANE)
    if not w:
        return None
    print(f"szybka odpowiedź ({w[0]}, {time.time() - t0:.2f} s): {tekst[:60]}", flush=True)
    try:
        st = json.loads(SZYBKIE_STAT.read_text()) if SZYBKIE_STAT.exists() else {}
        st[w[0]] = st.get(w[0], 0) + 1
        SZYBKIE_STAT.write_text(json.dumps(st))
    except (OSError, ValueError):
        pass
    return w[1]


def claude_odpowiedz(tekst, kanal="telegram", odpowiedz_na=None, pisze=True, glosem=False):
    """jedna wiadomosc do Claude (wspolna sesja dla czatu, glosowek i telefonu) -> (odpowiedz, akcje) albo wyjatek RuntimeError.
    Najpierw szybkie odpowiedzi bez AI (plan, sprawdziany, godzina…), gdy pytanie jest rozpoznane."""
    if not odpowiedz_na and kanal != "plik" and (sz := szybka_odpowiedz(tekst)):
        if kanal not in ("telegram", "glosowka_zapisana"):
            pamiec.zapisz("antek", kanal, tekst)
        return sz, []
    if kanal not in ("telegram", "glosowka_zapisana"):      # czat i glosowki zapisuje juz obsluz()/glosowka()
        pamiec.zapisz("antek", kanal, tekst)
    nazwa = wybierz_model(tekst, kanal)
    stop = threading.Event()

    def pisze_():
        while not stop.is_set():
            tg("sendChatAction", timeout=10, chat_id=stan()["wlasciciel"], action="typing")
            stop.wait(5)
    if pisze:
        threading.Thread(target=pisze_, daemon=True).start()
    try:
        d = zapytaj_model(nazwa, tekst, kanal, odpowiedz_na, glosem)
        if nazwa == "szybki" and "[[TRUDNE]]" in (d.get("result") or ""):     # Haiku: „to dla Sonneta”
            print(f"klaud: Haiku przekazał do Sonneta: {tekst[:60]}", flush=True)
            nazwa = "madry"
            d = zapytaj_model(nazwa, tekst, kanal, odpowiedz_na, glosem)
    finally:
        stop.set()
    odp = d.get("result") or ""
    if d.get("is_error"):
        PROCESY[nazwa].nowa_rozmowa()           # np. sesja wygasła po stronie Claude: następna wiadomość od nowa
        raise RuntimeError(odp or "błąd")
    odp = odp.replace("[[TRUDNE]]", "").strip()
    if m := re.search(r"\[\[INTENCJA:\s*(\w+)\s*\]\]", odp):       # Claude rozpoznał znaną intencję: zapamiętaj sformułowanie
        szybkie.naucz(tekst, m.group(1))
        odp = re.sub(r"\s*\[\[INTENCJA:\s*\w+\s*\]\]", "", odp)
    akcje = [a for a in AKCJE if f"[[AKCJA: {a}]]" in odp]
    for a in AKCJE:
        odp = odp.replace(f"[[AKCJA: {a}]]", "")
    for m in re.finditer(r"\[\[SUDO:\s*(.+?)\s*\]\]", odp, re.S):
        akcje.append(sudo_zapisz(m.group(1)))
    odp = re.sub(r"\[\[SUDO:\s*(.+?)\s*\]\]", "", odp, flags=re.S)
    return odp.strip(), akcje


def claude(tekst, kanal="telegram", odpowiedz_na=None, glosem=None):
    """glosem: None = sam zdecyduj (tryb_odpowiedzi); głosem idzie wiadomość głosowa z tekstem w podpisie"""
    if glosem is None:
        glosem = tryb_odpowiedzi(tekst, "glos" if kanal.startswith("glosowka") else "tekst") == "glos"
    try:
        odp, akcje = claude_odpowiedz(tekst, kanal, odpowiedz_na, glosem=glosem)
    except RuntimeError as ex:
        wyslij(f"⚠️ Claude: {ex}\nSpróbuj jeszcze raz.")
        return
    if not glosem or not wyslij_glos(odp):
        wyslij(odp, kto="claude")
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
                powiadom(f"🔴 <b>{e(i['tytul'])}</b>\n{e(i['opis'])}\n\n{LINK_DOM}/strony/zdrowie/", html_=True,
                         przyciski={"inline_keyboard": [[{"text": "👀 Widzę (nie dzwoń)", "callback_data": f"widze:{i['id']}"}]]},
                         linphone=f"🔴 {i['tytul']}\n{i['opis']}\n{LINK_DOM}/strony/zdrowie/\nOdpisz „widzę”, to nie zadzwonię za 10 min.")
                w[k] = "crit"
                w["dzwon:" + i["id"]] = time.time()
            elif not i.get("do") and poziom == "crit" and isinstance(w.get("dzwon:" + i["id"]), float) \
                    and time.time() - w["dzwon:" + i["id"]] > 600:
                zadzwon(f"Uwaga, problem na serwerze: {i['tytul']}. {i['opis']}", "czerwony alarm bez reakcji przez 10 minut")
                w["dzwon:" + i["id"]] = "zadzwoniono"
            elif i.get("do") and w.get(k) == "crit":
                powiadom(f"✅ Minęło: <b>{e(i['tytul'])}</b> (od {i['od'][11:16]} do {i['do'][11:16]})", html_=True)
                w[k] = "koniec"
            elif k not in w and poziom == "warn":
                zolte.append(i)
        if zolte and not cisza_nocna(s):       # w nocy czekaja do rana (wtedy jedna wiadomosc z lista)
            naglowek = "🟡 <b>Do sprawdzenia</b>" if len(zolte) == 1 else f"🟡 <b>Do sprawdzenia ({len(zolte)})</b>"
            powiadom(naglowek + "\n" + "\n".join(f"• {e(i['tytul'])}: {e(i['opis'])}" + (" (już minęło)" if i.get("do") else "")
                                                  for i in zolte) + "\n\nPo przejrzeniu: ✅ Przejrzane", html_=True,
                     linphone="🟡 Do sprawdzenia:\n" + "\n".join(f"• {i['tytul']}: {i['opis']}" + (" (już minęło)" if i.get("do") else "")
                                                            for i in zolte) + "\nPo przejrzeniu odpisz „przejrzane”.")
            for i in zolte:
                w["inc:" + i["id"]] = "warn"
        aktualne = {"inc:" + i["id"] for i in wszystkie}
        for k in [k for k in w if (k.startswith("inc:") and k not in aktualne) or (k.startswith("dzwon:") and "inc:" + k[6:] not in aktualne)]:
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
            powiadom(f"{tekst}\n{e(x['tytul'])}\nPowtórz zakładkę „Najważniejsze”: {link_sprawdzianu(x)}", html_=True)
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


def mac_ip(ip):
    try:
        out = subprocess.run(["ip", "neigh", "show", ip], capture_output=True, text=True, timeout=5).stdout
        return out.split("lladdr")[1].split()[0] if "lladdr" in out else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


TS_NAZWY = {"t": 0, "nazwy": {}}


def nazwa_tailscale(ip):
    """nazwa urzadzenia Tailscale po adresie 100.x (lista odswiezana co 5 min)"""
    if time.time() - TS_NAZWY["t"] > 300:
        try:
            d = json.loads(subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=10).stdout)
            TS_NAZWY["nazwy"] = {a: p.get("HostName", "?") for p in list((d.get("Peer") or {}).values()) + [d.get("Self") or {}]
                                 for a in p.get("TailscaleIPs") or []}
            TS_NAZWY["t"] = time.time()
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return TS_NAZWY["nazwy"].get(ip, "?")


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
    """krok: opis do sladu wizyty i logu NAS; alarm: (ikona, tytul, dodatek) do wyslania od razu.
    Ciche (tylko zapis, bez powiadomien): Tailscale (100.x) i zaufane urzadzenia wlasciciela (MAC w stan["zaufane"])."""
    if not ip or ip in ("127.0.0.1", "172.23.0.20", "172.23.0.24", "100.108.241.58"):      # samo Pi
        return
    teraz = time.time()
    if ip not in WIZYTY:
        if ip.startswith("100."):
            urz_nowe, mac, cichy = f"Tailscale: {nazwa_tailscale(ip)}", "", True
        else:
            mac = mac_ip(ip)
            zaufane = stan().get("zaufane", {})
            urz_nowe, cichy = urzadzenie(ip), bool(mac) and mac in zaufane
            if cichy:
                urz_nowe = f"zaufane: {zaufane[mac]}, " + urz_nowe
    else:
        urz_nowe = mac = None
        cichy = WIZYTY[ip].get("cichy", False)
    with WIZYTY_LOCK:
        w = WIZYTY.get(ip)
        nowa = w is None
        if nowa:
            w = WIZYTY[ip] = {"od": teraz, "ostatnio": teraz, "kroki": [], "alarmy": {}, "urz": urz_nowe or "", "liczniki": {},
                              "cichy": cichy, "mac": mac}
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
    if not stan()["wlasciciel"] or w.get("cichy"):
        return
    kto = f"IP: <code>{e(ip)}</code>" + (f" ({e(urz)})" if urz else "")
    if nowa:
        przyc = {"inline_keyboard": [[{"text": "✅ To moje urządzenie (nie powiadamiaj)", "callback_data": f"zaufaj:{w['mac']}"}]]} if w.get("mac") else None
        powiadom(f"🚪 <b>Nowe wejście na Pi z sieci domowej</b>\n{kto}\nPierwszy krok: {e(krok)}", html_=True, przyciski=przyc,
                 linphone=f"🚪 Nowe wejście na Pi z sieci domowej\nIP: {ip}" + (f" ({urz})" if urz else "") + f"\nPierwszy krok: {krok}"
                 + ("\nTo Twoje urządzenie? Odpisz „to moje”." if w.get("mac") else ""))
        if w.get("mac"):
            with LOCK:
                s2 = stan()
                s2["ostatnie_urzadzenie"] = {"mac": w["mac"], "nazwa": urz or ip}
                zapisz(s2)
    if wyslac:
        ikona, tytul, dodatek = alarm
        powiadom(f"{ikona} <b>{e(tytul)}</b>\n{kto}" + (f"\n{e(dodatek)}" if dodatek else ""), html_=True)


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
                return opis.format(*m.groups()) + ("" if z.get("zalogowany") or z.get("tailscale") else " → strona logowania (bez hasła)"), None, None, 0
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


# ---------------------------------------------------------------- zadania (todo) i przypomnienia
# Dane w portalu (/api/todo, dane/todo.json, strona /strony/todo/). Bot: dodawanie („todo …”, „przypomnij …”),
# lista (📝 Zadania) i przypomnienia o czasie (co 30 s), z przyciskami: zrobione, +15 min, +1 h, jutro.
DNI_TYG = {"poniedziałek": 0, "poniedzialek": 0, "wtorek": 1, "środa": 2, "środę": 2, "sroda": 2, "srode": 2, "czwartek": 3,
           "piątek": 4, "piatek": 4, "sobota": 5, "sobotę": 5, "sobote": 5, "niedziela": 6, "niedzielę": 6, "niedziele": 6}


def parsuj_zadanie(tekst):
    """„jutro o 17 trening”, „za 20 min wyjąć pranie”, „w piątek 8:30 dentysta”, „25.10 18:00 urodziny”,
    „codziennie 21:00 leki” -> (tekst, termin "RRRR-MM-DDTHH:MM" albo None, powtarzaj)"""
    import re as r_
    t = " " + tekst.strip() + " "
    teraz = datetime.now()
    dzien = godz = None
    powt = None
    for wzor, p in ((r"\s(codziennie|co\s+dzień|co\s+dzien)\s", "dzien"), (r"\sco\s+tydzień\s|\sco\s+tydzien\s", "tydzien"),
                    (r"\sco\s+miesiąc\s|\sco\s+miesiac\s", "miesiac")):
        if r_.search(wzor, t, r_.I):
            powt, t = p, r_.sub(wzor, " ", t, count=1, flags=r_.I)
    if m := r_.search(r"\sza\s+(\d+)\s*(min|minut|minuty|minutę|h|godz|godzin|godziny|godzinę|dni|dzień|dzien)\b\.?", t, r_.I):
        n, j = int(m.group(1)), m.group(2).lower()
        delta = timedelta(minutes=n) if j.startswith("min") else timedelta(days=n) if j.startswith("d") else timedelta(hours=n)
        kiedy = teraz + delta
        t = t[:m.start()] + " " + t[m.end():]
        return " ".join(t.split()), kiedy.strftime("%Y-%m-%dT%H:%M"), powt
    if m := r_.search(r"\s(dziś|dzis|dzisiaj|jutro|pojutrze)\s", t, r_.I):
        dzien = teraz.date() + timedelta(days={"jutro": 1, "pojutrze": 2}.get(m.group(1).lower(), 0))
        t = t[:m.start()] + " " + t[m.end():]
    elif m := r_.search(r"\s(?:w\s+|we\s+)?(" + "|".join(DNI_TYG) + r")\s", t, r_.I):
        cel = DNI_TYG[m.group(1).lower()]
        dzien = teraz.date() + timedelta(days=(cel - teraz.weekday()) % 7 or 7)
        t = t[:m.start()] + " " + t[m.end():]
    elif m := r_.search(r"\s(\d{4})-(\d{2})-(\d{2})\s", t):
        dzien = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        t = t[:m.start()] + " " + t[m.end():]
    elif m := r_.search(r"\s(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\s", t):
        try:
            dzien = date(int(m.group(3) or teraz.year), int(m.group(2)), int(m.group(1)))
            if not m.group(3) and dzien < teraz.date():
                dzien = dzien.replace(year=dzien.year + 1)
            t = t[:m.start()] + " " + t[m.end():]
        except ValueError:
            dzien = None
    # godzina: „17:30” zawsze, „17.30” i „17” tylko po „o”/„na”/„godz.” (żeby „3.14 rozdziału” nie było godziną)
    if m := r_.search(r"\s(?:o\s+|na\s+)?(?:godz\.?\s+)?(\d{1,2}):(\d{2})\s", t, r_.I) or \
            r_.search(r"\s(?:o|na|godz\.?)\s+(?:godz\.?\s+)?(\d{1,2})(?:\.(\d{2}))?\s", t, r_.I):
        g, mi = int(m.group(1)), int(m.group(2) or 0)
        if g < 24 and mi < 60:
            godz = (g, mi)
            t = t[:m.start()] + " " + t[m.end():]
    if dzien is None and godz is None:
        return " ".join(t.split()), None, None
    if godz is None:
        godz = (9, 0)
    if dzien is None:
        dzien = teraz.date()
        if (godz[0], godz[1]) <= (teraz.hour, teraz.minute):
            dzien += timedelta(days=1)
    return " ".join(t.split()), f"{dzien.isoformat()}T{godz[0]:02d}:{godz[1]:02d}", powt


def kiedy_tekst(termin):
    if not termin:
        return "bez terminu"
    d = datetime.strptime(termin, "%Y-%m-%dT%H:%M")
    dz = (d.date() - date.today()).days
    nazwa = {0: "dziś", 1: "jutro", -1: "wczoraj"}.get(dz) or d.strftime("%d.%m")
    return f"{nazwa} {d.strftime('%H:%M')}"


POWT_T = {"dzien": " · 🔁 codziennie", "tydzien": " · 🔁 co tydzień", "miesiac": " · 🔁 co miesiąc"}


def nowe_zadanie(tekst):
    """„jutro 17:00 trening (zadzwoń)” -> zapis w portalu; (zadanie, opis, termin, powt, dzwon) albo None (pusty opis).
    Wspólne dla Telegrama i czatu Linphone."""
    wz = r"(zadzwoń|zadzwon|dzwoń|dzwon|bardzo\s+ważne|bardzo\s+wazne|ważne|wazne|pilne)(?!\w)"     # „bardzo ważne” = Pi dzwoni
    dzwon = bool(re.search(r"(?<!\w)" + wz, tekst, re.I))
    tekst = re.sub(r"\s*(?<!\w)(i\s+)?" + wz + r"[!:,]*", "", tekst, flags=re.I)
    opis, termin, powt = parsuj_zadanie(tekst)
    if not opis:
        return None
    z = portal("/api/todo", {"tekst": opis, "termin": termin, "powtarzaj": powt, "dzwon": dzwon and bool(termin)})
    return z, opis, termin, powt, dzwon and bool(termin)


def dodaj_zadanie(tekst):
    w = nowe_zadanie(tekst)
    if not w:
        wyslij("Napisz, co dodać, np. „todo jutro 17:00 trening” albo „przypomnij za 20 min pranie”.")
        return
    z, opis, termin, powt, dzwon = w
    powt_t = POWT_T.get(powt, "")
    wyslij(f"📝 Dodane: <b>{e(opis)}</b>\n⏰ {kiedy_tekst(termin) if termin else 'bez terminu (bez przypomnienia)'}{powt_t}"
           + (" · 📞 zadzwonię" if dzwon and termin else ""), html_=True,
           przyciski={"inline_keyboard": [[{"text": "🗑 Cofnij", "callback_data": f"todo_usun:{z['id']}"}]
                                          + ([{"text": "📞 Bardzo ważne: zadzwoń", "callback_data": f"todo_dzwon:{z['id']}"}] if termin and not dzwon else [])]})


def zadania_do_zrobienia():
    """niezrobione zadania w kolejności listy (numery 1, 2, … w „zadania” = pozycje tutaj)"""
    lista = [z for z in portal("/api/todo")["zadania"] if not z.get("zrobione")]
    lista.sort(key=lambda z: (z.get("termin") or "9999", z["utworzono"]))
    return lista


def tekst_zadan():
    lista = zadania_do_zrobienia()
    if not lista:
        return "📝 Nic nie czeka. 🎉\nDodaj: „todo jutro 17:00 trening”.", None
    teraz = datetime.now().strftime("%Y-%m-%dT%H:%M")
    linie = ["<b>📝 Do zrobienia</b>"]
    for i, z in enumerate(lista[:20], 1):
        spoz = " ⚠️" if z.get("termin") and z["termin"] < teraz else ""
        powt = " 🔁" if z.get("powtarzaj") else ""
        linie.append(f"{i}. {e(z['tekst'])} · <i>{kiedy_tekst(z.get('termin'))}</i>{spoz}{powt}")
    spr = [x for x in sprawdziany() if x.get("data") and 0 <= (date.fromisoformat(x["data"]) - date.today()).days <= 14]
    if spr:
        linie.append("\n<b>📚 Sprawdziany i kartkówki</b>")
        for x in sorted(spr, key=lambda x: x["data"]):
            dz = (date.fromisoformat(x["data"]) - date.today()).days
            linie.append(f"• {e(x['przedmiot'])} ({e(x['typ'])}): <i>{'dziś' if dz == 0 else 'jutro' if dz == 1 else f'za {dz} dni'}</i>")
    linie.append(f"\nWszystkie: {LINK_DOM}/strony/todo/")
    przyc = [[{"text": f"✅ {i}", "callback_data": f"todo_ok:{z['id']}"} for i, z in list(enumerate(lista[:20], 1))[k:k + 5]] for k in range(0, min(len(lista), 20), 5)]
    return "\n".join(linie), {"inline_keyboard": przyc}


PRZYGOTOWANE = {}      # id zadania z telefonem -> {"termin", "tekst" (None = Claude jeszcze myśli)}


def przygotuj_rozmowe(z):
    """kilka minut przed terminem Claude układa, co powie, gdy Antek odbierze (żeby od razu mówić, bez czekania)"""
    tekst = claude_jednorazowo(
        f"[Za kilka minut, o {z['termin'][11:16]}, Pi dzwoni do Antka przez Linphone z przypomnieniem: „{z['tekst']}”. "
        "Napisz DOKŁADNIE to, co powiesz, gdy odbierze: 1–3 krótkie zdania po polsku, naturalnie, bez emotek, list "
        "i Markdown (zostanie przeczytane na głos). Zinterpretuj przypomnienie: powiedz, o czym pamiętać i co zrobić "
        "(możesz krótko coś sprawdzić, np. stan serwera, plan, pogodę, jeśli to pomaga). Bez pytań i formułek na końcu "
        "typu „jeśli chcesz coś powiedzieć” (Antek i tak może mówić po Tobie; „odhaczone” / „zrobione” zamyka zadanie). "
        "Nic poza samą wypowiedzią.]")
    PRZYGOTOWANE[z["id"]] = {"termin": z["termin"], "tekst": tekst or None, "gotowe": True}
    print(f"przygotowane przypomnienie {z['id']}: {(tekst or 'brak')[:80]}", flush=True)


def przypomnienia():
    if not stan()["wlasciciel"]:
        return
    teraz = datetime.now().strftime("%Y-%m-%dT%H:%M")
    za_chwile = (datetime.now() + timedelta(minutes=4)).strftime("%Y-%m-%dT%H:%M")
    for z in portal("/api/todo")["zadania"]:
        if (z.get("dzwon") and not z.get("zrobione") and z.get("termin") and not z.get("wyslano") and z["termin"] <= za_chwile
                and PRZYGOTOWANE.get(z["id"], {}).get("termin") != z["termin"]):
            PRZYGOTOWANE[z["id"]] = {"termin": z["termin"], "tekst": None}
            threading.Thread(target=przygotuj_rozmowe, args=(z,), daemon=True).start()
        if z.get("zrobione") or not z.get("termin") or z.get("wyslano") or z["termin"] > teraz:
            continue
        if z.get("dzwon"):
            p = PRZYGOTOWANE.pop(z["id"], {})
            powitanie = p.get("tekst") if p.get("termin") == z["termin"] and p.get("tekst") else f"Przypomnienie: {z['tekst']}."
            pamiec.zapisz("bot", "telefon", f"Dzwonię z przypomnieniem „{z['tekst']}” i mówię: {powitanie}")
            zadzwon(powitanie, "przypomnienie z telefonem", todo_id=z["id"])
        powt = {"dzien": "\n🔁 codziennie", "tydzien": "\n🔁 co tydzień", "miesiac": "\n🔁 co miesiąc"}.get(z.get("powtarzaj"), "")
        powiadom(f"⏰ <b>{e(z['tekst'])}</b>\n{kiedy_tekst(z['termin'])}{powt}", html_=True, todo_id=z["id"],
                 linphone=f"⏰ {z['tekst']}\n{kiedy_tekst(z['termin'])}{powt}\nOdpisz: zrobione, +15, +1h albo +jutro.", przyciski={"inline_keyboard": [
            [{"text": "✅ Zrobione", "callback_data": f"todo_ok:{z['id']}"}],
            [{"text": "⏰ +15 min", "callback_data": f"todo_odloz:{z['id']}:15"}, {"text": "⏰ +1 h", "callback_data": f"todo_odloz:{z['id']}:60"},
             {"text": "⏰ Jutro", "callback_data": f"todo_odloz:{z['id']}:jutro"}]]})
        portal(f"/api/todo/{z['id']}", {"wyslano": True})


def petla_przypomnien():
    while True:
        try:
            przypomnienia()
        except Exception as ex:
            print(f"przypomnienia: {type(ex).__name__}: {ex}", flush=True)
        time.sleep(30)


def callback_zadania(dane):
    _, zid, *reszta = dane.split(":")
    if dane.startswith("todo_ok:"):
        z = portal(f"/api/todo/{zid}", {"zrobione": True})
        if z.get("powtarzaj") and not z.get("zrobione"):
            return f"✅ Zrobione. Następnym razem: {kiedy_tekst(z['termin'])}."
        return f"✅ Zrobione: {z['tekst']}"
    if dane.startswith("todo_dzwon:"):
        z = portal(f"/api/todo/{zid}", {"dzwon": True})
        return f"📞 Bardzo ważne: {kiedy_tekst(z.get('termin'))} zadzwonię i napiszę."
    if dane.startswith("todo_usun:"):
        portal(f"/api/todo/{zid}", {"usun": True})
        return "🗑 Usunięte."
    if dane.startswith("todo_odloz:"):
        if reszta[0] == "jutro":
            z = next(x for x in portal("/api/todo")["zadania"] if x["id"] == zid)
            stary = datetime.strptime(z["termin"], "%Y-%m-%dT%H:%M") if z.get("termin") else datetime.now()
            nowy = datetime.combine(date.today() + timedelta(days=1), stary.time()).strftime("%Y-%m-%dT%H:%M")
            z = portal(f"/api/todo/{zid}", {"termin": nowy})
        else:
            z = portal(f"/api/todo/{zid}", {"odloz_min": int(reszta[0])})
        return f"⏰ Przypomnę {kiedy_tekst(z['termin'])}."
    return "?"


# ---------------------------------------------------------------- budziki (portal: /api/alarmy, dane/alarmy.json)
# O godzinie budzika Pi dzwoni przez Linphone i czyta poranny przegląd (serwer, poczta, lekcje i zmiany planu,
# sprawdziany, zadania); tekst układa Claude ok. 3 min wcześniej. Nieodebrany: jeszcze 2 razy co 5 min.
DNI_NAZWY = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
BUDZIK_TEKST = {}       # id budzika -> {"na": "RRRR-MM-DDTHH:MM", "tekst": None (Claude jeszcze układa) | str}
BUDZIK_PONOW = []       # [(kiedy, zlecenie)] nieodebrane budziki
BUDZIK_PROB = 3
BUDZIK_CO = 300


def nastepny_alarm(a, teraz=None):
    """najbliższe dzwonienie budzika (datetime) albo None; spóźnienie do 10 min wciąż się liczy"""
    teraz = teraz or datetime.now()
    if not a.get("aktywny"):
        return None
    h, m = map(int, a["godzina"].split(":"))
    if a.get("data"):
        t = datetime.strptime(f"{a['data']} {a['godzina']}", "%Y-%m-%d %H:%M")
        return t if a.get("ostatnio") != a["data"] and t >= teraz - timedelta(minutes=10) else None
    for d in range(-1, 8):
        dz = teraz.date() + timedelta(days=d)
        t = datetime.combine(dz, datetime.min.time()).replace(hour=h, minute=m)
        if dz.weekday() in a["dni"] and a.get("ostatnio") != dz.isoformat() and t >= teraz - timedelta(minutes=10):
            return t
    return None


def opis_alarmu(a):
    t = nastepny_alarm(a)
    if a.get("data"):
        kiedy = kiedy_tekst(f"{a['data']}T{a['godzina']}")
    elif sorted(a["dni"]) == list(range(7)):
        kiedy = f"codziennie {a['godzina']}"
    elif sorted(a["dni"]) == list(range(5)):
        kiedy = f"w dni robocze {a['godzina']}"
    elif sorted(a["dni"]) == [5, 6]:
        kiedy = f"w weekendy {a['godzina']}"
    else:
        kiedy = ", ".join(DNI_NAZWY[d][:3] for d in sorted(a["dni"])) + f" {a['godzina']}"
    return kiedy + ("" if a.get("aktywny") else " (wyłączony)") + (f" · {a['opis']}" if a.get("opis") else "") \
        + (f" · najbliższy: {kiedy_tekst(t.strftime('%Y-%m-%dT%H:%M'))}" if t and not a.get("data") else "")


def komenda_budzik(tekst):
    """„budzik jutro 6:15”, „obudź mnie o 7”, „budzik w dni robocze 6:30”, „budziki”, „usuń budzik 2” -> odpowiedź albo None"""
    t = " ".join(re.sub(r"[!?]", " ", tekst).split())
    tl = t.lower()
    if tl.strip(" .") in ("budziki", "alarmy", "/budziki", "⏰ budziki", "jakie mam budziki", "pokaż budziki"):
        lista = sorted(portal("/api/alarmy")["alarmy"], key=lambda a: nastepny_alarm(a) or datetime.max)
        if not lista:
            return "⏰ Nie masz budzików. Ustawisz: „budzik jutro 6:15” albo „budzik w dni robocze 6:30”."
        return "⏰ Budziki:\n" + "\n".join(f"{i}. {opis_alarmu(a)}" for i, a in enumerate(lista, 1)) + "\nUsuniesz: „usuń budzik 1”."
    if m := re.fullmatch(r"(?:usuń|usun|skasuj|wyłącz|wylacz|anuluj)\s+(?:budzik|alarm)\s*(\d+|wszystkie)?\s*\.?", tl):
        lista = sorted(portal("/api/alarmy")["alarmy"], key=lambda a: nastepny_alarm(a) or datetime.max)
        cel = lista if m.group(1) == "wszystkie" else [lista[int(m.group(1)) - 1]] if m.group(1) and 0 < int(m.group(1)) <= len(lista) \
            else lista[:1] if len(lista) == 1 else None
        if not cel:
            return "Który budzik? Napisz „budziki”, a potem np. „usuń budzik 2”."
        for a in cel:
            portal(f"/api/alarmy/{a['id']}", {"usun": True})
        return "🗑 Usunięte: " + "; ".join(opis_alarmu(a) for a in cel)
    m = re.fullmatch(r"(?:⏰\s*)?(?:ustaw\s+)?(?:budzik|alarm|obudź mnie|obudz mnie|zbudź mnie|zbudz mnie)\s+(?:na\s+)?(.+)", t, re.I)
    if not m:
        return None
    r = " " + m.group(1) + " "
    dni = None
    for wzor, d in ((r"\s(codziennie|co\s+dzień|co\s+dzien|każdego\s+dnia)\s", list(range(7))),
                    (r"\s(w\s+dni\s+robocze|w\s+tygodniu|pon(?:iedziałek)?\s*-\s*pt|od\s+poniedziałku\s+do\s+piątku|w\s+dni\s+szkolne)\s", list(range(5))),
                    (r"\s(w\s+weekendy?|w\s+soboty?\s+i\s+niedziel[eęa])\s", [5, 6])):
        if re.search(wzor, r, re.I):
            dni, r = d, re.sub(wzor, " ", r, count=1, flags=re.I)
    opis, termin, powt = parsuj_zadanie(r)
    g = re.search(r"\b(\d{1,2})[:.](\d{2})\b|\bo\s+(\d{1,2})\b", r)
    if not termin and not g:
        return "O której? Np. „budzik jutro 6:15” albo „budzik w dni robocze 6:30”."
    if dni or powt == "dzien":
        godz = termin[11:16] if termin else f"{int(g.group(1) or g.group(3)):02d}:{int(g.group(2) or 0):02d}"
        a = portal("/api/alarmy", {"godzina": godz, "dni": dni or list(range(7)), "opis": opis if len(opis) > 2 else ""})
    else:
        a = portal("/api/alarmy", {"godzina": termin[11:16], "data": termin[:10], "opis": opis if len(opis) > 2 else ""})
    return f"⏰ Budzik ustawiony: {opis_alarmu(a)}. Zadzwonię i przeczytam poranny przegląd."


# ---------------------------------------------------------------- Mobidziennik (mobi.py): tylko odczyt, co 10 min 6–22
def mobi_dzis():
    if mobi.skonfigurowany() and time.time() - mobi.OSTATNIO["t"] > 300:
        try:
            mobi.sprawdz(powiadom, mobi_nowy_sprawdzian)
        except Exception as ex:
            print(f"mobi: {type(ex).__name__}: {ex}", flush=True)
    return mobi.dzis()


def mobi_nowy_sprawdzian(x):
    """nowa zapowiedź w dzienniku: jeśli w Nauce już jest (ten dzień i przedmiot), nic; inaczej Claude przygotowuje
    stronę i sesje nauki albo prosi o materiały (w osobnym wątku, do 30 min)"""
    norm = lambda t: re.sub(r"[^a-ząćęłńóśźż]", "", (t or "").lower())[:6]
    if any(y.get("data") == x["data"] and norm(y.get("przedmiot")) == norm(x["przedmiot"]) for y in sprawdziany()):
        return

    def praca():
        odp = claude_jednorazowo(
            f"[Mobidziennik: nowa zapowiedź. {x['rodzaj']} z przedmiotu „{x['przedmiot']}”, {x['data']} o {x['godzina']}, "
            f"grupa {x['grupa']}, nauczyciel {x['nauczyciel']}. Tematyka (wpis nauczyciela): „{x['tematyka']}”.\n"
            "Oceń, czy ten opis wystarcza, żeby przygotować materiały (konkretny dział, temat, zakres albo strony). "
            "JEŚLI TAK: zrób stronę w Nauce dokładnie według instrukcji (wpis w sprawdziany.json, typ i data jak wyżej, "
            "kontrola sprawdz_strone.js), potem dodaj przez API todo 2–3 sesje nauki przed terminem (np. o 18:00 w dni "
            "przed sprawdzianem, ostatnia dzień przed; każda z krótkim opisem, co powtórzyć) i napisz Antkowi KRÓTKO: "
            "„📚 Dodano: …” (temat, link do strony) i listę dodanych sesji (dzień, godzina, co). "
            "JEŚLI NIE: niczego nie twórz, napisz krótko, czego brakuje i o co prosisz (np. zdjęcia stron z podręcznika "
            "albo notatki, do wysłania w Telegramie). Nie pisz do nikogo poza Antkiem.]", limit=1800)
        powiadom(odp or f"📚 Nowa zapowiedź: {x['rodzaj']} z {x['przedmiot']} {x['data']} ({x['tematyka'][:100]}). "
                        "Nie udało się przygotować materiałów automatycznie: wyślij mi materiały, to zrobię stronę w Nauce.")
    threading.Thread(target=praca, daemon=True).start()


def petla_mobi():
    time.sleep(30)
    while True:
        try:
            na_zadanie = (mobi.KAT / "odswiez").exists()       # przycisk „Sprawdź teraz” na stronie
            if na_zadanie:
                (mobi.KAT / "odswiez").unlink(missing_ok=True)
            if mobi.skonfigurowany() and (na_zadanie or 6 <= datetime.now().hour < 22 and time.time() - mobi.OSTATNIO["t"] >= 590):
                mobi.sprawdz(powiadom, mobi_nowy_sprawdzian)
        except Exception as ex:
            print(f"mobi: {type(ex).__name__}: {ex}", flush=True)
        time.sleep(5)


def komenda_mobi(tekst):
    """„plan”, „plan jutro”, „lekcje”, „lekcje w poniedziałek” -> plan dnia z Mobidziennika"""
    t = tekst.lower().strip(" ?.!")
    m = re.fullmatch(r"(?:📅\s*)?/?(?:plan|lekcje|plan lekcji)(?:\s+(?:na\s+)?(dziś|dzis|jutro|pojutrze|w\s+\S+|\S+))?", t)
    if not m:
        return None
    if not mobi.skonfigurowany():
        return "Mobidziennik nie jest jeszcze podłączony."
    kiedy = (m.group(1) or "dziś").replace("w ", "").strip()
    d = date.today() + timedelta(days={"dziś": 0, "dzis": 0, "jutro": 1, "pojutrze": 2}.get(kiedy, 0))
    if kiedy in DNI_TYG:
        d = date.today() + timedelta(days=(DNI_TYG[kiedy] - date.today().weekday()) % 7)
    if time.time() - mobi.OSTATNIO["t"] > 300:
        try:
            mobi.sprawdz(powiadom, mobi_nowy_sprawdzian)
        except Exception as ex:
            return f"⚠️ Mobidziennik: {ex}"
    return f"📅 {DNI_NAZWY[d.weekday()].capitalize()} {d.strftime('%d.%m')}: " + (mobi.dzis(d) or "brak danych")


def poczta_podsumowanie():
    return poczta.podsumowanie()


def petla_poczty():
    time.sleep(60)
    while True:
        try:
            if poczta.konta():
                poczta.sprawdz(powiadom, claude_bez_narzedzi, cisza_nocna(stan()))
        except Exception as ex:
            print(f"poczta: {type(ex).__name__}: {ex}", flush=True)
        time.sleep(poczta.CO)


def poranne_dane():
    """dane do porannego przeglądu (każda część osobno: brak jednej nie psuje reszty)"""
    czesci = []
    teraz = datetime.now()
    czesci.append(f"Teraz: {DNI_NAZWY[teraz.weekday()]}, {teraz.strftime('%d.%m.%Y %H:%M')}.")
    try:
        z = portal("/api/zdrowie")
        p = z.get("pomiary", {})
        czesci.append(f"Serwer: stan {z['stan']}, {p.get('temp', '?')} °C, CPU {round(p.get('cpu') or 0)}%, RAM {round(p.get('ram') or 0)}%."
                      + (" Problemy: " + "; ".join(i["tytul"] for i in z["aktywne"]) if z.get("aktywne") else " Bez problemów."))
    except (OSError, ValueError, KeyError):
        czesci.append("Serwer: nie udało się sprawdzić stanu.")
    for nazwa, f in (("Poczta", "poczta_podsumowanie"), ("Lekcje", "mobi_dzis")):
        fn = globals().get(f)
        if fn:
            try:
                t = fn()
                if t:
                    czesci.append(f"{nazwa}: {t}")
            except Exception as ex:
                czesci.append(f"{nazwa}: błąd odczytu ({type(ex).__name__}).")
    try:
        dzis = date.today().isoformat()
        zad = [z for z in zadania_do_zrobienia() if not z.get("termin") or z["termin"][:10] <= dzis]
        if zad:
            czesci.append("Zadania na dziś i zaległe: " + "; ".join(f"{z['tekst']}" + (f" ({z['termin'][11:16]})" if z.get("termin") and z["termin"][:10] == dzis else
                                                                                      " (zaległe)" if z.get("termin") else "") for z in zad[:10]))
        else:
            czesci.append("Zadania: nic na dziś.")
    except (OSError, ValueError):
        pass
    spr = [x for x in sprawdziany() if x.get("data") and 0 <= (date.fromisoformat(x["data"]) - date.today()).days <= 2]
    if spr:
        czesci.append("Sprawdziany i kartkówki: " + "; ".join(
            f"{x['przedmiot']} ({x['typ']}) {['dziś', 'jutro', 'pojutrze'][(date.fromisoformat(x['data']) - date.today()).days]}" for x in spr))
    return "\n".join(czesci)


def przygotuj_budzik(a, na):
    dane = poranne_dane()
    tekst = claude_jednorazowo(
        f"[Budzik o {a['godzina']}: za chwilę Pi dzwoni do Antka, żeby go obudzić. Ułóż DOKŁADNIE to, co powiesz (czytane "
        "głosem przez telefon): krótkie „dzień dobry”, dzień tygodnia i godzina, potem po kolei tylko to, co ważne: "
        "lekcje i zmiany planu, sprawdziany i kartkówki, ważne maile, zadania na dziś, a stan serwera jednym zdaniem "
        "(tylko gdy coś jest nie tak, powiedz co). 30–60 sekund mówienia, naturalnie i ciepło, bez list, emotek, "
        "Markdown i adresów. Bez pytań i formułek na końcu. Nic poza samą wypowiedzią.]\n\nDane:\n" + dane, limit=150)
    if not tekst:
        tekst = "Dzień dobry! Pora wstawać. " + dane.replace("\n", " ")
    BUDZIK_TEKST[a["id"]] = {"na": na, "tekst": tekst}
    print(f"budzik {a['id']} przygotowany: {tekst[:80]}", flush=True)


def budziki():
    teraz = datetime.now()
    while BUDZIK_PONOW and BUDZIK_PONOW[0][0] <= time.time():
        _, zl = BUDZIK_PONOW.pop(0)
        zadzwon(zl["tekst"], "budzik", budzik=zl["budzik"], proba=zl["proba"])
    for a in portal("/api/alarmy")["alarmy"]:
        t = nastepny_alarm(a, teraz)
        if not t:
            continue
        na = t.strftime("%Y-%m-%dT%H:%M")
        if t - teraz <= timedelta(minutes=3) and BUDZIK_TEKST.get(a["id"], {}).get("na") != na:
            BUDZIK_TEKST[a["id"]] = {"na": na, "tekst": None}
            threading.Thread(target=przygotuj_budzik, args=(a, na), daemon=True).start()
        if teraz >= t:
            gotowy = BUDZIK_TEKST.get(a["id"], {})
            if gotowy.get("tekst") is None and gotowy.get("na") == na and teraz - t < timedelta(seconds=45):
                continue                                    # Claude jeszcze układa: poczekaj chwilę (do 45 s)
            tekst = gotowy.get("tekst") if gotowy.get("na") == na and gotowy.get("tekst") else "Dzień dobry! Pora wstawać. " + poranne_dane().replace("\n", " ")
            portal(f"/api/alarmy/{a['id']}", {"ostatnio": t.date().isoformat(), **({"aktywny": False} if a.get("data") else {})})
            BUDZIK_TEKST.pop(a["id"], None)
            pamiec.zapisz("bot", "telefon", f"Budzik {a['godzina']}: dzwonię i mówię: {tekst}")
            zadzwon(tekst, "budzik", budzik=a["id"], proba=1)


def petla_budzikow():
    while True:
        try:
            budziki()
        except Exception as ex:
            print(f"budziki: {type(ex).__name__}: {ex}", flush=True)
        time.sleep(15)


# ---------------------------------------------------------------- glos (wiadomosci glosowe) i telefon
import sys
sys.path.insert(0, "/home/tonyg/glos")
TELEFON = KATALOG / "telefon"           # kolejka polaczen dla uslugi serwerek-telefon (telefon.py)


# ---------------------------------------------------------------- komunikacja miejska (ZTM Poznań)
# Odjazdy i trasy liczy portal (ztm.py, /api/ztm/...); lokalizacja: przycisk 📍 w Telegramie, lokalizacja „na żywo”,
# OwnTracks albo skrót iOS (POST /api/lokalizacja). Te same komendy działają w czacie Linphone.
ZTM_PRZYCISKI = {"inline_keyboard": [[{"text": "🏠 Do domu", "callback_data": "ztm:dom"},
                                      {"text": "🚏 Odjazdy obok", "callback_data": "ztm:odj"}]]}


def ztm_api(sciezka, dane=None, **arg):
    try:
        return portal(sciezka + ("?" + urllib.parse.urlencode(arg) if arg else ""), dane)
    except urllib.error.HTTPError as ex:
        try:
            return json.loads(ex.read())
        except ValueError:
            return {"tekst": f"Błąd portalu ({ex.code})."}
    except OSError as ex:
        return {"tekst": f"Portal nie odpowiada ({ex})."}


def zapisz_lokalizacje(loc, wyslano=None):
    """live_period: lokalizacja „na żywo” (Telegram wysyła zmiany tylko przy ruchu, więc do jej końca jest aktualna)"""
    na_zywo = (wyslano or time.time()) + loc["live_period"] if loc.get("live_period") else None
    ztm_api("/api/lokalizacja", {"lat": loc["latitude"], "lon": loc["longitude"], "acc": loc.get("horizontal_accuracy"),
                                 "zrodlo": "telegram na żywo" if na_zywo else "telegram", "na_zywo_do": na_zywo})


TU_SLOWA = r"(?:to\s+miejsce|tu|tutaj|tu\s+gdzie\s+(?:teraz\s+)?jestem|tam\s+gdzie\s+(?:teraz\s+)?jestem|gdzie\s+(?:teraz\s+)?jestem|moj[aą]\s+lokalizacj[eęa]|teraz)"


ZWYKLE_MIEJSCA = {"dom", "szkoła", "szkola", "praca", "uczelnia", "siłownia", "silownia", "babcia", "dziadkowie", "internat",
                  "trening", "basen", "kościół", "kosciol", "dziewczyna", "przystanek"}


def komenda_miejsca(tekst):
    """zapis / usunięcie miejsca słowami (czat, Linphone, telefon) -> odpowiedź albo None:
    „ustaw tu, gdzie teraz jestem, jako dom”, „zapisz to miejsce jako szkoła”, „zapisz siłownia” (tu),
    „zapisz dom ul. Fredry 5” (adres), „usuń miejsce siłownia”"""
    t = re.sub(r"[,.!?]", " ", tekst)
    t = " ".join(t.split())
    if m := re.fullmatch(r"(?:usuń|usun|skasuj)\s+miejsce\s+(.+)", t, re.I):
        w = ztm_api("/api/miejsca", {"nazwa": m.group(1), "usun": True})
        return f"🗑 Usunięte miejsce: {m.group(1)}." if "miejsca" in w else "⚠️ Nie udało się usunąć."
    m = re.fullmatch(r"(?:ustaw|zapisz|zapamiętaj|zapamietaj|dodaj|oznacz)\s+(?:miejsce\s+)?(.+)", t, re.I)
    if not m:
        return None
    r = m.group(1)
    if j := re.fullmatch(rf"(?:(?:{TU_SLOWA})\s+)*jako\s+(.+?)(?:\s+adres\s+(.+))?", r, re.I):       # „… jako dom”
        nazwa, adres = j.group(1), j.group(2)
    elif j := re.fullmatch(rf"(?:{TU_SLOWA})\s+(?:jako\s+)?(.+)", r, re.I):                            # „tutaj szkołę”
        nazwa, adres = j.group(1), None
    elif re.match(r"zapisz|zapamiętaj|zapamietaj", t, re.I) and (j := re.fullmatch(rf"(\S+)(?:\s+(.+))?", r, re.I)):
        nazwa, adres = j.group(1), j.group(2)                                                    # „zapisz dom [adres|tu]”
        if adres and re.fullmatch(rf"(?:{TU_SLOWA}\s*)+", adres, re.I):
            adres = None
        elif not adres and nazwa.lower() not in ZWYKLE_MIEJSCA:
            return None                                     # „zapisz zakupy”: to raczej nie miejsce
        elif adres and not re.search(r"\d|\bul\b|ulica|\bos\b|osiedle|plac|aleja|rondo", adres, re.I):
            return None                                     # „zapisz mi to…”: nie miejsce, niech odpowie Claude
    else:
        return None
    nazwa = re.sub(rf"\s+(?:{TU_SLOWA})$", "", nazwa.strip(), flags=re.I)
    if not nazwa or len(nazwa) > 40 or nazwa.lower() in ("przypomnienie", "zadanie", "todo", "mi", "to", "sobie", "go", "je"):
        return None
    if " " not in nazwa and nazwa.lower().endswith("ę"):    # „ustaw tutaj szkołę” -> szkoła
        nazwa = nazwa[:-1] + "a"
    dane = {"nazwa": nazwa, **({"adres": adres} if adres else {"tu": True})}
    w = ztm_api("/api/miejsca", dane)
    if w.get("blad"):
        return f"⚠️ {w['blad'].capitalize()}."
    if adres:
        mj = next((v for k, v in w.get("miejsca", {}).items() if v.get("nazwa") == nazwa), {})
        return f"📍 Zapisane: {nazwa} ({mj.get('opis') or adres})."
    l = ztm_api("/api/lokalizacja").get("lokalizacja") or {}
    return f"📍 Zapisane: {nazwa}, tu, gdzie jesteś (lokalizacja z {l.get('czas', '?')[11:16]})."


def komenda_ztm(tekst):
    """odjazdy / trasa / miejsca (Telegram i Linphone) -> tekst odpowiedzi albo None (to nie ta komenda)"""
    t = " ".join(tekst.strip().split())
    if m := re.fullmatch(r"(?:🚏\s*)?/?(?:odjazdy|odjazd)(?:\s+(?:z|ze|spod)?\s*(.+))?", t, re.I):
        return ztm_api("/api/ztm/odjazdy", skad=(m.group(1) or "tu").strip(" ?.!"), ile=10).get("tekst") or "Brak danych."
    if m := re.fullmatch(r"(?:🏠\s*)?(?:/?trasa|jak dojadę|jak dojade|dojazd)?\s*(?:z\s+(.+?)\s+)?do\s+(domu|dom)\s*[?.!]*", t, re.I) \
            or re.fullmatch(r"(?:🗺\s*)?(?:/?trasa|jak dojadę|jak dojade|dojazd)\s+(?:z\s+(.+?)\s+)?do\s+(.+?)\s*[?.!]*", t, re.I):
        dokad = "dom" if m.group(2).lower() in ("domu", "dom") else m.group(2)
        return ztm_api("/api/ztm/trasa", skad=m.group(1) or "tu", dokad=dokad).get("tekst") or "Brak danych."
    if (odp := komenda_miejsca(t)) is not None:
        return odp
    if t.lower() in ("miejsca", "/miejsca"):
        mj = ztm_api("/api/lokalizacja").get("miejsca", {})
        return ("📍 Miejsca: " + ", ".join(v["nazwa"] for v in mj.values()) + "\nDodasz: „zapisz dom” (tu, gdzie jesteś) albo „zapisz szkoła ul. … 5”.") \
            if mj else "Nie ma zapisanych miejsc. Dodasz: „zapisz dom” (tu, gdzie jesteś) albo „zapisz dom ul. … 5”."
    return None


def do_linphone(tekst, **dodatki):
    """wiadomość na czat Linphone: plik w kolejce, wysyła ją usługa serwerek-telefon (gdy konto jest zarejestrowane)"""
    kat = TELEFON / "czat"
    kat.mkdir(parents=True, exist_ok=True)
    p = kat / f"{time.time():.3f}.json"
    tmp = p.with_suffix(".tmp")                 # najpierw cały plik, potem zmiana nazwy: telefon.py nie czyta połówki
    tmp.write_text(json.dumps({"tekst": tekst, **dodatki}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def glos():
    try:
        import glos as g
    except ImportError:
        return None
    return g if g.gotowe() else None


def tg_plik(metoda, pole, sciezka, **dane):
    """wysylka pliku (multipart/form-data), np. sendVoice"""
    import uuid
    granica = uuid.uuid4().hex
    czesci = []
    for k, v in dane.items():
        czesci.append(f"--{granica}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v if isinstance(v, str) else json.dumps(v)}\r\n".encode())
    czesci.append(f"--{granica}\r\nContent-Disposition: form-data; name=\"{pole}\"; filename=\"{Path(sciezka).name}\"\r\n"
                  f"Content-Type: application/octet-stream\r\n\r\n".encode() + Path(sciezka).read_bytes() + b"\r\n")
    czesci.append(f"--{granica}--\r\n".encode())
    req = urllib.request.Request(API + metoda, data=b"".join(czesci), headers={"Content-Type": f"multipart/form-data; boundary={granica}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read()).get("result")
    except (urllib.error.URLError, OSError, ValueError) as ex:
        print(f"Telegram {metoda}: {ex}", flush=True)
        return None


def wyslij_glos(tekst):
    """odpowiedz Claude jako wiadomosc glosowa (Piper na Pi) z tekstem w podpisie; False = nie wyszlo (wtedy tekstem)"""
    g = glos()
    if not g or not tekst.strip():
        return False
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        try:
            tg("sendChatAction", timeout=10, chat_id=stan()["wlasciciel"], action="record_voice")
            wav, ogg = Path(tmp) / "odp.wav", Path(tmp) / "odp.ogg"
            g.powiedz(tekst[:4000], wav)
            g.do_ogg(wav, ogg)
            dane = {"chat_id": str(stan()["wlasciciel"])}
            if len(tekst) <= 1000:
                dane["caption"] = tekst
            w = tg_plik("sendVoice", "voice", ogg, **dane)
        except (OSError, subprocess.SubprocessError) as ex:
            print(f"glos: {ex}", flush=True)
            return False
    if not w:
        return False
    pamiec.zapisz("claude", "telegram", "[głosówka] " + tekst, w.get("message_id"))
    if len(tekst) > 1000:
        wyslij(tekst, kto="claude")
    return True


def glosowka(m):
    """wiadomosc glosowa od wlasciciela: rozpoznanie na Pi (whisper) -> Claude -> odpowiedz tekstem i glosem"""
    ustaw_kanal("telegram")
    g = glos()
    if not g:
        wyslij("🎙 Rozpoznawanie mowy jeszcze się instaluje na Pi. Napisz tekstem albo spróbuj za chwilę.")
        return
    v = m.get("voice") or m.get("audio")
    plik = pobierz_plik(v["file_id"], "glos.ogg")
    if not plik:
        wyslij("⚠️ Nie udało się pobrać wiadomości głosowej.")
        return
    tg("sendChatAction", timeout=10, chat_id=stan()["wlasciciel"], action="typing")
    try:
        tekst = g.rozpoznaj(plik)
    except (OSError, subprocess.SubprocessError) as ex:
        wyslij(f"⚠️ Nie udało się rozpoznać mowy: {ex}")
        return
    if not tekst:
        wyslij("🎙 Nic nie usłyszałem. Spróbuj jeszcze raz.")
        return
    pamiec.zapisz("antek", "glosowka", tekst, m.get("message_id"))
    KOLEJKA.append({"tekst": tekst, "kanal": "glosowka_zapisana", "glosem": None})
    KOLEJKA_BUDZIK.set()


def zadzwon(tekst, powod="prośba", **dodatki):
    """zlecenie polaczenia do wlasciciela dla uslugi serwerek-telefon (Linphone); wynik wraca przez petla_telefonu"""
    (TELEFON / "kolejka").mkdir(parents=True, exist_ok=True)
    nazwa = f"{time.time():.3f}.json"
    (TELEFON / "kolejka" / (nazwa + ".tmp")).write_text(json.dumps({"tekst": tekst, "powod": powod, **dodatki}, ensure_ascii=False), encoding="utf-8")
    os.replace(TELEFON / "kolejka" / (nazwa + ".tmp"), TELEFON / "kolejka" / nazwa)


def petla_telefonu():
    """wyniki polaczen i rozmow z uslugi telefonu -> wiadomosci w Telegramie"""
    while True:
        time.sleep(3)
        try:
            for p in sorted((TELEFON / "wyniki").glob("*.json")):
                w = json.loads(p.read_text(encoding="utf-8"))
                p.unlink()
                if w.get("stan") == "brak_konfiguracji":
                    powiadom(f"📞 Chciałem zadzwonić ({w.get('powod')}), ale telefon nie jest jeszcze skonfigurowany (konto Linphone).\n{w.get('tekst', '')}")
                elif w.get("stan") == "nieodebrane" and w.get("budzik") and int(w.get("proba", 1)) < BUDZIK_PROB:
                    BUDZIK_PONOW.append((time.time() + BUDZIK_CO, {"tekst": w.get("tekst", ""), "budzik": w["budzik"],
                                                                 "proba": int(w.get("proba", 1)) + 1}))
                    print(f"budzik nieodebrany (próba {w.get('proba')}), ponowię za {BUDZIK_CO // 60} min", flush=True)
                elif w.get("stan") == "nieodebrane":
                    powiadom(f"📞 Dzwoniłem, ale nie odebrałeś ({w.get('powod')}):\n{w.get('tekst', '')}")
                elif w.get("stan") == "rozmowa":
                    powiadom(f"📞 Rozmowa ({w.get('kierunek')}, {w.get('czas')}):\n{w.get('zapis', '')}"[:3900])
                elif w.get("stan") == "nieznany_wlasciciel":
                    powiadom(f"📞 Ktoś dzwonił do Pi z adresu {w.get('od')}. Jeśli to Ty, napisz „to mój adres Linphone”, "
                           "a Claude w sesji w chmurze dopisze go jako Twój (wtedy Pi będzie odbierać i dzwonić).")
                elif w.get("stan") == "obcy_czat":
                    powiadom(f"💬 Ktoś obcy napisał do Pi na Linphone ({w.get('od')}): {w.get('tekst')}\nNie odpowiedziałem.")
                elif w.get("stan") == "obcy":
                    powiadom(f"📞 Ktoś obcy próbował zadzwonić do Pi: {w.get('od')}. Odrzuciłem.")
                elif w.get("stan") == "blad":
                    powiadom(f"📞 Nie udało się zadzwonić: {w.get('opis')}")
        except Exception as ex:
            print(f"telefon: {type(ex).__name__}: {ex}", flush=True)


# ---------------------------------------------------------------- Minecraft: automatyczne wyłączanie bez graczy
def petla_minecrafta():
    """co minutę: gdy serwer działa i przez mc_auto_min minut nikt nie gra, zapisz świat i wyłącz (oszczędza RAM i CPU).
    Liczy się od włączenia serwera albo od ostatniej chwili, gdy ktoś grał; nieznana liczba graczy nie przybliża wyłączenia."""
    ostatnio_gracze = time.time()          # po starcie bota nie wiadomo, kto grał przed chwilą: licz od teraz
    while True:
        time.sleep(60)
        try:
            limit = stan()["ustawienia"].get("mc_auto_min", USTAWIENIA["mc_auto_min"])
            m = portal("/api/minecraft")
            if not limit or not m.get("dziala") or m.get("trwa") or m.get("gracze") is None:
                continue
            if m["gracze"] > 0:
                ostatnio_gracze = time.time()
                continue
            start = time.mktime(time.strptime(m["od"], "%Y-%m-%dT%H:%M:%S")) if m.get("od") else time.time()
            if time.time() - max(start, ostatnio_gracze) >= limit * 60:
                wynik = wykonaj("mc_wylacz")
                powiadom(f"🎮 Wyłączyłem Minecrafta: od {limit} min nikt nie grał (świat zapisany). Włączysz go przyciskiem 🎮 Minecraft.\n{wynik}")
        except Exception as ex:
            print(f"minecraft: {type(ex).__name__}: {ex}", flush=True)


MC_BOT = {"t": 0}       # bot sam włączył/wyłączył serwer i już o tym napisał: nie dubluj powiadomienia


def petla_mc_stanu():
    """co 15 s: powiadomienie o każdej zmianie stanu serwera Minecraft (włączony, wyłączony, restart, awaria)
    i o tym, że ktoś zaczął grać albo serwer opustoszał"""
    poprz = None
    while True:
        time.sleep(15)
        try:
            m = portal("/api/minecraft")
            if m.get("trwa"):
                continue
            teraz = {"dziala": m.get("dziala"), "od": m.get("od"), "stan": m.get("stan"),
                     "gracze": m.get("gracze") if m.get("dziala") else 0}
            if poprz is not None and stan()["wlasciciel"]:
                cichy = time.time() - MC_BOT["t"] < 120
                if teraz["stan"] == "failed" and poprz["stan"] != "failed":
                    powiadom("🔴 🎮 Serwer Minecraft się wysypał. Włączysz go ponownie przyciskiem 🎮 Minecraft.")
                elif teraz["dziala"] and not poprz["dziala"] and not cichy:
                    powiadom(f"🎮 Minecraft <b>włączony</b> ({(teraz['od'] or '')[11:16]}), można grać.", html_=True)
                elif not teraz["dziala"] and poprz["dziala"] and teraz["stan"] != "failed" and not cichy:
                    powiadom("⏹ Minecraft <b>wyłączony</b> (świat zapisany).", html_=True)
                elif teraz["dziala"] and poprz["dziala"] and teraz["od"] != poprz["od"] and not cichy:
                    powiadom(f"🔄 Minecraft <b>zrestartowany</b> ({(teraz['od'] or '')[11:16]}).", html_=True)
                if teraz["dziala"] and poprz["dziala"] and teraz["gracze"] is not None and poprz["gracze"] is not None:
                    if teraz["gracze"] > 0 and poprz["gracze"] == 0:
                        powiadom(f"👤 Ktoś gra na serwerze Minecraft (graczy: {teraz['gracze']}).")
                    elif teraz["gracze"] == 0 and poprz["gracze"] > 0:
                        auto = stan()["ustawienia"].get("mc_auto_min", USTAWIENIA["mc_auto_min"])
                        powiadom("👤 Serwer Minecraft opustoszał." + (f" Wyłączy się sam za {auto} min, jeśli nikt nie wejdzie." if auto else ""))
            if teraz["gracze"] is None and poprz:
                teraz["gracze"] = poprz["gracze"]
            poprz = teraz
        except Exception as ex:
            print(f"minecraft stan: {type(ex).__name__}: {ex}", flush=True)


POMOC_WSPOLNE = """📊 stan – temperatura, procesor, RAM, NAS, kopia, maksima dnia i tygodnia
📚 sprawdziany – najbliższe 2 tygodnie (też: jutro)
📝 zadania – lista do zrobienia
📝 todo <kiedy> <co> – dodaj zadanie, np. todo jutro 17:00 trening, todo za 20 min pranie,
    todo w piątek 8:30 dentysta, todo codziennie 21:00 leki, todo jutro 7:00 ważne pobudka
    („ważne” / „zadzwoń” = bardzo ważne: Pi zadzwoni; zrobione po 24 h idą do archiwum na stronie)
🚏 odjazdy [przystanek] – najbliższe odjazdy ZTM (bez nazwy: obok Ciebie), np. odjazdy Junikowo
🏠 do domu / trasa do <miejsce|przystanek|adres> – jak dojechać stąd (też: trasa z Junikowo do Rondo Kaponiera)
📍 ustaw tu jako dom / zapisz szkoła [adres] – zapamiętaj miejsce (bez adresu: tu, gdzie jesteś);
    miejsca – lista; usuń miejsce <nazwa>
📅 plan / plan jutro / plan w poniedziałek – lekcje z Mobidziennika (zastępstwa, odwołane, sprawdziany)
⏰ budzik jutro 6:15 / budzik w dni robocze 6:30 / budziki / usuń budzik 2 – Pi dzwoni i czyta poranny przegląd
📧 maile – ważne i nieprzeczytane; przy ważnym: przeczytaj mail / przeczytany / później
🎮 minecraft – stan serwera (włącz / wyłącz)
💾 kopia – kopia systemu na NAS teraz
✅ przejrzane – zgaś żółtą diodę
🧭 ścieżka [wczoraj | RRRR-MM-DD] – kto wchodził na Pi z sieci domowej
🔐 zaufane – Twoje urządzenia bez powiadomień
📞 zadzwoń – Pi zadzwoni do Ciebie przez Linphone
🆕 nowa rozmowa – zacznij rozmowę z Claude od nowa
❓ pomoc / help – ta lista

Wszystko inne trafia do Claude na Pi (pamięta wspólną rozmowę z Telegrama, Linphone i telefonu).
„przeczytaj / powiedz / nagraj” → odpowiedź głosówką; „wypisz / napisz” → tekstem; głosówki są rozpoznawane na Pi."""

POMOC_TELEGRAM = ("❓ <b>Pomoc: co umiem</b>\nPrzyciski na dole robią to samo co komendy:\n\n" + html.escape(POMOC_WSPOLNE, quote=False)
                  + "\n\nZdjęcia i PDF-y (np. strony podręcznika) z podpisem → Claude zrobi z nich zagadnienie w Nauce."
                  + "\nTelefon: zadzwoń z Linphone na antekserwerrpi4b@sip.linphone.org.")


# ---------------------------------------------------------------- odbieranie wiadomosci
KOLEJKA = []
KOLEJKA_BUDZIK = threading.Event()


def petla_claude():
    while True:
        KOLEJKA_BUDZIK.wait()
        KOLEJKA_BUDZIK.clear()
        while KOLEJKA:
            z = KOLEJKA.pop(0)
            try:
                claude(z["tekst"], z.get("kanal", "telegram"), z.get("odpowiedz_na"), z.get("glosem"))
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


def do_claude(pliki, podpis, kanal="telegram", odpowiedz_na=None, glosem=False):
    tekst = podpis or "Przysłałem materiały."
    if pliki:
        tekst += "\n\n[Załączone pliki (otwórz narzędziem Read): " + ", ".join(str(p) for p in pliki) + "]"
    KOLEJKA.append({"tekst": tekst, "kanal": kanal, "odpowiedz_na": odpowiedz_na, "glosem": glosem or None})
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
        if dane.startswith("widze:"):
            with LOCK:
                s2 = stan()
                s2["wyslane"]["dzwon:" + dane[6:]] = "widze"
                zapisz(s2)
            wyslij("👀 OK, nie będę dzwonić w tej sprawie.")
            return
        if dane.startswith("ztm:"):
            threading.Thread(target=lambda: wyslij(komenda_ztm("do domu" if dane == "ztm:dom" else "odjazdy"),
                                                   przyciski=ZTM_PRZYCISKI), daemon=True).start()
            return
        if dane.startswith("todo_"):
            try:
                wyslij(callback_zadania(dane))
            except (OSError, ValueError, StopIteration, KeyError):
                wyslij("⚠️ Nie znalazłem tego zadania (może już usunięte).")
            return
        if dane.startswith("zaufaj:") or dane.startswith("nieufaj:"):
            wyslij(zaufaj(dane.split(":", 1)[1], dane.startswith("zaufaj:")))
            return
        if dane.startswith("tak:") and czy_akcja(dane[4:]):
            if dane[4:] in ("mc_wlacz", "mc_wylacz"):
                wyslij("🎮 " + ("Włączam serwer Minecraft… (ok. 30 s)" if dane[4:] == "mc_wlacz" else "Zapisuję świat i wyłączam…"))
            if dane[4:].startswith("sudo:"):          # może trwać długo: w osobnym wątku
                wyslij("⏳ Uruchamiam…")
                threading.Thread(target=lambda a=dane[4:]: wyslij(wykonaj(a)), daemon=True).start()
            else:
                wyslij(wykonaj(dane[4:]))
        elif dane == "nie":
            wyslij("Nic nie zrobiłem.")
        return
    if (u.get("edited_message") or {}).get("location"):          # lokalizacja „na żywo”: tylko zapis, bez odpowiedzi
        em = u["edited_message"]
        if em["chat"]["id"] == s["wlasciciel"]:
            zapisz_lokalizacje(em["location"], em.get("date"))
        return
    m = u.get("message") or {}
    chat, tekst = (m.get("chat") or {}).get("id"), (m.get("text") or "").strip()
    if chat and chat == s["wlasciciel"] and m.get("location"):
        zapisz_lokalizacje(m["location"], m.get("date"))
        threading.Thread(target=lambda: wyslij(komenda_ztm("odjazdy") + "\n\n📍 Zapamiętałem Twoją lokalizację.", przyciski=ZTM_PRZYCISKI),
                         daemon=True).start()
        return
    if chat and chat == s["wlasciciel"] and (m.get("voice") or m.get("audio")):
        threading.Thread(target=glosowka, args=(m,), daemon=True).start()
        return
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
    pamiec.zapisz("antek", "telegram", tekst, m.get("message_id"))
    ustaw_kanal("telegram")                 # pisze z Telegrama: powiadomienia też tutaj, aż znów napisze na Linphone
    odp_na = pamiec.po_tg_id(m["reply_to_message"]["message_id"]) if m.get("reply_to_message") else None
    if tekst in ("📞 Zadzwoń", "/zadzwon") or tekst.lower() in ("zadzwoń", "zadzwon", "zadzwoń do mnie", "zadzwon do mnie"):
        zadzwon("Cześć, tu serwerek. Dzwonię, bo prosiłeś. W czym mogę pomóc?", "na Twoją prośbę")
        wyslij("📞 Dzwonię przez Linphone…")
    elif tekst in ("🎮 Minecraft", "/minecraft") or tekst.lower() in ("minecraft", "mc"):
        m = portal("/api/minecraft")
        auto = s["ustawienia"].get("mc_auto_min", USTAWIENIA["mc_auto_min"])
        if m.get("trwa"):
            wyslij("🎮 Minecraft właśnie się " + ("włącza…" if m["trwa"] == "start" else "wyłącza…"))
        elif m.get("dziala"):
            g = m.get("gracze")
            wyslij(f"🎮 Minecraft <b>działa</b> od {(m.get('od') or '')[11:16]}, RAM {m.get('ram_mb', '?')} MB, gracze: {g if g is not None else '?'}"
                   + (f"\nWyłączy się sam po {auto} min bez graczy." if auto else ""), html_=True,
                   przyciski={"inline_keyboard": [[{"text": "⏹ Wyłącz", "callback_data": "tak:mc_wylacz"}, {"text": "🔄 Restart", "callback_data": "tak:restart_minecrafta"}],
                                                  [{"text": "✖ Nic", "callback_data": "nie"}]]})
        else:
            wyslij("🎮 Minecraft jest <b>wyłączony</b> (nie zajmuje RAM ani procesora).", html_=True,
                   przyciski={"inline_keyboard": [[{"text": "▶ Włącz (ok. 30 s)", "callback_data": "tak:mc_wlacz"}, {"text": "✖ Nic", "callback_data": "nie"}]]})
    elif tekst in ("📊 Stan", "/stan"):
        wyslij(tekst_stanu(), html_=True)
    elif tekst.split()[0].lower() in ("🧭", "ścieżka", "sciezka", "/sciezka"):
        slowa = tekst.split()
        while slowa and slowa[0].lower() in ("🧭", "ścieżka", "sciezka", "/sciezka"):
            slowa.pop(0)
        wyslij(tekst_sciezki(" ".join(slowa)), html_=True)
    elif tekst in ("📝 Zadania", "/zadania", "/todo") or tekst.lower() in ("todo", "zadania", "lista"):
        t, p = tekst_zadan()
        wyslij(t, html_=True, przyciski=p)
    elif (odp_m := komenda_mobi(tekst)) is not None:
        wyslij(odp_m)
    elif (odp_p := poczta.reakcja(tekst)) is not None:
        wyslij(odp_p)
    elif (odp_b := komenda_budzik(tekst)) is not None:
        wyslij(odp_b)
    elif (odp_ztm := komenda_ztm(tekst)) is not None:
        wyslij(odp_ztm, przyciski=ZTM_PRZYCISKI if "🚏" in odp_ztm[:3] or odp_ztm.startswith("Najbliżej") else None)
    elif tekst.split()[0].lower() in ("todo", "/todo", "przypomnij", "/przypomnij", "zadanie", "📝"):
        dodaj_zadanie(tekst.split(None, 1)[1] if len(tekst.split()) > 1 else "")
    elif tekst.lower() in ("zaufane", "/zaufane"):
        z = s.get("zaufane", {})
        if not z:
            wyslij("Nie ma zaufanych urządzeń. Dodasz je przyciskiem „✅ To moje urządzenie” przy powiadomieniu o wejściu.")
        else:
            wyslij("🔐 <b>Zaufane urządzenia</b> (wejścia tylko zapisywane, bez powiadomień):\n" + "\n".join(f"• {e(n)}: <code>{e(m)}</code>" for m, n in z.items()),
                   html_=True, przyciski={"inline_keyboard": [[{"text": f"🗑 Usuń {n}", "callback_data": f"nieufaj:{m}"}] for m, n in z.items()]})
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
    elif tekst.lower() in ("/start", "/pomoc", "/help", "pomoc", "help", "?", "❓ pomoc"):
        wyslij(POMOC_TELEGRAM, html_=True)
    else:
        do_claude([], tekst, odpowiedz_na=odp_na)


def main():
    if not TOKEN:
        raise SystemExit("Brak TELEGRAM_TOKEN")
    with LOCK:
        s = stan()
        zapisz(s)
    tg("setMyCommands", commands=[{"command": c, "description": d} for c, d in (
        ("pomoc", "Lista komend"), ("zadania", "Lista zadań (dodawanie: todo jutro 17:00 trening)"), ("minecraft", "Włącz / wyłącz serwer Minecraft"), ("zadzwon", "Pi zadzwoni do Ciebie (Linphone)"), ("stan", "Stan serwera"), ("sprawdziany", "Najbliższe sprawdziany"), ("sciezka", "Kto i gdzie wchodził dziś (albo: /sciezka wczoraj)"), ("zaufane", "Twoje urządzenia bez powiadomień"), ("kopia", "Kopia systemu teraz"),
        ("przejrzane", "Zgaś żółtą diodę"), ("restart", "Restart portalu lub Minecrafta"), ("nowa", "Nowa rozmowa z Claude"))])
    threading.Thread(target=petla_powiadomien, daemon=True).start()
    threading.Thread(target=petla_claude, daemon=True).start()
    threading.Thread(target=petla_portalu, daemon=True).start()
    threading.Thread(target=petla_dziennika, daemon=True).start()
    threading.Thread(target=petla_wizyt, daemon=True).start()
    threading.Thread(target=petla_przypomnien, daemon=True).start()
    threading.Thread(target=petla_budzikow, daemon=True).start()
    threading.Thread(target=petla_poczty, daemon=True).start()
    threading.Thread(target=petla_mobi, daemon=True).start()
    threading.Thread(target=rozgrzej, daemon=True).start()
    threading.Thread(target=petla_telefonu, daemon=True).start()
    threading.Thread(target=petla_minecrafta, daemon=True).start()
    threading.Thread(target=petla_mc_stanu, daemon=True).start()
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
    dane = {"timeout": 50, "allowed_updates": ["message", "edited_message", "callback_query"]}
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
