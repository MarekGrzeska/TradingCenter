## Verdict

Wdrożone w całości, w sześciu commitach, po jednym na grupę zadań. Dwa pakiety pod
`packages/` zastąpiły ręczne kopie w sześciu z siedmiu modułów Pythona; `capital-gateway`
nie bierze żadnego i nie został ruszony. Granica runtime jest nietknięta — sprawdzone
gruntem, nie deklaracją: żaden moduł nie importuje innego modułu, a żaden pakiet nie
importuje żadnego modułu.

Dwie rzeczy, których późniejszy czytelnik nie powinien wziąć za przeoczenie. **Nie ma
`uv workspace`** — jest zależność ścieżkowa, i to jest zmiana wobec pierwotnego designu,
opisana w `design.md`, D3. **Zostały 74 linie liczone przez miernik jako kopia** i to jest
stan docelowy, nie dług: to trzy pary szwów, w których mieszka klucz API, ustawienie i typ
odpowiedzi każdego modułu — patrz „Gaps".

Ten artefakt powstał, choć od 18 sierpnia 2026 jest opcjonalny. Powód jest ten sam, który
`proposal.md` przewidział: to zmiana, której jedynym dowodem poprawności są testy siedmiu
modułów, a nie zachowanie, które dałoby się opisać scenariuszem.

**Dopisane, tego samego dnia, po zamknięciu grupy 5.** D1 się odwróciło — powstał trzeci
pakiet, `tc-mcp-kit`. Ten przebieg (sekcje „Verified" i „Findings" poniżej) sprawdzał
granicę runtime i nic więcej nie znalazł; nie sprawdzał, co pakiet ciągnie tranzytywnie do
konsumenta, co jest dokładnie tym, co poprawkę wywołało. Zapisane jako osobna sekcja,
„Poprawka D1", pod koniec tego pliku, żeby nie przepisywać weryfikacji, która była
prawdziwa dla tego, co wtedy sprawdzała.

## Verified

Uruchomione na `change/packages-replace-the-hand-copies`, po ostatnim commicie:

| Gdzie | Komenda | Wynik |
|---|---|---|
| `packages/tc-runtime` | `ruff check .` · `pyright` · `pytest -q` | ok · 0 błędów · **22 passed** |
| `packages/tc-openai` | jw. | ok · 0 błędów · **6 passed** |
| `modules/capital-gateway` | jw. | ok · 0 błędów · **205 passed, 11 skipped** |
| `modules/market-data` | jw. | ok · 0 błędów · **1029 passed, 7 skipped** |
| `modules/market-mcp` | jw. + `scripts/contract.py check` | ok · 0 błędów · **132 passed** · kontrakt aktualny |
| `modules/trading-mcp` | jw. + `scripts/contract.py check` | ok · 0 błędów · **85 passed** · kontrakt aktualny |
| `modules/teams-mcp` | jw. + `scripts/contract.py check` | ok · 0 błędów · **88 passed** · kontrakt aktualny |
| `modules/agent` | jw. | ok · 0 błędów · **354 passed** |
| `modules/teams` | jw. | ok · 0 błędów · **395 passed** |
| `modules/terminal` | `contract:check` · `tsc -b` · `vitest run` | aktualny · ok · **910 passed** |

Testy `-m db` w `agent`, `teams` i `market-data` biegły naprawdę — konteneryzowany
PostgreSQL wstaje z `conftest.py`, nie jest pomijany.

**Obrazy.** Wszystkie siedem zbudowane lokalnie z nowym kontekstem; w każdym uruchomiony
import punktu wejścia (`agent.app`, `teams.app`, `market_data.app`, trzy `*_mcp.server`) —
przechodzi, więc pakiet rozwiązuje się w obrazie, nie tylko w środowisku deweloperskim.
W obrazie agenta sprawdzone dodatkowo, że `MIGRATIONS` wskazuje istniejący katalog:
zależność ścieżkowa zmieniła układ obrazu i to jest rzecz, którą mogła cicho zepsuć.

**Filtr CI.** Sprawdzony wykonaniem, nie przeczytaniem: krok `changes` wyciągnięty z
`checks.yml` i uruchomiony na syntetycznych diffach. Zmiana w `packages/tc-runtime/`
odpala `market-data market-mcp trading-mcp teams-mcp agent teams packages`; zmiana w
`packages/tc-openai/` — `agent teams packages`; zmiana w jednym module odpala tylko jego.
To jest warunek 3 nowej reguły z `docs/architecture.md` i jedyne, co odkupuje gwarancję,
którą stara reguła dawała za darmo.

**Druga tura przeglądu, 18 sierpnia 2026 wieczorem** — po poprawce D1, wykonanej przez
drugą sesję w tym samym katalogu roboczym. Sprawdzone niezależnie, nie przyjęte na słowo:
`network_identity.py` i `detail.py` przeniesione **bajt w bajt** (`diff` przeciwko
`5abd532` pusty); liczby pakietów w lockach potwierdzone co do jednego (47→70→**48**,
54→70→**55**, 61→70→**62**); `alembic`, `sqlalchemy`, `asyncpg` i `fastapi` zniknęły z
wszystkich trzech; `market-mcp` zachowuje `azure-identity` z własnego powodu, który daje
się wskazać palcem (`client.py:55` konstruuje `DefaultAzureCredential`). Filtr CI
sprawdzony wykonaniem: zmiana w `tc-mcp-kit` odpala trzy moduły MCP i nic poza nimi,
`tc-runtime` — market-data, agent, teams. Macierz `packages` wzięła trzeci pakiet sama,
bo czyta się z katalogu. Wszystkie liczby testów identyczne jak wyżej.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| wysoka | `.github/workflows/checks.yml` (krok `changes`) | Wzorzec `archive` odwoływał się do `$tc_runtime` o linię wcześniej, niż zmienna powstawała. Pod `set -euo pipefail` job `changes` przewróciłby się na `unbound variable`, a że od niego zależą wszystkie pozostałe — **żaden** job nie wystartowałby, i to na każdym PR-ze, nie tylko na tym. Nie znalazłby tego żaden test; znalazło uruchomienie kroku na syntetycznym diffie. | **FIXED** w `93fc7c6` |
| wysoka | `packages/tc-runtime/pyproject.toml` | Pakiet deklarował `azure-identity` bez `aiohttp`. `azure.identity.aio` buduje transport leniwie i rzuca `ImportError` z **konstruktora** poświadczenia, więc pułapka sprężynuje dopiero tam, gdzie poświadczenie faktycznie powstaje — czyli w Azure, jako kontener, który nie wstaje. Dokładnie to, co market-mcp odkrył 13 sierpnia 2026. Agent miał `aiohttp` z własnych powodów i dlatego nie zobaczył tego lokalnie. | **FIXED** w `d5973a3` |
| średnia | `packages/tc-openai/tc_openai/provider.py` (`ToolSpec`) | Protokół deklarował `name`/`description`/`input_schema` jako zwykłe atrybuty, czyli zapisywalne. Deskryptory obu modułów są zamrożonymi dataclassami, więc `pyright` odrzucał je jako niezgodne — zmiana zatrzymałaby się na typecheckerze konsumenta, nie pakietu. | **FIXED** w `93fc7c6` |
| średnia | `.github/workflows/checks.yml` (job `packages`) | Macierz joba wymieniała pakiety z ręki (`[tc-runtime, tc-openai]`), a filtr, który ten job włącza, to `^packages/`. Trzeci pakiet dodany później **włączyłby job i nie został przetestowany** — job zzieleniałby, przechodząc testy dwóch cudzych pakietów. Ten sam kształt co znalezisko o sondach deploy z iteracji 0: mechanizm raportujący sukces, nie sprawdziwszy tego, co miał. | **FIXED** — macierz czytana z `ls packages` przez wyjście `package-list` joba `changes` |
| niska | `modules/teams-mcp/pyproject.toml` | Podział pakietów cofnął przypadkową naprawę. `teams-mcp` deklaruje `azure-identity` i **nie** ma `aiohttp` — dokładnie ta para, która 13 sierpnia 2026 wywaliła market-mcp jako niewstający kontener (`ImportError` z konstruktora poświadczenia, wyłącznie w Azure). To stan sprzed tej zmiany: `745783d` miał go tak samo, `tc-runtime` wciągnął `aiohttp` tranzytywnie i zasłonił problem, a `tc-mcp-kit` odsłonił z powrotem. **Dziś nieszkodliwe** — grep po `azure` w źródłach `teams_mcp` nie daje nic, więc żadne poświadczenie nie powstaje. Właściwą naprawą jest usunięcie martwej zależności, co należy do osobnej zmiany o balaście (`proposal.md`, „Poza zakresem"). | otwarte, przeniesione do zmiany o balaście |
| niska | `CLAUDE.md`, tabela komend | Mapa repozytorium wymieniała trzy pakiety, tabela komend tylko `tc-runtime` — `tc-openai` brakowało od iteracji 1, `tc-mcp-kit` doszedł bez wpisu. | **FIXED** przy tym przeglądzie |
| niska | `modules/agent/agent/runtime.py` ↔ `modules/teams/teams/runtime.py` | Dwa nowe pliki, które sam ten refaktor wprowadził, są w 61,9% identyczne. Poniżej progu 70% i każdy niesie inne stałe (8030 / 8050, własna ścieżka migracji), więc reguła ich nie obejmuje — ale to jest kopia, której wcześniej nie było, i uczciwiej ją nazwać, niż zaokrąglić do zera. | świadome |
| — | cała zmiana, pass 1 | Poza powyższymi diff nie dał znaleziska, które przeżyłoby weryfikację. Zmiana jest w większości przeniesieniem kodu bez modyfikacji — trzy rzeczy, które **zmieniły** zachowanie (klucz locka jako argument, `Conversation \| Briefing`, `detail` z nazwą upstreamu), mają własne testy wymienione niżej. | — |
| wysoka | `design.md`, D1 | Odrzucenie trzeciego pakietu (`tc-mcp-kit`) rozumowało o zależnościach `network_identity.py` i `_detail` samych w sobie, nie o drzewie, które dziedziczy konsument biorący `tc-runtime`. Trzy moduły MCP, żaden bez bazy, zaciągnęły `alembic`, `sqlalchemy`, `asyncpg`, `azure-identity`, `aiohttp`, `fastapi` za dwa importy — 70 pakietów w locku każdego, gdzie `trading-mcp` miał 47 przed `tc-runtime`. Nie znalazł tego ten review — sprawdzał granicę runtime, nie tranzytywne drzewo zależności — tylko pytanie o rozmiar diffu po trzech kolejnych scaleniach. | **FIXED**, patrz „Poprawka D1" niżej |

## Spec coverage

Zmiana ma `skip_specs: true` i **nie ma delty specyfikacji** — nie zmienia żadnego
wymagania. Ten przebieg jest więc pusty z założenia, nie z niedopatrzenia: `openspec/specs/`
nie zawiera po niej ani jednej linii, której by nie zawierał przed.

To, co zastępuje przebieg po scenariuszach, to dowód, że **nic się nie zmieniło**: dziewięć
zestawów testów przechodzi bez zmiany treści asercji poza tymi, które musiały nazwać nową
ścieżkę importu albo nowy logger. Kryterium akceptacji z `proposal.md` brzmiało dokładnie
tak i jest spełnione.

Trzy miejsca, w których zachowanie *jednak* się zmieniło, i co je pilnuje:

| Co się zmieniło | Dowód |
|---|---|
| Klucz advisory locka przestał być stałą w pliku i stał się argumentem | `modules/agent/tests/test_migrate.py::test_this_modules_lock_key_is_still_its_own` · `modules/teams/tests/test_migrate.py::test_this_modules_lock_key_is_still_its_own` · `packages/tc-runtime/tests/test_advisory_lock.py::test_the_key_reaches_postgres_unchanged` |
| Agent odziedziczył poprawkę teams na puste `heads` | `packages/tc-runtime/tests/test_schema_version.py::test_an_image_shipping_no_revision_says_so_rather_than_leaving_a_gap` |
| Wejście providera stało się unią zamiast dwóch parametrów | `packages/tc-openai/tests/test_given.py::test_a_briefing_has_nothing_to_append_to` · `::test_a_conversation_carries_its_turns_in_order` · `::test_neither_can_be_mutated_after_it_is_built` |

## Gaps

**Co zostaje ręczne mimo poprawki macierzy.** Sam pakiet jest testowany automatycznie od
chwili, gdy istnieje, ale to, że zmiana w nim odpala joby jego *konsumentów*, wciąż zależy
od dopisania jego wzorca do filtra obok `tc_runtime` i `tc_openai`. Tego nie dało się
wyliczyć tak samo, bo zależność idzie w drugą stronę — z `pyproject.toml` modułu, nie z
zawartości katalogu. Zapisane w `packages/tc-runtime/README.md`, „Adding a third package".

**74 linie, które miernik wciąż liczy jako kopię, zostają.** To `provider.py` (46 + 47),
`auth.py` (28 + 28) i `routers/models.py` (14 + 14) — po docstringu i jednej linii
wiązania. Trzymają dokładnie to, czego pakiet trzymać nie może: klucz API tego modułu, jego
ustawienie, jego typ odpowiedzi. Zejście do zera znaczyłoby skasowanie szwu, czyli pakiet
czytający własny klucz — a osobne klucze agenta i teams są celowe, żeby koszt eksperymentów
miał własną linię w rachunku.

**Czego ta zmiana nie sprawdziła i sprawdzić nie mogła.** Że obraz zbudowany przez
`deploy-*.yml` z nowym kontekstem faktycznie wstanie w App Service. Lokalnie budują się i
importują wszystkie siedem, ale kontekst builda i `.dockerignore` to rzeczy, które
zachowują się inaczej u dostawcy CI niż na maszynie. Pierwsze wdrożenie po scaleniu jest
tym sprawdzeniem — sondy z iteracji 0 asercują tag obrazu, więc zielony deploy nad starym
kontenerem jest wykluczony.

## Poprawka D1 (18 sierpnia 2026)

Skąd wzięło się pytanie: przyrost diffu na trzech kolejnych scaleniach tego dnia był
**+7 451** linii, z czego 68% to same lockfile'e. Rozbicie ich na moduły pokazało, że trzy
moduły MCP urosły w locku o 9–23 pakiety każdy — `trading-mcp` z 47 (sprzed `tc-runtime`)
do 70, `teams-mcp` z 54 do 70, `market-mcp` z 61 do 70 — mimo że żaden z nich nie bierze z
`tc-runtime` niczego poza `network_identity.RequireCallerIdentity` i `detail.detail`. To
jest dokładnie ten rodzaj znaleziska, który ten review pominął, bo sprawdzał, czy moduł
importuje moduł, a nie co pakiet ciągnie tranzytywnie do konsumenta.

**Zmiana.** `network_identity.py` i `detail.py` przeniesione, bez modyfikacji treści, z
`tc-runtime` do nowego `packages/tc-mcp-kit` (zależności: wyłącznie `httpx`, `starlette`).
Trzy moduły MCP przestawione z `tc-runtime` na `tc-mcp-kit` — żaden nie deklaruje już tej
pierwszej zależności. `checks.yml` dostał wzorzec `tc_mcp_kit` obok `tc_runtime`/
`tc_openai`; filtry `mcp`, `trading`, `teamsmcp` przestawione na niego. Szczegóły i pełne
uzasadnienie — `design.md`, D1, „Poprawione 18 sierpnia 2026"; co jest w pakiecie i czego
w nim nie ma — `packages/tc-mcp-kit/README.md`.

**Zweryfikowane, po przestawieniu:**

| Gdzie | Komenda | Wynik |
|---|---|---|
| `packages/tc-runtime` | `ruff check .` · `pyright` · `pytest -q` | ok · 0 błędów · **22 passed** (bez zmiany) |
| `packages/tc-mcp-kit` | jw. | ok · 0 błędów · **11 passed** (nowy pakiet — pierwsze testy tych dwóch plików niezależne od serwera trzech modułów) |
| `modules/market-mcp` | jw. + `scripts/contract.py check` | ok · 0 błędów · **132 passed** (bez zmiany) · kontrakt aktualny |
| `modules/trading-mcp` | jw. + `scripts/contract.py check` | ok · 0 błędów · **85 passed** (bez zmiany) · kontrakt aktualny |
| `modules/teams-mcp` | jw. + `scripts/contract.py check` | ok · 0 błędów · **88 passed** (bez zmiany) · kontrakt aktualny |

Liczby testów identyczne z tabelą „Verified" wyżej — dowód, że przestawienie nie zmieniło
zachowania żadnego z pięciu dotkniętych projektów, tylko to, co każdy z nich instaluje.

**Skutek uboczny, którego ten pomiar nie przewidywał z góry.** `tc-runtime`'s
`pyproject.toml` stracił `httpx` i `starlette` — nie tylko konsumenci `network_identity`/
`detail` mają je zapisane we własnym locku jako metadane pakietu, ale **każdy** konsument
`tc-runtime`, bo `uv.lock` osadza pełne `dependencies`/`requires-dist` pakietu, którego
dotyczy. `agent`, `teams` i `market-data` straciły więc te dwie pozycje z własnych
`uv.lock` mimo że żaden nie zmienił ani linii kodu. Liczba pakietów każdego z nich
nieznaczona — `httpx` i `starlette` były już w ich drzewie z innych powodów (FastAPI,
klient HTTP) — więc `uv lock` w każdym z trzech tylko usunął zdublowany wpis. `ruff check`,
`pyright` i pełne `pytest -q` (bez `-m db`) zielone we wszystkich trzech: agent **354
passed**, teams **395 passed**, market-data **1029 passed, 7 skipped** — te same liczby, co
w tabeli „Verified" na górze tego pliku.

**Pakiety w locku, przed i po:**

| Moduł | Przed `tc-runtime` | Z `tc-runtime` | Z `tc-mcp-kit` |
|---|---|---|---|
| `trading-mcp` | 47 | 70 | **48** |
| `teams-mcp` | 54 | 70 | **55** |
| `market-mcp` | 61 | 70 | **62** |

`market-mcp` zostaje nieco powyżej punktu wyjścia (62 vs 61) i zachowuje
`azure-identity`/`aiohttp` — z własnego powodu, jego uwierzytelnianie do market-data, nie z
`tc-runtime`; zapisane w jego własnym `pyproject.toml` od 13 sierpnia 2026, sprzed tej
poprawki.

**Obrazy.** Trzy dotknięte (`market-mcp`, `trading-mcp`, `teams-mcp`) zbudowane lokalnie z
tym samym kontekstem co reszta zmiany; w każdym uruchomiony import punktu wejścia
(`*_mcp.server`) — przechodzi. `agent`, `teams`, `market-data` nietknięte przez tę poprawkę
i nie przebudowane.

**Co ta poprawka nie zmienia.** D1 w części, która odrzuciła scalanie `server.py`,
`client.py`, `config.py`, `errors.py` w jeden pakiet — te są nadal zmierzone jako różne
pliki (8–58% wspólnych linii), nie kopie, i zostają u siebie. Cofnięty jest wyłącznie
wniosek o koszcie trzeciego pakietu, nie sam pomiar identyczności, na którym cała reguła
sharing stoi.
