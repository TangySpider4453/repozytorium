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
MODEL_SZYBKI = G / "modele" / "ggml-base.bin"           # telefon: szybciej
MODEL_DOKLADNY = G / "modele" / "ggml-small-q5_1.bin"   # wiadomości głosowe: dokładniej
PIPER = G / "piper" / "piper"
GLOS = G / "modele" / "pl_PL-gosia-medium.onnx"
WATKI = "3"                                              # 1 rdzeń zostaje dla Minecrafta


def gotowe():
    return WHISPER.exists() and MODEL_SZYBKI.exists() and PIPER.exists() and GLOS.exists()


# podpowiedź słownictwa dla whispera (nazwy, które inaczej przekręca)
SLOWNIK = "Serwerek, Raspberry Pi, Minecraft, serwer, NAS, Tailscale, Telegram, Claude, kartkówka, sprawdzian, Progres."


def rozpoznaj(plik, dokladnie=True, limit=180):
    """dokladnie=False: model base na 4 rdzeniach (telefon, ok. 1 s na 1 s mowy); True: small (ok. 2 s na 1 s mowy)"""
    import wave
    model = MODEL_DOKLADNY if dokladnie and MODEL_DOKLADNY.exists() else MODEL_SZYBKI
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "we.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(plik), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
                       check=True, timeout=60)
        with wave.open(str(wav)) as w:
            sek = w.getnframes() / 16000
        # okno kodera dopasowane do długości nagrania (domyślnie zawsze 30 s = 1500): 2-3 razy szybciej dla krótkich wypowiedzi
        okno = str(min(1500, max(256, int(sek * 50) + 96)))
        r = subprocess.run(["nice", "-n", "5", str(WHISPER), "-m", str(model), "-l", "pl", "-t", "4" if not dokladnie else WATKI,
                            "-ac", okno, "--prompt", SLOWNIK, "-nt", "-np", "-f", str(wav)],
                           capture_output=True, text=True, timeout=limit)
    tekst = " ".join(l.strip() for l in r.stdout.splitlines() if l.strip())
    tekst = re.sub(r"\[(BLANK_AUDIO|MUZYKA|Muzyka|muzyka)\]|\((muzyka|cisza)\)", "", tekst).strip()
    return tekst


def do_mowy(tekst):
    """tekst do czytania na głos: bez Markdown, emotek i adresów"""
    t = re.sub(r"https?://\S+", "link na czacie", tekst)
    t = re.sub(r"[*_`#>|]", "", t)
    t = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", t)
    t = t.replace("•", ",").replace("°C", " stopni").replace("%", " procent")
    return re.sub(r"\s+", " ", t).strip()


def powiedz(tekst, wyjscie, czestotliwosc=None):
    tekst = do_mowy(tekst)
    surowy = str(wyjscie) + ".surowy.wav" if czestotliwosc else str(wyjscie)
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
