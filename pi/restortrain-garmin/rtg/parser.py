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
- linia, której nie da się sparsować -> Unparsed (krok „lap button” z surowym tekstem) + ostrzeżenie w logu,
- rundy / superserie: nagłówek „… — 3 rundy naprzemiennie” albo linia „90s odpoczynku po obu ćwiczeniach” /
  „Po każdej parze odpocznij 90-120s” -> Circuit: ćwiczenia jedno po drugim w każdej rundzie, przerwa po rundzie.
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
    weight_kg: float | None = None          # „17,5 kg”, „20-22,5 kg” (zakres -> średnia)

    def __post_init__(self):
        if self.weight_kg is None:
            self.weight_kg = ciezar(self.note)


KG_RE = re.compile(r"(\d+(?:[.,]\d+)?)(?:\s*[-–]\s*(\d+(?:[.,]\d+)?))?\s*kg\b", re.I)


def ciezar(tekst):
    """pierwszy ciężar z opisu w kg; zakres „od-do” = średnia (np. 20-22,5 kg -> 21,25)"""
    m = KG_RE.search(tekst or "")
    if not m:
        return None
    a = float(m.group(1).replace(",", "."))
    b = float(m.group(2).replace(",", ".")) if m.group(2) else a
    return round((a + b) / 2, 2)


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
class RoundRest:
    raw: str
    seconds: int


@dataclass
class Circuit:
    """rundy (superseria / obwód): w każdej rundzie po jednej serii każdego ćwiczenia, potem przerwa"""
    exercises: list
    rounds: int
    rest_s: int | None = None
    raw: str = ""


@dataclass
class Section:
    name: str
    kind: str                               # warmup | main | cooldown
    rest_class: str                         # warmup | main | accessory | core | cooldown
    items: list = field(default_factory=list)
    rounds: int | None = None               # „3 rundy” w nagłówku
    circuit: bool = False                   # nagłówek mówi o rundach / naprzemiennie


ITEM_RE = re.compile(r"^\s*[-–•*]\s*(.+?)\s*$")
CZAS_RE = re.compile(r"^(?:\d+\s*[-–]\s*)?(\d+)\s*(min\w*|m|sek\w*|s)\b\.?\s*(.*)$", re.I)     # „8-10m” = 10 min
# serie rozgrzewkowe: „3-4 serie wstępne martwego ciągu”, „2 lekkie serie wyciskania hantli”, „Lekkie serie wstępne
# przysiadu” (bez liczby = 2), „2 lekkie serie pierwszego ćwiczenia” (= pierwsze ćwiczenie główne)
WSTEPNE_RE = re.compile(r"^(?:(\d+)(?:\s*[-–]\s*(\d+))?\s+)?(?:(?:lekk|wstępn|wstepn|rozgrzewkow)\w*\s+)+seri\w*"
                        r"(?:\s+(?:wstępn|wstepn|rozgrzewkow|lekk)\w*)*\s*(.*)$", re.I)
CWICZENIE_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<sets>\d+)\s*[x×X]\s*(?P<a>\d+)(?:\s*[-–]\s*(?P<b>\d+))?\s*(?P<unit>s|sek|min|m)?(?![\w])\s*(?P<rest>.*)$")
NA_STRONE_RE = re.compile(r"\bna\s+(nog[eę]|stron[eę]|r[eę]k[eę]|ka[zż]d[aą]\s+(nog[eę]|stron[eę]|r[eę]k[eę]))\b", re.I)


# przerwa po rundzie / parze: „90s odpoczynku po obu ćwiczeniach”, „Po każdej parze odpocznij 90-120s”
PRZERWA_RUNDY_RE = re.compile(r"(?:odpocz|odpoczyn|przerw)\w*", re.I)
PRZERWA_CZAS_RE = re.compile(r"(\d+)(?:\s*[-–]\s*(\d+))?\s*(s|sek\w*|min\w*|m)\b", re.I)
RUNDY_RE = re.compile(r"(\d+)\s*(?:rund|obwod|obwód|okrąż|okraz)\w*", re.I)
NAPRZEMIENNIE_RE = re.compile(r"naprzemienn|na\s+zmian|superseri|obw[oó]d|rund", re.I)
# „Spięcia brzucha na wyciągu: 12-15 powtórzeń, …” (jedna seria w rundzie)
POWT_RE = re.compile(r"^(?P<name>[^:]+?)\s*:\s*(?P<a>\d+)(?:\s*[-–]\s*(?P<b>\d+))?\s*(?:powt\w*|razy)\.?\s*(?P<rest>.*)$", re.I)


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
    if PRZERWA_RUNDY_RE.search(tekst) and (m := PRZERWA_CZAS_RE.search(tekst)) and not CWICZENIE_RE.match(tekst):
        return RoundRest(raw=tekst, seconds=sekundy(int(m.group(2) or m.group(1)), m.group(3)))
    if (m := WSTEPNE_RE.match(tekst)) or (m := re.match(r"^(\d+)(?:\s*[-–]\s*(\d+))?\s+seri\w*\s+(?:wstępn|wstepn|rozgrzewkow)\w*\s*(.*)$", tekst, re.I)):
        a = int(m.group(1) or 2)
        b = int(m.group(2) or a)
        ref = re.split(r"\s*[,;—–]\s*|\s+-\s+", m.group(3).strip(), maxsplit=1)[0]      # bez dopisków „, 12,5 kg …”
        return WarmupSets(raw=tekst, sets_min=min(a, b), sets_max=max(a, b), exercise_ref=ref.strip())
    if m := CZAS_RE.match(tekst):
        return TimedBlock(raw=tekst, seconds=sekundy(int(m.group(1)), m.group(2)), kind=kind, text=m.group(3).strip())
    if m := POWT_RE.match(tekst):
        a, b = int(m.group("a")), int(m.group("b") or m.group("a"))
        reszta = m.group("rest").strip(" ,;.-–—")
        return Exercise(raw=tekst, name_pl=m.group("name").strip(" ,"), sets=1, reps_min=min(a, b), reps_max=max(a, b),
                        per_side=bool(NA_STRONE_RE.search(reszta)), note=reszta)
    if m := CWICZENIE_RE.match(tekst):
        a = int(m.group("a"))
        b = int(m.group("b") or a)
        reszta = m.group("rest").strip(" ,;.-–—")
        per_side = bool(NA_STRONE_RE.search(reszta))
        if m.group("unit"):                            # seria na czas: „3x30s”, „3x1min”
            return Exercise(raw=tekst, name_pl=m.group("name").strip(" ,:"), sets=int(m.group("sets")),
                            duration_s=sekundy(max(a, b), m.group("unit")), per_side=per_side, note=reszta)
        return Exercise(raw=tekst, name_pl=m.group("name").strip(" ,:"), sets=int(m.group("sets")),
                        reps_min=min(a, b), reps_max=max(a, b), per_side=per_side, note=reszta)
    log.warning("nie rozumiem linii opisu (krok z przyciskiem okrążenia): %r", tekst)
    return Unparsed(raw=tekst)


def parsuj(opis):
    """opis -> [Section]; elementy przed pierwszym nagłówkiem trafiają do sekcji „Trening” (main).
    „pierwszego ćwiczenia” w seriach rozgrzewkowych = pierwsze ćwiczenie z serii w treningu."""
    sekcje = []
    for linia in (opis or "").splitlines():
        if not linia.strip():
            continue
        m = ITEM_RE.match(linia)
        # „Wiosłowanie hantlem: 4x8-10 na stronę, …” bez myślnika (format akapitowy) to też ćwiczenie
        if not m and re.match(r"^[^:]+:\s*\d+\s*[x×X]\s*\d", linia.strip()):
            m = re.match(r"^\s*(.+?)\s*$", linia)
        if not m:                                       # nagłówek sekcji
            kind, rest_class = rodzaj_sekcji(linia)
            r = RUNDY_RE.search(linia)
            sekcje.append(Section(name=linia.strip().rstrip(":"), kind=kind, rest_class=rest_class,
                                  rounds=int(r.group(1)) if r else None,
                                  circuit=bool(kind == "main" and NAPRZEMIENNIE_RE.search(linia))))
            continue
        if not sekcje:
            sekcje.append(Section(name="Trening", kind="main", rest_class="main"))
        s = sekcje[-1]
        s.items.append(parsuj_linie(m.group(1), s.kind))
    for x in sekcje:
        x.items = grupuj_rundy(x)
    cwiczenia = [i.name_pl for i in wszystkie_cwiczenia(sekcje)]
    rdzenie = lambda t: {w[:5] for w in normalizuj(t).split() if len(w) > 2}
    for x in sekcje:
        for i in x.items:
            if not isinstance(i, WarmupSets) or not cwiczenia:
                continue
            if re.search(r"pierwsz\w*\s+(ćwicz|cwicz)|^$", i.exercise_ref, re.I):
                i.exercise_ref = cwiczenia[0]
            else:                                   # „wyciskania hantli” -> „Wyciskanie hantli na skosie dodatnim”
                r = rdzenie(i.exercise_ref)
                i.exercise_ref = next((c for c in cwiczenia if r and r <= rdzenie(c)), i.exercise_ref)
    return sekcje


def grupuj_rundy(sek):
    """ćwiczenia sekcji „rundy / naprzemiennie” albo zakończone linią „odpocznij po parze” -> Circuit.
    Rund = liczba z nagłówka albo najmniejsza liczba serii w grupie; nadwyżka serii zostaje jako zwykłe ćwiczenie."""
    wynik, grupa = [], []

    def zamknij(przerwa=None):
        nonlocal grupa
        cw = [i for i in grupa if isinstance(i, Exercise)]
        if len(cw) < 2 or not (przerwa or sek.circuit):
            wynik.extend(grupa)
            if przerwa is not None:
                wynik.append(przerwa)
            grupa = []
            return
        rundy = sek.rounds or min(c.sets for c in cw)
        if all(c.sets == 1 for c in cw) and sek.rounds:
            rundy = sek.rounds
        wynik.append(Circuit(exercises=cw, rounds=rundy, rest_s=przerwa.seconds if przerwa else None,
                             raw=przerwa.raw if przerwa else sek.name))
        for c in cw:                                  # „3x” w obwodzie 3 rund = po jednej serii na rundę
            if c.sets > rundy and c.sets != 1:
                wynik.append(Exercise(**{**c.__dict__, "sets": c.sets - rundy}))
        wynik.extend(i for i in grupa if not isinstance(i, Exercise))
        grupa = []

    for i in sek.items:
        if isinstance(i, RoundRest):
            zamknij(i)
        elif isinstance(i, Exercise):
            grupa.append(i)
        else:
            zamknij()
            wynik.append(i)
    zamknij()
    return wynik


def wszystkie_cwiczenia(sekcje):
    for s in sekcje:
        for i in s.items:
            if isinstance(i, Exercise):
                yield i
            elif isinstance(i, Circuit):
                yield from i.exercises


def wyglada_na_silowy(opis):
    """co najmniej jedna linia ćwiczenia „NxM” (drugie kryterium rozpoznania treningu RestOrTrain)"""
    return any(True for _ in wszystkie_cwiczenia(parsuj(opis)))
