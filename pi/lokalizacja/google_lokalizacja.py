#!/home/tonyg/lokalizacja/venv/bin/python
"""
Lokalizacja Antka z Google Maps (udostępnianie lokalizacji) -> portal (/api/lokalizacja), co 15 min (timer systemd).

Antek udostępnia lokalizację w Google Maps drugiemu, pustemu kontu Google („serwerek”). Pi czyta ją ciasteczkami
logowania tego konta (plik Netscape: ~/portal/dane/google_cookies.txt, chmod 600, nigdy w repo; nowy plik Antek
wrzuca do Tony-Folder/Raspberry/Google/ na NAS, skrypt go zabiera i kasuje z NAS) przez nieoficjalną
bibliotekę locationsharinglib (venv ~/lokalizacja/venv). Czas lokalizacji = czas z Google (nie odczytu), więc stara
pozycja zapala żółty alarm w monitorze zdrowia. Błąd (np. wygasłe ciasteczka) zapisuje się w
~/portal/dane/lokalizacja_google.json i monitor dopisuje go do opisu alarmu.
"""
import json
import time
import urllib.request
from pathlib import Path

from locationsharinglib import Service

DANE = Path("/home/tonyg/portal/dane")
COOKIES = DANE / "google_cookies.txt"
KONTO = DANE / "google_konto.txt"          # adres drugiego konta (ten, któremu udostępniona jest lokalizacja)
STAN = DANE / "lokalizacja_google.json"
PORTAL = "http://127.0.0.1/api/lokalizacja"
NAS = Path("/mnt/nas/Raspberry/Google")


def zapisz_stan(**d):
    tmp = STAN.with_suffix(".tmp")
    tmp.write_text(json.dumps({"t": time.time(), **d}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STAN)


def odbierz_z_nas():
    """Antek wrzuca cookies.txt do Tony-Folder/Raspberry/Google/ na NAS: przenosimy go na Pi (600) i kasujemy z NAS"""
    for p in NAS.glob("*.txt"):
        if p.name.lower().startswith("czytaj"):
            continue
        tresc = p.read_text(encoding="utf-8", errors="replace")
        if "google.com" not in tresc:
            continue
        tmp = COOKIES.with_suffix(".tmp")
        tmp.touch(mode=0o600)
        tmp.write_text(tresc, encoding="utf-8")
        tmp.replace(COOKIES)
        p.unlink()
        print("google_lokalizacja: nowe ciasteczka z NAS", flush=True)


def main():
    try:
        odbierz_z_nas()
    except OSError as ex:
        print(f"google_lokalizacja: NAS: {ex}", flush=True)
    try:
        konto = KONTO.read_text().strip() if KONTO.exists() else "unknown@gmail.com"
        osoby = list(Service(cookies_file=str(COOKIES), authenticating_account=konto).get_shared_people())
        if not osoby:
            raise RuntimeError("nikt nie udostępnia lokalizacji temu kontu Google")
        o = osoby[0]
        if o.latitude is None or o.longitude is None:
            raise RuntimeError("Google nie podał pozycji")
        tst = (o.timestamp or 0) / 1000 if (o.timestamp or 0) > 1e11 else (o.timestamp or time.time())
        dane = {"lat": o.latitude, "lon": o.longitude, "acc": o.accuracy, "tst": int(tst), "zrodlo": "google"}
        req = urllib.request.Request(PORTAL, data=json.dumps(dane).encode(), headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=15).read()
        zapisz_stan(ok=True, osoba=o.full_name, czas=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(tst)))
    except Exception as ex:                  # wygasłe ciasteczka, zmiana po stronie Google, brak sieci
        zapisz_stan(ok=False, blad=f"{type(ex).__name__}: {ex}"[:300])
        print(f"google_lokalizacja: {type(ex).__name__}: {ex}", flush=True)


if __name__ == "__main__":
    main()
