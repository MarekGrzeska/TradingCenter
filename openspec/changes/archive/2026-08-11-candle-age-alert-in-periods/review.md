## Verdict

Alarm stoi teraz na `market_data.candle_age_periods` z progiem 3, `skip_metric_validation`
zdjęte. Wdrożone i zastosowane przez operatora 11 sierpnia — `candle_age_periods` ma punkty w
Application Insights, `alert-candle-age-stale` zszedł ze stanu `Fired` po raz pierwszy od 9
sierpnia. Nic celowo niedokończone: `..._seconds` zostaje bez zmian, jak zakładał `design.md`.

## Verified

- `uv run pytest tests/test_telemetry.py -q` (moduł `market-data`) — 14 passed
- `uv run pytest -q` (cały moduł `market-data`) — 565 passed, 7 skipped, 1 failed
  (`test_openapi.py::test_the_document_prints_with_no_environment_at_all`) — nie należy do tej
  zmiany: awaria podprocesu specyficzna dla Windows, odnotowana wcześniej w
  `docs/kiedy-produkcja-milczy.html`, pozycja 05, obecna też na czystym `main` sprzed tej
  zmiany.
- `uv run ruff check .` — All checks passed
- `uv run pyright` — 0 errors, 0 warnings, 0 informations
- `terraform fmt -check` i `terraform validate` w `infra/` — bez zmian formatu, konfiguracja
  poprawna
- Operator, po wdrożeniu: `market_data.candle_age_periods` ma punkty w Application Insights;
  `alert-candle-age-stale` zszedł ze stanu `Fired`

## Findings

Brak. Przegląd commita `dc7a035` (`feat(market-data): alert on candle age in periods, not raw
seconds`) przeciw punktowi rozgałęzienia nie znalazł defektu ani ryzyka wartego odnotowania.

| Severity | Where | Finding | Status |
|---|---|---|---|

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| Spóźnienie w jednostce niezależnej od rozdzielczości — Zdrowa para na najkrótszej i najdłuższej rozdzielczości | `test_telemetry.py::test_a_healthy_minute_pair_reports_less_than_one_period_late`, `test_telemetry.py::test_a_healthy_week_pair_reports_less_than_one_period_late` |
| Spóźnienie w jednostce niezależnej od rozdzielczości — Para przestała być uzupełniana | `test_telemetry.py::test_a_pair_skipped_the_same_number_of_periods_reports_the_same_value` |
| Spóźnienie w jednostce niezależnej od rozdzielczości — Świeca dopiero co zamknięta, jeszcze nieodebrana | `test_telemetry.py::test_a_candle_that_just_arrived_reports_zero_not_negative` |
| Spóźnienie w jednostce niezależnej od rozdzielczości — Rynek zamknięty | `test_telemetry.py::test_a_pair_whose_market_is_shut_is_excluded` (rozszerzony o asercję na wyprowadzoną metrykę w okresach) |
| Wiek w sekundach pozostaje dostępny — Diagnoza po fakcie | `test_telemetry.py::test_the_gauge_reports_what_was_last_set`, `test_telemetry.py::test_a_later_set_replaces_the_earlier_one` (zachowanie `CandleAgeGauge` niezmienione) — patrz Gaps |
| Jeden próg wystarcza dla wszystkich śledzonych rozdzielczości — Dodanie pary o długim okresie | operator, po `terraform apply`: patrz Verified |
| Jeden próg wystarcza dla wszystkich śledzonych rozdzielczości — Zatrzymanie jednej pary spośród wielu | operator, po `terraform apply`: patrz Verified |

## Gaps

- **Rejestracja instrumentów (`register()`) nie ma testu jednostkowego** — ani dla
  `candle_age_seconds` (sprzed tej zmiany), ani dla nowego `candle_age_periods`. Żaden test nie
  sprawdza wprost, że `meter.create_observable_gauge` dostaje właściwą nazwę metryki czy opis;
  to sprawdza dopiero uruchomiony proces eksportujący do Application Insights. Nie regresja tej
  zmiany — ten sam brak istniał już dla metryki sekundowej.
- **Dwa scenariusze reguły alarmu** ("Dodanie pary o długim okresie", "Zatrzymanie jednej pary
  spośród wielu") opisują zachowanie `azurerm_monitor_metric_alert` w Azure Monitor — nie da się
  ich sprawdzić testem jednostkowym Pythona. Zweryfikowane ręcznie przez operatora po
  `terraform apply` (obserwacja stanu `Fired` → spoczynek), nie automatycznym testem.
