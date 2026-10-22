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
Bot może też wysłać wiadomość na Linphone: plik JSON {"tekst": …} w ~/bot/telefon/czat/.
Konfiguracja: /etc/serwerek-bot/sip.env (SIP_UZYTKOWNIK, SIP_HASLO, SIP_DOMENA, SIP_WLASCICIEL), podawana przez systemd.
Bez konfiguracji usługa czeka i odpowiada na zlecenia wynikiem „brak_konfiguracji”.
"""
import json
import os
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
CZAS_DZWONIENIA = 45                                    # s: potem „nie odebrał”
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

    def mow(self, tekst):
        """synteza (Piper) i odtworzenie w rozmowie; czeka do końca wypowiedzi"""
        self.zapis.append(f"Pi: {tekst}")
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
        log(f"połączenie {ci.id}: {ci.stateText}")
        if ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
            self.odebrane = True
        if ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            if not self.odebrane and self.rozmowa.kierunek == "od Pi":
                z = self.rozmowa.zlecenie
                wynik(stan="nieodebrane", tekst=z.get("tekst", ""), powod=z.get("powod", ""))
            self.rozmowa.zakonczona()
            ZAKONCZONE.append(AKTYWNE.pop(ci.id, self))

    def onCallMediaState(self, prm):
        ci = self.getInfo()
        for mi in ci.media:
            if mi.type == pj.PJMEDIA_TYPE_AUDIO and mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE and self.media is None:
                self.media = self.getAudioMedia(mi.index)
                self.rec = pj.AudioMediaRecorder()
                self.rec.createRecorder(str(self.rozmowa.nagranie))
                self.media.startTransmit(self.rec)
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
    wav = Path(tempfile.mkdtemp(prefix="czat-", dir="/tmp")) / "odpowiedz.wav"
    glos.powiedz(tekst[:4000], wav, czestotliwosc=HZ)
    ms = int(czas_wav(wav) * 1000)
    g = uuid.uuid4().hex
    cialo = (f"--{g}\r\nContent-Disposition: form-data; name=\"File\"; filename=\"glosowka.wav\"\r\n"
             f"Content-Type: audio/wav\r\n\r\n").encode() + wav.read_bytes() + f"\r\n--{g}--\r\n".encode()
    req = urllib.request.Request(FT_SERWER, data=cialo, headers={"Content-Type": f"multipart/form-data; boundary={g}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        xml = r.read().decode("utf-8")
    import shutil
    shutil.rmtree(wav.parent, ignore_errors=True)
    # znaczniki głosówki Linphone: typ z voice-recording=yes i długość nagrania
    xml = xml.replace("<content-type>audio/wav</content-type>", "<content-type>audio/wav;voice-recording=yes</content-type>")
    xml = xml.replace('<file xmlns="urn:gsma:params:xml:ns:rcs:rcs:fthttp">',
                      '<file xmlns="urn:gsma:params:xml:ns:rcs:rcs:fthttp" xmlns:am="urn:gsma:params:xml:ns:rcs:rcs:rram">')
    xml = xml.replace("</file-info>", f"<am:playing-length>{ms}</am:playing-length></file-info>", 1)
    return xml


def pobierz_glosowke(url):
    import urllib.request
    p = Path(tempfile.mkdtemp(prefix="czat-", dir="/tmp")) / "glosowka"
    with urllib.request.urlopen(url, timeout=60) as r:
        p.write_bytes(r.read())
    return p


CZAT_AKCJA = {}     # akcja czekająca na „tak” w czacie Linphone (Linphone nie ma przycisków): {"akcja", "t"}
POMOC_LINPHONE_KONIEC = ("\n\nW Linphone nie ma przycisków: gdy coś trzeba potwierdzić (kopia, Minecraft, przejrzane), "
                         "odpisz „tak” w ciągu 2 minut. Zdjęcia i PDF-y wysyłaj w Telegramie.")


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
            tekst = glos.rozpoznaj(plik, dokladnie=True)
            import shutil
            shutil.rmtree(plik.parent, ignore_errors=True)
            if not tekst:
                AKCJE.put((wyslij_czat, ("🎙 Nic nie usłyszałem, spróbuj jeszcze raz.",)))
                return
        t = tekst.strip()
        sl = t.lower().split()
        akcja = None
        if t.lower() in ("pomoc", "help", "/pomoc", "/help", "?"):
            odp = "❓ Komendy (wpisz słowo):\n\n" + bot.POMOC_WSPOLNE + POMOC_LINPHONE_KONIEC
        elif t.lower() in ("tak", "tak!", "potwierdzam", "ok tak") and CZAT_AKCJA and time.time() - CZAT_AKCJA["t"] < 120:
            a = CZAT_AKCJA.pop("akcja")
            CZAT_AKCJA.clear()
            odp = bot.wykonaj(a)
        elif t.lower() in ("nie", "anuluj") and CZAT_AKCJA:
            CZAT_AKCJA.clear()
            odp = "Nic nie zrobiłem."
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
        elif sl and sl[0] in ("ścieżka", "sciezka", "/sciezka"):
            odp = czysty(bot.tekst_sciezki(" ".join(sl[1:])))
        elif t.lower() in ("minecraft", "mc", "/minecraft"):
            m = bot.portal("/api/minecraft")
            odp = (f"🎮 Minecraft działa od {(m.get('od') or '')[11:16]}, gracze: {m.get('gracze')}. Wyłączenie: „minecraft wyłącz”." if m.get("dziala")
                   else "🎮 Minecraft jest wyłączony. Włączenie: „minecraft włącz”.")
        elif sl and sl[0] in ("todo", "przypomnij", "zadanie") and len(sl) > 1:
            opis, termin, powt = bot.parsuj_zadanie(t.split(None, 1)[1])
            bot.portal("/api/todo", {"tekst": opis, "termin": termin, "powtarzaj": powt})
            odp = f"Dodane: {opis} ({bot.kiedy_tekst(termin) if termin else 'bez terminu'})."
        else:
            odp = None
        if akcja:
            CZAT_AKCJA.clear()
            CZAT_AKCJA.update(akcja=akcja, t=time.time())
            odp = f"❓ {bot.AKCJE[akcja][0]}? Odpisz „tak” (w ciągu 2 min) albo „nie”."
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
                odp += f"\n\n❓ {bot.AKCJE[akcje[0]][0]}? Odpisz „tak” (w ciągu 2 min) albo „nie”."
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


def zadzwon_do_wlasciciela(konto, zl):
    if not WLASCICIEL:
        wynik(stan="blad", opis="nie znam jeszcze Twojego adresu Linphone (SIP_WLASCICIEL). Zadzwoń raz do Pi z Linphone, to go podam.", **zl)
        return
    p = Polaczenie(konto, kierunek="od Pi", powitanie=zl["tekst"] + " Możesz mi odpowiedzieć albo się rozłączyć.", zlecenie=zl)
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
        ac.idUri = f"sip:{UZYT}@{DOMENA}"
        ac.regConfig.registrarUri = f"sip:{DOMENA};transport=tcp"
        ac.sipConfig.proxies.append(f"sip:{DOMENA};transport=tcp;lr")
        ac.sipConfig.authCreds.append(pj.AuthCredInfo("digest", "*", UZYT, 0, HASLO))
        ac.natConfig.iceEnabled = True
        ac.natConfig.sipOutboundUse = 1
        # Linphone szyfruje dźwięk (SRTP): bez tego połączenia kończą się „488 Not Acceptable Here”.
        # Opcjonalnie: oferujemy SRTP, ale przyjmiemy też zwykłe RTP; klucze SDES także przez TCP (secureSignaling 0).
        ac.mediaConfig.srtpUse = pj.PJMEDIA_SRTP_OPTIONAL
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
        GRACZE[:] = [(t, g) for t, g in GRACZE if t > teraz]
        for p in [p for p in ZAKONCZONE if not (p.watek and p.watek.is_alive())]:
            ZAKONCZONE.remove(p)
            p.rozmowa.p = None          # przerwij cykl referencji: obiekt pjsua2 zniknie tu, w głównym wątku
        for p in list(AKTYWNE.values()):         # nikt nie odebrał
            if p.rozmowa.kierunek == "od Pi" and not p.odebrane and teraz - p.utworzone > CZAS_DZWONIENIA:
                rozlacz(p)
        for p in sorted(CZAT.glob("*.json")):             # wiadomości od bota na Linphone
            try:
                tekst = json.loads(p.read_text(encoding="utf-8")).get("tekst", "")
            except (OSError, ValueError):
                tekst = ""
            p.unlink(missing_ok=True)
            if tekst and WLASCICIEL and konto.zarejestrowane:
                wyslij_czat(tekst)
        if not AKTYWNE:
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
