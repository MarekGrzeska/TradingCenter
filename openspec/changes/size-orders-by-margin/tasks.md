## 1. capital-gateway: warunki instrumentu

- [x] 1.1 `dtos.py`: model `InstrumentTerms` — `symbol`, `currency`, `lot_size`,
      `margin_factor`, `margin_factor_unit`, `min_deal_size`, `max_deal_size`,
      `size_increment`, każde pole poza `symbol` dopuszczające brak
- [x] 1.2 `mapping.py`: `instrument_terms_from_market_details` z odpowiedzi
      `GET /markets/{epic}` — `instrument.*` i `dealingRules.*`, bez podstawiania wartości
      domyślnych za brakujące pola
- [x] 1.3 `adapter.py`: `get_instrument_terms(symbol)`, ta sama `client.market(epic)`,
      404 providera jako `GatewayError` nazywający symbol
- [x] 1.4 `app.py`: trasa `GET /instruments/{symbol}/terms`, tag `market-data`,
      `response_model=InstrumentTerms`
- [x] 1.5 Testy jednostkowe mapowania na `tests/fixtures/market_gold.json` plus fixture
      z brakującym `marginFactor` i z `dealingRules` bez `minSizeIncrement`
- [x] 1.6 Test trasy: nieznany symbol → 404 nazywający symbol
- [x] 1.7 `uv run ruff check .` · `uv run pyright` · `uv run pytest`

## 2. trading-mcp: kontrakt i narzędzia

- [x] 2.1 Odświeżyć `contract/capital-gateway.openapi.json`, potem
      `uv run python scripts/contract.py check`
- [x] 2.2 Odczyt `/instruments/{symbol}/terms` — `_read` z `_shared.py` wystarcza,
      `client.py` bez zmian
- [x] 2.3 `tools/instruments.py` (nowy moduł): `InstrumentTermsOut` i narzędzie
      `get_instrument_terms(symbol)` z adnotacją `READ_ONLY`, bez pola ceny
- [x] 2.4 To samo miejsce: `size_for_margin(symbol, margin, price)` — `READ_ONLY`,
      arytmetyka na `Decimal`, zaokrąglenie w dół do `size_increment`, wynik niesie
      `size`, `margin_used`, `notional`
- [x] 2.5 Odmowy `size_for_margin`: rozmiar poniżej `min_deal_size` (z podaniem
      najmniejszego rozmiaru i jego depozytu), powyżej `max_deal_size`, nieznana
      `margin_factor_unit`, `price` lub `margin` niedodatnie
- [x] 2.6 Zarejestrować moduł narzędzi tam, gdzie rejestrowane są `account` i `orders`
- [x] 2.7 Testy: przeliczenie US100 z logu (marża 5%, cena 30 174,5 — rozmiar 1,263),
      każda z odmów z 2.5, oraz `get_instrument_terms` nieoddające ceny
- [x] 2.8 Test listy narzędzi: oba nowe wpisy oznaczone jako czytające
- [x] 2.9 `uv run ruff check .` · `uv run pyright` · `uv run pytest`

## 3. terminal: wyniki narzędzi w oknie outputów

- [x] 3.1 `teams/runs.ts`: `RecordedToolCall` niesie `arguments` i `resultText`,
      `mapRecordedToolCall` przestaje je gubić
- [x] 3.2 `teams/runs.ts`: `attachAgentKeys` przenosi oba pola na `TeamRunToolCall`;
      wywołanie ze strumienia zostaje bez nich, rozpoznawalne po ich braku
- [x] 3.3 `RunOutputsDialog.tsx`: sekcja `Called` renderuje wpis rozwijany — karetka,
      `aria-expanded`, argumenty i wynik/powód w `<pre>`, zwinięty domyślnie
- [x] 3.4 Wpis bez treści (przyszedł strumieniem, nie został doczytany) mówi to wprost
      zamiast pokazywać puste `arguments` i pusty wynik
- [x] 3.5 `useRunMonitor` już czyta `runToolCalls` raz na połączenie i scala je ze
      strumieniem — okno czyta jego stan, żadne wołanie nie doszło
- [x] 3.6 Testy: rozwinięcie pokazuje argumenty i wynik, wpisy startują zwinięte,
      wywołanie bez treści jest oznaczone, odmowa pokazuje powód
- [x] 3.7 `pnpm lint` · `pnpm typecheck` · `pnpm test`

## 4. Domknięcie

- [x] 4.1 README `capital-gateway` i `trading-mcp` — nowa trasa i dwa narzędzia
- [x] 4.2 `openspec validate size-orders-by-margin --strict`
- [x] 4.3 `review.md`
