## 1. Gateway: korekta salda

- [x] 1.1 `capital_gateway/client.py`: `POST /api/v1/accounts/topUp` z ciałem `{"amount": …}`
- [x] 1.2 `capital_gateway/adapter.py`: korekta salda, odmowa dostawcy tłumaczona na odmowę
      z powodem, nie na awarię (D3)
- [x] 1.3 `capital_gateway/dtos.py` i `app.py`: `POST /accounts/top-up`, ciało bez
      identyfikatora konta (D1), kwota zerowa odmawiana (D2)
- [x] 1.4 Testy gatewaya: kwota dodatnia i ujemna przechodzą tą samą drogą; odmowa
      dostawcy jest 4xx z powodem; kwota zerowa odmawiana przed dotknięciem dostawcy

## 2. Gateway: przełączenie mówi o strumieniu

- [x] 2.1 Opis trasy `PUT /accounts/active` w dokumencie OpenAPI nazywa zerwanie strumienia
      (`capital-session` w tej zmianie)
- [x] 2.2 Test: opublikowany dokument niesie to zdanie — opis trasy jest treścią kontraktu,
      nie komentarzem

## 3. trading-mcp: trzy narzędzia

- [x] 3.1 `tools/account.py`: `list_accounts` (odczyt), z oznaczeniem konta aktywnego
- [x] 3.2 `tools/account.py`: `switch_active_account` — zapis, opis nazywa zerwany strumień
      (D4, D5)
- [x] 3.3 `tools/account.py`: `top_up_demo_account` — zapis, kwota ujemna dozwolona, odmowa
      dostawcy jako `ToolRefusal` z powodem
- [x] 3.4 `client.py`: metoda pisząca do gatewaya, jeżeli brakuje jej dla `POST`
- [x] 3.5 Testy narzędzi: trzy nowe zachowania plus adnotacje (dwa zapisujące, jedno
      czytające)

## 4. Kontrakt i sufit

- [x] 4.1 `uv run python scripts/contract.py check` w `trading-mcp` — zobaczyć, jak się
      wywraca, dopiero potem odświeżyć snapshot
- [x] 4.2 `tests/test_tool_surface.py`: zmierzyć nową powierzchnię, podnieść sufit świadomie
      albo ścieśnić opisy; nowa liczba z powodem w komentarzu (D6)

## 5. Domknięcie

- [x] 5.1 `uv run pytest`, `ruff`, `pyright` w `capital-gateway` i w `trading-mcp`
- [x] 5.2 `uv run python scripts/contract.py check` przechodzi
- [x] 5.3 `openspec validate demo-account-is-the-operators-to-set --strict`
- [x] 5.4 `review.md` — co pokazał pierwszy pomiar powierzchni i czy odmowy dostawcy
      naprawdę przychodzą tak, jak zakłada D3 (jeżeli sprawdzone na żywo — powiedzieć jak;
      jeżeli nie — powiedzieć, że nie)
