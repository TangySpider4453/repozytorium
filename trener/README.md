# Trener — własny RestOrTrain (webapka na Pi 4)

Dane z Garmin Connect (nieoficjalne API, `garminconnect`) → SQLite → analizy i plany od Claude → treningi
(rower, bieg, siłka) automatycznie na zegarek/Edge → powiadomienia (push w webapce + Linphone) → czat z trenerem.

## Gdzie co jest (Pi 4, `~/trener/`)
| Część | Plik |
|---|---|
| synchronizacja (dni: sen, HRV, podsumowanie, gotowość, status; aktywności + serie siłowe) | `trener/sync.py`, wartości dnia `trener/dane.py` |
| kontekst dla Claude (14 dni, aktywności 28 dni, tygodnie, miesiące z całej historii, plan, pamięć) | `trener/kontekst.py` |
| Claude CLI (`--json-schema`, bez narzędzi, pusty katalog) | `trener/ai.py` |
| **baza wiedzy** (metodyka ze źródeł: periodyzacja, rozkład intensywności, strefy Coggana, biblioteka jednostek,
siłownia dla kolarza, bieg, HRV/sen, młody sportowiec — z linkami do badań) | `trener/wiedza/*.md` |
| **ankieta startowa** (7 kroków: cele, terminy, dni, sprzęt, siłka/bieg, jak ma wyglądać plan, zdrowie) → Claude dopytuje (0–4 pytania z opcjami) → dopiero wtedy makrocykl i plan (`start_gotowy`) | `trener/start.py`, `#start` w apce |
| **badania pod cel** (Claude ocenia, czy baza pasuje do celu, co brakuje/budzi wątpliwości; ZAWSZE szuka źródeł w internecie: WebSearch/WebFetch, 2–5 tematów → `dane/wiedza_cel/*.md`; linki sprawdzane kodem, plik bez działającego źródła odrzucany). Uruchamiane przy każdej zmianie celu przed makrocyklem; ekran „📚 Źródła trenera” (`#wiedza`) | `trener/badania.py` |
| **makrocykl** (fazy do celu: godziny, intensywność, sesje kluczowe, testy FTP; przebudowa przy zmianie celów) | `trener/cel.py` |
| analizy: rano (po śnie), po treningu, tydzień (pon.) | `trener/analiza.py` |
| plan na 7 dni wg fazy makrocyklu i bazy wiedzy + **kontrola kodem** (skok objętości > 30%, > 3 akcenty, akcenty dzień po dniu, < 48 h po ciężkich nogach, widełki fazy) → jedna poprawka przez Claude | `trener/plan.py` |
| plan → JSON treningu Garmin (strefy tętna, moc, tempo, kadencja; siłka z listą ćwiczeń) | `trener/budowa.py`, `trener/zasoby/` |
| wysyłanie / usuwanie (TYLKO ze znacznikiem `auto: trener` w opisie) | `trener/zegarek.py` |
| czat (akcje: przeplanuj, zapamiętaj, ustawienia, dane z dowolnego okresu) | `trener/czat.py` |
| push (VAPID w `dane/vapid.json`) + kolejka bota | `trener/powiadom.py` |
| cykl co 15 min + szybki co 1 min | `trener/cykl.py`, `systemd/trener-cykl.*` |
| webapka (Flask 127.0.0.1:8095) + PWA | `trener/web.py`, `static/` |

## Uruchamianie
- `trener-web.service` (Flask) i `trener-cykl.timer` (co 15 min), `trener-szybki.timer` (co minutę; nowy trening → cykl), oba z `EnvironmentFile=/etc/serwerek-bot/claude.env`.
- Na zewnątrz tylko w tailnecie: `sudo tailscale serve --bg --https=443 http://127.0.0.1:8095` (certyfikat Let's Encrypt
  od Tailscale). Adres apki: `https://<nazwa Pi w tailnecie>/` (zapisany też w bazie, `kv.adres_apki`; nie w repo).
- Ręcznie: `.venv/bin/python -m trener sync | historia | dzien RRRR-MM-DD | cykl | analiza rano | plan "prośba"`.
  Polecenia z Claude potrzebują tokenu: `sudo systemd-run --uid=tonyg -p EnvironmentFile=/etc/serwerek-bot/claude.env
  -E HOME=/home/tonyg --wait --pipe ...`.
- Token Garmina w `dane/garmin_tokens/` (700/600, poza gitem; nowe logowanie: Antek w terminalu `python -m trener login`) (logowanie z blokadą `dane/garmin.lock`).

## Dostęp z internetu (bez Tailscale w telefonie)
- Włączone 17.11: `sudo tailscale funnel --bg --https=443 http://127.0.0.1:8095` (UWAGA: samo `--bg 443` kieruje na
  port 443, nie na apkę). Tailscale Funnel, darmowy, ten sam adres ts.net → PWA i push bez zmian. Wyłączenie: `sudo tailscale funnel --https=443 off`
  (zostaje `serve` tylko w tailnecie). Jeśli Funnel wymaga zgody w tailnecie, komenda poda link do panelu.
- Ochrona: żądania z Funnel (nagłówek `Tailscale-Funnel-Request`) do `/api/*` tylko z zapamiętanym urządzeniem
  (ciasteczko `trener_klucz`, 400 dni, w bazie sha256 w tabeli `urzadzenia`). Urządzenie zapamiętuje się samo przy
  otwarciu apki przez tailnet. ⚙️ → „Wyloguj inne urządzenia”.
- Parowanie bez Tailscale: `python -m trener kod` na Pi → 8 znaków, jednorazowy, 15 min, 5 prób → wpisać na ekranie
  „Zapamiętaj to urządzenie”. (iPhone z włączonym Tailscale i tak łączył się przez Funnel, więc auto-zapamiętanie nie działało.)
- **Hasło (od 22.11):** ekran logowania ma zakładki „Trener” i „Zaloguj do panelu”; hasło to samo co do portalu
  (skrót tylko w `~/portal/dane/dostep.json`, zmiana: `portal-haslo`, w repo go nie ma). `POST /api/logowanie` daje
  `trener_klucz` i `portal_sesja` (5 złych = 5 min blokady na adres z `X-Forwarded-For`). Trener przyjmuje też samo
  `portal_sesja`, a portal samo `trener_klucz` (ten sam host ts.net, ciasteczka nie zależą od portu) → przełączanie
  bez logowania: ⚙️ „Przejdź do panelu” → `:8443`, w portalu link „🏋️ Trener” (`/trener`). Kod parowania nadal działa
  (ukryty pod „Mam kod parowania”).
- Push działa bez Tailscale (idzie przez serwery Apple); Tailscale/Funnel potrzebny tylko do otwarcia apki.

## iPhone
Safari → adres apki → Share → **Add to Home Screen** → otwórz z ekranu głównego → ⚙️ → **Włącz powiadomienia**.
(Push w webapkach iOS działa tylko z ekranu głównego, iOS 16.4+.)

## Dane (`dane/`, poza gitem)
`trener.db` (surowe odpowiedzi skompresowane zlib, aktywności, dni, analizy, plan, czat, push), `ustawienia.json`,
`vapid.json`.
