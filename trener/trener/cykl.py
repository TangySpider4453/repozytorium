"""Cykl co 15 min (timer; `szybki` co minutę odpala go wcześniej, gdy w Garminie pojawi się nowy trening): sync → strefy (raz dziennie) → analiza po treningu → analiza poranna (gdy jest sen) →
tygodniowa (poniedziałek) → uzupełnienie/korekta planu → wysłanie zmian na zegarek."""
import json
import logging
from datetime import date, datetime, timedelta

from . import analiza, baza, cel, config, plan, powiadom, zegarek
from .garmin import BrakLogowania, polacz, wywolaj
from .sync import _zablokuj, sync

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


def przeplanuj(powod, prosba="", powiadamiaj=True, pytaj=False):
    wyn = plan.zaplanuj(powod, prosba, pytaj=pytaj)
    if not wyn:
        return None
    db = baza.polacz()
    if config.ustawienia()["auto_zegarek"]:
        try:
            wyn["zegarek"] = zegarek.synchronizuj_plan(polacz(), db)
        except Exception as ex:
            log.exception("zegarek")
            wyn["zegarek"] = [f"błąd wysyłania: {ex}"]
    try:
        from . import dieta
        dieta.po_zmianie_planu()
    except Exception:
        log.exception("cel kalorii po zmianie planu")
    p = wyn.get("propozycja")
    if p:                                     # duża zmiana (usunięcie/dodanie jednostki) → pytanie do Antka
        powiadom.powiadom("❓ Trener pyta: zmienić plan?", wyn["komentarz"] + "\n" + "\n".join(p["zmiany"][:8])
                          + ("\nJuż zmienione: " + "; ".join(wyn["zmiany"][:6]) if wyn["zmiany"] else "")
                          + "\nSłabo się czujesz → Zmień. Czujesz się dobrze → Zostaw.", "/#plan", db)
    elif powiadamiaj and wyn["zmiany"]:
        powiadom.powiadom("📅 Plan zmieniony", wyn["komentarz"] + "\n" + "\n".join(wyn["zmiany"][:12]), "/#plan", db)
    return wyn


def szybki():
    """co minutę (timer): tylko 5 ostatnich aktywności z Garmina; nowa → od razu pełny cykl (analiza + push)"""
    db = baza.polacz()
    pauza = baza.kv(db, "szybki_pauza")
    if pauza and pauza > baza.teraz():
        return
    try:
        lista = wywolaj(polacz().get_activities, 0, 5) or []
    except BrakLogowania:
        return                                # zgłasza pełny cykl
    except Exception as ex:                   # np. 429 po ponowieniach → 10 min przerwy
        log.warning("szybki: %s", str(ex)[:120])
        baza.ustaw_kv(db, "szybki_pauza", (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S"))
        return
    nowe = [a for a in lista if not db.execute("SELECT 1 FROM aktywnosci WHERE id=?", (a["activityId"],)).fetchone()]
    if nowe:
        log.info("szybki: nowa aktywność %s → cykl", ", ".join(str(a.get("activityName")) for a in nowe))
        cykl()


def cykl():
    blok = _zablokuj("cykl")                  # cykl z timera i ze `szybki` nigdy naraz
    if not blok:
        log.info("cykl już trwa")
        return
    db = baza.polacz()
    u = config.ustawienia()
    try:                                      # 0) pytanie z czatu odłożone przez limit Claude
        from .czat import dokoncz_czekajace
        dokoncz_czekajace()
    except Exception:
        log.exception("odłożony czat")
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
                przeplanuj("analiza treningu", a.get("prosba_do_planu", ""), pytaj=True)
        except Exception:
            log.exception("analiza treningu")
        if any(a.get("activityType", {}).get("typeKey") == "strength_training" for a in w["nowe_aktywnosci"]):
            try:
                from . import tierlista
                tierlista.zapytaj_po_treningu(db)
            except Exception:
                log.exception("tierlista")
    # 1b) cel jedzenia: nowy trening → przelicz; co godzinę nowe aktywne kcal z Garmina
    try:
        from . import dieta
        dieta.aktualizuj(dieta.polacz(), w["nowe_aktywnosci"])
    except Exception:
        log.exception("cel jedzenia")
    # 2) rano, gdy jest dzisiejszy sen
    dzis = baza.dzien(db, date.today().isoformat()) or {}
    if u["analiza_rano"] and dzis.get("sen_h") and teraz.strftime("%H:%M") >= u["analiza_godzina_min"] \
            and not analiza.zrobiona(db, "rano", date.today().isoformat()):
        try:
            a = analiza.analizuj("rano", db=db)
            if a and u.get("korekta_po_snie", True) and u.get("start_gotowy"):   # codziennie: plan pod dzisiejszy sen
                przeplanuj("korekta po ocenie snu", a.get("prosba_do_planu", "") if a.get("zmienic_plan") else
                           "Sprawdź najbliższe 2–3 dni pod dzisiejszy sen i regenerację; jeśli pasują — bez zmian.",
                           pytaj=True)
            elif a and a.get("zmienic_plan"):
                przeplanuj("analiza poranna", a.get("prosba_do_planu", ""), pytaj=True)
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
    if braki and u.get("start_gotowy"):
        try:
            przeplanuj(f"uzupełnienie planu ({len(braki)} dni bez treningu)")
        except Exception:
            log.exception("plan")
    # 5) zaległe zmiany planu (np. błąd sieci)
    if u["auto_zegarek"] and db.execute("SELECT 1 FROM plan WHERE stan IN ('nowy','do_usuniecia')").fetchone():
        zegarek.synchronizuj_plan(g, db)
