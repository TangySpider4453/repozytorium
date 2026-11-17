"""Webapka Trener: Flask na 127.0.0.1:8095, na zewnątrz tylko przez `tailscale serve` (HTTPS w tailnecie).
Długie rzeczy (czat, plan, analiza, sync) idą w wątku jako zadanie; front odpytuje /api/zadanie/<id>."""
import json
import logging
import threading
import traceback
from datetime import date, timedelta

from flask import Flask, abort, jsonify, request, send_from_directory

from . import baza, budowa, config, kontekst, powiadom

log = logging.getLogger(__name__)
app = Flask(__name__, static_folder=None)


def db():
    return baza.polacz()


@app.after_request
def bez_cache(r):
    if request.path.startswith("/api/"):
        r.headers["Cache-Control"] = "no-store"
    return r


# ---------------------------------------------------------------- statyczne
@app.route("/")
def index():
    return send_from_directory(config.STATIC, "index.html")


@app.route("/sw.js")
def sw():
    r = send_from_directory(config.STATIC, "sw.js")
    r.headers["Service-Worker-Allowed"] = "/"
    r.headers["Cache-Control"] = "no-cache"
    return r


@app.route("/<path:p>")
def plik(p):
    if p.startswith("api/"):
        abort(404)
    return send_from_directory(config.STATIC, p)


# ---------------------------------------------------------------- zadania w tle
def zadanie(rodzaj, fn, *a, **kw):
    d = db()
    zid = d.execute("INSERT INTO zadania (rodzaj, stan, utworzono) VALUES (?, 'trwa', ?)", (rodzaj, baza.teraz())).lastrowid
    d.commit()

    def run():
        dd = db()
        try:
            w = fn(*a, **kw)
            dd.execute("UPDATE zadania SET stan='ok', wynik=?, zakonczono=? WHERE id=?",
                       (json.dumps(w, ensure_ascii=False, default=str)[:20000], baza.teraz(), zid))
        except Exception as ex:
            log.error("zadanie %s: %s", rodzaj, traceback.format_exc())
            dd.execute("UPDATE zadania SET stan='blad', wynik=?, zakonczono=? WHERE id=?",
                       (json.dumps(str(ex)[:500], ensure_ascii=False), baza.teraz(), zid))
        dd.commit()
    threading.Thread(target=run, daemon=True).start()
    return zid


@app.route("/api/zadanie/<int:zid>")
def api_zadanie(zid):
    r = db().execute("SELECT * FROM zadania WHERE id=?", (zid,)).fetchone()
    if not r:
        abort(404)
    return jsonify({"stan": r["stan"], "wynik": json.loads(r["wynik"]) if r["wynik"] else None})


@app.route("/api/akcja", methods=["POST"])
def api_akcja():
    b = request.get_json(silent=True) or {}
    r = b.get("rodzaj")
    if r == "sync":
        from .cykl import cykl
        return jsonify(zadanie("sync", lambda: cykl() or "ok"))
    if r == "plan":
        from .cykl import przeplanuj
        return jsonify(zadanie("plan", przeplanuj, "ręcznie z apki", b.get("prosba", "")))
    if r == "makrocykl":
        from .cel import zbuduj
        from .cykl import przeplanuj
        return jsonify(zadanie("makrocykl", lambda: (zbuduj(b.get("prosba", "")), przeplanuj("nowy makrocykl"))[0]))
    if r == "analiza":
        from .analiza import analizuj
        return jsonify(zadanie("analiza", analizuj, b.get("typ", "rano"), True))
    abort(400)


# ---------------------------------------------------------------- dane
def _plan(d, od, do):
    wyn = []
    for r in d.execute("SELECT * FROM plan WHERE dzien BETWEEN ? AND ? AND stan NOT IN ('usuniety','do_usuniecia') "
                       "ORDER BY dzien, id", (od, do)):
        t = dict(r)
        t["kroki"] = json.loads(t["kroki"] or "[]")
        t["min"] = budowa.czas_min(t) if t["sport"] != "odpoczynek" else 0
        wyn.append(t)
    return wyn


@app.route("/api/dzis")
def api_dzis():
    d = db()
    dzis = date.today()
    dni = baza.dni_zakres(d, (dzis - timedelta(days=29)).isoformat(), dzis.isoformat())
    ost = d.execute("SELECT id, rodzaj, dzien, utworzono, tytul, dane, przeczytano FROM analizy ORDER BY id DESC LIMIT 1").fetchone()
    zrobione = {r[0] for r in d.execute("SELECT DISTINCT dzien FROM aktywnosci WHERE dzien >= ?",
                                        ((dzis - timedelta(days=7)).isoformat(),))}
    return jsonify({
        "dzis": dzis.isoformat(), "dni": dni,
        "analiza": dict(ost, dane=json.loads(ost["dane"])) if ost else None,
        "plan": _plan(d, dzis.isoformat(), (dzis + timedelta(days=2)).isoformat()),
        "zrobione_dni": sorted(zrobione),
        "ostatni_sync": baza.kv(d, "ostatni_sync"), "historia": baza.kv(d, "historia_postep"),
        "ustawienia_puste": not config.ustawienia()["cele"]})


@app.route("/api/dni")
def api_dni():
    od = request.args.get("od") or (date.today() - timedelta(days=90)).isoformat()
    do = request.args.get("do") or date.today().isoformat()
    return jsonify(baza.dni_zakres(db(), od, do))


@app.route("/api/agregaty")
def api_agregaty():
    """per tydzień/miesiąc dla wykresów: godziny per sport, obciążenie, sen, HRV, RHR"""
    okres = request.args.get("okres", "tydzien")
    d = db()
    from collections import defaultdict
    from statistics import mean
    klucz = (lambda x: (x - timedelta(days=x.weekday())).isoformat()) if okres == "tydzien" else (lambda x: x.isoformat()[:7])
    g = defaultdict(lambda: {"h": defaultdict(float), "km": defaultdict(float), "obc": 0.0, "sen": [], "hrv": [], "rhr": [],
                             "vo2": []})
    for r in d.execute("SELECT dzien, typ, dane FROM aktywnosci"):
        j = baza.rozpakuj(r[2]) or {}
        x = g[klucz(date.fromisoformat(r[0]))]
        k = kontekst.kategoria(r[1])
        x["h"][k] += (j.get("duration") or 0) / 3600
        x["km"][k] += (j.get("distance") or 0) / 1000
        x["obc"] += j.get("activityTrainingLoad") or 0
    for r in d.execute("SELECT dzien, dane FROM dni"):
        w = json.loads(r[1])
        x = g[klucz(date.fromisoformat(r[0]))]
        for a, b in (("sen", "sen_h"), ("hrv", "hrv"), ("rhr", "tetno_spocz"), ("vo2", "vo2_rower")):
            if w.get(b):
                x[a].append(w[b])
    sr = lambda xs: round(mean(xs), 1) if xs else None   # noqa: E731
    return jsonify([{"okres": k, "h": {s: round(v, 1) for s, v in x["h"].items()}, "km": {s: round(v) for s, v in x["km"].items()},
                     "obc": round(x["obc"]), "sen": sr(x["sen"]), "hrv": sr(x["hrv"]), "rhr": sr(x["rhr"]), "vo2": sr(x["vo2"])}
                    for k, x in sorted(g.items())])


@app.route("/api/aktywnosci")
def api_aktywnosci():
    d = db()
    lim = min(int(request.args.get("limit", 50)), 500)
    off = int(request.args.get("offset", 0))
    typ = request.args.get("sport")
    rows = d.execute("SELECT typ, dane FROM aktywnosci ORDER BY start DESC LIMIT ? OFFSET ?", (lim * 4 if typ else lim, off)).fetchall()
    w = [kontekst.dane.streszczenie_aktywnosci(baza.rozpakuj(r[1]) or {}) for r in rows
         if not typ or kontekst.kategoria(r[0]) == typ]
    return jsonify(w[:lim])


@app.route("/api/aktywnosc/<int:aid>")
def api_aktywnosc(aid):
    r = db().execute("SELECT * FROM aktywnosci WHERE id=?", (aid,)).fetchone()
    if not r:
        abort(404)
    s = kontekst.dane.streszczenie_aktywnosci(baza.rozpakuj(r["dane"]) or {})
    if r["szczegoly"]:
        s["cwiczenia"] = kontekst.cwiczenia_silki(baza.rozpakuj(r["szczegoly"]))
    return jsonify(s)


@app.route("/api/plan")
def api_plan():
    dzis = date.today()
    od = request.args.get("od") or (dzis - timedelta(days=7)).isoformat()
    do = request.args.get("do") or (dzis + timedelta(days=14)).isoformat()
    d = db()
    zrobione = {}
    for r in d.execute("SELECT dzien, typ, nazwa, dane FROM aktywnosci WHERE dzien BETWEEN ? AND ?", (od, do)):
        zrobione.setdefault(r[0], []).append(kontekst.dane.streszczenie_aktywnosci(baza.rozpakuj(r[3]) or {}))
    return jsonify({"plan": _plan(d, od, do), "zrobione": zrobione, "dzis": dzis.isoformat()})


@app.route("/api/makrocykl")
def api_makrocykl():
    from . import cel
    d = db()
    m = cel.makrocykl(d)
    f = cel.faza_teraz(m) if m else None
    return jsonify({"makrocykl": m, "faza": f, "plan_uzasadnienie": baza.kv(d, "plan_uzasadnienie"),
                    "progi": cel.progi(d)})


@app.route("/api/analizy")
def api_analizy():
    d = db()
    if request.args.get("id"):
        r = d.execute("SELECT * FROM analizy WHERE id=?", (request.args["id"],)).fetchone()
        return jsonify(dict(r, dane=json.loads(r["dane"])) if r else None)
    return jsonify([dict(r, dane=json.loads(r["dane"])) for r in
                    d.execute("SELECT * FROM analizy ORDER BY id DESC LIMIT ?", (int(request.args.get("limit", 30)),))])


@app.route("/api/analizy/<int:aid>/przeczytane", methods=["POST"])
def api_przeczytane(aid):
    d = db()
    d.execute("UPDATE analizy SET przeczytano=? WHERE id=? AND przeczytano IS NULL", (baza.teraz(), aid))
    d.commit()
    return jsonify(True)


# ---------------------------------------------------------------- czat
@app.route("/api/czat", methods=["GET", "POST"])
def api_czat():
    if request.method == "GET":
        rows = db().execute("SELECT * FROM czat ORDER BY id DESC LIMIT 100").fetchall()[::-1]
        return jsonify([dict(r, akcje=json.loads(r["akcje"]) if r["akcje"] else []) for r in rows])
    b = request.get_json(silent=True) or {}
    t = (b.get("tresc") or "").strip()
    if not t or len(t) > 4000:
        abort(400)
    from .czat import odpowiedz
    return jsonify(zadanie("czat", odpowiedz, t, b.get("analiza_id")))


# ---------------------------------------------------------------- ustawienia, push
@app.route("/api/ustawienia", methods=["GET", "POST"])
def api_ustawienia():
    if request.method == "POST":
        u = config.zapisz_ustawienia(request.get_json(silent=True) or {})
        d = db()
        baza.ustaw_kv(d, "pamiec_trenera", (request.get_json(silent=True) or {}).get("pamiec", baza.kv(d, "pamiec_trenera", [])))
        return jsonify(u)
    return jsonify(dict(config.ustawienia(), pamiec=baza.kv(db(), "pamiec_trenera", [])))


@app.route("/api/push/klucz")
def api_push_klucz():
    return jsonify(powiadom.klucz_publiczny())


@app.route("/api/push/subskrybuj", methods=["POST"])
def api_push_sub():
    s = request.get_json(silent=True) or {}
    if not s.get("endpoint", "").startswith("https://"):
        abort(400)
    d = db()
    d.execute("INSERT OR REPLACE INTO push VALUES (?,?,?)", (s["endpoint"], json.dumps(s), baza.teraz()))
    d.commit()
    return jsonify(True)


@app.route("/api/push/test", methods=["POST"])
def api_push_test():
    return jsonify(powiadom.push("🏋️ Trener", "Powiadomienia działają.", "/"))
