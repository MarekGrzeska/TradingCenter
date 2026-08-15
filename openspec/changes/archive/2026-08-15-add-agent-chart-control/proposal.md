## Why

Operator prosi agenta o analizę i sam przekłada ją na wykres: włącza EMA 200, zmienia
interwał, przełącza symbol. Agent widzi te same dane co terminal — brakuje mu wyłącznie
prawa do powiedzenia „pokaż to", żeby odpowiedź i obraz na ekranie były tym samym.

To jest **pierwsze zapisujące narzędzie agenta** i tu zaczyna się rozszerzanie jego
zakresu. Granica przesuwa się świadomie i wąsko: agent dostaje wpływ na **to, co terminal
rysuje**, i na nic więcej — nie na archiwum, nie na zbieranie par, nie na zlecenia.

## What Changes

- Agent dostaje narzędzie ustawiające zawartość **aktywnego slotu** terminala: zestaw
  wskaźników (instancje z parametrami i kolorami), symbol i interwał. Narzędzie jest
  **lokalne dla modułu `agent`** — `market-mcp` zostaje czytające i nie wie o terminalu.
- Ustawienie zapisuje się w bazie agenta jako kolejne, numerowane polecenie. Terminal je
  czyta i stosuje: po turze i po wejściu na stronę. **BREAKING** dla dwóch wymagań
  `agent-tools`, które dziś tego zabraniają wprost.
- Polecenie stosuje się bez potwierdzania. Ślad jest widoczny w czacie jak każde inne
  wywołanie narzędzia, a operator cofa je wybierakiem.
- Żądanie tury niesie **migawkę tego, co terminal właśnie rysuje**, żeby model mówił
  o widocznym wykresie, a nie o wykresie sprzed dwóch tur.
- Symbol i interwał, których archiwum nie zbiera, są **odmawiane narzędziu ze zdaniem, co
  poprawić** — model może spróbować ponownie w granicach sufitu tury, tak samo jak przy
  odmowie z `market-mcp`.

## Capabilities

### New Capabilities

- `agent-chart-control`: narzędzie ustawiające wykres, kształt polecenia, jego numeracja
  i trwałość, oraz co narzędzie odmawia i jak to uzasadnia.

### Modified Capabilities

- `agent-tools`: narzędzie może pochodzić z tego modułu, nie tylko z serwera narzędzi; i
  nie każde narzędzie jest czytające — jedno wolno zapisujące, o nazwanej granicy.
- `agent-chat`: żądanie tury może nieść migawkę tego, co terminal rysuje.
- `terminal-grid`: aktywny slot stosuje polecenia agenta — wskaźniki, symbol i interwał —
  w granicach, które slot już ma (instrument archiwizowany, rozdzielczość archiwizowana).
- `terminal-agent-chat`: panel czyta nowe polecenia po turze i po wejściu na stronę,
  i mówi, że wykres został zmieniony przez agenta.

## Impact

- `modules/agent`: `agent/tools/` (narzędzie lokalne obok klienta MCP), `agent/graph.py`
  (pętla tury woła oba źródła narzędzi), `agent/contract.py`, `agent/models.py`,
  `agent/store.py`, nowy router, migracja w `migrations/versions/` — **alembic to ręczny
  krok operatora, deploy nie migruje**.
- `modules/terminal`: `data/agent*`/`agent/agentApi.ts` (odczyt poleceń), `grid/gridStore.ts`
  i `grid/GridView.tsx` (stosowanie do aktywnego slotu), `agent/AgentChat.tsx` (migawka
  w żądaniu tury, komunikat o zmianie).
- Bez zmian: `market-mcp` (zostaje czytające), `market-data`, `capital-gateway`,
  `market_data/contract.py`, `infra/**`.
- Prompt systemowy agenta: nowe narzędzie trzeba w nim nazwać, inaczej model go nie użyje
  tam, gdzie ma sens.
