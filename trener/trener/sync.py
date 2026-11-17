"""Pobieranie danych z Garmina: dni (sen, HRV, podsumowanie, gotowość, status) i aktywności.
`sync`  — ostatnie dni + nowe aktywności (timer co 30 min),
`historia` — cała historia od najnowszych do START_HISTORII (raz, potem tylko uzupełnia braki)."""
import fcntl
import logging
from datetime import date, datetime, timedelta

from . import baza, config, dane
from .garmin import polacz, wywolaj

log = logging.getLogger(__name__)
TYPY = ("sum", "sen", "hrv", "gotowosc", "status")


def _pobierz(g, typ, d):
    f = {"sum": g.get_user_summary, "sen": g.get_sleep_data, "hrv": g.get_hrv_data,
         "gotowosc": g.get_training_readiness, "status": g.get_training_status}[typ]
    w = wywolaj(f, d)
    return dane.przytnij_sen(w) if typ == "sen" else w


def _ostateczny(db, typ, d):
    """dane dnia są ostateczne, gdy pobrano je co najmniej 2 dni po nim"""
    r = db.execute("SELECT pobrano FROM surowe WHERE typ=? AND dzien=?", (typ, d)).fetchone()
    return bool(r) and r[0][:10] >= (date.fromisoformat(d) + timedelta(days=2)).isoformat()


def synchronizuj_dzien(g, db, d, wymus=False):
    zm = 0
    for typ in TYPY:
        if not wymus and _ostateczny(db, typ, d):
            continue
        baza.zapisz_surowe(db, typ, d, _pobierz(g, typ, d))
        zm += 1
    if zm:
        dane.wylicz(db, d)
        db.commit()
    return zm


def _zapisz_aktywnosc(db, a):
    start = a.get("startTimeLocal") or ""
    stara = db.execute("SELECT szczegoly FROM aktywnosci WHERE id=?", (a["activityId"],)).fetchone()
    db.execute("INSERT OR REPLACE INTO aktywnosci VALUES (?,?,?,?,?,?,?,?)",
               (a["activityId"], start, start[:10], (a.get("activityType") or {}).get("typeKey"), a.get("activityName"),
                baza.pakuj(a), stara[0] if stara else None, baza.teraz()))
    return stara is None


def synchronizuj_aktywnosci(g, db, wszystkie=False):
    """nowe (i zmienione) aktywności; przy `wszystkie` cała lista stronami po 100"""
    nowe, start, porcja = [], 0, 100 if wszystkie else 20
    while True:
        lista = wywolaj(g.get_activities, start, porcja) or []
        if not lista:
            break
        n = 0
        for a in lista:
            if _zapisz_aktywnosc(db, a):
                nowe.append(a)
                n += 1
        db.commit()
        if not wszystkie and n < len(lista):
            break
        start += porcja
    for a in nowe:
        if (a.get("activityType") or {}).get("typeKey") == "strength_training":
            sz = wywolaj(g.get_activity_exercise_sets, a["activityId"])
            db.execute("UPDATE aktywnosci SET szczegoly=? WHERE id=?", (baza.pakuj(sz), a["activityId"]))
    for d in sorted({(a.get("startTimeLocal") or "")[:10] for a in nowe} - {""}):
        dane.wylicz(db, d)
    db.commit()
    return nowe


def _zablokuj(nazwa):
    config.DANE.mkdir(parents=True, exist_ok=True)
    f = open(config.DANE / f"{nazwa}.lock", "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return None
    return f


def sync(dni=3):
    """szybka synchronizacja: ostatnie `dni` dni (zawsze od nowa) + nowe aktywności"""
    blok = _zablokuj("sync")
    if not blok:
        log.info("sync już trwa")
        return None
    db = baza.polacz()
    g = polacz()
    nowe = synchronizuj_aktywnosci(g, db)
    for d in dane.dni_wstecz(dni):
        synchronizuj_dzien(g, db, d, wymus=True)
    baza.ustaw_kv(db, "ostatni_sync", baza.teraz())
    log.info("sync: %d nowych aktywności", len(nowe))
    return {"nowe_aktywnosci": nowe, "db": db}


def historia(od=None):
    """cała historia: aktywności + każdy dzień od dziś wstecz (pomija dni już ostateczne)"""
    blok = _zablokuj("historia")
    if not blok:
        log.info("historia już trwa")
        return
    db = baza.polacz()
    g = polacz()
    synchronizuj_aktywnosci(g, db, wszystkie=True)
    pierwsza = db.execute("SELECT MIN(dzien) FROM aktywnosci").fetchone()[0] or config.START_HISTORII
    od = od or min(pierwsza, config.START_HISTORII)
    d, n = date.today(), 0
    while d.isoformat() >= od:
        n += synchronizuj_dzien(g, db, d.isoformat())
        if n and n % 50 == 0:
            log.info("historia: %s (%d zapytań)", d, n)
            baza.ustaw_kv(db, "historia_postep", d.isoformat())
        d -= timedelta(days=1)
    baza.ustaw_kv(db, "historia_postep", "gotowe")
    baza.ustaw_kv(db, "historia_koniec", baza.teraz())
    log.info("historia gotowa: %d zapytań", n)
