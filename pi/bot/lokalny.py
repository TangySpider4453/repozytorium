"""
Lokalny model zapasowy do rozmów (Ollama na Pi): odpowiada, gdy Claude się wysypie (brak tokenów, błąd, limit czasu).
Bez narzędzi i bez akcji: tylko krótka odpowiedź na podstawie ostatnich wiadomości z pamięci i bieżącej daty/godziny.
Inny (mniejszy, szybszy) model niż do Garmina, bo w rozmowie liczy się czas odpowiedzi.
"""
import json
import os
import urllib.request
from datetime import datetime

OLLAMA = "http://127.0.0.1:11434"
MODEL = os.environ.get("LOKALNY_MODEL", "qwen2.5:1.5b")   # test 16.11 na Pi 4: ok. 10–25 s na odpowiedź, poprawne fakty
# (qwen3:1.7b szybszy, ale mylił fakty; 3–4B to 30–60 s). Kontekst krótki: każdy token promptu to czas na Pi.
DNI = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]

SYSTEM = ("Jesteś zapasowym asystentem serwera domowego Antka (Raspberry Pi). Główny asystent (Claude) teraz nie działa. "
          "Odpowiadaj po polsku, krótko i konkretnie (1–3 zdania), bez Markdown i bez emotek. Nie masz dostępu do internetu, "
          "plików ani narzędzi i niczego nie wykonujesz: gdy Antek prosi o działanie (wysłanie, zmianę, sprawdzenie czegoś na "
          "serwerze), powiedz, że zrobi to główny asystent, gdy wróci, albo żeby użył komendy bota. Nie zmyślaj faktów; "
          "gdy nie wiesz, powiedz to. Teraz jest {teraz}.")


def odpowiedz(tekst, kontekst="", telefon=False, limit=120):
    """-> tekst odpowiedzi (wyjątek, gdy Ollama nie działa)"""
    n = datetime.now()
    teraz = f"{DNI[n.weekday()]}, {n.strftime('%d.%m.%Y')}, godzina {n.strftime('%H:%M')}"
    wiad = [{"role": "system", "content": SYSTEM.format(teraz=teraz) + (" Mówisz przez telefon: odpowiedź będzie czytana na głos."
                                                                         if telefon else "")}]
    if kontekst.strip():
        wiad.append({"role": "user", "content": "Ostatnie wiadomości (dla kontekstu):\n" + kontekst.strip()[-(600 if telefon else 1500):]})
        wiad.append({"role": "assistant", "content": "Rozumiem."})
    wiad.append({"role": "user", "content": tekst})
    dane = {"model": MODEL, "messages": wiad, "stream": False, "keep_alive": "2m", "think": False,
            "options": {"temperature": 0.3, "num_ctx": 2048, "num_predict": 120 if telefon else 300, "num_thread": 3}}
    req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(dane).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=limit) as r:
        d = json.loads(r.read())
    return (d.get("message") or {}).get("content", "").strip()


def rozgrzej():
    """wczytuje model do pamięci (pierwsza odpowiedź bez czekania na ładowanie)"""
    dane = {"model": MODEL, "prompt": "", "keep_alive": "2m"}
    req = urllib.request.Request(OLLAMA + "/api/generate", data=json.dumps(dane).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        r.read()
