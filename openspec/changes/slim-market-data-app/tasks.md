## 0. Punkt odniesienia

- [x] 0.1 Zrzucić schemat OpenAPI **przed** jakąkolwiek zmianą i zachować go poza repo — to jest wzorzec, do którego porównuje się wszystko poniżej

## 1. Cache statusu rynku przestaje być globalny

- [x] 1.1 Klasa `MarketStatus` we własnym module: konstruowana z samym TTL — *gateway jest podawany przy każdym wywołaniu, nie trzymany; patrz review.md*, metoda pytająca o symbol, cache w instancji; TTL i zasada „gateway, który nie odpowiada, też jest zapamiętywany" przeniesione **bez zmiany**, wraz z komentarzem, który je uzasadnia (74 żądania przez kwadrans weekendu)
- [x] 1.2 Budowana w `lifespan`, trzymana jako `app.state.market_status` — *czytana przez `request.app.state`, nie przez `Depends`. Trasa `/pairs` sięga tak samo po `instruments` i `ingest` w tych samych dwóch linijkach; osobny dostawca `Depends` dla jednej z trzech sąsiadujących zależności byłby niespójnością, nie porządkiem*
- [x] 1.3 Usunąć `_market_status_cache` i `_market_status` z `app.py`
- [x] 1.4 Testy jednostkowe `MarketStatus` bez `TestClient`: świeży odczyt pyta gateway, drugi w ramach TTL nie pyta, odczyt po TTL pyta znowu, a gateway rzucający `GatewayError` zostaje zapamiętany jako `None`
- [x] 1.5 Skasować z `test_app.py` fixture importujący `_market_status_cache`; testy tras przechodzą bez niego

## 2. Logika domenowa wychodzi z pliku tras

- [x] 2.1 `_decide_late_pairs` → `tracking.py`, obok `collection_state`
- [x] 2.2 `_fill_out` → `FillOut.of()` w `contract.py`, wzorem istniejącego `PairEstimateOut.of()`
- [x] 2.3 `_tracked_pair_out` → `TrackedPairOut.of()` w `contract.py`
- [x] 2.4 Testy rozstrzygania stanu spóźnionej pary wołające funkcję wprost: para świeża nie generuje pytania do gatewaya, dwie rozdzielczości tego samego symbolu to jedno pytanie, gateway milczący zostawia `UNKNOWN`
- [x] 2.5 `ruff` i pełny pakiet `market-data` przechodzą — po tym kroku `app.py` ma tylko trasy i montaż

## 3. Trasy rozbite na routery

- [x] 3.1 `routers/deps.py` — `pool` i `hub` jako dostawcy zależności, bez importu z `app.py`
- [x] 3.2 `routers/meta.py` — `/`, `/health`
- [x] 3.3 `routers/candles.py` — `/candles/{symbol}`, `/coverage/{symbol}`
- [x] 3.4 `routers/pairs.py` — `GET`/`POST` `/pairs`, `DELETE /pairs/{symbol}`, `/deletions`
- [x] 3.5 `routers/jobs.py` — `/jobs/estimate`, `/jobs`, `/jobs/{job_id}`, `/jobs/{job_id}/retry`
- [x] 3.6 `routers/stream.py` — `/ws/candles`
- [x] 3.7 `app.py` zostaje z `lifespan`, obsługą wyjątków i montażem routerów; `tags` MUST zostać dokładnie takie, jakie były

## 4. Dowód, że nic się nie ruszyło

- [x] 4.1 Zrzucić schemat OpenAPI **po** zmianie i porównać ze wzorcem z 0.1 — różnica zerowa; jeśli `generate-terminal-contract-from-openapi` już weszła, dodatkowo `contract:check` w terminalu
- [x] 4.2 `test_app.py` nie wymaga **żadnej** zmiany poza skasowaniem fixture z 1.5. Każda inna wymuszona zmiana to znalezisko — zapisać ją w review.md wraz z tym, co ją wymusiło, zamiast po cichu poprawić test — *wymusiły się dwie, obie zapisane w review.md: jedna linia w fixture `api` (podaje `MarketStatus`, bo fixture omija `lifespan`) i ścieżka importu `candle_feed`. Ani jedna asercja się nie zmieniła*
- [x] 4.3 `app.py` poniżej 200 linii; jeśli wyszło więcej, nazwać w review.md, co tam zostało i dlaczego — *190 linii, z 773*

## 5. Domknięcie

- [x] 5.1 `ruff` i `pytest` w `market-data`, łącznie z `pytest -m db` (435 passed, 7 skipped)
- [x] 5.2 README `market-data`: gdzie teraz mieszkają trasy i gdzie logika, którą stamtąd wyjęto
- [x] 5.3 `openspec validate slim-market-data-app --strict`
- [ ] 5.4 Ręcznie na uruchomionym zestawie: kreator, zlecenie, `Data History`, usunięcie i wykres na żywo — refaktor bez zmiany zachowania trzeba potwierdzić zachowaniem, a nie samym pakietem testów; *do ręcznego potwierdzenia przez operatora*
