"""
Mapowanie polskich nazw ćwiczeń na natywne ćwiczenia Garmin (exercises.yaml), walidacja z oficjalną listą
(data/garmin_exercises.json). Dopasowanie: dokładne po nazwie/aliasach (po normalizacji) -> po rdzeniach słów
(pierwsze 5 liter, np. „martwego ciągu” = „martwy ciąg”) -> rozmyte (rapidfuzz, próg 90). Poniżej progu: nieznane.
"""
import json
from dataclasses import dataclass
from pathlib import Path

import yaml
from rapidfuzz import fuzz, process

from .parser import normalizuj

KAT = Path(__file__).resolve().parent.parent
PROG = 90


@dataclass
class Dopasowanie:
    category: str | None
    exerciseName: str | None
    nazwa: str | None              # wpis z exercises.yaml
    sposob: str                    # dokladne | rdzen | rozmyte | nieznane
    wynik: float = 100.0
    rest_s: int | None = None


def oficjalne(sciezka=KAT / "data" / "garmin_exercises.json"):
    """{category: {exerciseName, ...}}"""
    d = json.loads(Path(sciezka).read_text(encoding="utf-8"))["categories"]
    return {k: set(v["exercises"]) for k, v in d.items()}


def wczytaj(sciezka=KAT / "exercises.yaml"):
    return yaml.safe_load(Path(sciezka).read_text(encoding="utf-8"))["cwiczenia"]


def bledy_walidacji(wpisy, lista):
    """wpisy, których para category/exerciseName nie istnieje na oficjalnej liście Garmina"""
    return [w for w in wpisy if w.get("exerciseName") not in lista.get(w.get("category"), set())]


def rdzen(t):
    return tuple(s[:5] for s in normalizuj(t).replace(",", " ").split() if len(s) > 2)


class Mapa:
    def __init__(self, wpisy=None):
        self.wpisy = wpisy if wpisy is not None else wczytaj()
        self.klucze = {}                                     # znormalizowana nazwa/alias -> wpis
        for w in self.wpisy:
            for n in [w["nazwa"], *w.get("aliasy", [])]:
                self.klucze.setdefault(normalizuj(n), w)

    def _wynik(self, w, sposob, wynik=100.0):
        return Dopasowanie(w["category"], w["exerciseName"], w["nazwa"], sposob, wynik, w.get("rest_s"))

    def znajdz(self, nazwa_pl):
        n = normalizuj(nazwa_pl)
        if n in self.klucze:
            return self._wynik(self.klucze[n], "dokladne")
        r = rdzen(nazwa_pl)
        for k, w in self.klucze.items():
            if r and rdzen(k) == r:
                return self._wynik(w, "rdzen")
        m = process.extractOne(n, list(self.klucze), scorer=fuzz.token_sort_ratio)
        if m and m[1] >= PROG:
            return self._wynik(self.klucze[m[0]], "rozmyte", m[1])
        return Dopasowanie(None, None, None, "nieznane", m[1] if m else 0.0)
