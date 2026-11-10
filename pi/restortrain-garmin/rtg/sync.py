"""
Synchronizacja (spec, sekcja 8): kalendarz Garmin Connect (dziś … dziś + okno_dni) -> treningi siłowe od RestOrTrain
(`workout.consumerName == "RestOrTrain"`, sport siłowy, opis z „NxM”) -> natywny trening siłowy na ten sam dzień.

Stan w SQLite (data/state.db, klucz: source_workout_id + date): nowy -> utwórz i zaplanuj; inny hash opisu -> usuń nasz
stary i utwórz nowy; bez zmian -> pomiń; oryginał zniknął z kalendarza -> odplanuj i usuń nasz. Usuwamy WYŁĄCZNIE treningi
ze znacznikiem „auto: restortrain-garmin” w opisie (sprawdzane w Garmin przed usunięciem).
Ustawienia: config.yaml, nadpisywane przez stronę Automatyczne (portal /api/automaty, moduł „garmin”).
"""
import json
import logging
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from .builder import WERSJA, buduj, hash_opisu, nasz
from .garmin import BrakLogowania, api, polacz
from .mapping import Mapa, dopisz_nieznane
from . import parser
from .parser import wyglada_na_silowy
from .powiadom import powiadom
from .stan import baza

log = logging.getLogger("rtg.sync")
KAT = Path(__file__).resolve().parent.parent
ZRODLO = "RestOrTrain"
SILOWY = "strength_training"
AKTYWNOSC_SILOWA = 13                      # activityTypeId zrobionego treningu siłowego w kalendarzu Garmina


def konfiguracja():
    cfg = yaml.safe_load((KAT / "config.yaml").read_text(encoding="utf-8"))
    try:                                    # ustawienia ze strony (portal na tym samym Pi)
        with urllib.request.urlopen("http://127.0.0.1/api/automaty", timeout=5) as r:
            g = json.loads(r.read())["wartosci"]["garmin"]
        cfg.update({k: g[k] for k in ("wlaczony", "co_min", "okno_dni", "rep_target", "rest_mode", "replace_original", "przejscie", "raport_linphone", "przejscie_rundy_s", "sprzataj_po_treningu") if k in g})
        cfg["przerwy_s"] = {k: g.get(f"przerwa_{k}", cfg["przerwy_s"].get(k)) for k in ("main", "accessory", "core", "warmup")}
    except (OSError, ValueError, KeyError):
        pass
    return cfg


def kalendarz(g, od, do):
    """(treningi siłowe zaplanowane w oknie, daty ze zrobionym już treningiem siłowym)"""
    pozycje, miesiace = [], sorted({(od.year, od.month), (do.year, do.month)})
    for r, m in miesiace:
        pozycje += api(g, "GET", f"/calendar-service/year/{r}/month/{m - 1}").get("calendarItems", [])   # miesiąc od 0
    w_oknie = [p for p in pozycje if od.isoformat() <= p.get("date", "") <= do.isoformat()]
    zrobione = {p["date"] for p in w_oknie if p.get("itemType") == "activity" and p.get("activityTypeId") == AKTYWNOSC_SILOWA}
    # tylko siła: szczegóły pobieramy wyłącznie dla treningów siłowych (bieg, rower itd. odpadają już tutaj)
    return [p for p in w_oknie if p.get("itemType") == "workout" and p.get("sportTypeKey") == SILOWY], zrobione


def sprzataj_oryginaly(g, db, cfg, zmiany, dni=3):
    """dzień ze zrobionym treningiem siłowym (ostatnie 3 dni): odplanuj z kalendarza oryginał RestOrTrain z tego dnia
    (tylko wpis w kalendarzu; definicja treningu zostaje). Tylko oryginały znane z bazy (source_workout_id)."""
    if not cfg.get("sprzataj_po_treningu", True):
        return
    dzis = date.today()
    pozycje, zrobione = kalendarz(g, dzis - timedelta(days=dni), dzis)
    zrodla = {r[0] for r in db.execute("SELECT source_workout_id FROM treningi")}
    for p in pozycje:
        if p["date"] in zrobione and str(p.get("workoutId")) in zrodla and p.get("id"):
            try:
                g.unschedule_workout(p["id"])
                zmiany.append(f"zrobiony trening {p['date']}: zdjęty z kalendarza oryginał „{p.get('title')}”")
            except Exception as ex:
                log.info("odplanowanie oryginału %s: %s", p["id"], type(ex).__name__)
            time.sleep(0.3)


def usun_nasz(g, workout_id, pozycje, dry_run, zmiany):
    """odplanuj i usuń trening — tylko jeśli ma nasz znacznik"""
    if not workout_id:
        return
    try:
        w = api(g, "GET", f"/workout-service/workout/{workout_id}")
    except Exception:
        return                                  # już go nie ma
    if not nasz(w):
        log.error("trening %s nie ma znacznika usługi: NIE usuwam", workout_id)
        return
    zmiany.append(f"usuń nasz trening {workout_id} ({w.get('workoutName')})")
    if dry_run:
        return
    for p in pozycje:
        if str(p.get("workoutId")) == str(workout_id) and p.get("id"):
            try:
                g.unschedule_workout(p["id"])
            except Exception as ex:             # 404: już odplanowany (Garmin zdejmuje go też przy usunięciu)
                log.info("odplanowanie %s: %s", p["id"], type(ex).__name__)
            time.sleep(0.5)
    try:
        g.delete_workout(workout_id)
    except Exception as ex:
        if "404" not in str(ex) and "NotFound" not in type(ex).__name__:
            raise


def utworz(g, zrodlo, data, cfg, mapa, dry_run, zmiany, nieznane, pokaz_json=False):
    w = buduj(zrodlo, cfg, mapa, nieznane)
    zmiany.append(f"utwórz „{w['workoutName']}” na {data}")
    if dry_run:
        if pokaz_json:
            print(json.dumps(w, ensure_ascii=False, indent=1))
        return None, None
    r = g.upload_workout(w)
    wid = r.get("workoutId")
    time.sleep(0.5)
    s = g.schedule_workout(wid, data)
    return wid, (s or {}).get("workoutScheduleId") or (s or {}).get("id")


def synchronizuj(dry_run=False, wymus=False, do_dnia=None):
    import fcntl
    blokada = open(KAT / "data" / "sync.lock", "w")
    try:                                    # timer i przycisk „teraz” naraz: drugi przebieg czeka na pierwszy
        fcntl.flock(blokada, fcntl.LOCK_EX)
    except OSError:
        pass
    cfg = konfiguracja()
    db = baza()
    teraz = datetime.now().isoformat(timespec="seconds")
    if not wymus and not dry_run:
        if not cfg.get("wlaczony", True):
            log.info("synchronizacja wyłączona na stronie Automatyczne")
            return 0
        ost = db.execute("SELECT t FROM przebiegi WHERE wynik='ok' ORDER BY t DESC LIMIT 1").fetchone()
        if ost and datetime.now() - datetime.fromisoformat(ost[0]) < timedelta(minutes=int(cfg.get("co_min", 10)) - 2):
            log.info("ostatni przebieg %s, następny wg ustawienia co %s min", ost[0], cfg.get("co_min"))
            return 0
    pokaz_json = dry_run                                # --dry-run z terminala: pełny JSON; tryb próbny z timera: sam plan
    proba = False
    if not cfg.get("zapis_dozwolony") and not dry_run:
        dry_run = proba = True                                  # przed zgodą Antka na zapis: tylko plan zmian
        log.info("zapis do Garmin Connect jeszcze niedozwolony (config.yaml: zapis_dozwolony): tylko plan")
    zmiany, nieznane = [], []
    try:
        g = polacz()
        od = date.today()
        do = date.fromisoformat(do_dnia) if do_dnia else od + timedelta(days=int(cfg.get("okno_dni", 14)))
        pozycje, zrobione = kalendarz(g, od, do)
        mapa = Mapa()
        parser.AI["wlaczone"] = bool(cfg.get("ai_analiza", True))      # opis czyta Claude (Sonnet), reguły jako zapas
        aktualne = set()
        for p in pozycje:
            if p["date"] in zrobione:                       # trening siłowy tego dnia już zrobiony: nie ruszamy
                aktualne |= {(r[0], p["date"]) for r in db.execute("SELECT source_workout_id FROM treningi WHERE date=?", (p["date"],))}
                continue
            if (str(p["workoutId"]), p["date"]) in {(r[0], r[1]) for r in db.execute("SELECT generated_workout_id, date FROM treningi")}:
                continue                                    # nasz wygenerowany trening: bez pobierania szczegółów
            try:
                w = api(g, "GET", f"/workout-service/workout/{p['workoutId']}")
            except Exception as ex:             # 404: np. nasz stary trening usunięty chwilę wcześniej w tym przebiegu
                if "404" in str(ex) or "NotFound" in type(ex).__name__:
                    continue
                raise
            time.sleep(0.3)
            if nasz(w) or w.get("consumerName") != ZRODLO or not wyglada_na_silowy(w.get("description") or ""):
                continue
            # hash: opis + wersja budowy + ustawienia (zmiana przerw / trybu na stronie też przebudowuje treningi)
            ust = json.dumps({k: cfg.get(k) for k in ("rep_target", "rest_mode", "przerwy_s", "przejscie", "ai_analiza", "przejscie_rundy_s")}, sort_keys=True) + hash_opisu((KAT / "exercises.yaml").read_text(encoding="utf-8"))[:12]   # zmiana mapowania -> przebudowa
            src, d, h = str(w["workoutId"]), p["date"], hash_opisu((w.get("description") or "") + WERSJA + ust)
            aktualne.add((src, d))
            if cfg.get("llm_fallback") and dopisz_nieznane(w.get("description") or "", mapa):
                mapa = Mapa()                               # Claude Code dopisał ćwiczenia do exercises.yaml
            row = db.execute("SELECT description_hash, generated_workout_id FROM treningi WHERE source_workout_id=? AND date=?", (src, d)).fetchone()
            if row and row[0] == h and row[1]:
                continue                                        # bez zmian
            if row and row[1]:
                usun_nasz(g, row[1], pozycje, dry_run, zmiany)  # opis się zmienił
            wid, sid = utworz(g, {**w, "title": p.get("title")}, d, cfg, mapa, dry_run, zmiany, nieznane, pokaz_json)
            if cfg.get("replace_original") and not dry_run and p.get("id"):
                g.unschedule_workout(p["id"])                   # oryginał z kalendarza (definicja zostaje)
                zmiany.append(f"zdejmij oryginał „{w.get('workoutName')}” z {d}")
            if not dry_run:
                db.execute("INSERT OR REPLACE INTO treningi VALUES (?,?,?,?,?,?,?,?,?)",
                           (src, d, h, str(wid), str(sid or ""), str(p.get("id") or ""), w.get("workoutName"),
                            "zastapiony" if cfg.get("replace_original") else "ok", teraz))
        # oryginał zniknął z kalendarza (RestOrTrain przeniósł / usunął): usuń nasz odpowiednik. Bezpiecznik: nic nie
        # usuwamy, gdy kalendarz wrócił bez żadnego treningu siłowego (chwilowa odpowiedź Garmina), a nasz trening dopiero
        # wtedy, gdy oryginału brak przy 2 kolejnych przebiegach (status „brak1” po pierwszym)
        if pozycje or not db.execute("SELECT 1 FROM treningi WHERE date >= ?", (od.isoformat(),)).fetchone():
            for src, d, gen, status in db.execute("SELECT source_workout_id, date, generated_workout_id, status FROM treningi WHERE date >= ?",
                                                   (od.isoformat(),)).fetchall():
                if (src, d) in aktualne or status == "zastapiony" or d > do.isoformat() or d in zrobione:
                    if status == "brak1" and not dry_run:
                        db.execute("UPDATE treningi SET status='ok' WHERE source_workout_id=? AND date=?", (src, d))
                    continue
                if status != "brak1":
                    if not dry_run:
                        db.execute("UPDATE treningi SET status='brak1' WHERE source_workout_id=? AND date=?", (src, d))
                    zmiany.append(f"oryginał z {d} zniknął (usunę nasz przy następnym sprawdzeniu, jeśli dalej go nie ma)")
                    continue
                usun_nasz(g, gen, pozycje, dry_run, zmiany)
                if not dry_run:
                    db.execute("DELETE FROM treningi WHERE source_workout_id=? AND date=?", (src, d))
        else:
            log.warning("kalendarz bez treningów siłowych, a w bazie są przyszłe: pomijam usuwanie (chwilowa odpowiedź?)")
        if not dry_run:
            db.commit()
            try:                                # po zrobionym treningu siłowym: zdejmij oryginał RestOrTrain z kalendarza
                sprzataj_oryginaly(g, db, cfg, zmiany)
            except Exception as ex:
                log.warning("sprzątanie oryginałów: %s: %s", type(ex).__name__, ex)
            try:                                # zrobione treningi -> raporty (strona + Linphone), plany do zrobienia
                from .raport import sprawdz_zrobione, zapisz_plany
                if (n := sprawdz_zrobione(g, cfg)):
                    zmiany.append(f"nowe raporty: {n}")
                zapisz_plany(g, db)
            except Exception as ex:             # raport nie może zepsuć synchronizacji
                log.warning("raporty: %s: %s", type(ex).__name__, ex)
        wynik, opis = "ok", "; ".join(zmiany) or "bez zmian"
    except BrakLogowania as ex:
        wynik, opis = "blad", str(ex)
        if not dry_run:
            powiadom(f"🏋 Garmin: logowanie wygasło. Zaloguj się: portal → Zdalne → Terminal → cd ~/restortrain-garmin && ./rtg.sh login")
    except Exception as ex:
        log.exception("synchronizacja")
        wynik, opis = "blad", f"{type(ex).__name__}: {ex}"[:300]
    if nieznane and not dry_run:
        powiadom("🏋 Garmin: nieznane ćwiczenia (dopisz alias w ~/restortrain-garmin/exercises.yaml): " + ", ".join(sorted(set(nieznane))))
    if not dry_run or proba:
        db.execute("INSERT INTO przebiegi VALUES (?,?,?)", (teraz, wynik, ("[próba, bez zapisu] " if proba else "") + opis))
        db.commit()
        bledy = [r[0] for r in db.execute("SELECT wynik FROM przebiegi ORDER BY t DESC LIMIT 3")]
        if wynik == "blad" and bledy == ["blad"] * 3:
            powiadom(f"🏋 Garmin: 3 nieudane synchronizacje z rzędu. Ostatni błąd: {opis}")
    print(("[dry-run] " if dry_run else "") + f"{wynik}: {opis}")
    return 0 if wynik == "ok" else 1
