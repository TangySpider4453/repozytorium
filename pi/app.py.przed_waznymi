#!/usr/bin/env python3
"""
Serwerek domowy - strona glowna Raspberry Pi 4B ("strona matka").

  /                  stan serwera, wszystkie dzialajace programy, linki do kazdej strony hostowanej na Pi
  /siec              wszystkie adresy IP (LAN, Tailscale, publiczny, tunel Minecraft), porty, urzadzenia Tailscale
  /terminal          terminal w przegladarce (osadza usluge home-terminal z portu 7681)
  /strony/<nazwa>/   strony statyczne z katalogu sites/<nazwa>/ (wystarczy wrzucic folder z index.html)
  /api/status, /api/siec   dane w JSON dla powyzszych stron
  /api/nauka/...     postepy nauki (fiszki, quizy) i zmiana daty sprawdzianu dla /strony/nauka/

Nasluch tylko na adresie Tailscale (port 80) - strona nie jest widoczna w sieci domowej ani w internecie.
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
nav a.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
nav a:hover{border-color:var(--accent)}
section{display:flex;flex-direction:column;gap:14px}
.sec-note{color:var(--muted);max-width:75ch;margin:0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,170px),1fr));gap:10px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tile .k{font-family:var(--mono);font-size:11.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}
.tile .v{font-family:var(--display);font-size:30px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.15}
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
</style></head>
<body><div class="wrap">
<header>
  <div><h1 id="h-title">Serwerek domowy</h1><div class="sub" id="h-sub">Raspberry Pi 4B · ładowanie…</div></div>
  <nav>
    <a href="/" data-p="start">Start</a>
    <a href="/siec" data-p="siec">Sieć i adresy</a>
    <a href="/terminal" data-p="terminal">Terminal</a>
    <a href="/strony/lazik/" data-p="lazik">Łazik</a>
    <a href="/strony/nauka/" data-p="nauka">Nauka</a>
  </nav>
</header>
<main id="main" class="wrap" style="padding:0;width:100%"></main>
<footer id="foot">Strona dostępna tylko przez Tailscale. Dane odświeżają się same.</footer>
</div>
<script>
const PAGE="%%PAGE%%", PORT=%%PORT%%, TERMINAL_PORT=%%TPORT%%;
document.querySelectorAll('nav a').forEach(a=>{if(a.dataset.p===PAGE)a.classList.add('on')});
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
function renderStart(d){
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
    h('section',null,h('h2',{text:'Strony na tym serwerze'}),h('p',{class:'sec-note',text:'Wszystko, co Pi udostępnia w przeglądarce. Nową stronę dodasz, wrzucając folder z plikiem index.html do ~/portal/sites/.'}),cards),
    h('section',null,h('h2',{text:'Działające programy ('+d.uslugi.length+')'}),h('p',{class:'sec-note',text:'Wszystkie usługi systemd, które teraz działają, pogrupowane według przeznaczenia.'}),...svc),
    h('section',null,h('h2',{text:'Co teraz najbardziej obciąża Pi'}),h('p',{class:'sec-note',text:'CPU mierzone między kolejnymi odświeżeniami strony (100 % = jeden pełny rdzeń).'}),procs)
  );
  document.getElementById('foot').textContent='Auto-aktualizacja serwera MC: następna '+(au.nastepne||'–')+', ostatnia '+(au.ostatnie||'–')+'. Strona dostępna tylko przez Tailscale, odświeża się co 5 s.';
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
    if(PAGE==='start'){renderStart(await getJSON('/api/status'))}
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
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@app.route("/")
def start():
    return page("start")


@app.route("/siec")
def siec():
    return page("siec")


@app.route("/terminal")
def terminal():
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
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024


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


def tailscale_ipv4():
    for _ in range(120):
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", sh(["ip", "-4", "-o", "addr", "show", "dev", "tailscale0"]))
        if m:
            return m.group(1)
        time.sleep(5)
    raise SystemExit("Brak adresu Tailscale - portal nie startuje (nie bedzie nasluchiwal w LAN).")


if __name__ == "__main__":
    app.run(host=tailscale_ipv4(), port=PORT, threaded=True)
