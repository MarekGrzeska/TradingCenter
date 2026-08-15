## Verdict

Wdrożone i działające na produkcji: `modules/agent` stoi jako czwarty moduł — własna baza,
własny klucz OpenAI, sesje trwające poza przeglądarką, odpowiedź strumieniem, zużycie
wyceniane w chwili zapisu. Terminal ma panel agenta obok outletu i zakładkę kosztów. Siedem
nowych zdolności, 71 z 73 zadań odhaczonych.

Dwa zadania zostają otwarte i oba są tego samego rodzaju — nikt tego nie zobaczył na
wdrożonej aplikacji. To nie jest formalność: 12.5 dotyczy buforowania i zerwania strumienia
po 230 s, czyli własności, których lokalny uvicorn nie ma i mieć nie może.

Przegląd znalazł dwa realne defekty, oba w tej samej szczelinie — między obrazem a bazą — i
oba wyszły dopiero w dniu archiwizacji, po tygodniu pracy modułu na produkcji. Jeden został
naprawiony kodem (PR #93), drugi ręcznie na produkcji. Żaden nie jest usterką w tym, co
moduł robi; oba są usterkami w tym, czego nikt nie sprawdzał.

## Verified

Uruchomione 15 sierpnia 2026, na tym, co leży na `main` po scaleniu PR #93:

- `modules/agent`: `uv run pytest` — 172 passed. `uv run pytest -m db` — 80 passed,
  przeciw prawdziwemu PostgreSQL-owi w kontenerze jednorazowym. `uv run ruff check .` —
  czysto. `uv run pyright` — 0 błędów.
- `modules/terminal`: `pnpm test` — 529 passed w 41 plikach. `pnpm lint` — czysto.
  `pnpm typecheck` — czysto. `pnpm contract:check` — kontrakt aktualny.
- Produkcja, odczytana wprost z bazy `agent` na `psql-tradingcenter`: schemat na `0003`,
  rola `app-tradingcenter-agent` ma komplet uprawnień do wszystkich tabel modułu, panel
  agenta i zarządzanie promptem odpowiadają z wdrożonej aplikacji (potwierdzone przez
  operatora).
- Zadanie 12.4 po stronie modułu: trzy tury strumieniem na trzech różnych modelach, każda
  zakończona `complete`, `/usage` liczy trzy różne stawki, `unknown_count` = 0.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| **High** | `modules/agent/Dockerfile`, `.github/workflows/deploy-agent.yml` | Komentarz w `Dockerfile` mówi, że migracje są „a deliberate, separate step run by the deploy workflow" — a `deploy-agent.yml` nie ma i nigdy nie miał takiego kroku. Nic nie wiązało obrazu ze schematem: wdrożenie obrazu niosącego `0003_prompt_revisions` wylądowało na bazie stojącej na `0002`, wszystko działało poza `GET /prompt`, które oddawało `500` z nieistniejącej tabeli, a wdrożenie raportowało sukces. Objaw wyszedł dopiero wtedy, gdy operator otworzył jedyny panel czytający nową tabelę. | FIXED: `agent/schema_version.py` (PR #93, `c4150fd`) — bliźniak strażnika, którego `market-data` dostał 10 sierpnia po tym samym wypadku. Lifespan odmawia startu przy rozjeździe rewizji w którąkolwiek stronę. |
| **Medium** | `design.md`, Migration Plan krok 3 | Krok „operator zakłada rolę Entra w bazie `agent` i nadaje jej uprawnienia" wykonano jednym `GRANT` na tabele istniejące tamtego dnia, bez `ALTER DEFAULT PRIVILEGES`. Każda tabela stworzona później przez administratora jest dla roli aplikacji niewidzialna — `prompt_revisions` nie miała ani `SELECT`, ani `INSERT`. Sama migracja niczego by nie naprawiła: `permission denied` czyta się na produkcji tak samo jak brak tabeli. | FIXED na produkcji 15 sierpnia: `GRANT` w kształcie, jaki miały pozostałe tabele, plus `ALTER DEFAULT PRIVILEGES FOR ROLE <administrator> IN SCHEMA public`. Zapisane w `modules/agent/README.md`, bo żaden test tego nie pilnuje. Uwaga: domyślne uprawnienia są związane z rolą, która tworzy obiekt — migracja puszczona inną tożsamością administratora wraca do tej samej dziury. |
| **Low** | `.github/workflows/deploy-agent.yml` | Sprawdzenie po wdrożeniu czyta płaszczyznę sterowania Azure — stan witryny i tag obrazu — a nie kontener. `state=Running` to stan strony, więc kontener w pętli restartów nadal daje zielone wdrożenie. Strażnik schematu z PR #93 zamienia awarię cichą na całkowitą i zalogowaną, ale **nie** zapala wdrożenia na czerwono, jak robi to sonda `market-data`. Agent nie ma ścieżki wyłączonej z Easy Auth, którą dałoby się sondować. | accepted — domknięcie (sonda czytająca logi kontenera) to osobna zmiana, nie ta. |

Przejrzane i odrzucone jako nie-znalezisko: kolejność wiadomości w transkrypcie (jeden
`ORDER BY` po `id`, testowany na powtarzalność), zapis zużycia przy zerwanej odpowiedzi
(`test_turn.py::test_usage_reported_before_a_failure_is_still_recorded`), oraz to, czy
skasowanie sesji zmniejsza rachunek (nie zmniejsza — `test_deleting_a_session_does_not_reduce_the_bill`).

## Gaps

- **Strumienia nikt nie widział na wdrożonej aplikacji.** Zadanie 12.5. App Service potrafi
  buforować odpowiedź i przerywa połączenie po 230 s — obie własności są niewidoczne
  lokalnie, gdzie uvicorn oddaje fragmenty natychmiast i nie ma limitu czasu. Twierdzenie
  „strumień działa na produkcji" jest dziś wnioskiem z testów, nie obserwacją.
- **Zadanie 12.4 jest odhaczone z resztą w treści.** Sam wpis mówi: zrobione po stronie
  modułu, „zostaje przejście tą samą drogą przez terminal (5173)". Odhaczone zadanie z
  niedokończoną połową jest gorsze niż nieodhaczone, bo znika z listy.
- **Lista dozwolonych adresów nie jest sprawdzana żadnym testem.** Wymaganie „Wywołanie
  z przeglądarki przychodzi z uznanego adresu" spełnia warstwa przed modułem
  (`infra/app-service.tf`), a moduł świadomie nie dokłada własnego CORS —
  `test_no_cors.py` pilnuje tylko tego drugiego. Że lista naprawdę zawiera adres terminala
  i naprawdę nie zawiera `*`, wie wyłącznie `terraform plan`.
- **Panelu i zakładki kosztów nie oglądał człowiek w ramach tego przeglądu.** 529 testów
  chodzi w jsdom, który nie ma układu ani szerokości.

## Spec coverage

Wymaganie po wymaganiu, z nazwanym dowodem. Wszystkie wymienione testy przechodzą w
przebiegu opisanym w `Verified`.

### `agent-chat`

| Requirement | Proven by |
|---|---|
| Sesja rozmowy trwa poza przeglądarką | `test_store.py::test_a_session_with_no_messages_is_not_listed`, `test_sessions_router.py::test_first_message_titles_the_session` |
| Transkrypt zachowuje kolejność i autorstwo | `test_store.py::test_message_order_is_stable_and_repeatable`, `test_store.py::test_operator_message_survives_a_failed_model_call` |
| Agent pracuje na jednym prompcie systemowym | `test_turn.py::test_a_reply_keeps_its_version_after_the_prompt_is_later_edited`, `test_tool_calls_store.py::test_a_turn_without_tools_runs_the_prompt_that_says_so` |
| Odpowiedź płynie strumieniem | `test_turn.py::test_fragments_arrive_before_completion`, `test_turn.py::test_an_abandoned_queue_still_gets_the_full_reply_written`, `test_turn.py::test_a_broken_stream_saves_the_partial_reply_as_incomplete` |
| Operator nazywa i usuwa rozmowy | `test_sessions_router.py::test_renaming_a_session_replaces_the_derived_title`, `::test_a_blank_or_overlong_title_is_refused`, `::test_a_deleted_session_leaves_the_list_and_reads_as_missing`, `::test_deleting_twice_is_a_404_not_a_second_success` |

### `agent-models`

| Requirement | Proven by |
|---|---|
| Katalog modeli wystarcza do zbudowania wybieraka | `test_app.py::test_get_models_is_enough_to_build_a_wybierak`, `test_models_catalogue.py::test_entries_are_sorted_cheapest_first` |
| Model jest wyborem sesji, a nie instalacji | `test_sessions_router.py::test_changing_the_model_is_reflected_on_the_session`, `test_store.py::test_changing_model_does_not_rewrite_earlier_messages` |
| Model spoza katalogu jest odmową, nie podmianą | `test_models_catalogue.py::test_resolve_with_an_unknown_request_refuses_rather_than_falling_back`, `::test_a_model_retired_from_the_catalogue_is_still_a_named_refusal` |

### `agent-usage`

| Requirement | Proven by |
|---|---|
| Każde wywołanie modelu zostawia ślad zużycia | `test_turn.py::test_usage_never_reported_is_recorded_as_unknown_not_skipped`, `test_turn.py::test_usage_reported_before_a_failure_is_still_recorded` |
| Koszt jest przypisany do wiersza w chwili zapisu | `test_store.py::test_usage_cost_is_computed_from_the_rates_given`, `test_usage_store.py::test_a_later_rate_does_not_change_an_earlier_rows_cost`, `test_store.py::test_usage_with_unknown_tokens_has_no_cost` |
| Zużycie da się odczytać zbiorczo | `test_usage_store.py::test_usage_by_model_sums_known_and_counts_unknown`, `::test_usage_by_session_is_one_row_per_session`, `::test_usage_by_day_buckets_by_calendar_day`, `::test_an_empty_range_is_an_empty_result_not_an_error` |
| Skasowanie rozmowy nie zmniejsza rachunku | `test_sessions_router.py::test_deleting_a_session_does_not_reduce_the_bill` |

### `agent-database-connection`

| Requirement | Proven by |
|---|---|
| Moduł przedstawia się tożsamością, nie hasłem | `test_db.py::test_credential_selects_a_service_principal_when_all_three_are_given`, `::test_token_provider_fetches_fresh_on_every_call`, `test_config.py::test_a_database_url_with_a_credential_refuses_to_start` |
| Połączenie z bazą zdalną jest szyfrowane | `test_config.py::test_a_database_url_that_does_not_require_tls_refuses_to_start`, `::test_local_mode_does_not_require_tls` |
| Praca bez tożsamości nie wychodzi poza maszynę | `test_config.py::test_no_database_user_with_a_remote_host_refuses_to_start`, `::test_a_blank_database_user_means_local_mode_not_a_role_named_blank` |
| Moduł nie dzieli bazy z innym modułem | `migrations/` modułu i `test_db.py::test_the_test_database_is_reachable`; rozdział ról jest w `infra/database.tf`, nie w teście |
| Poświadczenie nie wycieka do logów | `test_db.py::test_a_connection_failure_is_logged_without_the_credential`, `::test_connection_target_names_host_port_and_database_never_a_credential` |

### `agent-browser-access`

| Requirement | Proven by |
|---|---|
| Rozmowa należy do operatora, który ją prowadził | `test_store.py::test_a_foreign_session_reads_as_missing`, `test_sessions_router.py::test_a_foreign_or_missing_session_reads_the_same_404`, `test_usage_store.py::test_aggregation_is_scoped_to_the_callers_own_sessions` |
| Moduł nie bierze na wiarę warstwy przed sobą | `test_auth.py::test_no_identity_with_the_requirement_on_is_refused`, `::test_no_identity_and_no_requirement_is_the_local_identity`, `test_sessions_router.py::test_required_authentication_refuses_before_touching_the_model` |
| Poświadczenie nie wędruje w adresie | `agentApi.test.ts :: "hands back the turn's events, parsed from the streamed body"` — strumień jest `POST` z `fetch`/`ReadableStream`, nie `EventSource`, więc poświadczenie jedzie nagłówkiem |
| Wywołanie z przeglądarki przychodzi z uznanego adresu | **luka** — `test_no_cors.py` dowodzi tylko, że moduł świadomie nie dokłada własnego CORS; sama lista adresów jest w `infra/app-service.tf` i pilnuje jej `terraform plan` |
| Poświadczenia nie trafiają do logów ani do odpowiedzi | `test_db.py::test_a_connection_failure_is_logged_without_the_credential`, `test_config.py::test_a_missing_api_key_refuses_to_start` |

### `terminal-agent-chat`

| Requirement | Proven by |
|---|---|
| Panel należy do terminala, nie do zakładki | `agentChatStore.test.ts :: "keeps a streaming turn alive in the store across an unmount, for a later remount to pick up"`, `AgentChat.test.tsx :: "remembers whether it was open"` |
| Operator wybiera rozmowę albo zaczyna nową | `AgentChat.test.tsx :: "opens a past conversation from the list and loads its transcript from the module"`, `:: "starts a new conversation empty, and it only joins the list after the first exchange"`, `:: "remembers which conversation was open across a reload"` |
| Model wybiera się w oknie agenta | `AgentChat.test.tsx :: "shows the model catalogue with its cost difference, never a list the terminal invented"`, `:: "says the model picker is unavailable when the catalogue cannot be read, and offers no select"` |
| Widać, że odpowiedź powstaje | `AgentChat.test.tsx :: "shows waiting before the first fragment, streams the reply in, then settles it into the transcript"`, `:: "marks a broken reply as incomplete on the bubble itself, and keeps what arrived"`, `:: "says the module is unreachable and shows no reply bubble when nothing was accepted"` |
| Lista rozmów pozwala je nazwać i usunąć | `AgentChat.test.tsx :: "renames a conversation to whatever the operator types"`, `:: "abandons a rename on Escape, leaving the name the module still holds"`, `:: "asks before deleting, and keeps the conversation when told to"`, `agentChatStore.test.ts :: "clears the panel when the conversation it is showing is deleted"` |

### `terminal-agent-cost`

| Requirement | Proven by |
|---|---|
| Zakładka pokazuje koszt w trzech przekrojach | `AgentCostView.test.tsx :: "gives all three tables the same columns, so their numbers line up"`, `:: "says nothing was used, rather than an empty table with no explanation"`, `:: "opens the conversation from its row, since the module publishes no per-call breakdown"` |
| Liczby pochodzą z modułu, nie z przeglądarki | `AgentCostView.test.tsx :: "renders numbers straight from the module — tokens, cost and unknown count, untouched"`, `:: "says the module is unreachable and does not show yesterday's numbers as current"` |

Poza jedną luką nazwaną wyżej każde wymaganie ma nazwany dowód.

## Follow-ups

- Zadanie 12.5: przejść strumieniem po wdrożonej aplikacji — buforowanie i zerwanie po
  230 s. Do wykonania przez operatora, bo tylko on uruchamia stos i tylko na Azure to
  widać.
- Zadanie 12.4, druga połowa: ta sama droga przez terminal na `5173`.
- Sonda po wdrożeniu, która sięga do kontenera zamiast do płaszczyzny sterowania — inaczej
  strażnik schematu chroni produkcję, ale nie zapala wdrożenia na czerwono.
- `market_data` ma tę samą dziurę w uprawnieniach domyślnych co `agent` miał do dziś
  (`pg_default_acl` pusta). Następna migracja tworząca tam tabelę powtórzy ten wypadek na
  archiwum wartym dwadzieścia siedem godzin odtwarzania.
