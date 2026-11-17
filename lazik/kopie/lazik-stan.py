#!/usr/bin/env python3
"""Stan malinek łazika i ich kopii zapasowych dla zakładki „Kopie i malinki” na stronie /strony/lazik/ (Pi 4).

Co 5 s zapisuje ~/portal/sites/lazik/kopie.json: dostępność Pi (Tailscale + ping w sieci domowej), kopie na NAS
(Raspberry/Kopie-lazika/<pi>/), kopię trwającą na żywo (rosnący plik .czesc: rozmiar i tempo) i końcówkę logu.
Usługa lazik-stan.service (użytkownik tonyg, niski priorytet). Niczego nie zmienia, tylko czyta.
"""

import json
import os
import subprocess
import time

NAS = "/mnt/nas/Raspberry"
KOPIE = os.path.join(NAS, "Kopie-lazika")
LOG = os.path.join(NAS, "Logi", "kopie-lazika.log")
WYJSCIE = os.path.expanduser("~/portal/sites/lazik/kopie.json")
CO_ILE_DNI = 7
MALINKI = [  # (nazwa w Tailscale, opis, adres w sieci domowej)
    ("rpi-5-1", "Pi 5: łazik", "172.23.0.15"),
    ("rpi-zero2w-a1", "Zero 2W a1: stacja", "172.23.0.27"),
    ("rpi-zero2w-a2", "Zero 2W a2: satelita", "172.23.0.21"),
]


def tailscale():
    try:
        out = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=5).stdout
        peers = json.loads(out).get("Peer", {}).values()
    except Exception:
        return {}
    wynik = {}
    for p in peers:
        nazwa = (p.get("HostName") or "").lower()
        wynik[nazwa] = dict(online=bool(p.get("Online")), ostatnio=p.get("LastSeen"),
                            ip=(p.get("TailscaleIPs") or [None])[0])
    return wynik


def ping(ip):
    return subprocess.run(["ping", "-c", "1", "-W", "1", ip], capture_output=True).returncode == 0


poprzednie = {}  # pi → (czas, rozmiar) do liczenia tempa trwającej kopii


def kopie_pi(pi):
    k = os.path.join(KOPIE, pi)
    lista, trwa = [], None
    if not os.path.isdir(k):
        return lista, trwa
    for n in os.listdir(k):
        p = os.path.join(k, n)
        try:
            st = os.stat(p)
        except OSError:
            continue
        if n.endswith(".tar.zst"):
            lista.append(dict(plik=n, bajty=st.st_size, czas=st.st_mtime))
        elif n.endswith(".czesc"):
            teraz = time.time()
            tempo = None
            if pi in poprzednie:
                t0, r0 = poprzednie[pi]
                if teraz > t0 and st.st_size >= r0:
                    tempo = (st.st_size - r0) / (teraz - t0)
            poprzednie[pi] = (teraz, st.st_size)
            trwa = dict(bajty=st.st_size, start=st.st_ctime, zmiana=st.st_mtime, tempo=tempo,
                        aktywna=teraz - st.st_mtime < 60)  # plik rośnie = przesyłanie trwa
    if trwa is None:
        poprzednie.pop(pi, None)
    lista.sort(key=lambda x: -x["czas"])
    return lista, trwa


def zbierz():
    nas_ok = os.path.ismount("/mnt/nas") and os.path.exists(os.path.join(NAS, ".nas"))
    ts = tailscale()
    malinki = []
    for nazwa, opis, lan in MALINKI:
        t = ts.get(nazwa, {})
        lista, trwa = kopie_pi(nazwa) if nas_ok else ([], None)
        ostatnia = lista[0]["czas"] if lista else None
        malinki.append(dict(
            nazwa=nazwa, opis=opis, tailscale=t.get("online", False), ostatnio_widziany=t.get("ostatnio"),
            ip_tailscale=t.get("ip"), lan=lan, w_domu=ping(lan), kopie=lista, trwa=trwa,
            ostatnia_kopia=ostatnia, nastepna_najpozniej=ostatnia + CO_ILE_DNI * 86400 if ostatnia else None,
            zalegla=ostatnia is None or time.time() - ostatnia > CO_ILE_DNI * 86400))
    log = []
    try:
        with open(LOG, encoding="utf-8", errors="replace") as f:
            log = [l.rstrip("\n") for l in f.readlines()[-25:]]
    except OSError:
        pass
    wolne = None
    if nas_ok:
        s = os.statvfs("/mnt/nas")
        wolne = s.f_bavail * s.f_frsize
    return dict(czas=time.time(), nas=nas_ok, nas_wolne=wolne, co_ile_dni=CO_ILE_DNI, malinki=malinki, log=log)


def main():
    os.makedirs(os.path.dirname(WYJSCIE), exist_ok=True)
    while True:
        try:
            dane = zbierz()
            tmp = WYJSCIE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(dane, f, ensure_ascii=False)
            os.replace(tmp, WYJSCIE)
        except Exception as e:  # usługa ma działać dalej mimo chwilowych błędów (np. NAS odpięty)
            print("błąd:", e, flush=True)
        time.sleep(5)


if __name__ == "__main__":
    main()
