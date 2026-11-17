"""Cykl co 20 min (timer): sync → strefy (raz dziennie) → analiza po treningu → analiza poranna (gdy jest sen) →
tygodniowa (poniedziałek) → uzupełnienie/korekta planu → wysłanie zmian na zegarek."""
import json
import logging
from datetime import date, datetime

from . import analiza, baza, cel, config, plan, powiadom, zegarek
from .garmin import BrakLogowania, polacz, wywolaj
from .sync import sync

log = logging.getLogger(__name__)


def odswiez_strefy(g, db):
    if baza.kv(db, "strefy_dzien") == date.today().isoformat():
        return
    s = {}
    for nazwa, f in (("tetno", g.get_heart_rate_zones), ("ftp", g.get_cycling_ftp), ("prog_mleczanowy", g.get_lactate_threshold)):
        try:
            s[nazwa] = wywolaj(f)
        except Exception as ex:
            log.info("strefy %s: %s", nazwa, ex)
    baza.ustaw_kv(db, "strefy", s)
    baza.ustaw_kv(db, "strefy_dzien", date.today().isoformat())


def przeplanuj(powod, prosba="", powiadamiaj=True):
    wyn = plan.zaplanuj(powod, prosba)
    if not wyn:
        return None
    db = baza.polacz()
    if config.ustawienia()["auto_zegarek"]:
        try:
            wyn["zegarek"] = zegarek.synchronizuj_plan(polacz(), db)
        except Exception as ex:
            log.exception("zegarek")
            wyn["zegarek"] = [f"błąd wysyłania: {ex}"]
    if powiadamiaj and wyn["zmiany"]:
        powiadom.powiadom("📅 Plan zmieniony", wyn["komentarz"] + "\n" + "\n".join(wyn["zmiany"][:12]), "/#plan", db)
    return wyn


def cykl():
    db = baza.polacz()
    u = config.ustawienia()
    try:
        w = sync()
    except BrakLogowania as ex:
        if baza.kv(db, "blad_logowania_zgloszony") != date.today().isoformat():
            powiadom.linphone(f"🏋️ Trener: {ex}")
            baza.ustaw_kv(db, "blad_logowania_zgloszony", date.today().isoformat())
        raise
    if w is None:
        return
    g = polacz()
    odswiez_strefy(g, db)
    teraz = datetime.now()
    # 1) po treningu
    tr = analiza.nowe_treningi_do_analizy(db, w["nowe_aktywnosci"])
    if tr:
        try:
            a = analiza.analizuj("trening", aktywnosci=tr, db=db)
            if a and a.get("zmienic_plan"):
                przeplanuj("analiza treningu", a.get("prosba_do_planu", ""))
        except Exception:
            log.exception("analiza treningu")
    # 2) rano, gdy jest dzisiejszy sen
    dzis = baza.dzien(db, date.today().isoformat()) or {}
    if u["analiza_rano"] and dzis.get("sen_h") and teraz.strftime("%H:%M") >= u["analiza_godzina_min"] \
            and not analiza.zrobiona(db, "rano", date.today().isoformat()):
        try:
            a = analiza.analizuj("rano", db=db)
            if a and a.get("zmienic_plan"):
                przeplanuj("analiza poranna", a.get("prosba_do_planu", ""))
            if date.today().weekday() == 0:
                analiza.analizuj("tydzien", db=db)
        except Exception:
            log.exception("analiza poranna")
    # 3) periodyzacja (nowe cele / koniec makrocyklu) → pełne przeplanowanie
    if cel.potrzebny(db):
        try:
            m = cel.zbuduj(db=db)
            powiadom.powiadom("🗺️ Nowa periodyzacja", f"{m['cel_glowny']}: " + " → ".join(f["nazwa"] for f in m["fazy"]), "/#plan", db)
            przeplanuj("nowy makrocykl")
        except Exception:
            log.exception("makrocykl")
    # 4) plan: brakujące dni
    braki = plan.braki(db)
    if braki and (u["cele"] or baza.kv(db, "plan_bez_celow_ok")):
        try:
            przeplanuj(f"uzupełnienie planu ({len(braki)} dni bez treningu)")
        except Exception:
            log.exception("plan")
    # 5) zaległe zmiany planu (np. błąd sieci)
    if u["auto_zegarek"] and db.execute("SELECT 1 FROM plan WHERE stan IN ('nowy','do_usuniecia')").fetchone():
        zegarek.synchronizuj_plan(g, db)
