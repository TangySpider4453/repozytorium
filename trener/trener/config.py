"""Ścieżki i ustawienia. Sekrety tylko poza gitem: token Garmina w dane/garmin_tokens/, klucze VAPID w dane/."""
import json
import os
from pathlib import Path

KAT = Path(__file__).resolve().parent.parent
DANE = Path(os.environ.get("TRENER_DANE", KAT / "dane"))
BAZA = DANE / "trener.db"
TOKENY = Path(os.environ.get("TRENER_TOKENY", KAT / "dane" / "garmin_tokens"))
BLOKADA_GARMIN = DANE / "garmin.lock"
CLAUDE = Path(os.environ.get("TRENER_CLAUDE", "/home/tonyg/.local/bin/claude"))
KOLEJKA_BOTA = Path("/home/tonyg/bot/powiadomienia")
STATIC = KAT / "static"
ZNACZNIK = "auto: trener"          # w opisie treningów tworzonych przez apkę; usuwamy TYLKO takie
START_HISTORII = "2024-04-01"     # najstarsze dane (pierwsza aktywność 27.04.2024); backfill i tak schodzi do pierwszej

DOMYSLNE = {
    "cele": "",                     # cele Antka własnymi słowami (z ustawień / czatu)
    "dostepnosc": "",               # kiedy może trenować
    "sprzet": "",                   # rower, trenażer, siłownia…
    "sporty": ["rower", "bieg", "silka"],
    "plan_dni": 7,                  # na ile dni do przodu planować
    "auto_zegarek": True,           # treningi same idą do Garmina (decyzja Antka 17.11)
    "analiza_rano": True,
    "analiza_godzina_min": "06:30", # nie wcześniej niż
    "push": True,
    "linphone": False,   # Linphone tylko zapasowo, gdy push nie dojdzie do nikogo (Antek 18.11: bez podwójnych)
    "model_czat": "claude-opus-5-5",     # czat w apce (decyzja Antka 26.11)
    "model": "claude-sonnet-5-5",        # w tle: analiza, ankieta, cel dnia… (26.11: bez Haiku)
    "model_ciezki": "claude-sonnet-5-5", # ciężkie: plan, cel, badania
    "gora_tyg": 3, "nogi_tyg": 2, "dni_tylko_nogi": [], "dni_jedna_sesja": [], "weekend_dwie_max": 2, "silka_min_min": 55, "tetno_ciezkie": None,                  # siłka góra: tyle razy w tygodniu ZAWSZE (decyzja Antka 17.11, sprawdza kontrola planu)
    "wymagania": "Góra na siłowni 3× w tygodniu, niezmiennie, w każdej fazie i każdym tygodniu (w lżejszym tygodniu "
                 "lżej, ale 3×), zawsze jako trzy różne sesje: PUSH (klatka, barki przód/bok, triceps), PULL (plecy "
                 "szerokość i grubość, tylne barki, biceps) i FULL UPPER (cała góra). Tytuły: „Siłka Push”, „Siłka "
                 "Pull”, „Siłka Full Upper”. Pod V-taper priorytet: szerokie plecy (ściąganie/podciąganie) i barki "
                 "boczne/tylne. Na KAŻDYM treningu siłowym (także nóg) na końcu brzuch 2–3 ćwiczenia (spięcia na "
                 "wyciągu, unoszenie nóg w zwisie, reverse crunch, rollout, deska) — ale mało ćwiczeń na mięśnie "
                 "skośne/boczne (woodchop, deska bokiem, skłony boczne): max 1 krótkie w tygodniu, bez obciążenia, "
                 "bo poszerzają talię i nie pomagają w V-taperze. Nogi na siłowni prowadź wg bazy wiedzy (sekcja nóg).",
    "tierlista": {                  # tierlista ćwiczeń siłowych Antka (19.11), edycja w Ustawieniach; X = wykluczone
        "S": ["Wyciskanie hantli na skosie dodatnim", "Wiosłowanie hantlem", "Wyciskanie hantli nad głowę",
              "Unoszenie hantli bokiem", "Rozpiętki", "Uginanie bicepsa z hantlami", "Uginanie bicepsa na wyciągu",
              "Uginanie bicepsa ze sztangą", "Prostowanie tricepsa na wyciągu", "Rumuński martwy ciąg — RDL",
              "Martwy ciąg", "Przysiad ze sztangą", "Suwnica jednonóż", "Bułgary", "Wspięcia na palce",
              "Prostowanie nóg na maszynie", "Uginanie nóg siedząc", "Spięcia brzucha na wyciągu", "Woodchop na wyciągu"],
        "A": ["Wiosłowanie sztangą", "Ściąganie drążka wyciągu górnego", "Dipy na maszynie z pomocą",
              "Wyciskanie hantli na ławce płaskiej", "Odwrotne rozpiętki", "Uginanie młotkowe",
              "Uginanie hantli z supinacją", "Odwodzenie bioder na maszynie", "Przywodzenie bioder na maszynie",
              "Wspięcia na palce siedząc", "Uginanie nóg leżąc", "Hip thrust", "Wykroki", "Unoszenie nóg w zwisie",
              "Rollout z kolan — częściowy zakres jest akceptowany"],
        "B": ["Pompki", "Podciąganie, jeśli technika i dostęp do sprzętu pozwalają", "Wyciskanie hantli neutralnym chwytem",
              "Face pull", "Uginanie bicepsa na ławce skośnej", "Goblet squat", "Wykroki chodzone", "Step-up",
              "Przysiad bułgarski z mniejszym ciężarem", "Most biodrowy", "Plank", "Plank ze zwiększonym zakresem trudności"],
        "C": ["Prostowanie tricepsa hantlem zza głowy", "Francuskie wyciskanie", "Dipy bez maszyny",
              "Unoszenie nóg w podporze", "Side plank", "Ćwiczenia wykonywane na niestabilnym podłożu",
              "Ćwiczenia izolowane, które dublują już dobrze wykonany ruch"],
        "X": ["Szrugsy — nie chcę celowo rozbudowywać kapturów", "Uginanie bicepsa na modlitewniku",
              "Wyciskanie na maszynie o wymuszonej trajektorii", "Dipy bez pomocy, jeśli nie ma bezpiecznej kontroli ruchu",
              "Dwa ćwiczenia na triceps bezpośrednio po sobie",
              "Side plank jako stały element — głównie czuję bark, a nie brzuch",
              "Rollout z pełnego zakresu, jeśli technika się rozpada",
              "Dodawanie serii słabszej stronie przy różnicy aktywacji"],
    },
    "zasady_silka": "Główne ćwiczenia wykonuję po kolei, bez zbędnego przemieszczania się.\n"
                    "Mieszanie serii stosuję głównie w treningach góry ciała.\n"
                    "Ćwiczenia na nogi wykonuję po kolei.\n"
                    "Ćwiczenia na triceps rozdzielam ćwiczeniem innej partii.\n"
                    "Na każdym treningu siłowym ma być rozgrzewka i konkretne przerwy.\n"
                    "Na treningach nóg na końcu są odwodzenie i przywodzenie bioder: 2 serie po 12–20 powtórzeń, kontrolowanie, bez upadku.\n"
                    "Przy wiosłowaniu hantlem zaczynam od prawej strony.\n"
                    "Wyrównuję liczbę powtórzeń po obu stronach.\n"
                    "Nie dodaję dodatkowych serii słabszej stronie.\n"
                    "Nie zwiększam ciężaru, jeśli technika lub tor ruchu nie są stabilne.",
    "ankieta": {},                  # odpowiedzi z ankiety startowej (cele, terminy, dni, sprzęt, styl planu…)
    "start_gotowy": False,          # ankieta + dopytanie zakończone → wolno planować
}


def ustawienia():
    p = DANE / "ustawienia.json"
    u = dict(DOMYSLNE)
    if p.exists():
        try:
            u.update(json.loads(p.read_text(encoding="utf-8")))
        except ValueError:
            pass
    return u


def zapisz_ustawienia(zmiany):
    u = ustawienia()
    u.update({k: v for k, v in zmiany.items() if k in DOMYSLNE})
    DANE.mkdir(parents=True, exist_ok=True)
    tmp = DANE / "ustawienia.json.tmp"
    tmp.write_text(json.dumps(u, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DANE / "ustawienia.json")
    return u
