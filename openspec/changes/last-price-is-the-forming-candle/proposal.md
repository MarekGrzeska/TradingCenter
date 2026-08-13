## Why

Operator pyta agenta „ile teraz kosztuje US100" i dostaje 29698.2 — zamknięcie sprzed
35 godzin, z wiekiem podanym uczciwie w sekundach. Odpowiedź jest poprawna i nie jest tą, o
którą pytał.

Cena bieżąca leży dwa metry dalej, w pamięci tego samego procesu. `candle_sink` publikuje
do huba każdą świecę, którą widzi ingest, a `Room.forming` trzyma tę w toku dla każdej
śledzonej pary — bez żadnego subskrybenta, bo pokój powstaje przez `setdefault` przy
publikacji. Wychodzi wyłącznie WebSocketem `/ws/candles`, a MCP jest pytaniem i
odpowiedzią, nie subskrypcją.

## What Changes

- Archiwum udostępnia świecę w toku **odczytem**, nie tylko w subskrypcji. Ta sama świeca,
  ten sam znacznik „w budowie", jedno żądanie zamiast uścisku dłoni WebSocketa.
- Bez wskazanej rozdzielczości archiwum odpowiada z **najdrobniejszej śledzonej, która taką
  świecę ma**. To archiwum wie, który feed naprawdę żyje; wołający zgadujący „MINUTE" dla
  pary śledzonej na HOUR dostałby „brak" przy działającej cenie.
- Odpowiedź niesie też, czy rynek jest otwarty — bez tego „nie ma świecy w toku" i „rynek
  jest zamknięty" są jednym zdaniem, a prowadzą operatora gdzie indziej.
- `get_last_price` oddaje najprawdziwszą cenę, jaką archiwum ma: świecę w toku gdy jest,
  zamkniętą gdy jej nie ma — zawsze z jawnym znacznikiem, że okres się nie zamknął, i z
  wiekiem, który niosła zawsze. Nowego narzędzia nie ma: model pytający „ile teraz kosztuje"
  nie ma jak trafić źle, gdy jest jedno miejsce, a dwa podobne narzędzia to tury, w których
  sięgnie po drugie.
- Parametr `resolution` zostaje honorowany, gdy model go poda. Pominięty znaczy „wybierz
  sam". Odpowiedź nazywa rozdzielczość, której użyto, bo może się różnić od żądanej.

Świeca w toku nadal MUST NOT być zapisywana. Zmienia się przy każdym kwotowaniu i zaniża
własny zakres do zamknięcia okresu — to jest powód, dla którego nie ma jej w bazie, i on się
nie zmienia.

Nie jest to zmiana łamiąca: wołający podający rozdzielczość dostaje to, co dostawał, plus
pole mówiące, czy okres jest zamknięty.

## Capabilities

### New Capabilities

Żadnej.

### Modified Capabilities

- `market-data-api`: „Świeca w budowie jest oznaczona" — jest też odczytywalna, a nie
  wyłącznie nadawana w subskrypcji.
- `market-mcp-tools`: „Zestaw odpowiada na pytania o archiwum" — odpowiedź o cenie jest
  ceną bieżącą, gdy archiwum ją ma, oznaczoną jako okres w toku.

`market-mcp-answers` zostaje nietknięta: „Trzy rodzaje »nie wiem«" wymaga **co najmniej**
trzech, a rozróżnienie „rynek zamknięty" od „feed stoi" jest czwartym, dokładanym w
narzędziu, nie zamiast tamtych.

## Impact

**market-data** — `contract.py` (kształt odpowiedzi o świecy w toku), `hub.py` (odczyt tego,
co pokój trzyma), `routers/candles.py` (trasa), `market_status.py` (czy rynek otwarty —
istnieje, nie zmienia się).

**market-mcp** — `tools/candles.py` (`get_last_price`), `upstream.py` (kształt wejściowy),
`contract/market-data.openapi.json` (własny snapshot schematu, który `scripts/contract.py
check` porównuje).

**terminal** — `pnpm contract:generate` przepisuje `src/data/contract.generated.ts`, bo
generator bierze cały schemat. Terminal nowego pola nie czyta: ma świecę w toku ze
strumienia, którym rysuje wykres, i nic mu po drugiej drodze do tej samej rzeczy. Żadnego
`archive.ts`, `types.ts` ani komponentu.

**agent, capital-gateway, infra** — bez zmian.
