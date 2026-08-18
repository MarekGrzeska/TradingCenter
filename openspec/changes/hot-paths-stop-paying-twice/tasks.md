## 1. Odchudzanie schematu w pakiecie

- [x] 1.1 `packages/tc-mcp-kit/tc_mcp_kit/tool_schemas.py`: `slim_schema()` (czysta
      transformacja słownika: bez `title`, `anyOf` samych typów -> lista typów, opcjonalnie
      bez `default`) i `slim_tool_schemas(mcp)` nakładający ją na zarejestrowane narzędzia
- [x] 1.2 Zależność `mcp` w `pyproject.toml` pakietu; README pakietu wymienia nowy moduł
- [x] 1.3 Testy pakietu: zagnieżdżone `$defs`, `anyOf` z gałęzią niosącą więcej niż `type`
      (nietykana), `format` zachowany, `required` zachowane, wejście zachowuje `default`
- [x] 1.4 `docs/architecture.md`: warunek nr 1 dostaje drugą drogę spełnienia (kod nowy,
      identyczny u konsumentów od pierwszego dnia); `CLAUDE.md` w zdaniu o trzech warunkach

## 2. Sufit powierzchni w trzech modułach

- [x] 2.1 `market-mcp`, `teams-mcp`, `trading-mcp`: `slim_tool_schemas(mcp)` w `build_server`
- [x] 2.2 Test sufitu w każdym z trzech modułów: zserializowany `list_tools()` poniżej
      zapisanej stałej, komunikat podaje zmierzoną wielkość i sufit
- [x] 2.3 Test w każdym z trzech modułów: schemat nie niesie `title` ani `default` w wyjściu,
      a niesie każde pole, jego typ i `required` (to jest scenariusz „Schemat bez rusztowania")
- [x] 2.4 Zmierzyć po zmianie i ustawić sufity na wartość + ~5%

## 3. Opisy narzędzi

- [x] 3.1 `market-mcp`: docstringi 11 narzędzi do jednego kształtu (co odpowiada -> sufity ->
      jednostki, strefa, strona ceny); istniejące testy treści opisu zostają zielone
- [x] 3.2 `teams-mcp`: zmierzone tool po toolu i **zostawione bez zmian** — jego długie
      opisy niosą granice odmowy, których wymaga od nich jego własny spec (patrz `review.md`)
- [x] 3.3 `trading-mcp`: to samo dla 9 narzędzi; jednostka rozmiaru nazwana w każdym
      narzędziu zapisującym
- [x] 3.4 Test opisu w `trading-mcp` (jego spec dotąd go nie miał): opis, typowane parametry,
      nazwana jednostka rozmiaru
- [x] 3.5 Zmierzyć sumę trzech powierzchni tokenizerem i zapisać wynik w `review.md`

## 4. Gorące ścieżki upstreamu

- [x] 4.1 `market-data`: `_READERS` bez `"quote"`; test, że `read_message` zwraca `None` dla
      ramki `quote` i że pozostałe trzy rodzaje czyta bez zmian
- [x] 4.2 `market-mcp`: memo z TTL na `/pairs` w kliencie; test, że dwa odczyty w jednym
      wywołaniu narzędzia dają jeden request, i że po TTL leci kolejny
- [x] 4.3 `capital-gateway`: memo z TTL na `_market_open`; test, że odczyt świec DAY nie pyta
      `GET /markets/{epic}` dwa razy
- [x] 4.4 `capital-gateway`: `_write_json()` dla pięciu zapisów; test, że nie-JSON-owe 502
      wychodzi jako `GatewayError`, a nie jako nieobsłużony wyjątek

## 5. Demo-guard

- [x] 5.1 `capital-gateway`: `capabilities()` liczy `environment` z `capital_base_url`; test,
      że wartość wynika z ustawienia, a nie ze stałej
- [x] 5.2 `trading-mcp`: usunięcie `_demo_verified`, inwalidacji w `_send` i re-checku w
      `_write`; `ensure_demo_environment()` zostaje w ścieżce startowej
- [x] 5.3 Testy trading-mcp: start odmawia przy środowisku innym niż demo i przy nieosiągalnej
      bramie; zapis po błędzie kosztuje jedną rundę, nie dwie; usunięcie testów wymagania,
      które znika

## 6. Domknięcie

- [x] 6.1 `uv run pytest`, `ruff check .`, `pyright` w pakiecie i w pięciu dotkniętych modułach
- [x] 6.2 `uv run python scripts/contract.py check` w trzech modułach MCP
- [x] 6.3 `docs/plan-refactoru.html`: karta iteracji 4 na „zrobione", metryki tokenów i
      requestów upstream, akapit „co wyszło inaczej" (D3 i D4)
- [x] 6.4 `review.md`: zmierzone przed/po, co nie weszło i dlaczego
