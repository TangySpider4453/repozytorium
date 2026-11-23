# 🏋️ Trener: apka treningowa (Pi 4 `~/trener/`)

Czytaj, gdy: Trener, Garmin, zegarek, plan treningów, jedzenie/kalorie, czat trenera, wygląd apki.
Kod i opis: `trener/README.md`, `SERWER.md`. Stałe ustalenia (reguły planu, wygląd, iOS): [trener-ustalenia.md](trener-ustalenia.md),
czytaj je przed zmianą planowania, promptów albo CSS/JS apki.

## Stan
- Działa od 17.11. Zastąpiła RestOrTrain (stary most usunięty 18.11). Dane Garmina z całej historii, analizy i plany
  Claude, treningi same idą na zegarek, push, czat, dziennik kalorii, tło per urządzenie.
- Logowanie: to samo hasło co portal albo parowanie kodem (`python -m trener kod` na Pi). Z internetu przez Funnel.
- Ustalenia osobiste (profil, strefy, wzór tygodnia) są tylko na Pi: `dane/ustawienia.json` → `wymagania`.

## Otwarte
- [ ] Antek: przejrzeć na fēniksie 7 trening „Test – tylne barki” (ćwiczenia A–G), które mają własną nazwę i animację.
  Potem zmienić mapowanie „odwodzenie ramion w opadzie” w `cwiczenia_antka.json` (teraz BENT_OVER_LATERAL_RAISE)
  i usunąć test (id w `~/trener/kopie/test-tylne-barki.id`).
- [ ] Antek: zakończyć stary plan Garmin Coach w Garmin Connect (53 treningi blokują limit; API ich nie usunie).
- [ ] Antek: czy zegarek po synchronizacji pobrał wszystkie treningi i czy usunięte z Connect schodzą z zegarka.
- [ ] Antek: mapowanie „Rozpiętki” (hantle vs maszyna); karta „Oceń nowe ćwiczenia” po siłce.
- [ ] Antek: przybliżanie przebiegu dwoma palcami na iPhonie (gdy nie działa, zostają przyciski − + ‹ › „cały”).
- [ ] Sprawdzić, czy `trener-historia` skończył: `kv.historia_postep == "gotowe"`.
- [ ] Antek: terminy ferii/egzaminów/zawodów (do periodyzacji).
- [ ] Ok. 6–13.12: czy spadek masy (średnia 7 dni) mieści się w 0,5–0,7%/tydz. i czy cel kcal ma sens.
- Pomysły: plan vs wykonanie w analizach, power curve, FTP z testu, pływanie.

## Dziennik (najnowsze na górze; starsze: `archiwum/sesje-*.md`)
- 2026-11-23: Jedzenie: karta „Ten tydzień” (pon–nd, `tydzienKcal`): słupki dni, średnia kcal/dzień z dni zamkniętych,
  bilans vs cel, ile dziennie do niedzieli żeby tydzień wyszedł na cel; plus podsumowanie poprzedniego tygodnia.
  (2) Ta sama karta też dla białka (`TYDZ` + `tydzienMakro`): „Łącznie: nadwyżka +X / brakło X” kcal i g (dni zamknięte),
  poprzedni tydzień też z łącznym bilansem. `dieta.historia` zwraca też `cel_b` (cel białka z `makro_cel_<dzień>`).
  (3) Kolejność w Jedzeniu: posiłki → Ostatnie 2 tygodnie → Cel na dziś → Ten tydzień (na samym dole).
- 2026-11-22 (9): Progres: przełączniki „Średnia 7 dni” Wł./Wył. (`wagaTrend`) i „Skład” Razem/Osobno (`wagaSklad`,
  osobno = dwa wykresy z jedną osią); oba w localStorage.
- 2026-11-22 (8): Masa i skład na wspólnej osi dat (`osW`): ten sam zakres od–do; dni bez wartości puste, seria `lacz: true`
  łączy punkty ponad brakami w `rysujLinie`.
- 2026-11-22 (7): Progres: linia ciągła = każdy pomiar, przerywana = średnia 7 dni (masa, tłuszcz, mięśnie); w dymku i legendzie
  kreski w stylu linii zamiast kropek, kropka średniej pusta w środku.
- 2026-11-22 (6): Skład ciała na dwóch osiach (tłuszcz lewa, mięśnie prawa, każda na całą wysokość); `wyk` linia obsługuje `os: "prawa"`.
- 2026-11-22 (5): wykresy wagi i składu: przełącznik Każdy pomiar / Średnia tyg. / Średnia mies. (zapamiętany).
- 2026-11-22 (4): dotknięcie zdjęcia w podglądzie otwiera pełny ekran z przybliżaniem (szczypanie, przesuwanie, podwójne stuknięcie).
- 2026-11-22 (3): Progres ma podzakładki Pomiary / Zdjęcia (zdjęcia pogrupowane po dniu pomiaru, „+ zdjęcie” do dnia); w „Nowy pomiar” wiele zdjęć naraz z wyborem strony.
- 2026-11-22 (2): na pasku Progres (waga, skład, link do zdjęć) zamiast Planu; Plan otwiera się z Dziś jako ekran szczegółów.
- 2026-11-22: logowanie hasłem (zakładki Trener / Zaloguj do panelu, parowanie w „details”), karta „🖥️ Panel serwera”
  w Ustawieniach; mocniejszy Liquid Glass; karta „🎨 Tło” (tapeta, ułożenie, suwaki szkła); „Omów” wysyła analizę do czatu.
- 2026-11-21: superserie: 10 s przerwy między ćwiczeniami bez własnej przerwy; test mapowania tylnych barków na zegarku.
- 2026-11-19: menu Dziś · Plan · Jedzenie · Dane · Czat, tierlista, animacje, poprawka czarnego pasa iOS 26,
  trener w czacie mówi tylko na podstawie planu.
- 2026-11-17: start apki, ankieta, korekta po śnie, dziennik kalorii, Liquid Glass, auto-aktualizacja.
