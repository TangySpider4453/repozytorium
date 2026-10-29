"""
Wspólna pamięć rozmów z właścicielem (bot Telegram, wiadomości głosowe i telefon): ~/bot/pamiec.db (SQLite).
Każda wiadomość w obie strony jest zapisana, więc Claude wie, co bot napisał sam z siebie (alarmy, przypomnienia,
pytania), nawet gdy Antek odpisze po kilku godzinach albo gdy rozmowa z Claude zaczęła się od nowa.
  zapisz(kto, kanal, tekst, tg_id=None)      kto: "antek" | "bot" (powiadomienia) | "claude" (odpowiedzi Claude)
  kontekst(nowa_sesja)                        tekst dopisywany do wiadomości dla Claude
"""
import sqlite3
import threading
import time
from pathlib import Path

PLIK = Path(__file__).resolve().parent / "pamiec.db"
_LOCK = threading.Lock()


def _db():
    db = sqlite3.connect(PLIK, timeout=10)
    db.execute("""CREATE TABLE IF NOT EXISTS wiadomosci (id INTEGER PRIMARY KEY, czas REAL, kto TEXT, kanal TEXT,
                  tekst TEXT, tg_id INTEGER)""")
    return db


def zapisz(kto, kanal, tekst, tg_id=None):
    with _LOCK:
        db = _db()
        db.execute("INSERT INTO wiadomosci (czas, kto, kanal, tekst, tg_id) VALUES (?, ?, ?, ?, ?)",
                   (time.time(), kto, kanal, (tekst or "")[:4000], tg_id))
        db.execute("DELETE FROM wiadomosci WHERE czas < ?", (time.time() - 90 * 86400,))      # 90 dni
        db.commit()
        db.close()


def po_tg_id(tg_id):
    with _LOCK:
        db = _db()
        w = db.execute("SELECT czas, kto, tekst FROM wiadomosci WHERE tg_id = ? ORDER BY id DESC LIMIT 1", (tg_id,)).fetchone()
        db.close()
    return w


def _linia(czas, kto, kanal, tekst, limit=400):
    kto_t = {"antek": "Antek", "bot": "bot (sam z siebie)", "claude": "Ty (Claude)"}.get(kto, kto)
    kan = {"telefon": " przez telefon", "glosowka": " głosówką", "linphone": " na Linphone"}.get(kanal, "")
    t = " ".join((tekst or "").split())
    return f"{time.strftime('%d.%m %H:%M', time.localtime(czas))} {kto_t}{kan}: {t[:limit]}{'…' if len(t) > limit else ''}"


def kontekst(nowa_sesja, odpowiedz_na=None):
    """Na nowej sesji: ostatnie 30 wiadomości (pamięć między rozmowami). Zawsze: to, co bot wysłał sam z siebie od
    ostatniej wiadomości Antka (alarmy, przypomnienia, pytania), i wiadomość, na którą Antek właśnie odpowiada."""
    with _LOCK:
        db = _db()
        ost_antek = db.execute("SELECT MAX(id) FROM wiadomosci WHERE kto = 'antek'").fetchone()[0] or 0
        od_bota = db.execute("SELECT czas, kto, kanal, tekst FROM wiadomosci WHERE id > ? AND kto = 'bot' ORDER BY id",
                             (ost_antek,)).fetchall()
        historia = db.execute("SELECT czas, kto, kanal, tekst FROM wiadomosci ORDER BY id DESC LIMIT 30").fetchall()[::-1] \
            if nowa_sesja else []
        db.close()
    czesci = []
    if historia:
        czesci.append("Pamięć: ostatnie wiadomości z Antkiem (najstarsze pierwsze):\n" + "\n".join(_linia(*w) for w in historia))
    elif od_bota:
        czesci.append("Od ostatniej wiadomości Antka bot wysłał mu sam z siebie:\n" + "\n".join(_linia(*w) for w in od_bota[-15:]))
    if odpowiedz_na:
        czesci.append("Antek odpowiada na tę wiadomość: " + _linia(*odpowiedz_na[:2], "", odpowiedz_na[2], 800))
    return "\n\n".join(czesci)


def ostatnie_id():
    with _LOCK:
        db = _db()
        w = db.execute("SELECT MAX(id) FROM wiadomosci").fetchone()[0] or 0
        db.close()
    return w


def od_id(od, bez_ostatniej=True, limit=20):
    """wiadomości po danym id (np. wymienione z drugim modelem albo wysłane przez bota) jako tekst do kontekstu"""
    with _LOCK:
        db = _db()
        w = db.execute("SELECT id, czas, kto, kanal, tekst FROM wiadomosci WHERE id > ? ORDER BY id", (od,)).fetchall()
        db.close()
    if bez_ostatniej and w and w[-1][2] == "antek":
        w = w[:-1]
    w = w[-limit:]
    return "\n".join(_linia(*x[1:]) for x in w)
