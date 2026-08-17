## Why

Nic w tym stosie nie zna dźwigni. capital.com podaje `marginFactor` i zasady rozmiaru
(`minDealSize`, `maxDealSize`, `minSizeIncrement`, `lotSize`) na `GET /markets/{epic}` —
endpoint, który gateway **już woła** (`adapter.py`, `_market_open`) i z którego czyta
jedno pole: `snapshot.marketStatus`. Reszta jest odrzucana, więc żaden moduł niżej nie ma
jak jej zobaczyć.

Kosztowało to run zmierzony 17 sierpnia 2026: agent miał postawić 2% salda, policzył
`1 906,1366 / 30 174,5 = 0,0631704` — czyli 2% jako **wartość kontraktu** — i przy US100
z marżą 5% zablokował ~95 USD zamiast 1 906 USD. Dwadzieścia razy mniej, niż zamierzał, i
nic w odpowiedzi tego nie zdradziło. Broker dodatkowo ściął `0,0631704` do `0,063`
(`minSizeIncrement`), o czym model też się nie dowiedział.

Drugi brak jest w oknie outputów runu: pokazuje, że narzędzie zostało wywołane i jak
skończyło, ale nie co odpowiedziało. Czat agenta pokazuje to od początku, a to ta sama
potrzeba — zrozumieć, z czego wzięła się odpowiedź modelu.

## What Changes

- `capital-gateway` publikuje warunki handlowe instrumentu: nowe DTO i trasa
  `GET /instruments/{symbol}/terms`. Bez nowego ruchu do capital.com — ten sam
  `client.market(epic)`, który dziś jest wołany i wyrzucany.
- `trading-mcp` dostaje dwa narzędzia read-only: `get_instrument_terms` (marża, dźwignia,
  min/max/krok rozmiaru, waluta, koszt jednego lota przy bieżącej cenie) oraz
  `size_for_margin` — przeliczenie *ile mam wydać marży* na *jaki rozmiar wysłać*, z
  zaokrągleniem w dół do kroku i z faktyczną marżą oraz wartością kontraktu w odpowiedzi.
- Rola `trading-mcp` w spec zostaje doprecyzowana: moduł liczy warunki instrumentu, których
  model nie ma jak sprawdzić, i nadal nie podejmuje decyzji handlowych.
- Okno outputów runu w terminalu rozwija wywołanie narzędzia — argumenty i odpowiedź —
  wzorem transkryptu czatu.

Nie zmienia się nic w tym, czym jest `size` w `place_order`: to nadal lot, a
`place_order(size=1.0)` to jeden lot i działa dziś. Brakowało wyłącznie wiedzy, ile ten lot
kosztuje.

## Capabilities

### New Capabilities
- brak

### Modified Capabilities
- `capital-market-data`: gateway publikuje warunki handlowe instrumentu — marżę i zasady
  rozmiaru — jako osobny odczyt obok wyszukiwania instrumentów
- `trading-mcp-tools`: zestaw narzędzi obejmuje warunki instrumentu i przeliczenie marży na
  rozmiar; granica „to nie jest logika handlowa" zostaje nazwana wprost
- `terminal-teams`: okno outputów runu pokazuje argumenty i odpowiedź wywołanego narzędzia

## Impact

Kod: `capital-gateway` (`dtos.py`, `mapping.py`, `adapter.py`, `app.py`), `trading-mcp`
(`tools/`, snapshot `contract/capital-gateway.openapi.json`), `terminal`
(`teams/runs.ts`, `teams/RunOutputsDialog.tsx`, `teams/teamsApi.ts`).

Kontrakty: `capital_gateway/dtos.py` rośnie o nowy model i trasę — dodanie, nie zmiana
istniejącego kształtu, więc `market-data` nie wymaga niczego. Snapshot gatewayowego
OpenAPI w `trading-mcp` idzie do odświeżenia, inaczej `scripts/contract.py check`
zaczerwieni CI. Kontrakt `teams` **nie** jest ruszany: `ToolCallOut` wozi `arguments` i
`result_text` od początku, a ramka SSE `tool_call` zostaje szczupła celowo.

Dwie z trzech dotkniętych zdolności — `trading-mcp-tools` i `terminal-teams` — nie leżą
jeszcze w `openspec/specs/`, tylko w deltach niezarchiwizowanych zmian
(`add-trading-tools`, `add-teams-module`). Delty tej zmiany są pisane jako `ADDED` wobec
`openspec/specs/`, a przy archiwizacji trzeba je złożyć w kolejności: tamte zmiany przed tą.
