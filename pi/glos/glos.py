"""
Mowa na Raspberry Pi (wspólne dla bota Telegram i telefonu):
  rozpoznaj(plik) -> tekst      whisper.cpp (polski), dowolny format audio (ffmpeg zamienia na 16 kHz mono)
  powiedz(tekst, plik.wav)      Piper, polski głos „gosia” (WAV 22 050 Hz albo, z czestotliwosc=16000, 16 kHz)
  do_ogg(wav, ogg)              WAV -> OGG/Opus (wiadomość głosowa Telegrama)
Wszystko lokalnie, bez internetu. Pliki w /home/tonyg/glos/ (instaluj.sh).
"""
import os
import re
import subprocess
import tempfile
from pathlib import Path

G = Path("/home/tonyg/glos")
WHISPER = G / "whisper.cpp" / "build" / "bin" / "whisper-cli"
MODEL_SZYBKI = G / "modele" / "ggml-base.bin"           # telefon: szybciej (zapas, gdy nie ma q8_0)
MODEL_SZYBKI_Q8 = G / "modele" / "ggml-base-q8_0.bin"   # ten sam model skwantyzowany: ~2x szybciej, ten sam tekst
SERWER_ASR = "http://127.0.0.1:8787/inference"          # glos-whisper.service: model q8_0 stale w pamięci
MODEL_DOKLADNY = G / "modele" / "ggml-small-q5_1.bin"   # wiadomości głosowe: dokładniej
PIPER = G / "piper" / "piper"
GLOS = G / "modele" / "pl_PL-gosia-medium.onnx"
WATKI = "3"                                              # 1 rdzeń zostaje dla Minecrafta


def gotowe():
    return WHISPER.exists() and MODEL_SZYBKI.exists() and PIPER.exists() and GLOS.exists()


# podpowiedź słownictwa dla whispera (nazwy, które inaczej przekręca)
SLOWNIK = "Serwerek, Raspberry Pi, Minecraft, serwer, NAS, Samba, Tailscale, Telegram, Linphone, Claude, kartkówka, sprawdzian, Progres, plik, Mobidziennik."


def _serwer_asr(wav, okno, limit):
    """rozpoznanie przez stały serwer whisper (model już w pamięci) -> tekst albo None, gdy serwer nie działa"""
    import urllib.request
    import uuid
    gr = uuid.uuid4().hex
    pola = {"language": "pl", "response_format": "text", "prompt": SLOWNIK, "audio_ctx": okno, "beam_size": "1",
            "best_of": "1", "temperature": "0", "temperature_inc": "0", "no_timestamps": "true"}
    cialo = b"".join(f'--{gr}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in pola.items())
    cialo += f'--{gr}\r\nContent-Disposition: form-data; name="file"; filename="we.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
    cialo += Path(wav).read_bytes() + f"\r\n--{gr}--\r\n".encode()
    try:
        req = urllib.request.Request(SERWER_ASR, data=cialo, headers={"Content-Type": f"multipart/form-data; boundary={gr}"})
        with urllib.request.urlopen(req, timeout=limit) as r:
            return r.read().decode("utf-8", "replace")
    except OSError:
        return None


def rozpoznaj(plik, dokladnie=True, limit=180):
    """dokladnie=False (telefon): serwer whisper z modelem base q8_0 (ok. 0,3 s na 1 s mowy), a gdy nie działa: whisper-cli;
    True (wiadomości głosowe): small (ok. 2 s na 1 s mowy)"""
    import wave
    model = MODEL_DOKLADNY if dokladnie and MODEL_DOKLADNY.exists() else MODEL_SZYBKI_Q8 if MODEL_SZYBKI_Q8.exists() else MODEL_SZYBKI
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "we.wav"
        try:                                    # nagranie z rozmowy jest już 16 kHz mono: bez ffmpeg (~0,2 s mniej)
            with wave.open(str(plik)) as w:
                gotowy = w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2
        except (wave.Error, EOFError, OSError):
            gotowy = False
        if gotowy:
            wav = Path(plik)
        else:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(plik), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
                           check=True, timeout=60)
        with wave.open(str(wav)) as w:
            sek = w.getnframes() / 16000
        # okno kodera dopasowane do długości nagrania (domyślnie zawsze 30 s = 1500): 2-3 razy szybciej dla krótkich wypowiedzi
        okno = str(min(1500, max(256, int(sek * 50) + 96)))
        wynik = None if dokladnie else _serwer_asr(wav, okno, limit)
        if wynik is None:
            r = subprocess.run(["nice", "-n", "5", str(WHISPER), "-m", str(model), "-l", "pl", "-t", "4" if not dokladnie else WATKI,
                                "-ac", okno, "--prompt", SLOWNIK, "-nt", "-np", "-f", str(wav)]
                               + ([] if dokladnie else ["-bs", "1", "-bo", "1", "-nf"]),     # telefon: zachłannie, ok. 30% szybciej
                               capture_output=True, text=True, timeout=limit)
            wynik = r.stdout
    tekst = " ".join(l.strip() for l in wynik.splitlines() if l.strip())
    tekst = re.sub(r"\[(BLANK_AUDIO|MUZYKA|Muzyka|muzyka)\]|\((muzyka|cisza)\)", "", tekst).strip()
    return tekst


def do_mowy(tekst):
    """tekst do czytania na głos: bez Markdown, emotek i adresów"""
    t = re.sub(r"https?://\S+|\bwww\.\S+", "link na czacie", tekst)
    t = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "adres na czacie", t)                       # maile
    t = re.sub(r"\b(?:[\w-]+\.)+(?:pl|com|org|net|eu|io|edu|gov|info|me|app|dev)\b(?:/\S*)?", "adres na czacie", t)   # same domeny
    t = re.sub(r"(?<![\d:.])(\+?48[\s-]?)?(\d{3}[\s-]?\d{3}[\s-]?\d{3}|\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2})(?![\d:])",
               "numer na czacie", t)                                                    # telefony
    t = re.sub(r"(?<![\w.-])(?=[A-Za-z0-9-]*\d)(?=[A-Za-z0-9-]*[A-Za-z])[A-Za-z0-9][A-Za-z0-9-]{7,}(?![\w-])", "kod na czacie", t)  # kody
    t = re.sub(r"\bkod kod na czacie", "kod na czacie", t)
    t = re.sub(r"(?:~|/home|/etc|/mnt|/var|/usr)/\S+?(?=[.,;:!?]?(?:\s|$))", "ścieżka na czacie", t)     # ścieżki plików
    t = re.sub(r"[*_`#>|]", "", t)
    t = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", t)
    t = t.replace("•", ",").replace("°C", " stopni").replace("%", " procent")
    return re.sub(r"\s+", " ", t).strip()


class StalyPiper:
    """Piper uruchomiony raz (model wczytany na stałe), zdania przez stdin w JSON: ok. 1 s szybciej na każdą wypowiedź.
    Piper wypisuje ścieżkę pliku, gdy skończy. Jeden naraz (blokada); padnięty proces startuje znowu."""
    def __init__(self):
        import threading
        self.p, self.lock = None, threading.Lock()

    def _start(self):
        self.p = subprocess.Popen(["nice", "-n", "5", str(PIPER), "--model", str(GLOS), "--json-input", "--output_dir", "/tmp",
                                   "--sentence_silence", "0.25"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1, env={**os.environ, "LD_LIBRARY_PATH": str(PIPER.parent)})

    def syntezuj(self, tekst, plik, limit=60):
        import json
        import select
        import time
        with self.lock:
            if self.p is None or self.p.poll() is not None:
                self._start()
            self.p.stdin.write(json.dumps({"text": tekst, "output_file": plik}, ensure_ascii=False) + "\n")
            self.p.stdin.flush()
            koniec = time.time() + limit
            while time.time() < koniec:
                r, _, _ = select.select([self.p.stdout], [], [], max(0.1, koniec - time.time()))
                if not r:
                    break
                linia = self.p.stdout.readline()
                if not linia:                   # proces padł
                    break
                if linia.strip() == plik:
                    return True
            self.p.kill()
            self.p = None
            return False


PIPER_STALY = StalyPiper()


def powiedz(tekst, wyjscie, czestotliwosc=None):
    tekst = do_mowy(tekst)
    surowy = str(wyjscie) + ".surowy.wav" if czestotliwosc else str(wyjscie)
    try:
        ok = PIPER_STALY.syntezuj(tekst, surowy)
    except (OSError, ValueError):
        ok = False
    if not ok:                                  # zapas: jednorazowo (wczytanie modelu za każdym razem)
        subprocess.run(["nice", "-n", "5", str(PIPER), "--model", str(GLOS), "--output_file", surowy, "--sentence_silence", "0.25"],
                       input=tekst, text=True, check=True, timeout=120, capture_output=True,
                       env={**os.environ, "LD_LIBRARY_PATH": str(PIPER.parent)})
    if czestotliwosc:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", surowy, "-ar", str(czestotliwosc), "-ac", "1", "-c:a", "pcm_s16le",
                        str(wyjscie)], check=True, timeout=60)
        os.unlink(surowy)
    return wyjscie


def do_ogg(wav, ogg):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libopus", "-b:a", "32k", "-ac", "1", str(ogg)],
                   check=True, timeout=60)
    return ogg
