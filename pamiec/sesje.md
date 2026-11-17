# Dziennik sesji

Najnowsze na górze. Format: `RRRR-MM-DD (gdzie)`: co zrobiono; co zostało.

- **2026-11-17 (chmura, 4)**: Start z mózgu. Hook połączył Tailscale sam (`TS_AUTHKEY`), `ssh pi` wymagał linku
  „check” (podany, zatwierdzony). Przegląd Pi 4 09:23: wszystko zgodne z `uslugi.md` (45 °C, 0x0, RAM 1,8 GB, dysk 61%,
  kopia 02:00 OK). Na prośbę Antka oznaczono incydent `rtg-garmin-teraz` (05.11) jako przejrzany przez
  `POST /api/zdrowie/przejrzane` z `{"id": …}` → zdrowie: 0/0.
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
