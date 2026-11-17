# Dziennik sesji

Najnowsze na górze. Format: `RRRR-MM-DD (gdzie)`: co zrobiono; co zostało.

- **2026-11-17 (chmura, 4c)**: Claude Code na Pi: `~/.claude/settings.json` = `autoCompactWindow` 200000 + env `CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS=100000` (kompakt po ~1 h bezczynności, przed wygaśnięciem cache). Interaktywny `claude` na Pi nie jest zalogowany (token tylko w env usług). W chmurze tę zmienną Antek musi dodać sam w Settings środowiska (sesja nie może).
- **2026-11-17 (chmura, 4b)**: Zbudowano apkę **Trener** (`trener/`, Pi `~/trener/`): sync Garmina (pełna historia
  od 2021 w tle), analizy/plan/czat przez Claude (`--json-schema`), generator treningów rower/bieg/siłka (test: Garmin
  przyjął i usunął 3 treningi próbne), push VAPID + Linphone, PWA przez `tailscale serve` HTTPS. Testy: plan 44 s,
  analiza 22 s, czat 13 s. Timer działa, pierwsza poranna analiza wysłana. Czeka na cele Antka.
  Potem: baza wiedzy z badań (6 plików), makrocykl (`cel.py`), kontrola planu kodem; test na celu próbnym OK, usunięty.
  Potem: ankieta startowa + dopytanie przez Claude (`start.py`); planowanie dopiero po niej. Test OK, wyczyszczony.
  Potem: dostęp z internetu: klucz urządzenia (ciasteczko) dla żądań z Funnel — gotowe; włączenie Funnel zablokowane
  przez klasyfikator → czeka na Antka.
  Potem: badania pod cel (`badania.py`, Claude z WebSearch na Pi): test XCO 5 tematów, 25 źródeł działających, 5,5 min; wyczyszczony.
- **2026-11-17 (chmura, 4)**: Start z mózgu. Hook połączył Tailscale sam (`TS_AUTHKEY`), `ssh pi` wymagał linku
  „check” (podany, zatwierdzony). Przegląd Pi 4 09:23: wszystko zgodne z `uslugi.md` (45 °C, 0x0, RAM 1,8 GB, dysk 61%,
  kopia 02:00 OK). Na prośbę Antka oznaczono incydent `rtg-garmin-teraz` (05.11) jako przejrzany przez
  `POST /api/zdrowie/przejrzane` z `{"id": …}` → zdrowie: 0/0. Usunięto testowe modele Ollamy
  `qwen3:4b`, `qwen3:1.7b`, `llama3.2:3b` (nieużywane w kodzie ani w env) → dysk 61% → 51%; zostały qwen2.5:1.5b/3b i moondream.
  Stary token Claude przestał działać („organization has disabled Claude subscription access”) → nowy token:
  `claude setup-token` w tmux na Pi, Antek dał link→kod na czacie, token zapisany prosto do `claude.env` (kopia
  `.bak_2026-11-17`), test OK, restart przez `bez_rozmowy.sh` 09:29:54. Zapasowo jest `pi/bot/nowy_token.sh` (w `~/bot/`).
- **2026-11-17 (chmura)**: Podłączono repo do sesji. Tailscale nie działa: brak `TS_AUTHKEY` i sieć „Limited”
  blokuje hosty Tailscale; podano użytkownikowi instrukcję (angielskie nazwy w aplikacji). Utworzono `pamiec/` i
  wpisano do `CLAUDE.md`, że sesje mają z niej korzystać. Użytkownik ustawił sieć i klucz; połączono przez link
  logowania, `ssh pi` działa. Uwaga: `powernukkitx` (Minecraft) był `inactive` — zgłoszone użytkownikowi, nieruszane.
- **2026-11-17 (chmura, 3)**: Scalono `claude/nauka-z-claude`, `lazik-mapa` i `claude/pamiec` w gałąź domyślną
  (konflikt tylko w dzienniku `PLAN.md`). Nowy `CLAUDE.md` = start od mózgu. Hook startowy wypisuje stan Tailscale
  albo link logowania.
- **2026-11-17 (chmura, 2)**: Przegląd Pi 4 (wszystko zdrowe, Minecraft wyłączony celowo) i kopii ze starego konta
  (`Serwerek`, `Łazik`). Odkryto, że prawdziwy stan jest na gałęziach `claude/nauka-z-claude` i `lazik-mapa`.
  Zbudowano mózg: `MAPA.md` + węzły (zasady, urządzenia, usługi, repo, projekty). Hasła z kopii nieczytane.
- **2026-10-19 – 2026-11-16 (stare konto)**: serwer, nauka, bot, telefon, Garmin — `Serwerek/PRZEKAZANIE.md`;
  łazik — `Łazik…/PRZEKAZANIE.md` (kopie na Pi).
- **2026-10-19 – 2026-10-22**: historia wcześniejszych prac w dziennikach `PLAN.md` (sekcja 9), `PROGRES.md`, `SERWER.md`.
