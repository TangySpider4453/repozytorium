"""Ścieżki i ustawienia. Sekrety tylko poza gitem: token Garmina (wspólny z restortrain-garmin), klucze VAPID w dane/."""
import json
import os
from pathlib import Path

KAT = Path(__file__).resolve().parent.parent
DANE = Path(os.environ.get("TRENER_DANE", KAT / "dane"))
BAZA = DANE / "trener.db"
TOKENY = Path(os.environ.get("TRENER_TOKENY", "/home/tonyg/restortrain-garmin/tokens"))
BLOKADA_GARMIN = DANE / "garmin.lock"
CLAUDE = Path(os.environ.get("TRENER_CLAUDE", "/home/tonyg/.local/bin/claude"))
KOLEJKA_BOTA = Path("/home/tonyg/bot/powiadomienia")
STATIC = KAT / "static"
ZNACZNIK = "auto: trener"          # w opisie treningów tworzonych przez apkę; usuwamy TYLKO takie
START_HISTORII = "2024-04-01"     # najstarsze dane (pierwsza aktywność 27.04.2024); backfill i tak schodzi do pierwszej

DOMYSLNE = {
    "cele": "",                     # cele Antka własnymi słowami (z ustawień / czatu)
    "dostepnosc": "",               # kiedy może trenować
    "sprzet": "",                   # rower, trenażer, siłownia…
    "sporty": ["rower", "bieg", "silka"],
    "plan_dni": 7,                  # na ile dni do przodu planować
    "auto_zegarek": True,           # treningi same idą do Garmina (decyzja Antka 17.11)
    "analiza_rano": True,
    "analiza_godzina_min": "06:30", # nie wcześniej niż
    "push": True,
    "linphone": True,
    "model": "claude-sonnet-5-5",
    "ankieta": {},                  # odpowiedzi z ankiety startowej (cele, terminy, dni, sprzęt, styl planu…)
    "start_gotowy": False,          # ankieta + dopytanie zakończone → wolno planować
}


def ustawienia():
    p = DANE / "ustawienia.json"
    u = dict(DOMYSLNE)
    if p.exists():
        try:
            u.update(json.loads(p.read_text(encoding="utf-8")))
        except ValueError:
            pass
    return u


def zapisz_ustawienia(zmiany):
    u = ustawienia()
    u.update({k: v for k, v in zmiany.items() if k in DOMYSLNE})
    DANE.mkdir(parents=True, exist_ok=True)
    tmp = DANE / "ustawienia.json.tmp"
    tmp.write_text(json.dumps(u, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DANE / "ustawienia.json")
    return u
