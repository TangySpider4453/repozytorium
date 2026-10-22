#!/usr/bin/env python3
"""
Bot Telegram serwerka (@SerwerekAntek_bot): powiadomienia, przyciski i rozmowa z Claude na Pi.

  - Powiadomienia: czerwone problemy z monitora zdrowia od razu (o kazdej porze) i ich koniec; zolte zbiorczo,
    najwyzej co 3 h i nie w ciszy nocnej; nauka: dzien przed sprawdzianem/kartkowka (18:00), 3 dni przed
    sprawdzianem (18:00) i rano w dniu (7:00).
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
ZOLTE_CO = 3 * 3600
USTAWIENIA = {"nauka_wieczor": "18:00", "nauka_rano": "07:00", "cisza_od": 22, "cisza_do": 7}

AKCJE = {   # nazwa: (opis dla przycisku, polecenie)
    "kopia": ("Zrobić kopię systemu na NAS teraz", ["sudo", "systemctl", "start", "--no-block", "kopia-pi"]),
    "restart_portalu": ("Zrestartować portal (strony, diodę)", ["sudo", "systemctl", "restart", "home-portal"]),
    "restart_minecrafta": ("Zrestartować serwer Minecraft (rozłączy graczy)", None),
    "przejrzane": ("Oznaczyć wszystkie problemy jako przejrzane", None),
}
KLAWIATURA = {"keyboard": [["📊 Stan", "📚 Sprawdziany"], ["💾 Kopia", "✅ Przejrzane", "🔄 Restart"], ["🆕 Nowa rozmowa"]],
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
        if tg("sendMessage", **dane) is None and html_:         # zly HTML: wyslij jako zwykly tekst
            dane.pop("parse_mode")
            tg("sendMessage", **dane)


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
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900, cwd="/home/tonyg", env=env)
        d = json.loads(r.stdout or "{}")
    except subprocess.TimeoutExpired:
        d = {"is_error": True, "result": "Przekroczony czas (15 min)."}
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
        if zolte and not cisza_nocna(s) and time.time() - w.get("zolte_ostatnio", 0) > ZOLTE_CO:
            wyslij("🟡 <b>Do sprawdzenia</b>\n" + "\n".join(f"• {e(i['tytul'])}: {e(i['opis'])}" for i in zolte)
                   + "\n\nPo przejrzeniu: ✅ Przejrzane", html_=True)
            for i in zolte:
                w["inc:" + i["id"]] = "warn"
            w["zolte_ostatnio"] = time.time()
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
    for k in [k for k in w if k.startswith("nauka:") and k.split(":")[2] < (dzis - timedelta(days=7)).isoformat()]:
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
        KOLEJKA.append(tekst)
        KOLEJKA_BUDZIK.set()
        if len(KOLEJKA) > 1:
            wyslij("⏳ Claude jeszcze pracuje nad poprzednią wiadomością, ta poczeka w kolejce.")


def main():
    if not TOKEN:
        raise SystemExit("Brak TELEGRAM_TOKEN")
    with LOCK:
        s = stan()
        zapisz(s)
    tg("setMyCommands", commands=[{"command": c, "description": d} for c, d in (
        ("stan", "Stan serwera"), ("sprawdziany", "Najbliższe sprawdziany"), ("kopia", "Kopia systemu teraz"),
        ("przejrzane", "Zgaś żółtą diodę"), ("restart", "Restart portalu lub Minecrafta"), ("nowa", "Nowa rozmowa z Claude"))])
    threading.Thread(target=petla_powiadomien, daemon=True).start()
    threading.Thread(target=petla_claude, daemon=True).start()
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
