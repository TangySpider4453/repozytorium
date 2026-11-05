"""Klient Garmin Connect (biblioteka garminconnect 0.3.x, własne logowanie mobilne z MFA; garth jest porzucony).
Token: tokens/garmin_tokens.json (katalog 700, plik 600), poza gitem. Ponowienia z wykładniczym odstępem przy 429/5xx."""
import logging
import time
from pathlib import Path

from garminconnect import Garmin

log = logging.getLogger(__name__)
KAT = Path(__file__).resolve().parent.parent
TOKENY = KAT / "tokens"


class BrakLogowania(Exception):
    """token wygasł albo go nie ma: trzeba uruchomić `./rtg.sh login`"""


def polacz():
    if not (TOKENY / "garmin_tokens.json").exists():
        raise BrakLogowania("brak tokenu: uruchom ./rtg.sh login")
    g = Garmin()
    try:
        g.login(str(TOKENY))
    except Exception as ex:                       # biblioteka rzuca różne wyjątki przy złym tokenie
        raise BrakLogowania(f"token nie działa ({type(ex).__name__}): uruchom ./rtg.sh login") from ex
    return g


def zaloguj_interaktywnie():
    """tylko w terminalu z Antkiem: hasło przez getpass (nie trafia do plików ani historii), kod MFA z input()"""
    from getpass import getpass
    TOKENY.mkdir(mode=0o700, exist_ok=True)
    TOKENY.chmod(0o700)
    email = input("E-mail Garmin Connect: ").strip()
    g = Garmin(email, getpass("Hasło Garmin Connect (nie jest zapisywane): "), prompt_mfa=lambda: input("Kod MFA: ").strip())
    g.login(str(TOKENY))
    for p in TOKENY.iterdir():
        p.chmod(0o600)
    return g


def api(g, metoda, sciezka, **kw):
    """surowe zapytanie do connectapi z ponowieniami (429/5xx: 2, 4, 8, 16 s)"""
    for proba in range(5):
        try:
            if metoda == "GET":
                return g.client.connectapi(sciezka, **kw)
            # zapisy: transport biblioteki (POST/PUT/DELETE z nagłówkami sesji), api=True = odpowiedź jako JSON
            return {"POST": g.client.post, "PUT": g.client.put, "DELETE": g.client.delete}[metoda]("connectapi", sciezka, api=True, **kw)
        except Exception as ex:
            kod = getattr(getattr(ex, "response", None), "status_code", None) or 0
            tekst = str(ex)
            if (kod == 429 or kod >= 500 or "429" in tekst or "Too Many" in tekst) and proba < 4:
                czekaj = 2 ** (proba + 1)
                log.warning("Garmin %s %s: %s, ponawiam za %d s", metoda, sciezka, kod or tekst[:60], czekaj)
                time.sleep(czekaj)
                continue
            raise
