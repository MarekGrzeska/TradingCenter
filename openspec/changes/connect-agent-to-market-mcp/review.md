## Verdict

Wdrożone: `agent` woła narzędzia `market-mcp` w trakcie odpowiadania. Graf ma drugi
węzeł i krawędź warunkową między nimi; zestaw narzędzi jest odkrywany przez `tools/list`
i nie ma po tej stronie żadnej jego kopii; sufit ośmiu wywołań na turę jest liczbą w
kodzie; odmowa narzędzia wraca do modelu jako wynik, a nie kończy tury. Każde wywołanie
zostawia wiersz w `tool_calls`, każde wywołanie modelu — własny wiersz zużycia, oba pod
tą samą wypowiedzią agenta. Prompt `v3` w dwóch wariantach: z narzędziami i bez, o tych
samych granicach. Infrastruktura wpisuje tożsamość agenta w `allowed_applications`
`market-mcp` i podaje mu adres oraz scope.

Terminala nie dotknięto ani jedną linijką — świadomie, na decyzję operatora.
`agent/contract.py` nie zmienił się o żadne pole i jest to teraz asercja, nie deklaracja
(`tests/test_transcript_contract.py`). Podgląd wywołań w panelu jest następną zmianą, i
tabela, którą ta zmiana zapisuje, jest tym, co tamta odczyta.

Przegląd znalazł cztery rzeczy i wszystkie cztery były prawdziwymi błędami; żadnego z
nich nie złapał zestaw testów. Trzy z nich wyszły dopiero, gdy operator włączył
`MARKET_MCP_URL` u siebie i dostał trzy tury pod rząd oznaczone „incomplete — broke off":
modele rozumujące nie przyjmują narzędzi na `/v1/chat/completions`, węzeł modelu połykał
wyjątek bez wpisu w dzienniku, a treść z Responses API to bloki, nie string. Wszystkie
naprawione, szczegóły w Findings.

To jest dokładnie ta luka, którą ten przegląd zdążył zapisać, zanim się zmaterializowała
(„Pętla nie przeszła ani razu z prawdziwym modelem"). Zapisanie jej nie kosztowało nic i
nie uchroniło przed niczym — jedyne, co pomogło, to uruchomienie.

## Verified

Wszystko na Windows 11, z Dockerem — testy `db` weszły same, nie zostały pominięte.

- `cd modules/agent && uv run pytest -q` → `146 passed, 2 warnings`
- `cd modules/agent && uv run ruff check .` → `All checks passed!`
- `cd modules/agent && uv run pyright` → `0 errors, 0 warnings, 0 informations`
- `cd infra && terraform validate` → `Success! The configuration is valid.`
- `cd infra && terraform fmt -check -recursive` → czysto
- `bash -n scripts/dev.sh` → czysto; `dev.ps1` przez `[Parser]::ParseFile` → bez błędów
- `openspec validate connect-agent-to-market-mcp --strict` → `Change ... is valid`

**Przebieg przeciw prawdziwemu stosowi** (task 5.5): operator miał już uruchomione
8010/8020/8030/8040, więc klient agenta poszedł do prawdziwego `market-mcp` z prawdziwym
archiwum za nim. Odkrył 10 narzędzi z ich własnymi opisami, wyciągnął zbierane pary
(SILVER i dalej), na symbol spoza archiwum dostał notatkę „nobody is collecting it, not
because the market was quiet", odczytał katalog wskaźników i na złym porcie odpowiedział
`unavailable`.

**Pełna pętla z prawdziwym modelem** (`gpt-5.6-luna`, prawdziwy `market-mcp`, prawdziwe
archiwum). Pytanie: „które pary archiwum zbiera i jaka jest ostatnia cena jednej z nich".
Wynik: dwa obroty, `list_tracked_pairs` (72 ms) i `get_last_price` z rozdzielczością,
którą model wybrał sam (32 ms), trzy wywołania modelu, `failed=False`, odpowiedź niosąca
cenę bid, moment w UTC i wiek świecy. Ten przebieg jest tym, co wywróciło trzy błędy z
tabeli niżej; przed nimi nie działała ani jedna tura z narzędziami.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| **High** | `modules/agent/agent/provider.py` | Każda tura z narzędziami wywracała się na `400` od OpenAI: „Function tools with reasoning_effort are not supported for gpt-5.6-luna in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'none'." Modele rozumujące nie łączą narzędzi z `reasoning_effort` na starym endpoincie. Operator zobaczył trzy tury pod rząd jako „incomplete — broke off". Nie złapał tego żaden test, bo 146 testów wywołuje podstawionego dostawcę, a `ChatOpenAI` konstruuje się bez błędu — 400 przychodzi dopiero z sieci; luka nazwana w Gaps tego przeglądu („Pętla nie przeszła ani razu z prawdziwym modelem") zmaterializowała się w tej samej godzinie, w której ją zapisano. Naprawione: `use_responses_api=True`, dla każdego wywołania, nie tylko z narzędziami — druga droga (`reasoning_effort="none"`) kupuje narzędzia, oddając rozumowanie, po które ten model został wybrany. Test na kształt klienta, w tym po `bind_tools`. | fixed |
| **High** | `modules/agent/agent/graph.py` | Wyjątek dostawcy był łapany i zamieniany na `failed=True` **bez jednego wiersza dziennika**. `turn.py` ma własny backstop z `log.exception`, ale on nigdy nie działa, bo z węzła nic nie propaguje. Skutkiem było „incomplete — broke off" w panelu i cisza wszędzie indziej: nie dało się dowiedzieć, co pękło, bez podstawienia własnego skryptu — i tak właśnie znaleziono błąd powyżej. Naprawione: `log.exception` z liczbą dotychczasowych wywołań i liczbą oferowanych narzędzi, przed zamianą wyjątku na flagę. | fixed |
| **Medium** | `modules/agent/agent/provider.py` | Na Responses API `content` to lista bloków, a wywołanie narzędzia jest jednym z nich — `str(chunk.content)` wysłałby operatorowi do panelu `[{'type': 'function_call', 'name': 'list_tracked_pairs', ...}]` jako prozę. Ukryte za błędem powyżej: dopóki każda tura z narzędziami kończyła się 400, ten kod nigdy nie doszedł do bloku wywołania. Naprawione: `chunk.text`, który bierze bloki tekstowe i nic więcej, a na starym kształcie zwraca ten sam string. Test na obu kształtach. | fixed |
| **Medium** | `modules/agent/agent/tools/client.py` | Awaria dostępu do serwera narzędzi docierała do modelu jako `the tool server could not be reached: unhandled errors in a TaskGroup (1 sub-exception)`. Obie połówki transportu streamable-http chodzą w grupie zadań anyio, więc odmowa połączenia wychodzi opakowana w `BaseExceptionGroup`, którego `str()` nie nazywa niczego. Model dostawał zdanie bez treści dokładnie w sytuacji, w której ma powiedzieć operatorowi, co się stało — a operator dostawał to samo w dzienniku. Nie złapały tego testy: asercje sprawdzały rodzaj wyniku (`UNAVAILABLE`) i stałą część zdania, nie zmienną. Złapał przebieg z zadania 5.5, bo tam ten tekst po prostu widać. Naprawione: `_describe` rozwija grupę rekurencyjnie i deduplikuje liście — komunikat brzmi teraz `All connection attempts failed`. Test na zagnieżdżonych grupach plus asercja `"TaskGroup" not in outcome.text` w teście nieosiągalnego serwera. | fixed |

Sprawdzone i **niebędące** błędami — obie rzeczy wyglądały na problem i obie zostały
rozstrzygnięte pomiarem, nie rozumowaniem:

- **Sesja MCP przeżywa granicę tasków.** Router uruchamia każdą turę jako osobny
  `asyncio.create_task`, więc sesja powstaje w jednym tasku, a jest używana i zamykana w
  innych. Transport trzyma swoje połówki w grupie zadań anyio, a wyjście z zakresu grupy
  w innym tasku niż wejście to udokumentowany sposób na `RuntimeError`. Zmierzone: działa
  — otwarcie w turze pierwszej, użycie w drugiej, dwie równoległe i zamknięcie w
  czwartym tasku. Utrwalone testem
  (`test_tool_server.py::test_one_session_serves_turns_that_are_separate_tasks`), który
  jest też tym, co pęknie, jeśli przyszła wersja SDK przestanie to tolerować.
- **Sufit ośmiu a `recursion_limit` LangGraph.** Tura o N obrotach to 2N+1 superkroków,
  a domyślny limit to 25. Przy ośmiu to 17 — mieści się. Przy jedenastu graf wywróciłby
  się własnym błędem, zanim sufit zdążyłby cokolwiek powiedzieć, i nic w kodzie by na to
  nie wskazywało. Dopisane w komentarzu przy samej stałej, bo to jedyne miejsce, w którym
  ktoś ją podniesie.

## Deviations from design.md

- **Zapis wywołań przeniesiony z `graph.py` do `models.py`.** `design.md` mówi „Osobna
  tabela ... pisana po `append_agent_message`" i tak jest; niezapowiedziane jest to, że
  `RecordedCall` mieszka w `models.py`, a nie tam, gdzie powstaje. Powód: inaczej
  `store.py` importowałby `graph.py`, czyli warstwa bazy zależałaby od warstwy
  sterowania. To jest kształt domenowy — wywołanie, które się odbyło, zanim dostanie
  wiersz — i obie strony go potrzebują.
- **Prompt to dwa teksty, nie jeden z akapitem warunkowym.** `design.md` nie
  rozstrzygał, jak wygląda „wariant bez narzędzi" z zadania 4.3. Wybrane: dwa pełne
  teksty pod jedną wersją, ze wspólnym akapitem granic wstawianym w oba. Wersja jest
  jedna, bo to nie jest zmiana promptu — to fakt o turze.
- **`scripts/dev.*` nie wstrzykują `MARKET_MCP_URL`.** Zadanie 5.3 mówiło „agent dostaje
  `MARKET_MCP_URL` wskazujący na lokalny serwer". Zrobione inaczej: ustawienie jest w
  `.env.example`, a skrypty **mówią przy starcie**, gdy w `modules/agent/.env` go nie ma.
  Wstrzyknięcie przez zmienną środowiskową nadpisałoby świadomy wybór operatora, bo w
  `pydantic-settings` zmienna środowiskowa wygrywa z `.env` — a „chcę dziś bez narzędzi"
  jest poprawnym stanem tego modułu.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **agent-tools: Model sięga po narzędzia w trakcie odpowiadania** | |
| Pytanie wymagające danych archiwum | `test_graph.py::test_one_tool_call_produces_two_model_calls_and_one_record`, `::test_the_second_model_call_sees_the_round_it_asked_for` |
| Pytanie bez potrzeby narzędzia | `test_graph.py::test_a_turn_without_tool_calls_ends_after_one_model_call` |
| Prośby i wyniki nie są wiadomościami | `test_transcript_contract.py::test_a_message_on_the_wire_carries_exactly_these_fields`, `::test_nothing_about_tools_reaches_the_transcript`; `test_tool_calls_store.py::test_three_calls_leave_three_rows_in_a_recoverable_order` (trzy wywołania, jedna wypowiedź) |
| **agent-tools: Zestaw narzędzi pochodzi z serwera, nie z tego modułu** | |
| Narzędzie dołożone po stronie serwera | `test_tool_server.py::test_the_tool_list_comes_from_the_server` — zestaw jest dokładnie tym, co ogłosił serwer, więc dołożone tam pojawia się tutaj. Samego dołożenia w locie nie testuje nic; patrz Gaps |
| Opis narzędzia zmieniony po stronie serwera | `::test_the_tool_list_comes_from_the_server` (asercja na treści opisu i na schemacie parametru, oba z serwera) |
| **agent-tools: Wszystkie narzędzia agenta są czytające** | |
| Operator prosi o wykonanie akcji | `test_tool_server.py::test_the_tool_list_comes_from_the_server` (zestaw równy serwerowemu co do nazwy — moduł nie dokłada własnego narzędzia), `test_prompt.py::test_with_tools_the_prompt_says_the_tools_change_nothing` |
| **agent-tools: Tura ma sufit wywołań narzędzi** | |
| Model prosi o narzędzia bez końca | `test_graph.py::test_the_ceiling_stops_the_calls_and_still_gets_an_answer` — dokładnie osiem wywołań u serwera, dziewiąty model bez narzędzi, tura kończy się wypowiedzią |
| **agent-tools: Odmowa narzędzia jest wynikiem, nie awarią tury** | |
| Model prosi o nieznany symbol | `test_graph.py::test_a_refusal_reaches_the_model_and_the_turn_carries_on` (poprawia żądanie i dostaje odpowiedź), `test_tool_server.py::test_a_refusal_arrives_as_a_result_with_the_servers_own_words` |
| Model prosi o zakres ponad sufit narzędzia | te same dwa: zdanie serwera dociera do modelu dosłownie, `failed is False` |
| **agent-tools: Wywołanie narzędzia zostawia ślad** | |
| Tura z kilkoma wywołaniami | `test_tool_calls_store.py::test_three_calls_leave_three_rows_in_a_recoverable_order`, `::test_record_tool_calls_numbers_positions_within_each_round` |
| Wywołanie zakończone odmową | `test_tool_calls_store.py::test_a_refused_call_is_recorded_with_its_reason` |
| Ślad przy turze niepełnej | `test_tool_calls_store.py::test_an_incomplete_turn_still_records_what_it_managed` |
| **agent-tool-access: Tryb połączenia z serwerem narzędzi jest wybrany jednoznacznie** | |
| Adres zdalny bez tożsamości | `test_config.py::test_remote_tool_server_without_a_scope_is_refused` |
| Pętla zwrotna bez tożsamości | `test_config.py::test_loopback_tool_server_without_a_scope_is_accepted`, `::test_a_blank_tool_server_url_means_unset` |
| Oba tryby naraz | `test_config.py::test_scope_with_a_loopback_tool_server_is_refused`, `::test_a_scope_with_no_url_at_all_is_refused` |
| **agent-tool-access: Brak serwera narzędzi nie odbiera agentowi mowy** | |
| Serwer narzędzi nie odpowiada | `test_tool_server.py::test_an_unreachable_server_publishes_no_tools_rather_than_failing`, `::test_an_unreachable_server_is_unavailable_not_a_refusal`; `test_graph.py::test_an_unavailable_server_is_a_result_not_a_failed_turn`; `test_tool_calls_store.py::test_a_turn_without_tools_runs_the_prompt_that_says_so` (model dostaje prompt, który każe mu to powiedzieć); `test_prompt.py::test_without_tools_the_prompt_says_so_plainly` |
| Moduł startuje bez skonfigurowanego serwera | `test_config.py::test_no_tool_server_configured_is_a_valid_state`, `test_tool_server.py::test_no_configured_server_means_no_tools_and_no_calls`, `test_tool_calls_store.py::test_a_turn_with_no_tool_server_records_no_calls` |
| **agent-tool-access: Wołanie serwera narzędzi ma skończony czas** | |
| Narzędzie nie odpowiada w czasie | `test_tool_server.py::test_a_slow_server_times_out_as_unavailable` (prawdziwy serwer, prawdziwy limit 1 s) |
| Odróżnialne od odmowy | ten sam test przeciw `::test_a_refusal_arrives_as_a_result_with_the_servers_own_words` — `UNAVAILABLE` kontra `REFUSED`, dwa różne zdania |
| **agent-tool-access: Moduł nie trzyma kopii tego, co ogłasza serwer narzędzi** | |
| Narzędzie znika po stronie serwera | `test_tool_server.py::test_the_tool_list_comes_from_the_server` plus `_disconnect`, które zrzuca listę razem z sesją; samego zniknięcia w locie nie testuje nic — patrz Gaps |
| Moduł nie ma czego sprawdzać przed startem | strukturalnie: w `modules/agent` nie ma ani pliku snapshotu, ani `scripts/contract.py`, ani wpisu w `checks.yml`. Nie ma na to asercji i nie powinno być — testem tego jest brak pliku |
| **agent-chat (MODIFIED): Agent pracuje na jednym prompcie systemowym** | |
| Sesja pamięta wersję promptu | `test_store.py` (bez zmian w tej zmianie), `test_prompt.py::test_prompt_version_is_set` |
| Prompt zmienia się między rozmowami | `test_prompt.py::test_the_version_moved_when_the_prompt_did` |
| Prompt nazywa granice tego, co narzędzia mówią | `test_prompt.py::test_with_tools_the_prompt_names_the_three_easy_over_readings`, `::test_the_two_prompts_differ_only_where_the_world_does` |
| Agent bez narzędzi mówi, że ich nie ma | `test_prompt.py::test_without_tools_the_prompt_says_so_plainly`; `test_tool_calls_store.py::test_a_turn_without_tools_runs_the_prompt_that_says_so` i `::test_a_turn_with_tools_runs_the_prompt_that_says_that` — wybór tekstu robi się z tego, co tura naprawdę ma, nie z konfiguracji |
| **agent-usage (MODIFIED): Każde wywołanie modelu zostawia ślad zużycia** | |
| Zwykła wymiana zdań | `test_turn.py::test_fragments_arrive_before_completion`, `test_usage_router.py::test_usage_reflects_a_completed_turn` |
| Tura z wywołaniem narzędzia | `test_tool_calls_store.py::test_two_model_calls_leave_two_usage_rows_under_one_reply` — dwa wiersze, jedna wypowiedź, suma czytana przez `usage_by_session`, czyli przez ten sam agregat co zakładka kosztów |
| Odpowiedź przerwana błędem | `test_turn.py::test_usage_reported_before_a_failure_is_still_recorded` |
| Dostawca nie podał liczb | `test_turn.py` i `test_usage_store.py` (bez zmian) |

## Gaps

- ~~**Pętla nie przeszła ani razu z prawdziwym modelem.**~~ Przeszła, i kosztowała trzy
  błędy z tabeli wyżej. Zmierzone na `gpt-5.6-luna` z działającym `market-mcp`: pytanie
  „które pary archiwum zbiera i jaka jest ostatnia cena jednej z nich" dało dwa
  wywołania narzędzi w dwóch obrotach (`list_tracked_pairs`, potem `get_last_price` z
  rozdzielczością wybraną przez model), trzy wywołania modelu i odpowiedź niosącą cenę
  bid, moment w UTC i wiek świecy — czyli dokładnie to, czego prompt `v3` wymaga.
  Zostaje niezmierzone, jak pętla zachowuje się na droższych modelach z katalogu i przy
  pytaniach wymagających wskaźników.
- **Sufit ośmiu nie jest zmierzony, tylko oszacowany.** Wybrany z tego, jak wygląda
  hipotetyczna tura analityczna. Ile wywołań realnie robi model, wiadomo będzie z
  `tool_calls` po tygodniu — i wtedy dopiero ta liczba ma podstawę.
- **Cisza w panelu, kiedy narzędzie pracuje.** Strumień niesie tylko fragmenty tekstu, a
  wywołanie to do 15 sekund. Zapisane w `design.md` jako ryzyko i pozostaje otwarte;
  znika razem z podglądem wywołań w terminalu, czyli w następnej zmianie.
- **Zmiana zestawu narzędzi w locie nie jest testowana.** Lista jest pobierana raz na
  sesję z serwerem i zrzucana razem z nią przy każdej awarii, więc `market-mcp` po
  restarcie z innym zestawem zostanie odczytany od nowa. Testu na to nie ma: wymagałby
  serwera zmieniającego swój zestaw w trakcie, a to jest test SDK, nie tego modułu.
- **Archiwizacja tej zmiany jest zablokowana do czasu zarchiwizowania
  `add-agent-chat`.** `agent-chat` i `agent-usage` żyją w katalogu tamtej zmiany, nie w
  `openspec/specs/`, więc delty MODIFIED nie mają się do czego przyłożyć. Ta zmiana nic
  na to nie poradzi i nie próbuje; zapisane też w nagłówku `tasks.md`.
- **Nowe narzędzie po stronie `market-mcp` trafia do modelu bez przeglądu tutaj.**
  Przyjęte świadomie w `design.md`; broni tego zakaz narzędzi zapisujących w
  specyfikacji `market-mcp` i jego test powierzchni. Ryzyko materializuje się w dniu, w
  którym ten zakaz by padł, i nic po tej stronie o tym nie przypomni.
