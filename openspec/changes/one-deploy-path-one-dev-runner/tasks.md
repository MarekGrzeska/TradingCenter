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

- [ ] 5.1 `scripts/dev.py` — tabela serwisów jako lista zamrożonych dataclass (`name`, `directory`, `port`, `command`, `health_path`, `log_prefix`, `color`, `why`); proza kolejności startu przeniesiona do pola `why`
- [ ] 5.2 Kontrole przed startem: Docker obecny, porty wolne, `CAPITAL_GATEWAY_API_KEY` == `GATEWAY_API_KEY`, `DATABASE_URL` na loopbacku, `OPENAI_API_KEY` obecny w `agent` i `teams`
- [ ] 5.3 Ostrzeżenia bez odmowy: brak `MARKET_MCP_URL`, `TRADING_MCP_URL`, `TEAMS_MCP_URL` — każde nazwane osobno
- [ ] 5.4 Baza: start kontenera `compose.yaml`, utworzenie brakujących roli i baz `agent` oraz `teams`, oczekiwanie na gotowość
- [ ] 5.5 Nadzór i sprzątanie: wszystkie osiem procesów w jednym wykazie, log prefiksowany, śmierć któregokolwiek kończy całość, `finally` zabija wszystko, co uruchomił ten proces
- [ ] 5.6 Flaga wyłączająca terminal przyjmowana w obu pisowniach (`--no-terminal`, `-NoTerminal`)
- [ ] 5.7 Testy odmów — po jednym na każdą z 5.2, każdy wywołujący dokładnie ten scenariusz i sprawdzający, że runner odmawia przed uruchomieniem czegokolwiek
- [ ] 5.8 Test kolejności: wykaz serwisów daje kolejność gateway → market-data → market-mcp → trading-mcp → teams → teams-mcp → agent → terminal
- [ ] 5.9 Test parsowania flag: `--no-terminal` i `-NoTerminal` dają ten sam wynik
- [ ] 5.10 `dev.sh` i `dev.ps1` → wrappery przekazujące argumenty do `dev.py`
- [ ] 5.11 Uruchomić cały stack przez `dev.ps1` i sprawdzić, że wszystkie osiem odpowiada; zatrzymać po sobie

## 6. `checks.yml`

- [ ] 6.1 Job `infra` na ścieżce `infra/**` — `terraform fmt -check`, `terraform init -backend=false`, `terraform validate`; bez OIDC i bez backendu
- [ ] 6.2 Blok `case` translacji nazw → tablica asocjacyjna wzorców; wykaz nazw czytany z jej kluczy, nie z drugiej listy
- [ ] 6.3 Uruchomić krok `changes` na sztucznym diffie (`infra/main.tf`, `scripts/dev.py`, `modules/agent/`) pod `set -u` i sprawdzić decyzje — ten sam sposób, który w iteracji 1 złapał błąd przewracający cały job

## 7. Terraform

- [ ] 7.1 `infra/modules/easy-auth-app/` — `azuread_application` + `azuread_service_principal` + `azuread_application_password`, wejścia: nazwa wyświetlana, identifier URI, redirect URI, właściciel
- [ ] 7.2 Sześć wywołań modułu (market-data, market-mcp, trading-mcp, teams-mcp z `app-service.tf`; agent, teams z `entra.tf`) plus bloki `moved` dla wszystkich osiemnastu zasobów
- [ ] 7.3 `terraform plan` lokalnie: MUSI powiedzieć `0 to add, 0 to change, 0 to destroy`. Cokolwiek innego zatrzymuje zadanie i wraca do 7.2
- [ ] 7.4 `for_each` dla siedmiu `azurerm_key_vault_access_policy` plus `moved` dla nich; ponowny plan `0/0/0`
- [ ] 7.5 `local.web_app_names` jako źródło liczebników; treść alertu pamięci w `monitoring.tf` liczy przez `length(...)`
- [ ] 7.6 Przejrzeć 11 ręcznie wpisanych liczebników w `infra/*.tf`, poprawić nieprawdziwe, wyliczać te, które mają na czym stanąć; pozostałe zostawić z liczbą, którą właśnie sprawdzono
- [ ] 7.7 Zmierzyć linie `app-service.tf` i `entra.tf` przed i po
- [ ] 7.8 Operator: `terraform apply` lokalnie; potwierdzić, że sześć aplikacji dalej wpuszcza token operatora (terminal się loguje, `agent` i `teams` odpowiadają przez Easy Auth)

## 8. Domknięcie

- [ ] 8.1 `CLAUDE.md` — sekcja o skryptach dev i o siedmiu `deploy-*.yml`; dopisać job `scripts` do opisu CI
- [ ] 8.2 `README.md` — tam, gdzie opisuje uruchomienie stacka
- [ ] 8.3 Zaktualizować tabelę metryk w `docs/plan-refactoru.html` kolumną „Po iter. 2": linie workflow deploy, czas dodania nowego modułu
- [ ] 8.4 `review.md` — plan Terraforma, wynik pierwszego wdrożenia przez wspólny workflow, i to, co wyszło inaczej niż zakładał ten plan
