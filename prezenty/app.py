"""Prezenty: webapka z cyfrowymi prezentami (na start kalendarz adwentowy).
Flask na 127.0.0.1:8097, z internetu przez Tailscale Funnel :10000. Wejście tylko z kluczem (link ?k=…, potem
ciasteczko; klucz jest też w start_url manifestu, bo apka z ekranu głównego iOS ma osobne ciasteczka niż Safari).
Sekrety (klucze, VAPID) i treść prezentów tylko na Pi w dane/ (poza gitem)."""
import base64
import datetime as dt
import hmac
import json
import logging
import os
import secrets
import threading
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, abort, jsonify, make_response, redirect, request, send_from_directory

KATALOG = Path(__file__).resolve().parent
STATIC = KATALOG / "static"
DANE = Path(os.environ.get("PREZENTY_DANE", KATALOG / "dane"))
PLIKI = DANE / "pliki"
STREFA = ZoneInfo("Europe/Warsaw")
PORT = int(os.environ.get("PREZENTY_PORT", "8097"))
ROK_S = 400 * 86400
OBRAZY = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".mp4", ".mov", ".m4a", ".mp3"}

log = logging.getLogger("prezenty")
app = Flask(__name__, static_folder=None)
from werkzeug.middleware.proxy_fix import ProxyFix   # noqa: E402  (tailscale serve: prawdziwy host i https)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024
BLOKADA = threading.RLock()


# ---------------------------------------------------------------- pliki danych
def czytaj(nazwa, domyslne):
    p = DANE / nazwa
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return domyslne() if callable(domyslne) else domyslne


def zapisz(nazwa, d, prywatny=False):
    DANE.mkdir(parents=True, exist_ok=True)
    p = DANE / nazwa
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    if prywatny:
        tmp.chmod(0o600)
    tmp.replace(p)


def _nowe_klucze():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    k = ec.generate_private_key(ec.SECP256R1())
    pem = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                          serialization.NoEncryption()).decode()
    pub = k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    d = {"klucz": secrets.token_urlsafe(9), "admin": secrets.token_urlsafe(12),
         "vapid_pem": pem, "vapid_pub": base64.urlsafe_b64encode(pub).decode().rstrip("=")}
    zapisz("klucze.json", d, prywatny=True)
    return d


def klucze():
    with BLOKADA:
        return czytaj("klucze.json", _nowe_klucze)


def domyslne_prezenty():
    emoji = "🎁 ☕ 🍫 🎶 📸 🧣 🍪 💌 🌟 🕯️ 🎬 🧸 🍊 ❄️ 🎨 📚 🫖 💫 🌲 🍷 🧦 🎀 🔔 ❤️".split()
    return {
        "tytul": "Dla Ciebie",
        "imie": "",
        "adwent": {
            "rok": dt.date.today().year if dt.date.today().month >= 6 else dt.date.today().year - 1,
            "godzina_push": "08:00",
            "dni": {str(n): {"emoji": emoji[n - 1], "tytul": f"Niespodzianka nr {n}",
                             "tekst": f"Tu będzie prezent na {n} grudnia.", "link": "", "plik": "",
                             "zapowiedz": ""} for n in range(1, 25)},
        },
    }


def prezenty():
    return czytaj("prezenty.json", domyslne_prezenty)


def stan():
    return czytaj("stan.json", lambda: {"otwarte": {}, "powiadomione": {}, "push": {}})


# ---------------------------------------------------------------- dostęp
def _rowne(a, b):
    return bool(a) and bool(b) and hmac.compare_digest(str(a), str(b))


def jest_admin():
    return _rowne(request.cookies.get("prezenty_admin"), klucze()["admin"])


def ma_dostep():
    return jest_admin() or _rowne(request.cookies.get("prezenty_klucz"), klucze()["klucz"])


def _ciastko(r, nazwa, wartosc):
    r.set_cookie(nazwa, wartosc, max_age=ROK_S, httponly=True, secure=request.is_secure or
                 request.headers.get("X-Forwarded-Proto") == "https", samesite="Lax")
    return r


@app.before_request
def wejscie_z_kluczem():
    """?k=… (link / start_url) albo ?a=… (admin): ciasteczko i przekierowanie na czysty adres"""
    k, a = request.args.get("k"), request.args.get("a")
    if not (k or a) or request.method != "GET":
        return None
    kl = klucze()
    args = {x: y for x, y in request.args.items() if x not in ("k", "a")}
    cel = request.path + ("?" + "&".join(f"{x}={y}" for x, y in args.items()) if args else "")
    r = make_response(redirect(cel))
    if _rowne(k, kl["klucz"]):
        _ciastko(r, "prezenty_klucz", kl["klucz"])
    elif _rowne(a, kl["admin"]):
        _ciastko(r, "prezenty_admin", kl["admin"])
        _ciastko(r, "prezenty_klucz", kl["klucz"])
    else:
        time.sleep(1)
    return r


def wymagaj():
    if not ma_dostep():
        abort(401)


# ---------------------------------------------------------------- kalendarz
def teraz():
    return dt.datetime.now(STREFA)


def kafelki(dzis=None, admin=False):
    p, s = prezenty(), stan()
    a = p["adwent"]
    rok = int(a["rok"])
    dzis = dzis or teraz().date()
    wynik = []
    for nr in range(1, 25):
        d = dt.date(rok, 12, nr)
        tresc = a["dni"].get(str(nr), {})
        status = "dzis" if d == dzis else ("wkrotce" if d > dzis else "minione")
        k = {"nr": nr, "data": d.isoformat(), "status": status, "otwarte": str(nr) in s["otwarte"],
             "za_dni": (d - dzis).days}
        if status != "wkrotce" or admin:
            k.update(emoji=tresc.get("emoji", "🎁"), tytul=tresc.get("tytul", ""))
        wynik.append(k)
    kol = {"dzis": 0, "wkrotce": 1, "minione": 2}
    # najbardziej aktualne u góry po lewej: dziś → przyszłe po kolei → minione (najświeższe najpierw)
    wynik.sort(key=lambda k: (kol[k["status"]], k["nr"] if k["status"] != "minione" else -k["nr"]))
    return wynik


def nieotwarte(dzis=None):
    return sum(1 for k in kafelki(dzis) if k["status"] != "wkrotce" and not k["otwarte"])


def _dzien_symulowany():
    """admin może podejrzeć apkę „jakby był” inny dzień: ?dzien=2026-12-05"""
    if jest_admin() and request.args.get("dzien"):
        try:
            return dt.date.fromisoformat(request.args["dzien"])
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------- strony
@app.get("/")
def strona():
    return send_from_directory(STATIC, "index.html", max_age=0)


@app.get("/admin")
def admin_strona():
    if not jest_admin():
        abort(404)
    return send_from_directory(STATIC, "admin.html", max_age=0)


@app.get("/sw.js")
def sw():
    r = send_from_directory(STATIC, "sw.js", max_age=0)
    r.headers["Service-Worker-Allowed"] = "/"
    return r


@app.get("/manifest.webmanifest")
def manifest():
    p = prezenty()
    kl = klucze()
    start = f"/?a={kl['admin']}" if jest_admin() else (f"/?k={kl['klucz']}" if ma_dostep() else "/")
    m = {"name": p.get("tytul") or "Dla Ciebie", "short_name": p.get("tytul") or "Dla Ciebie",
         "start_url": start, "scope": "/", "display": "standalone", "background_color": "#140c22",
         "theme_color": "#140c22", "lang": "pl",
         "icons": [{"src": "/static/ikona-192.png", "sizes": "192x192", "type": "image/png"},
                   {"src": "/static/ikona-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]}
    r = jsonify(m)
    r.headers["Content-Type"] = "application/manifest+json"
    r.headers["Cache-Control"] = "no-store"
    return r


@app.get("/static/<path:f>")
def statyczne(f):
    return send_from_directory(STATIC, f, max_age=300)


@app.get("/pliki/<path:f>")
def pliki(f):
    wymagaj()
    return send_from_directory(PLIKI, f, max_age=86400)


# ---------------------------------------------------------------- API
@app.get("/api/stan")
def api_stan():
    if not ma_dostep():
        return jsonify({"dostep": False}), 401
    dzis = _dzien_symulowany()
    p = prezenty()
    rok = int(p["adwent"]["rok"])
    t = teraz()
    start = dt.datetime(rok, 12, 1, tzinfo=STREFA)
    return jsonify({
        "dostep": True, "admin": jest_admin(), "tytul": p.get("tytul"), "imie": p.get("imie", ""),
        "teraz": t.isoformat(), "dzis": (dzis or t.date()).isoformat(), "symulacja": bool(dzis),
        "adwent": {"rok": rok, "start": start.isoformat(), "kafelki": kafelki(dzis),
                   "otwartych": sum(1 for k in kafelki(dzis) if k["otwarte"]), "nieotwarte": nieotwarte(dzis)},
        "vapid": klucze()["vapid_pub"],
    })


@app.get("/api/dzien/<int:nr>")
def api_dzien(nr):
    wymagaj()
    if not 1 <= nr <= 24:
        abort(404)
    dzis = _dzien_symulowany() or teraz().date()
    a = prezenty()["adwent"]
    if dt.date(int(a["rok"]), 12, nr) > dzis and not jest_admin():
        return jsonify({"zamkniete": True}), 403
    t = dict(a["dni"].get(str(nr), {}))
    t["nr"] = nr
    if not jest_admin():
        with BLOKADA:
            s = stan()
            if str(nr) not in s["otwarte"]:
                s["otwarte"][str(nr)] = teraz().isoformat(timespec="seconds")
                zapisz("stan.json", s)
    t["nieotwarte"] = nieotwarte(dzis)
    return jsonify(t)


@app.post("/api/push")
def api_push():
    wymagaj()
    sub = request.get_json(force=True)
    if not isinstance(sub, dict) or not str(sub.get("endpoint", "")).startswith("https://"):
        abort(400)
    with BLOKADA:
        s = stan()
        s["push"][sub["endpoint"]] = {"sub": sub, "od": teraz().isoformat(timespec="seconds"),
                                      "admin": jest_admin(), "adres": request.host_url}
        zapisz("stan.json", s, prywatny=True)
    return jsonify({"ok": True})


# ---------------------------------------------------------------- admin
@app.get("/api/admin/dane")
def admin_dane():
    if not jest_admin():
        abort(404)
    s = stan()
    return jsonify({"prezenty": prezenty(), "otwarte": s["otwarte"], "powiadomione": s["powiadomione"],
                    "push": [{"od": v["od"], "admin": v.get("admin", False)} for v in s["push"].values()],
                    "link": request.host_url.rstrip("/") + "/?k=" + klucze()["klucz"],
                    "pliki": sorted(x.name for x in PLIKI.iterdir()) if PLIKI.exists() else []})


@app.post("/api/admin/dane")
def admin_zapisz():
    if not jest_admin():
        abort(404)
    d = request.get_json(force=True)
    if not isinstance(d, dict) or "adwent" not in d or len(d["adwent"].get("dni", {})) != 24:
        abort(400)
    with BLOKADA:
        zapisz("prezenty.json", d)
    return jsonify({"ok": True})


@app.post("/api/admin/plik")
def admin_plik():
    if not jest_admin():
        abort(404)
    f = request.files.get("plik")
    if not f or not f.filename:
        abort(400)
    roz = Path(f.filename).suffix.lower()
    if roz not in OBRAZY:
        return jsonify({"blad": "nieobsługiwany typ pliku"}), 400
    PLIKI.mkdir(parents=True, exist_ok=True)
    nazwa = f"{int(time.time())}-{secrets.token_hex(3)}{roz}"
    f.save(PLIKI / nazwa)
    return jsonify({"plik": nazwa})


@app.post("/api/admin/test")
def admin_test():
    if not jest_admin():
        abort(404)
    d = request.get_json(force=True) or {}
    n = wyslij(d.get("tytul") or "Test 🎁", d.get("tresc") or "Powiadomienia działają.",
               tylko_admin=bool(d.get("tylko_ja", True)))
    return jsonify({"wyslane": n})


@app.post("/api/admin/reset")
def admin_reset():
    """wyczyść „otwarte” (np. po testach przed 1 grudnia)"""
    if not jest_admin():
        abort(404)
    with BLOKADA:
        s = stan()
        s["otwarte"], s["powiadomione"] = {}, {}
        zapisz("stan.json", s, prywatny=True)
    return jsonify({"ok": True})


# ---------------------------------------------------------------- powiadomienia
def wyslij(tytul, tresc, url="/#adwent", tylko_admin=False):
    from py_vapid import Vapid
    from pywebpush import WebPushException, webpush
    kl = klucze()
    v = Vapid.from_pem(kl["vapid_pem"].encode())
    plak = nieotwarte()
    n = 0
    with BLOKADA:
        s = stan()
    for ep, w in list(s["push"].items()):
        if tylko_admin and not w.get("admin"):
            continue
        dane = {"tytul": tytul, "tresc": tresc, "url": url, "plakietka": max(plak, 1)}
        try:
            webpush(w["sub"], json.dumps(dane, ensure_ascii=False), vapid_private_key=v,
                    vapid_claims={"sub": (w.get("adres") or "https://localhost/").rstrip("/")}, ttl=86400)
            n += 1
        except WebPushException as ex:
            kod = getattr(ex.response, "status_code", 0)
            log.warning("push %s: %s", kod, str(ex)[:150])
            if kod in (404, 410):
                with BLOKADA:
                    s2 = stan()
                    s2["push"].pop(ep, None)
                    zapisz("stan.json", s2, prywatny=True)
        except Exception as ex:
            log.warning("push: %s", ex)
    return n


def harmonogram():
    """co pół minuty: dzisiejsze okienko otwarte i minęła godzina_push → jedno powiadomienie na dzień"""
    while True:
        try:
            t = teraz()
            a = prezenty()["adwent"]
            if t.month == 12 and t.year == int(a["rok"]) and t.day <= 24:
                gh, gm = (int(x) for x in a.get("godzina_push", "08:00").split(":"))
                if (t.hour, t.minute) >= (gh, gm) and str(t.day) not in stan()["powiadomione"]:
                    d = a["dni"].get(str(t.day), {})
                    tytul = f"Okienko nr {t.day} jest otwarte {d.get('emoji', '🎁')}"
                    tresc = d.get("zapowiedz") or "Zajrzyj, co dziś na Ciebie czeka 💝"
                    n = wyslij(tytul, tresc)
                    with BLOKADA:
                        s = stan()
                        s["powiadomione"][str(t.day)] = t.isoformat(timespec="seconds")
                        zapisz("stan.json", s, prywatny=True)
                    log.info("dzień %s: push do %s urządzeń", t.day, n)
        except Exception:
            log.exception("harmonogram")
        time.sleep(30)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    klucze()
    if not (DANE / "prezenty.json").exists():
        zapisz("prezenty.json", domyslne_prezenty())
    threading.Thread(target=harmonogram, daemon=True).start()
    try:
        from waitress import serve
        serve(app, host="127.0.0.1", port=PORT, threads=8)
    except ImportError:
        app.run(host="127.0.0.1", port=PORT, threaded=True)


if __name__ == "__main__":
    main()
