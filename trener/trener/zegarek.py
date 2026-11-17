"""Zapis planu do Garmin Connect: tworzenie treningu + wpis w kalendarzu; usuwanie TYLKO treningów ze znacznikiem."""
import json
import logging

from . import baza, budowa, config
from .garmin import api, wywolaj

log = logging.getLogger(__name__)


def nasz(g, workout_id):
    w = api(g, "GET", f"/workout-service/workout/{workout_id}")
    return w is not None and config.ZNACZNIK in (w.get("description") or ""), w


def usun(g, workout_id):
    """usuwa definicję treningu (Garmin zdejmuje go też z kalendarza) — tylko gdy ma znacznik apki"""
    if not workout_id:
        return True
    moj, w = nasz(g, workout_id)
    if w is None:
        return True                                   # już nie ma
    if not moj:
        log.warning("trening %s bez znacznika — NIE usuwam", workout_id)
        return False
    api(g, "DELETE", f"/workout-service/workout/{workout_id}")
    return True


def wyslij(g, t):
    """t = wiersz planu (dict z kroki jako lista) → (workout_id, kalendarz_id)"""
    w = budowa.buduj(t)
    r = wywolaj(g.upload_workout, w)
    wid = (r or {}).get("workoutId")
    if not wid:
        raise RuntimeError(f"Garmin nie zwrócił workoutId: {str(r)[:200]}")
    s = wywolaj(g.schedule_workout, wid, t["dzien"])
    kid = (s or {}).get("workoutScheduleId") or (s or {}).get("id")
    return wid, kid


def synchronizuj_plan(g, db):
    """stan planu → Garmin: 'nowy'/'zmieniony' wysyła, 'do_usuniecia' usuwa. -> lista opisów zmian"""
    zm = []
    for r in db.execute("SELECT * FROM plan WHERE stan IN ('do_usuniecia') ORDER BY dzien").fetchall():
        if usun(g, r["workout_id"]):
            db.execute("UPDATE plan SET stan='usuniety', zmieniono=? WHERE id=?", (baza.teraz(), r["id"]))
            zm.append(f"usunięty: {r['dzien']} {r['tytul']}")
        db.commit()
    for r in db.execute("SELECT * FROM plan WHERE stan IN ('nowy') ORDER BY dzien").fetchall():
        t = dict(r)
        if t["sport"] not in budowa.SPORT:            # odpoczynek / inne: tylko w apce
            db.execute("UPDATE plan SET stan='w_apce' WHERE id=?", (r["id"],))
            db.commit()
            continue
        t["kroki"] = json.loads(r["kroki"] or "[]")
        try:
            wid, kid = wyslij(g, t)
            db.execute("UPDATE plan SET stan='na_zegarku', workout_id=?, kalendarz_id=?, zmieniono=? WHERE id=?",
                       (wid, kid, baza.teraz(), r["id"]))
            zm.append(f"na zegarek: {t['dzien']} {t['tytul']}")
        except Exception as ex:                       # zły plan nie może zatrzymać reszty
            log.exception("nie wysłano %s", t["tytul"])
            db.execute("UPDATE plan SET stan='blad', zmieniono=?, zrodlo=? WHERE id=?",
                       (baza.teraz(), f"błąd: {str(ex)[:200]}", r["id"]))
        db.commit()
    return zm
