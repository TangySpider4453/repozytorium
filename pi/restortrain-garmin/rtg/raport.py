"""
Raporty ze zrobionych treningów siłowych (Garmin -> tekst do wklejenia w RestOrTrain).

Garmin przy każdej serii aktywności (`/activity-service/activity/<id>/exerciseSets`) podaje `wktStepIndex`: numer kroku
treningu w kolejności z zegarka (FIT: najpierw kroki z grupy serii, potem sam krok powtórzenia). Dzięki temu serię da
się przypisać do konkretnego ćwiczenia z planu (nazwa z kroku „Przygotuj: …”, plan z opisu kroku), łącznie z tym, czego
nie zrobiono. Aktywność bez naszego treningu (np. oryginał RestOrTrain albo trening „z ręki”): serie grupowane po
nazwie ćwiczenia Garmin, polska nazwa z exercises.yaml.

Wynik: data/raporty/<activityId>.json {id, data, start, tytul, minuty, tekst, wyslany}; po nowym treningu (start
< 12 h temu) tekst idzie na Linphone przez bota. Plany treningów do zrobienia: data/plany/<workoutId>.json.
Tylko odczyt z Garmina.
"""
import json
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from .mapping import wczytaj
from .parser import ROTACJA, normalizuj
from .powiadom import powiadom

log = logging.getLogger("rtg.raport")


def api(*a, **kw):                          # leniwy import: testy bez biblioteki garminconnect
    from .garmin import api as _api
    return _api(*a, **kw)
KAT = Path(__file__).resolve().parent.parent
RAPORTY = KAT / "data" / "raporty"
PLANY = KAT / "data" / "plany"
SILOWY = "strength_training"
SWIEZY_H = 12                       # po takim czasie od startu treningu już nie wysyłamy (np. pierwsze uruchomienie)
ODSWIEZ_DNI = 2                     # raporty z ostatnich dni są odświeżane (poprawki ciężarów w Garmin Connect)


# ---------------------------------------------------------------- plan z treningu Garmin (nasz wygenerowany)

def indeksy_fit(kroki):
    """[(indeks na zegarku, krok, grupa serii albo None)]: w grupie najpierw dzieci, potem krok powtórzenia"""
    wynik = []

    def idz(ks, grupa):
        for k in ks:
            if k["type"] == "RepeatGroupDTO":
                idz(k.get("workoutSteps", []), k)
                wynik.append((len(wynik), k, grupa))
            else:
                wynik.append((len(wynik), k, grupa))
    idz(kroki, None)
    return wynik


def _kg(x):
    return f"{x:g}".replace(".", ",") + " kg"


def plan_z_treningu(w):
    """trening Garmin (nasz) -> [{nazwa, plan, serie, strony, indeksy: [fit…], rozgrzewka}] w kolejności treningu"""
    kroki = w["workoutSegments"][0]["workoutSteps"]
    fit = indeksy_fit(kroki)
    po_kroku = {id(k): i for i, k, _ in fit}
    pozycje, nazwa, szczegol = [], None, ""
    for k in kroki:
        opis = k.get("description") or ""
        if k["type"] == "ExecutableStepDTO" and opis.startswith("Przygotuj: "):
            m = re.match(r"Przygotuj: (.+?)(?: \((.*)\))?$", opis, re.S)
            nazwa, szczegol = (m.group(1), m.group(2) or "") if m else (opis[11:], "")
            continue
        if k["type"] != "RepeatGroupDTO":
            continue
        cw = [x for x in k["workoutSteps"] if x.get("stepType", {}).get("stepTypeKey") == "interval"]
        if not cw:
            continue
        rozgrzewka = (cw[0].get("description") or "").startswith("seria rozgrzewkowa")
        nazwy = (nazwa or "").split(" + ") if nazwa else []
        # ćwiczenia w grupie: kolejne kroki interval; lewa/prawa tego samego ćwiczenia to jedno ćwiczenie
        grupy = []
        for x in cw:
            strona = re.match(r"(Lewa|Prawa) (noga|ręka|strona): ", x.get("description") or "")
            if strona and strona.group(1) == "Prawa" and grupy:
                grupy[-1]["indeksy"].append(po_kroku[id(x)])
                grupy[-1]["strony"] = strona.group(2)
                continue
            na = re.match(r"Na (nogę|rękę|stronę): ", x.get("description") or "")
            gr_na = {"nogę": "noga", "rękę": "ręka", "stronę": "strona"}[na.group(1)] if na else None
            obie = bool(na) and "(razem obie:" in (x.get("description") or "")   # cel = obie strony razem (całe ciało)
            grupy.append({"krok": x, "indeksy": [po_kroku[id(x)]], "strony": None, "razem": gr_na, "obie": obie})
        for j, gr in enumerate(grupy):
            x = gr["krok"]
            n = nazwy[j] if j < len(nazwy) else (x.get("exerciseName") or "ćwiczenie").replace("_", " ").lower()
            ile = x.get("endConditionValue")
            if gr.get("obie") and ile:
                ile = ile / 2                       # cel kroku = obie strony razem -> plan na stronę
            # wynik dzielimy tylko w ćwiczeniach całym ciałem (woodchop itd.); stare treningi miały „razem obie” też
            # przy rękach i nogach, a tam Antek wpisuje wynik na jedną stronę
            gr["obie"] = gr.get("obie") and bool(re.search(ROTACJA, normalizuj(f"{n} {x.get('exerciseName') or ''}".replace("_", " "))))
            kg = (x.get("weightValue") or 0) / 1000
            if len(grupy) > 1:
                plan = f"{k['numberOfIterations']} rundy" + (f", {int(ile)} powt." if ile and x["endCondition"]["conditionTypeKey"] == "reps" else "")
            else:
                plan = szczegol.split(",")[0] if szczegol else f"{k['numberOfIterations']} serie"
            if kg and "kg" not in plan:
                plan += f", {_kg(kg)}"
            pozycje.append({"nazwa": n + (" – rozgrzewka" if rozgrzewka else ""), "plan": plan, "serie": k["numberOfIterations"],
                            "strony": gr["strony"], "razem": gr.get("razem"), "obie": gr.get("obie"), "indeksy": gr["indeksy"], "rozgrzewka": rozgrzewka})
    return pozycje


def tekst_planu(w):
    """plan treningu do wyświetlenia (strona: treningi do zrobienia)"""
    linie = [w.get("workoutName") or "Trening"]
    for k in w["workoutSegments"][0]["workoutSteps"]:
        o = k.get("description") or ""
        if k["type"] == "ExecutableStepDTO" and k["stepType"]["stepTypeKey"] in ("warmup", "cooldown"):
            linie.append(f"- {o} ({int((k.get('endConditionValue') or 0) // 60)} min)")
        elif o.startswith("Przygotuj: "):
            linie.append("- " + o[11:])
    return "\n".join(linie)


# ---------------------------------------------------------------- raport

def _seria(s):
    """'10×50 kg' / '10' / '?'"""
    r = s.get("repetitionCount")
    kg = (s.get("weight") or 0) / 1000
    t = str(r) if r else "?"
    return f"{t}×{_kg(kg)}" if kg else t


def _seria_pol(s):
    """całe ciało liczone razem: 24 powtórzenia obu stron -> „12” na stronę (nieparzyste: 12,5)"""
    r = s.get("repetitionCount")
    kg = (s.get("weight") or 0) / 1000
    t = (f"{r / 2:g}".replace(".", ",")) if r else "?"
    return f"{t}×{_kg(kg)}" if kg else t


def _seria_obu(lewa, prawa, strona):
    """lewa/prawa w jednej serii: brak ciężaru po jednej stronie = ten sam co po drugiej"""
    kg = (prawa or {}).get("weight") or (lewa or {}).get("weight") or 0
    r = lambda s: str(s.get("repetitionCount")) if s and s.get("repetitionCount") else "?"
    l, p = ("L", "P")
    return f"{l} {r(lewa)} / {p} {r(prawa)}" + (f" × {_kg(kg / 1000)}" if kg else "")


def raport(akt, sety, trening=None, nazwy_pl=None):
    """tekst do RestOrTrain: zrobione (serie, powtórzenia, ciężar) i niezrobione z planu"""
    start = datetime.fromisoformat(akt["startTimeLocal"])
    minuty = round((akt.get("duration") or 0) / 60)
    aktywne = [s for s in sety if s.get("setType") == "ACTIVE"]
    linie = [f"{akt.get('activityName') or 'Trening siłowy'} – {start.strftime('%d.%m.%Y')} ({start.strftime('%H:%M')}, {minuty} min)", ""]
    zrobione, niezrobione = [], []
    if trening:
        po_indeksie = {}
        for s in aktywne:
            po_indeksie.setdefault(s.get("wktStepIndex"), []).append(s)
        uzyte = set()
        for p in plan_z_treningu(trening):
            if p["strony"]:
                lewe, prawe = (po_indeksie.get(p["indeksy"][0], []), po_indeksie.get(p["indeksy"][1], []) if len(p["indeksy"]) > 1 else [])
                n = max(len(lewe), len(prawe))
                opis = [_seria_obu(lewe[i] if i < len(lewe) else None, prawe[i] if i < len(prawe) else None, p["strony"]) for i in range(n)]
            elif p.get("obie"):                 # całe ciało (woodchop): zegarek liczy obie strony -> na stronę = połowa
                ss = [s for i in p["indeksy"] for s in po_indeksie.get(i, [])]
                n, opis = len(ss), [_seria_pol(s) for s in ss]
            else:                               # ręce / nogi: Antek wpisuje wynik na jedną stronę
                ss = [s for i in p["indeksy"] for s in po_indeksie.get(i, [])]
                n, opis = len(ss), [_seria(s) for s in ss]
            uzyte |= set(p["indeksy"])
            if not n:
                if not p["rozgrzewka"]:
                    niezrobione.append(f"- {p['nazwa']} (plan: {p['plan']})")
                continue
            brak = f" — {n} z {p['serie']} serii" if n < p["serie"] and not p["rozgrzewka"] else ""
            st = p["strony"] or p.get("razem")
            zrobione.append(f"- {p['nazwa']}{' (na ' + {'noga': 'nogę', 'ręka': 'rękę'}.get(st, 'stronę') + ')' if st else ''}: "
                            f"{', '.join(opis)} (plan: {p['plan']}){brak}")
        # serie spoza planu (ćwiczenie dodane na zegarku)
        reszta = [s for s in aktywne if s.get("wktStepIndex") not in uzyte and s.get("exercises") and (s["exercises"][0].get("name"))]
        zrobione += _po_nazwie(reszta, nazwy_pl, dopisek=" (poza planem)")
    else:
        zrobione = _po_nazwie([s for s in aktywne if s.get("exercises") and s["exercises"][0].get("name")], nazwy_pl)
    if not zrobione and not niezrobione:
        linie.append("Garmin nie zapisał serii (trening z oryginału RestOrTrain: jeden krok na czas, bez ćwiczeń).")
        return "\n".join(linie), start, minuty
    linie += ["Zrobione:"] + (zrobione or ["- nic"])
    if niezrobione:
        linie += ["", "Niezrobione:"] + niezrobione
    return "\n".join(linie), start, minuty


def _po_nazwie(sety, nazwy_pl, dopisek=""):
    grupy = {}
    for s in sety:
        grupy.setdefault(s["exercises"][0]["name"], []).append(s)
    nazwy_pl = nazwy_pl or {}
    return [f"- {nazwy_pl.get(n, n.replace('_', ' ').lower())}{dopisek}: {', '.join(_seria(s) for s in ss)}" for n, ss in grupy.items()]


def nazwy_polskie():
    """exerciseName Garmin -> polska nazwa z exercises.yaml (pierwsza pasująca)"""
    wynik = {}
    try:
        for w in wczytaj():
            if w.get("exerciseName"):
                wynik.setdefault(w["exerciseName"], w["nazwa"].capitalize())
    except Exception:
        pass
    return wynik


def sprawdz_zrobione(g, cfg=None, ile=20):
    """nowe / świeże aktywności siłowe -> raporty; nowy trening (< 12 h) -> Linphone. Zwraca liczbę nowych raportów."""
    RAPORTY.mkdir(parents=True, exist_ok=True)
    akt = api(g, "GET", "/activitylist-service/activities/search/activities", params={"start": 0, "limit": ile})
    nowe, nazwy = 0, None
    for a in akt:
        if (a.get("activityType") or {}).get("typeKey") != SILOWY:
            continue
        plik = RAPORTY / f"{a['activityId']}.json"
        start = datetime.fromisoformat(a["startTimeLocal"])
        stary = json.loads(plik.read_text(encoding="utf-8")) if plik.exists() else None
        if stary and datetime.now() - start > timedelta(days=ODSWIEZ_DNI):
            continue
        sety = api(g, "GET", f"/activity-service/activity/{a['activityId']}/exerciseSets").get("exerciseSets") or []
        trening = None
        if a.get("workoutId"):
            try:
                trening = api(g, "GET", f"/workout-service/workout/{a['workoutId']}")
                if not any(k["type"] == "RepeatGroupDTO" for k in trening["workoutSegments"][0]["workoutSteps"]):
                    trening = None              # oryginał RestOrTrain (jeden krok na czas): bez planu kroków
            except Exception:
                trening = None                  # trening usunięty: serie po nazwach
        nazwy = nazwy or nazwy_polskie()
        tekst, start, minuty = raport(a, sety, trening, nazwy)
        wyslany = (stary or {}).get("wyslany", False)
        d = {"id": a["activityId"], "data": start.strftime("%Y-%m-%d"), "start": start.strftime("%H:%M"),
             "tytul": a.get("activityName") or "Trening siłowy", "minuty": minuty, "tekst": tekst, "wyslany": wyslany,
             "z_planem": trening is not None, "zaktualizowano": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if not stary:
            nowe += 1
        if not wyslany and datetime.now() - start < timedelta(hours=SWIEZY_H) and sety \
                and (cfg or {}).get("raport_linphone", True):
            wyslij(tekst)
            d["wyslany"] = True
        elif not wyslany and datetime.now() - start >= timedelta(hours=SWIEZY_H):
            d["wyslany"] = "pominiety"          # stary trening: tylko na stronie
        tmp = plik.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(plik)
        time.sleep(0.3)
    return nowe


def wyslij(tekst):
    """na Linphone (bot przyjmuje do 1500 znaków w jednej wiadomości): dłuższy raport w częściach po liniach"""
    czesci, biez = [], ""
    for linia in ("🏋 Raport do RestOrTrain:\n" + tekst).splitlines():
        if len(biez) + len(linia) + 1 > 1400 and biez:
            czesci.append(biez)
            biez = ""
        biez += linia + "\n"
    czesci.append(biez)
    for i, c in enumerate(czesci):
        powiadom(c.rstrip() + (f"\n({i + 1}/{len(czesci)})" if len(czesci) > 1 else ""))
        time.sleep(0.01)


def zapisz_plany(g, db):
    """plany treningów do zrobienia (nasze wygenerowane), raz na trening: data/plany/<id>.json"""
    PLANY.mkdir(parents=True, exist_ok=True)
    aktualne = set()
    for d, tytul, wid in db.execute("SELECT date, title, generated_workout_id FROM treningi WHERE date >= ? AND status='ok'",
                                    (time.strftime("%Y-%m-%d"),)):
        if not wid:
            continue
        aktualne.add(f"{wid}.json")
        p = PLANY / f"{wid}.json"
        if p.exists():
            continue
        try:
            w = api(g, "GET", f"/workout-service/workout/{wid}")
        except Exception:
            continue
        p.write_text(json.dumps({"id": wid, "data": d, "tytul": tytul, "tekst": tekst_planu(w)}, ensure_ascii=False), encoding="utf-8")
    for p in PLANY.glob("*.json"):              # stare plany (przebudowane albo minione)
        if p.name not in aktualne:
            p.unlink(missing_ok=True)
