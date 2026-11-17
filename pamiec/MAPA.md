# 🧠 MAPA — mózg Claude

**Start każdej sesji tutaj.** Ta mapa mówi, co istnieje, jak się łączy i gdzie szukać szczegółów.
Repo jest **publiczne** → zero haseł, kluczy, kodów, publicznego IP domu i nazwisk (zasady: [zasady.md](zasady.md)).

## 1. Jak myśleć (pętla każdej sesji)
1. Przeczytaj tę mapę → [zasady.md](zasady.md) → plik z obszaru, którego dotyczy prośba (tabela w punkcie 3).
2. Połącz się z Pi ([dostep.md](dostep.md)) i **sprawdź stan, zanim coś zmienisz** (repo bywa nieaktualne).
3. Zrób zadanie. Przed wgraniem pliku na Pi porównaj md5 kopii z Pi i z gita.
4. Na koniec: dopisz [sesje.md](sesje.md), popraw [do-zrobienia.md](do-zrobienia.md), nowe ustalenia →
   [decyzje.md](decyzje.md) / [uzytkownik.md](uzytkownik.md), zmienione fakty → popraw węzeł (nie dopisuj sprzecznych).

## 2. Mapa świata

```mermaid
graph LR
  U(("👤 Antek<br/>iPhone · iPad · PC"))
  subgraph CHMURA["☁️ Claude Code w chmurze"]
    C["sesja Claude<br/>(claude-cloud)"]
    R[("GitHub<br/>TangySpider4453/repozytorium")]
  end
  subgraph TS["🔒 Tailscale (tailnet)"]
    PI4["🖥️ Pi 4B 8 GB<br/>serwer domowy<br/>raspberrypi"]
    PI5["🤖 Pi 5 + Hailo-8<br/>mózg łazika<br/>rpi-5-1"]
    Z1["📡 Zero 2W a1<br/>stacja LoRa"]
    Z2["🛰️ Zero 2W a2<br/>satelita"]
  end
  NAS[("💾 NAS Synology<br/>LAN, /mnt/nas")]
  C -- "ssh pi" --> PI4
  C -- git --> R
  U -- "portal, Linphone, Telegram" --> PI4
  U -- "strona sterowania" --> PI5
  PI4 -- "SMB: logi, zdjęcia, kopia systemu" --> NAS
  PI5 -- "kopie przez most SSH" --> PI4
  Z1 -. LoRa .- Z2
  Z1 -. LoRa .- PI5

  PI4 --- P1["📚 Nauka"]
  PI4 --- P2["💪 Progres sylwetki"]
  PI4 --- P3["🤖 Bot + 📞 telefon"]
  PI4 --- P4["🏋️ Garmin RestOrTrain"]
  PI4 --- P5["🩺 Zdrowie, NAS, kopie"]
  PI4 --- P6["🎮 Minecraft (znajomi!)"]
  PI4 --- P7["📅 todo, kalendarz, Mobidziennik, ZTM"]
  PI5 --- P8["🚗 Łazik: sterowanie, wizja"]
```

## 3. Gdzie szukać (router)

| Pytanie / zadanie dotyczy… | Węzeł pamięci | Pełna dokumentacja |
|---|---|---|
| czego nie wolno, zgody | [zasady.md](zasady.md) | — |
| kim jest użytkownik, styl pracy | [uzytkownik.md](uzytkownik.md) | — |
| sprzęt, adresy, sieć | [urzadzenia.md](urzadzenia.md) | `SERWER.md` |
| usługi i timery na Pi 4, co działa teraz | [uslugi.md](uslugi.md) | `SERWER.md` |
| projekty: stan, pliki, problemy | [projekty.md](projekty.md) | `PLAN.md`, `PROGRES.md`, `lazik/LAZIK.md` |
| gałęzie repo, co jest gdzie | [repo.md](repo.md) | — |
| łączenie z Pi, klucze (bez wartości) | [dostep.md](dostep.md) | `PLAN.md` §4 |
| co zostało do zrobienia | [do-zrobienia.md](do-zrobienia.md) | `PRZEKAZANIE.md` w kopiach |
| dlaczego coś jest tak, a nie inaczej | [decyzje.md](decyzje.md) | dzienniki w `SERWER.md`, `PLAN.md` §9 |
| co robiły poprzednie sesje | [sesje.md](sesje.md) | kopie rozmów na Pi (niżej) |

## 4. Źródła poza repo
- **Kopie rozmów ze starego konta Claude** (na Pi): `~/Desktop/dla claude kopie zapasowe/`
  - `Serwerek/` — serwer, nauka, bot, telefon, Garmin (19.10–16.11): `PRZEKAZANIE.md`, `zapis_rozmowy.md` (450 KB).
  - `Łazik - sterowanie, wizja, kopie (konto 1)/` — łazik (26.10–16.11): `PRZEKAZANIE.md`, `zapis_rozmowy.md`, kod.
  - `DOSTEP_PRYWATNE.md` w obu = hasła. **Nie czytaj bez potrzeby, nigdy nie kopiuj do repo ani na czat.**
- Dane na Pi: `~/portal/dane/` (postępy, zdrowie, progres), NAS `Tony-Folder/Raspberry/`.
