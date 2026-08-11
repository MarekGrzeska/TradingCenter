## 1. Trasa dostępności market-data

- [x] 1.1 Dodać `GET /ping` w `market_data/routers/meta.py` — odpowiedź stała, bez odczytu bazy, bramki ani stanu kolekcji (`/health` już istniało i robi coś innego — odkryte przy implementacji, stąd inna nazwa)
- [x] 1.2 Test: żądanie bez poświadczenia dostaje odpowiedź
- [x] 1.3 Test: odpowiedź nie zawiera pól o parach, świecach ani stanie kolekcji
- [x] 1.4 `uv run pytest`, `uv run ruff check .`, `uv run pyright` w `market-data` przechodzą

## 2. Instrumentacja żądań (oba moduły, osobno)

- [x] 2.1 W `market_data/app.py` przenieść wywołanie `telemetry.configure()` przed `from fastapi import FastAPI` (nie tylko przed `app = FastAPI(...)` — patrz design.md, Decisions, dla powodu)
- [x] 2.2 W `capital_gateway/app.py` to samo, niezależnie
- [x] 2.3 Potwierdzić lokalnie, że instancja `app` w obu modułach jest oznaczona jako zainstrumentowana (`app._is_instrumented_by_opentelemetry is True`) zaraz po imporcie, z `APPLICATIONINSIGHTS_CONNECTION_STRING` ustawionym — zweryfikowane bezpośrednio, `False`/nieobecne przed poprawką, `True` po niej
- [x] 2.4 `uv run pytest`, `uv run ruff check .`, `uv run pyright` w obu modułach przechodzą — bez regresji w testach importujących `app` bez uruchamiania `lifespan()`

## 3. Terraform — alerty

- [x] 3.1 `azurerm_monitor_metric_alert` na `Requests` (`Microsoft.Web/sites`, `Total`, `LessThanOrEqual 0` na oknie `PT30M`) dla `azurerm_linux_web_app.market_data`
- [x] 3.2 `azurerm_monitor_metric_alert` na `Http5xx` dla `azurerm_linux_web_app.market_data`, ten sam kształt co `alert-gateway-http-5xx`
- [x] 3.3 `azurerm_monitor_scheduled_query_rules_alert_v2` na `AppExceptions`, okno `PT15M`, częstotliwość `PT15M`, próg `15` (design.md, Decisions)
- [x] 3.4 `excluded_paths` w `azurerm_linux_web_app.market_data.auth_settings_v2` dostaje `/ping` obok `/ws/candles`, z komentarzem w stylu istniejącego

## 4. Terraform — test dostępności

- [x] 4.1 `azurerm_application_insights_standard_web_test` odpytujący `https://<market-data hostname>/ping` z zewnątrz
- [x] 4.2 `azurerm_monitor_metric_alert` na wynik testu dostępności (`application_insights_web_test_location_availability_criteria`)
- [x] 4.3 `terraform fmt` i `terraform validate` w `infra/` — oba przechodzą

## 5. Wdrożenie, w tej kolejności — operator, nie agent ani CI

- [ ] 5.1 Wdrożyć `market-data` i `capital-gateway` (trasa `/ping` musi istnieć, zanim test dostępności zacznie jej pytać)
- [ ] 5.2 Potwierdzić w Application Insights, że `AppRequests` ma punkty dla obu modułów
- [ ] 5.3 `terraform apply` (operator, lokalnie, nigdy CI)
- [ ] 5.4 Potwierdzić w Azure Portal, że test dostępności odpytuje `/ping` i dostaje sukces
- [ ] 5.5 Otworzyć PR — `terraform plan` w CI (`terraform.yml`) pokaże diff nowych zasobów

## 6. Dokumentacja

- [x] 6.1 Dopisać trasę `/ping` do README `market-data` (kontrakt, brak uwierzytelnienia, brak danych archiwum)
- [x] 6.2 Odnotować w `docs/kiedy-produkcja-milczy.html`, że pozycja 04 (widoczność w miejscu, gdzie operator patrzy) wciąż otwarta — ta zmiana jej nie dotyka, żeby nie sugerować zamknięcia, którego nie ma
