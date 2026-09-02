# An observation is collected, or it is gone

## Why

Obserwacja ma dziś trzy stany: zbierana, **zakończona** (zbieranie stoi, historia zostaje)
i taka, której skasowano historię (obserwacja zostaje, dane znikają). Trzeci wyszedł na jaw
tak, jak wychodzą stany, których nikt nie chciał — jako wiersz na ekranie, o którym operator
zapytał „kiedy jest ended?", bo nigdy tego nie kliknął.

Nie kliknął. `ended` ustawiają dokładnie dwie rzeczy: przycisk w terminalu i narzędzie
`untrack_event`. A `track_event` po uderzeniu w sufit obserwacji odpowiada modelowi dosłownie
*„untrack_event on something no longer interesting, then try again"* — więc model, robiąc
sobie miejsce, zatrzymuje cudzą obserwację i zostawia po niej wiersz, który nic nie zbiera.

**Potrzebne są dwa stany: zbieramy albo nie ma tego u nas.** Zatrzymana obserwacja jest
miejscem na liście, które nie robi nic i którego nie da się z tej listy usunąć jedną
czynnością. Nie chodzi o to, żeby ją ukryć — ukryta znaczy: historia w bazie, nieosiągalna
z ekranu i nie do skasowania. Chodzi o to, żeby ten stan przestał istnieć.

Druga rzecz jest o wierszu zwiniętym. Niesie dziś do czterech „liderów" z paskiem
i procentem — skrót rynku do jednej ceny „za", czyli dokładnie to, czego
`terminal-polymarket` zabrania w widoku rozwiniętym („widok MUST NOT sprowadzać rynku do
jednej ceny «za»"). Zwinięcie nie jest wyjątkiem od tej reguły, tylko miejscem, w którym ją
obeszliśmy.

## What Changes

- **Zakończenie obserwacji przestaje istnieć — w całym module, nie tylko na ekranie.** Znika
  trasa `DELETE /events/{id}/tracking`, znika narzędzie `untrack_event`, znika kolumna
  `tracking_ended_at` i stan `ended` na drucie. Stan, którego nic nie potrafi wytworzyć,
  a który kontrakt dalej ogłasza, jest gorszy od jego braku: to obietnica bez producenta.
- **Nowa czynność: usunięcie obserwacji w całości.** `DELETE /events/{provider_event_id}` —
  wydarzenie, jego rynki, wyniki, wszystkie próbki i wszystkie zapisy zebranego zakresu.
  Niepodzielnie, bo kaskady w schemacie już to gwarantują. Wyłącznie przez kontrakt REST;
  **żadne narzędzie tego nie dosięga**, tak jak nie dosięgało kasowania historii.
- **Model traci możliwość zatrzymywania obserwacji.** Po uderzeniu w sufit dostaje odmowę
  mówiącą, żeby poprosił operatora o zwolnienie miejsca, zamiast robić je sam. Polymarket ma
  wtedy **dwa** narzędzia piszące zamiast trzech, a reguła „żadne narzędzie nie niszczy
  historii" zostaje nienaruszona — bo teraz jedyne wyjście z listy niszczy historię.
- **Terminal**: jeden przycisk zamiast dwóch — „Remove", z potwierdzeniem nazywającym zakres
  i nieodwracalność. Zwinięty wiersz niesie tytuł, grupę, stan zbierania i ten przycisk.
  Bez pasków, bez procentów.
- **Migracja usuwa zastane wydarzenia w stanie `ended` wraz z ich historią.** Decyzja
  operatora, podjęta świadomie: to jest kasowanie danych, których dostawca nie odda.

## Capabilities

### Modified Capabilities

- `polymarket-data-api`: zarządzanie obserwacją to objęcie i usunięcie, nie objęcie
  i zakończenie; kasowanie przez kontrakt obejmuje teraz usunięcie całości.
- `polymarket-data-tracking`: zakończenie obserwacji znika jako wymaganie; dochodzi
  usunięcie jako jedyne wyjście z listy, z powiedzianym skutkiem dla ponownego objęcia.
- `polymarket-data-tools`: zestaw pisze w dwóch miejscach zamiast trzech, i nie umie
  zatrzymać cudzej obserwacji, żeby zrobić sobie miejsce.
- `terminal-polymarket`: znika zakończenie obserwacji; kasowanie historii staje się
  usunięciem całości; dochodzi to, czego zwinięty wiersz **nie** pokazuje.

## Impact

- `modules/polymarket-data`: migracja 0003 (usuwa zastane `ended`, zdejmuje kolumnę), trasa,
  `store.py`, `views.py`, `contract.py`, `tools/observations.py`, `mcp_app.py` i testy.
- `modules/terminal`: `EventCard` traci skrót cenowy i przycisk zatrzymania,
  `EndTrackingDialog` znika, `DeleteHistoryDialog` staje się `RemoveEventDialog`,
  `endTracking` znika z klienta razem z wołającym — metoda bez wołającego to droga, którą
  ktoś kiedyś pójdzie, nie wiedząc, że została po czymś świadomie zdjętym.
  `contract.polymarket.generated.ts` regenerowany.
- `CLAUDE.md`: wiersz `polymarket-data` mówi „trzy z jego narzędzi **piszą**". Dwa.
- `infra/`: bez zmian. Migracja jedzie we własnym lifespanie modułu, jak każda.

## Nieodwracalność, powiedziana wprost

Ta zmiana kasuje dane w dwóch miejscach i oba są nieodwracalne. Migracja usuwa historię
wydarzeń zatrzymanych wcześniej. Nowy przycisk usuwa historię wydarzenia, które operator
wskaże. Dostawca nie oddaje historii rynku, który się rozstrzygnął, a dla pozostałych sięga
tylko tak daleko, jak sięga — więc w większości przypadków usuniętych danych nie da się
zebrać ponownie żadnym kosztem. To jest cena dwóch stanów zamiast trzech i została przyjęta
świadomie.
