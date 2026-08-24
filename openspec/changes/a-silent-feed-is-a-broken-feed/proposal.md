## Why

24 sierpnia 2026 operator zgłosił, że US100 na D1 nie dociąga ceny na żywo. Pomiar na
produkcji, przez `/ws/stream` gatewaya, na wszystkich 29 zbieranych parach naraz:

| pokój | kwotowania w 25 s |
|---|---|
| 28 par — US100 M1/M5/M15/M30/H1/H4/**WEEK**, GOLD/BTCUSD/OIL_CRUDE ×7, w tym ich **DAY** | 47–265 |
| **US100 DAY** | **0** |

Zero powtórzyło się w próbach 150-sekundowej i ośmiominutowej. Pokój trzymał zamkniętą
świecę z **23.08 00:00 UTC** i od tamtej pory nie dostał nic — ostatnia linia logu tego
pokoju w gatewayu jest z 22.08 19:25. Świeży pokój na tę samą rozdzielczość (US500 DAY,
założony przy okazji pomiaru) ustalił granicę i ruszył w sekundę, więc kod jest sprawny;
zepsuty był **jeden egzemplarz pokoju**, a naprawił go dopiero ręczny restart
`app-tradingcenter-gateway` o 14:05 UTC — po nim US100 DAY publikuje świecę w budowie
otwartą 24.08 00:00 w ciągu kilku sekund.

Ten sam restart odsłonił drugą usterkę tej samej rodziny: **wszystkie cztery pokoje
`WEEK`** trzymały świecę otwartą **17.08** i doklejały do niej ceny z 24 sierpnia. Tydzień
przetoczył się o północy, provider nie przysłał zamknięcia, a moduł rozciągał trzymany
słupek dalej — czyli publikował świecę z wartościami, których nie było w żadnym z tych
dwóch tygodni. Po restarcie wszystkie startują od 24.08.

Cisza nie jest dziś nigdzie traktowana jak awaria, i to na trzech poziomach:

1. `capital_gateway/stream/upstream.py` — pętla reconnectu reaguje wyłącznie na wyjątek
   albo zamknięcie socketu. Połączenie żywe, przez które provider nic nie wysyła, jest
   trzymane w nieskończoność.
2. `capital_gateway/stream/hub.py` — dla `DAY` i `WEEK` `place_boundary()` wołane jest
   tylko z kwotowania (i raz przy zakładaniu pokoju). Pokój bez kwotowań nigdy nie ustali
   granicy na nowo, więc jedna cisza kosztuje całą dobę bez świecy w budowie. A
   `FormingCandle.on_quote` rozciąga trzymany słupek bez sprawdzenia, czy jego okres na
   pewno już minął — mimo że `PERIOD_SECONDS` jest bezpiecznym górnym ograniczeniem i
   `mark_forming` po stronie REST już z niego korzysta.
3. `market_data/ingest/live.py` — `_listen()` czeka na wiadomość bez timeoutu odbioru,
   więc drugi moduł też nie zauważa, że karmi się ciszą. Ingest dla US100 DAY wystartował
   22.08 21:50 i przez czterdzieści godzin ani razu nie zerwał subskrypcji: nie było ani
   resubskrypcji, ani `fill_gap`.

Koszt jest większy niż nieruchomy wykres. Świeca dzienna za 24 sierpnia zamknęłaby się
o północy do martwego pokoju — czyli **dziura w archiwum**, której nic by nie domknęło,
bo domykanie luki wisi na wznowieniu subskrypcji, a wznowienia nie było. A wskaźnik
`STALLED` w `/pairs` odezwałby się dla `DAY` dopiero po dwóch okresach plus grace, czyli
**po dwóch dniach**.

## What Changes

- **Cisza na strumieniu providera jest zerwaniem.** `Upstream` pilnuje, kiedy ostatnio
  cokolwiek przyszło; po przekroczeniu progu zamyka połączenie, publikuje status jak przy
  każdym innym zerwaniu i łączy się ponownie — a więc odtwarza subskrypcje i, dla `DAY`
  i `WEEK`, ustala granicę okresu na nowo.
- **Granica okresu odświeża się bez kwotowania.** Pokój, któremu brakuje granicy, pyta
  o nią providera z własnego zegara, a nie przy okazji cudzego kwotowania.
- **Świeca, której okres na pewno minął, nie jest rozciągana.** Dla rozdzielczości bez
  arytmetycznej granicy `PERIOD_SECONDS` służy jako górne ograniczenie: kwotowanie
  późniejsze niż trzymany słupek plus cała długość okresu MUST NOT go rozciągnąć — moduł
  pyta providera o granicę, tak jak po zamknięciu świecy.
- **Ingest zauważa ciszę.** Subskrypcja `capital-gateway`, przez którą nic nie przyszło
  dłużej niż próg, kończy się — i wpada w istniejącą pętlę: domknij lukę, subskrybuj
  ponownie. Nowego mechanizmu naprawczego nie ma, jest tylko doprowadzenie do tego, który
  już działa.

**Poza zakresem, świadomie.** Próg `STALE_AFTER_PERIODS` w `tracking.py` zostaje jaki
jest. To, że para dzienna jest sygnalizowana jako stojąca dopiero po dwóch dniach, jest
prawdziwą luką w monitoringu, ale odpowiedzią na nią jest inne pytanie — czym mierzyć
świeżość pary, której okres trwa dobę — i osobna zmiana. Ta zmiana sprawia, że nie ma
czego sygnalizować, bo strumień wraca sam.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `capital-streaming`: wymaganie „Strumień przeżywa zerwanie" mówi dziś wyłącznie
  o połączeniu, które **się zamknęło**, i dlatego połączenie milczące przeżyło czternaście
  godzin. Dochodzi cisza jako zerwanie. W wymaganiu „Świeca w budowie jest składana przez
  moduł" dochodzą dwie rzeczy, których dziś nie ma: granica ustalana z własnego zegara,
  gdy kwotowań nie ma, i zakaz rozciągania słupka, którego okres na pewno minął.
- `market-data-ingest`: wymaganie „Nasłuch na żywo dla każdej śledzonej pary" wznawia
  subskrypcję „po zerwaniu" — a subskrypcja, przez którą nic nie przychodzi, nigdy nie
  została zerwana. Cisza dłuższa niż próg MUST być traktowana jak koniec subskrypcji.

## Impact

**Kod.** `capital-gateway`: `stream/upstream.py` (watchdog ciszy), `stream/hub.py`
(odświeżanie granicy z zegara), `stream/forming.py` (odmowa rozciągnięcia po upływie
okresu, więc i `periods`-owy odpowiednik długości okresu po stronie gatewaya).
`market-data`: `gateway/stream.py` albo `ingest/live.py` — timeout odbioru na subskrypcji.

**Konfiguracja.** Progi ciszy jako stałe modułu, nie jako ustawienia w `.env`: mają
wynikać z tego, co provider robi, a nie z tego, co ktoś wpisał w plik. Wybór wartości
i to, co robią w weekend, należy do `design.md`.

**Czego nie dotyka.** Żadnego kontraktu — kształty wiadomości na `/ws/stream`, OpenAPI
market-data i wygenerowany kontrakt terminala zostają bez zmian. Żadnej migracji, żadnej
bazy, żadnego pliku w `infra/`, żadnego modułu poza tymi dwoma. Terminal nie wie o tej
zmianie nic i nie powinien.

**Budżet ruchu.** Każde wznowienie kosztuje providerowi jedno sprawdzenie sesji, a ustalenie
granicy `DAY`/`WEEK` do dwóch żądań — wszystko przez tę samą bramkę 10 żądań na sekundę
liczoną **na konto**. Zamknięty rynek jest cichy z definicji, więc próg dobrany bez namysłu
zamienia weekend w lawinę wznowień na 29 pokojach. To jest główne ryzyko tej zmiany i
główne pytanie dla `design.md`; gateway ma już memo `market_open`, którym można to obciąć.

## Artefakty tej zmiany

`design.md` — **tak**: cała trudność siedzi w doborze progów i w tym, żeby lekarstwo nie
było gorsze od choroby na zamkniętym rynku. `tasks.md` — **tak**, praca idzie w dwóch
modułach i kolejność ma znaczenie (gateway sam się naprawia; timeout w ingest jest drugą
linią obrony i ma sens tylko z pierwszą). `review.md` — **po wdrożeniu**, zgodnie z tym, co
zamyka zmianę w tym repozytorium.
