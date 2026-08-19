## Co zostało zweryfikowane

Wszystko poniżej biegło lokalnie na `refactor/agent-and-teams-one-workbench`.

| Co | Wynik |
|---|---|
| `modules/workbench`: `uv run pytest` | **838 passed** (w tym `-m db` wobec dwóch kontenerów PostgreSQL) |
| `modules/workbench`: `ruff check .`, `pyright` | czysto, 0 błędów |
| `packages/tc-runtime`: `pytest`, `ruff`, `pyright` | 22 passed, czysto |
| `scripts`: `pytest`, `ruff`, `pyright` | 151 passed, czysto |
| `modules/terminal`: `test`, `typecheck`, `lint`, `contract:check` | 915 passed, czysto, kontrakty aktualne |
| `infra`: `terraform fmt -check -recursive`, `validate` | czysto, oba korzenie |
| `openspec validate --strict` | valid |

Czego **nie** zweryfikowano i czego nie da się tutaj: `terraform plan` wobec prawdziwego
stanu, `moved.tf` (patrz niżej — to jest najważniejsza pozycja tego dokumentu), pierwszy
start procesu wobec dwóch produkcyjnych baz, i to, czy Easy Auth wpuszcza terminal na
niezmieniony rekord aplikacji. Wszystkie cztery są sprawdzalne wyłącznie przy wdrożeniu.

## Wymaganie → test

Delta tej zmiany ma dwie nowe zdolności; poniżej scenariusz → plik::test.

**`workbench-process`**

| Scenariusz | Test |
|---|---|
| Obie bazy odpowiadają / dwa procesy startują naraz | `tests/agent/test_migrate.py::test_only_one_of_two_processes_migrates`, `tests/teams/test_migrate.py` (ten sam kształt, drugi łańcuch) |
| Jedna z baz nie odpowiada | **luka** — nie ma testu, który wywraca jedną pulę i sprawdza, że proces nie wstaje. Sprawdzone ręcznie brakiem zmiennej (`ValidationError` przy starcie), co nie jest tym samym zdarzeniem |
| Koszt tury czatu / koszt przebiegu zespołu | `tests/agent/test_usage_store.py`, `tests/teams/test_cost_ledger.py` — obie sumują w swojej bazie, bo `pool` każdego drzewa jest inny |
| Konfiguracja nazywa poświadczenie tylko jednej powierzchni | `tests/conftest.py::workbench_env` odwrotnie: brak któregokolwiek klucza to `ValidationError` z nazwą pola, widoczny w każdym teście, który go pominie |
| Ścieżka kolidująca / literał wobec wzorca | `tests/test_route_collisions.py::test_each_surface_answers_its_own_catalogue`, `::test_the_literal_beats_the_team_id_it_looks_like` |
| Trasa niekolidująca | `tests/test_route_collisions.py::test_nothing_else_moved` |
| Jedno wejście bez poświadczenia | `tests/agent/test_app.py::test_health`, `tests/teams/test_app.py::test_health_requires_no_identity` |
| Powierzchnie nie sięgają do siebie / narzędzia przez kontrakt | `tests/test_layering.py` (4 reguły, czytane z AST) |

**`workbench-team-tools`** — cała zawartość przeniesiona wraz z testami: `tests/teams_tools/`
(67 testów) przeszło bez zmiany treści poza tym, co zmienił transport. Autorstwo:
`test_local_operator.py`, `test_operator.py`.

## Co znalazło się po drodze i jest warte zapisania

**1. `respx` nie widzi wywołania przez `ASGITransport`.** Domyślny mocker łata `httpcore`,
którego transport ASGI nie dotyka — 67 testów narzędzi przechodziłoby *obok* atrap, wprost
do obiektu aplikacji. Nie failowałyby: trafiałyby w prawdziwe routery bez bazy i dostawały
500, a asercje na treść odmowy przypadkiem by przeszły. Zamknięte jedną linią w
`tests/teams_tools/conftest.py` (`respx.mocks.DEFAULT_MOCKER = "httpx"`, mocker o warstwę
wyżej) i klasą `_NeverReached`, która krzyczy, gdy wywołanie jednak dojdzie do aplikacji.
To jest ten sam wzorzec, który to repozytorium już raz nazwało przy hooku z PowerShella:
zabezpieczenie, które nie umie się uruchomić, wygląda dokładnie jak zabezpieczenie, które
działa.

**2. Kolejność tras jest realna, nie teoretyczna.** Zmierzone na FastAPI 0.141.1 osobnym
eksperymentem: `/teams/{team_id}` zarejestrowane pierwsze odpowiada na `GET /teams/models`
błędem `422 int_parsing`. Test asercjonuje zachowanie (status i brak `int_parsing`), nie
kolejność w liście — lista przestała być czytelna, bo ta wersja FastAPI trzyma dołączone
routery leniwie (`_IncludedRouter`), więc `app.routes` nie jest płaskie.

**3. `tc_runtime.routers.models_router` czytał `app.state.catalogue`.** Pakiet nie mógł już
tego wiedzieć: dwie powierzchnie trzymają swój stan pod osobnymi nazwami na jednej
aplikacji. Doszedł drugi argument — funkcja zwracająca katalog dla żądania. Dokładnie ten
kształt, którego reguła pakietów wymaga: różnica wyrażona argumentem.

**4. Token operatora nie miał czym być w jednym procesie.** To jest korekta propozycji,
którą trzeba przeczytać: plan mówił „token operatora jedzie do narzędzi tak jak jechał".
Nie jedzie i nie może — token wymaga walidatora, a między czatem a trasami zespołów nie ma
już żadnego. Jedzie **principal**, zdjęty z obsługiwanego żądania, który przez walidator
już przeszedł. Wynik po drugiej stronie ten sam, poświadczeń w locie o jedno mniej,
i `agent/tools/client.py` traci cały tryb sesji-na-wywołanie, który istniał wyłącznie po
to, żeby nie dzielić sesji między operatorów.

**5. Migawka kontraktu zniknęła, ale dokument nie jest tym samym dokumentem.**
`contract.teams.generated.ts` schudł o 136 linii: wypadły z niego `/health` i wszystko, co
należy do procesu, a nie do powierzchni zespołów. To jest poprawne i warte odnotowania,
bo terminal generuje typy z tego pliku — plik opisuje teraz jedną powierzchnię, nie jeden
proces.

## Ryzyka przy wdrożeniu, w kolejności ważności

**`moved.tf` musi zadziałać, zanim cokolwiek innego.** Cztery bloki przenoszą adresy w
stanie: App Service, moduł Easy Auth, `pre_authorized` i reguła firewalla. Bez nich
Terraform czyta przemianowanie jako destroy+create, a dla rejestracji Easy Auth znaczy to
**nowy client id** — który trzyma build terminala i trzy listy `allowed_applications`.
Bramka jest ta sama, którą ten plik już raz opisał: `terraform plan` MUST pokazać dla tych
czterech `0 to add, 0 to change, 0 to destroy`. Cokolwiek innego to przeprowadzka, która
się nie odbyła, i wtedy **nie aplikować**.

**Rola w bazie `teams` przed obrazem, nie po.** Jedno App Service ma jedną tożsamość, więc
`app-tradingcenter-agent` musi istnieć jako rola w bazie `teams` i być właścicielem jej
schematu. Bez tego `lifespan` nie zmigruje drugiego łańcucha i proces nie wstanie —
głośno, co jest lepszym trybem awarii niż połowa serwująca, ale nadal przerwą.

**`apply` przed deployem.** Nowe ustawienia (`AGENT_*`, `TEAMS_*`) muszą dotknąć App
Service, zanim dotknie go obraz, który ich wymaga. Odwrotna kolejność to nie kwestia
estetyki: obraz bez `AGENT_DATABASE_URL` nie wstaje wcale.

**Cofnięcie.** Poprzedni obraz `agent` plus przywrócone z Terraforma App Service `teams`
i `teams-mcp`. Dane obu baz są nietknięte przez całą operację — żadna migracja nie jest
częścią tej zmiany.

## Czego ta zmiana świadomie nie zrobiła

Nie ruszyła pętli tury (`agent/turn.py`, `teams/runner/loop.py` — nietknięte), nie scaliła
baz, nie scaliła katalogów modeli ani kluczy OpenAI, i **nie przemianowała App Service** —
D2 wylicza, co to kosztuje i co kupuje. Nie zeszła też z B3, choć ubyły dwa tenanty:
ten SKU szedł w górę dwa razy na pomiarze, a nie na odejmowaniu, i powinien schodzić tak
samo.

Zostaje jedna rzecz, którą rachunek nazwał ceną i którą trzeba powtórzyć, bo brzmi jak
zysk, a nim nie jest: **tokeny na turę nie spadają.** Narzędzia zespołowe nadal jadą do
modelu w tej samej liczbie i za tę samą powierzchnię. Spada latencja, infrastruktura
i liczba miejsc do poprawienia.
