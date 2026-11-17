# Instrukcje dla Claude (repozytorium Antka)

## 🧠 Start każdej sesji
1. Przeczytaj **`pamiec/MAPA.md`**: mapa urządzeń i projektów, pętla pracy i tabela „gdzie szukać”.
2. Przeczytaj **`pamiec/zasady.md`**: czego nie wolno. Repo jest publiczne, a na Pi grają znajomi.
3. Połącz się z Pi: hook startowy wypisuje stan Tailscale. Jeśli poda link `login.tailscale.com/a/...`, od razu daj
   go użytkownikowi. Potem `ssh pi hostname`.
4. Pisz z użytkownikiem **po polsku**, krótko. Aplikację ma po angielsku, więc nazwy przycisków podawaj po angielsku.

## Koniec pracy
Uzupełnij `pamiec/`: wpis w `sesje.md`, popraw `do-zrobienia.md`, nowe ustalenia zapisz w `decyzje.md` lub
`uzytkownik.md`, a zmienione fakty popraw w odpowiednim pliku. Potem commit i push. **Żadnych sekretów w repo.**

## Dokumentacja projektów (czytaj, gdy dotyczy)
| Projekt | Plik | Zasada |
|---|---|---|
| Nauka (kartkówki, quizy) | `PLAN.md` | po zmianie zaktualizuj sekcje 2 i 9; kopia `strona/` = Pi; `sprawdziany.json` najpierw pobierz z Pi |
| Serwer: portal, bot, telefon, Garmin, NAS, zdrowie | `SERWER.md` | przeczytaj przed zmianami w `pi/app.py` albo w usługach |
| Progres sylwetki | `PROGRES.md` | zdjęcia prywatne: tylko Pi i NAS, nigdy repo |
| Łazik (Pi 5, LoRa) | `lazik/LAZIK.md`, `lazik/PRZEKAZANIE.md` | przed ruszaniem silnikami zapytaj |

Przed wgraniem pliku na Pi porównaj md5 kopii z Pi i z gita, żeby nie nadpisać zmian zrobionych na Pi.
