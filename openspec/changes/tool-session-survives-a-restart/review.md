## Verdict

Weszło jedno i drugie: `teams` ponawia wywołanie odrzucone jako nieznana sesja — raz, po jej
odtworzeniu — a okno outputów doczytuje nagrane wywołania po zakończeniu przebiegu i tym samym
zamyka duplikat strumień+nagrane, zostawiony jako otwarty w review zmiany `size-orders-by-margin`.

**Jedna rzecz jest tu ważniejsza od tego, co weszło: podczas pisania testów wyszedł osobny, cięższy
defekt i został świadomie NIE naprawiony.** Serwer narzędzi, który znika i **nie** wraca — a nie
restartuje się — potrafi wyprowadzić z `ToolServer.call()` `CancelledError` zamiast `ToolOutcome`,
czyli złamać obietnicę z pierwszego akapitu docstringu tego modułu („A call never raises into the
run"). Szczegóły i dowód niżej, w Findings. Nie jest to regresja tej zmiany i nie jest to coś, co
wolno naprawić na wyczucie w module składającym zlecenia.

## Verified

| Gdzie | Komenda | Wynik |
|---|---|---|
| teams | `uv run ruff check .` · `uv run pyright` | `All checks passed` · `0 errors` |
| teams | `uv run pytest tests/test_tool_server.py -q` | **17 passed** |
| teams | `uv run pytest -q` | **349 passed** |
| terminal | `pnpm typecheck` · `pnpm lint` | bez wyjścia · bez wyjścia |
| terminal | `pnpm test` | **888 passed (57 plików)** |

Nie uruchamiano: `-m db` (schemat nietknięty), `-m live`. Ponowienie nie zostało sprawdzone wobec
prawdziwego `trading-mcp` na Azure — dowodem jest stand-in restartowany na tym samym porcie.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| poważne | `teams/tools/client.py:280` (`call`) | Serwer, który **znika bez powrotu** przy otwartej sesji, kasuje grupę zadań transportu; oczekujące `session.call_tool` dostaje `CancelledError`, a to `BaseException` i przechodzi obok każdego `except Exception` w tym pliku. `call()` **podnosi** wtedy wyjątek do przebiegu zamiast zwrócić `unavailable`. Odtworzone testem (stand-in wyłączony bez następcy) — traceback: `anyio.WouldBlock` → `CancelledError: Cancelled via cancel scope`. Nie jest to regresja: ta ścieżka zachowuje się tak samo przed tą zmianą. | **otwarte, świadomie** — patrz Gaps |
| drobne | `tests/test_tool_server.py` | Asercja tekstu wyniku narzędzia zapisującego pisana jako `"order placed"`, gdy SDK oddaje `{"result": "order placed"}` przez `structuredContent`. | **FIXED** w `bacf219` |

Odnotowane, bez zmiany: `duration_ms` ponowionego wywołania obejmuje obie próby. Tak ma być — to
czas, przez który czekał model — i jest to jedyne miejsce, w którym ponowienie widać w śladzie.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **teams-tool-access — Wywołanie odrzucone z powodu nieznanej sesji jest ponawiane raz** | |
| Serwer narzędzi wstał od nowa między wywołaniami | `teams/tests/test_tool_server.py::test_a_call_survives_the_server_restarting_under_it` |
| (treść wymagania) rozróżnienie na odpowiedzi serwera, nie na nazwie narzędzia | `teams/tests/test_tool_server.py::test_a_write_tool_is_retried_on_the_same_terms_as_a_read` |
| Wywołanie przekracza dozwolony czas | `teams/tests/test_tool_server.py::test_a_slow_server_times_out_as_unavailable_not_as_a_refusal` |
| Ślad ponowionego wywołania | `teams/tests/test_tool_server.py::test_a_retried_call_is_one_outcome_with_one_duration` |
| (ta sama ścieżka dla odczytu katalogu) | `teams/tests/test_tool_server.py::test_the_tool_list_survives_the_server_restarting_under_it` |
| Sesji nie da się odtworzyć | **brak testu**, patrz Gaps |
| **terminal-teams — Zakończony przebieg pokazuje treść każdego wywołania** | |
| Wywołanie obserwowane na żywo, czytane po zakończeniu | `terminal/src/teams/TeamsView.test.tsx::reads the body of a call it watched arrive, once the run is over` |
| Wywołanie nagrane i to samo wywołanie ze strumienia | ten sam test (asercja `toHaveLength(1)`) |
| (odczyt, który się nie udał, nie wywraca widoku) | `terminal/src/teams/TeamsView.test.tsx::keeps the calls it has when the read at the end of a run fails` |

## Gaps

- **Scenariusz „Sesji nie da się odtworzyć" nie ma testu, i to jest ta sama sprawa co Finding
  numer jeden.** Test był napisany (`test_a_server_that_stays_down_gives_up_after_one_retry`),
  oblał, i został **usunięty razem z próbą naprawy**, zamiast zostać zaobrączkowany na zielono
  obejściem, którego nie rozumiem do końca. Próba wyglądała tak: przechwycić `CancelledError`
  i odróżnić „ktoś anulował nas" od „obca grupa zadań się zwinęła" po `asyncio.current_task().cancelling()`.
  Nie działa: sesja jest otwierana w tym samym zadaniu, które woła, więc zakres anulujący liczy
  się jako anulowanie **nas** i licznik nie odróżnia niczego. Wersje, które by odróżniły, ruszają
  księgowość anyio (`uncancel()`), a to jest ostatnia rzecz, jaką chce się zgadywać w module
  składającym zlecenia. Kod ponowienia jest w repozytorium bez tej obsługi, defekt jest sprzed tej
  zmiany, a poprawka wymaga zrozumienia własności zakresów anulowania w tym transporcie i należy
  do własnej zmiany.
- **Nie sprawdzono wobec prawdziwego Azure.** Dowodem jest stand-in na tym samym porcie. Pierwszy
  deploy `trading-mcp` po tej zmianie jest tym, co potwierdzi rzecz w warunkach, w których padła.
