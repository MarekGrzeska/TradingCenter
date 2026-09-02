## Why

Pętla, która przestaje chodzić, jest trybem awarii, o którym nikt się nie dowiaduje. Nie
trzyma połączenia, nie odpowiada na żądanie i nie rzuca wyjątkiem — proces stoi, `/ping`
jest zielony, a archiwum po prostu przestaje rosnąć. Zmierzone 24 sierpnia 2026 w
`market-data`: jeden pokój strumienia milczał czternaście godzin, podczas gdy 28 innych
publikowało od 47 do 265 kwotowań na 25 sekund. `a-silent-feed-is-a-broken-feed` naprawiło
to **w jednym module**.

Od tamtej pory doszły trzy moduły z własną pętlą i żaden z nich nie emituje ani jednej
metryki: próbkowanie w `polymarket-data`, zbieranie w `social-data`, ocena w `strategy`.
Telemetrię wysyłają dziś tylko `capital-gateway` i `market-data`, a wszystkie trzy istniejące
alerty i jedyny web test patrzą na `market-data` albo na bazę. Runbook
`docs/kiedy-produkcja-milczy.html` zna jeden alert.

To jest zmiana OpenSpec, bo dodaje wymaganie do trzech modułów: dziś żadna specyfikacja nie
mówi, że moduł ma o swojej pętli **cokolwiek** powiedzieć na zewnątrz.

## What Changes

- **Trzy nowe zdolności — `polymarket-data-liveness`, `social-data-liveness`,
  `strategy-liveness`.** Każda mówi to samo trzema różnymi powodami: moduł MUST publikować
  wiek ostatniego **ukończonego** przebiegu swojej pętli, mierzony w jej własnych interwałach,
  i MUST NOT liczyć przebiegu, który się nie udał.
- **Jednostką jest przebieg, nie sekunda.** Próbkowanie co minutę i zbieranie co pięć są oba
  zdrowe; jeden próg w sekundach byłby zły dla jednego z nich. To ta sama decyzja, którą
  `market-data` podjęło dla `candle_age_periods`.
- **`tc_runtime.liveness`** niesie mechanizm: `LoopHeartbeat`, `Heartbeats` i jedna metryka
  obserwowalna na moduł. Reguła jest testowana raz, w pakiecie; każdy moduł ma jeden test, że
  jego pętla naprawdę o nią prosi.
- **`tc_runtime.telemetry`** niesie konfigurację logowania i Application Insights, którą
  `market-data` i `capital-gateway` miały jako dwie kopie, a trzy nowe moduły miały tylko w
  połowie (samo logowanie, bez eksportu). Lista wyciszanych loggerów jest **parametrem**, i to
  nie jest kosmetyka: `httpx` na INFO jest szumem w czterech modułach i **dowodem** w piątym —
  `telegram-gateway` redaguje token bota dokładnie z tej linii, a pakiet, który by ją wyciszył,
  usunąłby rzecz badaną. Złapane przez `test_a_refusal_quoting_the_url_reports_without_the_token`.
- **Trzy alerty w `infra/monitoring.tf`**, po jednym na moduł, próg trzy przebiegi — jak przy
  świecach: dwa to restart, który źle wypadł, trzy to pętla, która stanęła.
- **Wiek trafia na `/health`, nigdy na `/ping`.** Plan mówił inaczej i plan był w tym miejscu
  sprzeczny z `market-data-liveness`, które wymaga, żeby trasa dostępności zwracała stałą treść
  niezależną od stanu. Sonda mówi, że proces żyje; że jego praca idzie dobrze, to inne pytanie,
  a web test czerwieniejący od spóźnionej pętli jest health checkiem w przebraniu liveness.

## Capabilities

### New Capabilities

- `polymarket-data-liveness`: pętla próbkowania mówi, kiedy ostatnio ukończyła przebieg.
- `social-data-liveness`: to samo dla pętli zbierania.
- `strategy-liveness`: to samo dla pętli oceniania.

## Impact

- **Kod**: `packages/tc-runtime` (`liveness.py`, `telemetry.py`, `pyproject.toml`);
  `polymarket_data/{app,ingest,routers/meta}.py`, `social_data/{app,ingest,routers/meta}.py`,
  `strategy/{app,runner/loop,routers/meta}.py`, `telegram_gateway/app.py` (sama telemetria).
- **Infrastruktura**: `infra/monitoring.tf` — trzy alerty. `APPLICATIONINSIGHTS_CONNECTION_STRING`
  już jest ustawione dla wszystkich ośmiu aplikacji, więc nic w `app-service.tf` się nie zmienia.
- **Operator**: `apply`, jak każdy tutaj. Bez niego moduły emitują metrykę, której nikt nie
  czyta — stan gorszy niż po, lepszy niż przed.
- **Poza zakresem: `telegram-gateway`.** Jego watcher to długi poll na każdego przyjętego bota,
  więc brama bez botów nie ma pętli, a cisza jest tam stanem **wspieranym**. Alert na to zapaliłby
  się w dniu, w którym operator niczego nie podpiął. Bierze z tej zmiany samą telemetrię.
- **Poza zakresem: `workbench`.** Jego scheduler ma własny ślad w bazie i własny ekran; to osobny
  pomiar, nie dopisek do tego.

`design.md` nie powstaje: jedyny wybór z alternatywą — `/ping` czy `/health` — mieści się w
jednym akapicie wyżej i jest rozstrzygnięty przez istniejące wymaganie, a nie przez nową decyzję.
