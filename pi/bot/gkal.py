"""
Plan lekcji z Mobidziennika -> Google Calendar (osobny kalendarz, np. „Plan lekcji”), od razu po każdym odczycie
Mobidziennika (co 10 min, 6–22). Google Calendar API przez konto usługi (service account): bez logowania przeglądarką
i bez wygasających tokenów. Podpis JWT (RS256) biblioteką cryptography, zapytania urllib (bez nowych pakietów).

Pliki (poza repo): ~/bot/google/kalendarz-klucz.json (klucz konta usługi, 600), ~/bot/google/kalendarz.json
{"id": "<identyfikator kalendarza>@group.calendar.google.com"}, stan: ~/bot/google/kalendarz-stan.json.
Kalendarz trzeba udostępnić adresowi konta usługi (client_email z klucza) z uprawnieniem „Wprowadzanie zmian w wydarzeniach”.

Wydarzenia mają stały identyfikator z (data, godzina, grupa), więc zmiana planu podmienia wydarzenie, a nie dubluje.
Zarządzamy tylko wydarzeniami z extendedProperties.private.zrodlo == "serwerek-mobi": inne wydarzenia są nietknięte.
"""
import base64
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

KAT = Path(__file__).resolve().parent / "google"
KLUCZ = KAT / "kalendarz-klucz.json"            # wariant 1: konto usługi
OAUTH_KLIENT = KAT / "oauth-klient.json"         # wariant 2: klient OAuth (Antek autoryzuje raz, zakres calendar.app.created)
OAUTH_TOKEN = KAT / "oauth-token.json"           # {"refresh_token": …}
ZAKRES_APP = "https://www.googleapis.com/auth/calendar.app.created"   # tylko kalendarze utworzone przez tę aplikację
PRZEKIEROWANIE = "http://localhost:8765"
KONFIG = KAT / "kalendarz.json"
STAN = KAT / "kalendarz-stan.json"
API = "https://www.googleapis.com/calendar/v3"
ZRODLO = "serwerek-mobi"
STREFA = "Europe/Warsaw"
KOLOR = {"zastępstwo": "5", "odwołana": "8", "sprawdzian": "11"}      # żółty, szary, czerwony
_TOKEN = {"t": 0.0, "token": None}


def skonfigurowany():
    return (KLUCZ.exists() and KONFIG.exists()) or (OAUTH_KLIENT.exists() and OAUTH_TOKEN.exists())


def _klient():
    d = json.loads(OAUTH_KLIENT.read_text(encoding="utf-8"))
    return d.get("web") or d.get("installed")


def adres_autoryzacji():
    k = _klient()
    return k["auth_uri"] + "?" + urllib.parse.urlencode({
        "client_id": k["client_id"], "redirect_uri": PRZEKIEROWANIE, "response_type": "code", "scope": ZAKRES_APP,
        "access_type": "offline", "prompt": "consent"})


def wymien_kod(kod_albo_adres):
    """kod z przekierowania (albo cały adres http://localhost:8765/?code=…) -> refresh_token zapisany w oauth-token.json"""
    kod = kod_albo_adres.strip()
    if "code=" in kod:
        kod = urllib.parse.parse_qs(urllib.parse.urlparse(kod).query)["code"][0]
    k = _klient()
    dane = urllib.parse.urlencode({"code": kod, "client_id": k["client_id"], "client_secret": k["client_secret"],
                                   "redirect_uri": PRZEKIEROWANIE, "grant_type": "authorization_code"}).encode()
    with urllib.request.urlopen(urllib.request.Request(k["token_uri"], data=dane), timeout=30) as r:
        d = json.loads(r.read())
    if not d.get("refresh_token"):
        raise RuntimeError("Google nie zwrócił refresh_token (spróbuj jeszcze raz z nowym linkiem)")
    OAUTH_TOKEN.write_text(json.dumps({"refresh_token": d["refresh_token"]}), encoding="utf-8")
    OAUTH_TOKEN.chmod(0o600)
    return True


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def token():
    """token dostępu (1 h) z konta usługi: JWT podpisany kluczem prywatnym -> oauth2.googleapis.com/token"""
    if _TOKEN["token"] and time.time() < _TOKEN["t"] - 120:
        return _TOKEN["token"]
    if not KLUCZ.exists():                          # klient OAuth: odświeżenie tokenem z jednorazowej autoryzacji
        k = _klient()
        dane = urllib.parse.urlencode({"client_id": k["client_id"], "client_secret": k["client_secret"], "grant_type": "refresh_token",
                                       "refresh_token": json.loads(OAUTH_TOKEN.read_text(encoding="utf-8"))["refresh_token"]}).encode()
        with urllib.request.urlopen(urllib.request.Request(k["token_uri"], data=dane), timeout=30) as r:
            d = json.loads(r.read())
        _TOKEN.update(token=d["access_token"], t=time.time() + d.get("expires_in", 3600))
        return _TOKEN["token"]
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    k = json.loads(KLUCZ.read_text(encoding="utf-8"))
    teraz = int(time.time())
    naglowek = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    tresc = _b64(json.dumps({"iss": k["client_email"], "scope": "https://www.googleapis.com/auth/calendar.events",
                             "aud": k["token_uri"], "iat": teraz, "exp": teraz + 3600}).encode())
    klucz = serialization.load_pem_private_key(k["private_key"].encode(), password=None)
    podpis = _b64(klucz.sign(f"{naglowek}.{tresc}".encode(), padding.PKCS1v15(), hashes.SHA256()))
    dane = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                   "assertion": f"{naglowek}.{tresc}.{podpis}"}).encode()
    with urllib.request.urlopen(urllib.request.Request(k["token_uri"], data=dane), timeout=30) as r:
        d = json.loads(r.read())
    _TOKEN.update(token=d["access_token"], t=time.time() + d.get("expires_in", 3600))
    return _TOKEN["token"]


def _api(metoda, sciezka, dane=None, param=None):
    url = API + sciezka + ("?" + urllib.parse.urlencode(param) if param else "")
    for proba in range(4):
        req = urllib.request.Request(url, method=metoda, data=json.dumps(dane).encode() if dane is not None else None,
                                     headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                tekst = r.read()
                return json.loads(tekst) if tekst else {}
        except urllib.error.HTTPError as ex:
            if ex.code in (429, 500, 502, 503) or (ex.code == 403 and b"rateLimit" in ex.read()):
                time.sleep(2 ** (proba + 1))
                continue
            raise


def id_wydarzenia(lekcja):
    """stały identyfikator Google (znaki a-v, 0-9): ta sama lekcja = to samo wydarzenie"""
    h = hashlib.sha1(f"{lekcja['data']}|{lekcja['od']}|{lekcja.get('grupa', '')}".encode()).digest()
    return "mobi" + base64.b32hexencode(h).decode().lower().rstrip("=")


def wydarzenia(stan_mobi, ust):
    """plan z Mobidziennika (stan.json) -> {id: wydarzenie Google} od dziś"""
    dzis = date.today().isoformat()
    spr = list((stan_mobi.get("sprawdziany") or {}).values())
    zadania = stan_mobi.get("zadania") or []
    wyn = {}
    for x in stan_mobi.get("plan", []):
        if x["data"] < dzis or not x.get("od") or not x.get("do"):
            continue
        status = x.get("status", "lekcja")
        if status == "odwołana" and ust.get("odwolane", "pokazuj") == "usuń":
            continue
        s = next((y for y in spr if y["data"] == x["data"] and y.get("godzina") == x["od"]), None) if ust.get("sprawdziany", True) else None
        zd = [y for y in zadania if y.get("termin") == x["data"] and (y.get("godzina") == x["od"] if y.get("godzina") else y.get("przedmiot") == x["przedmiot"])]
        tytul = x["przedmiot"]
        if status == "zastępstwo":
            tytul += " (zastępstwo)"
        if status == "odwołana":
            tytul = f"❌ {tytul} (odwołana)"
        if s:
            tytul = f"📝 {s.get('rodzaj', 'sprawdzian').capitalize()}: {tytul}"
        opis = [v for v in (x.get("nauczyciel"), x.get("zamiast") and f"zamiast: {x['zamiast']}", x.get("info"),
                            s and f"{s.get('rodzaj', 'sprawdzian')}: {s.get('tematyka', '')}") if v]
        opis += [f"🏠 Zadanie domowe: {y.get('tresc', '')}" for y in zd]
        w = {"summary": tytul, "location": f"sala {x['sala']}" if x.get("sala") else "",
             "description": "\n".join(opis) + "\n\n(z Mobidziennika, aktualizowane automatycznie przez serwerek)",
             "start": {"dateTime": f"{x['data']}T{x['od']}:00", "timeZone": STREFA},
             "end": {"dateTime": f"{x['data']}T{x['do']}:00", "timeZone": STREFA},
             "transparency": "transparent" if status == "odwołana" else "opaque",
             "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": int(ust["przypomnienie"])}]
                           if int(ust.get("przypomnienie", 0)) else []}}
        kolor = KOLOR.get("sprawdzian" if s else status)
        if kolor:
            w["colorId"] = kolor
        h = hashlib.sha1(json.dumps(w, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        w["extendedProperties"] = {"private": {"zrodlo": ZRODLO, "h": h}}
        wyn[id_wydarzenia(x)] = w
    return wyn


def synchronizuj(stan_mobi, ust):
    """wydarzenia z planu -> kalendarz Google: dodaj / zmień / usuń tylko nasze, od dziś do końca znanego planu"""
    if not skonfigurowany():
        return None
    if not KONFIG.exists():                         # OAuth: aplikacja sama tworzy swój kalendarz „Plan lekcji”
        k = _api("POST", "/calendars", {"summary": "Plan lekcji", "description": "Z Mobidziennika (serwerek, automatycznie)",
                                        "timeZone": STREFA})
        KONFIG.write_text(json.dumps({"id": k["id"]}), encoding="utf-8")
    kal = urllib.parse.quote(json.loads(KONFIG.read_text(encoding="utf-8"))["id"], safe="")
    chce = wydarzenia(stan_mobi, ust)
    dni = sorted(x["data"] for x in stan_mobi.get("plan", []))
    od = date.today().isoformat()
    do = max(dni[-1] if dni else od, od)
    jest, strona = {}, None
    while True:
        p = {"timeMin": f"{od}T00:00:00+00:00", "timeMax": f"{(date.fromisoformat(do) + timedelta(days=1)).isoformat()}T23:59:00+00:00",
             "privateExtendedProperty": f"zrodlo={ZRODLO}", "singleEvents": "true", "maxResults": "250", "showDeleted": "true"}
        if strona:
            p["pageToken"] = strona
        d = _api("GET", f"/calendars/{kal}/events", param=p)
        for e in d.get("items", []):
            jest[e["id"]] = e
        strona = d.get("nextPageToken")
        if not strona:
            break
    dodane = zmienione = usuniete = 0
    for eid, w in chce.items():
        e = jest.get(eid)
        if e and e.get("status") != "cancelled" and (e.get("extendedProperties") or {}).get("private", {}).get("h") == w["extendedProperties"]["private"]["h"]:
            continue
        if e:                                   # zmiana (albo przywrócenie wcześniej usuniętego): pełna podmiana
            _api("PUT", f"/calendars/{kal}/events/{eid}", {**w, "id": eid, "status": "confirmed"})
            zmienione += 1
        else:
            try:
                _api("POST", f"/calendars/{kal}/events", {**w, "id": eid})
            except urllib.error.HTTPError as ex:
                if ex.code != 409:              # 409: id już kiedyś użyte (usunięte poza oknem listy) -> podmień
                    raise
                _api("PUT", f"/calendars/{kal}/events/{eid}", {**w, "id": eid, "status": "confirmed"})
            dodane += 1
        time.sleep(0.15)
    for eid, e in jest.items():
        if eid not in chce and e.get("status") != "cancelled" and e["start"].get("dateTime", "")[:10] >= od:
            _api("DELETE", f"/calendars/{kal}/events/{eid}")
            usuniete += 1
            time.sleep(0.15)
    wynik = {"czas": datetime.now().isoformat(timespec="seconds"), "dodane": dodane, "zmienione": zmienione,
             "usuniete": usuniete, "wszystkie": len(chce), "blad": None}
    KAT.mkdir(exist_ok=True)
    STAN.write_text(json.dumps(wynik, ensure_ascii=False), encoding="utf-8")
    return wynik


def zapisz_blad(opis):
    KAT.mkdir(exist_ok=True)
    try:
        s = json.loads(STAN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        s = {}
    s.update(blad=opis[:300], czas_bledu=datetime.now().isoformat(timespec="seconds"))
    STAN.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["link"]:
        print(adres_autoryzacji())
    elif sys.argv[1:2] == ["kod"]:
        print("OK" if wymien_kod(sys.argv[2]) else "?")
