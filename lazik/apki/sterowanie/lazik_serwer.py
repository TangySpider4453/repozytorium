#!/usr/bin/env python3
"""Łazik: sterowanie. Usługa startująca z Pi 5 (lazik-sterowanie.service): strona WWW na porcie 8000 z podglądem
kamery, wyborem trybu jazdy i zaznaczaniem obiektu do śledzenia (dotknięcie na podglądzie).

Bezpieczeństwo: po starcie łazik stoi; tryb inny niż „stop” wymaga otwartej strony (puls co 1 s); brak pulsu przez
`stop_bez_strony_s` = STOP. Strona tylko z kodem dostępu (QR/link), bo steruje silnikami.
Hailo: po `zwolnij_hailo_po_s` bez strony i w trybie stop proces się kończy (systemd uruchamia go od nowa), żeby zwolnić
Hailo i kamerę dla „Łazik: wizja” / „analiza wideo” (zwalnianie Hailo w trakcie pracy jest w HailoRT 4.23 zawodne).
"""

import json
import os
import secrets
import sys
import threading
import time

import cv2
from flask import Flask, Response, jsonify, request, send_from_directory

KATALOG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KATALOG)
from naped import Naped  # noqa: E402
from percepcja import Percepcja, P  # noqa: E402
from tryby import DO_SLEDZENIA, TRYBY, Sterownik  # noqa: E402
from wizja import KLASY, ZDJECIA, System  # noqa: E402

PLIK_KONF = os.path.join(KATALOG, "konfiguracja.json")
PLIK_KODU = os.path.join(KATALOG, "kod_dostepu.txt")
KONF = json.load(open(PLIK_KONF, encoding="utf-8"))


def kod_dostepu():
    if not os.path.exists(PLIK_KODU):
        with open(PLIK_KODU, "w") as f:
            f.write(secrets.token_urlsafe(8))
        os.chmod(PLIK_KODU, 0o600)
    return open(PLIK_KODU).read().strip()


naped = Naped(KONF)
percepcja = Percepcja()
sterownik = Sterownik(naped, percepcja, KONF)
system = System()
puls = {"czas": time.monotonic()}  # ostatni puls ze strony (start usługi liczy się jak puls)
analiza = {"watek": None}
app = Flask(__name__)
app.json.sort_keys = False  # kolejność trybów i klas jak w kodzie


@app.before_request
def dostep():
    kod = kod_dostepu()
    if request.args.get("t") != kod and request.cookies.get("lazik_ster") != kod:
        return Response("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                        "<body style='font:18px system-ui;background:#0d1114;color:#e6ebee;padding:24px'>"
                        "<h2>Łazik: sterowanie</h2><p>Otwórz link z kodem (ikona na pulpicie Pi 5 albo link od Claude).</p>",
                        status=403, mimetype="text/html")


@app.after_request
def ciasteczko(resp):
    if request.args.get("t") == kod_dostepu():
        resp.set_cookie("lazik_ster", kod_dostepu(), max_age=365 * 24 * 3600, samesite="Lax")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/")
def strona():
    return send_from_directory(KATALOG, "strona.html")


@app.get("/strumien.mjpg")
def strumien():
    def generuj():
        ostatni = -1
        while True:
            percepcja.potrzebna()
            klatka, nr, _, _ = percepcja.najnowsze()
            if klatka is None or nr == ostatni:
                time.sleep(0.03)
                continue
            ostatni = nr
            ok, jpg = cv2.imencode(".jpg", klatka, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok:
                yield b"--klatka\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n"
    return Response(generuj(), mimetype="multipart/x-mixed-replace; boundary=klatka")


@app.get("/api/stan")
def stan():
    percepcja.potrzebna()
    _, _, obiekty, sektory = percepcja.najnowsze()
    a = analiza["watek"]
    st_an = None
    if a is not None:
        s = a.odczyt()
        st_an = dict(etap=s["etap"], gotowe=s["gotowe"], razem=s["razem"], punkty=s["punkty"],
                     skan=os.path.relpath(s["wynik"], P.SKANY) if s.get("wynik") else None, werdykt=s.get("werdykt"),
                     blad=s.get("blad"))
    zdjecia = sorted((f for f in os.listdir(ZDJECIA) if f.endswith(".jpg")), reverse=True)[:8] if os.path.isdir(ZDJECIA) else []
    return jsonify(
        tryb=sterownik.tryb, opis=sterownik.opis, tryby=TRYBY,
        obiekty=[dict(id=o["id"], klasa=o["klasa"], nazwa=o["nazwa"], pew=round(o["pew"], 2),
                      ramka=[round(v, 4) for v in o["ramka"]]) for o in obiekty],
        sektory=sektory, cel_id=sterownik.cel_id, cel_klasa=sterownik.cel_klasa,
        do_sledzenia=DO_SLEDZENIA, naped=[round(naped.lewy, 2), round(naped.prawy, 2)], blad_napedu=naped.blad,
        blad_wizji=percepcja.blad, kamera=percepcja.stan_kamery, fps=round(percepcja.fps, 1), ms=round(percepcja.ms),
        cpu=round(system.cpu), temp_cpu=system.temp, temp_hailo=percepcja.temp_hailo, ram=round(system.ram_proc),
        zasilanie=system.zasilanie, maks_moc=KONF["maks_moc"], nagrywanie=sterownik.nagrywanie.klatki if
        sterownik.nagrywanie.aktywne else None, wyprawa=os.path.basename(sterownik.ostatnia_wyprawa or "") or None,
        analiza=st_an, zdjecia=zdjecia, liczba_zdjec=sterownik.liczba_zdjec)


@app.post("/api/puls")
def api_puls():
    puls["czas"] = time.monotonic()
    return jsonify(ok=True)


@app.post("/api/tryb")
def api_tryb():
    d = request.get_json(force=True)
    puls["czas"] = time.monotonic()
    sterownik.ustaw_tryb(d.get("tryb", "stop"))
    return jsonify(ok=True, tryb=sterownik.tryb)


@app.post("/api/reczny")
def api_reczny():
    d = request.get_json(force=True)
    puls["czas"] = time.monotonic()
    if sterownik.tryb == "reczny":
        sterownik.reczny(max(-1, min(1, d.get("v", 0))), max(-1, min(1, d.get("s", 0))))
    return jsonify(ok=True)


@app.post("/api/cel")
def api_cel():
    d = request.get_json(force=True)
    sterownik.wybierz_cel(d.get("id"), d.get("klasa"))
    return jsonify(ok=True)


@app.post("/api/ustawienia")
def api_ustawienia():
    d = request.get_json(force=True)
    for k in ("maks_moc", "min_moc", "prog_przeszkody", "sledzenie_wysokosc"):
        if k in d:
            KONF[k] = max(0.0, min(1.0, float(d[k])))
    for k in ("odwroc_lewy", "odwroc_prawy", "zamien_strony"):
        if k in d:
            KONF[k] = bool(d[k])
    json.dump(KONF, open(PLIK_KONF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return jsonify(ok=True, konf=KONF)


@app.get("/api/konf")
def api_konf():
    return jsonify(KONF)


@app.post("/api/skan")
def api_skan():
    """Skan 3D z ostatniej wyprawy (tryb Zwiedzaj). Na czas analizy podgląd nie liczy głębi."""
    if sterownik.tryb != "stop" or not sterownik.ostatnia_wyprawa:
        return jsonify(ok=False, blad="Najpierw zakończ tryb Zwiedzaj (STOP)."), 400
    if analiza["watek"] is not None and analiza["watek"].is_alive():
        return jsonify(ok=False, blad="Analiza już trwa."), 400
    percepcja.glebia_wstrzymana = True
    a = P.Analiza(sterownik.ostatnia_wyprawa, percepcja.glebia)

    def po():
        a.join()
        percepcja.glebia_wstrzymana = False
    a.start()
    threading.Thread(target=po, daemon=True).start()
    analiza["watek"] = a
    return jsonify(ok=True)


@app.get("/zdjecia/<path:plik>")
def zdjecia(plik):
    return send_from_directory(ZDJECIA, plik)


@app.get("/skany/<path:plik>")
def skany(plik):
    return send_from_directory(P.SKANY, plik)


def straznik():
    """STOP bez strony; restart procesu po długiej bezczynności (zwalnia Hailo i kamerę dla innych aplikacji)."""
    t_stat = 0.0
    while True:
        time.sleep(0.5)
        if time.monotonic() - t_stat >= 1:
            system.odswiez()
            t_stat = time.monotonic()
        cisza = time.monotonic() - puls["czas"]
        bezczynnosc = time.monotonic() - max(puls["czas"], percepcja._uzycie)  # także podgląd i odczyty stanu
        if sterownik.tryb != "stop" and cisza > KONF["stop_bez_strony_s"]:
            sterownik.ustaw_tryb("stop")
            sterownik.opis = "Strona przestała odpowiadać: STOP dla bezpieczeństwa."
        trwa_analiza = analiza["watek"] is not None and analiza["watek"].is_alive()
        if (sterownik.tryb == "stop" and percepcja.hailo_wczytane() and not trwa_analiza
                and bezczynnosc > KONF["zwolnij_hailo_po_s"]):
            naped.stop()
            print("Bezczynność: kończę proces, żeby zwolnić Hailo i kamerę (systemd uruchomi usługę od nowa).", flush=True)
            os._exit(0)


if __name__ == "__main__":
    kod_dostepu()
    percepcja.start()
    sterownik.start()
    threading.Thread(target=straznik, daemon=True).start()
    app.run(host="0.0.0.0", port=KONF["port"], threaded=True)
