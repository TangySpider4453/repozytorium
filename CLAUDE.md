# Instrukcje dla Claude (repozytorium Antka)

## 🧠 Start każdej sesji
1. Przeczytaj **`pamiec/MAPA.md`**: krótki router, pętla pracy i sedno o użytkowniku. Pliki z `pamiec/tematy/` otwieraj
   dopiero, gdy zadanie ich dotyczy; `pamiec/archiwum/` tylko w razie potrzeby (oszczędza tokeny).
2. Przeczytaj **`pamiec/zasady.md`**: czego nie wolno. Repo jest publiczne, a na Pi grają znajomi.
3. Połącz się z Pi: hook startowy wypisuje stan Tailscale. Jeśli poda link `login.tailscale.com/a/...`, od razu daj
   go użytkownikowi. Potem `ssh pi hostname`.
4. Pisz z użytkownikiem **po polsku**, krótko. Aplikację ma po angielsku, więc nazwy przycisków podawaj po angielsku.

## Koniec pracy
W pliku tematu z `pamiec/tematy/`: wpis w „Dziennik” (max ~6, starsze do `archiwum/`), popraw „Otwarte”, nowe
ustalenia do „Ustalenia”, zmienione fakty popraw. Nowy temat = nowy plik + wiersz w routerze MAPA. Potem commit i push.
**Żadnych sekretów w repo.**

## Dokumentacja projektów (czytaj, gdy dotyczy)
| Projekt | Plik | Zasada |
|---|---|---|
| Nauka (kartkówki, quizy) | `PLAN.md` | po zmianie zaktualizuj sekcje 2 i 9; kopia `strona/` = Pi; `sprawdziany.json` najpierw pobierz z Pi |
| Serwer: portal, bot, telefon, Garmin, NAS, zdrowie | `SERWER.md` | przeczytaj przed zmianami w `pi/app.py` albo w usługach |
| Progres sylwetki | `PROGRES.md` | zdjęcia prywatne: tylko Pi i NAS, nigdy repo |
| Łazik (Pi 5, LoRa) | `lazik/LAZIK.md`, `lazik/PRZEKAZANIE.md` | przed ruszaniem silnikami zapytaj |

Przed wgraniem pliku na Pi porównaj md5 kopii z Pi i z gita, żeby nie nadpisać zmian zrobionych na Pi.
