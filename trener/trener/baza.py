"""SQLite: surowe odpowiedzi Garmina (skompresowane), aktywności, dni (wyliczone), analizy, plan, czat, push."""
import json
import sqlite3
import zlib
from datetime import datetime

from . import config

SCHEMAT = """
CREATE TABLE IF NOT EXISTS surowe (typ TEXT, dzien TEXT, dane BLOB, pobrano TEXT, PRIMARY KEY (typ, dzien));
CREATE TABLE IF NOT EXISTS aktywnosci (id INTEGER PRIMARY KEY, start TEXT, dzien TEXT, typ TEXT, nazwa TEXT,
    dane BLOB, szczegoly BLOB, pobrano TEXT);
CREATE INDEX IF NOT EXISTS akt_dzien ON aktywnosci (dzien);
CREATE TABLE IF NOT EXISTS dni (dzien TEXT PRIMARY KEY, dane TEXT);
CREATE TABLE IF NOT EXISTS analizy (id INTEGER PRIMARY KEY AUTOINCREMENT, rodzaj TEXT, dzien TEXT, utworzono TEXT,
    tytul TEXT, tresc TEXT, dane TEXT, przeczytano TEXT);
CREATE TABLE IF NOT EXISTS plan (id INTEGER PRIMARY KEY AUTOINCREMENT, dzien TEXT, sport TEXT, tytul TEXT,
    opis TEXT, kroki TEXT, hash TEXT, workout_id INTEGER, kalendarz_id INTEGER, stan TEXT, utworzono TEXT,
    zmieniono TEXT, zrodlo TEXT);
CREATE INDEX IF NOT EXISTS plan_dzien ON plan (dzien);
CREATE TABLE IF NOT EXISTS czat (id INTEGER PRIMARY KEY AUTOINCREMENT, kto TEXT, tresc TEXT, czas TEXT,
    analiza_id INTEGER, akcje TEXT);
CREATE TABLE IF NOT EXISTS push (endpoint TEXT PRIMARY KEY, dane TEXT, dodano TEXT);
CREATE TABLE IF NOT EXISTS kv (klucz TEXT PRIMARY KEY, wartosc TEXT);
CREATE TABLE IF NOT EXISTS zadania (id INTEGER PRIMARY KEY AUTOINCREMENT, rodzaj TEXT, stan TEXT, wynik TEXT,
    utworzono TEXT, zakonczono TEXT);
"""


def teraz():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def polacz():
    config.DANE.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(config.BAZA, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMAT)
    return db


def pakuj(obj):
    return zlib.compress(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode(), 6)


def rozpakuj(b):
    return None if b is None else json.loads(zlib.decompress(b))


def zapisz_surowe(db, typ, dzien, obj):
    db.execute("INSERT OR REPLACE INTO surowe VALUES (?,?,?,?)", (typ, dzien, pakuj(obj), teraz()))


def surowe(db, typ, dzien):
    r = db.execute("SELECT dane FROM surowe WHERE typ=? AND dzien=?", (typ, dzien)).fetchone()
    return rozpakuj(r[0]) if r else None


def kv(db, klucz, domyslna=None):
    r = db.execute("SELECT wartosc FROM kv WHERE klucz=?", (klucz,)).fetchone()
    return json.loads(r[0]) if r else domyslna


def ustaw_kv(db, klucz, wartosc):
    db.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (klucz, json.dumps(wartosc, ensure_ascii=False)))
    db.commit()


def dzien(db, d):
    r = db.execute("SELECT dane FROM dni WHERE dzien=?", (d,)).fetchone()
    return json.loads(r[0]) if r else None


def dni_zakres(db, od, do):
    return [dict(json.loads(r[1]), dzien=r[0]) for r in
            db.execute("SELECT dzien, dane FROM dni WHERE dzien BETWEEN ? AND ? ORDER BY dzien", (od, do))]
