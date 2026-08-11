## Verdict

Cztery poprawki wdrożone i zastosowane przez operatora 11 sierpnia: alert na zanik ruchu,
`GET /ping` z testem dostępności, drugi alert 5xx dla market-data, alert na wolumen wyjątków —
oraz naprawiony rzeczywisty powód, dla którego `AppRequests` nigdy nie miało punktu (kolejność
importu `fastapi.FastAPI` względem `telemetry.configure()` w obu modułach). Delta specyfikacji
obejmuje wyłącznie nową trasę `/ping` (`market-data-liveness`) — pozostałe trzy poprawki to
konfiguracja Terraform i naprawa błędu instrumentacji, bez nowego wymagania wobec produktu,
zgodnie z `proposal.md`. Próg alertu na wyjątki (15/15min) jest jawnie nazwanym oszacowaniem z
jednej nocy pomiarów (design.md, Open Questions), nie zweryfikowanym eksperymentalnie — nic
poza tym nie jest celowo niedokończone.

## Verified

- `uv run pytest tests/test_meta.py -v` (moduł `market-data`) — 2 passed
  (`test_ping_answers_with_no_state_set_up_at_all`, `test_ping_reveals_nothing_about_the_archive`)
- `uv run pytest -q` w `market-data` — 565 passed, 7 skipped, 1 failed
  (`test_openapi.py::test_the_document_prints_with_no_environment_at_all`, pre-existing,
  niezwiązane — Windows-only, patrz `docs/kiedy-produkcja-milczy.html` pozycja 05)
- `uv run pytest -q` w `capital-gateway` — 193 passed, 11 skipped
- `uv run ruff check .` i `uv run pyright` — czyste w obu modułach
- `terraform fmt -check` i `terraform validate` w `infra/` — bez zmian formatu, konfiguracja
  poprawna (potwierdza schemat `azurerm_application_insights_standard_web_test`,
  `application_insights_web_test_location_availability_criteria` i
  `azurerm_monitor_scheduled_query_rules_alert_v2` przeciw realnemu providerowi 4.81.0)
- Naprawa instrumentacji zweryfikowana bezpośrednio, nie tylko przez czytanie kodu:
  `app._is_instrumented_by_opentelemetry` — nieobecne/`False` przed przeniesieniem importu
  `FastAPI` pod `telemetry.configure()`, `True` po, w obu modułach osobno
- Operator, po wdrożeniu: `AppRequests` ma punkty dla obu modułów, test dostępności odpytuje
  `/ping` i dostaje sukces (tasks.md, sekcja 5)

## Findings

Przegląd commita `1e1e531` (`feat(monitoring): alert on a dead backend, not just a noisy one`)
przeciw punktowi rozgałęzienia:

| Severity | Where | Finding | Status |
|---|---|---|---|
| Low | `infra/monitoring.tf`, `azurerm_monitor_metric_alert.market_data_requests_low` | Próg `LessThanOrEqual 0` zakłada, że `Requests` zawsze publikuje punkt (choćby zerowy) w każdym oknie, a nie milczy przy braku ruchu — założenie niesprawdzone w tej zmianie, bo wymaga obserwacji realnego wzorca ruchu w czasie. Jeśli platforma pomija punkt zamiast publikować zero, reguła nie zapali się na prawdziwej ciszy tak samo jak `alert-candle-age-stale` nie paliła się wcześniej — dokładnie ten sam kształt awarii, który ta zmiana miała zamknąć. | Open — do potwierdzenia obserwacją, nie kodem |

## Spec coverage

Wyłącznie `market-data-liveness` — jedyna zdolność z deltą specyfikacji w tej zmianie.

| Requirement / Scenario | Proven by |
|---|---|
| Sonda dostępności odpowiada bez uwierzytelnienia — Żądanie bez poświadczenia | `test_meta.py::test_ping_answers_with_no_state_set_up_at_all` |
| Odpowiedź dowodzi tylko tego, że proces żyje — Baza danych nieosiągalna | `test_meta.py::test_ping_answers_with_no_state_set_up_at_all` (uruchomiony bez `app.state.pool` w ogóle — mocniejszy dowód niż „baza wolna": trasa nie sięga po nią wcale) |
| Odpowiedź dowodzi tylko tego, że proces żyje — Odpowiedź nie niesie danych archiwum | `test_meta.py::test_ping_reveals_nothing_about_the_archive` |
| Sonda dostępności nie zastępuje uwierzytelnionych tras — Próba wyciągnięcia czegokolwiek ponad status | `test_meta.py::test_ping_reveals_nothing_about_the_archive` (ciało odpowiedzi ma wyłącznie klucz `status`) |

## Gaps

- **`excluded_paths` faktycznie wyłącza `/ping` z Easy Auth w produkcji** — nie do sprawdzenia
  testem jednostkowym Pythona. Zweryfikowane ręcznie przez operatora: test dostępności
  Application Insights odpytuje `/ping` z zewnątrz i dostaje sukces (tasks.md 5.4).
- **Alert na zanik ruchu i alert 5xx dla market-data** — zachowanie reguł
  `azurerm_monitor_metric_alert` w Azure Monitor, nie do sprawdzenia lokalnie. Bez incydentu od
  wdrożenia nie ma jeszcze potwierdzenia, że którykolwiek faktycznie zapala się we właściwym
  momencie — tylko że `terraform apply` je założył bez błędu.
- **Próg alertu na wyjątki (15/15min)** — oszacowanie z jednej nocy pomiarów (`design.md`,
  Open Questions), nie zweryfikowane w praniu. Tania poprawka po fakcie, jeśli okaże się zbyt
  czuły albo zbyt tępy.
