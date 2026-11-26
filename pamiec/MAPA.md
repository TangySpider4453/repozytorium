# 🧠 MAPA: mózg Claude (czytaj na starcie, potem [zasady.md](zasady.md))

Na starcie czytasz tylko ten plik i `zasady.md`. Resztę otwieraj **wtedy, gdy zadanie jej dotyczy** (router niżej).
Repo jest **publiczne**: zero haseł, kluczy, kodów, publicznego IP, adresu tunelu MC, nazwisk, nazwy tailnetu.

## Sedno o użytkowniku
Antek, technikum (robotyk). Pisz po polsku, krótko i konkretnie; nazwy przycisków po angielsku. Nikomu nic nie wysyłaj
bez zgody. Więcej: [tematy/uzytkownik.md](tematy/uzytkownik.md).

## Pętla pracy
1. Otwórz plik tematu z routera. Połącz się z Pi (`ssh pi hostname`) i **sprawdź stan na Pi**, zanim coś zmienisz.
2. Przed wgraniem na Pi: md5 kopii z Pi i z gita, kopia do `kopie/`, scp, weryfikacja.
3. Koniec sesji, w pliku tematu: wpis w „Dziennik” (najnowszy na górze, max ~6; starsze przenieś do `archiwum/`),
   popraw „Otwarte”, nowe ustalenia do „Ustalenia” (zmienione fakty popraw, nie dopisuj sprzecznych). Commit + push.

## Router
| Zadanie dotyczy… | Plik | Pełna dokumentacja |
|---|---|---|
| łączenie z Pi/Tailscale, sprzęt, adresy, gałęzie repo, mapa świata | [tematy/infrastruktura.md](tematy/infrastruktura.md) | `SERWER.md` |
| portal, bot, telefon, token Claude, zdrowie, NAS, usługi/timery | [tematy/serwer.md](tematy/serwer.md) | `SERWER.md` |
| Trener: stan, otwarte, dziennik | [tematy/trener.md](tematy/trener.md) | `trener/README.md` |
| Trener: reguły planu, dieta, wygląd/iOS (przed zmianą kodu) | [tematy/trener-ustalenia.md](tematy/trener-ustalenia.md) | — |
| nauka, sprawdziany, Mobidziennik | [tematy/nauka.md](tematy/nauka.md) | `PLAN.md` |
| progres sylwetki | [tematy/progres.md](tematy/progres.md) | `PROGRES.md` |
| łazik | [tematy/lazik.md](tematy/lazik.md) | `lazik/LAZIK.md` |
| Prezenty dla dziewczyny (kalendarz adwentowy) | [tematy/prezenty.md](tematy/prezenty.md) | `SERWER.md` |
| Minecraft | [tematy/minecraft.md](tematy/minecraft.md) | `SERWER.md` |
| stara historia (sesje, decyzje, zadania do 22.11) | `archiwum/` (tylko gdy trzeba) | — |

## Źródła poza repo
- Kopie rozmów ze starego konta (na Pi): `~/Desktop/dla claude kopie zapasowe/` (`Serwerek/`, `Łazik …/`:
  `PRZEKAZANIE.md`, `zapis_rozmowy.md`). `DOSTEP_PRYWATNE.md` = hasła: **nie czytaj bez potrzeby, nigdy do repo ani na czat.**
- Dane na Pi: `~/portal/dane/`, `~/trener/dane/`; NAS `Tony-Folder/Raspberry/`.
