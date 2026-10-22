#!/usr/bin/env python3
"""
Telefon serwerka (usługa serwerek-telefon): rozmowy głosowe z właścicielem przez Linphone (SIP, sip.linphone.org).
  - Antek dzwoni do Pi (adres SIP konta Pi) -> Pi odbiera, słucha, odpowiada głosem.
  - Pi dzwoni do Antka: zlecenia z ~/bot/telefon/kolejka/*.json (bot: przycisk 📞, czerwony alarm bez reakcji,
    przypomnienie z telefonem); wynik do ~/bot/telefon/wyniki/*.json (bot pisze o nim w Telegramie).
Rozmowa: nagrywanie rozmowy do pliku (AudioMediaRecorder), wykrywanie końca wypowiedzi po energii dźwięku (VAD),
rozpoznanie mowy whisper.cpp na Pi -> Claude (ta sama sesja i pamięć co czat, bot serwerek_bot.claude_odpowiedz) ->
mowa Piper na Pi -> odtworzenie w rozmowie. Wszystkie wywołania pjsua2 tylko w głównym wątku (kolejka AKCJE).
Czat Linphone (wiadomości SIP MESSAGE, także w kopercie message/cpim): Antek pisze jak w Telegramie; proste komendy
(stan, sprawdziany, zadania, ścieżka, minecraft, „todo …”) i reszta do Claude (ta sama sesja i pamięć, kanał „linphone”).
Bot może też wysłać wiadomość na Linphone: plik JSON {"tekst": …, "glos": true|false} w ~/bot/telefon/czat/.
Konfiguracja: /etc/serwerek-bot/sip.env (SIP_UZYTKOWNIK, SIP_HASLO, SIP_DOMENA, SIP_WLASCICIEL), podawana przez systemd.
Bez konfiguracji usługa czeka i odpowiada na zlecenia wynikiem „brak_konfiguracji”.
"""
import json
import os
import re
import queue
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/tonyg/bot")
sys.path.insert(0, "/home/tonyg/glos")
import glos                     # noqa: E402
import pamiec                   # noqa: E402

KAT = Path("/home/tonyg/bot/telefon")
KOLEJKA, WYNIKI, CZAT = KAT / "kolejka", KAT / "wyniki", KAT / "czat"
UZYT, HASLO = os.environ.get("SIP_UZYTKOWNIK", ""), os.environ.get("SIP_HASLO", "")
DOMENA = os.environ.get("SIP_DOMENA", "sip.linphone.org")
WLASCICIEL = os.environ.get("SIP_WLASCICIEL", "")       # np. sip:antek@sip.linphone.org
HZ = 16000
RAMKA = HZ * 2 // 50                                    # 20 ms, 16 bit mono
CZEKAJ_PO_ODEBRANIU = 2.5                               # s: Pi dzwoni -> Antek odbiera -> 2,5 s ciszy -> powitanie
CZAS_DZWONIENIA = 60                                    # s: tyle Pi próbuje dzwonić, potem „nie odebrał”
PONOW = []          # [(kiedy, zlecenie)]: iPhone czasem od razu odrzuca (603), np. gdy Linphone jest otwarty; dzwonimy znowu
MAX_ROZMOWA = 20 * 60
CISZA_KONIEC = 90                                       # s ciszy: rozłącz
POZEGNANIA = ("do widzenia", "rozłącz", "rozlacz", "koniec rozmowy", "na razie", "pa pa", "cześć to wszystko")

AKCJE = queue.Queue()        # (funkcja, argumenty) do wykonania w głównym wątku pjsua2


def od_wlasciciela(uri):
    """czy adres SIP (np. "Antek" <sip:za_kolaz@sip.linphone.org>) należy do właściciela: porównanie nazwy użytkownika"""
    import re
    u = lambda x: (re.search(r"sips?:([^@;>]+)@", x or "") or [None, ""])[1].lower()
    return bool(WLASCICIEL) and u(uri) == u(WLASCICIEL) != ""


def log(t):
    print(time.strftime("%H:%M:%S ") + t, flush=True)


def wynik(**dane):
    WYNIKI.mkdir(parents=True, exist_ok=True)
    p = WYNIKI / f"{time.time():.3f}.json"
    p.with_suffix(".tmp").write_text(json.dumps(dane, ensure_ascii=False), encoding="utf-8")
    os.replace(p.with_suffix(".tmp"), p)


def czas_wav(p):
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


# ---------------------------------------------------------------- wykrywanie wypowiedzi (energia dźwięku)
class Sluchacz:
    """czyta rosnący plik nagrania rozmowy i oddaje kolejne wypowiedzi (bytes PCM 16 kHz)"""

    def __init__(self, plik):
        self.plik, self.poz, self.tlo = Path(plik), 44, 300.0

    def pomin_do_konca(self):
        try:
            self.poz = max(44, self.plik.stat().st_size // 2 * 2)
        except OSError:
            pass

    def czytaj(self):
        try:
            with open(self.plik, "rb") as f:
                f.seek(self.poz)
                d = f.read()
        except OSError:
            return b""
        d = d[:len(d) // RAMKA * RAMKA]
        self.poz += len(d)
        return d

    def wypowiedz(self, koniec_rozmowy, limit_ciszy):
        """czeka na wypowiedź: start po 3 głośnych ramkach, koniec po 0,9 s ciszy; None = cisza za długo / koniec"""
        mowa, cisza, glosne, start = bytearray(), 0, 0, time.time()
        while not koniec_rozmowy.is_set():
            d = self.czytaj()
            if not d:
                time.sleep(0.1)
                if not mowa and time.time() - start > limit_ciszy:
                    return None
                continue
            for i in range(0, len(d), RAMKA):
                r = np.frombuffer(d[i:i + RAMKA], dtype=np.int16).astype(np.float32)
                rms = float(np.sqrt(np.mean(r * r))) if len(r) else 0.0
                prog = max(500.0, self.tlo * 3)
                if not mowa:
                    self.tlo = 0.97 * self.tlo + 0.03 * rms if rms < prog else self.tlo
                    glosne = glosne + 1 if rms > prog else 0
                    if glosne >= 3:
                        mowa.extend(d[max(0, i - 10 * RAMKA):i + RAMKA])
                    continue
                mowa.extend(d[i:i + RAMKA])
                cisza = cisza + 1 if rms < prog * 0.7 else 0
                if cisza >= 45 or len(mowa) > HZ * 2 * 30:          # 0,9 s ciszy albo 30 s mówienia
                    return bytes(mowa) if len(mowa) > HZ * 2 * 0.4 else self.wypowiedz(koniec_rozmowy, limit_ciszy)
        return None


# ---------------------------------------------------------------- rozmowa (wątek roboczy)
class Rozmowa:
    def __init__(self, polaczenie, kierunek, powitanie, zlecenie=None):
        self.p, self.kierunek, self.powitanie, self.zlecenie = polaczenie, kierunek, powitanie, zlecenie or {}
        self.koniec = threading.Event()
        self.start = time.time()
        self.zapis = []
        self.tmp = Path(tempfile.mkdtemp(prefix="rozmowa-", dir="/tmp"))
        self.nagranie = self.tmp / "rozmowa.wav"
        self.przygotowanie = None
        if kierunek == "od Pi" and powitanie:
            self.przygotowanie = threading.Thread(target=self.przygotuj, args=(powitanie,), daemon=True)
            self.przygotowanie.start()

    def przygotuj(self, tekst):
        """synteza z wyprzedzeniem (np. powitanie, gdy telefon jeszcze dzwoni)"""
        wav = self.tmp / f"gotowe-{abs(hash(tekst))}.wav"
        try:
            glos.powiedz(tekst, wav.with_suffix(".tmp.wav"), czestotliwosc=HZ)
            os.replace(wav.with_suffix(".tmp.wav"), wav)
        except Exception as ex:
            log(f"Piper (z wyprzedzeniem): {ex}")

    def mow(self, tekst):
        """synteza (Piper) i odtworzenie w rozmowie; czeka do końca wypowiedzi"""
        self.zapis.append(f"Pi: {tekst}")
        wav = self.tmp / f"gotowe-{abs(hash(tekst))}.wav"
        for _ in range(100):                    # synteza z wyprzedzeniem jeszcze trwa: poczekaj na nią (max 10 s)
            if wav.exists() or not self.przygotowanie or not self.przygotowanie.is_alive():
                break
            time.sleep(0.1)
        if not wav.exists():
            wav = self.tmp / f"mowa-{time.time():.3f}.wav"
            try:
                glos.powiedz(tekst, wav, czestotliwosc=HZ)
            except Exception as ex:
                log(f"Piper: {ex}")
                return
        gotowe = threading.Event()
        AKCJE.put((graj, (self.p, wav, gotowe)))
        gotowe.wait(10)
        self.koniec.wait(czas_wav(wav) + 0.3)

    def praca(self):
        try:
            pj.Endpoint.instance().libRegisterThread("rozmowa")     # wymagane przez pjlib w każdym wątku, który go dotyka
            import serwerek_bot as bot
            s = Sluchacz(self.nagranie)
            if self.kierunek == "od Pi":        # czas na przełączenie na głośnomówiący, zanim Pi zacznie mówić
                self.koniec.wait(CZEKAJ_PO_ODEBRANIU)
                if self.koniec.is_set():
                    return
            self.mow(self.powitanie)
            s.pomin_do_konca()
            while not self.koniec.is_set() and time.time() - self.start < MAX_ROZMOWA:
                pcm = s.wypowiedz(self.koniec, CISZA_KONIEC)
                if self.koniec.is_set():
                    break
                if pcm is None:
                    self.mow("Nic nie słyszę, więc się rozłączam. Napisz albo zadzwoń, gdy będziesz potrzebować.")
                    break
                wav = self.tmp / "wypowiedz.wav"
                with wave.open(str(wav), "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(HZ)
                    w.writeframes(pcm)
                AKCJE.put((graj, (self.p, CHWILA, threading.Event())))         # „mhm”, żeby było wiadomo, że słucha
                tekst = glos.rozpoznaj(wav, dokladnie=False, limit=60)
                if not tekst:
                    s.pomin_do_konca()
                    continue
                self.zapis.append(f"Ty: {tekst}")
                log(f"Antek: {tekst}")
                tid = self.zlecenie.get("todo_id")
                if tid and not re.search(r"\bnie\s+(\w+\s+)?(zrobi|odhacz|skończ|skoncz|załatw|zalatw)", tekst.lower()) and re.search(r"\b(odhacz|odhaczon|odchacz|odhaczy|zrobion|zrobił|zrobil|gotowe|załatwion|zalatwion|wykonan|skończon|skonczon)\w*", tekst.lower()):
                    pamiec.zapisz("antek", "telefon", tekst)
                    odp = bot.callback_zadania(f"todo_ok:{tid}")
                    self.zlecenie.pop("todo_id", None)
                    self.mow("Odhaczone." if odp.startswith("✅ Zrobione:") else "Odhaczone. " + odp.replace("✅ Zrobione. ", ""))
                    pamiec.zapisz("bot", "telefon", f"Odhaczone przez telefon: {odp}")
                    s.pomin_do_konca()
                    continue
                if (odp_m := bot.komenda_miejsca(tekst) or bot.komenda_budzik(tekst) or bot.poczta.reakcja(tekst)) is not None:
                    pamiec.zapisz("antek", "telefon", tekst)
                    pamiec.zapisz("bot", "telefon", odp_m)
                    self.mow(odp_m)
                    s.pomin_do_konca()
                    continue
                if any(x in tekst.lower() for x in POZEGNANIA):
                    pamiec.zapisz("antek", "telefon", tekst)
                    self.mow("Na razie, trzymaj się!")
                    break
                try:
                    odp, akcje = bot.claude_odpowiedz(tekst, "telefon", pisze=False)
                except Exception as ex:
                    odp, akcje = f"Coś poszło nie tak po mojej stronie: {ex}. Spróbuj powtórzyć.", []
                pamiec.zapisz("claude", "telefon", odp)
                for a in akcje:
                    bot.zapytaj(a, " (proponuje Claude podczas rozmowy)")
                if akcje:
                    odp += " Wysłałem Ci też przycisk do potwierdzenia w Telegramie."
                self.mow(odp)
                s.pomin_do_konca()
        except Exception as ex:
            log(f"rozmowa: {type(ex).__name__}: {ex}")
        finally:
            AKCJE.put((rozlacz, (self.p,)))

    def zakonczona(self):
        self.koniec.set()
        trwala = int(time.time() - self.start)
        if self.zapis:
            wynik(stan="rozmowa", kierunek=self.kierunek, czas=f"{trwala // 60} min {trwala % 60} s", zapis="\n".join(self.zapis))
        import shutil
        threading.Timer(30, shutil.rmtree, args=(self.tmp, True)).start()


# ---------------------------------------------------------------- pjsua2 (tylko w głównym wątku)
import pjsua2 as pj         # noqa: E402

AKTYWNE = {}                # id połączenia -> obiekt Polaczenie (trzymamy referencje, inaczej Python je usunie)
ZAKONCZONE = []             # zakończone połączenia: usuwane dopiero w głównym wątku, gdy wątek rozmowy skończy pracę
GRACZE = []                 # odtwarzacze (też muszą żyć do końca odtwarzania)


class Polaczenie(pj.Call):
    def __init__(self, konto, call_id=pj.PJSUA_INVALID_ID, kierunek="do Pi", powitanie="", zlecenie=None):
        super().__init__(konto, call_id)
        self.rozmowa = Rozmowa(self, kierunek, powitanie, zlecenie)
        self.media = None
        self.rec = None
        self.utworzone = time.time()
        self.odebrane = False
        self.watek = None

    def onCallState(self, prm):
        ci = self.getInfo()
        log(f"połączenie {ci.id}: {ci.stateText}" + (f" ({ci.lastStatusCode} {ci.lastReason}, {ci.connectDuration.sec} s rozmowy)"
                                                      if ci.state == pj.PJSIP_INV_STATE_DISCONNECTED else ""))
        if ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
            self.odebrane = True
        if ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            if not self.odebrane and self.rozmowa.kierunek == "od Pi":
                z = self.rozmowa.zlecenie
                if ci.lastStatusCode in (408, 480, 486, 487, 503, 603) and time.time() + 8 - z.get("start", 0) < CZAS_DZWONIENIA:
                    PONOW.append((time.time() + 5, z))
                    log(f"odrzucone od razu ({ci.lastStatusCode}), dzwonię jeszcze raz za 5 s")
                else:
                    wynik(stan="nieodebrane", tekst=z.get("tekst", ""), powod=z.get("powod", ""),
                          **{k: z[k] for k in ("budzik", "proba", "todo_id") if k in z})
            self.rozmowa.zakonczona()
            ZAKONCZONE.append(AKTYWNE.pop(ci.id, self))

    def onCallMediaState(self, prm):
        ci = self.getInfo()
        for mi in ci.media:
            if mi.type == pj.PJMEDIA_TYPE_AUDIO and mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE:
                # Linphone po ICE odnawia media (UPDATE): pjsua tworzy nowy port w mostku, więc za każdym razem podpinamy
                # się do aktualnego; inaczej Pi mówi do starego portu i w słuchawce jest cisza
                self.media = self.getAudioMedia(mi.index)
                if self.rec is None:
                    self.rec = pj.AudioMediaRecorder()
                    self.rec.createRecorder(str(self.rozmowa.nagranie))
                self.media.startTransmit(self.rec)
                for _, g in GRACZE:             # to, co właśnie gra, też na nowy port
                    try:
                        g.startTransmit(self.media)
                    except pj.Error:
                        pass
                if self.watek is None:
                    self.watek = threading.Thread(target=self.rozmowa.praca, daemon=True)
                    self.watek.start()


def graj(p, wav, gotowe):
    try:
        if p.media is not None:
            g = pj.AudioMediaPlayer()
            g.createPlayer(str(wav), pj.PJMEDIA_FILE_NO_LOOP)
            g.startTransmit(p.media)
            GRACZE.append((time.time() + czas_wav(wav) + 2, g))
    except pj.Error as ex:
        log(f"graj: {ex.info()}")
    gotowe.set()


def rozlacz(p):
    try:
        p.hangup(pj.CallOpParam())
    except pj.Error:
        pass


class Konto(pj.Account):
    def __init__(self):
        super().__init__()
        self.zarejestrowane = False

    def onRegState(self, prm):
        ai = self.getInfo()
        self.zarejestrowane = ai.regIsActive
        log(f"rejestracja: {ai.regStatus} {ai.regStatusText} (aktywna: {ai.regIsActive})")
        zapisz_stan(self.zarejestrowane)

    def onInstantMessage(self, prm):
        if "rcs-ft-http" in (prm.msgBody + prm.contentType):       # wzór głosówki z Linphone (diagnostyka formatu)
            try:
                (KAT / "ostatni_plik_z_linphone.txt").write_text(f"{prm.contentType}\n\n{prm.msgBody}", encoding="utf-8")
            except OSError:
                pass
        w = tresc_wiadomosci(prm.msgBody, prm.contentType)
        if not w:
            return
        od = prm.fromUri
        rodzaj, wartosc = w
        if rodzaj == "plik" and not wartosc[1].startswith("audio"):
            if od_wlasciciela(od):
                AKCJE.put((wyslij_czat, ("Na razie rozumiem tylko tekst i wiadomości głosowe. Zdjęcia i pliki wyślij w Telegramie.",)))
            return
        if od_wlasciciela(od):
            log(f"czat od właściciela ({rodzaj}): {str(wartosc)[:80]}")
            threading.Thread(target=odpowiedz_czat, args=(wartosc[0] if rodzaj == "plik" else wartosc, "glos" if rodzaj == "plik" else "tekst"),
                             daemon=True).start()
        else:
            log(f"czat od obcego {od}: pomijam")
            wynik(stan="obcy_czat", od=od, tekst=(wartosc if rodzaj == "tekst" else "[plik]")[:300])

    def onIncomingCall(self, prm):
        p = Polaczenie(self, prm.callId, "do Pi", "Cześć, tu serwerek. Słucham.")
        ci = p.getInfo()
        od = ci.remoteUri
        AKTYWNE[ci.id] = p
        op = pj.CallOpParam()
        if WLASCICIEL and od_wlasciciela(od) and len(AKTYWNE) == 1:
            op.statusCode = 200
            p.answer(op)
            log(f"odbieram od {od}")
        else:
            op.statusCode = 603
            p.hangup(op)
            wynik(stan="obcy" if WLASCICIEL else "nieznany_wlasciciel", od=od)
            log(f"odrzucam {od}")


# ---------------------------------------------------------------- czat Linphone
FT_TYP = "application/vnd.gsma.rcs-ft-http+xml"         # plik w czacie Linphone (np. głosówka): XML z adresem pliku
FT_SERWER = "https://files.linphone.org/http-file-transfer-server/hft.php"


def tresc_wiadomosci(cialo, typ):
    """(rodzaj, wartość): ("tekst", tekst) albo ("plik", (url, typ_pliku)); None dla potwierdzeń i „pisze…”.
    Linphone zwykle opakowuje wiadomość w message/cpim (nagłówki CPIM, pusta linia, nagłówki MIME, pusta linia, treść)."""
    import re
    typ = (typ or "").lower()
    if "cpim" in typ:
        czesci = cialo.replace("\r\n", "\n").split("\n\n", 2)
        if len(czesci) < 3:
            return None
        m = re.search(r"content-type:\s*([^\n]+)", czesci[1], re.I)
        typ, cialo = (m.group(1).strip().lower() if m else "text/plain"), czesci[2]
    if "imdn" in typ or "iscomposing" in typ:
        return None
    if "rcs-ft-http" in typ:
        url = re.search(r'<data\s+url="([^"]+)"', cialo)
        ct = re.search(r"<content-type>([^<]+)</content-type>", cialo)
        return ("plik", (url.group(1), ct.group(1) if ct else "")) if url else None
    return ("tekst", cialo.strip()) if typ.startswith("text/plain") or not typ else None


def wyslij_glosowke(tekst):
    """odpowiedź jako głosówka w Linphone: Piper -> WAV -> serwer plików Linphone (link ważny 7 dni) -> wiadomość z plikiem"""
    import uuid
    import urllib.request
    import subprocess
    wav = Path(tempfile.mkdtemp(prefix="czat-", dir="/tmp")) / "odpowiedz.wav"
    glos.powiedz(tekst[:4000], wav, czestotliwosc=HZ)
    ms = int(czas_wav(wav) * 1000)
    # Linphone nagrywa i odtwarza głosówki jako Matroska audio (.mka) z Opusem, opisane jako audio/wav;voice-recording=yes
    mka = wav.with_suffix(".mka")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libopus", "-b:a", "32k", "-ar", "48000", "-ac", "1",
                    str(mka)], check=True, timeout=60)
    g = uuid.uuid4().hex
    cialo = (f"--{g}\r\nContent-Disposition: form-data; name=\"File\"; filename=\"voice-recording-{int(time.time())}.mka\"\r\n"
             f"Content-Type: audio/wav;voice-recording=yes\r\n\r\n").encode() + mka.read_bytes() + f"\r\n--{g}--\r\n".encode()
    req = urllib.request.Request(FT_SERWER, data=cialo, headers={"Content-Type": f"multipart/form-data; boundary={g}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        xml = r.read().decode("utf-8")
    import shutil
    shutil.rmtree(wav.parent, ignore_errors=True)
    # znaczniki głosówki Linphone: typ z voice-recording=yes i długość nagrania
    import re
    xml = re.sub(r"<content-type>[^<]*</content-type>", "<content-type>audio/wav;voice-recording=yes</content-type>", xml)
    xml = xml.replace('<file xmlns="urn:gsma:params:xml:ns:rcs:rcs:fthttp">',
                      '<file xmlns="urn:gsma:params:xml:ns:rcs:rcs:fthttp" xmlns:am="urn:gsma:params:xml:ns:rcs:rcs:rram">')
    xml = xml.replace("</content-type>", f"</content-type><am:playing-length>{ms}</am:playing-length>", 1)   # kolejność jak w Linphone
    return xml


def pobierz_glosowke(url):
    import urllib.request
    p = Path(tempfile.mkdtemp(prefix="czat-", dir="/tmp")) / "glosowka"
    with urllib.request.urlopen(url, timeout=60) as r:
        p.write_bytes(r.read())
    return p


CZAT_AKCJA = {}     # akcja czekająca na „tak” w czacie Linphone (Linphone nie ma przycisków): {"akcja", "t"}
POMOC_LINPHONE_KONIEC = ("\n\nW Linphone nie ma przycisków: gdy coś trzeba potwierdzić (kopia, Minecraft, przejrzane), "
                         "odpisz „tak” w ciągu 2 minut. Zdjęcia, PDF-y i lokalizację wysyłaj w Telegramie."
                         "\nPowiadomienia przychodzą tam, gdzie ostatnio pisałeś (gdy Linphone nie działa: Telegram); "
                         "„widzę” = nie dzwoń w sprawie alarmu, „to moje” = urządzenie z ostatniego powiadomienia o wejściu."
                         "\n\nZadania (przypomnienia przychodzą też tutaj):\n"
                         "✅ zrobione [nr] – ostatnie przypomnienie albo pozycja z listy „zadania”\n"
                         "⏰ +15, +1h, +jutro [nr] – odłóż\n"
                         "🗑 usuń <nr>, cofnij – usuń z listy / ostatnio dodane\n"
                         "📞 ważne [nr] – bardzo ważne: Pi zadzwoni o tej porze (też „todo jutro 8:00 ważne …”)")
OSTATNIE_ZADANIE = {}   # id zadania z ostatniego przypomnienia albo ostatnio dodanego (do „zrobione”, „+15”, „cofnij”)


def zadanie_czat(t, bot):
    """komendy zadań w czacie Linphone -> odpowiedź albo None (to nie komenda zadania)"""
    import re
    tl = t.lower().strip(" .!")

    def cel(nr):
        if not nr:
            return OSTATNIE_ZADANIE.get("id")
        lista = bot.zadania_do_zrobienia()
        return lista[int(nr) - 1]["id"] if 0 < int(nr) <= len(lista) else None
    if m := re.fullmatch(r"(?:✅\s*)?(zrobione|zrobiłem|zrobilem|zrobiłam|gotowe|done)(?:\s+(\d+))?", tl):
        zid = cel(m.group(2))
        if not zid:
            return "Nie wiem, które zadanie. Napisz „zadania”, a potem np. „zrobione 2”."
        return bot.callback_zadania(f"todo_ok:{zid}")
    if m := re.fullmatch(r"(?:odłóż|odloz)?\s*\+\s*(?:(\d+)\s*(min|m|minut|h|godz|godzin[ęy]?)?|(jutro))(?:\s+(\d+))?", tl):
        zid = cel(m.group(4))
        if not zid:
            return "Nie wiem, które zadanie. Napisz „zadania”, a potem np. „+1h 2”."
        if m.group(3):
            return bot.callback_zadania(f"todo_odloz:{zid}:jutro")
        n = int(m.group(1)) * (60 if (m.group(2) or "").startswith(("h", "godz")) else 1)
        return bot.callback_zadania(f"todo_odloz:{zid}:{n}")
    if m := re.fullmatch(r"(?:usuń|usun)\s+(\d+)", tl):
        zid = cel(m.group(1))
        return bot.callback_zadania(f"todo_usun:{zid}") if zid else "Nie ma takiej pozycji. Napisz „zadania”."
    if m := re.fullmatch(r"(?:bardzo\s+)?(?:ważne|wazne)(?:\s+(\d+))?", tl):
        zid = cel(m.group(1))
        return bot.callback_zadania(f"todo_dzwon:{zid}") if zid else "Nie wiem, które zadanie. Napisz „zadania”, a potem np. „ważne 2”."
    if tl == "cofnij":
        zid = OSTATNIE_ZADANIE.pop("dodane", None)
        return bot.callback_zadania(f"todo_usun:{zid}") if zid else "Nie ma czego cofnąć."
    return None


def odpowiedz_czat(tekst, wejscie="tekst"):
    """komenda albo Claude; odpowiedź wraca na Linphone (wysyłka w głównym wątku). wejscie: "tekst" albo "glos"
    (głosówka: najpierw rozpoznanie na Pi). Głosem albo tekstem: bot.tryb_odpowiedzi („przeczytaj” / „wypisz”…)."""
    import html as h
    import re
    try:
        pj.Endpoint.instance().libRegisterThread("czat")
    except pj.Error:
        pass
    czysty = lambda t: h.unescape(re.sub(r"<[^>]+>", "", t))
    try:
        import serwerek_bot as bot
        if wejscie == "glos":                   # tekst = adres pliku głosówki
            AKCJE.put((wyslij_czat, ("…", True)))
            plik = pobierz_glosowke(tekst)
            try:
                tekst = glos.rozpoznaj(plik, dokladnie=True)
            except Exception as ex:             # pusty albo uszkodzony plik (Linphone czasem wysyła sam nagłówek)
                log(f"głosówka nieczytelna: {type(ex).__name__}")
                tekst = ""
            import shutil
            shutil.rmtree(plik.parent, ignore_errors=True)
            if not tekst:
                AKCJE.put((wyslij_czat, ("🎙 Ta głosówka dotarła pusta albo nic nie słychać. Nagraj jeszcze raz albo napisz.",)))
                return
        t = tekst.strip()
        sl = t.lower().split()
        akcja = None
        bot.ustaw_kanal("linphone")         # pisze z Linphone: powiadomienia też tutaj
        if t.lower() in ("pomoc", "help", "/pomoc", "/help", "?"):
            odp = "❓ Komendy (wpisz słowo):\n\n" + bot.POMOC_WSPOLNE + POMOC_LINPHONE_KONIEC
        elif t.lower() in ("tak", "tak!", "potwierdzam", "ok tak") and CZAT_AKCJA and time.time() - CZAT_AKCJA["t"] < 120:
            a = CZAT_AKCJA.pop("akcja")
            CZAT_AKCJA.clear()
            odp = bot.wykonaj(a)
        elif t.lower() in ("nie", "anuluj") and CZAT_AKCJA:
            CZAT_AKCJA.clear()
            odp = "Nic nie zrobiłem."
        elif t.lower().strip(" .!") in ("widzę", "widze", "widzę alarm", "nie dzwoń", "nie dzwon"):
            odp = bot.widze_alarmy()
        elif t.lower().strip(" .!") in ("to moje", "to moje urządzenie", "to moje urzadzenie", "to ja"):
            odp = bot.zaufaj_ostatnie()
        elif t.lower() in ("kopia", "/kopia"):
            akcja = "kopia"
        elif t.lower() in ("przejrzane", "/przejrzane"):
            akcja = "przejrzane"
        elif t.lower() in ("minecraft włącz", "minecraft wlacz", "włącz minecraft", "wlacz minecraft", "mc start"):
            akcja = "mc_wlacz"
        elif t.lower() in ("minecraft wyłącz", "minecraft wylacz", "wyłącz minecraft", "wylacz minecraft", "mc stop"):
            akcja = "mc_wylacz"
        elif t.lower() in ("restart portalu", "restart portal"):
            akcja = "restart_portalu"
        elif t.lower() in ("zadzwoń", "zadzwon", "zadzwoń do mnie", "zadzwon do mnie", "/zadzwon"):
            bot.zadzwon("Cześć, tu serwerek. Dzwonię, bo prosiłeś na czacie. W czym mogę pomóc?", "prośba z czatu Linphone")
            odp = "📞 Dzwonię…"
        elif t.lower() in ("nowa rozmowa", "nowa", "/nowa"):
            with bot.LOCK:
                bot.nowa_sesja(bot.stan())
            odp = "🧹 Zaczynamy nową rozmowę z Claude."
        elif t.lower() in ("zaufane", "/zaufane"):
            z = bot.stan().get("zaufane", {})
            odp = ("🔐 Zaufane urządzenia:\n" + "\n".join(f"• {n}: {m}" for m, n in z.items())) if z else "Nie ma zaufanych urządzeń."
            odp += "\n(Usuwanie: komenda zaufane w Telegramie.)"
        elif sl and sl[0] in ("stan", "/stan"):
            odp = czysty(bot.tekst_stanu())
        elif sl and sl[0] in ("sprawdziany", "/sprawdziany", "jutro"):
            odp = czysty(bot.tekst_sprawdzianow())
        elif t.lower() in ("zadania", "todo", "lista", "/zadania"):
            odp = czysty(bot.tekst_zadan()[0])
            if not odp.startswith("📝 Nic"):
                odp += "\nOdpisz np.: zrobione 2, +1h 2, usuń 2."
        elif sl and sl[0] in ("ścieżka", "sciezka", "/sciezka"):
            odp = czysty(bot.tekst_sciezki(" ".join(sl[1:])))
        elif t.lower() in ("minecraft", "mc", "/minecraft"):
            m = bot.portal("/api/minecraft")
            odp = (f"🎮 Minecraft działa od {(m.get('od') or '')[11:16]}, gracze: {m.get('gracze')}. Wyłączenie: „minecraft wyłącz”." if m.get("dziala")
                   else "🎮 Minecraft jest wyłączony. Włączenie: „minecraft włącz”.")
        elif sl and sl[0] in ("todo", "przypomnij", "zadanie") and len(sl) > 1:
            w = bot.nowe_zadanie(t.split(None, 1)[1])
            if w:
                z, opis, termin, powt, dzwon = w
                OSTATNIE_ZADANIE.update(id=z["id"], dodane=z["id"])
                odp = (f"📝 Dodane: {opis}\n⏰ {bot.kiedy_tekst(termin) if termin else 'bez terminu (bez przypomnienia)'}"
                       f"{bot.POWT_T.get(powt, '')}{' · 📞 zadzwonię' if dzwon else ''}\n(„cofnij” usuwa)")
            else:
                odp = "Napisz, co dodać, np. „todo jutro 17:00 trening”."
        else:
            odp = zadanie_czat(t, bot)
            if odp is None:
                odp = bot.komenda_mobi(t)           # plan lekcji
            if odp is None:
                odp = bot.poczta.reakcja(t)         # „przeczytaj mail”, „przeczytany”, „później”, „maile”
            if odp is None:
                odp = bot.komenda_budzik(t)         # budziki
            if odp is None:
                odp = bot.komenda_ztm(t)            # odjazdy, trasa, zapisz miejsce
        if akcja:
            CZAT_AKCJA.clear()
            CZAT_AKCJA.update(akcja=akcja, t=time.time())
            odp = f"❓ {bot.opis_akcji(akcja)}? Odpisz „tak” (w ciągu 2 min) albo „nie”."
        if odp is not None:
            pamiec.zapisz("antek", "linphone", t)
            pamiec.zapisz("bot", "linphone", odp)
        else:
            AKCJE.put((wyslij_czat, ("…", True)))           # „pisze…”
            glosem = bot.tryb_odpowiedzi(t, "tekst") == "glos"
            try:
                odp, akcje = bot.claude_odpowiedz(t, "linphone", pisze=False, glosem=glosem)
            except Exception as ex:
                odp, akcje = f"⚠️ Claude: {ex}. Spróbuj jeszcze raz.", []
            pamiec.zapisz("claude", "linphone", odp)
            if akcje:
                CZAT_AKCJA.clear()
                CZAT_AKCJA.update(akcja=akcje[0], t=time.time())
                odp += f"\n\n❓ {bot.opis_akcji(akcje[0])}? Odpisz „tak” (w ciągu 2 min) albo „nie”."
        AKCJE.put((wyslij_czat, (odp,)))          # w Linphone zawsze tekst (głosówki od Pi mogą się nie odtwarzać)
        if bot.tryb_odpowiedzi(t, "tekst") == "glos":     # głosówka tylko na wyraźną prośbę („przeczytaj”, „powiedz”…)
            try:
                AKCJE.put((wyslij_czat, (wyslij_glosowke(odp), False, FT_TYP)))
            except Exception as ex:
                log(f"głosówka: {type(ex).__name__}: {ex}")
    except Exception as ex:
        log(f"czat: {type(ex).__name__}: {ex}")
        AKCJE.put((wyslij_czat, (f"⚠️ Błąd po stronie Pi: {ex}",)))


KONTAKT = {}


def wyslij_czat(tekst, pisze=False, typ="text/plain"):
    """wiadomość do właściciela na Linphone (tylko główny wątek); długie dzielone na części"""
    try:
        if "b" not in KONTAKT:
            bc = pj.BuddyConfig()
            bc.uri = WLASCICIEL
            b = pj.Buddy()
            b.create(KONTAKT["konto"], bc)
            KONTAKT["b"] = b
        b = KONTAKT["b"]
        if pisze:
            p = pj.SendTypingIndicationParam()
            p.isTyping = True
            b.sendTypingIndication(p)
            return
        for i in range(0, len(tekst), 1500 if typ == "text/plain" else len(tekst)):
            p = pj.SendInstantMessageParam()
            p.content = tekst[i:i + 1500] if typ == "text/plain" else tekst
            p.contentType = typ
            b.sendInstantMessage(p)
    except pj.Error as ex:
        log(f"wyślij czat: {ex.info()}")


def zapisz_stan(zarejestrowane):
    """dla bota: czy Linphone działa (powiadomienia idą na Linphone, a gdy nie, do Telegrama)"""
    try:
        tmp = KAT / "stan.json.tmp"
        tmp.write_text(json.dumps({"zarejestrowane": bool(zarejestrowane), "t": time.time()}), encoding="utf-8")
        os.replace(tmp, KAT / "stan.json")
    except OSError:
        pass


def zadzwon_do_wlasciciela(konto, zl):
    if not WLASCICIEL:
        wynik(stan="blad", opis="nie znam jeszcze Twojego adresu Linphone (SIP_WLASCICIEL). Zadzwoń raz do Pi z Linphone, to go podam.", **zl)
        return
    zl.setdefault("start", time.time())          # pierwsza próba: przez CZAS_DZWONIENIA dzwonimy (z ponowieniami)
    p = Polaczenie(konto, kierunek="od Pi", powitanie=zl["tekst"], zlecenie=zl)     # bez formułki na końcu: po powitaniu Pi i tak słucha
    try:
        p.makeCall(WLASCICIEL, pj.CallOpParam(True))
        AKTYWNE[p.getId()] = p
        log(f"dzwonię do {WLASCICIEL}: {zl['tekst']}")
    except pj.Error as ex:
        wynik(stan="blad", opis=ex.info())


def bez_konfiguracji():
    log("Brak konfiguracji SIP (/etc/serwerek-bot/sip.env): czekam; zlecenia dostają wynik „brak_konfiguracji”.")
    while True:
        for p in sorted(KOLEJKA.glob("*.json")):
            zl = json.loads(p.read_text(encoding="utf-8"))
            p.unlink()
            wynik(stan="brak_konfiguracji", **zl)
        time.sleep(3)


CHWILA = None


def main():
    global CHWILA
    KOLEJKA.mkdir(parents=True, exist_ok=True)
    WYNIKI.mkdir(parents=True, exist_ok=True)
    if not (UZYT and HASLO):
        bez_konfiguracji()
    while not glos.gotowe():
        log("czekam na instalację whisper/Piper")
        time.sleep(60)
    CHWILA = KAT / "mhm.wav"
    if not CHWILA.exists():
        glos.powiedz("Mhm, chwilka.", CHWILA, czestotliwosc=HZ)
    ep = pj.Endpoint()
    ep.libCreate()
    cfg = pj.EpConfig()
    cfg.uaConfig.threadCnt = 0
    cfg.uaConfig.mainThreadOnly = True
    cfg.uaConfig.userAgent = "serwerek-raspberry"
    lokalnie = DOMENA == "lokalnie"         # test na samym Pi: bez serwera SIP i STUN, adres sip:<uzytkownik>@127.0.0.1:5070
    if not lokalnie:
        cfg.uaConfig.stunServer.append("stun.linphone.org:3478")
    cfg.medConfig.clockRate = HZ
    cfg.medConfig.sndClockRate = HZ
    cfg.medConfig.ecTailLen = 0
    cfg.logConfig.level = 3
    cfg.logConfig.consoleLevel = 2
    if os.environ.get("TELEFON_LOG"):            # diagnostyka: pełny zapis SIP do pliku
        cfg.logConfig.level = int(os.environ["TELEFON_LOG"])
        cfg.logConfig.filename = "/tmp/telefon-sip.log"
    ep.libInit(cfg)
    tc = pj.TransportConfig()
    if lokalnie:
        tc.port = 5070
    ep.transportCreate(pj.PJSIP_TRANSPORT_TCP, tc)
    ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, tc)
    ep.libStart()
    ep.audDevManager().setNullDev()
    ac = pj.AccountConfig()
    if lokalnie:
        ac.idUri = f"sip:{UZYT}@127.0.0.1:5070"
    else:
        ac.idUri = f'"Serwer Rpi" <sip:{UZYT}@{DOMENA}>'      # nazwa w Linphone/CallKit zamiast „Anonymous”
        ac.regConfig.registrarUri = f"sip:{DOMENA};transport=tcp"
        ac.sipConfig.proxies.append(f"sip:{DOMENA};transport=tcp;lr")
        ac.sipConfig.authCreds.append(pj.AuthCredInfo("digest", "*", UZYT, 0, HASLO))
        ac.natConfig.iceEnabled = True
        ac.natConfig.sipOutboundUse = 1
        # Linphone szyfruje dźwięk (SRTP): bez tego połączenia kończą się „488 Not Acceptable Here”.
        # Wymagane (RTP/SAVP): przy „opcjonalnym” Pi oferuje zwykłe RTP/AVP i Linphone na iPhonie odrzuca połączenia od Pi
        # (603 Decline, „Anonymous”). Klucze SDES także przez TCP (secureSignaling 0).
        ac.mediaConfig.srtpUse = pj.PJMEDIA_SRTP_MANDATORY
        ac.mediaConfig.srtpSecureSignaling = 0
    konto = Konto()
    konto.create(ac)
    KONTAKT["konto"] = konto
    CZAT.mkdir(parents=True, exist_ok=True)
    log(f"telefon startuje jako {ac.idUri}, właściciel {WLASCICIEL}")
    while True:
        ep.libHandleEvents(20)
        while not AKCJE.empty():
            f, a = AKCJE.get()
            f(*a)
        teraz = time.time()
        if teraz - KONTAKT.get("stan_t", 0) > 60:
            KONTAKT["stan_t"] = teraz
            zapisz_stan(getattr(konto, "zarejestrowane", False))
        GRACZE[:] = [(t, g) for t, g in GRACZE if t > teraz]
        for p in [p for p in ZAKONCZONE if not (p.watek and p.watek.is_alive())]:
            ZAKONCZONE.remove(p)
            p.rozmowa.p = None          # przerwij cykl referencji: obiekt pjsua2 zniknie tu, w głównym wątku
        for p in list(AKTYWNE.values()):         # nikt nie odebrał
            if p.rozmowa.kierunek == "od Pi" and not p.odebrane and teraz - p.rozmowa.zlecenie.get("start", p.utworzone) > CZAS_DZWONIENIA:
                rozlacz(p)
        for p in sorted(CZAT.glob("*.json")):             # wiadomości od bota na Linphone
            try:
                zl = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                zl = {}
            p.unlink(missing_ok=True)
            if zl.get("tekst") and WLASCICIEL and konto.zarejestrowane:
                if zl.get("glos"):          # głosówka: synteza i wysyłka w wątku, potem wiadomość z plikiem w głównym
                    threading.Thread(target=lambda t=zl["tekst"]: AKCJE.put((wyslij_czat, (wyslij_glosowke(t), False, FT_TYP))),
                                     daemon=True).start()
                else:
                    wyslij_czat(zl["tekst"])
                if zl.get("todo_id"):      # przypomnienie: „zrobione” / „+15” w odpowiedzi dotyczy tego zadania
                    OSTATNIE_ZADANIE["id"] = zl["todo_id"]
        if not AKTYWNE and PONOW and PONOW[0][0] <= teraz:
            zadzwon_do_wlasciciela(konto, PONOW.pop(0)[1])
        elif not AKTYWNE and not PONOW:
            for p in sorted(KOLEJKA.glob("*.json")):
                try:
                    zl = json.loads(p.read_text(encoding="utf-8"))
                except ValueError:
                    if time.time() - p.stat().st_mtime > 10:      # zepsuty plik: usuń; świeży: może jeszcze się zapisuje
                        p.unlink()
                    continue
                p.unlink()
                if konto.zarejestrowane:
                    zadzwon_do_wlasciciela(konto, zl)
                else:
                    wynik(stan="blad", opis="Pi nie jest zalogowane do serwera SIP (sprawdź konto Linphone i hasło)", **zl)
                break


if __name__ == "__main__":
    main()
