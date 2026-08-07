## Verdict

Moduł jest kompletny wobec czterech specyfikacji i sprawdzony na żywym API demo, nie tylko
na mockach. Przegląd znalazł jeden realny wyciek poświadczeń w strumieniu i osiem luk
w pokryciu testami — wszystkie naprawione w tej samej gałęzi, więc gałąź jest gotowa do
scalenia. Świadomie niekompletne zostaje jedno: pętla połączenia w `stream/upstream.py`
(connect → subscribe → reconnect) nie ma testu jednostkowego i jest dowodzona wyłącznie
testami live.

## Verified

```
uv run pytest -q                   113 passed, 4 skipped
uv run pytest --run-live -m live   4 passed                      (48 s, konto demo2)
uv run ruff check .                All checks passed
uv run ruff format --check .       29 files already formatted
openspec validate add-capital-gateway --strict   valid
```

Zmierzone na żywym kluczu, nie zakładane:

| Odczyt | Wynik | Żądań | Czas |
|---|---|---|---|
| US100 `MINUTE_5` × 2 500 | 2 500 | 4 | 1,1 s |
| US100 `MINUTE_5` × 20 000 | 20 000, od 2026-05-01 | 29 | 25,6 s |
| US100 `DAY` × 20 000 | 9 449 — dno historii, 1991-08-12 | 14 | 3,9 s |
| stream US100 `MINUTE`, 60 s | 146 kwotowań, 146 świec w budowie, 2 zamknięte | — | — |

Liczby dla `DAY` zgadzają się co do sztuki z pomiarem zapisanym w `design.md`. Kwotowań było
146 na minutę wobec 296 w spike'u — inna aktywność rynku, nie regres.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Wysoka | `stream/upstream.py:_on_message` | Wiadomość błędu zrzucała cały payload providera. capital.com odsyła w błędzie treść żądania, które zawiera `cst` i `securityToken`, więc sesja trafiała do **każdego** subskrybenta. Spec `capital-streaming` tego zabrania wprost. | FIXED — cytowany jest wyłącznie `errorCode`, nigdy payload |
| Wysoka | `adapter.py:get_history` | `error.prices.not-found` przychodzi jako 404, a status był sprawdzany przed kodem błędu — głęboki odczyt dochodzący do dna historii wywalał się na ostatniej stronie i kasował wszystkie wcześniejsze | FIXED w `57461bf` |
| Średnia | `stream/hub.py:subscribe` | Powitalne wiadomości szły z pominięciem ochrony, którą ma `broadcast` — socket padający między akceptacją a subskrypcją wywracał całe wywołanie zamiast jednego subskrybenta | FIXED w `7c6c27c` |
| Niska | `mapping.py:candle_from_price` | `broker-gateway` liczył mid; strumień publikuje bid, więc mid dawałby pół spreadu skoku na szwie | Zmiana świadoma, opisana w `design.md` |

Poza tym w diffie 40 commitów nie znalazłem defektu, który przeżyłby weryfikację. Osobny
przebieg `/code-review` na gałęzi zgłosił osiem uwag — wszystkie dotyczyły hooka
archiwizacji dodanego po implementacji modułu, nie samego modułu; naprawione w `d5d4892`.

## Spec coverage

Wszystkie 22 wymagania i 51 scenariuszy mają test. Poniżej scenariusz → test, który go
dowodzi; testy dopisane w ramach tego przeglądu oznaczone **(+)**.

### capital-session

| Requirement / Scenario | Proven by |
|---|---|
| Poświadczenia nie opuszczają modułu / Konsument czyta dane bez poświadczenia | `test_app.py::test_no_response_carries_a_credential_or_a_session_token` |
| … / Brak poświadczeń przy starcie | `test_config.py::test_a_missing_credential_names_itself`, `::test_a_blank_credential_names_itself` |
| Wyłącznie demo / Skonfigurowany host produkcyjny | `test_config.py::test_a_non_demo_base_url_refuses_to_start`, `::test_a_non_demo_stream_url_refuses_to_start` |
| … / Możliwości nazywają środowisko | `test_app.py::test_capabilities_name_the_environment` |
| Sesja odnawia się / Sesja wygasła w trakcie wywołania | `test_client.py::test_an_expired_session_re_authenticates_and_retries_once` |
| … / Kilka wywołań trafia na brak sesji | `test_client.py::test_concurrent_callers_trigger_exactly_one_login`, `::test_a_login_is_shared_not_serialised` |
| Konta wyliczane / Wylistowanie kont | `test_adapter.py::test_accounts_mark_the_active_one` |
| … / Przełączenie aktywnego konta | **(+)** `test_adapter.py::test_switching_to_a_known_account_makes_it_active` |
| … / Przełączenie na nieznane konto | `test_adapter.py::test_switching_to_an_unknown_account_leaves_the_current_one` |
| Moduł publikuje możliwości / Odczyt możliwości | `test_app.py::test_capabilities_name_the_environment` |

### capital-market-data

| Requirement / Scenario | Proven by |
|---|---|
| Instrumenty wyszukiwalne / Wyszukiwanie po frazie | **(+)** `test_adapter.py::test_searching_returns_matching_instruments` |
| … / Wyliczenie katalogu | `test_adapter.py::test_the_traversal_dedupes_and_survives_a_bad_branch`, `::test_a_cut_short_traversal_says_so` |
| … / Gałąź katalogu nieczytelna | `test_adapter.py::test_the_traversal_dedupes_and_survives_a_bad_branch` |
| Świece w zadanej rozdzielczości / Odczyt bieżących świec | `test_adapter.py::test_candles_come_back_in_the_requested_resolution` |
| … / Nieznany symbol | `test_adapter.py::test_an_unknown_symbol_is_a_404_not_a_502` |
| Ta sama strona ceny / Historia styka się z live | **(+)** `test_mapping.py::test_history_and_the_stream_read_the_same_price_side`, `test_upstream.py::test_the_kept_side_is_the_one_history_uses` |
| Historia stronicowana / Więcej świec niż jedno żądanie | `test_history.py::test_a_multi_page_read_returns_one_ordered_series`, `::test_the_next_window_is_anchored_on_the_oldest_candle_received` |
| … / Historia instrumentu się kończy | `test_history.py::test_running_past_the_bottom_keeps_what_was_collected`, `::test_the_adapter_treats_not_found_as_an_ending` |
| … / Okno nie przynosi nic nowego | `test_history.py::test_a_window_with_no_progress_ends_the_loop` |
| Głęboki odczyt raportuje koszt / Zakończenie odczytu | `test_history.py::test_a_multi_page_read_returns_one_ordered_series`, live `::test_a_deep_read_pages_and_reports_its_cost` |
| … / Wywołujący porzuca odczyt | `test_history.py::test_paging_stops_when_the_caller_is_gone` |

### capital-trading

| Requirement / Scenario | Proven by |
|---|---|
| Pozycje czytelne / Odczyt pozycji | **(+)** `test_adapter.py::test_open_positions_are_readable` |
| … / Brak otwartych pozycji | **(+)** `test_adapter.py::test_no_positions_is_an_empty_list_not_an_error` |
| Zlecenia według typu / Zlecenie rynkowe | `test_adapter.py::test_a_market_order_settles_as_filled` |
| … / Zlecenie oczekujące | `test_adapter.py::test_a_resting_order_goes_to_working_orders_and_settles_as_working` |
| … / Zlecenie oczekujące bez poziomu | `test_dtos.py::test_a_resting_order_without_a_level_is_refused`, `test_app.py::test_a_resting_order_without_a_level_is_refused_by_the_schema` |
| … / Provider odmawia przyjęcia | `test_adapter.py::test_a_refused_deal_is_rejected_with_the_provider_reason` |
| Rozliczenie przed raportem / Rozliczenie przychodzi | `test_adapter.py::test_a_market_order_settles_as_filled`, `test_mapping.py::test_an_accepted_confirm_takes_the_status_of_its_action` |
| … / Rozliczenie nie przychodzi na czas | `test_adapter.py::test_a_deal_that_never_settles_is_pending_never_filled` |
| Pozycje zamykane i zmieniane / Zamknięcie pozycji | `test_adapter.py::test_closing_a_position_settles_as_closed` |
| … / Ustawienie jednego stopu | `test_adapter.py::test_an_amendment_sends_only_the_named_stop` |
| … / Usunięcie stopu | `test_adapter.py::test_clearing_a_stop_sends_null` |
| … / Zmiana bez żadnego stopu | `test_dtos.py::test_an_amendment_naming_neither_stop_is_refused` |
| Zlecenia oczekujące / Wylistowanie | **(+)** `test_adapter.py::test_working_orders_are_listed` |
| … / Anulowanie | `test_adapter.py::test_cancelling_a_working_order_settles_as_cancelled` |
| Handel tylko demo / Próba handlu poza demo | `test_config.py::test_a_non_demo_base_url_refuses_to_start` |

### capital-streaming

| Requirement / Scenario | Proven by |
|---|---|
| Subskrypcja po symbolu / Subskrypcja | `test_app.py::test_a_subscriber_hears_the_room_state_and_no_tokens` |
| … / Subskrypcja bez symbolu | `test_app.py::test_a_stream_missing_a_symbol_or_naming_a_bad_resolution_is_refused` |
| Strumień niesie świece i kwotowania / Świeca się zamyka | `test_hub.py::test_a_sealed_event_publishes_a_settled_candle`, **(+)** `test_upstream.py::test_a_sealed_candle_is_published_once_per_period` |
| … / Rynek rusza się wewnątrz świecy | `test_hub.py::test_a_quote_produces_both_a_quote_and_a_forming_candle`, **(+)** `test_upstream.py::test_a_quote_is_translated_not_forwarded` |
| … / Provider zgłasza awarię | **(+)** `test_upstream.py::test_a_failed_subscription_is_reported_rather_than_silent`, **(+)** `::test_credentials_never_appear_in_an_emitted_event`, **(+)** `test_hub.py::test_an_upstream_failure_reaches_the_subscribers` |
| Świeca w budowie / Pierwsze kwotowanie okresu | `test_forming.py::test_the_first_quote_opens_a_candle` |
| … / Kwotowania wewnątrz okresu | `test_forming.py::test_later_quotes_stretch_the_range_and_move_the_close` |
| … / Przychodzi świeca od providera | `test_forming.py::test_a_sealed_candle_overwrites_what_was_assembled` |
| … / Rozdzielczość bez stałej granicy | `test_forming.py::test_a_session_bound_resolution_never_guesses_a_boundary[DAY|WEEK]` |
| … / Subskrybent dołącza w środku okresu | `test_hub.py::test_a_late_joiner_is_handed_the_bar_already_forming` |
| Jedno połączenie na parę / Dołącza drugi konsument | `test_hub.py::test_a_second_subscriber_opens_no_second_connection`, `::test_a_different_resolution_is_a_different_room` |
| … / Odchodzi ostatni konsument | `test_hub.py::test_the_last_leaver_closes_the_connection` |
| Strumień przeżywa zerwanie / Połączenie pada | `test_hub.py::test_a_reconnecting_room_tells_its_subscribers` |
| … / Bezczynny strumień | **(+)** `test_upstream.py::test_an_idle_connection_is_kept_alive`, **(+)** `::test_the_ping_interval_leaves_room_under_the_provider_limit` |
| Strona ceny zgodna z historią / Provider raportuje obie strony | **(+)** `test_upstream.py::test_a_sealed_candle_is_published_once_per_period` |

## Gaps

- **Pętla połączenia w `stream/upstream.py` nie ma testu jednostkowego.** `_run` i
  `_session` — nawiązanie połączenia, subskrypcja, wznowienie po zerwaniu — są dowodzone
  wyłącznie testami live. Fałszywy WebSocket dowiódłby zachowania fałszywego WebSocketa,
  a nie tego, że reconnect działa wobec capital.com. Scenariusz „Połączenie z providerem
  pada" jest pokryty na poziomie huba: publikacja statusu `reconnecting` i wznowienie
  strumienia są sprawdzone, sama pętla ponawiania nie.
- **Nie ma testu składania zleceń na żywo.** Testy live są wyłącznie odczytem — konto demo
  to nadal konto, a test dymny, który handluje, to test dymny, którego nikt nie uruchamia.
  Ścieżka zleceń jest sprawdzona wyłącznie przez `respx`.
- **Bramka 10 żądań/s nie jest sprawdzona wobec realnego limitu providera.**
  `test_the_gate_bounds_the_request_rate` mierzy własne opóźnienie modułu; że capital.com
  faktycznie przyjmuje ten strumień żądań, wynika pośrednio z głębokiego odczytu na żywo
  (29 żądań, brak 429).
- **Wolumen na strumieniu jest zawsze `null`.** Ani zdarzenie świecy, ani kwotowania go nie
  niosą. To ograniczenie providera, nie brak implementacji — pole jest obecne, żeby kształt
  zgadzał się ze świecą z REST.
