## 1. Mechanizm w pakiecie

- [x] 1.1 `tc_runtime.liveness`: `LoopHeartbeat` (wiek, wiek w przebiegach, „nigdy nie chodziła"), `Heartbeats`, rejestracja metryki obserwowalnej
- [x] 1.2 `tc_runtime.telemetry`: logowanie i Application Insights, z listą wyciszanych loggerów jako parametrem
- [x] 1.3 `azure-monitor-opentelemetry` w zależnościach pakietu, nie w każdym module z osobna
- [x] 1.4 Testy reguły raz, w `packages/tc-runtime/tests/test_liveness.py`

## 2. Trzy pętle

- [x] 2.1 `polymarket-data`: bicie po ukończonym przebiegu próbkowania, `heartbeat=` w konstruktorze
- [x] 2.2 `social-data`: to samo dla zbierania
- [x] 2.3 `strategy`: to samo dla oceniania
- [x] 2.4 Po jednym teście na moduł, że pętla naprawdę o to prosi — nie że reguła działa, bo to jest w pakiecie
- [x] 2.5 `/health` każdego z trzech niesie wiek; `/ping` nietknięte

## 3. Telemetria tam, gdzie jej nie było

- [x] 3.1 Cztery moduły wołają `telemetry.configure()` **nad** importem FastAPI
- [x] 3.2 `telegram-gateway` nie wycisza `httpx` — jego linia żądania niesie token bota, a `redaction.py` istnieje po to, żeby go z niej wyjąć
- [x] 3.3 Lokalne `configure_logging` usunięte z czterech modułów

## 4. Alerty

- [x] 4.1 Trzy `azurerm_monitor_metric_alert` z `for_each`, próg trzy przebiegi
- [x] 4.2 `terraform fmt` i `validate`
- [ ] 4.3 `apply` operatora — bez niego metryka jest emitowana i nieczytana

## 5. Runbook

- [x] 5.1 `docs/kiedy-produkcja-milczy.html` dostaje trzy alerty i to, co przy każdym zrobić

## 6. Sprawdzenie

- [x] 6.1 Testy, `ruff` i `pyright` w każdym dotkniętym module i w pakiecie
- [ ] 6.2 Zatrzymanie pętli na produkcji i stoper do powiadomienia — operatora, po `apply`
