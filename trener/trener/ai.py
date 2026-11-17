"""Claude przez CLI na Pi (token nowego konta z /etc/serwerek-bot/claude.env w usłudze). Bez narzędzi, bez sesji,
w pustym katalogu (żadnego CLAUDE.md). Wynik: tekst albo JSON wg schematu (--json-schema)."""
import json
import logging
import os
import subprocess
import tempfile

from . import config

log = logging.getLogger(__name__)

SYSTEM = (
    "Jesteś osobistym trenerem i analitykiem danych Antka (nastolatek, uczeń technikum; głównie kolarz szosowy/MTB, "
    "do tego siłownia i bieganie; zegarek Garmin fenix 7 Pro, licznik Edge 1050, pas HRM-Pro). Masz jego dane z Garmin "
    "Connect. Piszesz po polsku, konkretnie, jak dobry trener: liczby, wnioski, co zrobić. Bez lania wody, bez "
    "Markdown-owych tabel (krótkie akapity i listy są OK). Dbasz o zdrowie: to młody sportowiec — regeneracja, sen i "
    "stopniowe obciążenie przed ambicją; przy objawach choroby lub bólu odradzasz trening i radzisz lekarza. "
    "Nie wymyślaj danych, których nie dostałeś; gdy czegoś brakuje, powiedz to.")


class BladAI(Exception):
    pass


def zapytaj(prompt, schemat=None, model=None, effort="medium", limit_s=300, narzedzia=None):
    """-> str albo dict (gdy schemat). narzedzia: np. ["WebSearch", "WebFetch"] (tylko odczyt internetu)"""
    model = model or config.ustawienia()["model"]
    nz = ",".join(narzedzia or [])
    cmd = [str(config.CLAUDE), "-p", "--output-format", "json", "--model", model, "--tools", nz,
           *(["--allowedTools", nz] if nz else []),
           "--strict-mcp-config", "--no-session-persistence", "--permission-mode", "dontAsk",
           "--setting-sources", "", "--system-prompt", SYSTEM, "--effort", effort]
    if schemat:
        cmd += ["--json-schema", json.dumps(schemat, ensure_ascii=False)]
    with tempfile.TemporaryDirectory(prefix="trener-ai-") as kat:
        try:
            p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=limit_s, cwd=kat,
                               env={**os.environ, "HOME": os.environ.get("HOME", "/home/tonyg")})
        except subprocess.TimeoutExpired as ex:
            raise BladAI(f"Claude nie odpowiedział w {limit_s} s") from ex
    try:
        w = json.loads(p.stdout)
    except ValueError:
        raise BladAI(f"Claude: {(p.stderr or p.stdout)[-300:]}")
    if w.get("is_error"):
        raise BladAI(f"Claude: {str(w.get('result'))[:300]}")
    if schemat:
        so = w.get("structured_output")
        if so is None:
            try:
                so = json.loads(w.get("result") or "")
            except ValueError:
                raise BladAI("Claude nie zwrócił JSON")
        return so
    return w.get("result") or ""
