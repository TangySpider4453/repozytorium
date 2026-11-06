"""
Analiza opisu treningu przez Claude (Sonnet, lokalny Claude Code na Pi, bez narzędzi).
RestOrTrain pisze każdy trening trochę inaczej (pisze go AI), więc opis czyta AI i zwraca uporządkowany plan
w JSON. Wynik jest walidowany i zamieniany na te same obiekty, co z parsera regułowego (parser.py), który zostaje
zapasem: gdy Claude nie odpowie albo zwróci coś niepoprawnego.

Koszt: jedno zapytanie na nowy albo zmieniony opis. Wynik leży w data/ai_cache.json (klucz: hash opisu + wersja
promptu), więc przebiegi co 10 minut i przebudowy po zmianie kodu nie pytają drugi raz.
"""
import hashlib
import json
import logging
import re
import subprocess
from pathlib import Path

from .parser import Circuit, Exercise, Section, TimedBlock, WarmupSets

log = logging.getLogger("rtg.ai")
KAT = Path(__file__).resolve().parent.parent
CACHE = KAT / "data" / "ai_cache.json"
CLAUDE = Path("/home/tonyg/.local/bin/claude")
MODEL = "claude-sonnet-5-5"
WERSJA_PROMPTU = "1"

PROMPT = """Jesteś parserem planu treningu siłowego (z aplikacji RestOrTrain) dla zegarka Garmin.
Przeczytaj opis i zwróć WYŁĄCZNIE JSON (bez komentarzy, bez ```), dokładnie w tym kształcie:
{"sekcje": [{"nazwa": "nagłówek sekcji", "rodzaj": "warmup|main|cooldown",
  "przerwy": "warmup|main|accessory|core|cooldown",
  "elementy": [
    {"typ": "czas", "sekundy": 600, "tekst": "mobilizacja bioder"},
    {"typ": "serie_rozgrzewkowe", "serie": 2, "cwiczenie": "<dokładna nazwa ćwiczenia z tego treningu>", "kg": null, "uwagi": ""},
    {"typ": "cwiczenie", "nazwa": "Martwy ciąg", "serie": 4, "powt_min": 4, "powt_max": 6, "czas_s": null,
     "jednostronne": false, "strona": null, "kg": 70, "uwagi": "1-2 powtórzenia w zapasie"},
    {"typ": "rundy", "rundy": 3, "przerwa_s": 90, "cwiczenia": [<obiekty "cwiczenie" z "serie": 1>]}
  ]}]}
Zasady:
- "nazwa": polska nazwa ćwiczenia jak w opisie (z kątem ławki, np. "Wyciskanie hantli na skosie dodatnim 30°"),
  bez liczby serii, powtórzeń i ciężaru.
- "4x8-10" = serie 4, powt_min 8, powt_max 10; "3x30s" = czas_s 30 (powt null). "8-10m"/"10 min" = minuty (czas w sekundach).
- "jednostronne": true, gdy ćwiczenie robi się osobno na każdą nogę / rękę / stronę ("jednonóż", "jednorącz", "na nogę",
  "na stronę" przy ruchu). "strona": "noga", "ręka" albo "strona". UWAGA: "25 kg na stronę plus sztanga" to talerze po obu
  stronach gryfu, NIE ćwiczenie jednostronne.
- "kg": ciężar całkowity jednej serii jako liczba: jedna wartość = ta wartość; zakres "20-22,5 kg" = średnia (21.25);
  "X kg na stronę plus sztanga" = 2*X + 20 (gryf 20 kg); "na hantel" = ciężar jednego hantla; "masa ciała" albo
  "dobierz ciężar" = null.
- "rundy": gdy plan każe robić ćwiczenia naprzemiennie / w rundach / w parach (superseria, obwód). Każde ćwiczenie w
  rundzie ma "serie": 1. "przerwa_s" = przerwa po całej rundzie (z zakresu "90-120s" weź górną wartość).
  Gdy plan mówi "naprzemiennie tylko jeśli stanowiska są blisko" — i tak zrób rundy, a warunek dopisz w "uwagi".
- Linia z samą przerwą ("90s odpoczynku po obu ćwiczeniach") NIE jest osobnym elementem, tylko "przerwa_s" rundy.
- "serie_rozgrzewkowe": "lekkie serie / serie wstępne <ćwiczenia>"; "cwiczenie" = DOKŁADNA "nazwa" tego ćwiczenia z
  treningu ("pierwszego ćwiczenia" = pierwsze ćwiczenie główne); bez liczby = 2 serie.
- Wskazówki (tempo, technika, kąt ławki, "zapisz kg", "ten sam ciężar") wpisz w "uwagi" właściwego ćwiczenia, krótko;
  ciężar zostaw też w "uwagi" w oryginalnym zapisie (np. "17,5 kg na hantel", "25 kg na stronę plus sztanga").
- Rozgrzewka i schłodzenie: "rodzaj" warmup / cooldown. "przerwy": accessory dla akcesoriów, core dla brzucha,
  inaczej main.
- Nie wymyślaj ćwiczeń ani liczb, których nie ma w opisie.

Opis treningu:
"""


def _klucz(opis):
    return hashlib.sha256((WERSJA_PROMPTU + MODEL + (opis or "")).encode("utf-8")).hexdigest()


def _cache():
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _zapytaj(opis):
    r = subprocess.run([str(CLAUDE), "-p", PROMPT + opis, "--output-format", "json", "--tools", "", "--strict-mcp-config",
                        "--model", MODEL, "--effort", "low"], capture_output=True, text=True, timeout=240,
                       stdin=subprocess.DEVNULL, cwd=str(KAT))
    d = json.loads(r.stdout or "{}")
    if d.get("is_error"):
        raise RuntimeError(d.get("result") or "błąd claude")
    t = (d.get("result") or "").strip()
    m = re.search(r"\{.*\}", t, re.S)
    return json.loads(m.group(0))


def _int(x, lo, hi, pole):
    if x is None:
        return None
    v = int(round(float(x)))
    if not lo <= v <= hi:
        raise ValueError(f"{pole}={x}")
    return v


def _cwiczenie(e):
    nazwa = (e.get("nazwa") or "").strip()
    if not nazwa:
        raise ValueError("ćwiczenie bez nazwy")
    a, b = _int(e.get("powt_min"), 1, 100, "powt_min"), _int(e.get("powt_max"), 1, 100, "powt_max")
    a, b = a or b, b or a
    czas = _int(e.get("czas_s"), 1, 3600, "czas_s")
    if not (a or czas):
        raise ValueError(f"{nazwa}: brak powtórzeń i czasu")
    kg = e.get("kg")
    kg = round(float(kg), 2) if isinstance(kg, (int, float)) and 0 < kg < 500 else None
    c = Exercise(raw=nazwa, name_pl=nazwa, sets=_int(e.get("serie") or 1, 1, 20, "serie"),
                 reps_min=min(a, b) if a else None, reps_max=max(a, b) if a else None, duration_s=czas,
                 per_side=bool(e.get("jednostronne")), note=(e.get("uwagi") or "").strip(), weight_kg=kg or 0.0)
    c.weight_kg = kg                     # None = bez ciężaru (bez zgadywania z uwag)
    c.per_side = bool(e.get("jednostronne"))
    if c.per_side and e.get("strona") in ("noga", "ręka", "strona"):
        c.side_word = e["strona"]
    return c


def na_sekcje(dane):
    """JSON od Claude -> [Section] (walidacja; wyjątek = użyj parsera regułowego)"""
    sekcje = []
    for s in dane["sekcje"]:
        rodzaj = s.get("rodzaj") if s.get("rodzaj") in ("warmup", "main", "cooldown") else "main"
        przerwy = s.get("przerwy") if s.get("przerwy") in ("warmup", "main", "accessory", "core", "cooldown") else "main"
        sek = Section(name=(s.get("nazwa") or "Trening").strip(), kind=rodzaj, rest_class=przerwy)
        for e in s.get("elementy") or []:
            t = e.get("typ")
            if t == "czas":
                sek.items.append(TimedBlock(raw=e.get("tekst") or "", seconds=_int(e.get("sekundy"), 1, 7200, "sekundy"),
                                            kind=rodzaj, text=(e.get("tekst") or "").strip()))
            elif t == "serie_rozgrzewkowe":
                n = _int(e.get("serie") or 2, 1, 10, "serie")
                kg = e.get("kg")
                uwagi = (e.get("uwagi") or "").strip()
                uw = ", ".join(x for x in (f"{kg:g} kg".replace(".", ",") if isinstance(kg, (int, float)) and kg > 0 and "kg" not in uwagi else "",
                                           (e.get("uwagi") or "").strip()) if x)
                ref = (e.get("cwiczenie") or "").strip()
                sek.items.append(WarmupSets(raw=f"{n} serie rozgrzewkowe: {ref}" + (f", {uw}" if uw else ""),
                                            sets_min=n, sets_max=n, exercise_ref=ref, note=uw))
            elif t == "cwiczenie":
                sek.items.append(_cwiczenie(e))
            elif t == "rundy":
                cw = [_cwiczenie(x) for x in e.get("cwiczenia") or []]
                if not cw:
                    raise ValueError("rundy bez ćwiczeń")
                for c in cw:
                    c.sets = 1
                sek.items.append(Circuit(exercises=cw, rounds=_int(e.get("rundy"), 1, 20, "rundy"),
                                         rest_s=_int(e.get("przerwa_s"), 1, 900, "przerwa_s"), raw=sek.name))
            else:
                raise ValueError(f"nieznany typ {t!r}")
        sekcje.append(sek)
    if not any(isinstance(i, (Exercise, Circuit)) for s in sekcje for i in s.items):
        raise ValueError("brak ćwiczeń")
    return sekcje


def analizuj(opis, pytaj=_zapytaj):
    """[Section] od Claude (z pamięci albo nowe zapytanie) albo None, gdy się nie udało"""
    k = _klucz(opis)
    pamiec = _cache()
    try:
        if k in pamiec:
            return na_sekcje(pamiec[k])
        dane = pytaj(opis)
        sekcje = na_sekcje(dane)
    except Exception as ex:
        log.warning("analiza AI nieudana (%s), parser regułowy", str(ex)[:200])
        return None
    pamiec[k] = dane
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(pamiec, ensure_ascii=False), encoding="utf-8")
    log.info("analiza AI (%s): %d sekcji", MODEL, len(sekcje))
    return sekcje
