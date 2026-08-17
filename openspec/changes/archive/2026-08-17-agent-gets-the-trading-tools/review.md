# Review

## Verdict

Zmiana jest napisana w całości i **stoi na produkcji**: `agent` ma `TRADING_MCP_URL` i
`TRADING_MCP_SCOPE`, a tożsamość agenta jest w `allowed_applications` `trading-mcp`, więc
para „kod bez ustawienia / ustawienie bez wpisu" jest domknięta z obu stron. Rdzeniem nie są
same narzędzia — te przyszły z `add-trading-tools` — a czwarty skutek wywołania: `unknown`,
odróżniony od `unavailable` w kodzie, w bazie (`0011`), na drucie, w promptcie (`0012`) i w
kolorze w terminalu. Ślad powstaje przed wysłaniem i jest domykany po, a wiersz, którego
nikt nie domknął, wychodzi własną trasą, bo nie ma wypowiedzi, pod którą dałoby się go
podwiesić.

Przegląd znalazł trzy rzeczy i żadna nie dotyczy tego, czy zlecenie dociera. Jedna
zatrzymywała archiwizację i jest naprawiona w tym przeglądzie; dwie zostają zapisane jako
otwarte, obie w tym samym miejscu: **`unknown` mówi „może doszło" także wtedy, gdy moduł
wie, że nic nie wyszło**, i to samo w terminalu — blok o wywołaniu bez odpowiedzi pokazuje
się nad zleceniem, które właśnie normalnie leci. Kierunek obu pomyłek jest bezpieczny
(alarm zamiast ciszy), ale oba uczą operatora nie ufać najgłośniejszej rzeczy w tym panelu,
a to jest dokładnie ta obietnica, na której cała zmiana stoi.

Z pomiaru na żywo (8.4) jest **połowa**: operator potwierdził w terminalu, że wdrożony agent
widzi rachunek — narzędzia doszły, więc cała droga tożsamości i ustawień działa od czatu do
gatewaya. Nie ma drugiej połowy: **żadne zlecenie nie zostało złożone**, więc to, że ślad
powstaje przed odpowiedzią, jest tu sprawdzone wyłącznie przeciw dublerowi serwera narzędzi,
a nie na rachunku.

## Verified

Uruchomione 17 sierpnia 2026 na `main` (`af52a78`), po naprawie z pierwszego wiersza
`Findings`:

- `modules/agent`: `uv run ruff check .` — „All checks passed!". `uv run pyright` —
  **0 errors, 0 warnings**. `uv run pytest -q` — **371 passed**. `uv run pytest -m db -q` —
  **234 passed**, 137 deselected, przeciw jednorazowemu PostgreSQL-owi w kontenerze.
- `modules/terminal`: `tsc -b --noEmit` — czysto. `node scripts/contract.mjs check` —
  „Every contract is up to date." `eslint .` — czysto. `vitest run` — **901 passed**
  w 57 plikach.
- `openspec validate agent-gets-the-trading-tools --strict` — „is valid". **Przed naprawą
  z `Findings` to samo polecenie kończyło się błędem**, mimo że zadanie 8.3 jest odhaczone.
- `infra`: `terraform init`, potem `plan` — **0 to add, 6 to change, 0 to destroy**, co do
  liczby to, co zadanie 6.3 przewidziało. `apply` z zapisanego planu — **0 added,
  2 changed, 0 destroyed**: sześć z planu, bo cztery listy `allowed_applications` wracały
  jako `(known after apply)`, i cztery z nich okazały się bez różnicy. Żadnego `azuread_*`,
  więc filtr `terraform-apply.yml` nie miał czego odrzucać.
- Azure, odczytane z płaszczyzny sterowania, **nie ze stanu Terraforma** (zadanie 6.4):
  `az webapp config appsettings list` na `app-tradingcenter-agent` — `TRADING_MCP_URL` =
  `https://app-tradingcenter-trading-mcp.azurewebsites.net`, `TRADING_MCP_SCOPE` =
  `api://tradingcenter-trading-mcp/.default`, obok nietkniętych `MARKET_MCP_*` i
  `TEAMS_MCP_*`. `authsettingsV2` `trading-mcp` — `allowedApplications` z **dwoma** wpisami:
  `b4569a04-…` (`teams`) i `126d11d3-…`, który `az ad sp show` potwierdza jako
  `app-tradingcenter-agent`. Cztery pozostałe listy wróciły identyczne: `market-data`
  `[6682e44a, 85d133f7]`, `market-mcp` `[126d11d3, b4569a04]`, `teams` `[6682e44a,
  f75704dc]`, `teams-mcp` `[126d11d3]`.
- Wdrożony obraz: `agent:6754a244c77f65e6cc773b66644e7556a10d563a`, czyli merge tej zmiany.
  `GET /health` — **200**, a skoro migracja idzie w `lifespan` przed obsługą ruchu, jest to
  jednocześnie dowód schematu na `head` (`0012`).
- **Odczyt rachunku na żywo — potwierdzony przez operatora** 17 sierpnia 2026: wdrożony
  agent zapytany w terminalu o pozycje widzi je, zamiast odpowiadać, że nie ma takich
  narzędzi. To jest potwierdzenie operatora, nie polecenie zapisane w tym repo, i dotyczy
  wyłącznie narzędzi czytających.
- **Nie uruchamiano:** żadnego zlecenia na koncie demo — więc ani ścieżki `unknown`, ani
  śladu przed wysłaniem nikt nie widział poza testami — i żadnego przebiegu na uruchomionym
  lokalnie stosie. Testów `live` ten moduł nie ma i nie zyskał: serwer narzędzi jest w
  testach dublowany.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| **Medium** | `openspec/changes/agent-gets-the-trading-tools/specs/agent-tools/spec.md:51` | Delta zmieniała nazwę scenariusza (`Operator prosi o wykonanie akcji poza wykresem` → `…poza tymi dwoma zakresami`), a OpenSpec 1.8.0 nie ma zmiany nazwy na poziomie scenariusza: `MODIFIED` zastępuje cały blok, więc zniknięcie starej nazwy czyta jako **skasowanie scenariusza** i `validate --strict` odmawia. Zmiany nie dało się zarchiwizować, mimo że zadanie 8.3 jest odhaczone — pomiar był albo sprzed zmiany nazwy, albo nie został powtórzony po niej. | FIXED w tym przeglądzie: nazwa scenariusza wraca do tej, którą niesie spec, ciało zostaje nowe — bo to ciało było tym, co się zmieniło. Tytuł wymagania niesie nowy zakres i on się nie zmienia. |
| **Low** | `modules/agent/agent/tools/client.py:245` | `may_have_landed` obejmuje **całe** `async with self._session_for(...)`, więc awaria *zestawienia* sesji — martwy port, DNS, 401 od Easy Auth, nieudany token z `DefaultAzureCredential` — daje `unknown` i zdanie „the call may have gone through — do not send it again… check the account". W tym przypadku moduł wie, że nic nie wyszło: `session.call_tool` nigdy nie zostało wywołane. Trafia to dokładnie w połowiczny stan, który `CLAUDE.md` opisuje jako spodziewany — obraz z narzędziami przy tożsamości jeszcze niewpisanej w `allowed_applications` — i wtedy **każda** próba zlecenia zostawia wiersz „nieznany" i każe operatorowi sprawdzać rachunek, na którym nic nie stoi. Zachowanie jest celowe i otestowane (`test_an_unreachable_write_is_unknown_rather_than_unavailable` używa martwego portu), więc to nie jest przeoczenie — to wybór, którego cena jest wyższa, niż wygląda: alarm, który myli się w przewidywalny sposób, przestaje być alarmem. | Otwarte, zapisane. Naprawa jest rozdzieleniem, nie zmianą zasady: pobrać sesję przed okienkiem „mogło dojść", a `UNKNOWN` zostawić dla awarii po tym, jak `call_tool` zostało oczekiwane. `UNAVAILABLE` z „nothing was sent" jest wtedy prawdziwe i nadal ostrożne. |
| **Low** | `modules/agent/agent/store.py:318` (`_SELECT_SESSION_ORPHAN_TOOL_CALLS`) | „Osierocony" to `message_id IS NULL`, a wiersz nosi `NULL` **od `begin_tool_call` do końca tury** — więc także wtedy, gdy tura normalnie trwa. Odświeżenie strony albo powrót do rozmowy w chwili, gdy zlecenie leci (do 35 s), pokazuje blok w kolorze krytycznym: „One call was left without a reply… Check the account before asking again" — o wywołaniu, które właśnie się wykonuje. Znika przy następnym odczycie, więc jest to fałszywy alarm przelotny, ale okno pokrywa się dokładnie z powodem, dla którego operator odświeża stronę: odpowiedź długo nie przychodzi. | Otwarte, zapisane. Trasa potrzebuje pojęcia „jeszcze leci" — najprościej pomijając wiersze młodsze od sufitu tury, bo tura ma swój własny ograniczony czas. |

Nie znalezione, choć szukane, i warte zapisania, żeby następny czytelnik nie sprawdzał
drugi raz: `position` zgadza się między dwiema drogami zapisu (`graph.py` daje
`len(recorded)` w obrębie rundy, `record_tool_calls` liczy pominięte wiersze, zamiast je
przeskakiwać — inaczej każde późniejsze wywołanie w rundzie przesunęłoby się o jeden);
`attach_tool_calls_to_message` nie przejmie cudzego wiersza (`AND message_id IS NULL`);
`Complete` ląduje na kolejce **po** zapisie, więc terminal czytający po zamknięciu
strumienia nie widzi wiersza jeszcze niepodwieszonego; a `read_only is not True` traktuje
brak adnotacji jako zapis, czyli w stronę wiersza za dużo.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **agent-trading** — Moduł nie narzuca własnych granic handlowych | Dowodem jest brak kodu: nigdzie nie ma walidacji wielkości ani licznika zleceń. Argumenty modelu docierają do serwera bez zmiany — `test_graph.py::test_an_order_is_traced_before_it_is_sent_and_settled_after` (`{"symbol": "US100"}` w takiej samej postaci w śladzie i u serwera) |
| — Operator prosi o zlecenie dowolnie dużej wielkości | Ten sam test dla kształtu; wielkości ponad zdrowy rozsądek nie sprawdza żaden test → luka |
| — Wiele zleceń w jednej rozmowie | Testu nie ma, licznika też nie ma → luka |
| — Tura osiąga sufit wywołań przy narzędziu zapisującym | Testu nie ma. Sam sufit jest sprawdzony (`test_graph.py::test_the_ceiling_stops_the_calls_and_still_gets_an_answer`, `::test_both_kinds_of_tool_share_one_turn_and_one_ceiling`), ale żaden test nie bada brzmienia komunikatu przy wywołaniu zapisującym → luka |
| — Wywołanie ruszające rachunek zostawia ślad przed wysłaniem | `test_graph.py::test_an_order_is_traced_before_it_is_sent_and_settled_after`, `::test_a_read_gets_no_trace_of_its_own`, `::test_an_order_whose_trace_cannot_be_written_is_not_sent`, `::test_without_a_trace_at_all_the_graph_still_runs_orders` |
| — Tura umiera po złożeniu zlecenia | `test_tool_calls_store.py::test_a_turn_that_dies_with_the_order_in_flight_still_leaves_it_unknown`, `::test_a_turn_that_dies_after_the_order_settled_keeps_the_settled_row` |
| — Odpowiedź na wywołanie zapisujące nie wraca | `test_tool_calls_store.py::test_an_order_whose_answer_never_came_is_recorded_as_unknown`, `test_tool_server.py::test_an_unreachable_write_is_unknown_rather_than_unavailable`, `::test_a_slow_write_times_out_as_unknown`, `::test_a_read_on_the_same_server_is_still_unavailable` |
| — Zlecenie zostaje złożone | `test_tool_calls_store.py::test_an_order_that_answered_reads_back_like_any_other_call`, `::test_settling_replaces_the_placeholder_the_row_was_begun_with`, `::test_a_read_beside_an_order_keeps_its_place_in_the_round`, `::test_attaching_never_claims_a_row_that_already_belongs_to_a_reply` |
| — Operator odczytuje, co agent zrobił na rachunku | `test_sessions_router.py::test_an_order_that_outlived_its_turn_reaches_the_wire`, `::test_unclaimed_tool_calls_are_empty_for_a_turn_that_reached_its_reply`; terminal `AgentChat.test.tsx` → „shows the calls no reply claimed, and says what they are", „says nothing about unclaimed calls when there are none", „keeps the transcript when the unclaimed read is the thing that fails" |
| — Agent nie potwierdza zlecenia, którego skutku nie zna | Sprawdzone **na promptcie i na tekście wyniku**, nie na zachowaniu modelu: `test_prompt_store.py::test_both_seeded_texts_forbid_resending_a_call_of_unknown_outcome`, `::test_both_seeded_texts_name_the_trading_tools`, `::test_no_seeded_text_still_claims_the_agent_cannot_place_an_order`, `::test_both_seeded_texts_say_the_account_is_a_demo_one`; słowa, które dostaje model — `test_tool_server.py::test_an_unreachable_write_is_unknown_rather_than_unavailable` („may have gone through", „do not send it again", bez „was not made") |
| — Agent po nieznanym skutku zlecenia | Te same testy promptu. Tego, że model tak **odpowie**, nie sprawdza nic → luka (zadanie 8.4) |
| — Agent nie ponawia zlecenia sam | Prompt zabrania i to jest sprawdzone; że model nie ponowi — nie → luka (zadanie 8.4) |
| — Narzędzie odmawia zlecenia | `test_tool_server.py::test_a_refusal_arrives_as_a_result_with_the_servers_own_words`, `::test_an_unknown_tool_is_a_refusal_not_an_outage`; terminal `toolCall.test.ts` → „carries an unknown outcome through as itself", „keeps an outcome it has no name for out of the four it does" |
| **agent-tools** (MODIFIED) — Agent zapisuje w widoku terminala i na rachunku demonstracyjnym | `test_tool_registry.py::test_from_settings_builds_three_servers_and_only_one_forwards_the_operators_token`, `::test_only_trading_mcp_is_built_as_a_server_that_can_move_the_account`, `::test_whether_a_name_moves_the_account_is_answered_by_its_own_server`, `::test_a_name_nobody_announced_does_not_move_the_account` |
| — Operator prosi o złożenie zlecenia | `test_prompt_store.py::test_no_seeded_text_still_claims_the_agent_cannot_place_an_order` (zdanie „nie umiem" usunięte z promptu, bo stało się fałszem), `test_tool_server.py::test_the_read_only_hint_comes_from_the_server`, `::test_an_unannotated_tool_counts_as_moving_the_account`, `::test_a_name_this_server_never_described_counts_as_moving_the_account` |
| — Operator prosi o pokazanie wskaźnika / o naniesienie oporu / cofa to, co ustawił albo narysował agent | Bez zmiany w tej zmianie: testy `test_chart_focus_tool.py` i `test_drawings_tool.py` sprzed niej, przechodzą dalej |
| — Operator prosi o wykonanie akcji poza wykresem | Ciało scenariusza jest w tej zmianie nowe (dwa zakresy zapisu zamiast jednego), sprawdzenia nie zyskało: dowodem jest zestaw narzędzi, którego moduł nie ma — `test_tool_registry.py::test_one_server_configured_and_the_others_absent_is_a_working_configuration` |
| — Konfiguracja trzech serwerów niezależnie | `test_tool_registry.py::test_the_trading_server_is_configured_without_touching_the_other_two`, `::test_a_blank_trading_server_url_means_unset`, `::test_the_trading_servers_ceiling_matches_what_trading_mcp_waits_for` |
| — Czwarty skutek na drucie i w terminalu | `agent/contract.py` (`examples`), migracja `0011` i `test_migrate.py::test_the_account_trace_migration_comes_back_down_over_a_row_it_forbids`; terminal `AgentChat.test.tsx` → „shows an unknown outcome as the loudest of the four, not as an outage" |
| **terminal-chart** (MODIFIED) — Operator zarządza naniesionymi obiektami z listy | Zmiana jest wyłącznie odsyłaczem do nowej nazwy wymagania `agent-tools`; nie ma w niej zachowania, które dałoby się sprawdzić, i testów tej listy nie rusza |
| `allowed_applications` — agent wpuszczony do `trading-mcp` | Testu nie ma i mieć nie może: egzekwuje to Easy Auth przed kontenerem. Dowodem jest odczyt `authsettingsV2` w sekcji `Verified` |

## Gaps

- **8.4 wykonane w połowie.** Odczyt rachunku na żywo jest potwierdzony przez operatora;
  zlecenie na koncie demo nie zostało złożone, więc ani `unknown`, ani ślad powstający przed
  wysłaniem nie zostały zobaczone nigdzie poza testami. „Agent nie potwierdza zlecenia,
  którego skutku nie zna" opiera się do tego czasu na promptcie i na tekście wyniku —
  sprawdzone jest to, co model **dostaje**, nie to, co z tym robi. Zamknięte świadomie na
  tym etapie, nie przeoczone.
- **Trzy scenariusze bez testu w „Moduł nie narzuca własnych granic handlowych".** Dowodem
  jest tam brak kodu, co dla dwóch pierwszych jest uczciwe (nie ma czego wywołać), ale
  trzeci — brzmienie komunikatu o sufitcie przy narzędziu zapisującym — jest zwykłym
  tekstem i dałby się sprawdzić jednym asertem. Dziś komunikat mówi „this turn has already
  made 8 tool calls, which is the limit", czyli nazywa wywołania, nie zlecenia; nic tego
  nie pilnuje.
- **Dwa znaleziska zostają otwarte** (`Low` w tabeli wyżej): `unknown` dla awarii
  zestawienia sesji, i blok o wywołaniach bez odpowiedzi zapalający się nad wywołaniem,
  które jeszcze trwa. Oba mylą się w stronę alarmu, więc żadne nie ukrywa zlecenia — i oba
  zużywają tę samą wiarygodność.
- **`unknown` nie ma drogi wyjścia.** Wiersz zapisany jako nieznany zostaje nieznany na
  zawsze: nic go później nie uzgadnia z rachunkiem, choć `trading-mcp` umie przeczytać
  pozycje. Nie jest to usterka tej zmiany — spec żąda właśnie tego, żeby wiersza nie
  ruszać — ale operator, który sprawdzi rachunek i już wie, nie ma gdzie tego zapisać.
