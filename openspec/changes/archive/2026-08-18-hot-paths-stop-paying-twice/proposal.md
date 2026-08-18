## Why

Powierzchnia narzędzi MCP kosztuje **15 134 tokeny w każdej turze** agenta i nic jej nie
pilnuje, więc rośnie z każdym narzędziem (zmierzone 18.08.2026: market-mcp 6 013,
teams-mcp 5 670, trading-mcp 3 451 — `cl100k_base` na zserializowanym `list_tools()`
każdego modułu; agent montuje wszystkie trzy). Ponad połowa tej liczby to nie treść, tylko
rusztowanie, które pydantic dokłada do schematu: `title` powtarzający nazwę pola,
`anyOf: [{type}, {type: null}]` zamiast listy typów, `default` w schemacie **odpowiedzi**,
której nikt nie konstruuje z domyślnych.

Obok tego trzy gorące ścieżki płacą po dwa razy za to samo pytanie: `market-data` waliduje
pydantikiem ~5 ramek `quote` na sekundę na parę, których nikt nie odbiera (przy 160 parach
to setki obiektów na sekundę do kosza); `market-mcp` pobiera `/pairs` 2–3 razy w jednym
wywołaniu narzędzia; brama pyta `GET /markets/{epic}` dwa razy przy jednym odczycie świec
DAY/WEEK — a limit 10 req/s capital.com liczy się przeciw **rachunkowi**, więc to jest
budżet zabrany komuś innemu.

Osobno: demo-guard `trading-mcp` utrzymuje trójstanowy cache i re-check przed każdym
zapisem po to, żeby porównać pole `environment` z literałem `"demo"` zahardkodowanym w
bramie. Guard nie umie wykryć tego, przed czym broni, a kosztuje dwie rundy na każdy zapis
po dowolnym błędzie.

## What Changes

- **Schemat narzędzi bez rusztowania.** Nowy `tc_mcp_kit.tool_schemas.slim_tool_schemas()`
  zdejmuje z publikowanych schematów `title`, zwija `anyOf` z samych typów do listy typów i
  usuwa `default` ze schematów **wyjściowych**. Trzy moduły MCP wołają go raz, w
  `build_server`. Zmierzone: 15 134 → 11 718 tokenów (−22,6%), bez utraty jednego pola.
- **Opis narzędzia dostaje budżet.** Docstringi wyrównane do jednego kształtu (co odpowiada
  → sufity → jednostki, strefa, strona ceny); dziś ich długość koreluje z datą napisania
  narzędzia (68–676 znaków), nie z jego złożonością.
- **Sufit powierzchni jest testem**, w każdym z trzech modułów: zserializowany
  `list_tools()` poniżej zapisanej liczby. Dziś nikt nie pilnuje totalu, więc tylko rośnie.
- **Ramki `quote` odrzucane przed parsowaniem** w `market-data` — `read_message` zwraca dla
  nich `None`, tak jak dla każdego rodzaju, którego ten moduł nie konsumuje.
- **`/pairs` pobierane raz na wywołanie narzędzia** (krótkie memo w kliencie market-mcp),
  `_market_open` w bramie też — memo z TTL zamiast drugiego requestu.
- **Zapisy bramy przez `_write_json()`** — nie-JSON-owe 502/504 z App Service przestają
  wychodzić jako nieobsłużone 500 ze stack trace.
- **Demo-guard schudnie do jednego sprawdzenia.** Brama wylicza `environment` z
  `capital_base_url` zamiast zwracać literał; `trading-mcp` zostaje przy checku startowym i
  traci `_demo_verified` z całą otoczką inwalidacji. **BREAKING** dla wymagania
  „sprawdzenie powtórzone po odzyskaniu połączenia" — patrz delta.
- **Warunek nr 1 dzielenia kodu dostaje zdanie o kodzie nowym.**
  `docs/architecture.md` wymaga zmierzonej kopii ≥70%, czego kod, który jeszcze nie
  istnieje, nie może spełnić — a napisanie `slim_tool_schemas` trzy razy jest dokładnie tą
  klasą dryfu, przed którą reguła broni. Warunki 2 i 3 zostają bez zmian.

## Capabilities

### New Capabilities

Żadnych. Wszystkie zmiany dotykają zachowań już opisanych.

### Modified Capabilities

- `market-mcp-tools`: „Opis narzędzia jest częścią kontraktu" dostaje sufit **całej**
  powierzchni narzędzi, pilnowany testem — dziś sufit jest wpisany w opis każdego
  narzędzia z osobna, a suma nie jest niczyja.
- `teams-mcp-tools`: to samo wymaganie, ten sam sufit.
- `trading-mcp-tools`: ten moduł nie ma dziś wymagania o opisie narzędzia w ogóle —
  dostaje je razem z sufitem powierzchni.
- `trading-mcp-upstream-access`: „Moduł pracuje wyłącznie na rachunku demonstracyjnym"
  traci scenariusz „Gateway zmienia środowisko przy odzyskanym połączeniu" i zdanie o
  powtarzaniu sprawdzenia; zyskuje zdanie o tym, że publikowane środowisko MUST wynikać z
  wiązania bramy, a nie być stałą.
- `capital-session`: „Publikowane możliwości nazywają środowisko" — środowisko w
  `/capabilities` MUST być wyliczone z adresu bazowego, którym moduł jest związany.

## Impact

- `packages/tc-mcp-kit` — nowy moduł `tool_schemas.py` i zależność od `mcp`; testy pakietu.
  Zmiana w `packages/` odpala w CI joby wszystkich konsumentów (warunek 3).
- `modules/market-mcp` — `server.py`, docstringi narzędzi w `tools/*.py`, memo `/pairs` w
  `client.py`/`tools/_shared.py`, test sufitu w `tests/test_tool_surface.py`.
- `modules/teams-mcp`, `modules/trading-mcp` — `server.py`, docstringi, test sufitu;
  w trading-mcp dodatkowo `client.py` (demo-guard) i jego testy.
- `modules/market-data` — `gateway/stream.py` (`_READERS`), jego testy.
- `modules/capital-gateway` — `adapter.py` (`_write_json`, memo `_market_open`,
  `capabilities()`), `contract`/snapshot OpenAPI trading-mcp bez zmiany kształtu.
- `docs/architecture.md` — warunek nr 1; `docs/plan-refactoru.html` — karta iteracji 4.
- Bez zmian w `infra/**` i bez migracji.

`design.md` powstaje: iteracja niesie trzy decyzje z alternatywami (gdzie żyje odchudzanie
schematu, co zostaje z demo-guarda, dlaczego rozbicie `compute_indicators` **nie** wchodzi
mimo planu). `review.md` powstanie po wykonaniu — zmiana rusza ścieżkę zleceń.
