## Verdict

Poszło wszystko, co proponowano: `capital-gateway` publikuje warunki instrumentu z
`GET /markets/{epic}`, którego i tak już wołał, `trading-mcp` dostał dwa narzędzia
czytające — warunki i przeliczenie depozytu na rozmiar — a okno outputów przebiegu rozwija
wywołanie do argumentów i odpowiedzi. Kontrakt `teams` nie został ruszony i nie musiał być:
`ToolCallOut` woził oba pola od początku, gubił je mapper terminala.

Świadomie niedokończone i **nie do wzięcia za przeoczenie**: `lot_size` jest publikowany,
ale nie wchodzi do arytmetyki — `notional` to `size × price`. Jedyny pomiar, jaki mamy
(US100, P/L −0,1134 USD na rozmiarze 0,063 przy 1,8 punktu spreadu), zgadza się z mnożnikiem
1 i nie odróżnia instrumentu o `lotSize ≠ 1`. Mnożenie bez dowodu byłoby tym samym zgadywaniem,
przed którym broni reszta tego modułu, więc liczba jest publikowana i nieużywana, dopóki nie
zostanie zmierzona. Drugi świadomy brak: żaden sufit liczony w depozycie nie powstał —
`max_order_size` w `teams` dalej jest liczbą w jednostkach instrumentu.

## Verified

W kolejności, w jakiej były uruchamiane:

| Gdzie | Komenda | Wynik |
|---|---|---|
| capital-gateway | `uv run ruff check .` · `uv run pyright` · `uv run pytest -q` | `All checks passed` · `0 errors` · **199 passed, 11 skipped** |
| trading-mcp | `uv run python scripts/contract.py check` | `Contract is up to date.` (po `generate`) |
| trading-mcp | `uv run ruff check .` · `uv run pyright` · `uv run pytest -q` | `All checks passed` · `0 errors` · **83 passed** |
| terminal | `pnpm typecheck` · `pnpm lint` · `pnpm contract:check` | bez wyjścia · bez wyjścia · `Every contract is up to date.` |
| terminal | `pnpm test` | **886 passed (57 plików)** |

Nie uruchamiano: `uv run pytest -m db` (żaden moduł z bazą nie był ruszany),
`-m live --run-live` ani `--run-live-trading`. Trasa `/instruments/{symbol}/terms` nie została
sprawdzona wobec prawdziwego capital.com — patrz Gaps.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| poważne | `trading_mcp/tools/instruments.py:112` | Depozyt mniejszy niż jeden krok rozmiaru zaokrąglał się w dół do `0`, a przy instrumencie bez `min_deal_size` nic tego nie łapało — `size_for_margin` oddawałby `0`, a `place_order` poniósłby je do gatewaya. | **FIXED** w `b6e38f5` (jawna odmowa „rounds down to nothing" + `test_a_deposit_under_one_step_is_refused_rather_than_sized_at_zero`) |
| drobne | `teams/runs.ts:65` | Nowy interfejs `ToolCallDetail` wszedł **pomiędzy** komentarz dokumentujący `TeamRunToolCall` a sam interfejs — komentarz opisywał odtąd nie ten typ. | **FIXED** w commicie z tym review |
| do wiedzy | `teams/useRunMonitor.ts:127` | Wywołanie, które przyjdzie strumieniem *w trakcie* czytania nagranych wierszy, może trafić na listę dwa razy — raz bez treści, raz z nią — a klucz Reacta `round-position-toolName` nie jest wtedy unikalny. Zachowanie **sprzed tej zmiany**; ta zmiana czyni je widocznym (dwa wpisy różnią się teraz zawartością po rozwinięciu), nie tworzy. | otwarte, poza zakresem |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **capital-market-data — Warunki handlowe instrumentu są osobnym odczytem** | |
| Odczyt warunków instrumentu | `capital-gateway/tests/test_mapping.py::test_market_details_carry_the_deposit_and_the_size_rules`, `capital-gateway/tests/test_app.py::test_instrument_terms_come_from_the_market_detail` |
| Warunki instrumentu spoza providera | `capital-gateway/tests/test_app.py::test_terms_for_an_instrument_the_provider_does_not_know_name_the_symbol` |
| Provider nie podaje któregoś z warunków | `capital-gateway/tests/test_mapping.py::test_a_rule_the_provider_omits_stays_missing_rather_than_becoming_zero`, `::test_market_details_without_dealing_rules_at_all` |
| (treść wymagania) odczyt nie niesie ceny | `capital-gateway/tests/test_mapping.py::test_market_details_carry_no_price` |
| (treść wymagania) odczyt jest osobny od wyszukiwania | `capital-gateway/tests/test_app.py::test_every_route_appears_in_the_published_schema` |
| **trading-mcp-tools — Zestaw podaje warunki instrumentu, na których liczy się rozmiar** | |
| Model czyta warunki instrumentu | `trading-mcp/tests/test_instrument_tools.py::test_get_instrument_terms_carries_the_deposit_and_the_size_rules`, `::test_get_instrument_terms_answers_no_price` |
| Warunki instrumentu spoza providera | `trading-mcp/tests/test_instrument_tools.py::test_get_instrument_terms_for_an_unknown_symbol_is_a_refusal` |
| (treść wymagania) narzędzie oznaczone jako czytające | `trading-mcp/tests/test_tool_surface.py::test_read_tools_are_annotated_read_only` |
| **trading-mcp-tools — Rozmiar wynikający z zadanej marży liczy moduł, nie model** | |
| Depozyt przeliczony na rozmiar | `trading-mcp/tests/test_instrument_tools.py::test_the_run_that_prompted_this_sized_against_the_contract_not_the_deposit` |
| (treść wymagania) zaokrąglenie w dół | `trading-mcp/tests/test_instrument_tools.py::test_the_size_is_rounded_down_to_the_step_not_to_the_nearest` |
| (treść wymagania) cena jest argumentem | `trading-mcp/tests/test_instrument_tools.py::test_a_non_positive_margin_or_price_is_refused_before_the_gateway` (dowodzi, że cena wchodzi wywołaniem; brak trasy cenowej dowodzi reszty) |
| Zadana kwota nie starcza na najmniejsze zlecenie | `trading-mcp/tests/test_instrument_tools.py::test_a_deposit_too_small_for_the_smallest_order_is_refused_with_both_numbers`, `::test_a_deposit_under_one_step_is_refused_rather_than_sized_at_zero` |
| Zadana kwota przekracza największe dopuszczalne zlecenie | `trading-mcp/tests/test_instrument_tools.py::test_a_deposit_over_the_largest_order_is_refused` |
| Jednostka wymogu depozytu jest nieznana modułowi | `trading-mcp/tests/test_instrument_tools.py::test_a_margin_unit_this_module_cannot_compute_with_is_refused_by_name`, `::test_an_instrument_without_a_published_margin_requirement_is_refused` |
| (treść wymagania) narzędzie MUST NOT składać zlecenia | `trading-mcp/tests/test_tool_surface.py::test_read_tools_are_annotated_read_only` — **tylko adnotacja**, patrz Gaps |
| (treść wymagania) MUST NOT podpowiadać kierunku | **brak testu**, patrz Gaps |
| **terminal-teams — Wywołanie narzędzia w oknie outputów da się rozwinąć** | |
| Operator rozwija wywołanie | `terminal/src/teams/TeamsView.test.tsx::keeps a call collapsed until the operator opens it, then shows both halves` |
| Wpisy są zwinięte na wejściu | ten sam test (asercja przed kliknięciem) |
| Treść wywołania jeszcze nie dotarła | `terminal/src/teams/TeamsView.test.tsx::says a call watched live has not been read rather than showing it empty` |
| Wywołanie zakończone odmową | `terminal/src/teams/TeamsView.test.tsx::labels a refused call's body as the reason it gave` |
| (mapper przestaje gubić pola) | `terminal/src/teams/runs.test.ts::names the agent whose step made the call, and keeps what it was given and answered` |

## Gaps

- **„`size_for_margin` MUST NOT składać zlecenia" jest dowodzone adnotacją, nie zachowaniem.**
  `test_read_tools_are_annotated_read_only` sprawdza, że narzędzie ogłasza się jako czytające;
  żaden test nie stwierdza, że jego wywołanie nie wysyła `POST`. Test wprost — `respx` bez
  zamockowanej trasy zapisu — kosztowałby trzy linijki i go nie ma.
- **„MUST NOT podpowiadać kierunku" nie ma testu i mieć nie będzie.** To wymaganie o kształcie
  odpowiedzi, a `SizeForMarginOut` nie ma pola, w którym kierunek dałoby się wyrazić. Pilnuje
  tego typ, nie asercja.
- **Nic nie zostało sprawdzone wobec prawdziwego capital.com.** Wszystkie liczby US100 w testach
  — marża 5%, krok 0,001 — pochodzą z odczytania logu przebiegu, nie z odpowiedzi providera:
  jedyna nagrana fixture z detalem rynku to GOLD (marża 100%, krok 0,01). Pierwsze prawdziwe
  wywołanie `/instruments/US100/terms` jest tym, co te liczby potwierdzi albo obali.
- **`lot_size` publikowany i nieużywany** — powód w Verdict.
