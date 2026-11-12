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
    sposob: str                    # dokladne | rdzen | rozmyte | nieznane | brak (Garmin nie ma odpowiednika)
    wynik: float = 100.0
    rest_s: int | None = None
    x2: bool | None = None         # jednostronne: True = do Garmina powtórzenia ×2 (obie strony jednym ciągiem)


def oficjalne(sciezka=KAT / "data" / "garmin_exercises.json"):
    """{category: {exerciseName, ...}}"""
    d = json.loads(Path(sciezka).read_text(encoding="utf-8"))["categories"]
    return {k: set(v["exercises"]) for k, v in d.items()}


def wczytaj(sciezka=KAT / "exercises.yaml"):
    return yaml.safe_load(Path(sciezka).read_text(encoding="utf-8"))["cwiczenia"]


def bledy_walidacji(wpisy, lista):
    """wpisy, których para category/exerciseName nie istnieje na oficjalnej liście Garmina"""
    return [w for w in wpisy if not (w.get("category") is None and w.get("exerciseName") is None)
            and w.get("exerciseName") not in lista.get(w.get("category"), set())]


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
        if w["category"] is None:                            # świadomie bez odpowiednika (np. maszyna do prostowania nóg)
            sposob = "brak"
        return Dopasowanie(w["category"], w["exerciseName"], w["nazwa"], sposob, wynik, w.get("rest_s"), w.get("x2"))

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


# ---------------------------------------------------------------- nieznane ćwiczenia: Claude Code (llm_fallback)
CLAUDE = Path("/home/tonyg/.local/bin/claude")
MODEL = "claude-sonnet-5-5"            # dopasowanie nowych ćwiczeń (Haiku mylił, np. uginanie nóg siedząc -> suwnica)
NIEUDANE = KAT / "data" / "llm_nieudane.json"          # nazwa -> czas ostatniej nieudanej próby (ponów po 24 h)


def _claude(prompt):
    import subprocess
    r = subprocess.run([str(CLAUDE), "-p", prompt, "--output-format", "json", "--tools", "", "--strict-mcp-config",
                        "--model", MODEL, "--effort", "low"], capture_output=True, text=True, timeout=90,
                       stdin=subprocess.DEVNULL, cwd=str(KAT))
    d = json.loads(r.stdout or "{}")
    return None if d.get("is_error") else (d.get("result") or "").strip()


def _json_z(tekst):
    import re
    m = re.search(r"\{.*\}", tekst or "", re.S)
    return json.loads(m.group(0)) if m else {}


def dopasuj_llm(nazwa_pl, lista):
    """2 krótkie pytania do Claude (bez narzędzi): kategoria spośród 47, potem ćwiczenie z tej kategorii.
    Wynik zawsze walidowany z oficjalną listą -> (category, exerciseName) albo None"""
    kat = _json_z(_claude(
        f"Ćwiczenie siłowe po polsku: „{nazwa_pl}”. Wybierz JEDNĄ kategorię Garmin, do której najlepiej pasuje, z listy: "
        f"{', '.join(sorted(lista))}. Odpowiedz tylko JSON: {{\"category\": \"...\"}}")).get("category")
    if kat not in lista:
        return None
    cw = _json_z(_claude(
        f"Ćwiczenie siłowe po polsku: „{nazwa_pl}”, kategoria Garmin {kat}. Wybierz JEDNO najbliższe ćwiczenie z listy: "
        f"{', '.join(sorted(lista[kat]))}. Odpowiedz tylko JSON: {{\"exerciseName\": \"...\"}}")).get("exerciseName")
    return (kat, cw) if cw in lista[kat] else None


def dopisz_nieznane(opis, mapa, sciezka=KAT / "exercises.yaml"):
    """nieznane ćwiczenia z opisu -> propozycja Claude (zwalidowana) dopisana do exercises.yaml z „auto: true”;
    zwraca True, gdy coś dopisano. Bez dopasowania: powiadomienie z prośbą o alias."""
    import time
    from .parser import WarmupSets, analizuj, wszystkie_cwiczenia
    from .powiadom import powiadom
    sekcje = analizuj(opis)
    nazwy = {i.name_pl for i in wszystkie_cwiczenia(sekcje)} | \
            {i.exercise_ref for x in sekcje for i in x.items if isinstance(i, WarmupSets)}
    nieznane = [n for n in sorted(nazwy) if mapa.znajdz(n).sposob == "nieznane"]
    if not nieznane:
        return False
    try:
        nieudane = json.loads(NIEUDANE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        nieudane = {}
    lista, dopisane = oficjalne(), []
    for n in nieznane:
        if time.time() - nieudane.get(n, 0) < 86400:
            continue
        try:
            wynik = dopasuj_llm(n, lista)
        except Exception:
            wynik = None
        if not wynik:
            nieudane[n] = time.time()
            powiadom(f"🏋 Garmin: nie umiem dopasować ćwiczenia „{n}”. Dopisz alias w ~/restortrain-garmin/exercises.yaml.")
            continue
        with open(sciezka, "a", encoding="utf-8") as f:
            f.write(f"  - nazwa: {n.lower()}\n    aliasy: []\n    category: {wynik[0]}\n    exerciseName: {wynik[1]}\n"
                    f"    auto: true                      # propozycja Claude ({time.strftime('%Y-%m-%d')}), do przejrzenia\n")
        dopisane.append(f"{n} → {wynik[0]}/{wynik[1]}")
    NIEUDANE.parent.mkdir(exist_ok=True)
    NIEUDANE.write_text(json.dumps(nieudane, ensure_ascii=False), encoding="utf-8")
    if dopisane:
        powiadom("🏋 Garmin: Claude dopisał ćwiczenia (sprawdź, czy pasują): " + "; ".join(dopisane))
    return bool(dopisane)
