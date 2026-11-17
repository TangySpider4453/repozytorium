# Pamięć Claude: indeks

Wspólna pamięć wszystkich sesji Claude (chmura, komputer, iPad). **Każda sesja czyta ten plik na starcie**,
a na końcu pracy uzupełnia pamięć. Pamięć jest krótka i wskazuje na szczegóły, zamiast je powtarzać.

| Plik | Co tam jest |
|---|---|
| [uzytkownik.md](uzytkownik.md) | kim jest użytkownik, jak lubi pracować, preferencje |
| [projekty.md](projekty.md) | mapa projektów i gdzie szukać szczegółów (`PLAN.md`, `PROGRES.md`, `SERWER.md`) |
| [dostep.md](dostep.md) | jak sesja dostaje się do Raspberry Pi i GitHuba (bez sekretów) |
| [decyzje.md](decyzje.md) | ustalenia i zasady na stałe, z datą i powodem |
| [do-zrobienia.md](do-zrobienia.md) | otwarte sprawy, pomysły, rzeczy do sprawdzenia |
| [sesje.md](sesje.md) | dziennik sesji: data, co zrobiono, co zostało |

## Zasady pisania pamięci
1. **Nigdy żadnych sekretów** (klucze, hasła, tokeny) i nic ze zdjęć/danych prywatnych z `progres`.
2. Wpis = data `RRRR-MM-DD` + konkret. Bez lania wody.
3. Fakt się zmienił → popraw stary wpis (nie dopisuj sprzecznego). Coś przestało obowiązywać → przenieś do historii
   z dopiskiem „nieaktualne od …”.
4. Szczegóły techniczne projektu idą do jego dokumentu (`PLAN.md` itd.); tu tylko wskazówka, gdzie są.
5. Na koniec sesji: dopisz wpis w `sesje.md`, popraw `do-zrobienia.md`, a nowe ustalenia z rozmowy zapisz w
   `decyzje.md` albo `uzytkownik.md`.
