"""
restortrain-garmin: CLI
  ./rtg.sh parse <plik.txt>          parser + mapowanie, czytelny wydruk (bez sieci)
  ./rtg.sh login                     logowanie do Garmin Connect (MFA), zapis tylko tokenu
  ./rtg.sh pobierz-wzorce [nazwa]    zapisuje JSON-y do tests/fixtures (trening referencyjny + RestOrTrain)
  ./rtg.sh sync [--dry-run]          synchronizacja (etap 6+)
  ./rtg.sh status                    ostatnie uruchomienia i stan treningów
"""
import argparse
import json
import logging
import sys
from pathlib import Path

from .mapping import Mapa
from .parser import Exercise, TimedBlock, Unparsed, WarmupSets, parsuj

KAT = Path(__file__).resolve().parent.parent


def drukuj_parse(tekst):
    m = Mapa()
    for s in parsuj(tekst):
        print(f"\n== {s.name}  [{s.kind}, przerwy: {s.rest_class}]")
        for i in s.items:
            if isinstance(i, TimedBlock):
                print(f"  ⏱  {i.seconds // 60} min {i.seconds % 60:02d} s  {i.text}  ({i.kind})")
            elif isinstance(i, WarmupSets):
                d = m.znajdz(i.exercise_ref)
                print(f"  🔥 serie wstępne {i.sets_min}-{i.sets_max} × (do przycisku)  {i.exercise_ref} -> "
                      f"{d.category}/{d.exerciseName} [{d.sposob}]")
            elif isinstance(i, Exercise):
                d = m.znajdz(i.name_pl)
                ile = f"{i.reps_min}-{i.reps_max} powt." if i.reps_max and i.reps_min != i.reps_max else \
                      f"{i.reps_max} powt." if i.reps_max else f"{i.duration_s} s"
                print(f"  🏋  {i.name_pl}: {i.sets} serie × {ile}{' (na stronę)' if i.per_side else ''}"
                      f"{' · ' + i.note if i.note else ''}\n      -> {d.category}/{d.exerciseName} [{d.sposob}"
                      f"{f' {d.wynik:.0f}' if d.sposob == 'rozmyte' else ''}]")
            elif isinstance(i, Unparsed):
                print(f"  ❓ nie rozumiem: {i.raw} (krok do przycisku okrążenia)")


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="rtg", description="RestOrTrain -> natywne treningi siłowe Garmin")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("parse")
    sp.add_argument("plik")
    sub.add_parser("login")
    pw = sub.add_parser("pobierz-wzorce")
    pw.add_argument("nazwa", nargs="?", help="nazwa ręcznie utworzonego treningu referencyjnego")
    ss = sub.add_parser("sync")
    ss.add_argument("--dry-run", action="store_true")
    ss.add_argument("--teraz", action="store_true", help="bez czekania na odstęp z ustawień (przycisk „Synchronizuj teraz”)")
    sub.add_parser("status")
    a = p.parse_args(argv)
    if a.cmd == "parse":
        drukuj_parse(Path(a.plik).read_text(encoding="utf-8"))
    elif a.cmd == "login":
        from .garmin import zaloguj_interaktywnie
        g = zaloguj_interaktywnie()
        print(f"✅ Zalogowano ({g.get_full_name() if hasattr(g, 'get_full_name') else 'OK'}). Token zapisany w tokens/.")
    elif a.cmd == "pobierz-wzorce":
        from .wzorce import pobierz_wzorce
        pobierz_wzorce(a.nazwa)
    elif a.cmd == "sync":
        from .sync import synchronizuj
        sys.exit(synchronizuj(dry_run=a.dry_run, wymus=a.teraz))
    elif a.cmd == "status":
        from .stan import drukuj_status
        drukuj_status()


if __name__ == "__main__":
    main()
