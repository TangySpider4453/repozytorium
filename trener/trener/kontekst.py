"""Zwięzły obraz danych dla Claude: ostatnie dni, aktywności, tygodnie, miesiące z całej historii, plan."""
import json
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean

from . import baza, config, dane


def kategoria(typ):
    t = typ or ""
    if any(x in t for x in ("cycl", "biking", "bike", "ride", "bmx")):
        return "rower"
    if "run" in t:
        return "bieg"
    if t == "strength_training":
        return "silka"
    return "inne"


def _sr(xs, n=1):
    xs = [x for x in xs if x is not None]
    return round(mean(xs), n) if xs else None


def hm(h):
    """7.57 → '7:34' (czas w godzinach:minutach, żeby Claude nie pisał ułamków godzin)"""
    if h is None:
        return "?"
    m = round(h * 60)
    return f"{m // 60}:{m % 60:02d}"


def wiersz_dnia(d):
    w = d
    tr = "; ".join(f"{t['nazwa']} {t['min']}min{(' ' + str(t['km']) + 'km') if t.get('km') else ''} obc{t.get('obc')}"
                   for t in w.get("treningi", []))
    pola = [z_dniem(w["dzien"]),
            f"sen {hm(w.get('sen_h'))} h wynik {w.get('sen_wynik')} (głęb {hm(w.get('sen_gleboki_h'))} REM {hm(w.get('sen_rem_h'))}) {w.get('sen_od')}-{w.get('sen_do')}" if w.get("sen_h") else "sen brak",
            f"HRV {w.get('hrv')} (7d {w.get('hrv_7d')}, {w.get('hrv_status')}, norma {w.get('hrv_norma')})" if w.get("hrv") else "",
            f"tętno spocz {w.get('tetno_spocz')}" if w.get("tetno_spocz") else "",
            f"BB rano {w.get('bb_rano')} max {w.get('bb_max')}" if w.get("bb_max") else "",
            f"stres {w.get('stres')}" if w.get("stres") else "",
            f"gotowość {w.get('gotowosc')} {w.get('gotowosc_poziom', '')}" if w.get("gotowosc") is not None else "",
            f"obc ostre {w.get('obc_ostre')}/przewl {w.get('obc_przewlekle')} status {w.get('status')}" if w.get("obc_ostre") else "",
            f"treningi: {tr}" if tr else "bez treningu"]
    return " | ".join(p for p in pola if p)


def ostatnie_dni(db, n=14):
    dzis = date.today()
    return [wiersz_dnia(d) for d in baza.dni_zakres(db, (dzis - timedelta(days=n - 1)).isoformat(), dzis.isoformat())]


def aktywnosci(db, od, do=None):
    do = do or date.today().isoformat()
    w = []
    for r in db.execute("SELECT dane, szczegoly, typ FROM aktywnosci WHERE dzien BETWEEN ? AND ? ORDER BY start", (od, do)):
        s = dane.streszczenie_aktywnosci(baza.rozpakuj(r[0]))
        if r[2] == "strength_training" and r[1]:
            s["cwiczenia"] = cwiczenia_silki(baza.rozpakuj(r[1]))
        w.append(s)
    return w


def cwiczenia_silki(sz):
    """serie z aktywności siłowej: nazwa → [powt×kg]"""
    wyn = defaultdict(list)
    for s in (sz or {}).get("exerciseSets") or []:
        if s.get("setType") != "ACTIVE":
            continue
        cw = ((s.get("exercises") or [{}])[0] or {})
        nazwa = (cw.get("name") or cw.get("category") or "?").lower()
        kg = (s.get("weight") or 0) / 1000
        wyn[nazwa].append(f"{s.get('repetitionCount') or '?'}" + (f"×{kg:g}kg" if kg else ""))
    return {k: ", ".join(v) for k, v in wyn.items()}


def agregaty(db, okres="tydzien", od=None):
    """per tydzień/miesiąc: godziny i km per sport, obciążenie, średni sen, HRV, tętno spoczynkowe, VO2"""
    grupy = defaultdict(lambda: {"h": defaultdict(float), "km": defaultdict(float), "n": defaultdict(int), "obc": 0,
                                 "sen": [], "hrv": [], "rhr": [], "vo2": []})
    klucz = (lambda d: (d - timedelta(days=d.weekday())).isoformat()) if okres == "tydzien" else (lambda d: d.isoformat()[:7])
    for r in db.execute("SELECT dzien, typ, dane FROM aktywnosci WHERE dzien >= ?", (od or "2000-01-01",)):
        j = baza.rozpakuj(r[2]) or {}
        g = grupy[klucz(date.fromisoformat(r[0]))]
        k = kategoria(r[1])
        g["h"][k] += (j.get("duration") or 0) / 3600
        g["km"][k] += (j.get("distance") or 0) / 1000
        g["n"][k] += 1
        g["obc"] += j.get("activityTrainingLoad") or 0
    for r in db.execute("SELECT dzien, dane FROM dni WHERE dzien >= ?", (od or "2000-01-01",)):
        w = json.loads(r[1])
        g = grupy[klucz(date.fromisoformat(r[0]))]
        g["sen"].append(w.get("sen_h"))
        g["hrv"].append(w.get("hrv"))
        g["rhr"].append(w.get("tetno_spocz"))
        g["vo2"].append(w.get("vo2_rower"))
    wyn = []
    for k in sorted(grupy):
        g = grupy[k]
        sporty = ", ".join(f"{s} {g['n'][s]}× {hm(g['h'][s])} h" + (f" {g['km'][s]:.0f}km" if g["km"][s] >= 1 else "")
                           for s in sorted(g["h"], key=lambda s: -g["h"][s]))
        wyn.append(f"{k}: {sporty or 'bez treningów'} | obc {g['obc']:.0f} | sen {hm(_sr(g['sen'], 2))} h HRV {_sr(g['hrv'], 0)} "
                   f"RHR {_sr(g['rhr'], 0)} VO2rower {_sr(g['vo2'])}")
    return wyn


DNI_TYG = ['pon', 'wt', 'śr', 'czw', 'pt', 'sob', 'ndz']


DNI_PELNE = ['poniedziałek', 'wtorek', 'środa', 'czwartek', 'piątek', 'sobota', 'niedziela']


def z_dniem(iso):
    """2026-11-19 → '2026-11-19 czw JUTRO' (dzień tygodnia + względem dziś, żeby model nie mylił dni)"""
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return iso
    r = (d - date.today()).days
    wzgl = {0: " DZIŚ", 1: " JUTRO", -1: " WCZORAJ", 2: " POJUTRZE"}.get(r, "")
    return f"{iso} {DNI_TYG[d.weekday()]}{wzgl}"


def slownie(iso):
    """dzień dla Antka: dziś / jutro / wczoraj / pojutrze / czwartek; dalej niż tydzień: 'czwartek 26.11'"""
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return iso
    r = (d - date.today()).days
    if r in (-1, 0, 1, 2):
        return {0: "dziś", 1: "jutro", -1: "wczoraj", 2: "pojutrze"}[r]
    n = DNI_PELNE[d.weekday()]
    return n if -7 < r < 7 else f"{n} {d.day}.{d.month:02d}"


def plan_tekst(db, od, do):
    return [f"{z_dniem(r['dzien'])} [{r['sport']}] {r['tytul']} ({r['stan']}): {r['opis'] or ''}"
            for r in db.execute("SELECT * FROM plan WHERE dzien BETWEEN ? AND ? AND stan != 'usuniety' ORDER BY dzien",
                                (od, do))]


def pelny(db, dni=14, akt_dni=28, tygodnie=16, cel=None):
    dzis = date.today()
    u = config.ustawienia()
    from datetime import datetime
    cz = [f"DZIŚ: {dzis.isoformat()} ({DNI_PELNE[dzis.weekday()]}), teraz godz. {datetime.now():%H:%M}. JUTRO: "
          f"{(dzis + timedelta(days=1)).isoformat()} ({DNI_PELNE[(dzis + timedelta(days=1)).weekday()]}). Pilnuj, o którym "
          "dniu mówisz: „dziś” to tylko DZIŚ; trening z planu na jutro nazywaj „jutro”, dalsze — dniem tygodnia.",
          f"CELE ANTKA: {u['cele'] or '(nie podał jeszcze — zapytaj / załóż ogólny rozwój formy kolarskiej)'}",
          f"DOSTĘPNOŚĆ: {u['dostepnosc'] or '(brak)'}", f"SPRZĘT: {u['sprzet'] or '(brak)'}",
          f"SPORTY DO PLANU: {', '.join(u['sporty'])}"]
    if u.get("wymagania"):
        cz.append("STAŁE WYMAGANIA ANTKA (niezmienne, mają pierwszeństwo przed makrocyklem, ankietą i wcześniejszymi "
                  "ustaleniami):\n" + u["wymagania"])
    if u.get("ankieta"):
        from .start import tekst_ankiety
        cz.append("ANKIETA ANTKA (jego odpowiedzi — szanuj preferencje co do wyglądu planu, długości, analiz):\n"
                  + tekst_ankiety(u["ankieta"]))
    from . import cel
    cz.append("MAKROCYKL (periodyzacja do celu, ▶ = bieżąca faza):\n" + cel.tekst(cel.makrocykl(db)))
    cz.append("PROGI:\n" + cel.progi(db))
    from . import dieta
    jedz = dieta.tekst(db)
    if jedz:
        cz.append("JEDZENIE I SKŁAD CIAŁA (dziennik w apce; cel liczy trener):\n" + jedz)
    pamiec = baza.kv(db, "pamiec_trenera", [])
    if pamiec:
        cz.append("ZAPAMIĘTANE USTALENIA Z ROZMÓW:\n" + "\n".join("- " + p for p in pamiec[-30:]))
    cz.append(f"\nOSTATNIE {dni} DNI (sen dotyczy nocy przed danym dniem):\n" + "\n".join(ostatnie_dni(db, dni)))
    cz.append(f"\nAKTYWNOŚCI OSTATNIE {akt_dni} DNI:\n" + "\n".join(
        json.dumps(a, ensure_ascii=False) for a in aktywnosci(db, (dzis - timedelta(days=akt_dni)).isoformat())))
    cz.append(f"\nTYGODNIE (ostatnie {tygodnie}):\n" + "\n".join(
        agregaty(db, "tydzien", (dzis - timedelta(weeks=tygodnie)).isoformat())))
    cz.append("\nMIESIĄCE (cała historia):\n" + "\n".join(agregaty(db, "miesiac")))
    prop = baza.kv(db, "propozycja_planu")
    if prop and prop.get("do", "") >= dzis.isoformat():
        cz.append("CZEKA NA DECYZJĘ ANTKA (propozycja po ocenie snu, jeszcze NIE wprowadzona — nie wprowadzaj jej sam): "
                  + prop.get("komentarz", "") + " | " + "; ".join(prop.get("zmiany", [])))
    pl = plan_tekst(db, (dzis - timedelta(days=7)).isoformat(), (dzis + timedelta(days=14)).isoformat())
    cz.append("\nPLAN (ostatni tydzień i następne 2 tygodnie):\n" + ("\n".join(pl) if pl else "(brak planu)"))
    return "\n".join(cz)
