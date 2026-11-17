"""Analizy Claude: poranna (po śnie), po treningu, tygodniowa. Zapis w tabeli analizy + powiadomienie
„można omówić”. Gdy analiza uzna, że plan trzeba zmienić — przekazuje prośbę do planu."""
import json
import logging
from datetime import date, timedelta

from . import ai, baza, cel, kontekst, powiadom

log = logging.getLogger(__name__)

SCHEMAT = {"type": "object", "properties": {
    "tytul": {"type": "string", "description": "≤ 60 znaków, sedno (np. 'Słaba noc, HRV nisko — dziś lżej')"},
    "krotko": {"type": "string", "description": "1-2 zdania do powiadomienia"},
    "tresc": {"type": "string", "description": "pełna analiza: liczby, trendy, porównanie z normą, co robić"},
    "ocena": {"type": "string", "enum": ["dobrze", "uwaga", "zle"]},
    "zmienic_plan": {"type": "boolean"},
    "prosba_do_planu": {"type": "string", "description": "co zmienić w planie (gdy zmienic_plan)"}},
    "required": ["tytul", "krotko", "tresc", "ocena", "zmienic_plan"]}

ZADANIA = {
    "rano": "Poranna analiza: oceń noc (sen, fazy, HRV na tle normy, tętno spoczynkowe, Body Battery, gotowość) i "
            "obciążenie z ostatnich dni. Powiedz, czy dzisiejszy zaplanowany trening ma sens, czy go zmienić. Porównaj z "
            "typowymi wartościami Antka z historii (tygodnie/miesiące).",
    "trening": "Analiza zakończonego treningu (lista niżej): jak poszło względem planu i poprzednich podobnych treningów "
               "(moc/tempo/tętno/strefy, w siłce serie i ciężary — progres?), efekt treningowy, co dalej. Czy plan na "
               "najbliższe dni trzeba skorygować?",
    "tydzien": "Podsumowanie tygodnia: objętość per sport, obciążenie, sen i regeneracja, realizacja planu, trendy (VO2, "
               "HRV, tętno spocz.) na tle ostatnich miesięcy. Wnioski i kierunek na następny tydzień.",
}


def zrobiona(db, rodzaj, dzien):
    return db.execute("SELECT 1 FROM analizy WHERE rodzaj=? AND dzien=?", (rodzaj, dzien)).fetchone() is not None


def analizuj(rodzaj="rano", wymus=False, aktywnosci=None, db=None):
    db = db or baza.polacz()
    dzis = date.today().isoformat()
    if not wymus and rodzaj != "trening" and zrobiona(db, rodzaj, dzis):
        return None
    zasady = "\n\n".join((cel.WIEDZA / f).read_text(encoding="utf-8") for f in ("01_zasady_ogolne.md", "05_regeneracja.md"))
    prompt = ("BAZA WIEDZY (oceniaj wg tych zasad):\n" + zasady + "\n\n" + kontekst.pelny(db) + "\n\nZADANIE: " + ZADANIA[rodzaj]
              + " Oceń też, czy realizacja zgadza się z bieżącą fazą makrocyklu.")
    if aktywnosci:
        prompt += "\n\nTRENING(I) DO ANALIZY:\n" + "\n".join(json.dumps(a, ensure_ascii=False) for a in aktywnosci)
    w = ai.zapytaj(prompt, SCHEMAT, effort="medium")
    cur = db.execute("INSERT INTO analizy (rodzaj, dzien, utworzono, tytul, tresc, dane) VALUES (?,?,?,?,?,?)",
                     (rodzaj, dzis, baza.teraz(), w["tytul"], w["tresc"], json.dumps(w, ensure_ascii=False)))
    db.commit()
    aid = cur.lastrowid
    znak = {"dobrze": "✅", "uwaga": "⚠️", "zle": "🛑"}.get(w.get("ocena"), "📊")
    powiadom.powiadom(f"{znak} {w['tytul']}", w["krotko"] + " Dotknij, żeby omówić.", f"/#analiza/{aid}", db)
    return {"id": aid, **w}


def nowe_treningi_do_analizy(db, nowe):
    """z listy nowych aktywności — te zakończone w ostatnich 12 h (bez starych z historii)"""
    granica = (date.today() - timedelta(days=1)).isoformat()
    wyn = []
    for a in nowe:
        if (a.get("startTimeLocal") or "")[:10] >= granica and (a.get("duration") or 0) > 600:
            s = kontekst.dane.streszczenie_aktywnosci(a)
            if a.get("activityType", {}).get("typeKey") == "strength_training":
                r = db.execute("SELECT szczegoly FROM aktywnosci WHERE id=?", (a["activityId"],)).fetchone()
                if r and r[0]:
                    s["cwiczenia"] = kontekst.cwiczenia_silki(baza.rozpakuj(r[0]))
            wyn.append(s)
    return wyn
