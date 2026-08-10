## Why

`alert-plan-memory-high` odpalił się 10.08.2026 12:14 UTC przy 85.27% — próg 85 leży dosłownie na
linii baseline'u, który `design.md` (`archive/2026-08-09-authenticate-terminal-to-market-data`)
odnotował już przy jego ustalaniu jako „~80% pamięci zajęte". Diagnoza metryk `MemoryPercentage`
z planu za ostatnie 30h pokazuje piłokształtny wzorzec dobowy (dołek ~01:00-06:00 UTC, szczyt
wieczorem/rano), nie monotoniczny wyciek — a Activity Log nie ma żadnego restartu/recyklingu od
08-09, więc wzorca nie maskuje odzyskiwanie pamięci przez platformę. Drugi dobowy szczyt wypadł
wyżej niż pierwszy, ale jednego dnia danych za mało, by odróżnić powolny wyciek od zwykłej różnicy
poniedziałek-vs-niedziela w ruchu. Przy tak wąskim zapasie próg 85 łapie normalny stan planu, nie
problem.

## What Changes

- Próg `azurerm_monitor_metric_alert.plan_memory` w `infra/monitoring.tf` rośnie z 85 do 92.
- Żadnej zmiany planu (`sku_name` zostaje `B1`), `worker_count` zostaje 1 — ograniczenie
  `RateGate` capital.com (`app-service.tf`, komentarz przy `worker_count`) się nie zmienia.
- Żadnej zmiany kodu aplikacji.

## Capabilities

Brak — czysta korekta wartości progu alertu operacyjnego, nie zmiana zachowania systemu ani
kontraktu między modułami. `skip_specs: true` w `.openspec.yaml`.

## Impact

- `infra/monitoring.tf` — jedna wartość (`threshold`) w `azurerm_monitor_metric_alert.plan_memory`.
- Brak wpływu na `capital-gateway`, `market-data`, `terminal`.
- `terraform apply` robi operator lokalnie (CI tylko planuje) — zgodnie z resztą `infra/**`.
