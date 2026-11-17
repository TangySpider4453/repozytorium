# Dostęp (bez sekretów)

## GitHub
- Repo `TangySpider4453/repozytorium`, konto GitHub połączone z Claude (2026-11-17).

## Raspberry Pi przez Tailscale (sesja w chmurze)
- Hook `.claude/hooks/session-start.sh` instaluje Tailscale, ustawia alias `ssh pi` i łączy kluczem ze zmiennej
  środowiska **`TS_AUTHKEY`** (ustawia ją użytkownik w ustawieniach środowiska Claude; klucz nigdy w repo ani na czacie).
- Środowisko potrzebuje dostępu do sieci Tailscale (`*.tailscale.com`, serwery DERP). Przy dostępie „Limited” bez tych
  hostów wszystko kończy się 403 z proxy (sprawdzone 2026-11-17).
- Sprawdzenie: `tailscale status`, `ssh pi hostname`. SSH na Pi jest w trybie „check”: przy pierwszym połączeniu podaj
  użytkownikowi link `login.tailscale.com/a/...` do zatwierdzenia (wygasa po kilku minutach).
- Gdy `tailscaled` padnie: uruchom ponownie z tym samym `--state`, klucz niepotrzebny.
- Pełny opis: `PLAN.md`, sekcja 4 („Sesja w chmurze a Pi”).

## Bez Tailscale
- Przygotuj pliki w repo; wgranie na Pi zrobi sesja na komputerze użytkownika albo on sam przez Sambę
  `\\100.108.241.58\tonyg`. Powiedz mu wprost, że trzeba jeszcze wgrać.
