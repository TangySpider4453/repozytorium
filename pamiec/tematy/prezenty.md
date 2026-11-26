# Prezenty (apka dla dziewczyny)

Pełna dokumentacja: `SERWER.md` → „Prezenty”. Kod: `prezenty/`.

## Ustalenia
- Osobny adres: Funnel na porcie 10000 → `127.0.0.1:8097`. Nie ruszać Funneli 443 i 8443.
- Treść prezentów, klucze, VAPID i pliki tylko na Pi (`~/prezenty/dane/`). Linki z kluczami tylko na czacie.
- Ekran główny = lista prezentów (karty); kolejne prezenty dodaje się jako nowe karty/widoki.
- Kalendarz: dziś na górze (pełna szerokość), potem „Wkrótce”, na końcu „Minione”. Telefon i iPad.
- Push jak w Trenerze (pywebpush + VAPID) + `setAppBadge`. iOS: push działa tylko z apki dodanej do ekranu początkowego.
- Nikomu nic nie wysyłać bez zgody: linki Antek wysyła sam.

## Otwarte
- Antek wypełnia 24 okienka w `/admin` (do 1.12).
- Push nie testowany end-to-end: „Test push do mnie” z apki admina na ekranie początkowym.
- Prezent nr 2: karta „Wkrótce” czeka na pomysł.

## Dziennik
- 2026-11-26: Zbudowana apka (start + kalendarz adwentowy + admin), wdrożona na Pi, Funnel :10000.
