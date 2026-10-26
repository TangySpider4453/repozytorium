"""
intervals.icu w bocie (TYLKO odczyt, co 5 min): zaplanowane treningi na dziś i najbliższe dni oraz wykonane aktywności.
Poranny bieg (Run/TrailRun/VirtualRun/Treadmill, start przed POZNO) -> zadanie „Weź kreatynę” z dzwonieniem
10 min po końcu biegu (raz na dzień), chyba że Antek wyłączył to na stronie „Automatyczne” (np. wyjazd bez kreatyny).

Klucz: INTERVALS_API_KEY (i opcjonalnie INTERVALS_ATLETA, domyślnie „0” = właściciel klucza) w
/etc/serwerek-bot/intervals.env (root 600, EnvironmentFile bota). Stan: ~/bot/intervals/stan.json,
ustawienia (włącznik kreatyny, minuty po biegu, „poranny do”): moduł „treningi” w /api/automaty (portal).
"""
import base64
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

KAT = Path(__file__).resolve().parent / "intervals"
API = "https://intervals.icu/api/v1"
CO = 300                        # s między sprawdzeniami
PO_BIEGU = 10                   # min po końcu biegu -> telefon o kreatynie
POZNO = 12                      # bieg zaczęty przed tą godziną = poranny
BIEGI = {"Run", "TrailRun", "VirtualRun", "Treadmill"}
OSTATNIO = {"t": 0.0}


def skonfigurowany():
    return bool(os.environ.get("INTERVALS_API_KEY"))


def _get(sciezka, **param):
    url = f"{API}/athlete/{os.environ.get('INTERVALS_ATLETA', '0')}{sciezka}?" + urllib.parse.urlencode(param)
    klucz = base64.b64encode(f"API_KEY:{os.environ['INTERVALS_API_KEY']}".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {klucz}", "Accept": "application/json",
                                               "User-Agent": "serwerek-raspberry"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _czytaj(nazwa, domyslnie):
    try:
        return json.loads((KAT / nazwa).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return domyslnie


def _zapisz(nazwa, dane):
    KAT.mkdir(exist_ok=True)
    tmp = KAT / (nazwa + ".tmp")
    tmp.write_text(json.dumps(dane, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, KAT / nazwa)


def stan():
    return _czytaj("stan.json", {})


def _trening(e):
    return {"data": (e.get("start_date_local") or "")[:10], "nazwa": (e.get("name") or "Trening").strip(),
            "typ": e.get("type") or "", "opis": (e.get("description") or "").strip(),
            "czas_min": round((e.get("moving_time") or 0) / 60) or None,
            "dystans_km": round(e["distance"] / 1000, 1) if e.get("distance") else None}


def _aktywnosc(a):
    start = a.get("start_date_local") or ""
    dl = a.get("elapsed_time") or a.get("moving_time") or 0
    try:
        koniec = (datetime.fromisoformat(start[:19]) + timedelta(seconds=dl)).isoformat(timespec="minutes")
    except ValueError:
        koniec = None
    return {"id": str(a.get("id")), "nazwa": a.get("name") or "", "typ": a.get("type") or "", "start": start[:16],
            "koniec": koniec, "czas_min": round(dl / 60), "dystans_km": round((a.get("distance") or 0) / 1000, 1)}


def sprawdz(dodaj_kreatyne, u=None):
    """odczyt z intervals.icu, zapis stanu; dodaj_kreatyne(termin "RRRR-MM-DDTHH:MM", opis) przy porannym biegu.
    u = ustawienia „treningi” z portalu (kreatyna, po_biegu, poranny_do)"""
    u = u or {}
    dzis = date.today()
    # zakres dla kalendarza: plan ±5 tygodni, wykonane 5 tygodni wstecz
    plan = _get("/events", oldest=(dzis - timedelta(days=35)).isoformat(), newest=(dzis + timedelta(days=35)).isoformat(), category="WORKOUT")
    akt = _get("/activities", oldest=(dzis - timedelta(days=35)).isoformat(), newest=dzis.isoformat())
    st = stan()
    st.update({"czas": datetime.now().isoformat(timespec="seconds"), "blad": None,
               "treningi": [_trening(e) for e in plan if isinstance(e, dict)],
               "kalendarz_aktywnosci": sorted((_aktywnosc(a) for a in akt if isinstance(a, dict)), key=lambda a: a["start"])})
    st["aktywnosci"] = st["kalendarz_aktywnosci"][-10:]
    zrobione = st.setdefault("kreatyna", {})            # data -> id biegu, po którym już przypomniano (raz na dzień)
    for a in st["aktywnosci"]:
        if a["typ"] not in BIEGI or not a["koniec"] or a["start"][:10] != dzis.isoformat() or zrobione.get(a["start"][:10]):
            continue
        if int(a["start"][11:13]) >= u.get("poranny_do", POZNO):
            continue
        termin = datetime.fromisoformat(a["koniec"]) + timedelta(minutes=u.get("po_biegu", PO_BIEGU))
        if datetime.now() - termin > timedelta(hours=1):        # bieg zsynchronizowany dużo później albo przerwa w działaniu
            zrobione[a["start"][:10]] = a["id"]
            continue
        if u.get("kreatyna", True):
            termin = max(termin, datetime.now() + timedelta(minutes=1))
            dodaj_kreatyne(termin.strftime("%Y-%m-%dT%H:%M"), f"{a['nazwa'] or 'bieg'}, {a['dystans_km']} km, koniec {a['koniec'][11:16]}")
        zrobione[a["start"][:10]] = a["id"]
    for d in [d for d in zrobione if d < (dzis - timedelta(days=14)).isoformat()]:
        del zrobione[d]
    _zapisz("stan.json", st)
    OSTATNIO["t"] = time.time()
    return st


def blad(opis):
    st = stan()
    st["blad"] = opis
    st["czas_bledu"] = datetime.now().isoformat(timespec="seconds")
    _zapisz("stan.json", st)


def treningi_na(d, szczegoly=False):
    """treningi zaplanowane na dzień d -> tekst albo None (szczegoly=False: same nazwy, np. do budzika)"""
    l = [t for t in stan().get("treningi", []) if t["data"] == d.isoformat()]
    if not l:
        return None
    if not szczegoly:
        return ", ".join(t["nazwa"] for t in l)
    out = []
    for t in l:
        info = ", ".join(x for x in (t["typ"], f"{t['czas_min']} min" if t["czas_min"] else "",
                                     f"{t['dystans_km']} km" if t["dystans_km"] else "") if x)
        out.append(f"• {t['nazwa']}" + (f" ({info})" if info else "") + (f"\n{t['opis']}" if t["opis"] else ""))
    return "\n".join(out)
