#!/usr/bin/env python3
"""Łazik: analiza wideo. Osobna aplikacja na pełny ekran: filmy z telefonu (kod QR) albo z kamery łazika →
notatki (osoby, przedmioty, oś czasu), opis AI i/lub skan 3D → raport HTML (na Pi i na telefonie).
Krzyżyk albo Esc zamyka."""

import os
import shutil
import socket
import subprocess
import sys
import threading
import time

KATALOG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KATALOG)
import analiza_wideo as A  # noqa: E402  (dodaje też ścieżkę do aplikacji „wizja”)
import cv2  # noqa: E402
import qrcode  # noqa: E402
from PyQt5.QtCore import QFileSystemWatcher, QPointF, QRectF, QSize, Qt, QTimer  # noqa: E402
from PyQt5.QtGui import QColor, QImage, QPainter, QPixmap, QPolygonF  # noqa: E402
from PyQt5.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,  # noqa: E402
                             QProgressBar, QScroller, QSlider, QStackedWidget, QVBoxLayout, QWidget)
from wizja import (CZERWONY, PANEL, SZARY, TEKST, TLO, ZIELONY, ZOLTY, System, Wiersz, bgr_na_qimage,  # noqa: E402
                   kolor_temp, przycisk)
import serwer_wideo  # noqa: E402

PORT = serwer_wideo.PORT


def adres_lan():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def adres_tailscale():
    try:
        return subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=3).stdout.split()[0]
    except Exception:
        return None


def obraz_qr(tekst, rozmiar=170):
    q = qrcode.QRCode(border=2, box_size=6)
    q.add_data(tekst)
    q.make(fit=True)
    img = q.make_image(fill_color="black", back_color="white").convert("RGB")
    qi = QImage(img.tobytes(), img.width, img.height, 3 * img.width, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(qi).scaled(rozmiar, rozmiar, Qt.KeepAspectRatio, Qt.FastTransformation)


def otworz_w_przegladarce(sciezka):
    flagi = ["--ozone-platform=wayland"] if os.environ.get("WAYLAND_DISPLAY") else []
    subprocess.Popen(["chromium", *flagi, f"--app=file://{sciezka}", "--start-maximized"], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


AKCENT = "#e0a640"


def ikona_dom(r=26):
    """Domek: kod QR dla domowego WiFi."""
    px = QPixmap(r, r)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(AKCENT))
    p.drawPolygon(QPolygonF([QPointF(r / 2, 2), QPointF(r - 2, r * 0.48), QPointF(2, r * 0.48)]))
    p.drawRect(QRectF(r * 0.2, r * 0.46, r * 0.6, r * 0.48))
    p.setBrush(QColor(PANEL))
    p.drawRect(QRectF(r * 0.42, r * 0.64, r * 0.16, r * 0.3))
    p.end()
    return px


def ikona_tailscale(r=26):
    """Kropki 3×3 jak w logo Tailscale: kod QR dla adresu Tailscale."""
    px = QPixmap(r, r)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    jasne = {(0, 1), (1, 1), (2, 1), (1, 2)}
    for x in range(3):
        for y in range(3):
            p.setBrush(QColor("#ffffff" if (x, y) in jasne else "#5b6670"))
            p.drawEllipse(QPointF(r * (0.2 + 0.3 * x), r * (0.2 + 0.3 * y)), r * 0.11, r * 0.11)
    p.end()
    return px


class Klikalny(QLabel):
    def __init__(self, akcja):
        super().__init__()
        self.akcja = akcja
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        self.akcja()


class WierszFilmu(QWidget):
    """Wiersz listy: miniatura, data nagrania i długość, nazwa pliku, stan raportu."""

    def __init__(self, f, m):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(12)
        mini = QLabel()
        mini.setFixedSize(128, 72)
        mini.setAlignment(Qt.AlignCenter)
        mini.setStyleSheet("background:#000;border-radius:6px;color:#5b6670;font-size:12px")
        if m and m.get("miniatura") and os.path.exists(m["miniatura"]):
            mini.setPixmap(QPixmap(m["miniatura"]).scaled(128, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            mini.setText("…")
        lay.addWidget(mini)
        tekst = QVBoxLayout()
        tekst.setSpacing(2)
        kiedy = A.ladna_data(m["nagrany"]) if m and m.get("nagrany") else \
            A.ladna_data(time.strftime("%Y-%m-%d %H:%M", time.localtime(f["czas"])))
        dl = f" · {A.czas_mmss(m['sekundy'])}" if m and m.get("sekundy") else ""
        t1 = QLabel(f"{kiedy}{dl}")
        t1.setStyleSheet(f"font-size:17px;font-weight:700;color:{TEKST};background:transparent")
        roz = f" · {m['szer']}×{m['wys']}" if m and m.get("szer") else ""
        zrodlo = "z telefonu / pliku" if f["zrodlo"] == "przesłany" else "z kamery łazika"
        nazwa = f["nazwa"].split("_", 2)[-1] if f["zrodlo"] == "przesłany" else f["nazwa"]
        t2 = QLabel(f"{nazwa} · {zrodlo}{roz} · {f['rozmiar_mb']:.0f} MB")
        t2.setStyleSheet("font-size:13px;color:#b5c0c7;background:transparent")
        t3 = QLabel("✓ raport gotowy" if f["ma_raport"] else "jeszcze nie analizowany")
        t3.setStyleSheet(f"font-size:13px;font-weight:600;color:{ZIELONY if f['ma_raport'] else SZARY};background:transparent")
        for t in (t1, t2, t3):
            tekst.addWidget(t)
        lay.addLayout(tekst, 1)


class Odtwarzacz(QWidget):
    """Podgląd filmu w aplikacji (bez dźwięku): pauza, suwak, krzyżyk."""

    def __init__(self, okno):
        super().__init__(okno)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background:#000;color:#e6ebee")
        self.cap, self.fps, self.n = None, 30.0, 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        gora = QHBoxLayout()
        self.tytul = QLabel()
        self.tytul.setStyleSheet("font-size:17px;font-weight:700")
        b_x = przycisk("✕", 52, rozmiar=22)
        b_x.clicked.connect(self.zamknij)
        gora.addWidget(self.tytul, 1)
        gora.addWidget(b_x)
        lay.addLayout(gora)
        self.obraz = QLabel()
        self.obraz.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.obraz, 1)
        dol = QHBoxLayout()
        self.b_graj = przycisk("❚❚", 64, rozmiar=20)
        self.b_graj.clicked.connect(self.przelacz)
        self.suwak = QSlider(Qt.Horizontal)
        self.suwak.setStyleSheet(
            "QSlider::groove:horizontal{height:10px;background:#2a333a;border-radius:5px}"
            f"QSlider::sub-page:horizontal{{background:{AKCENT};border-radius:5px}}"
            "QSlider::handle:horizontal{width:30px;margin:-11px 0;background:#ffffff;border-radius:15px}")
        self.suwak.sliderMoved.connect(self.skocz)
        self.czas = QLabel()
        self.czas.setStyleSheet("font-size:15px;font-family:monospace")
        dol.addWidget(self.b_graj)
        dol.addWidget(self.suwak, 1)
        dol.addWidget(self.czas)
        lay.addLayout(dol)
        self.t = QTimer(self, timeout=self.klatka)
        self.hide()

    def otworz(self, f):
        self.cap = cv2.VideoCapture(f["sciezka"])
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.n = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.suwak.setRange(0, max(self.n - 1, 1))
        self.tytul.setText(f["nazwa"])
        self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        self.graj(True)

    def graj(self, wl):
        self.b_graj.setText("❚❚" if wl else "▶")
        if wl:
            self.t.start(int(1000 / min(self.fps, 30)))
        else:
            self.t.stop()

    def przelacz(self):
        self.graj(not self.t.isActive())

    def skocz(self, nr):
        if self.cap is not None:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, nr)
            if not self.t.isActive():
                self.klatka()

    def klatka(self):
        if self.cap is None:
            return
        ok, k = self.cap.read()
        if not ok:
            self.graj(False)
            return
        nr = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
        if not self.suwak.isSliderDown():
            self.suwak.setValue(nr)
        self.czas.setText(f"{A.czas_mmss(nr / self.fps)} / {A.czas_mmss(self.n / self.fps)}")
        self.obraz.setPixmap(QPixmap.fromImage(bgr_na_qimage(k)).scaled(
            self.obraz.size(), Qt.KeepAspectRatio, Qt.FastTransformation))

    def zamknij(self):
        self.graj(False)
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.hide()


class Okno(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Łazik: analiza wideo")
        self.setStyleSheet(f"background:{TLO};color:{TEKST}")
        self.system = System()
        self.analiza = None
        self._lista_klucz = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 10, 12, 12)
        lay.setSpacing(8)
        gora = QHBoxLayout()
        tytul = QLabel("Łazik · analiza wideo")
        tytul.setStyleSheet("font-size:22px;font-weight:700")
        self.b_zamknij = przycisk("✕", 52, rozmiar=22)
        self.b_zamknij.clicked.connect(self.close)
        gora.addWidget(tytul)
        gora.addStretch()
        gora.addWidget(self.b_zamknij)
        lay.addLayout(gora)
        self.strony = QStackedWidget()
        lay.addWidget(self.strony, 1)

        # --- strona 0: filmy + wysyłanie + opcje ---
        s0 = QWidget()
        l0 = QHBoxLayout(s0)
        l0.setContentsMargins(0, 0, 0, 0)
        l0.setSpacing(14)
        lewa = QVBoxLayout()
        self.lista = QListWidget()
        self.lista.setStyleSheet(
            "QListWidget{background:#161c21;border:none;border-radius:10px;font-size:15px;outline:0}"
            "QListWidget::item{border-bottom:1px solid #2a333a;border-left:6px solid transparent}"
            f"QListWidget::item:selected{{background:#3a4a56;border-left:6px solid {AKCENT}}}")
        self.lista.setFocusPolicy(Qt.NoFocus)
        self.lista.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        QScroller.grabGesture(self.lista.viewport(), QScroller.LeftMouseButtonGesture)
        self.lista.itemSelectionChanged.connect(self._zaznaczone)
        self.lista.itemDoubleClicked.connect(lambda _: self.podglad_filmu())
        lewa.addWidget(self.lista, 1)
        rd = QHBoxLayout()
        self.b_dodaj = przycisk("Dodaj z pliku / pendrive’a", wys=40, rozmiar=14)
        self.b_dodaj.clicked.connect(self.dodaj_z_pliku)
        self.b_raport = przycisk("Otwórz raport", wys=40, rozmiar=14)
        self.b_raport.clicked.connect(self.otworz_raport)
        self.b_podglad = przycisk("▶ Podgląd", wys=40, rozmiar=14)
        self.b_podglad.clicked.connect(self.podglad_filmu)
        rd.addWidget(self.b_podglad)
        rd.addWidget(self.b_raport)
        rd.addWidget(self.b_dodaj)
        lewa.addLayout(rd)
        l0.addLayout(lewa, 1)

        prawa = QWidget()
        prawa.setFixedWidth(330)
        prawa.setStyleSheet(f"background:{PANEL};border-radius:10px")
        pr = QVBoxLayout(prawa)
        pr.setContentsMargins(14, 12, 14, 12)
        pr.setSpacing(8)
        rq = QHBoxLayout()
        self.qr = Klikalny(self.przelacz_qr)
        self.qr.setFixedSize(120, 120)
        prawa_qr = QVBoxLayout()
        prawa_qr.setSpacing(4)
        opis_qr = QLabel("<b>Wyślij film z telefonu</b><br>Zeskanuj kod aparatem telefonu.")
        opis_qr.setWordWrap(True)
        opis_qr.setStyleSheet("font-size:13px;background:transparent")
        rodzaj = QHBoxLayout()
        rodzaj.setSpacing(6)
        self.qr_ikona = QLabel()
        self.qr_ikona.setFixedSize(26, 26)
        self.qr_ikona.setStyleSheet("background:transparent")
        self.qr_nazwa = QLabel()
        self.qr_nazwa.setWordWrap(True)
        self.qr_nazwa.setStyleSheet(f"font-size:13px;font-weight:700;color:{AKCENT};background:transparent")
        rodzaj.addWidget(self.qr_ikona)
        rodzaj.addWidget(self.qr_nazwa, 1)
        przel = QLabel("Dotknij kodu, żeby przełączyć.")
        przel.setWordWrap(True)
        przel.setStyleSheet(f"font-size:12px;color:{SZARY};background:transparent")
        prawa_qr.addWidget(opis_qr)
        prawa_qr.addLayout(rodzaj)
        prawa_qr.addWidget(przel)
        prawa_qr.addStretch()
        rq.addWidget(self.qr)
        rq.addLayout(prawa_qr, 1)
        pr.addLayout(rq)
        self.adresy = QLabel()
        self.adresy.setWordWrap(True)
        self.adresy.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.adresy.setStyleSheet(f"color:{SZARY};font-size:12px;background:transparent")
        pr.addWidget(self.adresy)
        co = QLabel("Co zrobić z filmem:")
        co.setStyleSheet("font-size:15px;font-weight:600;background:transparent;margin-top:4px")
        pr.addWidget(co)
        self.o_notatki = przycisk("Notatki: osoby, twarze, przedmioty", wys=38, rozmiar=13)
        self.o_ai = przycisk("Opis AI (zaawansowany, wolny)", wys=38, rozmiar=13)
        self.o_3d = przycisk("Skan 3D", wys=38, rozmiar=13)
        for b in (self.o_notatki, self.o_ai, self.o_3d):
            b.setCheckable(True)
            b.setStyleSheet(b.styleSheet() + f"QPushButton:checked{{background:{ZIELONY};color:#0b0b0b}}")
            pr.addWidget(b)
        self.o_notatki.setChecked(True)
        self.stan_ai = QLabel()
        self.stan_ai.setWordWrap(True)
        self.stan_ai.setStyleSheet(f"color:{SZARY};font-size:12px;background:transparent")
        pr.addWidget(self.stan_ai)
        pr.addStretch()
        self.b_analizuj = przycisk("Analizuj wybrany film", wys=48, rozmiar=16)
        self.b_analizuj.setStyleSheet(self.b_analizuj.styleSheet() + f"QPushButton{{background:{ZOLTY};color:#111}}")
        self.b_analizuj.clicked.connect(self.analizuj)
        pr.addWidget(self.b_analizuj)
        l0.addWidget(prawa)
        self.strony.addWidget(s0)

        # --- strona 1: postęp ---
        s1 = QWidget()
        l1 = QHBoxLayout(s1)
        l1.setContentsMargins(0, 0, 0, 0)
        l1.setSpacing(16)
        lp = QVBoxLayout()
        self.podglad = QLabel()
        self.podglad.setFixedSize(600, 250)
        self.podglad.setAlignment(Qt.AlignCenter)
        self.podglad.setStyleSheet("background:#000;border-radius:8px")
        lp.addWidget(self.podglad)
        self.pasek = QProgressBar()
        self.pasek.setRange(0, 1000)
        self.pasek.setTextVisible(False)
        self.pasek.setFixedHeight(16)
        self.pasek.setStyleSheet(f"QProgressBar{{background:#2a333a;border:none;border-radius:8px}}"
                                 f"QProgressBar::chunk{{background:{ZIELONY};border-radius:8px}}")
        lp.addWidget(self.pasek)
        self.t_krok = QLabel()
        self.t_krok.setStyleSheet("font-size:18px;font-weight:700")
        lp.addWidget(self.t_krok)
        self.t_szczeg = QLabel()
        self.t_szczeg.setWordWrap(True)
        self.t_szczeg.setStyleSheet(f"color:{SZARY};font-size:14px")
        lp.addWidget(self.t_szczeg)
        self.t_wynik = QLabel()
        self.t_wynik.setWordWrap(True)
        self.t_wynik.setStyleSheet("font-size:14px;background:#1f272d;border-radius:8px;padding:8px")
        self.t_wynik.hide()
        lp.addWidget(self.t_wynik)
        lp.addStretch()
        l1.addLayout(lp, 1)
        pp = QVBoxLayout()
        pp.setSpacing(10)
        self.w_cpu, self.w_ram, self.w_hailo = Wiersz("Procesor"), Wiersz("RAM"), Wiersz("Hailo")
        self.w_zas = Wiersz("Zasilanie", pasek=False)
        for w in (self.w_cpu, self.w_ram, self.w_hailo, self.w_zas):
            pp.addWidget(w)
        pp.addStretch()
        self.b_przerwij, self.b_wynik, self.b_lista = przycisk("Przerwij"), przycisk("Otwórz raport"), przycisk("Do listy")
        self.b_przerwij.clicked.connect(self.przerwij)
        self.b_wynik.clicked.connect(lambda: otworz_w_przegladarce(self.analiza.odczyt()["wynik"]))
        self.b_lista.clicked.connect(self.do_listy)
        for b in (self.b_przerwij, self.b_wynik, self.b_lista):
            pp.addWidget(b)
        op = QWidget()
        op.setFixedWidth(290)
        op.setLayout(pp)
        l1.addWidget(op)
        self.strony.addWidget(s1)

        self.dymek = QLabel(self)
        self.dymek.setStyleSheet(f"background:{ZOLTY};color:#111;font-size:15px;font-weight:600;border-radius:8px;padding:8px 14px")
        self.dymek.hide()
        self._dymek_do = 0.0

        kod = serwer_wideo.kod_dostepu()
        lan, ts = adres_lan(), adres_tailscale()
        self.kody_qr = []  # (ikona, nazwa, adres)
        if lan:
            self.kody_qr.append((ikona_dom(), "Sieć domowa (WiFi)", f"http://{lan}:{PORT}/?t={kod}"))
        if ts:
            self.kody_qr.append((ikona_tailscale(), "Tailscale (z każdego miejsca)", f"http://{ts}:{PORT}/?t={kod}"))
        if not self.kody_qr:
            self.kody_qr.append((ikona_dom(), "Adres lokalny", f"http://rpi-5-1:{PORT}/?t={kod}"))
        self._qr_nr = -1
        self.przelacz_qr()

        self.odtwarzacz = Odtwarzacz(self)
        self._meta = {}               # ścieżka → metadane (miniatura, data, długość)
        self._meta_kolejka = []
        self._meta_nowe = False
        threading.Thread(target=self._licz_metadane, daemon=True).start()
        # lista odświeża się sama: od razu, gdy w folderach coś się zmieni, i dodatkowo co 2 s
        self.watcher = QFileSystemWatcher(self)
        for k in (A.FILMY, A.RAPORTY, A.P.NAGRANIA):
            os.makedirs(k, exist_ok=True)
            self.watcher.addPath(k)
        self.watcher.directoryChanged.connect(lambda _: QTimer.singleShot(300, self.odswiez_liste))

        self.t_lista = QTimer(self, timeout=self.odswiez_liste)
        self.t_lista.start(2000)
        self.t_post = QTimer(self, timeout=self.odswiez_postep)
        self.t_post.start(300)
        self.t_stat = QTimer(self, timeout=self.system.odswiez)
        self.t_stat.start(1000)
        self.odswiez_liste()
        self._stan_ai()

    # --- lista filmów ---
    def przelacz_qr(self):
        self._qr_nr = (self._qr_nr + 1) % len(self.kody_qr)
        ikona, nazwa, adres = self.kody_qr[self._qr_nr]
        self.qr.setPixmap(obraz_qr(adres, 120))
        self.qr_ikona.setPixmap(ikona)
        self.qr_nazwa.setText(nazwa)
        self.adresy.setText(adres)

    def _licz_metadane(self):
        """Wątek w tle: miniatury i dane filmów (ffprobe + jedna klatka), żeby lista się nie zacinała."""
        while True:
            if self._meta_kolejka:
                sciezka = self._meta_kolejka.pop(0)
                try:
                    self._meta[sciezka] = A.metadane(sciezka)
                except Exception:
                    self._meta[sciezka] = {}
                self._meta_nowe = True
            else:
                time.sleep(0.3)

    def odswiez_liste(self):
        filmy = A.lista_filmow()
        for f in filmy:
            if f["sciezka"] not in self._meta and f["sciezka"] not in self._meta_kolejka:
                self._meta_kolejka.append(f["sciezka"])
        klucz = tuple((f["sciezka"], f["ma_raport"], round(f["rozmiar_mb"])) for f in filmy)
        if klucz == self._lista_klucz and not self._meta_nowe:
            return
        self._meta_nowe = False
        wybrany = self._wybrany()["sciezka"] if self._wybrany() else None
        nowe = self._lista_klucz is not None and len(klucz) > len(self._lista_klucz)
        self._lista_klucz = klucz
        self.lista.clear()
        for f in filmy:
            it = QListWidgetItem()
            it.setData(Qt.UserRole, f)
            it.setSizeHint(QSize(100, 88))
            self.lista.addItem(it)
            self.lista.setItemWidget(it, WierszFilmu(f, self._meta.get(f["sciezka"])))
            if f["sciezka"] == wybrany and not nowe:
                self.lista.setCurrentItem(it)
        if not filmy:
            it = QListWidgetItem("Brak filmów. Wyślij film z telefonu (kod QR obok), dodaj z pliku "
                                 "albo nagraj w „Łazik: wizja” (tryb Przestrzeń).")
            it.setFlags(Qt.NoItemFlags)
            self.lista.addItem(it)
        elif nowe or self.lista.currentItem() is None:
            self.lista.setCurrentRow(0)  # nowy film (najnowszy jest na górze) od razu zaznaczony
            if nowe:
                self.komunikat("Nowy film na liście.")
        self._zaznaczone()

    def podglad_filmu(self):
        f = self._wybrany()
        if f:
            self.odtwarzacz.otworz(f)

    def _wybrany(self):
        it = self.lista.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _zaznaczone(self):
        f = self._wybrany()
        self.b_analizuj.setEnabled(bool(f))
        self.b_podglad.setEnabled(bool(f))
        self.b_raport.setEnabled(bool(f and f["ma_raport"]))

    def _stan_ai(self):
        dziala, ma_model, kom = A.ollama_gotowa()
        self.stan_ai.setText(f"Opis AI: {kom}." if not (dziala and ma_model) else
                             f"Opis AI: {kom}. Liczy na procesorze Pi 5 (nie na Hailo): ok. 2 min na klatkę, do 8 klatek, "
                             "czyli kilkanaście minut na film.")

    def dodaj_z_pliku(self):
        pliki, _ = QFileDialog.getOpenFileNames(self, "Wybierz filmy", "/media",
                                                "Filmy (*.mp4 *.mov *.m4v *.avi *.mkv *.webm *.3gp)")
        if not pliki:
            return
        os.makedirs(A.FILMY, exist_ok=True)
        for p in pliki:
            shutil.copy(p, os.path.join(A.FILMY, time.strftime("%Y-%m-%d_%H%M%S_") + os.path.basename(p).replace(" ", "_")))
        self._lista_klucz = None
        self.odswiez_liste()
        self.komunikat(f"Dodano {len(pliki)} film(y).")

    def otworz_raport(self):
        f = self._wybrany()
        if f and f["ma_raport"]:
            otworz_w_przegladarce(os.path.join(f["raport"], "raport.html"))

    # --- analiza ---
    def analizuj(self):
        f = self._wybrany()
        if not f:
            return
        if not (self.o_notatki.isChecked() or self.o_ai.isChecked() or self.o_3d.isChecked()):
            self.komunikat("Wybierz co najmniej jedną rzecz: notatki, opis AI albo skan 3D.")
            return
        self.analiza = A.AnalizaWideo(f["sciezka"], self.o_notatki.isChecked(), self.o_ai.isChecked(),
                                      self.o_3d.isChecked())
        self.analiza.start()
        self.t_wynik.hide()
        self.podglad.clear()
        self.b_przerwij.setEnabled(True)
        self.b_wynik.setEnabled(False)
        self.b_lista.setEnabled(False)
        self.b_zamknij.setEnabled(False)
        self.strony.setCurrentIndex(1)

    def przerwij(self):
        if self.analiza and self.analiza.is_alive():
            self.analiza.zatrzymaj()
            self.t_krok.setText("Przerywam…")

    def do_listy(self):
        self.strony.setCurrentIndex(0)
        self.b_zamknij.setEnabled(True)
        self._lista_klucz = None
        self.odswiez_liste()
        self._stan_ai()

    def odswiez_postep(self):
        if self.dymek.isVisible() and time.monotonic() > self._dymek_do:
            self.dymek.hide()
        if self.strony.currentIndex() != 1 or self.analiza is None:
            return
        sy = self.system
        t_cpu = f" · {sy.temp:.0f} °C" if sy.temp is not None else ""
        self.w_cpu.ustaw(f"{sy.cpu:.0f}%{t_cpu}", sy.cpu, kolor=kolor_temp(sy.temp, 70, 80))
        self.w_ram.ustaw(f"{sy.ram_uzyte:.1f} / {sy.ram_razem:.1f} GB", sy.ram_proc)
        self.w_zas.ustaw(sy.zasilanie, kolor=ZIELONY if sy.zasilanie == "OK" else ZOLTY)
        st = self.analiza.odczyt()
        trwa = self.analiza.is_alive()
        ht = st["hailo_temp"]
        hp = st["hailo_proc"] if trwa and st["etap"] in ("notatki", "skan") else 0.0
        self.w_hailo.ustaw(f"{hp:.0f}%" + (f" · {ht:.0f} °C" if ht is not None else ""), hp, kolor=kolor_temp(ht))
        razem = max(st["razem"], 1)
        self.pasek.setValue(int(1000 * min(st["gotowe"], razem) / razem))
        self.t_krok.setText(st["krok"] or "Przygotowuję…")
        zost = st["zostalo"]
        czesci = []
        if st["etap"] in ("notatki", "skan"):
            czesci.append(f"{st['gotowe']} / {st['razem']} klatek filmu ({100 * st['gotowe'] / razem:.0f}%) · "
                          f"{st['kl_s']:.0f} kl/s")
        elif st["etap"] == "opis":
            czesci.append(f"{st['gotowe']} / {st['razem'] - 1} klatek kluczowych opisanych")
        if zost and trwa:
            czesci.append(f"zostało ~{int(zost) // 60} min {int(zost) % 60} s")
        if self.analiza.opcje["notatki"] and st["etap"] != "skan":
            czesci.append(f"\nTwarze: {st['osoby_pewne']} różnych (wszystkich grup {st['osoby']}) · "
                          f"najwięcej osób naraz: {st['naraz']}")
            if st["obiekty"]:
                czesci.append("\nW kadrze: " + ", ".join(f"{n} (maks. {k})" for n, k in st["obiekty"]))
        self.t_szczeg.setText(" · ".join(c for c in czesci if not c.startswith("\n")) +
                              "".join(c for c in czesci if c.startswith("\n")))
        with self.analiza.lock:
            pg = self.analiza.podglad
        if pg is not None:
            self.podglad.setPixmap(QPixmap.fromImage(bgr_na_qimage(pg[0])).scaled(
                self.podglad.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if not trwa and self.b_przerwij.isEnabled():
            self.b_przerwij.setEnabled(False)
            self.b_lista.setEnabled(True)
            self.b_zamknij.setEnabled(True)
            if st["etap"] == "gotowe":
                self.pasek.setValue(1000)
                self.t_krok.setText("Gotowe: raport zapisany")
                self.t_wynik.setText((st["podsumowanie"] or "Raport z notatkami jest gotowy.") +
                                     f"\n\nPlik: {st['wynik']}\nNa telefonie: lista „Filmy na Pi” → „Raport”.")
                self.b_wynik.setEnabled(True)
            elif st["etap"] == "błąd":
                self.t_krok.setText("Błąd analizy")
                self.t_wynik.setText(st["blad"] or "")
            else:
                self.t_krok.setText("Przerwano")
                self.t_wynik.setText("Analiza przerwana, raport nie został zapisany.")
            self.t_wynik.show()

    def komunikat(self, tekst, sekundy=4.0):
        self.dymek.setText(tekst)
        self.dymek.adjustSize()
        self.dymek.move(18, self.height() - self.dymek.height() - 16)
        self.dymek.show()
        self.dymek.raise_()
        self._dymek_do = time.monotonic() + sekundy

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and self.odtwarzacz.isVisible():
            self.odtwarzacz.zamknij()
        elif e.key() == Qt.Key_Escape and self.b_zamknij.isEnabled():
            self.close()

    def resizeEvent(self, e):
        if self.odtwarzacz.isVisible():
            self.odtwarzacz.setGeometry(self.rect())
        super().resizeEvent(e)

    def closeEvent(self, e):
        if self.analiza and self.analiza.is_alive():
            self.analiza.zatrzymaj()
            self.analiza.join(timeout=5)
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    okno = Okno()
    okno.showFullScreen()
    kod = app.exec_()
    os._exit(kod)  # bez sprzątania HailoRT przy wyjściu (w tej wersji potrafi się wysypać)


if __name__ == "__main__":
    main()
