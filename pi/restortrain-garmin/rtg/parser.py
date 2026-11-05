"""
Parser opisu treningu siłowego RestOrTrain (deterministyczny, bez sieci).

Wejście: opis tekstowy, np.
    Główne ćwiczenia
    - Martwy ciąg 4x4-6, 1-2 powtórzenia w zapasie
Wyjście: lista sekcji z elementami: Exercise, TimedBlock, WarmupSets albo Unparsed.

Zasady (spec, sekcja 5):
- linia bez „- ” na początku = nagłówek sekcji; „rozgrzew” -> warmup, „schłodz/cool/rozciąg” -> cooldown, reszta -> main
  (rest_class: „akcesor” -> accessory, „brzuch/core/abs” -> core, inaczej main; od tego zależy przerwa),
- „10m”, „10 min” = minuty (nie metry), „30s” = sekundy,
- „4x4-6”, „4x8”, „3 x 10”, „4×8”, „3x30s” (seria na czas),
- „X-Y serie wstępne <ćwiczenie>” = serie rozgrzewkowe (koniec przyciskiem okrążenia),
- „na nogę / na stronę / na rękę” -> per_side, dopiski -> note,
- linia, której nie da się sparsować -> Unparsed (krok „lap button” z surowym tekstem) + ostrzeżenie w logu.
"""
import logging
import re
import unicodedata
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


def normalizuj(t):
    """małe litery, bez polskich znaków, pojedyncze spacje (do dopasowań)"""
    t = (t or "").replace("ł", "l").replace("Ł", "L")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t.lower()).strip()


@dataclass
class Exercise:
    raw: str
    name_pl: str
    sets: int
    reps_min: int | None = None
    reps_max: int | None = None
    duration_s: int | None = None          # seria na czas („3x30s”)
    per_side: bool = False
    note: str = ""


@dataclass
class TimedBlock:
    raw: str
    seconds: int
    kind: str                               # warmup | main | cooldown
    text: str = ""


@dataclass
class WarmupSets:
    raw: str
    sets_min: int
    sets_max: int
    exercise_ref: str


@dataclass
class Unparsed:
    raw: str


@dataclass
class Section:
    name: str
    kind: str                               # warmup | main | cooldown
    rest_class: str                         # warmup | main | accessory | core | cooldown
    items: list = field(default_factory=list)


ITEM_RE = re.compile(r"^\s*[-–•*]\s*(.+?)\s*$")
CZAS_RE = re.compile(r"^(\d+)\s*(min\w*|m|sek\w*|s)\b\.?\s*(.*)$", re.I)
WSTEPNE_RE = re.compile(r"^(\d+)(?:\s*[-–]\s*(\d+))?\s+seri\w*\s+(?:wstępn|wstepn|rozgrzewkow)\w*\s*(.*)$", re.I)
CWICZENIE_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<sets>\d+)\s*[x×X]\s*(?P<a>\d+)(?:\s*[-–]\s*(?P<b>\d+))?\s*(?P<unit>s|sek|min|m)?(?![\w])\s*(?P<rest>.*)$")
NA_STRONE_RE = re.compile(r"\bna\s+(nog[eę]|stron[eę]|r[eę]k[eę]|ka[zż]d[aą]\s+(nog[eę]|stron[eę]|r[eę]k[eę]))\b", re.I)


def rodzaj_sekcji(nazwa):
    n = normalizuj(nazwa)
    if "rozgrzew" in n or "warm" in n:
        return "warmup", "warmup"
    if "schlodz" in n or "cool" in n or "rozciag" in n:
        return "cooldown", "cooldown"
    if "akcesor" in n:
        return "main", "accessory"
    if "brzuch" in n or "core" in n or "abs" in n:
        return "main", "core"
    return "main", "main"


def sekundy(liczba, jednostka):
    j = jednostka.lower()
    return liczba * 60 if j.startswith("m") else liczba


def parsuj_linie(tekst, kind):
    if m := WSTEPNE_RE.match(tekst):
        a = int(m.group(1))
        b = int(m.group(2) or a)
        return WarmupSets(raw=tekst, sets_min=min(a, b), sets_max=max(a, b), exercise_ref=m.group(3).strip())
    if m := CZAS_RE.match(tekst):
        return TimedBlock(raw=tekst, seconds=sekundy(int(m.group(1)), m.group(2)), kind=kind, text=m.group(3).strip())
    if m := CWICZENIE_RE.match(tekst):
        a = int(m.group("a"))
        b = int(m.group("b") or a)
        reszta = m.group("rest").strip(" ,;.-–")
        per_side = bool(NA_STRONE_RE.search(reszta))
        if m.group("unit"):                            # seria na czas: „3x30s”, „3x1min”
            return Exercise(raw=tekst, name_pl=m.group("name").strip(" ,"), sets=int(m.group("sets")),
                            duration_s=sekundy(max(a, b), m.group("unit")), per_side=per_side, note=reszta)
        return Exercise(raw=tekst, name_pl=m.group("name").strip(" ,"), sets=int(m.group("sets")),
                        reps_min=min(a, b), reps_max=max(a, b), per_side=per_side, note=reszta)
    log.warning("nie rozumiem linii opisu (krok z przyciskiem okrążenia): %r", tekst)
    return Unparsed(raw=tekst)


def parsuj(opis):
    """opis -> [Section]; elementy przed pierwszym nagłówkiem trafiają do sekcji „Trening” (main)"""
    sekcje = []
    for linia in (opis or "").splitlines():
        if not linia.strip():
            continue
        m = ITEM_RE.match(linia)
        if not m:                                       # nagłówek sekcji
            kind, rest_class = rodzaj_sekcji(linia)
            sekcje.append(Section(name=linia.strip().rstrip(":"), kind=kind, rest_class=rest_class))
            continue
        if not sekcje:
            sekcje.append(Section(name="Trening", kind="main", rest_class="main"))
        s = sekcje[-1]
        s.items.append(parsuj_linie(m.group(1), s.kind))
    return sekcje


def wyglada_na_silowy(opis):
    """co najmniej jedna linia ćwiczenia „NxM” (drugie kryterium rozpoznania treningu RestOrTrain)"""
    return any(isinstance(i, Exercise) for s in parsuj(opis) for i in s.items)
