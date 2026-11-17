"""Powiadomienia: Web Push do webapki (iPhone: apka dodana do ekranu głównego) + Linphone/Telegram przez kolejkę bota.
Klucze VAPID generowane raz, w dane/vapid.json (600), poza gitem."""
import base64
import json
import logging
import time

from . import baza, config

log = logging.getLogger(__name__)


def _vapid():
    p = config.DANE / "vapid.json"
    if p.exists():
        return json.loads(p.read_text())
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    k = ec.generate_private_key(ec.SECP256R1())
    pem = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                          serialization.NoEncryption()).decode()
    pub = k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    d = {"prywatny_pem": pem, "publiczny": base64.urlsafe_b64encode(pub).decode().rstrip("=")}
    config.DANE.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d))
    p.chmod(0o600)
    return d


def klucz_publiczny():
    return _vapid()["publiczny"]


def adres(db=None):
    db = db or baza.polacz()
    return baza.kv(db, "adres_apki", "")


def push(tytul, tresc, url="/", db=None):
    db = db or baza.polacz()
    from pywebpush import WebPushException, webpush
    v = _vapid()
    sub = adres(db) or "https://raspberrypi.local"
    n = 0
    for r in db.execute("SELECT endpoint, dane FROM push").fetchall():
        try:
            webpush(json.loads(r[1]), json.dumps({"tytul": tytul, "tresc": tresc[:300], "url": url}, ensure_ascii=False),
                    vapid_private_key=v["prywatny_pem"], vapid_claims={"sub": sub}, ttl=86400)
            n += 1
        except WebPushException as ex:
            kod = getattr(ex.response, "status_code", 0)
            if kod in (404, 410):
                db.execute("DELETE FROM push WHERE endpoint=?", (r[0],))
                db.commit()
            log.warning("push %s: %s", kod, str(ex)[:150])
        except Exception as ex:
            log.warning("push: %s", ex)
    return n


def linphone(tekst):
    try:
        config.KOLEJKA_BOTA.mkdir(exist_ok=True)
        p = config.KOLEJKA_BOTA / f"trener-{time.time():.3f}.json"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"tekst": tekst, "od": "trener"}, ensure_ascii=False), encoding="utf-8")
        tmp.rename(p)
        return True
    except OSError as ex:
        log.warning("linphone: %s", ex)
        return False


def powiadom(tytul, tresc, url="/", db=None):
    """push (gdy włączony i jest subskrypcja) + Linphone (gdy włączony albo push nie doszedł do nikogo)"""
    u = config.ustawienia()
    db = db or baza.polacz()
    n = push(tytul, tresc, url, db) if u["push"] else 0
    if u["linphone"] or n == 0:
        link = adres(db)
        linphone(f"🏋️ {tytul}\n{tresc}" + (f"\n\nOmów w apce Trener: {link.rstrip('/')}{url}" if link else ""))
    return n
