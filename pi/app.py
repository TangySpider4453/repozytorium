#!/usr/bin/env python3
"""
Serwerek domowy - strona glowna Raspberry Pi 4B ("strona matka").

  /                  stan serwera, wszystkie dzialajace programy, linki do kazdej strony hostowanej na Pi
  /siec              wszystkie adresy IP (LAN, Tailscale, publiczny, tunel Minecraft), porty, urzadzenia Tailscale
  /terminal          terminal w przegladarce (osadza usluge home-terminal z portu 7681)
  /strony/<nazwa>/   strony statyczne z katalogu sites/<nazwa>/ (wystarczy wrzucic folder z index.html)
  /api/status, /api/siec   dane w JSON dla powyzszych stron
  /api/nauka/...     postepy nauki (fiszki, quizy), zmiana daty, „wazne” i ustawienia listy dla /strony/nauka/
  /api/progres/...   dziennik sylwetki: pomiary z wagi i zdjecia (tylko na Pi, dane/progres/) dla /strony/progres/
  /api/zdrowie       stan serwera dla diody na kazdej stronie i dziennik problemow (dane/zdrowie/), strona /strony/zdrowie/
  /api/todo          lista zadan z przypomnieniami (dane/todo.json), strona /strony/todo/, przypomnienia wysyla bot Telegram

NAS (Tony-Folder/Raspberry w /mnt/nas, montuje go nas-montuj.timer): zdjecia i filmy Progres oraz logi zdrowia ida tam
od razu. Gdy NAS niedostepny, zostaja na Pi (czerwona dioda) i przenosza sie same po jego powrocie (watek nas_petla).

Nasluch na porcie 80 wszystkich adresow Pi: przez Tailscale bez hasla, z sieci domowej (172.23.0.x) po zalogowaniu
haslem (ciasteczko na rok, sekcja „Dostep z sieci domowej”). Z internetu strona nie jest widoczna (brak publicznego IP).
Uruchamiane przez systemd: home-portal.service (uzytkownik tonyg, CAP_NET_BIND_SERVICE dla portu 80).
Konfiguracja (adres tunelu Minecraft, dodatkowe linki): config.json obok tego pliku.
"""
import json
import os
import pwd
import random
import re
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Flask, Response, abort, jsonify, redirect, send_from_directory

BASE = Path(__file__).resolve().parent
SITES = BASE / "sites"
CONFIG_FILE = BASE / "config.json"
PORT = 80
TERMINAL_PORT = 7681
DASHBOARD_PORT = 8090
MC_PORT = 19132

app = Flask(__name__)
HZ = os.sysconf("SC_CLK_TCK")
PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")


# ---------------------------------------------------------------- pomocnicze

def sh(args, timeout=8):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


_cache = {}


def cached(key, ttl, fn):
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = fn()
    _cache[key] = (now, value)
    return value


def config():
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read(path, default=""):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return default


def uptime_s():
    return float(read("/proc/uptime", "0 0").split()[0])


def unit_of(pid):
    """Nazwa uslugi systemd, do ktorej nalezy proces (z /proc/<pid>/cgroup)."""
    found = re.findall(r"([^/\n]+)\.service", read(f"/proc/{pid}/cgroup"))
    return found[-1] if found else ""


# ---------------------------------------------------------------- opisy

SERVICE_INFO = {
    "powernukkitx": ("Serwer i projekty", "Serwer Minecraft Bedrock (PowerNukkitX), gra na porcie 19132/UDP"),
    "playit": ("Serwer i projekty", "Tunel playit.gg: publiczny adres serwera Minecraft mimo braku publicznego IP"),
    "pi-dashboard": ("Serwer i projekty", "Panel Minecraft: temperatura, gracze, pobór mocy i konsola serwera (port 8090)"),
    "home-portal": ("Serwer i projekty", "Ta strona: stan serwera, adresy i linki (port 80, tylko Tailscale)"),
    "serwerek-telefon": ("Serwer i projekty", "Telefon serwerka: rozmowy przez Linphone, mowa rozpoznawana i syntezowana na Pi"),
    "serwerek-bot": ("Serwer i projekty", "Bot Telegram @SerwerekAntek_bot: powiadomienia, przyciski i rozmowa z Claude"),
    "home-terminal": ("Serwer i projekty", "Terminal w przeglądarce (port 7681, tylko Tailscale, logowanie hasłem Linuksa)"),
    "ollama": ("Serwer i projekty", "Ollama: lokalne modele językowe AI, API tylko na tym Pi (port 11434)"),
    "tailscaled": ("Sieć i zdalny dostęp", "Tailscale: prywatna sieć VPN łącząca Twoje urządzenia"),
    "ssh": ("Sieć i zdalny dostęp", "SSH: zdalna konsola (port 22)"),
    "wayvnc": ("Sieć i zdalny dostęp", "VNC: zdalny pulpit (port 5900)"),
    "wayvnc-control": ("Sieć i zdalny dostęp", "Sterowanie serwerem VNC"),
    "NetworkManager": ("Sieć i zdalny dostęp", "Zarządzanie połączeniami sieciowymi (kabel, WiFi)"),
    "wpa_supplicant": ("Sieć i zdalny dostęp", "Logowanie do sieci WiFi"),
    "avahi-daemon": ("Sieć i zdalny dostęp", "mDNS: nazwa raspberrypi.local w sieci domowej"),
    "ModemManager": ("Sieć i zdalny dostęp", "Obsługa modemów komórkowych (tu niepotrzebna)"),
    "smbd": ("Pliki i drukowanie", "Samba: udostępnianie folderów w sieci Windows (porty 139, 445)"),
    "nmbd": ("Pliki i drukowanie", "Samba: nazwy NetBIOS w sieci domowej"),
    "winbind": ("Pliki i drukowanie", "Samba: obsługa kont i domen Windows"),
    "rpcbind": ("Pliki i drukowanie", "RPC dla udziałów NFS (port 111)"),
    "nfs-blkmap": ("Pliki i drukowanie", "NFS: obsługa układu bloków"),
    "cups": ("Pliki i drukowanie", "CUPS: drukowanie (tylko lokalnie)"),
    "cups-browsed": ("Pliki i drukowanie", "CUPS: wyszukiwanie drukarek w sieci"),
    "lightdm": ("Pulpit", "Pulpit graficzny i ekran logowania"),
    "getty@tty1": ("Pulpit", "Konsola tekstowa na podłączonym ekranie"),
    "accounts-daemon": ("Pulpit", "Informacje o kontach dla pulpitu"),
    "colord": ("Pulpit", "Profile kolorów ekranu i drukarek"),
    "udisks2": ("Pulpit", "Montowanie dysków i pendrive'ów"),
    "user@1000": ("Pulpit", "Sesja użytkownika tonyg"),
    "polkit": ("System", "Uprawnienia do działań administracyjnych"),
    "cron": ("System", "Harmonogram zadań"),
    "dbus": ("System", "Komunikacja między programami"),
    "systemd-journald": ("System", "Dziennik systemowy (logi)"),
    "systemd-logind": ("System", "Logowanie użytkowników i sesje"),
    "systemd-timesyncd": ("System", "Synchronizacja zegara z internetem"),
    "systemd-udevd": ("System", "Wykrywanie podłączanych urządzeń"),
}
GROUPS = ["Serwer i projekty", "Sieć i zdalny dostęp", "Pliki i drukowanie", "Pulpit", "System"]

PORT_INFO = {
    ("tcp", 22): "SSH: zdalna konsola",
    ("tcp", 80): "Ta strona (portal)",
    ("tcp", 7681): "Terminal w przeglądarce",
    ("tcp", 8090): "Panel Minecraft",
    ("udp", 19132): "Minecraft Bedrock: gra",
    ("tcp", 5900): "VNC: zdalny pulpit",
    ("tcp", 139): "Samba (NetBIOS)",
    ("tcp", 445): "Samba: udziały plików",
    ("udp", 137): "NetBIOS: nazwy komputerów",
    ("udp", 138): "NetBIOS: datagramy",
    ("tcp", 111): "rpcbind (NFS)",
    ("udp", 111): "rpcbind (NFS)",
    ("tcp", 631): "CUPS: drukowanie",
    ("tcp", 11434): "Ollama: API modeli AI",
    ("udp", 5353): "mDNS (raspberrypi.local)",
    ("udp", 41641): "Tailscale: tunel WireGuard",
}
PROGRAM_INFO = {
    "playit": "playit: połączenia z serwerami tunelu (porty losowe)",
    "tailscaled": "Tailscale: usługi wewnętrzne",
    "avahi-daemon": "mDNS (Avahi): wykrywanie w sieci domowej",
}

IFACE_INFO = {
    "eth0": "Sieć domowa przez kabel Ethernet",
    "wlan0": "Sieć domowa przez WiFi",
    "tailscale0": "Tailscale: prywatna sieć VPN Twoich urządzeń",
    "lo": "Pętla zwrotna: Pi sam do siebie",
}


# ---------------------------------------------------------------- system

_cpu_prev = None


def cpu_percent():
    global _cpu_prev

    def sample():
        vals = [int(x) for x in read("/proc/stat").splitlines()[0].split()[1:]]
        return vals[3] + vals[4], sum(vals)

    cur = sample()
    prev = _cpu_prev
    if prev is None or cur[1] - prev[1] <= 0:
        time.sleep(0.25)
        prev, cur = cur, sample()
    _cpu_prev = cur
    d_idle, d_total = cur[0] - prev[0], cur[1] - prev[1]
    return round(100.0 * (1 - d_idle / d_total), 1) if d_total > 0 else 0.0


def meminfo():
    m = {}
    for line in read("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        m[k] = int(v.split()[0]) * 1024 if v.split() else 0
    return m


def os_name():
    for line in read("/etc/os-release").splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip('"')
    return ""


def timer_info(name):
    out = sh(["systemctl", "show", name, "--no-pager", "-p", "NextElapseUSecRealtime", "-p", "LastTriggerUSec",
              "-p", "ActiveState"])
    d = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return {"nastepne": d.get("NextElapseUSecRealtime", ""), "ostatnie": d.get("LastTriggerUSec", ""),
            "stan": d.get("ActiveState", "")}


def system_info():
    m = meminfo()
    du = shutil.disk_usage("/")
    try:
        temp = int(read("/sys/class/thermal/thermal_zone0/temp", "0")) / 1000
    except ValueError:
        temp = None
    return {
        "host": socket.gethostname(),
        "model": read("/proc/device-tree/model").strip("\x00").strip(),
        "system": os_name(),
        "jadro": os.uname().release,
        "uptime": uptime_s(),
        "temp": temp,
        "cpu": cpu_percent(),
        "load": [round(x, 2) for x in os.getloadavg()],
        "rdzenie": os.cpu_count(),
        "ram_total": m.get("MemTotal", 0),
        "ram_uzyte": m.get("MemTotal", 0) - m.get("MemAvailable", 0),
        "swap_total": m.get("SwapTotal", 0),
        "swap_uzyte": m.get("SwapTotal", 0) - m.get("SwapFree", 0),
        "dysk_total": du.total,
        "dysk_uzyte": du.used,
        "autoupdate": timer_info("mc-autoupdate.timer"),
        "restart_wymagany": Path("/var/run/reboot-required").exists(),
        "nieudane_uslugi": [l.split()[0] for l in sh(["systemctl", "--failed", "--no-legend", "--plain",
                                                       "--no-pager"]).splitlines() if l.strip()],
    }


def services():
    out = sh(["systemctl", "list-units", "--type=service", "--state=running", "--no-legend", "--plain", "--no-pager"])
    ids = [line.split()[0] for line in out.splitlines() if line.strip()]
    if not ids:
        return []
    props = sh(["systemctl", "show", "--no-pager", "-p", "Id", "-p", "Description", "-p", "MainPID",
                "-p", "ActiveEnterTimestampMonotonic", "-p", "MemoryCurrent", *ids])
    up = uptime_s()
    result = []
    for block in props.strip().split("\n\n"):
        d = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        uid = d.get("Id", "")
        name = uid[:-8] if uid.endswith(".service") else uid
        group, desc = SERVICE_INFO.get(name, ("System", d.get("Description", "")))
        try:
            since = max(0.0, up - int(d.get("ActiveEnterTimestampMonotonic", "0")) / 1e6)
        except ValueError:
            since = None
        mem = d.get("MemoryCurrent", "")
        result.append({
            "nazwa": name, "grupa": group, "opis": desc, "opis_systemd": d.get("Description", ""),
            "pid": int(d.get("MainPID") or 0), "dziala_od_s": since,
            "ram_mb": round(int(mem) / 1048576, 1) if mem.isdigit() else None,
        })
    result.sort(key=lambda s: (GROUPS.index(s["grupa"]) if s["grupa"] in GROUPS else 99, s["nazwa"].lower()))
    return result


_proc_prev = None


def top_processes(limit=10):
    """Procesy najbardziej obciazajace CPU (pomiar miedzy kolejnymi odswiezeniami) i pamiec."""
    global _proc_prev
    now = time.monotonic()
    cur, info = {}, {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            stat = Path(f"/proc/{d}/stat").read_text()
            rp = stat.rfind(")")
            comm = stat[stat.find("(") + 1:rp]
            f = stat[rp + 2:].split()
            ticks = int(f[11]) + int(f[12])
            rss = int(f[21]) * PAGE_SIZE
            uid = os.stat(f"/proc/{d}").st_uid
        except Exception:
            continue
        pid = int(d)
        cur[pid] = ticks
        info[pid] = (comm, rss, uid)
    rows = []
    prev = _proc_prev
    for pid, (comm, rss, uid) in info.items():
        cpu = None
        if prev and now - prev[0] > 0.5:
            cpu = round((cur[pid] - prev[1].get(pid, cur[pid])) / HZ / (now - prev[0]) * 100, 1)
        try:
            user = pwd.getpwuid(uid).pw_name
        except KeyError:
            user = str(uid)
        rows.append({"pid": pid, "nazwa": comm, "uzytkownik": user, "cpu": cpu, "ram_mb": round(rss / 1048576, 1)})
    _proc_prev = (now, cur)
    rows.sort(key=lambda r: ((r["cpu"] or 0), r["ram_mb"]), reverse=True)
    top = rows[:limit]
    for r in top:
        r["usluga"] = unit_of(r["pid"])
    return top


# ---------------------------------------------------------------- porty

def reach(addresses):
    cats = set()
    for a in addresses:
        base, _, iface = a.partition("%")
        base = base.strip("[]")
        if base in ("*", "0.0.0.0", "::"):
            cats.add("all")
        elif base.startswith("127.") or base == "::1":
            cats.add("local")
        elif base.startswith("100.") or base.startswith("fd7a:115c:a1e0") or iface == "tailscale0":
            cats.add("ts")
        else:
            cats.add("lan")
    if "all" in cats:
        return "LAN + Tailscale"
    names = {"local": "tylko ten Pi", "ts": "tylko Tailscale", "lan": "tylko LAN"}
    return ", ".join(names[c] for c in ("ts", "lan", "local") if c in cats)


def listening():
    out = sh(["sudo", "-n", "ss", "-tulpnH"]) or sh(["ss", "-tulnH"])
    groups = {}
    for line in out.splitlines():
        p = line.split()
        if len(p) < 5:
            continue
        proto, local = p[0], p[4]
        addr, _, port = local.rpartition(":")
        if not port.isdigit():
            continue
        procs = re.findall(r'\("([^"]+)",pid=(\d+)', line)
        prog = procs[0][0] if procs else "?"
        pid = int(procs[0][1]) if procs else 0
        key = (proto, int(port), prog)
        g = groups.setdefault(key, {"proto": proto, "port": int(port), "program": prog,
                                    "usluga": unit_of(pid) if pid else "", "adresy": []})
        if addr not in g["adresy"]:
            g["adresy"].append(addr)
    rows = []
    for g in groups.values():
        g["zasieg"] = reach(g["adresy"])
        g["opis"] = PORT_INFO.get((g["proto"], g["port"])) or PROGRAM_INFO.get(g["program"], "")
        rows.append(g)
    rows.sort(key=lambda g: (g["port"], g["proto"]))
    return rows


def is_http(addr, port):
    host = "127.0.0.1" if addr.strip("[]") in ("*", "0.0.0.0", "::") else addr.split("%")[0].strip("[]")
    try:
        with socket.create_connection((host, port), timeout=0.8) as s:
            s.sendall(b"HEAD / HTTP/1.0\r\nHost: localhost\r\n\r\n")
            return s.recv(5) == b"HTTP/"
    except Exception:
        return False


# ---------------------------------------------------------------- strony

def site_list():
    pages = []
    if SITES.is_dir():
        for d in sorted(SITES.iterdir()):
            if d.is_dir() and (d / "index.html").is_file() and re.fullmatch(r"[a-z0-9_-]+", d.name):
                meta = {}
                try:
                    meta = json.loads((d / "site.json").read_text(encoding="utf-8"))
                except Exception:
                    pass
                pages.append({"nazwa": meta.get("tytul", d.name), "opis": meta.get("opis", ""),
                              "port": PORT, "sciezka": f"/strony/{d.name}/", "dziala": True, "typ": "strona"})
    return pages


def web_pages(ports):
    tcp = {g["port"]: g for g in ports if g["proto"] == "tcp"}
    pages = [
        {"nazwa": "Sieć i adresy", "opis": "Wszystkie adresy IP serwera, tunel Minecraft, porty i urządzenia w Tailscale",
         "port": PORT, "sciezka": "/siec", "dziala": True, "typ": "portal"},
        {"nazwa": "Terminal", "opis": "Konsola Linuksa w przeglądarce, logowanie hasłem użytkownika",
         "port": PORT, "sciezka": "/terminal", "dziala": TERMINAL_PORT in tcp, "typ": "portal"},
        {"nazwa": "Panel Minecraft", "opis": "Temperatura, gracze online, pobór mocy (szacunek) i konsola serwera",
         "port": DASHBOARD_PORT, "sciezka": "/", "dziala": DASHBOARD_PORT in tcp, "typ": "aplikacja",
         "dodatkowe": [{"nazwa": "Konsola serwera MC", "sciezka": "/console"}]},
    ]
    pages += site_list()
    known = {PORT, TERMINAL_PORT, DASHBOARD_PORT}
    for extra in config().get("strony_dodatkowe", []):
        try:
            port = int(extra.get("port", PORT))
        except (TypeError, ValueError):
            continue
        known.add(port)
        pages.append({"nazwa": extra.get("nazwa", f"port {port}"), "opis": extra.get("opis", ""), "port": port,
                      "sciezka": extra.get("sciezka", "/"), "dziala": port in tcp, "typ": "aplikacja"})
    skip = {"sshd", "smbd", "rpcbind", "wayvnc", "tailscaled", "cupsd", "systemd", "ollama"}
    for port, g in sorted(tcp.items()):
        if port in known or g["program"] in skip or g["zasieg"] == "tylko ten Pi":
            continue
        if cached(f"http:{port}", 120, lambda g=g, port=port: is_http(g["adresy"][0], port)):
            pages.append({"nazwa": f"{g['program']} (port {port})", "port": port, "sciezka": "/", "dziala": True,
                          "opis": "Wykryte automatycznie: ten program odpowiada jak strona WWW", "typ": "wykryta"})
    return pages


# ---------------------------------------------------------------- siec

def address_note(iface, fam, addr, default_dev):
    if iface == "lo":
        return "Pętla zwrotna: Pi łączy się sam ze sobą. Niedostępne z zewnątrz."
    if addr.startswith("fe80:"):
        return "Adres lokalny łącza IPv6: tworzony automatycznie, działa tylko w obrębie jednej sieci. Do niczego go nie używasz."
    if iface == "tailscale0":
        if fam == "IPv4":
            return "Stały adres w Tailscale. Działa z każdego Twojego urządzenia z Tailscale, w domu i poza domem. Tego adresu używaj."
        return "Ten sam adres Tailscale w wersji IPv6."
    if iface == "eth0" and fam == "IPv4":
        main = " Główne połączenie (trasa domyślna)." if default_dev == "eth0" else ""
        return "Adres w sieci domowej przez kabel. Działa tylko z urządzeń w domu." + main
    if iface == "wlan0" and fam == "IPv4":
        main = " Główne połączenie (trasa domyślna)." if default_dev == "wlan0" else " Zapasowe: ta sama sieć co kabel."
        return "Adres w sieci domowej przez WiFi. Działa tylko z urządzeń w domu." + main
    return ""


def wifi_info():
    out = sh(["/usr/sbin/iw", "dev", "wlan0", "link"]) or sh(["iw", "dev", "wlan0", "link"])
    info = {}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("SSID:"):
            info["ssid"] = line[5:].strip()
        elif line.startswith("signal:"):
            info["sygnal"] = line[7:].strip()
        elif line.startswith("freq:"):
            info["czestotliwosc"] = line[5:].strip() + " MHz"
        elif line.startswith("tx bitrate:"):
            info["predkosc"] = line[11:].strip()
    return info


def tailscale_info():
    try:
        d = json.loads(sh(["tailscale", "status", "--json"]) or "{}")
    except ValueError:
        d = {}
    me = d.get("Self", {}) or {}
    peers = []
    for p in (d.get("Peer") or {}).values():
        if p.get("CurAddr"):
            via = "bezpośrednio (" + p["CurAddr"] + ")"
        elif p.get("Relay") and p.get("Online"):
            via = "przez przekaźnik Tailscale (" + p["Relay"] + ")"
        else:
            via = ""
        peers.append({"nazwa": p.get("HostName", ""), "dns": (p.get("DNSName") or "").rstrip("."),
                      "ip": p.get("TailscaleIPs") or [], "system": p.get("OS", ""), "online": bool(p.get("Online")),
                      "ostatnio": "" if p.get("Online") else (p.get("LastSeen") or ""), "polaczenie": via})
    peers.sort(key=lambda x: (not x["online"], x["nazwa"].lower()))
    return {"nazwa": me.get("HostName", ""), "dns": (me.get("DNSName") or "").rstrip("."),
            "ip": me.get("TailscaleIPs") or [], "magicdns": d.get("MagicDNSSuffix", ""),
            "wersja": d.get("Version", ""), "urzadzenia": peers}


def public_address():
    """Adres, pod ktorym Pi wychodzi do internetu (z pomiaru Tailscale netcheck, bez zewnetrznych stron)."""
    try:
        d = json.loads(sh(["tailscale", "netcheck", "--format=json"], timeout=20) or "{}")
    except ValueError:
        d = {}
    v4 = (d.get("GlobalV4") or "").rsplit(":", 1)[0]
    v6 = (d.get("GlobalV6") or "")
    if v6.startswith("["):
        v6 = v6[1:v6.find("]")]
    return {"ipv4": v4, "ipv6": v6, "udp": d.get("UDP"), "zmierzono": time.strftime("%H:%M:%S")}


RAKNET_MAGIC = bytes.fromhex("00ffff00fefefefefdfdfdfd12345678")


def raknet_ping(host, port, timeout=2.5):
    """Zapytanie Unconnected Ping protokolu Bedrock - to samo, co robi gra na liscie serwerow."""
    result = {"ok": False, "blad": "", "ip": ""}
    try:
        infos = socket.getaddrinfo(host, port, 0, socket.SOCK_DGRAM)
    except OSError as e:
        result["blad"] = f"nie da się rozwiązać nazwy ({e})"
        return result
    infos.sort(key=lambda i: 0 if i[0] == socket.AF_INET else 1)
    seen = set()
    for fam, _, _, _, sa in infos:
        if sa[0] in seen:
            continue
        seen.add(sa[0])
        pkt = b"\x01" + struct.pack(">q", int(time.time() * 1000)) + RAKNET_MAGIC + struct.pack(">q", random.getrandbits(62))
        try:
            with socket.socket(fam, socket.SOCK_DGRAM) as s:
                s.settimeout(timeout)
                t0 = time.monotonic()
                s.sendto(pkt, sa)
                data, _ = s.recvfrom(4096)
                ms = round((time.monotonic() - t0) * 1000)
        except OSError as e:
            result["blad"] = f"brak odpowiedzi z {sa[0]} ({e.__class__.__name__})"
            continue
        if not data or data[0] != 0x1C or len(data) < 35:
            result["blad"] = "nieprawidłowa odpowiedź"
            continue
        ln = struct.unpack(">H", data[33:35])[0]
        f = data[35:35 + ln].decode("utf-8", "replace").split(";")
        result.update({"ok": True, "blad": "", "ip": sa[0], "ms": ms,
                       "motd": re.sub(r"§.", "", f[1]) if len(f) > 1 else "",
                       "wersja": f[3] if len(f) > 3 else "",
                       "gracze": int(f[4]) if len(f) > 4 and f[4].isdigit() else None,
                       "max": int(f[5]) if len(f) > 5 and f[5].isdigit() else None})
        return result
    return result


def samba_shares():
    shares, cur = [], None
    for raw in read("/etc/samba/smb.conf").splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        m = re.fullmatch(r"\[(.+)\]", line)
        if m:
            name = m.group(1)
            cur = None if name.lower() in ("global", "printers", "print$") else {"nazwa": name, "sciezka": "", "opis": "",
                                                                                 "zapis": False, "uzytkownicy": ""}
            if cur:
                shares.append(cur)
            continue
        if cur is None or "=" not in line:
            continue
        k, v = (x.strip() for x in line.split("=", 1))
        k = k.lower()
        if k == "path":
            cur["sciezka"] = v
        elif k == "comment":
            cur["opis"] = v
        elif k in ("writable", "writeable", "write ok") and v.lower() in ("yes", "true", "1"):
            cur["zapis"] = True
        elif k == "read only" and v.lower() in ("no", "false", "0"):
            cur["zapis"] = True
        elif k == "valid users":
            cur["uzytkownicy"] = v
    for s in shares:
        if s["nazwa"] == "homes" and not s["sciezka"]:
            s["sciezka"] = "katalog domowy zalogowanego użytkownika"
    return shares


def network():
    try:
        raw = json.loads(sh(["ip", "-j", "addr"]) or "[]")
        routes = json.loads(sh(["ip", "-j", "route"]) or "[]")
    except ValueError:
        raw, routes = [], []
    defaults = [{"bramka": r.get("gateway", ""), "interfejs": r.get("dev", ""), "metryka": r.get("metric")}
                for r in routes if r.get("dst") == "default"]
    defaults.sort(key=lambda r: r["metryka"] if r["metryka"] is not None else 0)
    default_dev = defaults[0]["interfejs"] if defaults else ""
    interfaces = []
    for itf in raw:
        name = itf.get("ifname", "")
        addrs = []
        for a in itf.get("addr_info", []):
            fam = "IPv4" if a.get("family") == "inet" else "IPv6"
            addrs.append({"adres": a.get("local", ""), "prefiks": a.get("prefixlen"), "rodzina": fam,
                          "opis": address_note(name, fam, a.get("local", ""), default_dev)})
        interfaces.append({"nazwa": name, "opis": IFACE_INFO.get(name, ""), "stan": itf.get("operstate", ""),
                           "mac": itf.get("address") if name not in ("lo", "tailscale0") else "", "adresy": addrs})
    order = {"tailscale0": 0, "eth0": 1, "wlan0": 2, "lo": 9}
    interfaces.sort(key=lambda i: order.get(i["nazwa"], 5))
    dns = [l.split()[1] for l in read("/etc/resolv.conf").splitlines() if l.startswith("nameserver") and len(l.split()) > 1]

    def ipv4(dev):
        for i in interfaces:
            if i["nazwa"] == dev:
                for a in i["adresy"]:
                    if a["rodzina"] == "IPv4":
                        return a["adres"]
        return ""

    ts = cached("tailscale", 15, tailscale_info)
    cfg = config().get("tunel_mc", {})
    tunnel_host, tunnel_port = cfg.get("adres", ""), int(cfg.get("port", 0) or 0)
    local_mc = cached("mc_local", 15, lambda: raknet_ping("127.0.0.1", MC_PORT, 1.5))
    tunnel_mc = cached("mc_tunel", 60, lambda: raknet_ping(tunnel_host, tunnel_port)) if tunnel_host and tunnel_port \
        else {"ok": False, "blad": "brak adresu tunelu w config.json"}
    ts_ip = next((x for x in ts["ip"] if "." in x), "")
    mc = [
        {"gdzie": "Internet (znajomi)", "adres": f"{tunnel_host}:{tunnel_port}" if tunnel_host else "",
         "opis": "Publiczny adres przez tunel playit.gg. Ten adres dajesz znajomym. Działa bez publicznego IP.",
         "status": tunnel_mc},
        {"gdzie": "Tailscale", "adres": f"{ts_ip}:{MC_PORT}",
         "opis": "Z Twoich urządzeń w Tailscale, z dowolnego miejsca. Omija tunel, więc ma najmniejsze opóźnienie.",
         "status": local_mc},
        {"gdzie": "Sieć domowa", "adres": f"{ipv4(default_dev) or ipv4('eth0')}:{MC_PORT}",
         "opis": "Dla graczy podłączonych do domowego WiFi lub kabla.", "status": local_mc},
    ]
    access = [
        {"nazwa": "Tailscale (IPv4)", "adres": ts_ip, "opis": "Główny adres do wszystkiego: tej strony, SSH, terminala, panelu."},
        {"nazwa": "Tailscale (nazwa MagicDNS)", "adres": ts["dns"],
         "opis": "To samo co adres Tailscale, tylko nazwą. Działa w przeglądarce na urządzeniach z Tailscale."},
        {"nazwa": "Sieć domowa: kabel", "adres": ipv4("eth0"), "opis": "Tylko z urządzeń w domu. Ta strona i terminal są tu celowo niedostępne."},
        {"nazwa": "Sieć domowa: WiFi", "adres": ipv4("wlan0"), "opis": "Drugie połączenie z tą samą siecią domową (zapasowe)."},
        {"nazwa": "Nazwa w sieci domowej", "adres": socket.gethostname() + ".local",
         "opis": "Nazwa mDNS (Avahi) zamiast adresu, w domowej sieci."},
    ]
    pub = cached("publiczny", 900, public_address)
    return {
        "dostep": access,
        "publiczny": pub,
        "minecraft": mc,
        "interfejsy": interfaces,
        "bramki": defaults,
        "dns": dns,
        "wifi": wifi_info(),
        "tailscale": ts,
        "porty": cached("porty", 10, listening),
        "samba": samba_shares(),
    }


# ---------------------------------------------------------------- HTML

PAGE = r"""<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%%TITLE%%</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=Archivo+Narrow:wght@600;700&display=swap" rel="stylesheet">
<style>
/* Uklad: waska kolumna z naglowkiem, kafle stanu, potem tabele. Akcent: zielen "zasilania" (serwer energooszczedny). */
:root{
  --bg:#EEF1EF; --surface:#FAFBFA; --ink:#17201C; --muted:#5B6862; --line:#D0D8D3;
  --accent:#1F7A5A; --accent-soft:#D7EDE3; --warn:#A8620A; --warn-soft:#F5E6CF; --bad:#B2382C; --bad-soft:#F6DCD8;
  --display:"Archivo Narrow","Arial Narrow",sans-serif;
  --body:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Consolas,monospace;
  color-scheme:light;
}
@media (prefers-color-scheme: dark){:root{
  --bg:#0E1412; --surface:#151D1A; --ink:#E2EAE6; --muted:#93A39B; --line:#26322D;
  --accent:#5FD1A5; --accent-soft:#123227; --warn:#E9A23B; --warn-soft:#3A2A10; --bad:#F07167; --bad-soft:#3B1714; color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 var(--body);padding:0 max(16px,env(safe-area-inset-left)) 0 max(16px,env(safe-area-inset-right))}
.wrap{max-width:1100px;margin:0 auto;padding:22px 0 60px;display:flex;flex-direction:column;gap:34px}
header{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:14px;border-bottom:1px solid var(--line);padding-bottom:16px}
h1,h2,h3{font-family:var(--display);font-weight:700;line-height:1.05;margin:0;letter-spacing:.01em;text-wrap:balance}
h1{font-size:clamp(32px,6vw,48px)}
h2{font-size:28px}
h3{font-size:19px;font-weight:600}
.sub{color:var(--muted);font-size:14px;margin-top:4px}
nav{display:flex;flex-wrap:wrap;gap:6px}
nav a{font-family:var(--mono);font-size:13px;text-decoration:none;color:var(--ink);border:1px solid var(--line);background:var(--surface);padding:6px 12px;border-radius:999px}
nav a .ik{font-family:"Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",sans-serif;margin-right:5px;font-size:14px}
nav a.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
nav a:hover{border-color:var(--accent)}
section{display:flex;flex-direction:column;gap:14px}
.sec-note{color:var(--muted);max-width:75ch;margin:0}
/* 5 kafelkow bez osieroconego ostatniego: telefon 2+2+1, tablet 3+2, szeroki ekran 5 w rzedzie */
.tiles{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px;display:flex;flex-direction:column;grid-column:span 2;min-width:0}
.tile:nth-child(4),.tile:nth-child(5){grid-column:span 3}
.tile .bar{margin-top:auto}
.tile .d{margin-bottom:8px}
@media (max-width:540px){.tile,.tile:nth-child(4){grid-column:span 3}.tile:nth-child(5){grid-column:span 6}}
@media (max-width:360px){.tile .v{white-space:normal}}
@media (min-width:1080px){.tiles{grid-template-columns:repeat(5,minmax(0,1fr))}.tile,.tile:nth-child(4),.tile:nth-child(5){grid-column:span 1}.tile .v{font-size:26px}}
.tile .k{font-family:var(--mono);font-size:11.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}
.tile .v{font-family:var(--display);font-size:clamp(22px,6vw,30px);font-weight:700;font-variant-numeric:tabular-nums;line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile .d{font-size:13px;color:var(--muted)}
.bar{height:5px;background:var(--line);border-radius:3px;overflow:hidden;margin-top:6px}
.bar i{display:block;height:100%;background:var(--accent)}
.bar i.w{background:var(--warn)} .bar i.b{background:var(--bad)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:12px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px;display:flex;flex-direction:column;gap:8px}
.card .top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
.card p{margin:0;color:var(--muted);font-size:14px}
.btns{display:flex;flex-wrap:wrap;gap:8px;margin-top:auto}
.btn{font-family:var(--mono);font-size:13px;text-decoration:none;padding:6px 12px;border-radius:7px;background:var(--accent);color:var(--surface);border:1px solid var(--accent)}
.btn.alt{background:transparent;color:var(--accent)}
.btn:hover{filter:brightness(1.08)}
.chip{font-family:var(--mono);font-size:11.5px;padding:2px 8px;border-radius:999px;white-space:nowrap;border:1px solid var(--line);color:var(--muted)}
.chip.ok{background:var(--accent-soft);color:var(--accent);border-color:transparent}
.chip.warn{background:var(--warn-soft);color:var(--warn);border-color:transparent}
.chip.bad{background:var(--bad-soft);color:var(--bad);border-color:transparent}
.tbl{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}
th{font-family:var(--mono);font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);white-space:nowrap}
td.m,.m{font-family:var(--mono);font-size:13px;font-variant-numeric:tabular-nums}
td.n{white-space:nowrap}
td .s{display:block;color:var(--muted);font-size:13px}
.grp{font-family:var(--mono);font-size:12px;text-transform:uppercase;letter-spacing:.07em;color:var(--accent);margin-top:6px}
.copy{cursor:pointer;border-bottom:1px dashed var(--muted)}
.copy:hover{color:var(--accent)}
.err{background:var(--bad-soft);color:var(--bad);padding:10px 14px;border-radius:8px}
.iface{display:grid;grid-template-columns:minmax(0,1fr);gap:6px}
footer{color:var(--muted);font-size:13px;border-top:1px solid var(--line);padding-top:12px}
.term{height:min(78vh,900px);border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#0f1519}
.term iframe{width:100%;height:100%;border:0;display:block}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media (max-width:640px){th,td{padding:7px 9px}}
.zad{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 16px}
.zad-sek{display:flex;flex-direction:column;gap:10px}
</style><script src="/strony/zdrowie/zadania.js"></script><script src="/strony/zdrowie/obciazenie.js"></script></head>
<body><div class="wrap">
<header>
  <div><h1 id="h-title">Serwerek domowy</h1><div class="sub" id="h-sub">Raspberry Pi 4B · ładowanie…</div></div>
  <nav>
    <a href="/" data-p="start"><span class="ik" aria-hidden="true">🏠</span>Start</a>
    <a href="/siec" data-p="siec"><span class="ik" aria-hidden="true">🌐</span>Sieć i adresy</a>
    <a href="/terminal" data-p="terminal"><span class="ik" aria-hidden="true">💻</span>Terminal</a>
    <a href="/strony/lazik/" data-p="lazik"><span class="ik" aria-hidden="true">🚙</span>Łazik</a>
    <a href="/strony/nauka/" data-p="nauka"><span class="ik" aria-hidden="true">📚</span>Nauka</a>
    <a href="/strony/progres/" data-p="progres"><span class="ik" aria-hidden="true">💪</span>Progres</a>
    <a href="/strony/zdrowie/" data-p="zdrowie"><span class="ik" aria-hidden="true">🩺</span>Zdrowie</a>
    <a href="/strony/todo/" data-p="todo"><span class="ik" aria-hidden="true">📝</span>Zadania</a>
    <a href="/strony/zawodowe/" data-p="zawodowe"><span class="ik" aria-hidden="true">🤖</span>Zawodowe</a>
  </nav>
</header>
<main id="main" class="wrap" style="padding:0;width:100%"></main>
<footer id="foot">Przez Tailscale bez hasła, z sieci domowej po zalogowaniu. Dane odświeżają się same.</footer>
</div>
<script>
const PAGE="%%PAGE%%", PORT=%%PORT%%, TERMINAL_PORT=%%TPORT%%;
document.querySelectorAll('nav a').forEach(a=>{if(a.dataset.p===PAGE)a.classList.add('on')});
fetch('/api/dostep').then(r=>r.json()).then(d=>{if(d.siec==='domowa'){const a=document.createElement('a');a.href='/wyloguj';a.innerHTML='<span class="ik" aria-hidden="true">🚪</span>Wyloguj';a.title='Zapomnij to urządzenie (wejście z sieci domowej)';document.querySelector('nav').append(a)}}).catch(()=>{});
function h(tag,attrs,...kids){const e=document.createElement(tag);for(const[k,v] of Object.entries(attrs||{})){if(v==null||v===false)continue;if(k==='class')e.className=v;else if(k==='text')e.textContent=v;else if(k.startsWith('on'))e.addEventListener(k.slice(2),v);else e.setAttribute(k,v===true?'':v)}for(const k of kids.flat(9)){if(k==null||k===false)continue;e.append(k instanceof Node?k:document.createTextNode(String(k)))}return e}
const main=document.getElementById('main');
function dur(s){if(s==null)return'–';s=Math.floor(s);const d=Math.floor(s/86400),g=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);if(d)return d+' d '+g+' h';if(g)return g+' h '+m+' min';if(m)return m+' min';return s+' s'}
function gb(b){return (b/1073741824).toFixed(1)}
function pct(a,b){return b?Math.round(a/b*100):0}
function bar(p){return h('div',{class:'bar'},h('i',{class:p>90?'b':p>75?'w':'',style:'width:'+Math.min(100,p)+'%'}))}
function chip(ok,txt,warn){return h('span',{class:'chip '+(ok?'ok':warn?'warn':'bad'),text:txt})}
function urlFor(port,path){return port===PORT?path:location.protocol+'//'+location.hostname+':'+port+path}
function copyable(t){if(!t)return'–';return h('span',{class:'copy m',title:'Kliknij, żeby skopiować',onclick:e=>{navigator.clipboard&&navigator.clipboard.writeText(t).then(()=>{e.target.textContent='skopiowano';setTimeout(()=>e.target.textContent=t,900)}).catch(()=>{})},text:t})}
function table(head,rows){return h('div',{class:'tbl'},h('table',null,h('thead',null,h('tr',null,head.map(x=>h('th',{text:x})))),h('tbody',null,rows)))}
async function getJSON(u){const r=await fetch(u,{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);return r.json()}
function setSub(s){document.getElementById('h-sub').textContent=s.model+' · '+s.system+' · działa od '+dur(s.uptime)}

/* ---------- START ---------- */
/* Minecraft włączany ręcznie: stan i przycisk Włącz/Wyłącz (POST /api/minecraft) */
let MC=null;
function mcKarta(){
  const box=h('section',{class:'zad',id:'mcKarta',style:'display:flex;align-items:center;gap:12px;flex-wrap:wrap'});
  mcRysuj(box);return box;
}
function mcRysuj(box){
  box=box||document.getElementById('mcKarta');if(!box)return;
  const m=MC;box.replaceChildren();
  if(!m){box.append(h('span',{text:'🎮 Minecraft: sprawdzam…'}));return}
  const opis=m.trwa==='start'?'włącza się (ok. 30 s)…':m.trwa==='stop'?'zapisuje świat i się wyłącza…':m.dziala?
    `działa${m.od?' od '+m.od.slice(11,16):''}${m.ram_mb?' · '+m.ram_mb+' MB RAM':''}${m.gracze!=null?' · gracze: '+m.gracze:''}`:
    (m.stan==='failed'?'wysypał się – włącz ponownie':'wyłączony (nie zajmuje RAM ani procesora)');
  box.append(h('div',{style:'flex:1;min-width:200px'},h('b',{text:'🎮 Minecraft '}),h('span',{class:'s',text:opis})));
  if(!m.trwa)box.append(h('button',{class:'btn',text:m.dziala?'⏹ Wyłącz':'▶ Włącz',onclick:async()=>{
    if(m.dziala&&m.gracze>0&&!confirm(`Grają ${m.gracze} osoby. Wyłączyć serwer?`))return;
    MC=Object.assign({},m,{trwa:m.dziala?'stop':'start'});mcRysuj();
    try{MC=await(await fetch('/api/minecraft',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({akcja:m.dziala?'stop':'start'})})).json()}catch(e){}
    mcRysuj();mcOdswiez();}}));
}
let mcT=0;
async function mcOdswiez(){clearTimeout(mcT);try{MC=await(await fetch('/api/minecraft',{cache:'no-store'})).json()}catch(e){}mcRysuj();mcT=setTimeout(mcOdswiez,MC&&MC.trwa?3000:15000)}
if(PAGE==='start')mcOdswiez();
function renderStart(d,zad,obc){
  const s=d.system;setSub(s);
  const ram=pct(s.ram_uzyte,s.ram_total),disk=pct(s.dysk_uzyte,s.dysk_total),cpu=s.cpu,t=s.temp;
  const tiles=h('div',{class:'tiles'},
    h('div',{class:'tile'},h('div',{class:'k',text:'Temperatura'}),h('div',{class:'v',text:t!=null?t.toFixed(1)+' °C':'–'}),h('div',{class:'d',text:t>75?'wysoka':t>65?'podwyższona':'w normie'}),bar(t?t/85*100:0)),
    h('div',{class:'tile'},h('div',{class:'k',text:'Procesor'}),h('div',{class:'v',text:cpu+' %'}),h('div',{class:'d',text:'obciążenie '+s.load.join(' / ')+' (1/5/15 min, '+s.rdzenie+' rdzenie)'}),bar(cpu)),
    h('div',{class:'tile'},h('div',{class:'k',text:'Pamięć RAM'}),h('div',{class:'v',text:gb(s.ram_uzyte)+' / '+gb(s.ram_total)+' GB'}),h('div',{class:'d',text:ram+' % użyte'+(s.swap_uzyte>0?', swap '+gb(s.swap_uzyte)+' GB':'')}),bar(ram)),
    h('div',{class:'tile'},h('div',{class:'k',text:'Karta SD'}),h('div',{class:'v',text:gb(s.dysk_uzyte)+' / '+gb(s.dysk_total)+' GB'}),h('div',{class:'d',text:disk+' % zajęte'}),bar(disk)),
    h('div',{class:'tile'},h('div',{class:'k',text:'Działa bez przerwy'}),h('div',{class:'v',text:dur(s.uptime)}),h('div',{class:'d',text:'jądro '+s.jadro}))
  );
  const alerts=[];
  if(s.nieudane_uslugi.length)alerts.push(h('div',{class:'err',text:'Usługi z błędem: '+s.nieudane_uslugi.join(', ')}));
  if(s.restart_wymagany)alerts.push(h('div',{class:'err',text:'Po aktualizacji systemu potrzebny jest restart Pi (zrób go, gdy nikt nie gra).'}));

  const cards=h('div',{class:'cards'},d.strony.map(p=>h('div',{class:'card'},
    h('div',{class:'top'},h('h3',{text:p.nazwa}),chip(p.dziala,p.dziala?'działa':'nie działa')),
    h('p',{text:p.opis}),
    h('div',{class:'m',style:'color:var(--muted)'},urlFor(p.port,p.sciezka).replace(location.protocol+'//','')),
    h('div',{class:'btns'},
      p.dziala?h('a',{class:'btn',href:urlFor(p.port,p.sciezka),text:'Otwórz'}):null,
      (p.dodatkowe||[]).map(x=>h('a',{class:'btn alt',href:urlFor(p.port,x.sciezka),text:x.nazwa})))
  )));

  const portsBy={};d.porty.forEach(g=>{if(g.usluga){(portsBy[g.usluga]=portsBy[g.usluga]||[]).push(g.port+'/'+g.proto)}});
  const groups={};d.uslugi.forEach(u=>{(groups[u.grupa]=groups[u.grupa]||[]).push(u)});
  const svc=[];
  Object.keys(groups).forEach(g=>{
    svc.push(h('div',{class:'grp',text:g+' · '+groups[g].length}));
    svc.push(table(['Program','Co robi','Działa od','RAM','Porty'],groups[g].map(u=>h('tr',null,
      h('td',{class:'m n',text:u.nazwa}),
      h('td',null,u.opis,u.opis_systemd&&u.opis_systemd!==u.opis?h('span',{class:'s',text:u.opis_systemd}):null),
      h('td',{class:'m n',text:dur(u.dziala_od_s)}),
      h('td',{class:'m n',text:u.ram_mb!=null?u.ram_mb+' MB':'–'}),
      h('td',{class:'m',text:[...new Set(portsBy[u.nazwa]||[])].join(', ')||'–'})))));
  });

  const procs=table(['Proces','Usługa','Użytkownik','CPU','RAM'],d.procesy.map(p=>h('tr',null,
    h('td',{class:'m',text:p.nazwa+' ('+p.pid+')'}),h('td',{class:'m',text:p.usluga||'–'}),h('td',{class:'m',text:p.uzytkownik}),
    h('td',{class:'m n',text:p.cpu!=null?p.cpu+' %':'mierzę…'}),h('td',{class:'m n',text:p.ram_mb+' MB'}))));

  const au=s.autoupdate;
  main.replaceChildren(
    h('section',null,tiles,...alerts),
    mcKarta(),
    zad&&window.Zadania||obc&&window.Obciazenie?h('section',{class:'zad-sek'},zad&&window.Zadania?h('div',{class:'zad'},Zadania.panel(zad)):null,obc&&window.Obciazenie?h('div',{class:'zad'},Obciazenie.panel(obc)):null):null,
    h('section',null,h('h2',{text:'Strony na tym serwerze'}),h('p',{class:'sec-note',text:'Wszystko, co Pi udostępnia w przeglądarce. Nową stronę dodasz, wrzucając folder z plikiem index.html do ~/portal/sites/.'}),cards),
    h('section',null,h('h2',{text:'Działające programy ('+d.uslugi.length+')'}),h('p',{class:'sec-note',text:'Wszystkie usługi systemd, które teraz działają, pogrupowane według przeznaczenia.'}),...svc),
    h('section',null,h('h2',{text:'Co teraz najbardziej obciąża Pi'}),h('p',{class:'sec-note',text:'CPU mierzone między kolejnymi odświeżeniami strony (100 % = jeden pełny rdzeń).'}),procs)
  );
  document.getElementById('foot').textContent='Auto-aktualizacja serwera MC: następna '+(au.nastepne||'–')+', ostatnia '+(au.ostatnie||'–')+'. Przez Tailscale bez hasła, z sieci domowej po zalogowaniu; odświeża się co 5 s.';
}

/* ---------- SIEC ---------- */
function stat(st){if(!st)return'–';if(st.ok)return h('span',null,chip(true,'działa · '+st.ms+' ms'),' ',h('span',{class:'s',text:(st.gracze!=null?'gracze '+st.gracze+'/'+st.max+' · ':'')+'wersja '+(st.wersja||'?')}));return h('span',null,chip(false,'brak odpowiedzi'),h('span',{class:'s',text:st.blad||''}))}
function renderSiec(n){
  const access=table(['Sposób','Adres','Opis'],n.dostep.map(a=>h('tr',null,h('td',{class:'n',text:a.nazwa}),h('td',null,copyable(a.adres)),h('td',{text:a.opis}))));
  const pub=n.publiczny;
  const pubT=table(['Adres publiczny','Wartość','Opis'],[
    h('tr',null,h('td',{class:'n',text:'IPv4 (wyjście do internetu)'}),h('td',null,copyable(pub.ipv4)),h('td',{text:'Adres, pod którym Pi widzą strony w internecie (adres routera lub operatora). Nie da się nim wejść na Pi z zewnątrz, bo operator nie daje publicznego IP. Dlatego Minecraft idzie przez tunel.'})),
    h('tr',null,h('td',{class:'n',text:'IPv6 (wyjście do internetu)'}),h('td',null,copyable(pub.ipv6)),h('td',{text:pub.ipv6?'Publiczny adres IPv6.':'Brak publicznego IPv6 w tej sieci.'}))]);
  const mc=table(['Dla kogo','Adres serwera Minecraft','Stan','Opis'],n.minecraft.map(m=>h('tr',null,h('td',{class:'n',text:m.gdzie}),h('td',null,copyable(m.adres)),h('td',null,stat(m.status)),h('td',{text:m.opis}))));
  const ifs=n.interfejsy.map(i=>h('div',{class:'iface'},
    h('div',{class:'grp',text:i.nazwa+' · '+(i.opis||'')+(i.mac?' · MAC '+i.mac:'')+' · '+i.stan}),
    table(['Adres','Rodzina','Co to jest'],i.adresy.map(a=>h('tr',null,h('td',null,copyable(a.adres+(a.prefiks!=null?'/'+a.prefiks:''))),h('td',{class:'m n',text:a.rodzina}),h('td',{text:a.opis}))))));
  const w=n.wifi||{};
  const misc=table(['Co','Wartość','Opis'],[
    ...n.bramki.map((b,i)=>h('tr',null,h('td',{class:'n',text:'Brama (router)'}),h('td',null,copyable(b.bramka)),h('td',{text:'przez '+b.interfejs+(i===0?' (używana)':' (zapasowa)')+', metryka '+b.metryka}))),
    ...n.dns.map(x=>h('tr',null,h('td',{class:'n',text:'Serwer DNS'}),h('td',null,copyable(x)),h('td',{text:x.startsWith('100.100.100.100')||x.startsWith('fd7a:115c:a1e0::53')?'DNS Tailscale (MagicDNS): rozwiązuje nazwy urządzeń i przekazuje resztę dalej.':'Serwer nazw'}))),
    w.ssid?h('tr',null,h('td',{class:'n',text:'Sieć WiFi'}),h('td',{class:'m',text:w.ssid}),h('td',{text:[w.sygnal&&'sygnał '+w.sygnal,w.czestotliwosc,w.predkosc].filter(Boolean).join(' · ')})):null]);
  const ts=n.tailscale;
  const peers=table(['Urządzenie','Adres Tailscale','System','Stan','Połączenie'],ts.urzadzenia.map(p=>h('tr',null,
    h('td',null,h('span',{class:'m',text:p.nazwa}),h('span',{class:'s',text:p.dns})),h('td',null,copyable((p.ip||[]).find(x=>x.includes('.'))||'')),h('td',{class:'m',text:p.system}),
    h('td',null,chip(p.online,p.online?'online':'offline',!p.online)),h('td',{class:'m',text:p.online?p.polaczenie:(p.ostatnio?'ostatnio '+p.ostatnio.replace('T',' ').slice(0,16):'')}))));
  const ports=table(['Port','Program','Usługa','Skąd dostępny','Opis'],n.porty.map(g=>h('tr',null,
    h('td',{class:'m n',text:g.port+'/'+g.proto}),h('td',{class:'m',text:g.program}),h('td',{class:'m',text:g.usluga||'–'}),
    h('td',null,h('span',{class:'chip '+(g.zasieg.startsWith('tylko ten')?'':g.zasieg.startsWith('tylko Tailscale')?'ok':'warn'),text:g.zasieg}),h('span',{class:'s m',text:g.adresy.join(' ')})),
    h('td',{text:g.opis}))));
  const smb=n.samba.length?table(['Udział','Adres w Windows','Folder na Pi','Zapis'],n.samba.map(s=>h('tr',null,h('td',{class:'m',text:s.nazwa}),h('td',null,copyable('\\\\'+(n.dostep[2].adres||'')+'\\'+(s.nazwa==='homes'?'tonyg':s.nazwa))),h('td',{class:'m',text:s.sciezka+(s.uzytkownicy?' (dla: '+s.uzytkownicy+')':'')}),h('td',null,chip(!s.zapis,s.zapis?'tak':'tylko odczyt',s.zapis))))):h('p',{class:'sec-note',text:'Brak udziałów Samba.'});
  main.replaceChildren(
    h('section',null,h('h2',{text:'Jak wejść na serwer'}),h('p',{class:'sec-note',text:'Kliknij adres, żeby go skopiować.'}),access),
    h('section',null,h('h2',{text:'Minecraft: adresy serwera'}),h('p',{class:'sec-note',text:'Stan sprawdzany tak jak robi to gra (zapytanie Bedrock), co 15 s lokalnie i co minutę przez tunel.'}),mc),
    h('section',null,h('h2',{text:'Internet'}),pubT),
    h('section',null,h('h2',{text:'Interfejsy sieciowe i wszystkie adresy'}),...ifs),
    h('section',null,h('h2',{text:'Router, DNS i WiFi'}),misc),
    h('section',null,h('h2',{text:'Urządzenia w Twojej sieci Tailscale'}),h('p',{class:'sec-note',text:'Ten serwer: '+ts.dns+' ('+ts.ip.join(', ')+'), Tailscale '+ts.wersja+'.'}),peers),
    h('section',null,h('h2',{text:'Otwarte porty'}),h('p',{class:'sec-note',text:'„LAN + Tailscale” oznacza dostęp z sieci domowej i z Tailscale. Z internetu nic nie jest otwarte poza Minecraftem przez tunel playit.'}),ports),
    h('section',null,h('h2',{text:'Udostępnione foldery (Samba)'}),smb)
  );
  setSubFromCache();
}
let lastSys=null;function setSubFromCache(){if(lastSys)setSub(lastSys)}

/* ---------- TERMINAL ---------- */
function loadAsset(tag,attrs){return new Promise((ok,bad)=>{const e=document.createElement(tag);Object.assign(e,attrs);e.onload=ok;e.onerror=()=>bad(new Error('nie udało się pobrać '+(attrs.src||attrs.href)));document.head.append(e)})}
function renderTerminal(){
  const direct=location.protocol+'//'+location.hostname+':'+TERMINAL_PORT+'/';
  const box=h('div',{class:'term',style:'padding:8px'});
  const status=h('span',{class:'chip',text:'łączenie…'});
  main.replaceChildren(h('section',null,
    h('p',{class:'sec-note',text:'Zaloguj się nazwą użytkownika (tonyg) i hasłem Linuksa. Każda karta to osobna sesja; zamknięcie karty lub przejście na inną stronę kończy sesję. Terminal działa tylko przez Tailscale.'}),
    box,
    h('div',{class:'btns'},status,h('a',{class:'btn alt',href:location.pathname,text:'Nowa sesja'}),h('a',{class:'btn alt',href:direct,target:'_blank',rel:'noopener',text:'Otwórz sam terminal w nowej karcie'}))));
  getJSON('/api/status?lekki=1').then(d=>{lastSys=d.system;setSub(d.system)}).catch(()=>{});
  const CDN='https://cdn.jsdelivr.net/npm/';
  Promise.all([loadAsset('link',{rel:'stylesheet',href:CDN+'@xterm/xterm@5.5.0/css/xterm.css'}),loadAsset('script',{src:CDN+'@xterm/xterm@5.5.0/lib/xterm.js'})])
  .then(()=>loadAsset('script',{src:CDN+'@xterm/addon-fit@0.10.0/lib/addon-fit.js'}))
  .then(()=>{
    const term=new Terminal({cursorBlink:true,fontSize:15,scrollback:5000,fontFamily:'"IBM Plex Mono","Cascadia Mono",Consolas,ui-monospace,monospace',
      theme:{background:'#0f1519',foreground:'#d7e0e6',cursor:'#5fd1a5',selectionBackground:'#2c4a55'}});
    const fit=new FitAddon.FitAddon();term.loadAddon(fit);term.open(box);fit.fit();
    const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.hostname+':'+TERMINAL_PORT+'/ws');
    ws.binaryType='arraybuffer';
    const send=o=>{if(ws.readyState===1)ws.send(JSON.stringify(o))};
    let opened=false;
    ws.onopen=()=>{opened=true;status.className='chip ok';status.textContent='połączono';send({t:'r',c:term.cols,r:term.rows});term.focus()};
    ws.onmessage=e=>term.write(typeof e.data==='string'?e.data:new Uint8Array(e.data));
    ws.onclose=()=>{
      status.className='chip bad';
      if(!opened){status.textContent='brak połączenia';box.replaceChildren(h('div',{class:'err'},'Ta przeglądarka nie pozwoliła połączyć się z terminalem na porcie '+TERMINAL_PORT+'. ',h('a',{href:direct,text:'Otwórz terminal bezpośrednio'}),' (to ta sama usługa, logowanie tak samo).'));return}
      status.textContent='sesja zakończona';term.write('\r\n\x1b[33m[Sesja zakończona. Kliknij „Nowa sesja”, żeby zalogować się ponownie.]\x1b[0m\r\n')};
    term.onData(d=>send({t:'i',d}));
    term.onResize(s=>send({t:'r',c:s.cols,r:s.rows}));
    addEventListener('resize',()=>fit.fit());
  })
  .catch(e=>{status.className='chip bad';status.textContent='błąd';box.replaceChildren(h('div',{class:'err',text:'Nie udało się uruchomić terminala: '+e.message+'. Przeglądarka musi mieć dostęp do internetu (cdn.jsdelivr.net).'}))});
}

async function tick(){
  try{
    if(PAGE==='start'){const [d,zad,obc]=await Promise.all([getJSON('/api/status'),getJSON('/api/zadania').catch(()=>null),getJSON('/api/obciazenie').catch(()=>null)]);renderStart(d,zad,obc)}
    else if(PAGE==='siec'){const [n,s]=await Promise.all([getJSON('/api/siec'),getJSON('/api/status?lekki=1')]);lastSys=s.system;renderSiec(n)}
  }catch(e){main.replaceChildren(h('div',{class:'err',text:'Nie udało się pobrać danych z serwera ('+e.message+'). Ponawiam…'}))}
}
if(PAGE==='terminal')renderTerminal();else{tick();setInterval(tick,PAGE==='start'?5000:15000)}
</script></body></html>"""

TITLES = {"start": "Serwerek domowy", "siec": "Sieć i adresy · serwerek", "terminal": "Terminal · serwerek"}


def page(name):
    html = (PAGE.replace("%%TITLE%%", TITLES[name]).replace("%%PAGE%%", name)
            .replace("%%PORT%%", str(PORT)).replace("%%TPORT%%", str(TERMINAL_PORT)))
    return Response(html, mimetype="text/html")


@app.after_request
def no_cache(resp):
    if resp.mimetype in ("application/json", "text/html"):
        resp.headers["Cache-Control"] = "no-store"
    elif resp.mimetype in ("text/javascript", "application/javascript", "text/css") and "Cache-Control" not in resp.headers:
        # skrypty stron: przegladarka zawsze pyta o nowsza wersje (iPad trzymal stare app.js po aktualizacji)
        resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return wstaw_diode(resp)


DIODA_TAG = b'<script src="/strony/zdrowie/dioda.js" defer></script>'


def wstaw_diode(resp):
    """dioda stanu serwera na kazdej stronie HTML (portal i /strony/*): skrypt doklejany przed </body>"""
    from flask import request
    if resp.mimetype != "text/html" or resp.status_code != 200 or request.path.startswith("/api/") or request.path == "/logowanie":
        return resp
    resp.direct_passthrough = False
    body = resp.get_data()
    if DIODA_TAG not in body and b"</body>" in body:
        i = body.rfind(b"</body>")
        resp.set_data(body[:i] + DIODA_TAG + body[i:])
    return resp


# ---------- Dostep z sieci domowej: haslo + ciasteczko (Tailscale i samo Pi bez hasla) ----------
# dane/dostep.json (600, tylko na Pi): {"hash": skrot hasla (werkzeug, scrypt), "klucz": klucz podpisu ciasteczek,
# "wersja": n}. Zmiana hasla (komenda portal-haslo) podbija wersje, co wylogowuje wszystkie urzadzenia.
# Ciasteczko „portal_sesja”: podpisane, HttpOnly, SameSite=Lax, wazne rok. Po 5 zlych haslach z jednego adresu: 5 min blokady.
import ipaddress

DOSTEP = BASE / "dane" / "dostep.json"
SESJA = "portal_sesja"
SESJA_DNI = 365
ZAUFANE_SIECI = [ipaddress.ip_network(n) for n in ("100.64.0.0/10", "fd7a:115c:a1e0::/48", "127.0.0.0/8", "::1/128")]
LOGOWANIE_PROBY = {}
LOGOWANIE_LOCK = threading.Lock()
WEJSCIA = BASE / "dane" / "wejscia.jsonl"      # dla bota Telegram: kazde zapytanie z sieci domowej i logowania


def wejscie_zapisz(rodzaj, **dane):
    from flask import request
    rek = {"czas": time.strftime("%Y-%m-%dT%H:%M:%S"), "rodzaj": rodzaj, "ip": request.remote_addr,
           "ua": (request.user_agent.string or "")[:200], **dane}
    try:
        with open(WEJSCIA, "a", encoding="utf-8") as f:
            f.write(json.dumps(rek, ensure_ascii=False) + "\n")
    except OSError:
        pass


def dostep_dane():
    return cached("dostep", 5, lambda: json.loads(DOSTEP.read_text(encoding="utf-8")) if DOSTEP.exists() else None)


def przez_tailscale():
    """Tailscale (100.64.0.0/10; nftables Tailscale odrzuca takie adresy spoza tailscale0) albo samo Pi"""
    from flask import request
    try:
        ip = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        return False
    return any(ip in n for n in ZAUFANE_SIECI)


def sesja_podpis():
    from itsdangerous import URLSafeTimedSerializer
    d = dostep_dane()
    return URLSafeTimedSerializer(d["klucz"], salt="portal-sesja") if d else None


def zalogowany():
    from flask import request
    from itsdangerous import BadData
    s, d = sesja_podpis(), dostep_dane()
    tok = request.cookies.get(SESJA)
    if not (s and tok):
        return False
    try:
        return s.loads(tok, max_age=SESJA_DNI * 86400).get("w") == d.get("wersja", 1)
    except BadData:
        return False


@app.before_request
def wymagaj_hasla():
    from flask import request
    if przez_tailscale():
        return None
    if request.path in ("/logowanie", "/wyloguj") or zalogowany():
        return None
    if request.path.startswith("/api/"):
        return jsonify({"blad": "zaloguj się", "logowanie": "/logowanie"}), 401
    if request.method != "GET":
        abort(401)
    nast = request.full_path.rstrip("?") if request.query_string else request.path
    from urllib.parse import quote
    return redirect("/logowanie?nast=" + quote(nast, safe="/"))


LOGOWANIE_HTML = """<!doctype html><html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Serwerek: logowanie</title>
<style>
:root{--bg:#EEF1EF;--card:#FAFBFA;--ink:#17201C;--muted:#5B6862;--line:#D0D8D3;--acc:#1f7a4d;--accInk:#fff;--bad:#b42335;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#0E1412;--card:#151D1A;--ink:#E2EAE6;--muted:#93A39B;--line:#26322D;--acc:#3fae74;--accInk:#06140c;--bad:#ef6b7b;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:var(--bg);color:var(--ink);
  font:17px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;padding:16px}
form{width:100%;max-width:380px;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:24px 22px}
h1{margin:0 0 4px;font-size:26px} p{margin:0 0 18px;color:var(--muted);font-size:15px}
label{display:block;font-weight:600;margin-bottom:6px}
input{width:100%;font:inherit;font-size:18px;padding:11px 12px;border:1.5px solid var(--line);border-radius:10px;background:var(--bg);color:var(--ink)}
input:focus{outline:3px solid color-mix(in srgb,var(--acc) 45%,transparent);border-color:var(--acc)}
button{width:100%;margin-top:14px;font:inherit;font-weight:700;padding:12px;border:0;border-radius:10px;background:var(--acc);color:var(--accInk);cursor:pointer}
.err{color:var(--bad);font-weight:600;margin:12px 0 0}
small{display:block;margin-top:14px;color:var(--muted);font-size:13.5px}
.pole{position:relative} .pole input{padding-right:84px}
#pokaz{position:absolute;right:6px;top:50%;transform:translateY(-50%);width:auto;margin:0;padding:6px 12px;font-size:15px;
  background:transparent;color:var(--acc);border:1.5px solid var(--line);border-radius:8px}
</style></head><body>
<form method="post" action="/logowanie">
  <h1>Serwerek domowy</h1>
  <p>Wejście z sieci domowej. Hasło wpisujesz raz: to urządzenie zostanie zapamiętane na rok.</p>
  <input type="hidden" name="nast" value="%%NAST%%">
  <input type="text" name="username" value="serwerek" autocomplete="username" hidden>
  <label for="h">Hasło</label>
  <div class="pole"><input id="h" name="haslo" type="password" autocomplete="current-password" autocapitalize="off" autocorrect="off" spellcheck="false" autofocus required>
    <button type="button" id="pokaz" aria-controls="h" aria-pressed="false">Pokaż</button></div>
  <button type="submit">Wejdź</button>
  %%BLAD%%
  <small>Przez Tailscale hasło nie jest potrzebne.</small>
</form>
<script>
const h = document.getElementById("h"), b = document.getElementById("pokaz");
b.onclick = () => { const p = h.type === "password"; h.type = p ? "text" : "password"; b.textContent = p ? "Ukryj" : "Pokaż";
  b.setAttribute("aria-pressed", p); h.focus(); };
</script></body></html>"""


def logowanie_strona(blad="", nast="/", kod=200):
    from html import escape
    html = LOGOWANIE_HTML.replace("%%NAST%%", escape(nast)).replace("%%BLAD%%", f'<p class="err">{escape(blad)}</p>' if blad else "")
    return Response(html, status=kod, mimetype="text/html")


def nast_ok(n):
    return n if isinstance(n, str) and n.startswith("/") and not n.startswith("//") and "\\" not in n and n != "/logowanie" else "/"


@app.route("/logowanie", methods=["GET", "POST"])
def logowanie():
    from flask import request
    from werkzeug.security import check_password_hash
    nast = nast_ok(request.values.get("nast"))
    if przez_tailscale() or (request.method == "GET" and zalogowany()):
        return redirect(nast)
    d = dostep_dane()
    if d is None:
        return logowanie_strona("Hasło nie jest jeszcze ustawione (komenda portal-haslo na Pi).", nast, 503)
    if request.method == "GET":
        wejscie_zapisz("panel_logowania")
        return logowanie_strona(nast=nast)
    ip, teraz = request.remote_addr or "?", time.time()
    with LOGOWANIE_LOCK:
        proby = [t for t in LOGOWANIE_PROBY.get(ip, []) if t > teraz - 300]
        LOGOWANIE_PROBY[ip] = proby
        if len(proby) >= 5:
            if not LOGOWANIE_PROBY.get(ip + ":zgloszone"):
                LOGOWANIE_PROBY[ip + ":zgloszone"] = [teraz]
                wejscie_zapisz("blokada")
            return logowanie_strona(f"Za dużo złych haseł. Spróbuj za {int(300 - (teraz - proby[0])) // 60 + 1} min.", nast, 429)
    import unicodedata
    surowe = request.form.get("haslo", "")
    haslo = unicodedata.normalize("NFKC", surowe).strip()      # spacja na koncu, znaki z klawiatury iOS
    if not (0 < len(haslo) <= 200 and check_password_hash(d["hash"], haslo)):
        with LOGOWANIE_LOCK:
            LOGOWANIE_PROBY.setdefault(ip, []).append(teraz)
            LOGOWANIE_PROBY.pop(ip + ":zgloszone", None)
            wejscie_zapisz("zle_haslo", proba=len(LOGOWANIE_PROBY[ip]))
        # podpowiedz do dziennika bez zapisywania hasla: dlugosc i czy pasowaloby z inna wielkoscia liter
        wl = next((n for n, w in (("odwrocona wielkosc liter", haslo.swapcase()), ("pierwsza litera mala", haslo[:1].lower() + haslo[1:]),
                                  ("pierwsza litera wielka", haslo[:1].upper() + haslo[1:])) if w != haslo and check_password_hash(d["hash"], w)), "")
        try:
            zdrowie_log(f"LOGOWANIE zle haslo z {ip} (dlugosc {len(surowe)}{', pasowaloby: ' + wl if wl else ''})")
        except OSError:
            pass
        time.sleep(1)
        return logowanie_strona("Złe hasło.", nast, 401)
    with LOGOWANIE_LOCK:
        LOGOWANIE_PROBY.pop(ip, None)
    wejscie_zapisz("logowanie_ok")
    try:
        zdrowie_log(f"LOGOWANIE ok z {ip} ({(request.user_agent.string or '')[:80]})")
    except OSError:
        pass
    resp = redirect(nast)
    resp.set_cookie(SESJA, sesja_podpis().dumps({"w": d.get("wersja", 1)}), max_age=SESJA_DNI * 86400,
                    httponly=True, samesite="Lax", path="/")
    return resp


@app.after_request
def wejscia_sciezka(resp):
    """kazde zapytanie (sciezka, metoda, wynik) do sladu wizyt w bocie Telegram; z Tailscale tylko zapis, bez powiadomien"""
    from flask import request
    if not (request.remote_addr or "").startswith("127."):      # bot i skrypty na samym Pi pomijamy
        ts = przez_tailscale()
        wejscie_zapisz("zapytanie", metoda=request.method, sciezka=request.full_path.rstrip("?")[:200], wynik=resp.status_code,
                       zalogowany=ts or zalogowany() or SESJA in resp.headers.get("Set-Cookie", ""), tailscale=ts)
    return resp


@app.route("/wyloguj")
def wyloguj():
    resp = redirect("/logowanie")
    resp.delete_cookie(SESJA, path="/")
    return resp


@app.route("/api/dostep")
def api_dostep():
    return jsonify({"siec": "tailscale" if przez_tailscale() else "domowa"})


@app.route("/")
def start():
    return page("start")


@app.route("/siec")
def siec():
    return page("siec")


@app.route("/terminal")
def terminal():
    if not przez_tailscale():
        return Response('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                        '<title>Terminal</title><body style="font:17px system-ui;padding:24px;max-width:520px;margin:auto">'
                        '<h1>Terminal tylko przez Tailscale</h1><p>Ze względów bezpieczeństwa terminal nie działa z sieci domowej. '
                        'Włącz Tailscale na tym urządzeniu i wejdź na <b>http://100.108.241.58/terminal</b>.</p>'
                        '<p><a href="/">← Strona główna</a></p></body>', mimetype="text/html")
    return page("terminal")


@app.route("/api/status")
def api_status():
    from flask import request
    s = cached("system", 2, system_info)
    if request.args.get("lekki"):
        return jsonify({"system": s})
    ports = cached("porty", 10, listening)
    return jsonify({
        "system": s,
        "uslugi": cached("uslugi", 5, services),
        "porty": ports,
        "strony": cached("strony", 10, lambda: web_pages(ports)),
        "procesy": cached("procesy", 4, top_processes),
    })


@app.route("/api/siec")
def api_siec():
    return jsonify(cached("siec", 10, network))


# ---------- Minecraft włączany ręcznie (komenda /usr/local/bin/minecraft, przycisk na stronie głównej i w bocie) ----------
MC_STAN = {"trwa": None}


def mc_stan():
    st = usluga_stan("powernukkitx")
    d = {"dziala": st.get("ActiveState") == "active", "stan": st.get("ActiveState"), "trwa": MC_STAN["trwa"]}
    if d["dziala"]:
        pid = sh(["systemctl", "show", "-p", "MainPID", "--value", "powernukkitx"]).strip()
        m = re.search(r"VmRSS:\s+(\d+)", read(f"/proc/{pid}/status"))
        d["ram_mb"] = int(m.group(1)) // 1024 if m else None
        m = re.search(r"@(\d+)", sh(["systemctl", "show", "--timestamp=unix", "-p", "ActiveEnterTimestamp", "--value", "powernukkitx"]))
        d["od"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(int(m.group(1)))) if m else None
        try:
            mc = next((x for x in cached("siec", 10, network)["minecraft"] if x.get("status")), None)
            d["gracze"] = (mc or {}).get("status", {}).get("gracze")
        except Exception:
            d["gracze"] = None
    return d


@app.route("/api/minecraft", methods=["GET", "POST"])
def api_minecraft():
    from flask import request
    if request.method == "POST":
        b = request.get_json(silent=True) or {}
        akcja = b.get("akcja")
        if akcja not in ("start", "stop"):
            abort(400)
        if MC_STAN["trwa"]:
            return jsonify(mc_stan()), 409

        def wykonaj():
            MC_STAN["trwa"] = akcja
            try:
                subprocess.run(["sudo", "/usr/local/bin/minecraft", akcja], capture_output=True, timeout=240)
            finally:
                MC_STAN["trwa"] = None
        threading.Thread(target=wykonaj, daemon=True).start()
        time.sleep(0.3)
    return jsonify(mc_stan())


# ---------- Zadania (todo) z przypomnieniami: strona /strony/todo/ i bot Telegram ----------
# dane/todo.json: [{id, tekst, termin "RRRR-MM-DDTHH:MM" albo null, powtarzaj null|dzien|tydzien|miesiac, zrobione iso|null,
#   utworzono, wyslano iso|null (przypomnienie dla obecnego terminu juz poszlo), dzwon (bot dodatkowo dzwoni przez Linphone)}].
#   Przypomnienia wysyla bot (co 30 s).
TODO = BASE / "dane" / "todo.json"
TODO_LOCK = threading.Lock()
TODO_POWT = (None, "dzien", "tydzien", "miesiac")


def todo_lista():
    try:
        return json.loads(TODO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def todo_termin_ok(v):
    if v is None:
        return True
    try:
        time.strptime(v, "%Y-%m-%dT%H:%M")
        return True
    except (TypeError, ValueError):
        return False


def todo_nastepny(termin, powt):
    """kolejny termin zadania powtarzanego"""
    from datetime import datetime, timedelta
    t = datetime.strptime(termin, "%Y-%m-%dT%H:%M")
    if powt == "dzien":
        t += timedelta(days=1)
    elif powt == "tydzien":
        t += timedelta(days=7)
    elif powt == "miesiac":
        import calendar
        r, m = (t.year + 1, 1) if t.month == 12 else (t.year, t.month + 1)
        t = t.replace(year=r, month=m, day=min(t.day, calendar.monthrange(r, m)[1]))
    return t.strftime("%Y-%m-%dT%H:%M")


@app.route("/api/todo", methods=["GET", "POST"])
def api_todo():
    from flask import request
    if request.method == "GET":
        return jsonify({"zadania": todo_lista()})
    b = request.get_json(silent=True)
    if not isinstance(b, dict) or not isinstance(b.get("tekst"), str) or not 0 < len(b["tekst"].strip()) <= 500:
        abort(400)
    if not todo_termin_ok(b.get("termin")) or b.get("powtarzaj") not in TODO_POWT or (b.get("powtarzaj") and not b.get("termin")):
        abort(400)
    z = {"id": uuid_hex()[:12], "tekst": b["tekst"].strip(), "termin": b.get("termin"), "powtarzaj": b.get("powtarzaj"),
         "zrobione": None, "utworzono": time.strftime("%Y-%m-%dT%H:%M:%S"), "wyslano": None, "dzwon": b.get("dzwon") is True}
    with TODO_LOCK:
        lista = todo_lista()
        lista.append(z)
        zapisz_json(TODO, lista)
    return jsonify(z)


@app.route("/api/todo/<zid>", methods=["POST"])
def api_todo_zmien(zid):
    from flask import request
    b = request.get_json(silent=True)
    if not isinstance(b, dict):
        abort(400)
    with TODO_LOCK:
        lista = todo_lista()
        z = next((x for x in lista if x["id"] == zid), None)
        if z is None:
            abort(404)
        if b.get("usun") is True:
            lista.remove(z)
            zapisz_json(TODO, lista)
            return jsonify({"ok": True})
        if "tekst" in b:
            if not isinstance(b["tekst"], str) or not 0 < len(b["tekst"].strip()) <= 500:
                abort(400)
            z["tekst"] = b["tekst"].strip()
        if "termin" in b:
            if not todo_termin_ok(b["termin"]):
                abort(400)
            z["termin"], z["wyslano"] = b["termin"], None
        if "dzwon" in b:
            z["dzwon"] = b["dzwon"] is True
        if "powtarzaj" in b:
            if b["powtarzaj"] not in TODO_POWT:
                abort(400)
            z["powtarzaj"] = b["powtarzaj"]
        if b.get("odloz_min"):
            from datetime import datetime, timedelta
            minuty = int(b["odloz_min"])
            if not 0 < minuty <= 60 * 24 * 30:
                abort(400)
            z["termin"], z["wyslano"] = (datetime.now() + timedelta(minutes=minuty)).strftime("%Y-%m-%dT%H:%M"), None
        if "wyslano" in b:
            z["wyslano"] = time.strftime("%Y-%m-%dT%H:%M:%S") if b["wyslano"] else None
        if "zrobione" in b:
            if b["zrobione"] and z.get("powtarzaj") and z.get("termin"):
                z["termin"], z["wyslano"] = todo_nastepny(z["termin"], z["powtarzaj"]), None      # powtarzane: przesun termin
                z["ostatnio_zrobione"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            else:
                z["zrobione"] = time.strftime("%Y-%m-%dT%H:%M:%S") if b["zrobione"] else None
        if z.get("powtarzaj") and not z.get("termin"):
            z["powtarzaj"] = None
        zapisz_json(TODO, lista)
    return jsonify(z)


@app.route("/strony/<site>")
def site_root_redirect(site):
    return redirect(f"/strony/{site}/")


@app.route("/strony/<site>/", defaults={"path": "index.html"})
@app.route("/strony/<site>/<path:path>")
def site_files(site, path):
    if not re.fullmatch(r"[a-z0-9_-]+", site) or not (SITES / site).is_dir():
        abort(404)
    if path.endswith("/") or (SITES / site / path).is_dir():
        if not path.endswith("/"):
            return redirect(f"/strony/{site}/{path}/")
        path += "index.html"
    return send_from_directory(SITES / site, path)


# ---------- Nauka: postepy (fiszki, quizy) i zmiana daty sprawdzianu ----------
# Postepy: dane/nauka/<id>.json (poza sites/, wspolne dla wszystkich urzadzen).
# Spis sprawdzianow: sites/nauka/sprawdziany.json (zmiana daty zapisuje go w miejscu).
NAUKA = SITES / "nauka"
NAUKA_DANE = BASE / "dane" / "nauka"
NAUKA_LOCK = threading.Lock()
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # zdjecia w /api/progres; reszta API ma limit 64 KB ponizej


@app.before_request
def limit_malych_zapytan():
    from flask import request
    if request.path.startswith("/api/") and not request.path.startswith("/api/progres/"):
        if (request.content_length or 0) > 64 * 1024:
            abort(413)


def zapisz_json(path, obj, indent=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=indent) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def nauka_spis():
    return json.loads((NAUKA / "sprawdziany.json").read_text(encoding="utf-8"))


def nauka_id_ok(nid):
    return bool(re.fullmatch(r"[a-z0-9_-]{1,80}", nid)) and any(x.get("id") == nid for x in nauka_spis())


def nauka_postep(nid):
    try:
        d = json.loads((NAUKA_DANE / f"{nid}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    for k, v in (("fiszki", {}), ("quizy", []), ("bledne", {}), ("ile", {})):
        d.setdefault(k, v)
    return d


@app.route("/api/nauka/postep")
def api_nauka_postep_wszystkie():
    return jsonify({p.stem: nauka_postep(p.stem) for p in NAUKA_DANE.glob("*.json")})


@app.route("/api/nauka/postep/<nid>", methods=["GET", "POST"])
def api_nauka_postep(nid):
    from flask import request
    if not nauka_id_ok(nid):
        abort(404)
    if request.method == "GET":
        return jsonify(nauka_postep(nid))
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(400)
    tekst = lambda v: isinstance(v, str) and 0 < len(v) <= 300
    liczba = lambda v: isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 10000
    op = body.get("op")
    with NAUKA_LOCK:
        d = nauka_postep(nid)
        if op == "fiszka":
            k = body.get("klucz")
            if not tekst(k) or not isinstance(body.get("umiem"), bool):
                abort(400)
            if k not in d["fiszki"] and len(d["fiszki"]) >= 3000:
                abort(400)
            d["fiszki"][k] = 1 if body["umiem"] else 0
        elif op == "zeruj_fiszki":
            d["fiszki"] = {}
        elif op == "quiz":
            w, bl, po = body.get("wynik"), body.get("bledne", []), body.get("poprawne", [])
            if not (isinstance(w, dict) and isinstance(w.get("filtr"), str) and len(w["filtr"]) <= 60
                    and liczba(w.get("dobre")) and liczba(w.get("wszystkie")) and w["dobre"] <= w["wszystkie"]):
                abort(400)
            if not (isinstance(bl, list) and isinstance(po, list) and len(bl) + len(po) <= 1000
                    and all(tekst(x) for x in bl + po)):
                abort(400)
            d["quizy"].append({"czas": time.strftime("%Y-%m-%dT%H:%M:%S"), "filtr": w["filtr"],
                               "dobre": w["dobre"], "wszystkie": w["wszystkie"]})
            d["quizy"] = d["quizy"][-300:]
            for x in po:
                d["bledne"].pop(x, None)
            for x in bl:
                d["bledne"][x] = d["bledne"].get(x, 0) + 1
        elif op == "ile":
            i = body.get("ile")
            if not (isinstance(i, dict) and all(k in ("fiszki", "quiz") and liczba(v) for k, v in i.items())):
                abort(400)
            d["ile"] = i
        else:
            abort(400)
        zapisz_json(NAUKA_DANE / f"{nid}.json", d)
    return jsonify(d)


@app.route("/api/nauka/data/<nid>", methods=["POST"])
def api_nauka_data(nid):
    from flask import request
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or "data" not in body:
        abort(400)
    data = body["data"]
    if data is not None:
        if not (isinstance(data, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", data)):
            abort(400)
        try:
            time.strptime(data, "%Y-%m-%d")
        except ValueError:
            abort(400)
    with NAUKA_LOCK:
        spis = nauka_spis()
        wpis = next((x for x in spis if x.get("id") == nid), None)
        if wpis is None:
            abort(404)
        wpis["data"] = data
        zapisz_json(NAUKA / "sprawdziany.json", spis, indent=2)
    return jsonify({"ok": True, "id": nid, "data": data})


@app.route("/api/nauka/wazne/<nid>", methods=["POST"])
def api_nauka_wazne(nid):
    from flask import request
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("wazne"), bool):
        abort(400)
    with NAUKA_LOCK:
        spis = nauka_spis()
        wpis = next((x for x in spis if x.get("id") == nid), None)
        if wpis is None:
            abort(404)
        if body["wazne"]:
            wpis["wazne"] = True
        else:
            wpis.pop("wazne", None)
        zapisz_json(NAUKA / "sprawdziany.json", spis, indent=2)
    return jsonify({"ok": True, "id": nid, "wazne": body["wazne"]})


NAUKA_USTAWIENIA = BASE / "dane" / "nauka-ustawienia.json"


@app.route("/api/nauka/ustawienia", methods=["GET", "POST"])
def api_nauka_ustawienia():
    from flask import request
    try:
        u = json.loads(NAUKA_USTAWIENIA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        u = {}
    if request.method == "GET":
        return jsonify(u)
    body = request.get_json(silent=True)
    if not (isinstance(body, dict) and body and all(k == "najpierw_wazne" and isinstance(v, bool) for k, v in body.items())):
        abort(400)
    with NAUKA_LOCK:
        u.update(body)
        zapisz_json(NAUKA_USTAWIENIA, u)
    return jsonify(u)


# ---------- NAS: zdjecia, filmy i logi od razu na NAS, Pi tylko jako bufor, gdy NAS niedostepny ----------
# /mnt/nas = //172.23.0.28/Tony-Folder (fstab + nas-montuj). Znacznik Raspberry/.nas odroznia zamontowany NAS
# od pustego katalogu na karcie. Sprawdzenie w osobnym watku z limitem czasu: zawieszony NAS nie blokuje portalu.
NAS = Path("/mnt/nas/Raspberry")
NAS_ZDJ, NAS_FILMY, NAS_LOGI = NAS / "Progres-zdjecia", NAS / "Progres-filmy", NAS / "Logi"
NAS_STAN = {"ok": False, "t": -1e9}
NAS_BUDZIK = threading.Event()


def nas_ok(ttl=15):
    if time.monotonic() - NAS_STAN["t"] < ttl:
        return NAS_STAN["ok"]
    wynik = []
    th = threading.Thread(target=lambda: wynik.append(os.path.ismount("/mnt/nas") and (NAS / ".nas").is_file()), daemon=True)
    th.start()
    th.join(5)
    NAS_STAN.update(ok=bool(wynik and wynik[0]), t=time.monotonic())
    return NAS_STAN["ok"]


def nas_blad():
    NAS_STAN.update(ok=False, t=time.monotonic())


def nas_zapisz(cel, dane=None, zrodlo=None):
    """zapis na NAS przez plik .tmp (przerwany zapis nie zostawia polowy pliku pod wlasciwa nazwa)"""
    cel.parent.mkdir(parents=True, exist_ok=True)
    tmp = cel.with_name(cel.name + ".tmp")
    try:
        if zrodlo is not None:
            shutil.copyfile(zrodlo, tmp)
        else:
            tmp.write_bytes(dane)
        os.replace(tmp, cel)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def nas_przenies(zrodlo, cel):
    nas_zapisz(cel, zrodlo=zrodlo)


# ---------- Zawodowe: program od nauczyciela (ASTORINO Web Lab) prosto z NAS ----------
# Nowa wersja: wrzucic plik .html (dowolna nazwa) do Tony-Folder/Raspberry/Zawodowe/ i usunac stary. Strona pokazuje
# najnowszy plik .html z tego folderu i trzyma jego kopie w sites/zawodowe/index.html (dziala tez bez NAS).
ZAWODOWE_NAS = NAS / "Zawodowe"
ZAWODOWE = SITES / "zawodowe"


def zawodowe_odswiez():
    if not nas_ok():
        return
    try:
        pliki = [p for p in ZAWODOWE_NAS.glob("*.htm*") if p.is_file() and not p.name.startswith(".")]
        if not pliki:
            return
        naj = max(pliki, key=lambda p: p.stat().st_mtime)
        st = naj.stat()
        podpis = f"{naj.name}|{st.st_size}|{int(st.st_mtime)}"
        znacznik = ZAWODOWE / "zrodlo.txt"
        if read(znacznik).strip() == podpis and (ZAWODOWE / "index.html").is_file():
            return
        ZAWODOWE.mkdir(exist_ok=True)
        tmp = ZAWODOWE / "index.html.tmp"
        shutil.copyfile(naj, tmp)
        os.replace(tmp, ZAWODOWE / "index.html")
        znacznik.write_text(podpis + "\n", encoding="utf-8")
    except OSError:
        nas_blad()


@app.route("/strony/zawodowe/")
def zawodowe():
    zawodowe_odswiez()
    if not (ZAWODOWE / "index.html").is_file():
        return Response("Brak programu: wrzuć plik .html do Tony-Folder/Raspberry/Zawodowe na NAS.", 404,
                        mimetype="text/plain; charset=utf-8")
    return send_from_directory(ZAWODOWE, "index.html", max_age=0)
    zrodlo.unlink()


# ---------- Progres: dziennik sylwetki (pomiary z wagi i zdjecia) ----------
# Dane: dane/progres/dane.json na Pi (kopia na NAS: Progres-zdjecia/dane.json). Zdjecia <id>.jpg i <id>_m.jpg
# (miniatura) od razu na NAS w Progres-zdjecia/; dane/progres/zdjecia/ to tylko bufor, gdy NAS niedostepny.
# Usuniete zdjecia trafiaja do Progres-zdjecia/Usuniete/ (albo dane/progres/kosz/ na Pi), nie sa kasowane.
PROGRES = BASE / "dane" / "progres"
PROGRES_ZDJ = PROGRES / "zdjecia"
PROGRES_LOCK = threading.Lock()
PROGRES_TYPY = ("przod", "bok", "biceps", "tyl", "tylbiceps", "inne")


def progres_dane():
    try:
        d = json.loads((PROGRES / "dane.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    for k, v in (("wpisy", {}), ("zdjecia", []), ("ustawienia", {})):
        d.setdefault(k, v)
    return d


def progres_data_ok(v):
    if not (isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v)):
        return False
    try:
        time.strptime(v, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def progres_lm_ok(lm):
    """33 punkty MediaPipe [x, y, widocznosc] (ulamki zdjecia) albo [] = sylwetki nie rozpoznano"""
    return lm is None or (isinstance(lm, list) and len(lm) in (0, 33) and all(
        isinstance(p, list) and len(p) == 3 and all(isinstance(v, (int, float)) and not isinstance(v, bool) and -5 <= v <= 5 for v in p)
        for p in lm))


def progres_pose_ok(p):
    return p is None or (isinstance(p, dict) and len(p) <= 8 and all(
        k in ("cx", "cy", "s", "ok") and (isinstance(v, (int, float)) and not isinstance(v, bool) and -10 <= v <= 10 or isinstance(v, bool))
        for k, v in p.items()))


def progres_reczne_ok(p):
    return p is None or (isinstance(p, dict) and all(
        k in ("dx", "dy", "z") and isinstance(v, (int, float)) and not isinstance(v, bool) and -10 <= v <= 10 for k, v in p.items()))


@app.route("/api/progres")
def api_progres():
    return jsonify(progres_dane())


@app.route("/api/progres/wpis", methods=["POST"])
def api_progres_wpis():
    from flask import request
    b = request.get_json(silent=True)
    if not isinstance(b, dict) or not progres_data_ok(b.get("data")):
        abort(400)
    wpis = {}
    for k, lo, hi in (("masa", 20, 400), ("fat", 0, 80), ("muscle", 0, 100)):
        v = b.get(k)
        if v is None:
            continue
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not lo <= v <= hi:
            abort(400)
        wpis[k] = round(float(v), 2)
    n = b.get("notatka")
    if n:
        if not isinstance(n, str) or len(n) > 1000:
            abort(400)
        wpis["notatka"] = n
    with PROGRES_LOCK:
        d = progres_dane()
        if wpis:
            d["wpisy"][b["data"]] = wpis
        else:
            d["wpisy"].pop(b["data"], None)
        zapisz_json(PROGRES / "dane.json", d)
    return jsonify(d)


@app.route("/api/progres/zdjecie", methods=["POST"])
def api_progres_zdjecie_nowe():
    from flask import request
    from PIL import Image
    import io
    import uuid
    f, m = request.files.get("plik"), request.files.get("miniatura")
    data, typ = request.form.get("data"), request.form.get("typ")
    if not f or not m or not progres_data_ok(data) or typ not in PROGRES_TYPY:
        abort(400)
    try:
        pose = json.loads(request.form.get("pose") or "null")
    except ValueError:
        abort(400)
    try:
        lm = json.loads(request.form.get("lm") or "null")
    except ValueError:
        abort(400)
    if not progres_pose_ok(pose) or not progres_lm_ok(lm):
        abort(400)
    duze, male = f.read(), m.read()
    if len(male) > 2 * 1024 * 1024:
        abort(413)
    try:
        with Image.open(io.BytesIO(duze)) as im:
            if im.format != "JPEG":
                abort(400)
            w, h = im.size
        with Image.open(io.BytesIO(male)) as im:
            if im.format != "JPEG":
                abort(400)
    except OSError:
        abort(400)
    zid = uuid.uuid4().hex
    progres_zapisz_zdjecie(f"{zid}.jpg", duze)
    progres_zapisz_zdjecie(f"{zid}_m.jpg", male)
    rec = {"id": zid, "data": data, "typ": typ, "w": w, "h": h, "dodano": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if pose:
        rec["pose"] = pose
    if lm is not None:
        rec["lm"] = lm
    with PROGRES_LOCK:
        d = progres_dane()
        d["zdjecia"].append(rec)
        zapisz_json(PROGRES / "dane.json", d)
    return jsonify(rec)


@app.route("/api/progres/zdjecie/<zid>", methods=["POST"])
def api_progres_zdjecie_zmien(zid):
    from flask import request
    if not re.fullmatch(r"[0-9a-f]{32}", zid):
        abort(404)
    b = request.get_json(silent=True)
    if not isinstance(b, dict):
        abort(400)
    with PROGRES_LOCK:
        d = progres_dane()
        rec = next((z for z in d["zdjecia"] if z["id"] == zid), None)
        if rec is None:
            abort(404)
        if b.get("usun") is True:
            for nazwa in (f"{zid}.jpg", f"{zid}_m.jpg"):
                if (PROGRES_ZDJ / nazwa).exists():
                    (PROGRES / "kosz").mkdir(parents=True, exist_ok=True)
                    os.replace(PROGRES_ZDJ / nazwa, PROGRES / "kosz" / nazwa)
                elif nas_ok():
                    try:
                        if (NAS_ZDJ / nazwa).exists():
                            (NAS_ZDJ / "Usuniete").mkdir(exist_ok=True)
                            os.replace(NAS_ZDJ / nazwa, NAS_ZDJ / "Usuniete" / nazwa)
                    except OSError:
                        nas_blad()      # zostanie na NAS bez wpisu w dane.json: nas_petla przeniesie go do Usuniete
            d["zdjecia"] = [z for z in d["zdjecia"] if z["id"] != zid]
        else:
            if "data" in b:
                if not progres_data_ok(b["data"]):
                    abort(400)
                rec["data"] = b["data"]
            if "typ" in b:
                if b["typ"] not in PROGRES_TYPY:
                    abort(400)
                rec["typ"] = b["typ"]
            if "lm" in b:
                if not progres_lm_ok(b["lm"]):
                    abort(400)
                if b["lm"] is None:
                    rec.pop("lm", None)
                else:
                    rec["lm"] = b["lm"]
            for k, ok in (("pose", progres_pose_ok), ("reczne", progres_reczne_ok)):
                if k in b:
                    if not ok(b[k]):
                        abort(400)
                    if b[k]:
                        rec[k] = b[k]
                    else:
                        rec.pop(k, None)
        zapisz_json(PROGRES / "dane.json", d)
    return jsonify(d)


def progres_zapisz_zdjecie(nazwa, dane):
    """na NAS; gdy sie nie da, na Pi (bufor) i od razu czerwona dioda"""
    if nas_ok():
        try:
            nas_zapisz(NAS_ZDJ / nazwa, dane)
            return
        except OSError:
            nas_blad()
    PROGRES_ZDJ.mkdir(parents=True, exist_ok=True)
    (PROGRES_ZDJ / nazwa).write_bytes(dane)
    ZDROWIE_BUDZIK.set()


def progres_gdzie(lokalny, na_nas, nazwa):
    """katalog, w ktorym jest plik: najpierw bufor na Pi, potem NAS"""
    if (lokalny / nazwa).is_file():
        return lokalny
    if nas_ok():
        try:
            if (na_nas / nazwa).is_file():
                return na_nas
        except OSError:
            nas_blad()
    return None


@app.route("/api/progres/plik/<nazwa>")
def api_progres_plik(nazwa):
    if not re.fullmatch(r"[0-9a-f]{32}(_m)?\.jpg", nazwa):
        abort(404)
    katalog = progres_gdzie(PROGRES_ZDJ, NAS_ZDJ, nazwa)
    if katalog is None:
        abort(503 if not nas_ok() else 404)
    resp = send_from_directory(katalog, nazwa, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return resp


@app.route("/api/progres/ustawienia", methods=["POST"])
def api_progres_ustawienia():
    from flask import request
    b = request.get_json(silent=True)
    if not isinstance(b, dict) or len(json.dumps(b)) > 4000:
        abort(400)
    with PROGRES_LOCK:
        d = progres_dane()
        d["ustawienia"].update(b)
        zapisz_json(PROGRES / "dane.json", d)
    return jsonify(d["ustawienia"])


# ---------- Progres: render filmu na Pi (kolejka, jeden film naraz, nice 15) ----------
# dane/progres/filmy/<id>.json (opis i stan), <id>.mp4 (gotowy film), <id>.postep (procent w trakcie)
PROGRES_FILMY = PROGRES / "filmy"
RENDER_SKRYPT = BASE / "progres_render.py"
RENDER_BUDZIK = threading.Event()
RENDER_FORMATY = {"4:5": (1080, 1350), "9:16": (1080, 1920), "1:1": (1080, 1080)}


def film_meta(fid):
    try:
        return json.loads((PROGRES_FILMY / f"{fid}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def film_zapisz(m):
    zapisz_json(PROGRES_FILMY / f"{m['id']}.json", m)


def render_petla():
    while True:
        oczekujace = sorted((m for m in (film_meta(p.stem) for p in PROGRES_FILMY.glob("*.json")) if m and m.get("status") == "oczekuje"),
                            key=lambda m: m["utworzono"])
        if not oczekujace:
            RENDER_BUDZIK.wait(600)
            RENDER_BUDZIK.clear()
            continue
        m = oczekujace[0]
        m["status"], m["start"] = "renderuje", time.strftime("%Y-%m-%dT%H:%M:%S")
        film_zapisz(m)
        d = progres_dane()
        zd = {z["id"]: z for z in d["zdjecia"]}
        kl = [{k: zd[i][k] for k in ("id", "w", "h", "data", "pose", "reczne") if k in zd[i]} for i in m["ids"] if i in zd]
        for z in kl:
            if z["id"] in (m.get("geo") or {}):
                z["geo"] = m["geo"][z["id"]]
        wej = PROGRES_FILMY / f"{m['id']}.wejscie.json"
        zapisz_json(wej, {"film": m["film"], "kl": kl, "wpisy": d["wpisy"], "katalogi": [str(PROGRES_ZDJ), str(NAS_ZDJ)]})
        tmp, post = PROGRES_FILMY / f"{m['id']}.tmp.mp4", PROGRES_FILMY / f"{m['id']}.postep"
        t0 = time.time()
        try:
            r = subprocess.run(["nice", "-n", "15", sys.executable, str(RENDER_SKRYPT), str(wej), str(tmp), str(post)],
                               capture_output=True, text=True, timeout=3 * 3600)
            ok, blad = r.returncode == 0 and tmp.exists(), (r.stderr or "")[-400:]
        except (OSError, subprocess.TimeoutExpired) as e:
            ok, blad = False, str(e)[-400:]
        m = film_meta(m["id"]) or m
        if ok:
            gotowy = PROGRES_FILMY / f"{m['id']}.mp4"
            os.replace(tmp, gotowy)
            m.update(status="gotowe", rozmiar=gotowy.stat().st_size, czas_renderu=round(time.time() - t0))
            if nas_ok():
                try:
                    nas_przenies(gotowy, NAS_FILMY / gotowy.name)
                except OSError:
                    nas_blad()
            if gotowy.exists():
                ZDROWIE_BUDZIK.set()
        else:
            m.update(status="blad", blad=blad or "nieznany blad")
            tmp.unlink(missing_ok=True)
        for p in (wej, post):
            p.unlink(missing_ok=True)
        film_zapisz(m)


def render_start():
    PROGRES_FILMY.mkdir(parents=True, exist_ok=True)
    for p in PROGRES_FILMY.glob("*.json"):            # przerwany restartem portalu: zrob jeszcze raz
        m = film_meta(p.stem)
        if m and m.get("status") == "renderuje":
            m["status"] = "oczekuje"
            film_zapisz(m)
    threading.Thread(target=render_petla, name="progres-render", daemon=True).start()


@app.route("/api/progres/render", methods=["POST"])
def api_progres_render():
    from flask import request
    import uuid
    b = request.get_json(silent=True)
    if not isinstance(b, dict) or not isinstance(b.get("film"), dict) or len(json.dumps(b["film"])) > 4000:
        abort(400)
    ids = b.get("ids")
    znane = {z["id"] for z in progres_dane()["zdjecia"]}
    if not (isinstance(ids, list) and 1 <= len(ids) <= 2000 and all(isinstance(i, str) and i in znane for i in ids)):
        abort(400)
    if b["film"].get("format", "4:5") not in RENDER_FORMATY:
        abort(400)
    geo = b.get("geo") or {}
    if not (isinstance(geo, dict) and all(k in ids and isinstance(v, list) and len(v) == 3 and all(
            isinstance(x, (int, float)) and not isinstance(x, bool) and abs(x) < 1e6 for x in v) for k, v in geo.items())):
        abort(400)
    opis = b.get("opis")
    m = {"id": uuid.uuid4().hex, "status": "oczekuje", "utworzono": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "film": b["film"], "ids": ids, "geo": geo, "opis": opis[:200] if isinstance(opis, str) else ""}
    film_zapisz(m)
    RENDER_BUDZIK.set()
    return jsonify(m)


@app.route("/api/progres/filmy")
def api_progres_filmy():
    lista = []
    for p in PROGRES_FILMY.glob("*.json"):
        if p.name.endswith(".wejscie.json"):
            continue
        m = film_meta(p.stem)
        if not m:
            continue
        if m.get("status") == "renderuje":
            try:
                m["postep"] = int((PROGRES_FILMY / f"{m['id']}.postep").read_text())
            except (OSError, ValueError):
                m["postep"] = 0
        m.pop("ids", None)
        m.pop("geo", None)
        lista.append(m)
    return jsonify(sorted(lista, key=lambda m: m["utworzono"], reverse=True))


@app.route("/api/progres/film/<nazwa>")
def api_progres_film_plik(nazwa):
    if not re.fullmatch(r"[0-9a-f]{32}\.mp4", nazwa):
        abort(404)
    katalog = progres_gdzie(PROGRES_FILMY, NAS_FILMY, nazwa)
    if katalog is None:
        abort(503 if not nas_ok() else 404)
    resp = send_from_directory(katalog, nazwa, mimetype="video/mp4", conditional=True)
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp


@app.route("/api/progres/film/<fid>", methods=["POST"])
def api_progres_film_zmien(fid):
    from flask import request
    if not re.fullmatch(r"[0-9a-f]{32}", fid):
        abort(404)
    b = request.get_json(silent=True)
    m = film_meta(fid)
    if m is None:
        abort(404)
    if not isinstance(b, dict) or b.get("usun") is not True:
        abort(400)
    if m.get("status") == "renderuje":
        abort(409)
    for nazwa in (f"{fid}.json", f"{fid}.mp4", f"{fid}.tmp.mp4", f"{fid}.postep", f"{fid}.wejscie.json"):
        (PROGRES_FILMY / nazwa).unlink(missing_ok=True)
    if nas_ok():
        try:
            (NAS_FILMY / f"{fid}.mp4").unlink(missing_ok=True)
        except OSError:
            nas_blad()
    return jsonify({"ok": True})


render_start()


# ---------- Zdrowie serwera: monitor co minute, aktywne problemy i dziennik zdarzen ----------
# dane/zdrowie/incydenty.json: kazdy problem {id, klucz, tytul, opis, poziom (warn/crit, najgorszy), od, do, wartosc,
#   przejrzane}; zakonczony problem czeka na „Przejrzane”, wiec nic nie znika bez sladu.
# dane/zdrowie/dziennik.log: kazda zmiana jako linia tekstu (start, pogorszenie, koniec).
# Oba pliki sa od razu kopiowane na NAS (Logi/zdrowie-dziennik.log, Logi/zdrowie-incydenty.json) przez nas_petla.
# Progi mozna nadpisac w config.json: {"zdrowie": {"temp": [70, 80], ...}}.
ZDROWIE = BASE / "dane" / "zdrowie"
ZDROWIE_LOCK = threading.Lock()
ZDROWIE_PROGI = {
    "temp": [70, 80],            # °C: zolta, czerwona
    "dysk": [80, 90],            # % zajetosci (karta SD, /boot/firmware)
    "ram": [85, 95],             # % uzycia (bez cache)
    "swap": [80, 95],            # % uzycia swap (zram)
    "cpu": [85, 95],             # % sredniego obciazenia: zolta po 10 min, czerwona po 30 min
    "cpu_min": [10, 30],
    "uslugi_kryt": ["playit", "tailscaled", "home-portal"],
    "uslugi_reczne": ["powernukkitx"],      # włączane ręcznie (minecraft start): wyłączone = OK, czerwona tylko po awarii
    "uslugi": ["pi-dashboard", "home-terminal", "smbd", "nmbd", "wayvnc", "ollama", "serwerek-bot", "serwerek-telefon"],
    "zadania": ["mc-autoupdate"],    # usluga uruchamiana timerem: ostatni przebieg zakonczony bledem -> zolta
}
ZDROWIE_STAN = {"sprawdzono": None, "pomiary": {}, "liczniki": {}, "cpu": [], "cpu_prev": None}
ZDROWIE_BUDZIK = threading.Event()      # pomiar od razu (np. zdjecie zapisane na Pi, bo NAS niedostepny)
KOPIA_STAN = Path("/var/lib/kopia-pi")  # stan nocnej kopii systemu (skrypt kopia-pi)


def zdrowie_progi():
    p = dict(ZDROWIE_PROGI)
    p.update((config().get("zdrowie") or {}))
    return p


def zdrowie_incydenty():
    try:
        return json.loads((ZDROWIE / "incydenty.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def zdrowie_log(linia):
    ZDROWIE.mkdir(parents=True, exist_ok=True)
    with open(ZDROWIE / "dziennik.log", "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + linia + "\n")
    NAS_BUDZIK.set()


def zdrowie_cpu():
    """wlasny pomiar CPU (nie miesza sie z pomiarem strony glownej)"""
    vals = [int(x) for x in read("/proc/stat").splitlines()[0].split()[1:]]
    cur = (vals[3] + vals[4], sum(vals))
    prev, ZDROWIE_STAN["cpu_prev"] = ZDROWIE_STAN["cpu_prev"], cur
    if not prev or cur[1] - prev[1] <= 0:
        return None
    return 100.0 * (1 - (cur[0] - prev[0]) / (cur[1] - prev[1]))


def usluga_stan(nazwa):
    out = sh(["systemctl", "show", "-p", "LoadState,ActiveState,SubState,Result", f"{nazwa}.service"])
    return dict(l.split("=", 1) for l in out.splitlines() if "=" in l)


def zdrowie_problemy(prog):
    """lista aktualnych problemow: (klucz, poziom, tytul, opis, wartosc)"""
    pr, pom = [], {}
    pz = lambda v, p: "crit" if v >= p[1] else "warn" if v >= p[0] else None
    try:
        t = int(read("/sys/class/thermal/thermal_zone0/temp", "0")) / 1000
        pom["temp"] = round(t, 1)
        if pz(t, prog["temp"]):
            pr.append(("temp", pz(t, prog["temp"]), "Wysoka temperatura procesora", f"{t:.1f} °C (progi {prog['temp'][0]}/{prog['temp'][1]} °C)", round(t, 1)))
    except ValueError:
        pass
    out = sh(["vcgencmd", "get_throttled"])
    m = re.search(r"0x([0-9a-fA-F]+)", out)
    if m:
        v = int(m.group(1), 16)
        pom["throttled"] = hex(v)
        if v & 0x1:
            pr.append(("napiecie", "crit", "Za niskie napięcie zasilania", "Zasilacz nie daje rady (ryzyko uszkodzenia karty SD). Sprawdź zasilacz i kabel.", 1))
        if v & 0x4:
            pr.append(("throttling", "crit", "Procesor zwolniony (throttling)", "Pi obniża taktowanie z powodu temperatury lub zasilania.", 1))
        elif v & 0x2 or v & 0x8:
            pr.append(("taktowanie", "warn", "Ograniczone taktowanie procesora", "Pi zbliża się do limitu temperatury.", 1))
        boot = read("/proc/sys/kernel/random/boot_id").strip()
        plik = ZDROWIE / "boot.json"
        try:
            zap = json.loads(plik.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            zap = {}
        znane = zap.get("bity", 0) if zap.get("boot") == boot else 0
        nowe = v & 0x50000 & ~znane          # „wystapilo od uruchomienia”: zapis jednorazowy na uruchomienie Pi
        if nowe:
            zapisz_json(plik, {"boot": boot, "bity": znane | nowe})
            opis = "za niskie napięcie" if nowe & 0x10000 else "zwolnienie procesora"
            pr.append(("historia_zasilania", "warn", "Od uruchomienia Pi wystąpiło: " + opis, "Problem minął, ale się zdarzył. Warto sprawdzić zasilacz.", 1, "jednorazowo"))
    for nazwa, sciezka in (("dysk", "/"), ("boot", "/boot/firmware")):
        try:
            du = shutil.disk_usage(sciezka)
        except OSError:
            continue
        proc = du.used / du.total * 100
        pom[nazwa] = round(proc, 1)
        if pz(proc, prog["dysk"]):
            pr.append((f"dysk:{sciezka}", pz(proc, prog["dysk"]), f"Mało miejsca: {sciezka}", f"Zajęte {proc:.0f}% (wolne {du.free / 1e9:.1f} GB)", round(proc, 1)))
    mi = meminfo()
    if mi.get("MemTotal"):
        ram = (mi["MemTotal"] - mi.get("MemAvailable", 0)) / mi["MemTotal"] * 100
        pom["ram"] = round(ram, 1)
        if pz(ram, prog["ram"]):
            pr.append(("ram", pz(ram, prog["ram"]), "Kończy się pamięć RAM", f"Użyte {ram:.0f}%", round(ram, 1)))
    if mi.get("SwapTotal"):
        sw = (mi["SwapTotal"] - mi.get("SwapFree", 0)) / mi["SwapTotal"] * 100
        pom["swap"] = round(sw, 1)
        if pz(sw, prog["swap"]):
            pr.append(("swap", pz(sw, prog["swap"]), "Pełny swap (pamięć zapasowa)", f"Użyte {sw:.0f}%", round(sw, 1)))
    c = zdrowie_cpu()
    if c is not None:
        teraz = time.time()
        ZDROWIE_STAN["cpu"] = [x for x in ZDROWIE_STAN["cpu"] if x[0] > teraz - 3600] + [(teraz, c)]
        def srednia(minuty):
            xs = [v for t_, v in ZDROWIE_STAN["cpu"] if t_ > teraz - minuty * 60]
            pelne = ZDROWIE_STAN["cpu"] and ZDROWIE_STAN["cpu"][0][0] <= teraz - minuty * 60 + 90
            return sum(xs) / len(xs) if xs and pelne else None
        s10, s30 = srednia(prog["cpu_min"][0]), srednia(prog["cpu_min"][1])
        pom["cpu"], pom["cpu10"], pom["cpu30"] = round(c, 1), s10 and round(s10, 1), s30 and round(s30, 1)
        if s30 is not None and s30 >= prog["cpu"][1]:
            pr.append(("cpu", "crit", "Procesor długo przeciążony", f"Średnio {s30:.0f}% przez {prog['cpu_min'][1]} min", round(s30, 1)))
        elif s10 is not None and s10 >= prog["cpu"][0]:
            pr.append(("cpu", "warn", "Procesor mocno obciążony", f"Średnio {s10:.0f}% przez {prog['cpu_min'][0]} min", round(s10, 1)))
    uslugi = {}
    for poziom, lista in (("crit", prog["uslugi_kryt"]), ("warn", prog["uslugi"])):
        for u in lista:
            st = usluga_stan(u)
            if st.get("LoadState") != "loaded":
                continue
            uslugi[u] = st.get("ActiveState")
            if st.get("ActiveState") != "active":
                opis = SERVICE_INFO.get(u, ("", u))[1]
                pr.append((f"usluga:{u}", poziom, f"Usługa nie działa: {u}", f"{opis}. Stan: {st.get('ActiveState')}/{st.get('SubState')}.", 1))
    for u in prog.get("uslugi_reczne", []):
        st = usluga_stan(u)
        if st.get("LoadState") != "loaded":
            continue
        uslugi[u] = st.get("ActiveState") if st.get("ActiveState") in ("active", "failed") else "recznie"
        if st.get("ActiveState") == "failed":
            pr.append((f"usluga:{u}", "crit", f"Usługa się wysypała: {u}", f"{SERVICE_INFO.get(u, ('', u))[1]}. Włącz ponownie: minecraft start.", 1))
    for u in prog["zadania"]:
        st = usluga_stan(u)
        if st.get("LoadState") == "loaded" and st.get("Result") not in (None, "", "success"):
            pr.append((f"zadanie:{u}", "warn", f"Zadanie zakończone błędem: {u}", f"Ostatni przebieg: {st.get('Result')}.", 1))
    for u in [l.split()[0] for l in sh(["systemctl", "--failed", "--no-legend", "--plain", "--no-pager"]).splitlines() if l.strip()]:
        nazwa = u.removesuffix(".service")
        if nazwa not in uslugi and nazwa not in prog["zadania"]:
            pr.append((f"failed:{u}", "warn", f"Jednostka systemd z błędem: {u}", "systemctl --failed", 1))
    nas = nas_ok(ttl=0)
    pom["nas"] = "ok" if nas else "brak"
    if not nas:
        pr.append(("nas", "crit", "NAS niedostępny", "Zdjęcia, filmy i logi zapisują się na Pi, nocna kopia systemu się nie zrobi. "
                   "Sprawdź, czy NAS (172.23.0.28) jest włączony.", 1))
    bufor = [p for p in list(PROGRES_ZDJ.glob("*.jpg")) + list(PROGRES_FILMY.glob("*.mp4")) if not p.name.endswith(".tmp.mp4")]
    pom["bufor"] = len(bufor)
    if bufor:
        pr.append(("nas_bufor", "crit", "Zdjęcia lub filmy tylko na Pi (nie ma ich na NAS)",
                   f"{len(bufor)} plików czeka na Pi. Przeniosą się same, gdy NAS będzie dostępny.", len(bufor), "natychmiast"))
    try:
        st = json.loads((KOPIA_STAN / "stan.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = None
    try:
        ok_ = json.loads((KOPIA_STAN / "ostatnia-udana.json").read_text(encoding="utf-8"))
        wiek = (time.time() - time.mktime(time.strptime(ok_["czas"], "%Y-%m-%dT%H:%M:%S"))) / 3600
        pom["kopia"] = ok_["czas"]
    except (OSError, ValueError, KeyError):
        wiek = None
    if st and st.get("wynik") == "blad":
        pr.append(("kopia", "crit", "Nocna kopia systemu nie udała się", f"Próba {st.get('start', '?')}. Szczegóły: NAS → Raspberry/Logi/kopia-systemu.log.", 1))
    elif st and (wiek is None or wiek > 26):
        poziom = "crit" if wiek is None or wiek > 50 else "warn"
        pr.append(("kopia_stara", poziom, "Dawno nie było kopii systemu",
                   f"Ostatnia udana: {pom.get('kopia', 'nigdy')}.", round(wiek or 0)))
    if Path("/var/run/reboot-required").exists():
        pr.append(("restart", "warn", "Potrzebny restart Pi", "Po aktualizacji systemu. Zrób go, gdy nikt nie gra.", 1))
    pom["uslugi"] = uslugi
    return pr, pom


def zdrowie_krok(teraz=None):
    """jeden przebieg monitora: problem zaczyna sie po 2 kolejnych wykryciach, konczy po 2 kolejnych brakach"""
    teraz = teraz or time.strftime("%Y-%m-%dT%H:%M:%S")
    prog = zdrowie_progi()
    problemy, pom = zdrowie_problemy(prog)
    with ZDROWIE_LOCK:
        inc = zdrowie_incydenty()
        aktywne = {i["klucz"]: i for i in inc if not i.get("do")}
        licz = ZDROWIE_STAN["liczniki"]
        for k in aktywne:                   # po restarcie portalu: aktywne problemy musza moc sie zakonczyc
            licz.setdefault(k, 2)
        widziane = set()
        for pr in problemy:
            klucz, poziom, tytul, opis, wartosc = pr[:5]
            jednorazowy = pr[5:] == ("jednorazowo",)
            prog_startu = 1 if pr[5:] == ("natychmiast",) else 2
            widziane.add(klucz)
            licz[klucz] = licz.get(klucz, 0) + 1 if licz.get(klucz, 0) >= 0 else 1
            if jednorazowy:
                inc.append({"id": uuid_hex(), "klucz": klucz, "tytul": tytul, "opis": opis, "poziom": poziom,
                            "od": teraz, "do": teraz, "wartosc": wartosc, "przejrzane": False})
                zdrowie_log(f"ZDARZENIE {poziom} {klucz}: {tytul}")
                continue
            if klucz in aktywne:
                a = aktywne[klucz]
                a["opis"], a["ostatnio"], a["teraz"] = opis, teraz, poziom
                if isinstance(wartosc, (int, float)) and wartosc > (a.get("wartosc") or 0):
                    a["wartosc"] = wartosc
                if poziom == "crit" and a["poziom"] != "crit":
                    a["poziom"] = "crit"
                    zdrowie_log(f"POGORSZENIE crit {klucz}: {tytul} - {opis}")
            elif licz[klucz] >= prog_startu:
                inc.append({"id": uuid_hex(), "klucz": klucz, "tytul": tytul, "opis": opis, "poziom": poziom, "teraz": poziom,
                            "od": teraz, "do": None, "ostatnio": teraz, "wartosc": wartosc, "przejrzane": False})
                zdrowie_log(f"START {poziom} {klucz}: {tytul} - {opis}")
        for klucz in list(licz):
            if klucz not in widziane:
                licz[klucz] = min(licz[klucz], 0) - 1
                if klucz in aktywne and licz[klucz] <= -2:
                    aktywne[klucz]["do"] = teraz
                    zdrowie_log(f"KONIEC {aktywne[klucz]['poziom']} {klucz}: {aktywne[klucz]['tytul']} (od {aktywne[klucz]['od']})")
                if licz[klucz] <= -2 and klucz not in aktywne:
                    licz.pop(klucz)
        # porzadek: zostaw 1000 ostatnich, ale nigdy nie wyrzucaj aktywnych ani nieprzejrzanych
        if len(inc) > 1000:
            stare = [i for i in inc if i.get("do") and i.get("przejrzane")]
            usun = {i["id"] for i in stare[:len(inc) - 1000]}
            inc = [i for i in inc if i["id"] not in usun]
        zapisz_json(ZDROWIE / "incydenty.json", inc)
        ZDROWIE_STAN["sprawdzono"], ZDROWIE_STAN["pomiary"] = teraz, pom


def uuid_hex():
    import uuid
    return uuid.uuid4().hex


def zdrowie_petla():
    zdrowie_cpu()
    time.sleep(5)
    while True:
        try:
            zdrowie_krok()
        except Exception as e:      # monitor nie moze zatrzymac portalu
            try:
                zdrowie_log(f"BLAD MONITORA {type(e).__name__}: {e}")
            except OSError:
                pass
        ZDROWIE_BUDZIK.wait(60)
        ZDROWIE_BUDZIK.clear()


def zdrowie_podsumowanie():
    inc = zdrowie_incydenty()
    aktywne = [i for i in inc if not i.get("do")]
    do_przejrzenia = [i for i in inc if i.get("do") and not i.get("przejrzane")]
    stan = "crit" if any(i.get("teraz", i["poziom"]) == "crit" for i in aktywne) else "warn" if aktywne or do_przejrzenia else "ok"
    return {"stan": stan, "liczba": len(aktywne) + len(do_przejrzenia), "aktywne": aktywne,
            "do_przejrzenia": sorted(do_przejrzenia, key=lambda i: i["od"], reverse=True),
            "sprawdzono": ZDROWIE_STAN["sprawdzono"], "pomiary": ZDROWIE_STAN["pomiary"], "progi": zdrowie_progi()}


@app.route("/api/zdrowie")
def api_zdrowie():
    from flask import request
    d = zdrowie_podsumowanie()
    if request.args.get("historia"):
        inc = zdrowie_incydenty()
        d["historia"] = sorted((i for i in inc if i.get("do") and i.get("przejrzane")), key=lambda i: i["od"], reverse=True)[:200]
    return jsonify(d)


@app.route("/api/zdrowie/przejrzane", methods=["POST"])
def api_zdrowie_przejrzane():
    from flask import request
    b = request.get_json(silent=True)
    if not isinstance(b, dict) or not (b.get("wszystkie") is True or isinstance(b.get("id"), str)):
        abort(400)
    with ZDROWIE_LOCK:
        inc = zdrowie_incydenty()
        n = 0
        for i in inc:
            if i.get("do") and not i.get("przejrzane") and (b.get("wszystkie") is True or i["id"] == b.get("id")):
                i["przejrzane"], i["przejrzano"] = True, time.strftime("%Y-%m-%dT%H:%M:%S")
                n += 1
        zapisz_json(ZDROWIE / "incydenty.json", inc)
    if n:
        zdrowie_log(f"PRZEJRZANE {n} zdarzen")
    return jsonify(zdrowie_podsumowanie())


@app.route("/api/zdrowie/dziennik")
def api_zdrowie_dziennik():
    try:
        linie = (ZDROWIE / "dziennik.log").read_text(encoding="utf-8").splitlines()[-300:]
    except OSError:
        linie = []
    return jsonify(linie[::-1])


# ---------- Obciazenie: kazdy przedzial czasu z CPU > 60 %, temperatura > 55 °C, RAM > 60 % ----------
# Watek co 5 s. Przedzial zaczyna sie po 2 kolejnych pomiarach ponad progiem (>= 10 s), konczy po 3 ponizej (15 s).
# Zapis: dane/zdrowie/obciazenie.json (lista przedzialow) + czytelne logi cpu.log, temperatura.log, ram.log
# (START od razu, KONIEC z maksimum, srednia i glownymi „zjadaczami”), kopiowane na NAS do Logi/ przez nas_petla.
# Progi: config.json "obciazenie": {"cpu": 60, "temp": 55, "ram": 60}.
OBC_PROGI = {"cpu": 60, "temp": 55, "ram": 60}
OBC_TYPY = {"cpu": ("cpu.log", "CPU", "%"), "temp": ("temperatura.log", "Temperatura", " °C"), "ram": ("ram.log", "RAM", "%")}
OBC_LOCK = threading.Lock()
OBC_STAN = {"trwa": {}, "licz": {}, "pomiar": {}}


def obc_progi():
    p = dict(OBC_PROGI)
    p.update(config().get("obciazenie") or {})
    return p


def obc_epizody():
    try:
        return json.loads((ZDROWIE / "obciazenie.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def obc_procesy(prev):
    """czas CPU (tiki) i RAM kazdego procesu; nazwa = program (usluga)"""
    cur = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            st = Path(f"/proc/{d}/stat").read_text()
            rp = st.rfind(")")
            f = st[rp + 2:].split()
            klucz = (int(d), f[19])                     # pid + czas startu (pid moze zostac uzyty ponownie)
            nazwa = prev[klucz][2] if klucz in prev else st[st.find("(") + 1:rp]
            if klucz not in prev:
                u = unit_of(d)
                nazwa = f"{nazwa} ({u})" if u and u != nazwa else nazwa
            cur[klucz] = (int(f[11]) + int(f[12]), int(f[21]) * PAGE_SIZE, nazwa)
        except (OSError, ValueError, IndexError):
            continue
    return cur


def obc_czas(sek):
    sek = int(round(sek))
    return f"{sek} s" if sek < 60 else f"{sek // 60} min {sek % 60} s" if sek < 3600 else f"{sek // 3600} h {sek % 3600 // 60} min"


def obc_top(e, n=5):
    if e["typ"] == "ram":
        lista = sorted(e["ram_max"].items(), key=lambda x: -x[1])[:n]
        return [{"nazwa": k, "mb": round(v / 1048576)} for k, v in lista]
    dl = max(1.0, e["sek"])
    lista = sorted(e["cpu_s"].items(), key=lambda x: -x[1])[:n]
    return [{"nazwa": k, "cpu": round(v / dl * 100)} for k, v in lista if v > 0]


def obc_opis_top(top):
    return ", ".join(f"{t['nazwa']} {t['mb']} MB" if "mb" in t else f"{t['nazwa']} {t['cpu']}%" for t in top) or "–"


def obc_log(typ, linia):
    ZDROWIE.mkdir(parents=True, exist_ok=True)
    with open(ZDROWIE / OBC_TYPY[typ][0], "a", encoding="utf-8") as f:
        f.write(linia + "\n")
    NAS_BUDZIK.set()


def obc_dodaj(e, v, procesy, teraz):
    e["suma"] += v
    e["n"] += 1
    if v >= e["max"]:
        e["max"], e["max_czas"] = v, time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(teraz))
    for nazwa, (cpu_s, rss) in procesy.items():
        if cpu_s > 0:
            e["cpu_s"][nazwa] = e["cpu_s"].get(nazwa, 0) + cpu_s
        if rss > e["ram_max"].get(nazwa, 0):
            e["ram_max"][nazwa] = rss


def obc_krok(wart, procesy, dt, teraz):
    """jeden pomiar: wart = {"cpu": %, "temp": °C, "ram": %}, procesy = {nazwa: (sekundy CPU w ostatnich dt, RAM)}"""
    prog = obc_progi()
    with OBC_LOCK:
        poprz = OBC_STAN.get("poprz") or {}
        for typ, v in wart.items():
            if v is None:
                continue
            licz, e = OBC_STAN["licz"], OBC_STAN["trwa"].get(typ)
            if v > prog[typ]:
                licz[typ] = max(0, licz.get(typ, 0)) + 1
                if e is None and licz[typ] >= 2:
                    t0 = teraz - 2 * dt         # przedzial zaczal sie przy poprzednim pomiarze
                    e = OBC_STAN["trwa"][typ] = {"typ": typ, "od": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0)), "t0": t0,
                                                 "max": 0, "max_czas": None, "suma": 0.0, "n": 0, "prog": prog[typ], "sek": 0.0,
                                                 "cpu_s": {}, "ram_max": {}, "ponizej": 0, "ostatnio": teraz}
                    if typ in poprz:
                        obc_dodaj(e, poprz[typ][0], poprz[typ][1], teraz - dt)
                    _, nazwa, jedn = OBC_TYPY[typ]
                    obc_log(typ, f"{e['od'].replace('T', ' ')} START {nazwa} > {prog[typ]}{jedn} (teraz {v:.0f}{jedn})")
                if e:
                    e["ponizej"], e["ostatnio"] = 0, teraz
                    obc_dodaj(e, v, procesy, teraz)
                    e["sek"] = teraz - e["t0"]
            else:
                licz[typ] = min(0, licz.get(typ, 0)) - 1
                if e:
                    e["ponizej"] += 1
                    if e["ponizej"] >= 3:
                        obc_zakoncz(e, e["ostatnio"])
                        del OBC_STAN["trwa"][typ]
        OBC_STAN["poprz"] = {typ: (v, procesy) for typ, v in wart.items() if v is not None}


def obc_zakoncz(e, koniec):
    _, nazwa, jedn = OBC_TYPY[e["typ"]]
    e["sek"] = max(0, koniec - e["t0"])
    rek = {"typ": e["typ"], "od": e["od"], "do": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(koniec)),
           "sek": round(e["sek"]), "max": round(e["max"], 1), "max_czas": e["max_czas"],
           "srednia": round(e["suma"] / max(1, e["n"]), 1), "prog": e["prog"], "top": obc_top(e)}
    obc_log(e["typ"], f"{rek['od'].replace('T', ' ')} – {rek['do'][11:]} ({obc_czas(rek['sek'])}) {nazwa} max {rek['max']:.0f}{jedn}"
                      f" o {(rek['max_czas'] or '')[11:]}, średnio {rek['srednia']:.0f}{jedn} · najwięcej: {obc_opis_top(rek['top'])}")
    lista = obc_epizody()
    lista.append(rek)
    zapisz_json(ZDROWIE / "obciazenie.json", lista[-3000:], indent=None)


OBC_MAKS = ZDROWIE / "maksima.json"     # {"RRRR-MM-DD": {"cpu": [wartosc, "HH:MM"], "temp": [...], "ram": [...]}}, 60 dni


def obc_maksima(wart, teraz):
    """najwyzsze wartosci kazdego dnia (pomiar co 5 s), zapis na karte co minute"""
    m = OBC_STAN.get("maks")
    if m is None:
        try:
            m = json.loads(OBC_MAKS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            m = {}
        OBC_STAN["maks"] = m
    dzien, godz = time.strftime("%Y-%m-%d"), time.strftime("%H:%M")
    d = m.setdefault(dzien, {})
    for k, v in wart.items():
        if v is not None and (k not in d or v > d[k][0]):
            d[k] = [round(v, 1), godz]
    if teraz - OBC_STAN.get("maks_zapis", 0) > 60:
        OBC_STAN["maks_zapis"] = teraz
        for stary in sorted(m)[:-60]:
            del m[stary]
        zapisz_json(OBC_MAKS, m, indent=None)


def obc_maks_okres(dni):
    """maksimum z ostatnich dni (dzis wlacznie): {typ: [wartosc, "RRRR-MM-DD HH:MM"]}"""
    m = OBC_STAN.get("maks") or {}
    granica = time.strftime("%Y-%m-%d", time.localtime(time.time() - (dni - 1) * 86400))
    wynik = {}
    for dzien, d in m.items():
        if dzien >= granica:
            for k, (v, g) in d.items():
                if k not in wynik or v > wynik[k][0]:
                    wynik[k] = [v, f"{dzien} {g}"]
    return wynik


def obc_petla():
    prev_cpu, prev_proc, t_prev = None, {}, None
    while True:
        try:
            teraz = time.time()
            vals = [int(x) for x in read("/proc/stat").splitlines()[0].split()[1:]]
            cur_cpu = (vals[3] + vals[4], sum(vals))
            cur_proc = obc_procesy(prev_proc)
            if prev_cpu and t_prev and cur_cpu[1] > prev_cpu[1]:
                dt = teraz - t_prev
                cpu = 100.0 * (1 - (cur_cpu[0] - prev_cpu[0]) / (cur_cpu[1] - prev_cpu[1]))
                try:
                    temp = int(read("/sys/class/thermal/thermal_zone0/temp", "0")) / 1000 or None
                except ValueError:
                    temp = None
                mi = meminfo()
                ram = (mi["MemTotal"] - mi.get("MemAvailable", 0)) / mi["MemTotal"] * 100 if mi.get("MemTotal") else None
                procesy = {}
                for k, (tiki, rss, nazwa) in cur_proc.items():
                    cpu_s = (tiki - prev_proc[k][0]) / HZ if k in prev_proc else 0.0
                    a = procesy.get(nazwa, (0.0, 0))
                    procesy[nazwa] = (a[0] + cpu_s, a[1] + rss)
                OBC_STAN["pomiar"] = {"cpu": round(cpu, 1), "temp": temp and round(temp, 1), "ram": ram and round(ram, 1),
                                      "czas": time.strftime("%Y-%m-%dT%H:%M:%S")}
                obc_krok({"cpu": cpu, "temp": temp, "ram": ram}, procesy, dt, teraz)
                obc_maksima({"cpu": cpu, "temp": temp, "ram": ram}, teraz)
            prev_cpu, prev_proc, t_prev = cur_cpu, cur_proc, teraz
        except Exception as e:      # pomiar nie moze zatrzymac portalu
            try:
                zdrowie_log(f"BLAD OBCIAZENIA {type(e).__name__}: {e}")
            except OSError:
                pass
            time.sleep(55)
        time.sleep(5)


@app.route("/api/obciazenie")
def api_obciazenie():
    with OBC_LOCK:
        trwa = [{"typ": e["typ"], "od": e["od"], "sek": round(e["sek"]), "max": round(e["max"], 1), "max_czas": e["max_czas"],
                 "srednia": round(e["suma"] / max(1, e["n"]), 1), "prog": e["prog"], "top": obc_top(e)} for e in OBC_STAN["trwa"].values()]
    lista = obc_epizody()
    granica = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 86400))
    doba = {}
    for typ in OBC_TYPY:
        ep = [e for e in lista if e["typ"] == typ and e["do"] >= granica]
        doba[typ] = {"ile": len(ep), "sek": sum(e["sek"] for e in ep), "max": max((e["max"] for e in ep), default=None)}
    return jsonify({"progi": obc_progi(), "teraz": OBC_STAN["pomiar"], "trwa": trwa, "doba": doba, "przedzialy": lista[::-1][:150],
                    "maks": {"dzis": obc_maks_okres(1), "tydzien": obc_maks_okres(7)}})


# ---------- Zadania w tle: kopia systemu, render, NAS, logi, aktualizacje (panel na /strony/zdrowie/) ----------
ZADANIA = [   # (usluga, timer, nazwa, opis)
    ("kopia-pi", "kopia-pi.timer", "Kopia całego systemu na NAS", "Co noc o 02:00, tylko zmiany, do NAS → Raspberry/Kopia-systemu"),
    ("logi-na-nas", "logi-na-nas.timer", "Dziennik systemu na NAS", "Co minutę do NAS → Raspberry/Logi/system"),
    ("nas-montuj", "nas-montuj.timer", "Połączenie z NAS", "Sprawdzane co 2 minuty, po zerwaniu łączy od nowa"),
    ("mc-autoupdate", "mc-autoupdate.timer", "Aktualizacja serwera Minecraft", "Automatyczna aktualizacja PowerNukkitX"),
    ("apt-daily-upgrade", "apt-daily-upgrade.timer", "Aktualizacje systemu", "Automatyczne poprawki bezpieczeństwa (apt)"),
]


def zadania_timery():
    try:
        return {t["unit"]: t for t in json.loads(sh(["systemctl", "list-timers", "--all", "--output=json", "--no-pager"]) or "[]")}
    except ValueError:
        return {}


def usec_iso(v):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(v / 1e6)) if isinstance(v, (int, float)) and v > 0 else None


def kopia_postep():
    """postep trwajacej kopii: z postep.json skryptu, a gdy go nie ma, szacunek z zajetosci pliku kopii"""
    try:
        p = json.loads((KOPIA_STAN / "postep.json").read_text(encoding="utf-8"))
        return {"faza": p.get("faza"), "procent": p.get("procent"), "pliki": p.get("pliki"), "start": p.get("start")}
    except (OSError, ValueError):
        pass
    try:
        kopia = shutil.disk_usage("/mnt/pi-kopia")
        if not os.path.ismount("/mnt/pi-kopia"):
            return {"faza": "przygotowanie", "procent": None}
        zrodlo = shutil.disk_usage("/").used + shutil.disk_usage("/boot/firmware").used - 2 * 1024 ** 3
        return {"faza": "kopiowanie", "procent": min(99, round(kopia.used / max(1, zrodlo) * 100)), "szacunek": True}
    except OSError:
        return {"faza": "przygotowanie", "procent": None}


def zadania_lista():
    timery, lista = zadania_timery(), []
    for usluga, timer, nazwa, opis in ZADANIA:
        st = usluga_stan(usluga)
        if st.get("LoadState") != "loaded":
            continue
        t = timery.get(timer, {})
        z = {"id": usluga, "nazwa": nazwa, "opis": opis, "trwa": st.get("ActiveState") in ("activating", "active", "deactivating"),
             "wynik": st.get("Result") or None, "ostatnio": usec_iso(t.get("last")), "nastepnie": usec_iso(t.get("next"))}
        if usluga == "kopia-pi":
            for plik, klucz in (("stan.json", "ostatni"), ("ostatnia-udana.json", "udana")):
                try:
                    z[klucz] = json.loads((KOPIA_STAN / plik).read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    z[klucz] = None
            if z["trwa"]:
                z.update(kopia_postep())
                if not z.get("start"):
                    m = re.search(r"@(\d+)", sh(["systemctl", "show", "--timestamp=unix", "-p", "ExecMainStartTimestamp", "--value", "kopia-pi"]))
                    z["start"] = usec_iso(int(m.group(1)) * 1e6) if m else z["ostatnio"]
        lista.append(z)
    filmy = [m for m in (film_meta(p.stem) for p in PROGRES_FILMY.glob("*.json") if not p.name.endswith(".wejscie.json")) if m]
    trwa = next((m for m in filmy if m.get("status") == "renderuje"), None)
    render = {"id": "render", "nazwa": "Render filmów (Progres)", "opis": "Filmy z postępu sylwetki, jeden naraz, niski priorytet",
              "trwa": bool(trwa), "kolejka": sum(m.get("status") == "oczekuje" for m in filmy)}
    if trwa:
        try:
            render["procent"] = int((PROGRES_FILMY / f"{trwa['id']}.postep").read_text())
        except (OSError, ValueError):
            render["procent"] = 0
        render.update(faza="renderuje", start=trwa.get("start"), cel=trwa.get("opis") or "")
    gotowe = [m for m in filmy if m.get("status") in ("gotowe", "blad")]
    if gotowe:
        ost = max(gotowe, key=lambda m: m["utworzono"])
        render.update(ostatnio=ost.get("start") or ost["utworzono"], wynik="success" if ost["status"] == "gotowe" else "blad")
    lista.insert(1, render)
    bufor = [p for p in list(PROGRES_ZDJ.glob("*.jpg")) + list(PROGRES_FILMY.glob("*.mp4")) if not p.name.endswith(".tmp.mp4")]
    lista.insert(2, {"id": "nas-bufor", "nazwa": "Zdjęcia i filmy na NAS", "opis": "Zapis od razu na NAS; gdy był niedostępny, Pi przenosi zaległe co 30 s",
                     "trwa": bool(bufor) and nas_ok(), "czeka": len(bufor), "wynik": "success" if not bufor else None})
    nas = {"ok": nas_ok()}
    if nas["ok"]:
        try:
            du = shutil.disk_usage("/mnt/nas")
            nas.update(wolne_gb=round(du.free / 1e9), razem_gb=round(du.total / 1e9))
        except OSError:
            pass
    return {"zadania": lista, "nas": nas, "teraz": time.strftime("%Y-%m-%dT%H:%M:%S")}


@app.route("/api/zadania")
def api_zadania():
    return jsonify(zadania_lista())


# ---------- NAS: przenoszenie bufora z Pi i kopie logow (co 30 s albo od razu po zmianie) ----------
NAS_KOPIE = {}      # plik -> zawartosc ostatnio wyslana na NAS


def nas_lustro(zrodlo, cel):
    try:
        dane = zrodlo.read_bytes()
    except OSError:
        return
    if NAS_KOPIE.get(cel) != dane:
        nas_zapisz(cel, dane)
        NAS_KOPIE[cel] = dane


def nas_krok(sprzatanie=False):
    if not nas_ok():
        return
    try:
        for p in sorted(PROGRES_ZDJ.glob("*.jpg")):
            nas_przenies(p, NAS_ZDJ / p.name)
        for p in sorted((PROGRES / "kosz").glob("*.jpg")):
            nas_przenies(p, NAS_ZDJ / "Usuniete" / p.name)
        for p in sorted(PROGRES_FILMY.glob("*.mp4")):
            if not p.name.endswith(".tmp.mp4"):
                nas_przenies(p, NAS_FILMY / p.name)
        nas_lustro(ZDROWIE / "dziennik.log", NAS_LOGI / "zdrowie-dziennik.log")
        nas_lustro(ZDROWIE / "incydenty.json", NAS_LOGI / "zdrowie-incydenty.json")
        nas_lustro(PROGRES / "dane.json", NAS_ZDJ / "dane.json")
        for plik, _, _ in OBC_TYPY.values():
            nas_lustro(ZDROWIE / plik, NAS_LOGI / plik)
        if sprzatanie:      # pliki usuniete na stronie, gdy NAS byl niedostepny (starsze niz 10 min: nie w trakcie dodawania)
            znane = {z["id"] for z in progres_dane()["zdjecia"]}
            filmy = {p.stem for p in PROGRES_FILMY.glob("*.json")}
            stare = time.time() - 600
            for p in NAS_ZDJ.glob("*.jpg"):
                if p.name.split(".")[0].removesuffix("_m") not in znane and p.stat().st_mtime < stare:
                    (NAS_ZDJ / "Usuniete").mkdir(exist_ok=True)
                    os.replace(p, NAS_ZDJ / "Usuniete" / p.name)
            for p in NAS_FILMY.glob("*.mp4"):
                if p.stem not in filmy and p.stat().st_mtime < stare:
                    p.unlink()
    except OSError:
        nas_blad()


def nas_petla():
    n = 0
    while True:
        try:
            nas_krok(sprzatanie=n % 20 == 0)
        except Exception as e:      # watek nie moze zatrzymac portalu
            try:
                zdrowie_log(f"BLAD NAS {type(e).__name__}: {e}")
            except OSError:
                pass
        n += 1
        NAS_BUDZIK.wait(30)
        NAS_BUDZIK.clear()
        time.sleep(1)       # kilka zmian naraz = jedna kopia


if not os.environ.get("PORTAL_TEST"):
    threading.Thread(target=zdrowie_petla, name="zdrowie", daemon=True).start()
    threading.Thread(target=nas_petla, name="nas", daemon=True).start()
    threading.Thread(target=obc_petla, name="obciazenie", daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
