## Verdict

Weszło wszystko z iteracji 4 poza jedną rzeczą: **cel „< 10 tys. tokenów na turę" nie
został osiągnięty**. Powierzchnia trzech serwerów MCP spadła z 15 134 do **11 704**
tokenów (−22,7%), i to jest cała oszczędność, jaką dało się wziąć bez oddania czegoś, co
działa — dalsza droga prowadzi przez usunięcie `outputSchema`, czyli jedynej rzeczy, która
w tym repozytorium wykryła realną awarię odpowiedzi narzędzia. Rozbicie
`compute_indicators` nie weszło, bo policzone **dokłada** znaki zamiast je ujmować (D3);
to nie jest pominięcie, tylko wynik pomiaru sprzeczny z planem.

Reszta jest zamknięta: ramki `quote` nie są już parsowane, `/pairs` i
`GET /markets/{epic}` pytane raz na wywołanie, zapisy bramy nie wychodzą już jako
nieobsłużony 500, a demo-guard `trading-mcp` sprowadzony do jednego sprawdzenia, które
może wypaść inaczej — bo brama wreszcie wylicza `environment`, zamiast go deklarować.

## Verified

Uruchomione w pakiecie i w pięciu modułach (`uv run pytest` · `ruff check .` · `pyright`),
wszystko na `perf/hot-paths`:

| Gdzie | pytest | ruff | pyright |
|---|---|---|---|
| `packages/tc-mcp-kit` | 26 passed | clean | 0 errors |
| `modules/capital-gateway` | 214 passed, 11 skipped | clean | 0 errors |
| `modules/market-data` | 1030 passed, 7 skipped | clean | 0 errors |
| `modules/market-mcp` | 140 passed | clean | 0 errors |
| `modules/teams-mcp` | 93 passed | clean | 0 errors |
| `modules/trading-mcp` | 91 passed | clean | 0 errors |

`uv run python scripts/contract.py check` w trzech modułach MCP: „Contract is up to date."
Testy `live` i `db` nie były uruchamiane (odpowiednio: wymagają sesji capital.com i nie
dotyczy — żaden dotknięty moduł nie ma bazy).

Pomiar powierzchni: serwery zbudowane w procesie, `list_tools()` zserializowany do JSON-a
bez spacji, policzony `cl100k_base`.

| Moduł | znaki przed | znaki po | tokeny przed | tokeny po |
|---|---:|---:|---:|---:|
| market-mcp | 25 474 | 18 842 | 6 013 | 4 407 |
| teams-mcp | 24 512 | 20 164 | 5 670 | 4 659 |
| trading-mcp | 14 430 | 11 092 | 3 451 | 2 638 |
| **razem** | **64 416** | **50 098** | **15 134** | **11 704** |

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| wysoka | `tc_mcp_kit/tool_schemas.py:63` (`_walk`) | Odchudzacz kasował **każdy** klucz `title`/`default`, także tam, gdzie to jest nazwa pola, a nie słowo kluczowe. `IndicatorParamOut` publikuje parametr o nazwie `default`, więc `list_indicators` i `describe_indicator` ogłaszały cztery pola przy pięciu w odpowiedzi — i brakowało dokładnie tego, dla którego katalog istnieje („wystarcza do zbudowania żądania"). Nic nie padało: `required` nadal nazywał pole, a JSON Schema nie protestuje przeciw właściwości, o której nie wie. | FIXED `9d858de` |
| średnia | `modules/*/tests/test_tool_surface.py` | Pierwsza wersja testu „schemat bez rusztowania" szukała słowa `default` w **tekście** schematu i zaczerwieniła się na `list_indicators` z tego samego powodu. Poprawione na chodzenie po kluczach, zanim weszło. | FIXED `97ff474` |
| niska | `capital_gateway/adapter.py:_market_open_memo` | Słownik rośnie o wpis na każdy instrument, o który ktoś zapytał w rozdzielczości DAY/WEEK, i nigdy nie jest czyszczony. Wpis to krotka `(float, bool)`; przy liczbie instrumentów, jaką ta brama obsługuje, jest to kilkadziesiąt bajtów — świadomie zostawione, nie przeoczone. | OPEN, świadome |
| niska | `market_mcp/client.py:pairs` | Memo trzyma obiekt `httpx.Response`, nie sparsowane wiersze, więc każdy czytelnik parsuje JSON od nowa. Tańsze niż request, o który tu chodzi, i zostawia `raise_for_status` w rękach wywołującego. | OPEN, świadome |

Poza tym z przeglądu diffu: nic. W szczególności sprawdzone i **nie** będące błędem —
`GatewayError` z `_write_json` wychodzi jako 502 przez `_gateway_error_handler`, a
`trading-mcp` czyta 502 jako awarię dostępu, czyli „efekt na rachunku nieznany", co jest
poprawnym zdaniem o zapisie, którego odpowiedzi nie dało się przeczytać.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **market-mcp-tools** · Opis narzędzia jest częścią kontraktu | |
| Narzędzie bez kompletnego opisu | `market-mcp/tests/test_tool_surface.py::test_every_tool_has_a_description`, `::test_every_ceiling_is_named_in_the_description`, `::test_every_parameter_is_typed`, `::test_price_tools_name_which_side_of_the_spread` |
| Czas jest jednoznaczny | `market-mcp/tests/test_tool_surface.py::test_time_tools_name_the_timezone` |
| **market-mcp-tools** · Powierzchnia narzędzi ma zapisany sufit | |
| Zestaw urósł ponad sufit | `market-mcp/tests/test_tool_surface.py::test_the_surface_stays_under_its_ceiling` |
| Schemat bez rusztowania | `market-mcp/tests/test_tool_surface.py::test_the_schema_carries_no_scaffolding`, `::test_the_schema_still_says_what_a_reply_holds`, `::test_the_catalogue_still_publishes_a_parameter_default`; w pakiecie `tc-mcp-kit/tests/test_tool_schemas.py::test_a_reply_valid_before_is_valid_after`, `::test_a_field_named_like_a_keyword_survives` |
| **teams-mcp-tools** · Powierzchnia narzędzi ma zapisany sufit | |
| Zestaw urósł ponad sufit | `teams-mcp/tests/test_tool_surface.py::test_the_surface_stays_under_its_ceiling` |
| Schemat bez rusztowania | `teams-mcp/tests/test_tool_surface.py::test_the_schema_carries_no_scaffolding`, `::test_the_schema_still_says_what_a_reply_holds` |
| **trading-mcp-tools** · Opis narzędzia jest częścią kontraktu | |
| Narzędzie bez nazwanych jednostek | `trading-mcp/tests/test_tool_surface.py::test_a_tool_taking_a_size_says_what_a_size_is`, `::test_every_write_tool_has_a_description` |
| **trading-mcp-tools** · Powierzchnia narzędzi ma zapisany sufit | |
| Zestaw urósł ponad sufit | `trading-mcp/tests/test_tool_surface.py::test_the_surface_stays_under_its_ceiling` |
| Schemat bez rusztowania | `trading-mcp/tests/test_tool_surface.py::test_the_schema_carries_no_scaffolding`, `::test_the_schema_still_says_what_a_reply_holds` |
| **trading-mcp-upstream-access** · Moduł pracuje wyłącznie na rachunku demonstracyjnym | |
| Gateway nie zgłasza środowiska demonstracyjnego | `trading-mcp/tests/test_demo_guard.py::test_non_demo_environment_is_refused`, `::test_a_missing_environment_field_is_refused_too`, oraz `tests/test_transport.py::test_the_process_does_not_listen_when_the_account_is_not_demo` (część „nie zaczyna nasłuchiwać") |
| Gateway nie odpowiada przy starcie | `trading-mcp/tests/test_demo_guard.py::test_an_unreachable_gateway_stops_the_start`, `::test_a_gateway_refusal_stops_the_start`, `tests/test_transport.py::test_the_process_does_not_listen_when_the_gateway_is_unreachable` |
| **capital-session** · Wyłącznie środowisko demo | |
| Skonfigurowany host produkcyjny | `capital-gateway/tests/test_config.py::test_a_non_demo_base_url_refuses_to_start` (istniejący) |
| Publikowane możliwości nazywają środowisko | `capital-gateway/tests/test_app.py::test_capabilities_name_the_environment` |
| … i nazwa jest wyprowadzona z hosta | `capital-gateway/tests/test_config.py::test_the_demo_host_is_the_demo_environment`, `::test_any_other_host_is_not` |

Bez luk: każdy scenariusz z delt ma test. Dwa testy w `test_transport.py` powstały
**w trakcie tego przeglądu** — pass 2 pokazał, że zdanie „nie zaczyna nasłuchiwać" nie
miało niczego, co by je sprawdzało, a po usunięciu re-checku per zapis jest to jedyna
obrona, jaka temu modułowi została (zasada nr 5: obrona bez testu swojego trybu awarii).

Zmiany bez wymagania w spec, sprawdzone testami u siebie: ramki `quote`
(`market-data/tests/test_gateway_stream.py::test_a_quote_frame_is_not_read_at_all`,
`::test_the_quote_reader_still_reads_a_quote`), memo `/pairs`
(`market-mcp/tests/test_pairs_memo.py`, 4 testy), memo `_market_open` i `_write_json`
(`capital-gateway/tests/test_adapter.py`, 6 testów).

## Czego nie da się kupić za mniej niż to, co kosztuje

Zapis dla czytelnika za rok, żeby nie próbował tego jeszcze raz z tym samym wynikiem.
Zmierzone warianty, cała powierzchnia trzech modułów:

- dziś, po tej zmianie: **11 704** tokenów;
- bez `outputSchema` w ogóle: **6 512**. Różnica 5,2 tys. tokenów kosztuje walidację
  odpowiedzi w serwerze lowlevel — jedyne, co złapało `WindowedOut` ogłaszający `from_`
  przy odpowiedzi niosącej `from`, i czego `FastMCP.call_tool` (ścieżka wszystkich testów)
  nie sprawdza;
- rozbicie `compute_indicators` na tryb `latest` i osobne `indicator_series`:
  **+1 100 znaków**, bo oba narzędzia niosą własną kopię wspólnej części schematu, a
  `markers`/`zones`/`levels` zostają w obu;
- opisy: 13 265 → 12 967 znaków. Skrócone tam, gdzie zdanie powtarzało poprzednie (pięć w
  market-mcp), i **wydłużone** w trading-mcp, gdzie żadne narzędzie zapisujące nie mówiło,
  w czym wyrażony jest `size`. Reszta niesie granice odmowy, których wymagają od nich ich
  własne specyfikacje — teams-mcp jest tu w całości.

Zejście poniżej 10 tys. wymaga decyzji o zakresie (mniej narzędzi), nie o formacie.
