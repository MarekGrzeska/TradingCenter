## 1. Dom testowy dla `scripts/`

- [x] 1.1 `scripts/pyproject.toml` — projekt `tc-scripts`, Python 3.12, `httpx`, dev-grupa z `pytest`, `ruff`, `pyright`; `scripts/README.md` w jednym akapicie
- [x] 1.2 `scripts/tests/` z jednym testem-szkieletem; `uv run pytest`, `uv run ruff check .`, `uv run pyright` przechodzą lokalnie
- [x] 1.3 Job `scripts` w `checks.yml` na ścieżce `scripts/**` — te same trzy komendy; dopisać `scripts` do wykazu nazw w jobie `changes`
- [x] 1.4 `scripts/.venv` i `scripts/*.egg-info` w `.gitignore` oraz `.dockerignore` — już pokryte regułami globalnymi (`.venv/`, `*.egg-info/`, `**/.venv`) i wykluczeniem całego `scripts` z kontekstu builda; bez zmian

## 2. Sonda wdrożenia

- [x] 2.1 `scripts/deploy_probe.py` — pętla przyjmująca `current_image()` i `probe()` jako argumenty; parametry `app_name`, `expected_image`, `probe_path`, `expected_status`, `body_contains`, `attempts`, `sleep_seconds`
- [x] 2.2 `main()` podstawia `az webapp config container show` i `httpx`; kod wyjścia 1 i komunikat `::error::` nazywający, który warunek nie został spełniony
- [x] 2.3 Test trybu awarii z 16 sierpnia: `current_image()` zwraca stary SHA, `probe()` zwraca 200 z poprawnym ciałem → sonda MUSI nie przejść
- [x] 2.4 Test drugiego trybu: poprawny SHA, 200 z ciałem bez `body_contains` (odpowiedź nie z kontenera) → sonda MUSI nie przejść
- [x] 2.5 Test wariantu control-plane (`probe_path` puste): sam zgodny SHA wystarcza, `probe()` nie jest wołane ani razu
- [x] 2.6 Test szczęśliwej ścieżki i test wyczerpania prób: dokładnie `attempts` wywołań, potem kod 1

## 3. Reusable workflow i pierwszy wywołujący

- [x] 3.1 Odczytane: `AZURE_*` to zmienne **repozytorium**, środowisko `production` nie ma własnych. `environment: production` zostaje i tak — federated credential ma w subject `:environment:production`, więc bez tego nie ma uwierzytelnienia do Azure
- [x] 3.2 `.github/workflows/_deploy-app-service.yml` — `workflow_call`. Wejść wyszło osiem, nie dziesięć: `image_name` i cache scope są zawsze równe `module` (zmierzone na wszystkich siedmiu), a `dockerfile` wyprowadza się z `module`, bo `file:` jest relatywne do workspace'u, nie do kontekstu. Doszło `failure_hint`, żeby rada per moduł z logów `trading-mcp` i `teams-mcp` nie zginęła
- [x] 3.3 Krok sondy woła `scripts/deploy_probe.py` przez `uv run`
- [x] 3.4 `deploy-market-mcp.yml` → wywołujący: wyzwalacz, filtr ścieżki (plus `_deploy-app-service.yml` i `scripts/deploy_probe.py`), `concurrency`, `with:`. Komentarze-incydenty zostają w pliku
- [ ] 3.5 (operator — wymaga merge’a) Zmerge'ować i obejrzeć wdrożenie `market-mcp` w Actions — zielone, z logiem sondy pokazującym zgodny SHA i 200 z `"status"`

## 4. Pozostałych sześciu wywołujących

- [x] 4.1 `deploy-agent.yml` i `deploy-teams.yml` — `probe_path: /health`, `expected_status: 200`, `body_contains: '"status"'` (zaostrzenie), `attempts: 20`
- [x] 4.2 `deploy-trading-mcp.yml` i `deploy-teams-mcp.yml` — jak market-mcp, `attempts: 12`
- [x] 4.3 `deploy-market-data.yml` — `probe_path: /ws/candles`, `expected_status: 404`, `body_contains: '"detail"'`, `attempts: 12`
- [x] 4.4 `deploy-gateway.yml` — `probe_path` puste, `build_context: modules/capital-gateway` bez `dockerfile`, `attempts: 10`
- [x] 4.5 Zmierzone: **458 → 256** linii kodu workflow (145 w siedmiu wywołujących, 19–23 każdy, plus 111 we wspólnym). Cel planu ~175 **nie osiągnięty** i nie będzie: sam blok `inputs` z opisami to ~50 z tych 111, a opisy są tu dokumentacją, nie balastem. Do tego pętla sondy przestała być 7 × ~18 linii wklejonego shella bez testu i jest jednym modułem 233 linii z 21 testami — w sumie linii jest więcej, i to jest uczciwa liczba
- [ ] 4.6 (operator — wymaga merge'a) Sprawdzić po merge'u, że wszystkie siedem wdrożeń przeszło i żadne nie zgłosiło pustego `client-id`

## 5. Runner dev

- [x] 5.1 `scripts/dev.py` — tabela serwisów jako lista zamrożonych dataclass (`name`, `directory`, `port`, `command`, `health_path`, `log_prefix`, `color`, `why`); proza kolejności startu przeniesiona do pola `why`
- [x] 5.2 Kontrole przed startem: Docker obecny, porty wolne, `CAPITAL_GATEWAY_API_KEY` == `GATEWAY_API_KEY`, `DATABASE_URL` na loopbacku, `OPENAI_API_KEY` obecny w `agent` i `teams`
- [x] 5.3 Ostrzeżenia bez odmowy: brak `MARKET_MCP_URL`, `TRADING_MCP_URL`, `TEAMS_MCP_URL` — każde nazwane osobno
- [x] 5.4 Baza: start kontenera `compose.yaml`, utworzenie brakujących roli i baz `agent` oraz `teams`, oczekiwanie na gotowość
- [x] 5.5 Nadzór i sprzątanie: wszystkie osiem procesów w jednym wykazie, log prefiksowany, śmierć któregokolwiek kończy całość, `finally` zabija wszystko, co uruchomił ten proces
- [x] 5.6 Flaga wyłączająca terminal przyjmowana w obu pisowniach (`--no-terminal`, `-NoTerminal`)
- [x] 5.7 Testy odmów — po jednym na każdą z 5.2, każdy wywołujący dokładnie ten scenariusz i sprawdzający, że runner odmawia przed uruchomieniem czegokolwiek
- [x] 5.8 Test kolejności: wykaz serwisów daje kolejność gateway → market-data → market-mcp → trading-mcp → teams → teams-mcp → agent → terminal
- [x] 5.9 Test parsowania flag: `--no-terminal` i `-NoTerminal` dają ten sam wynik
- [x] 5.10 `dev.sh` i `dev.ps1` → wrappery przekazujące argumenty do `dev.py`
- [ ] 5.11 (operator — stack jest Twój) Uruchomić cały stack przez `dev.ps1` i sprawdzić, że wszystkie osiem odpowiada. Sprawdzone zamiast tego bez startowania czegokolwiek: `preflight` na realnym repo daje 0 problemów, oba wrappery dochodzą do `dev.py` z kodem 0, a `--explain` wypisuje kolejność. Przy okazji wyszła prawdziwa luka w `modules/agent/.env` — brak `TRADING_MCP_URL`

## 6. `checks.yml`

- [x] 6.1 Job `infra` na ścieżce `infra/**` — `fmt -check -recursive`, potem `init -backend=false` + `validate` **w obu rootach**: `infra/bootstrap/` był dotąd poza każdym checkiem. Sprawdzone lokalnie: oba przechodzą
- [x] 6.2 Blok `case` translacji nazw → tablica asocjacyjna wzorców; wykaz nazw czytany z jej kluczy, nie z drugiej listy
- [x] 6.3 Zrobione jako **trwały test**, nie jednorazowy przebieg: `tests/test_checks_filter.py` wyciąga blok `run:` kroku `filter`, podstawia sztuczny diff i wykonuje prawdziwy shell pod `set -u`. 16 przypadków, w tym oba kierunki spójności — każdy bramkowany job ma wzorzec i każdy wzorzec ma czytającego

## 7. Terraform

- [x] 7.1 `infra/modules/easy-auth-app/` — `azuread_application` + `azuread_service_principal` + `azuread_application_password`, wejścia: nazwa wyświetlana, identifier URI, redirect URI, właściciel
- [x] 7.2 Sześć wywołań modułu plus `moved` dla **dwudziestu jednego** zasobów, nie osiemnastu: tryplet ×6 to osiemnaście, a trzy stabilne GUID-y scopeów (`random_uuid`) też wchodzą do modułu i też trzeba je przenieść
- [x] 7.3 Bramka spełniona, ale w innym brzmieniu, niż zapowiadał design — i to jest istotne. **`0 to add, 0 to change, 0 to destroy` jest na tym stanie nieosiągalne, bo `main` planuje dziś cztery zmiany.** Zmierzone w osobnym worktree: plan na `main` to `0 to add, 4 to change, 0 to destroy`, dokładnie te same cztery App Service’y. Dryf idzie z `WEBSITES_ENABLE_APP_SERVICE_STORAGE` na `teams`, który odkłada trzy data source’y tożsamości i przez to zmienia `allowed_applications` w trzech kolejnych aplikacjach na `known after apply`. Uczciwa bramka: **plan gałęzi jest identyczny z planem `main` poza notkami `moved`, przy 0 add i 0 destroy** — i taki jest. Wszystkie 28 przeniesień trafiło w istniejące obiekty, te same ID
- [x] 7.4 `for_each` po `local.web_app_principal_ids` plus siedem `moved`. Ponowny plan: siedem przeniesień, **zero zmian** na tych politykach
- [x] 7.5 `local.web_app_names` jako źródło liczebników; treść alertu pamięci w `monitoring.tf` liczy przez `length(...)`
- [x] 7.6 Przejrzane wszystkie 19 wystąpień, nie 11 — audyt policzył tylko te, które sam sprawdził. **Nieprawdziwych osiem**: nagłówek „six apps” przy siedmiu i z niepełną listą; „both apps” o poświadczeniach GHCR przy siedmiu; „same as the other two apps” o `WEBSITES_PORT`, którego nie nadpisuje żaden; „three deploy workflows” w trzech miejscach przy jednym wspólnym; „both apps read gateway-api-key” przy trzech (trading-mcp doszedł na `add-trading-mcp`); treść alertu wyjątków „across both apps” przy zapytaniu obejmującym cały workspace. **Wyliczane teraz dwie**, obie operatorskie: treść alertu pamięci i treść alertu wyjątków, przez `length(local.web_app_names)`. **Zostawione jako historia**: pomiary datowane (73,5% przy dwóch, 83,1% przy czterech, 84% przy sześciu) — to nie są stęchłe liczby, to zapis pomiaru. **Zostawione jako poprawne w kontekście**: pięć „the other two” o trzech serwerach narzędzi i trzech URL-ach
- [x] 7.7 `app-service.tf` 1 367 → 1 240, `entra.tf` 225 → 169 (razem −183). Całe `infra/` 2 640 → 2 779, czyli **w górę o 139**: doszedł moduł (155 linii z README) i `moved.tf` (159). `moved.tf` schodzi po zarchiwizowaniu zmiany, więc trwały bilans to ok. −20 linii przy siedmiu politykach i sześciu trypletach zwiniętych do jednego miejsca. Cel „~300 linii mechanicznego boilerplate” z audytu nie jest osiągnięty w liniach i jest osiągnięty w tym, co się liczy: nowy moduł to jedno wywołanie z pięcioma argumentami, nie trzydzieści linii do skopiowania
- [ ] 7.8 (operator — `apply` jest Twój) `terraform apply` lokalnie; potwierdzić, że sześć aplikacji dalej wpuszcza token operatora (terminal się loguje, `agent` i `teams` odpowiadają przez Easy Auth)

## 8. Domknięcie

- [ ] 8.1 `CLAUDE.md` — sekcja o skryptach dev i o siedmiu `deploy-*.yml`; dopisać job `scripts` do opisu CI
- [ ] 8.2 `README.md` — tam, gdzie opisuje uruchomienie stacka
- [ ] 8.3 Zaktualizować tabelę metryk w `docs/plan-refactoru.html` kolumną „Po iter. 2": linie workflow deploy, czas dodania nowego modułu
- [ ] 8.4 `review.md` — plan Terraforma, wynik pierwszego wdrożenia przez wspólny workflow, i to, co wyszło inaczej niż zakładał ten plan
