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

`terraform plan` wobec **prawdziwego stanu** dobiegł w CI na PR&nbsp;#176 i zamknął
najważniejszą pozycję tego dokumentu: `Plan: 1 to add, 14 to change, 45 to destroy`, ani
jednego `forces replacement`. Cztery bloki `moved` zadziałały jako przeniesienia,
`azurerm_linux_web_app.workbench` jest aktualizowane w miejscu, a wyjścia dowodzą, że to ten
sam zasób — `workbench_managed_identity_principal_id` ma tę samą wartość
(`b4ac41a9-…`), którą miało `agent_managed_identity_principal_id`. Tożsamość przeżyła, więc
rola w Postgresie, client id trzymany przez build terminala i trzy listy w cudzych modułach
nadal wskazują na coś, co istnieje.

Czego **nie** zweryfikowano i czego nie da się tutaj: pierwszy start procesu wobec dwóch
produkcyjnych baz, i to, czy Easy Auth wpuszcza terminal na niezmieniony rekord aplikacji.
Oba są sprawdzalne wyłącznie przy wdrożeniu.

Uboczne znalezisko z tego samego planu, **nie spowodowane tą zmianą**: `azuread_application_password`
modułów `market_data` i `trading_mcp` też planują się jako aktualizacja w miejscu. Żadnego
z nich ta gałąź nie dotyka — to istniejący dryf i warto na niego spojrzeć **przed** apply,
a nie w trakcie.

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

**`moved.tf` — sprawdzone, trzyma** (szczegóły wyżej). Zostaje jako bramka na wypadek
rebase'u: przed apply plan MUST nadal czytać się jako przeniesienie, bez `forces
replacement` na App Service i module Easy Auth. Bez tych bloków Terraform czyta
przemianowanie jako destroy+create, a dla rejestracji Easy Auth znaczy to **nowy client
id** — który trzyma build terminala i trzy listy `allowed_applications`.

**Rola w bazie `teams` przed obrazem, nie po.** Jedno App Service ma jedną tożsamość, więc
`app-tradingcenter-agent` musi istnieć jako rola w bazie `teams` i być właścicielem jej
schematu. Bez tego `lifespan` nie zmigruje drugiego łańcucha i proces nie wstanie —
głośno, co jest lepszym trybem awarii niż połowa serwująca, ale nadal przerwą.

**`apply` i merge nie dają się ustawić bezboleśnie — i to jest korekta do tego, co ten
dokument mówił najpierw.** Napisałem „`apply` przed deployem", co jest prawdą o kierunku
i przemilcza połowę: `app_settings` w `azurerm_linux_web_app` jest **autorytatywne**, więc
apply nie dokłada `AGENT_DATABASE_URL` obok `DATABASE_URL`, tylko **zabiera** stare nazwy.
Stary obraz, który wtedy jeszcze biegnie, czyta `DATABASE_URL` i przy pierwszym restarcie
(a zmiana ustawień restartuje) nie wstaje.

Obie kolejności dają więc okno, tej samej długości i o różnym objawie:

| Kolejność | Co się dzieje w oknie |
|---|---|
| apply → merge | stary obraz traci `DATABASE_URL` i wchodzi w pętlę restartów; okno = build + deploy nowego obrazu (~5 min). Sonda deploy'u na końcu **przechodzi** |
| merge → apply | nowy obraz startuje bez `AGENT_DATABASE_URL` i nie wstaje; sonda deploy'u **czerwona**; okno = czas do ręcznego apply |

Zalecane: **apply → merge**, bo kończy się zielono i okno jest ograniczone czasem
wdrożenia, a nie czasem reakcji operatora. Powierzchnia zespołów jest niedostępna od apply
(App Service `teams` znika w nim) do końca deployu, niezależnie od wyboru.

Zerowego okna da się dokupić za dwa applies: najpierw wersja `app-service.tf` niosąca
**oba** komplety nazw, potem merge i deploy, potem drugi apply kasujący stare. Przy jednym
operatorze i koncie demo to prawdopodobnie nie jest tego warte — ale jest to wybór, a nie
konieczność, więc niech będzie zapisane, że istnieje.

`terraform apply` jest tu **lokalne**, nie z CI: ta zmiana rusza `azuread_*`, a
`terraform-apply.yml` odmawia każdego planu, który je dotyka.

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
