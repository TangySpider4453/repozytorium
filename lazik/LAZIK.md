# Łazik: projekt i strony na Pi (opis dla kolejnych sesji)

Szkolny projekt autonomicznego łazika z łącznością LoRa. Pisz z użytkownikiem po polsku. **Nie używamy nazwiska
nauczyciela** w żadnym materiale. Repozytorium jest **publiczne**: nie wpisuj tu publicznego IP domu, adresu tunelu
Minecrafta, haseł ani kluczy.

Pełny obraz projektu jest w **mapie projektu** (`strona/mapa.html`): architektura (łazik Pi 5 – satelita a2 – stacja
a1), radio (A = 868 MHz w podpasmie 869,4–869,65 MHz, B = 433 MHz na DX-LR03), protokół DTN P0–P5 z HMAC,
autonomia (OAK-D Lite, slam_toolbox, Nav2, Hailo-8), etapy E0–E11, sprzęt, historia koncepcji, ryzyka, otwarte decyzje.
**Stan: przed E0/E1**, nowego kodu jeszcze nie ma.

## Trzy strony projektu na Pi 4B (rozwijamy je razem z projektem)

| Strona | Adres (tylko Tailscale) | Plik na Pi | Kopia w repo |
|---|---|---|---|
| Koncepcja | http://100.108.241.58/strony/lazik/ | `~/portal/sites/lazik/index.html` | `strona/index.html` (**jeszcze nie pobrana**) |
| Lista zakupów | http://100.108.241.58/strony/lazik/zakupy.html | `~/portal/sites/lazik/zakupy.html` | `strona/zakupy.html` (**jeszcze nie pobrana**) |
| Mapa projektu | http://100.108.241.58/strony/lazik/mapa.html | `~/portal/sites/lazik/mapa.html` | `strona/mapa.html` (**jeszcze nie wgrana na Pi**) |

- Lista zakupów zapisuje stan (do kupienia / zamówione / mam, notatki) przez `/api/zakupy` w `~/portal/app.py`, dane
  w `~/portal/data/zakupy.json`. **Użytkownik sam odhacza pozycje**, więc danych nie nadpisuj i nie trzymaj w repo.
- Kopia `pi/app.py` w repo jest **starsza** niż na Pi (nie ma `/api/zakupy`, dodane 2026-10-26 z PC). Przed zmianą
  portalu pobierz aktualny `app.py` z Pi. Zasady pracy z portalem i usługami: `SERWER.md` (nie ruszać Minecrafta).
- Nowe pliki w `sites/lazik/` działają od razu, bez restartu portalu. Dioda zdrowia dokleja się sama przed `</body>`.

## Jak pracować ze stronami

1. Na początku sesji (Tailscale musi działać, patrz `PLAN.md` sekcja 4): pobierz aktualne strony z Pi, bo użytkownik
   lub sesja na PC mogły je zmienić:
   `scp pi:/home/tonyg/portal/sites/lazik/{index.html,zakupy.html,mapa.html} lazik/strona/`
2. Zmień pliki w `lazik/strona/`, wgraj na Pi (`scp lazik/strona/<plik> pi:/home/tonyg/portal/sites/lazik/`),
   sprawdź `curl -s -o /dev/null -w '%{http_code}' http://raspberrypi/strony/lazik/<plik>` (ma być 200).
3. Każdą nową decyzję wpisz w mapę (sekcja, której dotyczy, plus „Historia koncepcji”), zaktualizuj „Stan”
   poniżej i dopisz wiersz do dziennika. Commit + push.

Bez Tailscale: przygotuj pliki w repo i powiedz użytkownikowi, że trzeba je wgrać na Pi. Sam może to zrobić przez
udział Samba `\\100.108.241.58\tonyg` do `portal\sites\lazik\`.

## Do zrobienia przy pierwszym dostępie do Pi

- [ ] wgrać `strona/mapa.html` na Pi i sprawdzić w przeglądarce,
- [ ] pobrać `index.html` i `zakupy.html` do `strona/` (sprawdzić, czy nie ma w nich publicznego IP ani nazwiska),
- [ ] na stronie koncepcji i liście zakupów dodać linki do mapy (i odwrotnie są już w mapie),
- [ ] pobrać aktualny `app.py` do `pi/app.py`.

## Malinki projektu

| | Rola (propozycja) | Tailscale | LAN | Kod |
|---|---|---|---|---|
| a1 `rpi-zero2w-a1` | stacja domowa | 100.124.7.125 | 172.23.0.27 | `/home/rpi/Documents/lora_field/` |
| a2 `rpi-zero2w-a2` | satelita | 100.89.71.96 | 172.23.0.21 | jw., usługa `lora_field.service` |

Użytkownik `rpi`, Debian 13, Python 3.13. Klucz SSH z chmury na nich nie działa; do ustalenia: Tailscale SSH
(`sudo tailscale set --ssh`) albo skok przez Pi 4B.

Dokumentacja źródłowa jest u użytkownika na PC (`C:\Users\tonyg\Documents\claude kopia\`): plik główny projektu
(części 1–3), dziennik kodu (tylko kod sprawdzony na sprzęcie, wpisy z datą i godziną `RRRR-MM-DD GG:MM`, zdjęcia
`RRRR-MM-DD_GGMM_opis.jpg`) i kopia sprzed 2026-10-18. Mapa projektu jest ich streszczeniem.

## Stan

| Data | Co |
|---|---|
| 2026-10-26 | Mapa projektu zrobiona z trzech plików dokumentacji i historii czatu; zapisana w `strona/mapa.html`. Na Pi jeszcze jej nie ma (brak `TS_AUTHKEY` w środowisku chmury). |
