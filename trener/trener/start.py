"""Ankieta startowa: cele, terminy, dostępność, sprzęt, jak ma wyglądać plan. Po ankiecie Claude dopytuje (max 4
pytania), dopiero potem makrocykl + plan. Bez ankiety apka nie planuje (tylko dane i analizy)."""
import json
import logging

from . import ai, baza, config, kontekst

log = logging.getLogger(__name__)

DNI = ["pon", "wt", "śr", "czw", "pt", "sob", "ndz"]


def tekst_ankiety(a):
    """ankieta → czytelny tekst do promptów"""
    if not a:
        return ""
    w = []
    def dodaj(n, v):
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v if x)
        if v not in (None, "", []):
            w.append(f"- {n}: {v}")
    dodaj("Cele", a.get("cele"))
    dodaj("Cel własnymi słowami", a.get("cel_opis"))
    dodaj("Zawody / terminy", a.get("zawody"))
    dodaj("Siłownia tygodniowo", a.get("silka"))
    dodaj("Bieganie", a.get("bieg"))
    if a.get("dni"):
        dodaj("Czas na trening", "; ".join(f"{d} {a['dni'].get(d) or '—'}" for d in DNI))
    dodaj("Gdzie jeździ", a.get("gdzie"))
    dodaj("Sprzęt", a.get("sprzet"))
    dodaj("Charakter planu", a.get("styl"))
    dodaj("Treningi na zegarku", a.get("zegarek"))
    dodaj("Analizy", a.get("analizy"))
    dodaj("Powiadomienia", a.get("powiadomienia"))
    dodaj("Zdrowie / kontuzje", a.get("zdrowie"))
    dodaj("Szkoła: egzaminy, ferie, wyjazdy", a.get("szkola"))
    dodaj("Inne", a.get("inne"))
    for p in a.get("doprecyzowanie") or []:
        dodaj(f"Doprecyzowanie — {p.get('pytanie')}", p.get("odpowiedz"))
    return "\n".join(w)


def zapisz(a):
    """ankieta → ustawienia (cele/dostępność/sprzęt/sporty to skróty z ankiety)"""
    sporty = ["rower"]
    if a.get("bieg") and not str(a["bieg"]).startswith("nie"):
        sporty.append("bieg")
    if a.get("silka") and str(a["silka"]) not in ("0", "nie"):
        sporty.append("silka")
    cele = "; ".join(x for x in [", ".join(a.get("cele") or []), a.get("cel_opis", ""), a.get("zawody", "")] if x)
    dni = "; ".join(f"{d} {a.get('dni', {}).get(d) or '—'}" for d in DNI) if a.get("dni") else ""
    return config.zapisz_ustawienia({"ankieta": a, "cele": cele, "dostepnosc": dni,
                                     "sprzet": ", ".join(a.get("sprzet") or []), "sporty": sporty, "start_gotowy": False})


SCHEMAT = {"type": "object", "properties": {
    "podsumowanie": {"type": "string", "description": "2-3 zdania: jak rozumiesz cel i co z tego wynika"},
    "pytania": {"type": "array", "maxItems": 4, "items": {"type": "object", "properties": {
        "pytanie": {"type": "string"}, "opcje": {"type": "array", "items": {"type": "string"}},
        "wielokrotny": {"type": "boolean"}}, "required": ["pytanie"]}}},
    "required": ["podsumowanie", "pytania"]}


def dopytaj(a):
    """po ankiecie: Claude czyta odpowiedzi + dane i zadaje najważniejsze brakujące pytania (0-4)"""
    zapisz(a)
    db = baza.polacz()
    prompt = (kontekst.pelny(db, akt_dni=14, tygodnie=12) + "\n\nANKIETA ANTKA:\n" + tekst_ankiety(a) +
              "\n\nZADANIE: Jesteś trenerem po pierwszej rozmowie. Sprawdź, czego brakuje, żeby ułożyć dobrą periodyzację "
              "(np. konkretny termin/ranga zawodów, doświadczenie w siłowni, sprzeczne odpowiedzi, cel mierzalny, ograniczenia). "
              "Zadaj 0–4 krótkie pytania — tylko takie, które realnie zmienią plan; daj gotowe opcje do kliknięcia, gdy się da. "
              "Nie pytaj o rzeczy widoczne w danych Garmina.")
    w = ai.zapytaj(prompt, SCHEMAT, effort="medium")
    baza.ustaw_kv(db, "start_pytania", w)
    return w


def zakoncz(odpowiedzi):
    """odpowiedzi na dopytanie → makrocykl → plan → zegarek"""
    u = config.ustawienia()
    a = dict(u.get("ankieta") or {})
    a["doprecyzowanie"] = [x for x in odpowiedzi if x.get("odpowiedz")]
    zapisz(a)
    config.zapisz_ustawienia({"start_gotowy": True})
    from .cel import zbuduj
    from .cykl import przeplanuj
    m = zbuduj()
    wyn = przeplanuj("plan startowy po ankiecie", powiadamiaj=True) or {}
    return {"makrocykl": m, "plan": wyn}
