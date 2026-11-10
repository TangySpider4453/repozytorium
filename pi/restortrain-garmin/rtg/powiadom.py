"""Powiadomienia przez bota serwerka (Linphone, a gdy nie działa: Telegram): plik JSON w ~/bot/powiadomienia/,
który bot odbiera co kilka sekund. Bez tokenów i haseł w treści."""
import json
import time
from pathlib import Path

KOLEJKA = Path("/home/tonyg/bot/powiadomienia")


def powiadom(tekst):
    try:
        KOLEJKA.mkdir(exist_ok=True)
        p = KOLEJKA / f"rtg-{time.time():.3f}.json"
        p.with_suffix(".tmp").write_text(json.dumps({"tekst": tekst, "od": "restortrain-garmin"}, ensure_ascii=False), encoding="utf-8")
        p.with_suffix(".tmp").rename(p)
    except OSError:
        pass
