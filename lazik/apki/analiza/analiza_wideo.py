"""Silnik analizy filmu dla aplikacji „Łazik: analiza wideo”.

Trzy niezależne części (wybierane przy każdym filmie):
- notatki: obiekty YOLOv8m na Hailo (co było w kadrze, ile naraz, kiedy), twarze YuNet + SFace na procesorze
  (grupowane w obrębie filmu, żeby policzyć różne osoby: bez nazwisk i bez żadnej bazy osób), oś czasu, klatki kluczowe;
- opis AI: lokalny model wizyjny przez Ollamę (domyślnie gemma3:4b) opisuje klatki kluczowe i cały film po polsku;
- skan 3D: analiza przestrzeni z aplikacji „Łazik: wizja” (głębia na Hailo + ruch kamery).
Wynik: raporty/<film>/raport.html (+ miniatury, dane.json, notatki.txt, skan/).
"""

import base64
import html
import json
import os
import sys
import threading
import time
import urllib.request

import cv2
import numpy as np

KATALOG = os.path.dirname(os.path.abspath(__file__))
WIZJA = os.path.join(os.path.dirname(KATALOG), "wizja")
sys.path.insert(0, WIZJA)
import przestrzen as P  # noqa: E402
from wizja import KLASY, MODELE, Sledzenie, nazwa, slug  # noqa: E402

FILMY = os.path.join(KATALOG, "filmy")
RAPORTY = os.path.join(KATALOG, "raporty")
MODELE_TWARZY = os.path.join(KATALOG, "modele")
OLLAMA = "http://127.0.0.1:11434"
MODEL_AI = "gemma3:4b"
PODOBIENSTWO_TWARZY = 0.363   # próg cosinusowy SFace zalecany przez OpenCV
ANALIZ_NA_SEKUNDE = 10        # tyle klatek na sekundę filmu przechodzi przez YOLO i twarze
MAKS_KLUCZOWYCH = 12

ROZSZERZENIA = (".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".3gp")


def czas_mmss(s):
    s = int(round(s))
    return f"{s // 60:02d}:{s % 60:02d}"


def lista_filmow():
    """Filmy przesłane (filmy/) i nagrania z aplikacji „Łazik: wizja” (wizja/nagrania/*/wideo.avi)."""
    wynik = []
    if os.path.isdir(FILMY):
        for n in os.listdir(FILMY):
            if n.lower().endswith(ROZSZERZENIA) and not n.startswith("."):
                wynik.append(dict(sciezka=os.path.join(FILMY, n), nazwa=n, zrodlo="przesłany"))
    for kat in (P.NAGRANIA,):
        if os.path.isdir(kat):
            for d in os.listdir(kat):
                p = os.path.join(kat, d, "wideo.avi")
                if os.path.exists(p):
                    wynik.append(dict(sciezka=p, nazwa=d, zrodlo="nagranie z kamery"))
    for f in wynik:
        f["rozmiar_mb"] = os.path.getsize(f["sciezka"]) / 1e6
        f["czas"] = os.path.getmtime(f["sciezka"])
        f["raport"] = katalog_raportu(f["sciezka"])
        f["ma_raport"] = os.path.exists(os.path.join(f["raport"], "raport.html"))
    return sorted(wynik, key=lambda f: -f["czas"])


def katalog_raportu(sciezka):
    baza = os.path.basename(os.path.dirname(sciezka)) if os.path.basename(sciezka) == "wideo.avi" else \
        os.path.splitext(os.path.basename(sciezka))[0]
    return os.path.join(RAPORTY, slug(baza) or "film")


def ollama_gotowa():
    """(czy działa, czy ma model, komunikat)"""
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=3) as r:
            modele = [m["name"] for m in json.load(r).get("models", [])]
    except Exception:
        return False, False, "Ollama nie działa (zainstaluj: patrz instrukcja w aplikacji)"
    if not any(m.split(":")[0] == MODEL_AI.split(":")[0] and m.endswith(MODEL_AI.split(":")[1]) for m in modele):
        return True, False, f"brak modelu {MODEL_AI} (ollama pull {MODEL_AI})"
    return True, True, f"gotowa ({MODEL_AI})"


def zapytaj_ai(prompt, obraz_bgr=None, maks_tokenow=220):
    dane = dict(model=MODEL_AI, prompt=prompt, stream=False,
                options=dict(temperature=0.2, num_predict=maks_tokenow, num_ctx=4096))
    if obraz_bgr is not None:
        h, w = obraz_bgr.shape[:2]
        s = 768 / max(h, w)
        if s < 1:
            obraz_bgr = cv2.resize(obraz_bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        ok, jpg = cv2.imencode(".jpg", obraz_bgr, [cv2.IMWRITE_JPEG_QUALITY, 88])
        dane["images"] = [base64.b64encode(jpg.tobytes()).decode()]
    zad = urllib.request.Request(OLLAMA + "/api/generate", data=json.dumps(dane).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(zad, timeout=1800) as r:
        return json.load(r).get("response", "").strip()


class Twarze:
    """Wykrywanie (YuNet) i grupowanie twarzy (SFace) w obrębie jednego filmu."""

    def __init__(self):
        self.det = cv2.FaceDetectorYN.create(os.path.join(MODELE_TWARZY, "yunet.onnx"), "", (320, 320), 0.8, 0.3, 50)
        self.rec = cv2.FaceRecognizerSF.create(os.path.join(MODELE_TWARZY, "sface.onnx"), "")
        self.osoby = []  # dict(srodek, n, miniatura, wielkosc, od, do)

    def przetworz(self, klatka, t):
        h, w = klatka.shape[:2]
        self.det.setInputSize((w, h))
        _, twarze = self.det.detect(klatka)
        wynik = []
        if twarze is None:
            return wynik
        for f in twarze:
            x, y, fw, fh, pew = int(f[0]), int(f[1]), int(f[2]), int(f[3]), float(f[14])
            if fw < 36 or fh < 36 or pew < 0.85:  # za małe albo niepewne do porównywania
                wynik.append((x, y, fw, fh, None))
                continue
            cecha = self.rec.feature(self.rec.alignCrop(klatka, f)).reshape(-1)
            cecha = cecha / (np.linalg.norm(cecha) + 1e-9)
            nr = self._przypisz(cecha, klatka, (x, y, fw, fh), t)
            wynik.append((x, y, fw, fh, nr))
        return wynik

    def _przypisz(self, cecha, klatka, ramka, t):
        najl, podob = None, PODOBIENSTWO_TWARZY
        for i, o in enumerate(self.osoby):
            s = float(o["srodek"] @ cecha)
            if s > podob:
                najl, podob = i, s
        x, y, fw, fh = ramka
        if najl is None:
            self.osoby.append(dict(suma=cecha.copy(), srodek=cecha.copy(), n=0, miniatura=None, wielkosc=0, od=t, do=t))
            najl = len(self.osoby) - 1
        o = self.osoby[najl]
        o["suma"] += cecha
        o["srodek"] = o["suma"] / (np.linalg.norm(o["suma"]) + 1e-9)
        o["n"] += 1
        o["do"] = t
        if fw * fh > o["wielkosc"]:  # zostawiamy największe (najczytelniejsze) ujęcie twarzy
            H, W = klatka.shape[:2]
            m = int(0.25 * max(fw, fh))
            wyc = klatka[max(0, y - m):min(H, y + fh + m), max(0, x - m):min(W, x + fw + m)]
            if wyc.size:
                o["miniatura"], o["wielkosc"] = cv2.resize(wyc, (128, int(128 * wyc.shape[0] / wyc.shape[1]))), fw * fh
        return najl

    def scal(self):
        """Na koniec łączy grupy, które okazały się tą samą osobą."""
        zmiana = True
        while zmiana:
            zmiana = False
            for i in range(len(self.osoby)):
                for j in range(i + 1, len(self.osoby)):
                    a, b = self.osoby[i], self.osoby[j]
                    if float(a["srodek"] @ b["srodek"]) > PODOBIENSTWO_TWARZY + 0.05:
                        a["suma"] += b["suma"]
                        a["srodek"] = a["suma"] / (np.linalg.norm(a["suma"]) + 1e-9)
                        a["n"] += b["n"]
                        a["od"], a["do"] = min(a["od"], b["od"]), max(a["do"], b["do"])
                        if b["wielkosc"] > a["wielkosc"]:
                            a["miniatura"], a["wielkosc"] = b["miniatura"], b["wielkosc"]
                        del self.osoby[j]
                        zmiana = True
                        break
                if zmiana:
                    break


class AnalizaWideo(threading.Thread):
    """Analiza jednego filmu w tle; postęp w self.stan (czyta interfejs przez odczyt())."""

    SERIA = 8

    def __init__(self, sciezka, notatki=True, opis_ai=False, skan3d=False):
        super().__init__(daemon=True)
        self.sciezka, self.opcje = sciezka, dict(notatki=notatki, opis_ai=opis_ai, skan3d=skan3d)
        self.przerwij = False
        self.lock = threading.Lock()
        self.podglad = None
        self._dev_temp = None
        self.stan = dict(etap="start", krok="", gotowe=0, razem=0, kl_s=0.0, zostalo=None, osoby=0, osoby_pewne=0,
                         naraz=0, obiekty=[], hailo_proc=0.0, hailo_temp=None, wynik=None, blad=None, podsumowanie="")

    def _ustaw(self, **kw):
        with self.lock:
            self.stan.update(kw)

    def odczyt(self):
        with self.lock:
            return dict(self.stan)

    def _temp_hailo(self, hailo):
        try:
            if self._dev_temp is None:
                self._dev_temp = hailo.target.get_physical_devices()[0]
            t = self._dev_temp.control.get_chip_temperature()
            self._ustaw(hailo_temp=max(t.ts0_temperature, t.ts1_temperature))
        except Exception:
            pass

    def run(self):
        try:
            self._analizuj()
        except Exception as e:
            import traceback
            traceback.print_exc()
            msg = str(e)
            if "HAILO_OUT_OF_PHYSICAL_DEVICES" in msg or "physical devices" in msg.lower():
                msg = "Hailo jest zajęte przez inną aplikację (zamknij „Łazik: wizja”)."
            self._ustaw(etap="błąd", blad=msg)

    # ---------- główny przebieg ----------
    def _analizuj(self):
        self.raport = katalog_raportu(self.sciezka)
        os.makedirs(os.path.join(self.raport, "miniatury"), exist_ok=True)
        cap = cv2.VideoCapture(self.sciezka)
        if not cap.isOpened():
            raise RuntimeError("nie da się otworzyć filmu (nieobsługiwany format?)")
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        razem = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        szer, wys = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        self.info = dict(plik=os.path.basename(self.sciezka) if not self.sciezka.endswith("wideo.avi")
                         else os.path.basename(os.path.dirname(self.sciezka)),
                         fps=round(fps, 1), klatki=razem, sekundy=razem / fps if fps else 0, rozdzielczosc=f"{szer}×{wys}")
        notatki, kluczowe = None, []
        if self.opcje["notatki"] or self.opcje["opis_ai"]:
            notatki, kluczowe = self._notatki(fps, razem)
        if self.przerwij:
            return self._ustaw(etap="przerwano")
        opisy, podsumowanie = [], ""
        if self.opcje["opis_ai"]:
            opisy, podsumowanie = self._opis_ai(kluczowe, notatki)
        if self.przerwij:
            return self._ustaw(etap="przerwano")
        skan = None
        if self.opcje["skan3d"]:
            skan = self._skan3d()
        if self.przerwij:
            return self._ustaw(etap="przerwano")
        self._ustaw(etap="zapis", krok="Zapisuję raport")
        sciezka = self._raport(notatki, kluczowe, opisy, podsumowanie, skan)
        self._ustaw(etap="gotowe", wynik=sciezka, podsumowanie=podsumowanie)

    # ---------- notatki: obiekty, osoby, oś czasu ----------
    def _notatki(self, fps, razem):
        from picamera2.devices import Hailo
        self._ustaw(etap="notatki", krok="Ładuję model YOLOv8m na Hailo", razem=razem, gotowe=0)
        sciezki = MODELE[1][1] + MODELE[0][1]  # YOLOv8m, a gdy go brak: YOLOv8s
        hailo = Hailo(next(p for p in sciezki if os.path.exists(p)))
        mh, mw, _ = hailo.get_input_shape()
        twarze = Twarze()
        sled = Sledzenie()
        krok = max(1, int(round(fps / ANALIZ_NA_SEKUNDE)))
        cap = cv2.VideoCapture(self.sciezka)
        klasy = {}      # klasa → dict(naraz, sekundy:set, sledzone:set, miniatura, pew, od)
        naraz_osob = 0
        kluczowe, poprz_hist, ostatnia_kl = [], None, -999.0
        t0, czas_hailo, nr, gotowe = time.monotonic(), 0.0, 0, 0
        temp_t = 0.0
        self._ustaw(krok="Notatki: osoby i przedmioty")
        while not self.przerwij:
            seria = []
            while len(seria) < self.SERIA:
                ok = cap.grab()
                if not ok:
                    break
                if nr % krok == 0:
                    ok, k = cap.retrieve()
                    if ok:
                        if k.shape[1] > 1280:  # filmy 4K/1080p z telefonu: wystarczy 1280 px szerokości
                            k = cv2.resize(k, (1280, int(k.shape[0] * 1280 / k.shape[1])), interpolation=cv2.INTER_AREA)
                        seria.append((nr / fps, k))
                nr += 1
            if not seria:
                break
            th = time.monotonic()
            zlecenia = [hailo.run_async(cv2.resize(cv2.cvtColor(k, cv2.COLOR_BGR2RGB), (mw, mh))) for _, k in seria]
            wyniki = [z.result() for z in zlecenia]
            czas_hailo += time.monotonic() - th
            for (t, k), out in zip(seria, wyniki):
                wyk = [(kl, float(d[1]), float(d[0]), float(d[3]), float(d[2]), float(d[4]))
                       for kl, ds in enumerate(out) for d in ds if d[4] >= 0.45]
                obiekty = sled.aktualizuj(wyk, t)  # czas filmu zamiast zegara: śledzenie działa też przy skokach
                licz = {}
                for o in obiekty:
                    licz[o["klasa"]] = licz.get(o["klasa"], 0) + 1
                    k_ = klasy.setdefault(o["klasa"], dict(naraz=0, sekundy=set(), sledzone=set(), miniatura=None,
                                                           pew=0.0, od=t))
                    k_["sekundy"].add(int(t))
                    k_["sledzone"].add(o["id"])
                    if o["pew"] > k_["pew"]:
                        H, W = k.shape[:2]
                        x0, y0, x1, y1 = o["ramka"]
                        wyc = k[int(max(0, y0) * H):int(min(1, y1) * H), int(max(0, x0) * W):int(min(1, x1) * W)]
                        if wyc.size and wyc.shape[0] > 8 and wyc.shape[1] > 8:
                            s = 160 / max(wyc.shape[:2])
                            k_["miniatura"] = cv2.resize(wyc, (max(1, int(wyc.shape[1] * s)), max(1, int(wyc.shape[0] * s))))
                            k_["pew"] = o["pew"]
                for kl, n in licz.items():
                    klasy[kl]["naraz"] = max(klasy[kl]["naraz"], n)
                naraz_osob = max(naraz_osob, licz.get(0, 0))
                ramki_twarzy = twarze.przetworz(k, t) if licz.get(0) else []
                # klatki kluczowe: zmiana sceny (histogram) albo co najmniej co 1/12 filmu
                hist = cv2.calcHist([cv2.cvtColor(cv2.resize(k, (160, 90)), cv2.COLOR_BGR2HSV)], [0, 1], None,
                                    [16, 8], [0, 180, 0, 256])
                cv2.normalize(hist, hist)
                zmiana = 1.0 if poprz_hist is None else 1 - cv2.compareHist(poprz_hist, hist, cv2.HISTCMP_CORREL)
                dlugosc = razem / fps if fps else 1
                if (zmiana > 0.35 and t - ostatnia_kl > 2) or t - ostatnia_kl > dlugosc / MAKS_KLUCZOWYCH:
                    kluczowe.append((t, k.copy(), sorted(licz.items(), key=lambda x: -x[1])))
                    ostatnia_kl, poprz_hist = t, hist
                gotowe += 1
                if gotowe % 4 == 0:
                    with self.lock:
                        self.podglad = (self._narysuj(k, obiekty, ramki_twarzy), t)
            dt = time.monotonic() - t0
            pozycja = min(nr, razem)
            tempo = pozycja / dt if dt else 0
            if time.monotonic() - temp_t > 2:
                self._temp_hailo(hailo)
                temp_t = time.monotonic()
            pewne = sum(1 for o in twarze.osoby if o["n"] >= 2)
            top = sorted(((nazwa(kl), v["naraz"]) for kl, v in klasy.items()), key=lambda x: -x[1])[:8]
            self._ustaw(gotowe=pozycja, kl_s=tempo, zostalo=(razem - pozycja) / tempo if tempo else None,
                        osoby=len(twarze.osoby), osoby_pewne=pewne, naraz=naraz_osob, obiekty=top,
                        hailo_proc=min(100.0, 100 * czas_hailo / dt) if dt else 0)
        cap.release()
        twarze.scal()
        if len(kluczowe) > MAKS_KLUCZOWYCH:  # równomiernie wybrane, gdy zmian sceny było dużo
            idx = np.linspace(0, len(kluczowe) - 1, MAKS_KLUCZOWYCH).round().astype(int)
            kluczowe = [kluczowe[i] for i in sorted(set(idx))]
        return dict(klasy=klasy, osoby=twarze.osoby, naraz=naraz_osob), kluczowe

    @staticmethod
    def _narysuj(k, obiekty, ramki_twarzy):
        k = k.copy()
        H, W = k.shape[:2]
        for o in obiekty:
            x0, y0, x1, y1 = o["ramka"]
            kol = [int(c) for c in cv2.cvtColor(np.uint8([[[(o["klasa"] * 47 // 2) % 180, 190, 255]]]), cv2.COLOR_HSV2BGR)[0, 0]]
            cv2.rectangle(k, (int(x0 * W), int(y0 * H)), (int(x1 * W), int(y1 * H)), kol, 2)
            cv2.putText(k, slug(nazwa(o["klasa"])), (int(x0 * W) + 3, int(y0 * H) + 18), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, kol, 2)
        for x, y, fw, fh, nr in ramki_twarzy:
            cv2.rectangle(k, (x, y), (x + fw, y + fh), (255, 255, 255), 2)
            if nr is not None:
                cv2.putText(k, f"osoba {nr + 1}", (x, max(14, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        return k

    # ---------- opis AI ----------
    def _opis_ai(self, kluczowe, notatki):
        dziala, ma_model, kom = ollama_gotowa()
        if not (dziala and ma_model):
            return [], f"Opis AI niedostępny: {kom}."
        opisy = []
        t0 = time.monotonic()
        for i, (t, k, licz) in enumerate(kluczowe):
            if self.przerwij:
                return opisy, ""
            uplyw = time.monotonic() - t0
            zost = uplyw / i * (len(kluczowe) - i) if i else None
            self._ustaw(etap="opis", krok=f"Opis AI: klatka {i + 1} z {len(kluczowe)} ({czas_mmss(t)})",
                        gotowe=i, razem=len(kluczowe) + 1, zostalo=zost, kl_s=0)
            with self.lock:
                self.podglad = (k, t)
            wykryte = ", ".join(f"{nazwa(kl)} ×{n}" for kl, n in licz) or "nic"
            opisy.append(zapytaj_ai(
                "Opisz po polsku w 2–3 zdaniach, co widać na tej klatce filmu: miejsce, osoby (bez zgadywania, "
                f"kim są), co robią, ważne przedmioty. Detektor obiektów wskazał: {wykryte}.", k))
        self._ustaw(krok="Opis AI: podsumowanie całego filmu", gotowe=len(kluczowe))
        linie = "\n".join(f"[{czas_mmss(t)}] {o}" for (t, _, _), o in zip(kluczowe, opisy))
        przedm = ", ".join(f"{nazwa(kl)} (maks. {v['naraz']} naraz)" for kl, v in
                           sorted(notatki["klasy"].items(), key=lambda x: -len(x[1]["sekundy"]))[:15]) if notatki else ""
        osoby = sum(1 for o in notatki["osoby"] if o["n"] >= 2) if notatki else 0
        podsumowanie = zapytaj_ai(
            f"Oto opisy kolejnych klatek filmu ({czas_mmss(self.info['sekundy'])}):\n{linie}\n"
            f"Wykryte przedmioty: {przedm}. Różnych twarzy: {osoby}.\n"
            "Napisz po polsku zwięzły opis całego filmu (5–8 zdań): gdzie się dzieje, kto i co robi, jak zmienia się "
            "scena, co jest w otoczeniu. Nie zgaduj tożsamości osób.", None, maks_tokenow=420)
        return opisy, podsumowanie

    # ---------- skan 3D ----------
    def _skan3d(self):
        self._ustaw(etap="skan", krok="Skan 3D: głębia i ruch kamery", gotowe=0, razem=0)
        P.SKANY = os.path.join(self.raport, "skan")  # skan trafia do folderu raportu (widać go też na telefonie)
        katalog = os.path.dirname(self.sciezka)
        a = P.Analiza(katalog, P.Glebia(), wideo=self.sciezka)
        a.start()
        while a.is_alive():
            if self.przerwij:
                a.przerwij = True
            st = a.odczyt()
            with a.lock:
                if a.podglad is not None:
                    kl, g = a.podglad
                    with self.lock:
                        self.podglad = (cv2.hconcat([kl, P.mapa_kolorow(g, kl.shape)]), None)
            self._ustaw(gotowe=st["gotowe"], razem=st["razem"], kl_s=st["kl_s"], zostalo=st["zostalo"],
                        hailo_proc=st.get("hailo_proc", 0.0),
                        krok=f"Skan 3D: {st['punkty']:,} punktów, droga ≈{st['droga']:.1f} m, obrót {st['obrot']:.0f}°".replace(",", " "))
            time.sleep(0.3)
        st = a.odczyt()
        if st["etap"] != "gotowe":
            return dict(blad=st.get("blad") or st["etap"])
        return dict(katalog=st["wynik"], werdykt=st["werdykt"], punkty=st["punkty"])

    # ---------- raport ----------
    def _raport(self, notatki, kluczowe, opisy, podsumowanie, skan):
        R = self.raport
        mini = os.path.join(R, "miniatury")
        info = self.info
        sekcje = []
        dane = dict(film=info, analiza=time.strftime("%Y-%m-%d %H:%M"), opcje=self.opcje)
        tekst = [f"Film: {info['plik']} ({czas_mmss(info['sekundy'])}, {info['rozdzielczosc']})"]
        if podsumowanie:
            sekcje.append(f"<section><h2>Opis filmu (AI)</h2><p class='duzy'>{html.escape(podsumowanie)}</p></section>")
            tekst.append("\nOPIS: " + podsumowanie)
        if notatki:
            osoby = sorted(notatki["osoby"], key=lambda o: o["od"])
            pewne = [o for o in osoby if o["n"] >= 2]
            karty = []
            for i, o in enumerate(osoby):
                plik = f"twarz_{i + 1}.jpg"
                if o["miniatura"] is not None:
                    cv2.imwrite(os.path.join(mini, plik), o["miniatura"])
                pew = "" if o["n"] >= 2 else "<small class='szary'>widziana raz: może to ta sama osoba</small>"
                karty.append(f"<figure class='twarz'><img src='miniatury/{plik}' alt='Osoba {i + 1}'><figcaption>"
                             f"<b>Osoba {i + 1}</b><br>{czas_mmss(o['od'])}–{czas_mmss(o['do'])} · {o['n']}× {pew}"
                             f"</figcaption></figure>")
            sekcje.append(
                "<section><h2>Osoby</h2>"
                f"<div class='liczby'><div><b>{len(pewne)}</b>różne twarze (pewne)</div>"
                f"<div><b>{len(osoby)}</b>wszystkie grupy twarzy</div>"
                f"<div><b>{notatki['naraz']}</b>najwięcej osób naraz (sylwetki)</div></div>"
                f"<div class='twarze'>{''.join(karty) or '<p>Nie wykryto twarzy (za małe, odwrócone albo brak osób).</p>'}</div>"
                "<p class='szary'>Twarze są tylko grupowane w obrębie tego filmu, bez nazwisk i bez żadnej bazy osób. "
                "Dane zostają na Pi.</p></section>")
            tekst.append(f"\nOSOBY: różne twarze {len(pewne)} (wszystkich grup {len(osoby)}), najwięcej naraz {notatki['naraz']}")
            wiersze = []
            for kl, v in sorted(notatki["klasy"].items(), key=lambda x: -len(x[1]["sekundy"])):
                plik = f"obiekt_{kl}.jpg"
                if v["miniatura"] is not None:
                    cv2.imwrite(os.path.join(mini, plik), v["miniatura"])
                wiersze.append(f"<tr><td><img src='miniatury/{plik}' alt=''></td><td><b>{html.escape(nazwa(kl))}</b></td>"
                               f"<td class='num'>{v['naraz']}</td><td class='num'>{len(v['sekundy'])} s</td>"
                               f"<td class='num'>{czas_mmss(v['od'])}</td></tr>")
                tekst.append(f"- {nazwa(kl)}: maks. {v['naraz']} naraz, widoczne {len(v['sekundy'])} s, od {czas_mmss(v['od'])}")
            sekcje.append("<section><h2>Co było w kadrze</h2><div class='przewin'><table><thead><tr><th></th><th>Przedmiot"
                          "</th><th>Maks. naraz</th><th>Widoczny</th><th>Pierwszy raz</th></tr></thead><tbody>"
                          + ("".join(wiersze) or "<tr><td colspan=5>Nic nie rozpoznano.</td></tr>") + "</tbody></table></div></section>")
            os_czasu = []
            for kl, v in notatki["klasy"].items():
                s = sorted(v["sekundy"])
                start = prev = s[0] if s else None
                for x in s[1:] + [None]:
                    if x is None or x - prev > 2:
                        os_czasu.append((start, prev + 1, nazwa(kl)))
                        start = x
                    prev = x if x is not None else prev
            os_czasu.sort()
            sekcje.append("<section><h2>Oś czasu</h2><ul class='os'>" + "".join(
                f"<li><span class='czas'>{czas_mmss(a)}–{czas_mmss(b)}</span> {html.escape(n)}</li>"
                for a, b, n in os_czasu[:60]) + "</ul></section>")
            dane.update(osoby=[dict(nr=i + 1, od=o["od"], do=o["do"], ujecia=o["n"]) for i, o in enumerate(osoby)],
                        najwiecej_osob_naraz=notatki["naraz"],
                        przedmioty=[dict(klasa=nazwa(kl), maks_naraz=v["naraz"], sekundy=len(v["sekundy"]), od=v["od"])
                                    for kl, v in notatki["klasy"].items()])
        if kluczowe:
            karty = []
            for i, (t, k, licz) in enumerate(kluczowe):
                plik = f"klatka_{i + 1}.jpg"
                s = 480 / k.shape[1]
                cv2.imwrite(os.path.join(mini, plik), cv2.resize(k, (480, int(k.shape[0] * s))), [cv2.IMWRITE_JPEG_QUALITY, 85])
                opis = f"<p>{html.escape(opisy[i])}</p>" if i < len(opisy) else ""
                wykr = ", ".join(f"{nazwa(kl)} ×{n}" for kl, n in licz) or "nic nie rozpoznano"
                karty.append(f"<figure class='klatka'><img src='miniatury/{plik}' alt=''><figcaption>"
                             f"<span class='czas'>{czas_mmss(t)}</span> {html.escape(wykr)}{opis}</figcaption></figure>")
                if i < len(opisy):
                    tekst.append(f"[{czas_mmss(t)}] {opisy[i]}")
            sekcje.append("<section><h2>Klatki kluczowe</h2><div class='klatki'>" + "".join(karty) + "</div></section>")
        if skan:
            if skan.get("katalog"):
                wzgl = os.path.relpath(os.path.join(skan["katalog"], "skan.html"), R)
                sekcje.append(f"<section><h2>Skan 3D</h2><p>{html.escape(skan['werdykt'])}</p>"
                              f"<p><a class='przycisk' href='{wzgl}'>Otwórz skan 3D ({skan['punkty']:,} punktów)</a></p></section>".replace(",", " "))
                dane["skan"] = dict(katalog=os.path.relpath(skan["katalog"], R), werdykt=skan["werdykt"])
            else:
                sekcje.append(f"<section><h2>Skan 3D</h2><p>Nie udało się: {html.escape(skan['blad'])}</p></section>")
        tytul = html.escape(info["plik"])
        strona = f"""<!doctype html><html lang="pl" translate="no"><head><meta charset="utf-8">
<meta name="google" content="notranslate"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Raport: {tytul}</title><style>
:root{{--tlo:#0d1114;--panel:#161c21;--tekst:#e6ebee;--szary:#8b979f;--akcent:#e0a640;--linia:#232b31}}
body{{margin:0;background:var(--tlo);color:var(--tekst);font:16px/1.5 system-ui,"Segoe UI",sans-serif}}
main{{max-width:980px;margin:0 auto;padding:22px max(16px,env(safe-area-inset-left)) 60px;display:flex;flex-direction:column;gap:26px}}
h1{{font-size:26px;margin:0}} h2{{font-size:20px;margin:0 0 10px}} p{{margin:0 0 8px;max-width:72ch}}
.szary{{color:var(--szary);font-size:14px}} .duzy{{font-size:17px}}
section{{background:var(--panel);border:1px solid var(--linia);border-radius:12px;padding:16px 18px}}
.liczby{{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:12px}} .liczby div{{background:#1f272d;border-radius:10px;padding:10px 14px;color:var(--szary);font-size:14px;display:flex;flex-direction:column}}
.liczby b{{font-size:28px;color:var(--tekst)}}
.twarze{{display:flex;flex-wrap:wrap;gap:12px}} .twarz{{margin:0;width:140px}} .twarz img{{width:128px;border-radius:8px;display:block}}
.twarz figcaption{{font-size:13px;color:var(--szary);margin-top:4px}}
table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}} th,td{{text-align:left;padding:6px 10px;border-bottom:1px solid var(--linia);vertical-align:middle}}
th{{color:var(--szary);font-size:13px;font-weight:600}} td img{{max-width:64px;max-height:64px;border-radius:6px;display:block}} .num{{text-align:right;white-space:nowrap}}
.przewin{{overflow-x:auto}} .os{{list-style:none;padding:0;margin:0;columns:2 260px}} .os li{{padding:3px 0;break-inside:avoid}}
.czas{{font-family:ui-monospace,monospace;color:var(--akcent);font-size:14px;margin-right:6px}}
.klatki{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}} .klatka{{margin:0}} .klatka img{{width:100%;border-radius:8px;display:block}}
.klatka figcaption{{font-size:14px;color:var(--szary);margin-top:6px}} .klatka figcaption p{{color:var(--tekst);margin-top:4px}}
a{{color:var(--akcent)}} .przycisk{{display:inline-block;background:var(--akcent);color:#111;padding:10px 16px;border-radius:10px;text-decoration:none;font-weight:600}}
</style></head><body><main>
<header><h1>Raport: {tytul}</h1><p class="szary">{czas_mmss(info['sekundy'])} · {info['rozdzielczosc']} · {info['fps']} kl/s ·
analiza {dane['analiza']} · Łazik: analiza wideo</p></header>
{''.join(sekcje)}
</main></body></html>"""
        open(os.path.join(R, "raport.html"), "w", encoding="utf-8").write(strona)
        json.dump(dane, open(os.path.join(R, "dane.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
        open(os.path.join(R, "notatki.txt"), "w", encoding="utf-8").write("\n".join(tekst) + "\n")
        return os.path.join(R, "raport.html")
