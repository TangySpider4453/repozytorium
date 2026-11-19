"""Tierlista ćwiczeń siłowych Antka: S/A/B/C/X (X = wykluczone). Trzymana w ustawieniach (klucz "tierlista"),
plan jej używa, a po treningu siłowym apka pyta o ocenę ćwiczeń, których na liście jeszcze nie ma."""
import json
import re
from datetime import date, timedelta

from . import baza, budowa, config

TIERY = {"S": "S: priorytet, najbardziej lubiane", "A": "A: bardzo dobre, regularnie", "B": "B: zamienniki, uzupełnienie",
         "C": "C: tylko gdy trening/sprzęt wymaga", "X": "WYKLUCZONE / niepreferowane"}


def _norm(s):
    s = (s or "").lower().split(" — ")[0].split(",")[0].split("(")[0]
    return re.sub(r"\s+", " ", re.sub(r"[^\wąćęłńóśźż ]", " ", s)).strip()


def _kanon(s):
    """nazwa → nazwa kanoniczna z listy ćwiczeń Antka (aliasy), inaczej znormalizowana"""
    n = _norm(s)
    e = budowa.cwiczenia_antka().get(n)
    return _norm(e["nazwa"]) if e else n


def tier_cwiczenia(nazwa, tl=None):
    """-> 'S'/'A'/… albo None, gdy ćwiczenia nie ma na liście"""
    tl = tl if tl is not None else config.ustawienia()["tierlista"]
    n = _norm(nazwa)
    if not n:
        return None
    klucze = {n, _kanon(nazwa)}

    def luzno(nx):                                 # „unoszenie bokiem” ⊂ „unoszenie hantli bokiem” (słowa po kolei, min. 2)
        a, b = n.split(), nx.split()
        m, d = (a, b) if len(a) <= len(b) else (b, a)
        it = iter(d)
        return len(m) >= 2 and all(w in it for w in m)
    for dokladnie in (True, False):
        for t in TIERY:
            for x in tl.get(t) or []:
                if ({_norm(x), _kanon(x)} & klucze) if dokladnie else luzno(_norm(x)):
                    return t
    return None


def tekst_do_planu(u=None):
    u = u or config.ustawienia()
    tl = u.get("tierlista") or {}
    linie = [f"{TIERY[t]}: " + "; ".join(tl.get(t) or []) for t in TIERY if tl.get(t)]
    return ("TIERLISTA ĆWICZEŃ ANTKA (wybieraj głównie S i A, B jako zamienniki, C tylko gdy trzeba; WYKLUCZONYCH nie dawaj; "
            "nowe ćwiczenie spoza listy wolno, ale rzadko, max 1 na trening, a po treningu Antek je oceni):\n"
            + "\n".join(linie) + ("\n\nZASADY UKŁADANIA SIŁKI ANTKA:\n" + u["zasady_silka"] if u.get("zasady_silka") else ""))


def _nazwy(kroki):
    for k in kroki or []:
        if k.get("rodzaj") == "cwiczenie" and k.get("nazwa"):
            yield k["nazwa"].strip()
        yield from _nazwy(k.get("kroki"))


def do_oceny(db, dni=14):
    """ćwiczenia z zaplanowanych siłek w dni, kiedy była siłka (ostatnie 2 tyg.), których nie ma w tierliście"""
    od = (date.today() - timedelta(days=dni)).isoformat()
    dni_silki = {r[0] for r in db.execute("SELECT dzien FROM aktywnosci WHERE dzien >= ? AND typ='strength_training'", (od,))}
    tl = config.ustawienia()["tierlista"]
    pominiete = {_kanon(x) for x in baza.kv(db, "tier_pominiete", [])}
    wyn, byly = [], set()
    for dz, kroki in db.execute("SELECT dzien, kroki FROM plan WHERE sport='silka' AND dzien >= ? AND stan != 'usuniety' "
                                "ORDER BY dzien, id", (od,)):
        if dz not in dni_silki:
            continue
        for n in _nazwy(json.loads(kroki or "[]")):
            k = _kanon(n)
            if k and k not in byly and k not in pominiete and not tier_cwiczenia(n, tl):
                byly.add(k)
                wyn.append(n[:1].upper() + n[1:])
    return wyn


def ocen(db, nazwa, tier):
    """tier: S/A/B/C/X → dopisz do tierlisty; 'pomin' → nie pytaj więcej"""
    if tier == "pomin":
        baza.ustaw_kv(db, "tier_pominiete", baza.kv(db, "tier_pominiete", []) + [nazwa])
        return
    if tier not in TIERY:
        raise ValueError("zły tier")
    tl = {t: [x for x in (l or []) if _kanon(x) != _kanon(nazwa)] for t, l in config.ustawienia()["tierlista"].items()}
    tl.setdefault(tier, []).append(nazwa)
    config.zapisz_ustawienia({"tierlista": tl})


def zapytaj_po_treningu(db):
    """po synchronizacji siłki: jedno powiadomienie o ćwiczeniach do oceny (każde zgłaszane tylko raz)"""
    from . import powiadom
    nowe = do_oceny(db, dni=2)
    zgl = set(baza.kv(db, "tier_zgloszone", []))
    nowe = [n for n in nowe if _kanon(n) not in zgl]
    if not nowe:
        return
    baza.ustaw_kv(db, "tier_zgloszone", sorted(zgl | {_kanon(n) for n in nowe})[-300:])
    powiadom.powiadom("🏋️ Oceń nowe ćwiczenia", ", ".join(nowe[:4]) + (" i inne" if len(nowe) > 4 else "")
                      + ": jak je oceniasz (S/A/B/C)?", "/#dzis", db)
