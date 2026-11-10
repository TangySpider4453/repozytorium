"""Etap 4 (inżynieria wsteczna): pobiera prawdziwe JSON-y z Garmin Connect do tests/fixtures/:
- reference_strength_workout.json: ręcznie utworzony przez Antka trening siłowy (po nazwie),
- restortrain_<id>.json: treningi z kalendarza (14 dni), które wyglądają na siłowe od RestOrTrain,
- calendar_items.json: pozycje kalendarza (do znalezienia pola „źródła” RestOrTrain).
Nic nie zapisuje w Garmin Connect (tylko GET)."""
import json
import re
from datetime import date, timedelta
from pathlib import Path

from .garmin import api, polacz
from .parser import wyglada_na_silowy

FIX = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def miesiace(od, do):
    m = {(od.year, od.month), (do.year, do.month)}
    return sorted(m)


def pola_zrodla(d, sciezka=""):
    """wszystkie pola, których nazwa albo wartość wskazuje na źródło/aplikację partnerską"""
    wyn = []
    if isinstance(d, dict):
        for k, v in d.items():
            p = f"{sciezka}.{k}" if sciezka else k
            if re.search(r"provider|source|partner|app|author|owner|creat|origin|consumer|atp|external", k, re.I) and not isinstance(v, (dict, list)):
                wyn.append((p, v))
            elif isinstance(v, str) and re.search(r"restortrain", v, re.I):
                wyn.append((p, v))
            wyn += pola_zrodla(v, p)
    elif isinstance(d, list):
        for i, v in enumerate(d[:50]):
            wyn += pola_zrodla(v, f"{sciezka}[{i}]")
    return wyn


def pobierz_wzorce(nazwa_ref=None):
    FIX.mkdir(parents=True, exist_ok=True)
    g = polacz()
    dzis = date.today()
    pozycje = []
    for r, m in miesiace(dzis, dzis + timedelta(days=14)):
        pozycje += api(g, "GET", f"/calendar-service/year/{r}/month/{m - 1}").get("calendarItems", [])   # miesiąc od 0
    (FIX / "calendar_items.json").write_text(json.dumps(pozycje, ensure_ascii=False, indent=1), encoding="utf-8")
    treningi = [p for p in pozycje if p.get("itemType") == "workout" and dzis.isoformat() <= p.get("date", "") <= (dzis + timedelta(days=14)).isoformat()]
    print(f"Kalendarz: {len(pozycje)} pozycji, treningów w 14 dniach: {len(treningi)}")
    for p in treningi:
        w = api(g, "GET", f"/workout-service/workout/{p['workoutId']}")
        sport = (w.get("sportType") or {}).get("sportTypeKey")
        silowy = wyglada_na_silowy(w.get("description") or "")
        print(f"  {p['date']} {p.get('title')!r} sport={sport} siłowy_opis={silowy} workoutId={p['workoutId']}")
        if silowy:
            (FIX / f"restortrain_{p['workoutId']}.json").write_text(json.dumps({"kalendarz": p, "workout": w}, ensure_ascii=False, indent=1), encoding="utf-8")
            for k, v in pola_zrodla({"kalendarz": p, "workout": w}):
                print(f"      źródło? {k} = {v!r}")
    if nazwa_ref:
        lista = g.get_workouts(0, 200)
        ref = next((w for w in lista if (w.get("workoutName") or "").strip().lower() == nazwa_ref.strip().lower()), None)
        if not ref:
            print(f"❌ Nie znalazłem treningu „{nazwa_ref}” w bibliotece treningów.")
        else:
            w = api(g, "GET", f"/workout-service/workout/{ref['workoutId']}")
            (FIX / "reference_strength_workout.json").write_text(json.dumps(w, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"✅ Trening referencyjny zapisany (workoutId={ref['workoutId']}).")
