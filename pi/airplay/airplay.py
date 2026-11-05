#!/usr/bin/env python3
"""
Głośnik AirPlay 2 (multiroom) na Pi: shairport-sync (zbudowany z --with-airplay-2, nqptp jako usługa systemowa)
działa jako usługa użytkownika tonyg `airplay.service` i gra przez PipeWire na wyjście wybrane na stronie
/strony/glosnik/: AUX (gniazdo 3,5 mm) albo głośnik Bluetooth.

Bluetooth tylko na czas grania: shairport-sync woła `airplay.py start` przed odtwarzaniem (łączy głośnik BT i ustawia go
jako wyjście) i `airplay.py stop` po 20 s ciszy od rozłączenia AirPlay (rozłącza głośnik, żeby był wolny dla innych).

  airplay.py stan                 JSON dla portalu
  airplay.py wlacz | wylacz       usługa airplay.service (i zapamiętanie w ustawieniach)
  airplay.py tryb aux|bt          wyjście; zostaje, dopóki nie zmienisz
  airplay.py skanuj               urządzenia Bluetooth w pobliżu (10 s) + sparowane
  airplay.py wybierz MAC          parowanie (raz) i zapamiętanie głośnika
  airplay.py start | stop         wywoływane przez shairport-sync (sessioncontrol)
Ustawienia: ~/airplay/ustawienia.json, stan grania: ~/airplay/stan.json, konfiguracja shairport-sync:
~/airplay/shairport-sync.conf (generowana z ustawień).
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

KAT = Path("/home/tonyg/airplay")
UST = KAT / "ustawienia.json"
STAN = KAT / "stan.json"
KONF = KAT / "shairport-sync.conf"
USLUGA = "airplay.service"
ENV = {**os.environ, "XDG_RUNTIME_DIR": "/run/user/1000", "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus"}
DOMYSLNE = {"wlaczony": True, "tryb": "aux", "bt_mac": None, "bt_nazwa": None, "nazwa": "Serwerek", "opoznienie_bt": 0.0,
            "usb": None}


def sh(*cmd, limit=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=limit, env=ENV)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as ex:
        return 1, str(ex)


def czytaj(p, dom):
    try:
        return {**dom, **json.loads(p.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(dom)


def zapisz(p, d):
    KAT.mkdir(exist_ok=True)
    p.with_suffix(".tmp").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(p.with_suffix(".tmp"), p)


def ustawienia():
    return czytaj(UST, DOMYSLNE)


# ---------------------------------------------------------------- PipeWire: wyjścia
def wyjscia():
    """[(id, nazwa, opis)] sinków PipeWire (wpctl status + inspect)"""
    _, out = sh("wpctl", "status")
    sek = out.split("Sinks:", 1)[1].split("Sources:", 1)[0] if "Sinks:" in out else ""
    wyn = []
    for m in re.finditer(r"(\d+)\.\s+(.+?)(?:\s+\[vol:.*)?$", sek, re.M):
        _, ins = sh("wpctl", "inspect", m.group(1))
        n = re.search(r'node\.name = "([^"]+)"', ins)
        wyn.append((m.group(1), n.group(1) if n else "", m.group(2).strip()))
    return wyn


def karty_usb():
    """podłączone karty dźwiękowe USB: [{nazwa (node.name), opis}]"""
    return [{"nazwa": n, "opis": o} for _, n, o in wyjscia() if "usb" in n.lower()]


def ustaw_wyjscie(tryb, mac=None, usb=None):
    """domyślne wyjście PipeWire: AUX = analogowe (bcm2835 / Wbudowany dźwięk), BT = bluez_output.<MAC>,
    USB = karta dźwiękowa USB (zapamiętana, a gdy jej nie ma: pierwsza podłączona)"""
    if tryb == "usb":
        karty = karty_usb()
        usb = next((k["nazwa"] for k in karty if k["nazwa"] == usb), karty[0]["nazwa"] if karty else None)
    for _ in range(20):                       # sink BT pojawia się chwilę po połączeniu
        for i, nazwa, opis in wyjscia():
            if (tryb == "bt" and mac and mac.replace(":", "_").lower() in nazwa.lower()) or (tryb == "usb" and usb and nazwa == usb) or \
               (tryb == "aux" and ("bcm2835" in nazwa or "analog" in nazwa.lower() or "Wbudowany" in opis or "Headphones" in opis)):
                sh("wpctl", "set-default", i)
                return True
        if tryb != "bt":
            return False
        time.sleep(0.5)
    return False


# ---------------------------------------------------------------- Bluetooth
def bt(*arg, limit=20):
    return sh("bluetoothctl", *arg, limit=limit)


def bt_dostepny():
    kod, out = bt("show", limit=5)
    if kod == 0 and "Controller" in out and "Powered: no" in out:     # np. po restarcie: włącz radio BT
        bt("power", "on", limit=5)
    return kod == 0 and "Controller" in out


def bt_polaczony(mac):
    if not mac:
        return False
    _, out = bt("info", mac, limit=5)
    return "Connected: yes" in out


# ---------------------------------------------------------------- shairport-sync
def konfiguracja(u):
    """konfiguracja shairport-sync: PipeWire (backend pa, wyjście = domyślne), hooki start/stop, AirPlay 2"""
    py = f"/usr/bin/python3 {Path(__file__).resolve()}"
    opozn = float(u.get("opoznienie_bt") or 0) if u["tryb"] == "bt" else 0.0
    KONF.write_text(f'''// generowane przez airplay.py ({time.strftime("%Y-%m-%d %H:%M")}); zmiany na stronie /strony/glosnik/
general = {{
  name = "{u["nazwa"]}";
  output_backend = "pa";
  mdns_backend = "avahi";
  interpolation = "soxr";
  volume_range_db = 60;
  audio_backend_latency_offset_in_seconds = {opozn:.2f};
  resync_threshold_in_seconds = 0.0;   // bez przeskakiwania: przy BT stałe ~0,08 s opóźnienia rwało dźwięk co 0,3 s
  drift_tolerance_in_seconds = 0.010;
}};
diagnostics = {{
  log_verbosity = 1;          // błędy i najważniejsze zdarzenia do dziennika (journalctl --user -u airplay)
  statistics = "yes";
}};
sessioncontrol = {{
  run_this_before_entering_active_state = "{py} start";
  run_this_after_exiting_active_state = "{py} stop";
  active_state_timeout = 20.0;
  wait_for_completion = "yes";
}};
pa = {{
  application_name = "AirPlay";
}};
''', encoding="utf-8")


def usluga(*arg):
    return sh("systemctl", "--user", *arg, USLUGA)


def wlacz(tak):
    u = ustawienia()
    u["wlaczony"] = tak
    zapisz(UST, u)
    if tak:
        konfiguracja(u)
        ustaw_wyjscie("aux") if u["tryb"] == "aux" else None
        usluga("enable", "--now")
        usluga("restart")
    else:
        usluga("disable", "--now")
        if u["tryb"] == "bt" and bt_polaczony(u["bt_mac"]):
            bt("disconnect", u["bt_mac"])
        zapisz(STAN, {"gra": False, "t": time.time()})


def tryb(t):
    u = ustawienia()
    if t not in ("aux", "bt", "usb"):
        raise SystemExit("tryb: aux, bt albo usb")
    stary = u["tryb"]
    u["tryb"] = t
    zapisz(UST, u)
    konfiguracja(u)
    gra = czytaj(STAN, {"gra": False})["gra"]
    if t in ("aux", "usb"):
        if t == "usb":
            karty = karty_usb()
            if karty and u.get("usb") not in [k["nazwa"] for k in karty]:
                u["usb"] = karty[0]["nazwa"]
                zapisz(UST, u)
        if not ustaw_wyjscie(t, usb=u.get("usb")):
            ustaw_wyjscie("aux")
        if stary == "bt" and bt_polaczony(u["bt_mac"]):
            bt("disconnect", u["bt_mac"])
    elif gra and u["bt_mac"]:                 # przełączenie w trakcie grania: od razu na głośnik BT
        bt("connect", u["bt_mac"], limit=25)
        ustaw_wyjscie("bt", u["bt_mac"])
    if u["wlaczony"] and not gra:             # nowe opóźnienie wyjścia w konfiguracji (gdy nic nie gra)
        usluga("restart")


def skanuj():
    if not bt_dostepny():
        return {"bt": False, "urzadzenia": []}
    bt("--timeout", "10", "scan", "on", limit=15)
    _, out = bt("devices", limit=5)
    _, spar = bt("devices", "Paired", limit=5)
    sparowane = set(re.findall(r"Device ([0-9A-F:]{17})", spar))
    wyn = []
    for mac, nazwa in re.findall(r"Device ([0-9A-F:]{17}) (.+)", out):
        if nazwa.replace("-", ":") == mac:     # bez nazwy (np. telefony w pobliżu): pomijamy
            continue
        _, info = bt("info", mac, limit=5)
        ikona = re.search(r"Icon: (\S+)", info)
        wyn.append({"mac": mac, "nazwa": nazwa.strip(), "sparowany": mac in sparowane, "ikona": ikona.group(1) if ikona else ""})
    wyn.sort(key=lambda d: (not d["sparowany"], d["ikona"] != "audio-card" and d["ikona"] != "audio-headset", d["nazwa"].lower()))
    return {"bt": True, "urzadzenia": wyn}


def wybierz(mac):
    if not re.fullmatch(r"[0-9A-F:]{17}", mac or ""):
        raise SystemExit("zły adres MAC")
    _, info = bt("info", mac, limit=5)
    if "Paired: yes" not in info:
        bt("--timeout", "8", "scan", "on", limit=12)   # urządzenie musi być widoczne (tryb parowania głośnika)
        kod, out = bt("pair", mac, limit=30)
        if kod != 0 or "Failed" in out:
            raise SystemExit("Nie udało się sparować: włącz w głośniku tryb parowania i spróbuj jeszcze raz.")
    bt("trust", mac, limit=10)
    nazwa = re.search(r"Name: (.+)", bt("info", mac, limit=5)[1])
    u = ustawienia()
    u["bt_mac"], u["bt_nazwa"] = mac, nazwa.group(1).strip() if nazwa else mac
    zapisz(UST, u)
    bt("disconnect", mac, limit=10)              # po parowaniu wolny, połączy się dopiero przy AirPlay


def start():
    """shairport-sync: zaraz zacznie grać"""
    u = ustawienia()
    bt_dostepny()
    zapisz(STAN, {"gra": True, "t": time.time()})
    if u["tryb"] == "bt" and u["bt_mac"]:
        for _ in range(3):
            if bt_polaczony(u["bt_mac"]) or bt("connect", u["bt_mac"], limit=25)[0] == 0:
                break
            time.sleep(2)
        if not ustaw_wyjscie("bt", u["bt_mac"]):
            ustaw_wyjscie("aux")              # głośnik BT niedostępny: gra przez AUX, żeby nie było ciszy
            zapisz(STAN, {"gra": True, "t": time.time(), "uwaga": "Głośnik Bluetooth niedostępny: gram przez AUX."})
    elif u["tryb"] == "usb":
        if not ustaw_wyjscie("usb", usb=u.get("usb")):
            ustaw_wyjscie("aux")              # karta USB odłączona: gra przez AUX
            zapisz(STAN, {"gra": True, "t": time.time(), "uwaga": "Karta dźwiękowa USB niepodłączona: gram przez AUX."})
    else:
        ustaw_wyjscie("aux")


def stop():
    """shairport-sync: 20 s po końcu sesji AirPlay -> zwolnij głośnik BT"""
    u = ustawienia()
    zapisz(STAN, {"gra": False, "t": time.time()})
    if u["bt_mac"] and bt_polaczony(u["bt_mac"]):
        bt("disconnect", u["bt_mac"])
    if not (u["tryb"] == "usb" and ustaw_wyjscie("usb", usb=u.get("usb"))):
        ustaw_wyjscie("aux")


ZDROWIE = KAT / "zdrowie.json"


def gra_naprawde(sekund=60):
    """shairport-sync wypisuje statystyki odtwarzania (player.c:2656) co ~8 s, gdy dźwięk płynie do wyjścia"""
    _, out = sh("journalctl", "--user", "-u", USLUGA, "--since", f"-{sekund}s", "--no-pager", "-o", "cat", limit=15)
    return "player.c:2656" in out or "Playback started" in out


def wyjscie_gra():
    """czy domyślne wyjście PipeWire faktycznie odtwarza (stan „running”)"""
    _, out = sh("wpctl", "inspect", "@DEFAULT_AUDIO_SINK@", limit=10)
    _, info = sh("pw-cli", "info", re.search(r"id (\d+)", out).group(1) if re.search(r"id (\d+)", out) else "0", limit=10)
    return 'state: "running"' in info


def pilnuj():
    """strażnik (co 20 s): sprawdza AirPlay jak iPhone (usługa, port 7000, nqptp, PipeWire, głośnik BT) i naprawia tylko to,
    co na pewno jest zepsute; NIGDY nie restartuje w trakcie grania, gdy dźwięk płynie. Wynik: ~/airplay/zdrowie.json
    (strona Głośnik, dioda portalu i powiadomienie przy problemie, który się nie naprawił)."""
    u = ustawienia()
    z = czytaj(ZDROWIE, {"naprawy": [], "zawieszony": 0})
    testy, naprawy = [], z.get("naprawy", [])[-10:]

    def test(nazwa, ok, opis=""):
        testy.append({"nazwa": nazwa, "ok": bool(ok), "opis": opis})
        return ok

    def naprawa(co):
        naprawy.append({"t": time.strftime("%Y-%m-%d %H:%M"), "co": co})
        print("pilnuj: " + co, flush=True)
    if not u["wlaczony"]:
        zapisz(ZDROWIE, {"czas": time.strftime("%Y-%m-%d %H:%M:%S"), "ok": True, "wylaczony": True, "testy": [], "naprawy": naprawy})
        return
    _, akt = usluga("is-active")
    if not test("Usługa AirPlay działa", akt.strip() == "active"):
        usluga("restart")
        naprawa("usługa AirPlay nie działała: uruchomiona")
    test("Synchronizacja AirPlay 2 (nqptp)", sh("systemctl", "is-active", "nqptp")[1].strip() == "active", "multiroom wymaga nqptp")
    test("iPhone może się połączyć (port 7000)", ":7000 " in sh("ss", "-ltn")[1])
    test("Dźwięk systemu (PipeWire)", "Sinks:" in sh("wpctl", "status")[1])
    if u["tryb"] == "bt":
        if test("Bluetooth włączony", bt_dostepny()) and u["bt_mac"]:
            _, info = bt("info", u["bt_mac"], limit=5)
            test(f"Głośnik {u['bt_nazwa'] or u['bt_mac']} sparowany", "Paired: yes" in info, "sparuj go jeszcze raz na stronie Głośnik")
    s = czytaj(STAN, {"gra": False})
    if s.get("gra") and time.time() - s.get("t", 0) > 45:
        plynie = gra_naprawde(60) or wyjscie_gra()
        if u["tryb"] == "bt" and u["bt_mac"] and not bt_polaczony(u["bt_mac"]):
            bt("connect", u["bt_mac"], limit=25)                 # w trakcie grania głośnik odpadł: połącz, bez restartu
            ustaw_wyjscie("bt", u["bt_mac"]) or ustaw_wyjscie("aux")
            naprawa("głośnik BT odpadł w trakcie grania: połączony ponownie")
        zaw = 0 if plynie else z.get("zawieszony", 0) + 1
        test("Dźwięk płynie do głośnika", plynie, "AirPlay połączony, ale nic nie gra")
        if zaw >= 3:                                         # ~1 min bez żadnego dźwięku przy „grającej” sesji: zawieszony
            zaw = 0
            zapisz(STAN, {"gra": False, "t": time.time(), "uwaga": "AirPlay się zaciął i został uruchomiony od nowa: puść jeszcze raz."})
            usluga("restart")
            naprawa("AirPlay zawieszony (sesja bez dźwięku przez minutę): uruchomiony od nowa")
    else:
        zaw = 0
    zle = [t for t in testy if not t["ok"]]
    zapisz(ZDROWIE, {"czas": time.strftime("%Y-%m-%d %H:%M:%S"), "ok": not zle, "testy": testy, "naprawy": naprawy[-10:],
                     "zawieszony": zaw, "problem_od": (z.get("problem_od") or time.time()) if zle else None})


def stan():
    u = ustawienia()
    _, akt = usluga("is-active")
    s = czytaj(STAN, {"gra": False})
    dost = bt_dostepny()
    return {**u, "dziala": akt.strip() == "active", "gra": s.get("gra", False), "uwaga": s.get("uwaga"),
            "bt_dostepny": dost, "bt_polaczony": bt_polaczony(u["bt_mac"]) if dost else False,
            "zbudowany": Path("/usr/local/bin/shairport-sync").exists(), "karty_usb": karty_usb(), "zdrowie": czytaj(ZDROWIE, {})}


if __name__ == "__main__":
    k = sys.argv[1] if len(sys.argv) > 1 else "stan"
    if k == "stan":
        print(json.dumps(stan(), ensure_ascii=False))
    elif k in ("wlacz", "wylacz"):
        wlacz(k == "wlacz")
    elif k == "tryb":
        tryb(sys.argv[2])
    elif k == "skanuj":
        print(json.dumps(skanuj(), ensure_ascii=False))
    elif k == "wybierz":
        wybierz(sys.argv[2])
    elif k == "start":
        start()
    elif k == "stop":
        stop()
    elif k == "pilnuj":
        pilnuj()
    elif k == "konfiguracja":              # ExecStartPre usługi: świeża konfiguracja, po starcie nic jeszcze nie gra
        konfiguracja(ustawienia())
        zapisz(STAN, {"gra": False, "t": time.time()})
    else:
        raise SystemExit(__doc__)
