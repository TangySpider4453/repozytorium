# 🏋️ Trener: stałe ustalenia

Czytaj, gdy: zmieniasz planowanie, prompty, dietę, wykresy albo wygląd/JS apki Trener. Stan i otwarte: [trener.md](trener.md).

## Model i działanie
- Claude w Trenerze (i każdy na Pi): domyślnie Haiku, Sonnet do planu/celu/badań, **Opus nigdy**.
- Nie planuje przed ankietą startową (cele + jak ma wyglądać plan) i dopytaniem.
- Planuje wg bazy wiedzy ze źródeł (`trener/trener/wiedza/`, nowe zasady z linkiem) + makrocykl do celu + kontrola reguł
  kodem. Po podaniu celu zawsze szuka źródeł w internecie (`dane/wiedza_cel/`), dopiero potem periodyzacja.
- Cel: rekompozycja do 30.04.2027 bez agresywnego deficytu; rower pod cele kolarskie; sporty + bieg.
- Powiadomienia tylko push z apki; Linphone zapasowo (push nie doszedł, błąd logowania Garmina).
- Dni nazywa słowami (dziś, jutro, w czwartek), nie datami.
- W czacie się nie kłóci: Antek decyduje o czasie; robi zmianę albo daje 1–2 układy z kosztem w jednym zdaniu.
  O planie mówi tylko na podstawie planu.
- Po porannej ocenie snu przegląda najbliższe dni (`korekta_po_snie`): małe zmiany od razu; usunięcie/dodanie jednostki
  idzie do kv `propozycja_planu` (push „❓ Trener pyta”, Zmień / Zostaw). Prośby z czatu zmieniają bez pytania.
- Przeplanowanie z czatu: effort medium, tylko to, czego dotyczy prośba (`zostaw_id`); automatyczne zostaje na high.

## Reguły planu (kod pilnuje)
- Góra 3×/tydz.: Push, Pull, Full Upper; brzuch na końcu każdej siłki; skośne max 1/tydz.
- Nogi 2×/tydz. (`nogi_tyg`), wtorek tylko nogi (`dni_tylko_nogi`); odwodzenie+przywodzenie na końcu; bez szrugsów;
  bez 2 tricepsów pod rząd; `tetno_ciezkie` liczy jednostki intensywne.
- Dwie sesje tylko w czwartek i w jeden dzień weekendu; śr i pt sama siłka. Siłka zawsze pełna, 60–75 min,
  min. 55 min (`silka_min_min`, w deloadzie 80%): lżej = RIR/ciężar.
- Siłka wg tierlisty Antka z Ustawień (S/A najczęściej, wykluczone nigdy).

## Dieta
- Maksymalne **bezpieczne** tempo: deficyt ≤ 500 kcal i ≤ 20%, EA ≥ 35 kcal/kg FFM, białko ~2 g/kg, tłuszcz ≥ 0,8 g/kg
  (`dieta._przytnij`).
- Wydatek dnia = spoczynkowe z Garmina + mediana ruchu dnia (bez treningów) + treningi (zrobione z Garmina, plan z szacunku).
- Czas trwania zawsze h:mm.

## Apka (front)
- Menu: Dziś · Progres · Jedzenie · Dane · Czat; Plan otwierany z Dziś („cały plan” przy nagłówku i przycisk pod dniami), `#waga` → `#progres`; historia treningów jako podzakładka Dane.
- Przewija się `body` (`SKR.scrollTo`/`SKR.scrollTop`), nie okno. iOS 26 standalone: `html { min-height: min(100lvh,
  calc(100% + env(safe-area-inset-top))) }` w styl.css (WebKit 301108). Nie usuwać.
- Liquid Glass: zmienne `--szklo`, `--blask`, `--rozmyj`, `--sprezyna`; `--pierscien` do obwódek wykresów.
  Rogi squircle przez `static/sq.svg`. Bez powiększania (`user-scalable=no`, `touch-action`, blokada `gesture*`;
  nie blokować `touchend`).
- Tło per urządzenie: IndexedDB `trener-tlo` + localStorage `trener:tlo` (prywatne zdjęcie, nie na serwer).
- Aktualizacja: `/wersja` przy powrocie i co 60 s (nie w trakcie pisania/ankiety); dane `/api/wersja` co 60 s (3 s, gdy
  trener pracuje), bez websocketów.
- Animacje: karuzela zakładek, szczegóły rosną z karty; dane z pamięci zamiast „Ładuję…”.
- Wykresy w czacie: Claude daje specyfikację (`wykresy`), apka rysuje; jeden kanał = jeden wykres, bez dwóch osi Y.
- Wykres bloczkowy treningu (`wykresTreningu`): szerokość = czas, wysokość/kolor = strefa z `progi`.
- Logowanie: jedno hasło z portalem (skrót w `~/portal/dane/dostep.json`), ciasteczka `trener_klucz`/`portal_sesja`
  w obie strony.
