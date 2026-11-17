"""Połączenie z Garmin Connect (nieoficjalne API, biblioteka garminconnect). Token wspólny z restortrain-garmin;
logowanie z tokenu pod blokadą pliku, żeby dwa procesy naraz nie odświeżały tokenu. Ponowienia przy 429/5xx."""
import fcntl
import logging
import time
from contextlib import contextmanager

from . import config

log = logging.getLogger(__name__)


class BrakLogowania(Exception):
    pass


@contextmanager
def _blokada():
    config.DANE.mkdir(parents=True, exist_ok=True)
    with open(config.BLOKADA_GARMIN, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def polacz():
    from garminconnect import Garmin
    if not (config.TOKENY / "garmin_tokens.json").exists():
        raise BrakLogowania("brak tokenu Garmina (zaloguj w restortrain-garmin: ./rtg.sh login)")
    g = Garmin()
    with _blokada():
        try:
            g.login(str(config.TOKENY))
        except Exception as ex:
            raise BrakLogowania(f"token Garmina nie działa ({type(ex).__name__})") from ex
    return g


def wywolaj(fn, *a, pauza=0.4, **kw):
    """wywołanie metody biblioteki z ponowieniami (429/5xx: 2, 4, 8, 16, 32 s); 404 → None"""
    for proba in range(6):
        try:
            w = fn(*a, **kw)
            time.sleep(pauza)
            return w
        except Exception as ex:
            kod = getattr(getattr(ex, "response", None), "status_code", None) or 0
            t = str(ex)
            if kod == 404 or "404" in t[:200]:
                return None
            if (kod == 429 or kod >= 500 or "429" in t or "Too Many" in t) and proba < 5:
                czekaj = 2 ** (proba + 1)
                log.warning("Garmin %s: %s, ponawiam za %d s", getattr(fn, "__name__", fn), kod or t[:80], czekaj)
                time.sleep(czekaj)
                continue
            raise


def api(g, metoda, sciezka, **kw):
    """surowe zapytanie do connectapi (jak w restortrain-garmin)"""
    if metoda == "GET":
        return wywolaj(g.client.connectapi, sciezka, **kw)
    f = {"POST": g.client.post, "PUT": g.client.put, "DELETE": g.client.delete}[metoda]
    return wywolaj(f, "connectapi", sciezka, api=True, **kw)
