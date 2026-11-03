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
import ustawienia as U  # noqa: E402
from wizja import ZDJECIA, System  # noqa: E402

PLIK_KONF = os.path.join(KATALOG, "konfiguracja.json")
PLIK_KODU = os.path.join(KATALOG, "kod_dostepu.txt")
KONF = U.wczytaj(PLIK_KONF)


def kod_dostepu():
    if not os.path.exists(PLIK_KODU):
        with open(PLIK_KODU, "w") as f:
            f.write(secrets.token_urlsafe(8))
        os.chmod(PLIK_KODU, 0o600)
    return open(PLIK_KODU).read().strip()


naped = Naped(KONF)
percepcja = Percepcja(KONF)
sterownik = Sterownik(naped, percepcja, KONF)
system = System()
czujnik = {"dane": None, "blad": None}
zyro = {"imu": None, "blad": None}


def wlacz_zyroskop():
    """MPU6050 na I2C: kurs względny, trzymanie toru w napędzie i STOP przy przewróceniu."""
    try:
        from zyroskop import Zyroskop
        imu = Zyroskop(KONF, spoczynek=naped.spoczynek)
    except Exception as e:
        zyro["blad"] = f"żyroskop niedostępny: {e}"
        return
    imu.start()
    zyro["imu"] = naped.imu = imu


def czytaj_czujnik():
    """BME280 co 2 s (temperatura, wilgotność, ciśnienie) do stałego panelu na stronie."""
    try:
        from bme280 import BME280
        c = BME280()
    except Exception as e:
        czujnik["blad"] = f"czujnik BME280 niedostępny: {e}"
        return
    while True:
        try:
            czujnik["dane"], czujnik["blad"] = c.odczyt(), None
        except Exception as e:
            czujnik["blad"] = f"błąd odczytu BME280: {e}"
        time.sleep(2)
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
            klatka, nr = percepcja.do_podgladu()
            if klatka is None or nr == ostatni:
                time.sleep(0.03)
                continue
            ostatni = nr
            szer = int(KONF["szer_strumienia"]) * (2 if KONF["strumien_glebia"] else 1)
            if klatka.shape[1] > szer:
                klatka = cv2.resize(klatka, (szer, int(klatka.shape[0] * szer / klatka.shape[1])), interpolation=cv2.INTER_AREA)
            ok, jpg = cv2.imencode(".jpg", klatka, [cv2.IMWRITE_JPEG_QUALITY, int(KONF["jakosc_strumienia"])])
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
        zasilanie=system.zasilanie, hailo_proc=round(percepcja.hailo_proc), czujnik=czujnik["dane"],
        blad_czujnika=czujnik["blad"],
        zyroskop=zyro["imu"].odczyt() if zyro["imu"] else None, blad_zyroskopu=zyro["blad"] or (zyro["imu"].blad if zyro["imu"] else None),
        trzymaj_tor=bool(KONF.get("trzymaj_tor")), trzyma_tor=naped.trzyma_tor, korekta=round(naped.korekta, 2),
        maks_przechyl=KONF["maks_przechyl"], ram_gb=[round(system.ram_uzyte, 1), round(system.ram_razem, 1)], maks_moc=KONF["maks_moc"], nagrywanie=sterownik.nagrywanie.klatki if
        sterownik.nagrywanie.aktywne else None, wyprawa=os.path.basename(sterownik.ostatnia_wyprawa or "") or None,
        analiza=st_an, zdjecia=zdjecia, liczba_zdjec=sterownik.liczba_zdjec, model=percepcja.nazwa_modelu,
        proporcje=2 * 4 / 3 if KONF["strumien_glebia"] else 4 / 3)


@app.post("/api/zyroskop/<akcja>")
def api_zyroskop(akcja):
    imu = zyro["imu"]
    if imu is None:
        return jsonify(blad=zyro["blad"] or "brak żyroskopu"), 404
    if akcja == "zeruj":
        imu.zeruj()
    elif akcja == "kalibruj":
        naped.stop()
        imu.kalibruj()
    else:
        return jsonify(blad="nieznana akcja"), 400
    return jsonify(ok=True)


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
        maks = 1.0 if d.get("pelna") else None  # pad: tryby pełnej mocy, spustów i gałki proporcjonalnej pomijają maks. moc
        sterownik.reczny(max(-1, min(1, d.get("v", 0))), max(-1, min(1, d.get("s", 0))), maks, bool(d.get("liniowo")))
    return jsonify(ok=True)


@app.post("/api/cel")
def api_cel():
    d = request.get_json(force=True)
    sterownik.wybierz_cel(d.get("id"), d.get("klasa"))
    return jsonify(ok=True)


@app.get("/api/schemat")
def api_schemat():
    return jsonify(pola=U.schemat(), wartosci={k: KONF.get(k) for k in U.DOMYSLNE if k not in ("piny", "kamera_v4l2")})


@app.post("/api/ustawienia")
def api_ustawienia():
    """Zapis dowolnych pól z opisu ustawień (sprawdzone zakresy). Zmiany kamery otwierają ją ponownie."""
    d = request.get_json(force=True)
    bledy = {}
    for k, v in d.items():
        try:
            KONF[k] = U.sprawdz(k, v)
        except ValueError as e:
            bledy[k] = str(e)
    if {"kamera_rozdzielczosc", "kamera_fps", "kamera_stale_kl_s"} & set(d):
        percepcja.ponownie_kamera()
    U.zapisz(PLIK_KONF, KONF)
    return jsonify(ok=not bledy, bledy=bledy, konf=KONF)


@app.post("/api/ustawienia/domyslne")
def api_domyslne():
    zakladka = request.get_json(force=True).get("zakladka")
    for p in U.schemat():
        if p["zakladka"] == zakladka:
            KONF[p["klucz"]] = p["domyslnie"]
    if zakladka == "Kamera":
        KONF["kamera_v4l2"] = {}
        urz = percepcja.kamera.urzadzenie if percepcja.kamera else None
        for c in (U.kontrolki_kamery(urz) if urz else []):
            try:
                U.ustaw_kontrolke(urz, c["nazwa"], c["domyslnie"])
            except ValueError:
                pass
        percepcja.ponownie_kamera()
    U.zapisz(PLIK_KONF, KONF)
    return jsonify(ok=True)


@app.get("/api/konf")
def api_konf():
    return jsonify(KONF)


@app.get("/api/kamera/kontrolki")
def api_kontrolki():
    percepcja.potrzebna()
    urz = percepcja.kamera.urzadzenie if percepcja.kamera else None
    lista = U.kontrolki_kamery(urz) if urz else []
    for c in lista:
        c["podpis"] = U.PODPISY_KAMERY.get(c["nazwa"], c["nazwa"].replace("_", " "))
    return jsonify(urzadzenie=urz, kontrolki=lista)


@app.post("/api/kamera/kontrolki")
def api_kontrolka():
    d = request.get_json(force=True)
    urz = percepcja.kamera.urzadzenie if percepcja.kamera else None
    if not urz:
        return jsonify(ok=False, blad="kamera wyłączona"), 400
    try:
        U.ustaw_kontrolke(urz, d["nazwa"], d["wartosc"])
    except (ValueError, KeyError) as e:
        return jsonify(ok=False, blad=str(e)), 400
    KONF.setdefault("kamera_v4l2", {})[d["nazwa"]] = int(d["wartosc"])  # zapamiętane i nakładane przy otwarciu kamery
    U.zapisz(PLIK_KONF, KONF)
    return jsonify(ok=True)


@app.post("/api/restart")
def api_restart():
    """Restart usługi (systemd uruchamia ją od nowa); łazik staje."""
    naped.stop()
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return jsonify(ok=True)


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
        temp = max(system.temp or 0, percepcja.temp_hailo or 0)
        if sterownik.tryb not in ("stop", "reczny") and temp > KONF["maks_temp"]:
            sterownik.ustaw_tryb("stop")
            sterownik.opis = f"Za gorąco ({temp:.0f} °C > {KONF['maks_temp']} °C): STOP trybu, żeby układy ostygły."
        imu = zyro["imu"]
        if imu is not None and imu.ok and imu.przechyl > KONF["maks_przechyl"] and (naped.lewy or naped.prawy or sterownik.tryb != "stop"):
            sterownik.ustaw_tryb("stop")
            naped.stop()
            sterownik.opis = f"Przechył {imu.przechyl:.0f}° (> {KONF['maks_przechyl']}°): STOP, łazik mógł się przewrócić."
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
    threading.Thread(target=czytaj_czujnik, daemon=True).start()
    wlacz_zyroskop()
    sterownik.start()
    threading.Thread(target=straznik, daemon=True).start()
    app.run(host="0.0.0.0", port=KONF["port"], threaded=True)
