"""
Test szybkich odpowiedzi (bez Pi i bez sieci): python3 pi/bot/test_szybkie.py
Każde zdanie musi trafić w oczekiwaną intencję (None = ma iść do Claude); na końcu przykładowe odpowiedzi na danych testowych.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import szybkie  # noqa: E402

szybkie.NAUCZONE = Path("/nonexistent/szybkie_nauczone.json")

PRZYPADKI = {
    "pierwsza_lekcja": [
        "o której zaczynam", "o której zaczynam jutro", "O której jutro zaczynam?", "na którą jutro do szkoły", "na którą jutro",
        "o której zaczynam lekcje", "o której zaczynam lekcje jutro", "o której jutro zaczynam lekcje", "kiedy zaczynam jutro",
        "o której mam pierwszą lekcję", "o której mam pierwszą lekcję jutro", "kiedy pierwsza lekcja", "pierwsza lekcja jutro",
        "pierwsza lekcja", "jaka jest pierwsza lekcja jutro", "co mam na pierwszej lekcji", "co mam na pierwszej lekcji jutro",
        "o której zaczynam w poniedziałek", "o której zaczynam w piątek", "na którą w poniedziałek", "o której mam być w szkole",
        "o której mam być w szkole jutro", "o której muszę być w szkole jutro", "na którą idę do szkoły", "na którą idę jutro do szkoły",
        "o której idę do szkoły", "o ktorej zaczynam", "o ktorej jutro zaczynam", "na ktora jutro", "od której mam lekcje jutro",
        "od której jutro lekcje", "kiedy szkoła jutro", "o której szkoła", "o której mam lekcje jutro", "o której zaczyna się szkoła",
        "o której zaczyna się szkoła jutro", "o której zaczynamy jutro", "na którą mam jutro", "na którą mam w poniedziałek",
        "Hej, o której jutro zaczynam?", "serwerku o której zaczynam jutro", "powiedz mi o której zaczynam jutro",
        "o której mam pierwszą lekcję w przyszły poniedziałek", "start lekcji jutro", "początek lekcji jutro",
        "o której zaczynam dzisiaj", "o której dziś zaczynam", "na którą dzisiaj", "o której mam iść do szkoły jutro",
        "kiedy mam wyjść do szkoły", "o której mam wyjść do szkoły jutro", "pierwsza lekcja w poniedziałek",
    ],
    "ostatnia_lekcja": [
        "o której kończę", "o której kończę jutro", "o której jutro kończę", "o której kończę lekcje", "o której kończę dzisiaj",
        "kiedy kończę", "kiedy kończę lekcje", "o której wracam", "o której wracam jutro", "do której mam lekcje", "do której mam jutro lekcje",
        "do której jutro", "do której mam lekcje w piątek", "ostatnia lekcja", "jaka jest ostatnia lekcja", "kiedy ostatnia lekcja",
        "ostatnia lekcja jutro", "koniec lekcji", "koniec lekcji jutro", "o której mam koniec", "o której jest koniec lekcji",
        "o której wychodzę ze szkoły", "o której kończy się szkoła", "o której kończymy jutro", "o której będę w domu",
        "o której skończę jutro", "do której jestem w szkole", "do której siedzę w szkole jutro", "o ktorej koncze",
    ],
    "ile_lekcji": ["czy mam jutro szkołę", "czy jutro idę do szkoły", "czy mam jutro lekcje", "czy jutro jest szkoła", "mam jutro lekcje",
                   "ile mam lekcji", "ile mam lekcji jutro", "ile lekcji jutro", "ile mam jutro lekcji", "ile lekcji w poniedziałek",
                   "ile godzin lekcji jutro", "ile mam dzisiaj lekcji", "ile lekcji dzisiaj"],
    "plan_dnia": ["jaki mam plan jutro", "jaki plan na jutro", "plan lekcji na jutro", "plan na jutro", "jaki mam plan na poniedziałek",
                  "co mam jutro", "co mam dzisiaj", "co mam jutro w szkole", "co mam jutro na lekcjach", "jakie mam lekcje jutro",
                  "jakie lekcje jutro", "jakie mam lekcje w piątek", "lekcje jutro", "lekcje na jutro", "co jutro w szkole", "plan lekcji",
                  "jaki mam plan", "co będę mieć jutro", "co mam w środę", "rozkład lekcji na jutro", "jakie zajęcia jutro"],
    "teraz_lekcja": ["jaka teraz lekcja", "co mam teraz", "jaka mam teraz lekcję", "co teraz mam", "jaka następna lekcja",
                     "co mam następne", "jaka jest następna lekcja", "co mam po przerwie", "co mam po tej lekcji", "następna lekcja",
                     "kolejna lekcja", "co zaraz mam", "jaką mam teraz", "co mam zaraz", "co mam potem"],
    "sala": ["w jakiej sali mam matmę", "w której sali jest fizyka", "jaka sala na polski", "gdzie mam angielski", "gdzie mam fizykę jutro",
             "w jakiej sali mam następną lekcję", "w której sali mam wf", "gdzie jest chemia"],
    "kiedy_przedmiot": ["kiedy mam matmę", "kiedy mam fizykę", "kiedy mam wf", "kiedy jest angielski", "czy mam jutro matmę",
                        "czy mam matmę jutro", "czy mam wf w piątek", "czy jest jutro chemia", "kiedy następna fizyka",
                        "o której mam polski", "czy mam dziś angielski", "mam jutro wf", "kiedy mam historię", "czy będzie jutro biologia"],
    "zmiany": ["czy są zastępstwa", "zastępstwa", "zastępstwa jutro", "czy mam jakieś zastępstwa", "czy coś jest odwołane",
               "co jest odwołane jutro", "odwołane lekcje", "czy są jakieś zmiany w planie", "zmiany w planie", "czy coś się zmieniło w planie",
               "czy mam wolne jutro", "czy mam okienko", "jakieś zastępstwa jutro", "czy są odwołane lekcje jutro", "zmiany planu"],
    "sprawdziany": ["jakie mam sprawdziany", "czy mam jutro sprawdzian", "czy mam sprawdzian jutro", "sprawdziany w tym tygodniu",
                    "co piszę jutro", "kiedy mam sprawdzian z matmy", "kiedy sprawdzian z fizyki", "najbliższy sprawdzian", "najbliższa kartkówka",
                    "czy mam jakieś kartkówki", "kartkówki jutro", "kiedy kartkówka z fizyki", "z czego mam sprawdzian jutro",
                    "czego mam się uczyć na jutro", "czego się uczyć na jutro", "co muszę powtórzyć na jutro", "testy", "sprawdziany",
                    "czy będą kartkówki jutro", "co piszemy jutro", "następny sprawdzian", "czy mam test jutro", "sprawdzian z polskiego",
                    "ile dni do sprawdzianu z matmy", "za ile dni kartkówka", "za ile jest sprawdzian z polskiego", "ile dni zostało do kartkówki z fizyki"],
    "zadania_domowe": ["co mam zadane", "co mam zadane na jutro", "czy mam zadanie domowe", "zadania domowe", "zadanie domowe na jutro",
                       "czy coś mam zadane", "co jest zadane z polskiego", "prace domowe na jutro", "czy mam coś do odrobienia",
                       "co mam do odrobienia na jutro", "jakie mam zadania domowe"],
    "todo": ["co mam do zrobienia", "co mam do zrobienia dzisiaj", "co jest na liście", "ile mam zadań", "moje zadania", "todo",
             "o czym mam pamiętać", "o czym mam dziś pamiętać", "co muszę dziś zrobić", "jakie mam zadania na liście", "lista zadań"],
    "budzik": ["na którą mam budzik", "o której mam budzik", "czy mam ustawiony budzik", "czy mam nastawiony budzik na jutro",
               "o której mnie obudzisz", "kiedy mnie budzisz", "moje budziki", "na którą mam alarm"],
    "godzina": ["która godzina", "która jest godzina", "jaka jest godzina", "która jest", "godzina", "jaki jest czas"],
    "data": ["jaki będzie jutro dzień", "jaki dzień jest jutro",
             "jaki dziś dzień", "jaki jest dzień tygodnia", "którego dzisiaj mamy", "jaka jest data", "jaka jest dzisiaj data", "jaki mamy dzień"],
    "serwer": ["jak się ma serwer", "jak się czuje serwer", "czy wszystko działa", "stan serwera", "status", "jak tam na serwerze",
               "czy serwer działa", "jak się ma raspberry", "jak z serwerem", "statystyki serwera"],
    "temperatura": ["jaka jest temperatura", "jaka temperatura procesora", "ile stopni ma procesor", "temperatura", "temperatura pi",
                    "jaka jest teraz temperatura procesora", "ile ma stopni", "czy pi się grzeje", "czy procesor się przegrzewa",
                    "jaka temperatura na serwerze", "temp procesora", "sprawcie go jest te paratura na procesorza", "jaka paratura",
                    "ile stopni", "jaka jest temperatura raspberry"],
    "cpu": ["zużycie procesora", "ile zużywa procesor", "jakie jest obciążenie procesora", "obciążenie cpu", "ile procesora",
            "jakie jest zużycie procesora na pi", "procesor", "ile cpu"],
    "ram": ["ile ramu", "ile jest zużycia ramu", "ile wolnej pamięci", "zużycie ramu", "ile jest ramu zajęte", "ram", "ile pamięci jest zajętej",
            "jakie jest zużycie pamięci", "ile wolnego ramu"],
    "dysk": ["ile wolnego miejsca", "ile miejsca na karcie", "ile jest wolnego miejsca na dysku", "czy karta jest pełna", "wolne miejsce",
             "ile zostało miejsca", "ile miejsca na nas", "stan dysku", "ile gb zostało"],
    "uptime": ["od kiedy działa pi", "jak długo działa serwer", "kiedy był ostatni restart", "ile dni działa raspberry", "uptime",
               "od kiedy działa bez przerwy"],
    "zasilanie": ["czy zasilanie jest ok", "czy zasilacz wystarcza", "czy jest throttling", "czy pi zwalnia", "czy są spadki napięcia"],
    "nas": ["czy nas działa", "czy nas jest podłączony", "jak z nasem", "czy pi widzi nas", "stan nasa", "czy synology odpowiada",
            "co tam z nasem"],
    "kopia": ["kiedy była ostatnia kopia", "czy kopia się zrobiła", "czy była kopia", "ostatnia kopia", "stan kopii", "kiedy kopia zapasowa"],
    "usluga": ["czy działa portal", "czy portal działa", "czy tailscale działa", "czy działa vnc", "czy wszystkie usługi działają",
               "czy coś nie działa", "czy telefon działa", "czy działa playit", "czy samba działa", "czy bot działa"],
    "co_obciaza": ["co obciąża procesor", "co zjada ram", "co najbardziej obciąża pi", "jakie procesy zużywają najwięcej", "co zajmuje pamięć"],
    "siec": ["czy jest internet", "jaki jest adres ip", "jakie ip ma pi", "czy pi ma internet", "adres ip"],
    "lokalizacja": ["gdzie jestem", "jaka jest moja lokalizacja", "gdzie mnie widzisz"],
    "minecraft": ["czy minecraft działa", "czy serwer minecraft jest włączony", "ile osób gra na minecraft", "kto gra", "status minecrafta"],
    "poczta": ["czy mam nowe maile", "czy mam jakieś maile", "maile", "co nowego w poczcie", "czy mam ważne maile", "sprawdź pocztę"],
    "autobus": ["kiedy autobus", "kiedy najbliższy autobus", "kiedy jedzie tramwaj", "najbliższy tramwaj", "następny autobus z junikowo",
                "kiedy autobus z junikowo", "czym pojadę", "najbliższy odjazd"],
    "do_domu": ["jak dojadę do domu", "jak wrócę do domu", "czym mogę wrócić do domu", "trasa do domu", "kiedy mam wyjść żeby być w domu",
                "o której mogę wrócić do domu"],
    None: ["napisz mi wypracowanie o kowalu", "o której zaczynam jutro i przypomnij mi o kartkówce", "zrób stronę do nauki z fizyki",
           "co sądzisz o tym planie", "jak się masz", "dzięki", "ok", "zadzwoń do mnie za 10 minut", "gdzie jest mój telefon",
           "mam pytanie", "kiedy będzie lepsza pogoda", "jakie są najlepsze gry", "opowiedz kawał", "przetłumacz na angielski kot",
           "co to jest wielomian", "jak rozwiązać równanie kwadratowe", "wyślij maila do nauczyciela", "co jest", "o której", "co mam",
           "kto to", "mam dość", "gdzie mam iść", "lista zakupów", "co mam zrobić z tym błędem", "co mam powiedzieć mamie", "kiedy wrócisz",
           "jest ok", "mam problem z kodem", "kiedy będzie aktualizacja", "co jest nie tak z serwerem", "jaki jest najlepszy plan na wakacje",
           "kiedy mam iść do lekarza", "czy mam rację", "mam jutro urodziny", "kiedy jest wigilia", "gdzie jest klucz", "co mam dzisiaj zjeść",
           "status zamówienia z allegro", "ile kosztuje bilet", "czy mam gorączkę", "co mam na obiad", "kiedy jest mecz", "gdzie mam pieniądze",
           "napraw temperaturę procesora", "dlaczego procesor się grzeje", "wyłącz nas", "co u nas słychać", "przyjdź do nas jutro",
           "dlaczego nas nie działa", "zrób miejsce na karcie"],
}


def main():
    zle, n = [], 0
    for oczekiwana, zdania in PRZYPADKI.items():
        for z in zdania:
            n += 1
            wyn, _ = szybkie.rozpoznaj(z)
            if wyn != oczekiwana:
                zle.append((z, oczekiwana, wyn))
    for z, o, w in zle:
        print(f"ŹLE: {z!r}: oczekiwano {o}, jest {w}")
    print(f"{n - len(zle)}/{n} poprawnie")
    # odpowiedzi na danych testowych
    jutro = (date.today() + timedelta(days=1)).isoformat()
    plan = [{"data": jutro, "od": "08:20", "do": "09:05", "przedmiot": "matematyka", "sala": "205", "status": "odwołana", "info": ""},
            {"data": jutro, "od": "09:15", "do": "10:00", "przedmiot": "język polski", "sala": "211", "status": "lekcja", "info": ""},
            {"data": jutro, "od": "10:15", "do": "11:00", "przedmiot": "zajęcia wychowawczo - opiekuńcze", "sala": "CKP_4",
             "status": "zastępstwo", "zamiast": "chemia", "info": ""},
            {"data": jutro, "od": "14:00", "do": "14:45", "przedmiot": "fizyka", "sala": "108", "status": "lekcja", "info": ""}]
    dane = {"plan": lambda: plan, "sprawdziany": lambda: [{"data": jutro, "godzina": "14:00", "przedmiot": "fizyka", "rodzaj": "kartkówka",
                                                           "tematyka": "pole elektryczne"}],
            "zadania_domowe": lambda: [{"termin": jutro, "przedmiot": "język polski", "tresc": "zagadnienie nr 44", "zrobione": False}],
            "todo": lambda: [{"tekst": "trening", "termin": None}], "budziki": lambda: ["jutro 06:15"],
            "serwer": lambda: "Serwer OK.", "minecraft": lambda: "Minecraft wyłączony.", "poczta": lambda: "Brak maili.",
            "odjazdy": lambda s: f"odjazdy {s}", "trasa": lambda s: f"trasa {s}"}
    for z in ["o której zaczynam jutro", "o której kończę jutro", "ile mam lekcji jutro", "jaki mam plan jutro", "czy są zastępstwa jutro",
              "co piszę jutro", "co mam zadane na jutro", "czy mam jutro matmę", "w jakiej sali mam fizykę jutro", "która godzina"]:
        print(f"{z} -> {szybkie.odpowiedz(z, dane)}")
    return 1 if zle else 0


if __name__ == "__main__":
    sys.exit(main())
