"""
Stale uruchomiony Claude Code (tryb stream-json): proces startuje raz i dostaje kolejne wiadomości przez stdin, więc
odpowiedź nie czeka ok. 6 s na start programu (Haiku: 1–2 s, Sonnet: 1,5–4 s zamiast 7–9 s).

  Proces(nazwa, model, effort, polecenie)   polecenie() -> (cmd bez promptu, env): uprawnienia, instrukcja, strażnik
  p.zapytaj(tekst, limit) -> dict           wynik ze zdarzenia "result" ({result, session_id, is_error, usage, …})
  p.zamknij()                               koniec procesu (nowa rozmowa, zmiana instrukcji); następne zapytanie
                                            uruchomi go od nowa (z --resume, jeśli sesja jest jeszcze świeża)
Jeden proces obsługuje jedno zapytanie naraz (blokada); zawieszony albo martwy proces jest zabijany i uruchamiany znowu.
"""
import json
import queue
import subprocess
import threading
import time


class Proces:
    def __init__(self, nazwa, model, effort, polecenie):
        self.nazwa, self.model, self.effort, self.polecenie = nazwa, model, effort, polecenie
        self.p = None
        self.linie = None
        self.sesja = None            # id sesji Claude (z ostatniego wyniku)
        self.kontekst = 0            # tokeny kontekstu ostatniego wywołania
        self.ostatnio = 0.0
        self.lock = threading.Lock()

    def _start(self, resume=None):
        cmd, env = self.polecenie()
        cmd = cmd + ["--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                     "--model", self.model, "--effort", self.effort]
        if resume:
            cmd += ["--resume", resume]
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  text=True, bufsize=1, cwd="/home/tonyg", env=env)
        self.linie = queue.Queue()
        threading.Thread(target=self._czytaj, args=(self.p, self.linie), daemon=True).start()
        print(f"klaud {self.nazwa}: start ({self.model}, {self.effort}{', wznowienie' if resume else ''})", flush=True)

    @staticmethod
    def _czytaj(p, q):
        for linia in p.stdout:
            q.put(linia)
        q.put(None)

    def zamknij(self):
        if self.p:
            try:
                self.p.stdin.close()
                self.p.wait(timeout=5)
            except Exception:
                self.p.kill()
        self.p = None

    def nowa_rozmowa(self):
        with self.lock:
            self.zamknij()
            self.sesja, self.kontekst = None, 0

    def zapytaj(self, tekst, limit=1800, resume=None):
        """jedna wiadomość -> wynik (dict); proces startuje przy pierwszym zapytaniu"""
        with self.lock:
            if self.p is None or self.p.poll() is not None:
                self._start(resume or self.sesja)
            try:
                self.p.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": tekst}}) + "\n")
                self.p.stdin.flush()
            except OSError:
                self.zamknij()
                self._start(resume or self.sesja)
                self.p.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": tekst}}) + "\n")
                self.p.stdin.flush()
            koniec = time.time() + limit
            while True:
                try:
                    linia = self.linie.get(timeout=max(0.1, koniec - time.time()))
                except queue.Empty:
                    print(f"klaud {self.nazwa}: przekroczony czas, restart procesu", flush=True)
                    self.p.kill()
                    self.p = None
                    return {"is_error": True, "result": "Przekroczony czas odpowiedzi."}
                if linia is None:                               # proces się zakończył
                    self.p = None
                    return {"is_error": True, "result": "Claude przerwał pracę (proces się zakończył)."}
                try:
                    d = json.loads(linia)
                except ValueError:
                    continue
                if d.get("type") != "result":
                    continue
                if d.get("session_id"):
                    self.sesja = d["session_id"]
                u = d.get("usage") or {}
                # rozmiar kontekstu ~ wejście ostatniego wywołania (z pamięcią podręczną)
                self.kontekst = (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
                self.ostatnio = time.time()
                return d
