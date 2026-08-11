## Why

Śledztwo z 11.08.2026 (docs/kiedy-produkcja-milczy.html, pozycja 04, i osobny dokument
„TradingCenter · infrastructure follow-ups") pokazało, że dziewięciogodzinną ciszę
market-data z 10–11 sierpnia przespały wszystkie pięć skonfigurowanych alertów — bo żaden z
nich nie patrzy na to, co faktycznie padło. Alert na wiek świecy to osobna, już otwarta
zmiana (`candle-age-alert-in-periods`); tu zostają cztery luki, które ta sama noc
odsłoniła obok niej: brak reguły na zanik ruchu, brak sposobu, żeby z zewnątrz sprawdzić,
czy kontener market-data w ogóle żyje, alert na 5xx patrzący tylko na gateway, i brak
alertu na wolumen wyjątków — a przy tym ostatnim odkryty został powód, dla którego
`AppRequests` nie istnieje wcale: `FastAPIInstrumentor` łata klasę `fastapi.FastAPI` przy
`configure_azure_monitor()`, ale `app = FastAPI(...)` w obu modułach powstaje wcześniej,
przy imporcie — więc łatka nigdy nie obejmuje jedynej istniejącej instancji.

## What Changes

- Nowa, nieuwierzytelniona trasa `GET /ping` w market-data (`/health` już istnieje i
  odpowiada za coś innego — czyta bazę, wymaga uwierzytelnienia — odkryte dopiero przy
  implementacji), dopisana do
  `excluded_paths` w `infra/app-service.tf` obok `/ws/candles` — dowodzi, że proces żyje
  i odpowiada, nic więcej. Do niej: `azurerm_application_insights_standard_web_test`
  odpytujący ją z zewnątrz plus alert na wynik dostępności.
- Nowy `azurerm_monitor_metric_alert` na `Http Requests` market-data — zero żądań w oknie
  znacząco krótszym niż zmierzony baseline (~360/h) sygnalizuje ciszę, zanim zrobi to
  cokolwiek innego. Gateway zostaje bez tej reguły: nie jest publicznie osiągalny
  (`ip_restriction_default_action = "Deny"`), więc sonda z zewnątrz i tak by go nie
  dosięgła.
- Drugi `azurerm_monitor_metric_alert` na `Http5xx`, tej samej postaci co
  `alert-gateway-http-5xx`, tym razem zakresu `azurerm_linux_web_app.market_data`.
- Nowa reguła zapytania zaplanowanego na `AppExceptions`, z progiem dobranym tak, by
  odróżnić prawdziwą burzę wyjątków od zmierzonego szumu przełączeń WebSocketa.
- **BREAKING dla niczego zewnętrznego, ale zmiana zachowania**: `telemetry.configure()`
  w `market_data/app.py` i `capital_gateway/app.py` przenosi się na poziom modułu, przed
  instrukcję `from fastapi import FastAPI` (nie tylko przed `FastAPI(...)` — dopiero
  zweryfikowane przy implementacji: łatka OpenTelemetry podmienia atrybut klasy na module
  `fastapi`, a `from fastapi import FastAPI` już wcześniej wiąże nazwę w tym module z tym,
  co atrybut trzymał w chwili wykonania tej instrukcji, więc samo przeniesienie wywołania
  za instancjonowanie aplikacji nic by nie dało). Bez tego `AppRequests` nie napełni się
  nigdy, niezależnie od tego, czy `APPLICATIONINSIGHTS_CONNECTION_STRING` jest ustawione.

## Capabilities

### New Capabilities
- `market-data-liveness`: nieuwierzytelniona trasa dowodząca, że proces market-data żyje —
  co wolno jej ujawnić (nic poza samym faktem odpowiedzi) i że nie zastępuje uwierzytelnionych
  tras ani stanu kolekcji.

### Modified Capabilities
<!-- Brak: pozostałe trzy poprawki (alert 5xx, alert wyjątków, kolejność
     `telemetry.configure()`) to konfiguracja operacyjna i naprawa błędu w instrumentacji,
     nie zmiana wymagania wobec żadnej istniejącej zdolności. -->

## Impact

- `infra/monitoring.tf` — trzy nowe reguły (ruch, 5xx market-data, wyjątki) plus test
  dostępności.
- `infra/app-service.tf` — `excluded_paths` market-data dostaje drugą pozycję.
- `modules/market-data/market_data/routers/meta.py` — nowa trasa `/ping`; `telemetry.configure()`
  przeniesione przed `app = FastAPI(...)`.
- `modules/capital-gateway/capital_gateway/app.py` — to samo przeniesienie
  `telemetry.configure()`, niezależnie (moduły nie dzielą kodu).
- Wdrożenie: `terraform apply` i weryfikacja w Application Insights są operatora, nie CI ani
  agenta — zapisane osobno w `tasks.md`.
- Bez wpływu na: kontrakt HTTP market-data poza jedną nową, jawnie nieuwierzytelnioną trasą;
  terminal; bazę danych; zmianę `candle-age-alert-in-periods` (inny alert, inna metryka, bez
  konfliktu w `infra/monitoring.tf`).
