## 1. Uwierzytelnianie w `capital-gateway`

Idzie pierwsze i w całości lokalnie. Nic nie staje w internecie, zanim to nie działa.

- [x] 1.1 Rozstrzygnij pytanie otwarte z `design.md`: klucz współdzielony w nagłówku czy token tożsamości zarządzanej. Zapisz wybór i powód w `design.md` — **klucz współdzielony w nagłówku `X-Gateway-Key`**, wybrany z użytkownikiem
- [x] 1.2 Dodaj do `config.py` konfigurację poświadczenia; **brak konfiguracji MUST przerwać start** — moduł nie może wstać w trybie bez uwierzytelniania
- [x] 1.3 Wepnij weryfikację poświadczenia przed wszystkimi trasami HTTP; odmowa to `401` bez dotknięcia providera
- [x] 1.4 Wepnij weryfikację przy zestawianiu WebSocketa `/ws/stream` — odmowa zamyka połączenie przed zapisaniem konsumenta do rozgłaszania
- [x] 1.5 Przejrzyj trasę `/` pod kątem sondy zdrowia: zostaje jedynym wyjątkiem bez poświadczenia i MUST NOT ujawniać konta, stanu sesji ani wersji zależności
- [x] 1.6 Wyłącz `docs_url` i `openapi_url` w konfiguracji produkcyjnej; poza produkcją zostają — na nich stoi generowanie kontraktu
- [x] 1.7 Upewnij się, że poświadczenie wywołującego nie trafia do logów ani do komunikatów błędów
- [x] 1.8 Testy do wszystkich wymagań `specs/capital-access-control/spec.md`: brak poświadczenia, poświadczenie nieuznane, WebSocket bez poświadczenia, odmowa startu bez konfiguracji, `404` na dokumentacji w produkcji, schemat dostępny poza produkcją, brak poświadczenia w logu
- [x] 1.9 Zaktualizuj `modules/capital-gateway/.env.example` i `README.md`
- [x] 1.10 Sprawdź, że generowanie kontraktu terminala z OpenAPI nadal działa — **nie dotyczy**: `contract.mjs` czyta schemat `market-data` (`python -m market_data.openapi`), nigdy gatewaya; zmiana w tym module nie ma na nie wpływu

## 2. Konsumenci gatewaya

Przed włączeniem wymogu po stronie gatewaya — inaczej wszystko przestaje działać naraz.

- [x] 2.1 `market-data`: dodaj poświadczenie do żądań REST i do zestawiania WebSocketa; brak konfiguracji MUST przerwać start — `gateway_api_key` w `Settings`, wspólny nagłówek na `http_client()` i `subscribe()`
- [x] 2.2 `market-data`: odróżnij odmowę dostępu od braku danych — odmowa MUST NOT zapisać pokrycia ani oznaczyć okresu jako zebranego — **już zapewnione** przez istniejący `except GatewayError` w `backfill.py` (`GatewayRefused` dziedziczy po nim); dopisany tylko test to potwierdzający
- [x] 2.3 `market-data`: poświadczenie nie trafia do logów — poprawiony też mylący docstring w `errors.py`, który twierdził, że na tej ścieżce nie ma żadnego poświadczenia
- [x] 2.4 Testy do `specs/market-data-upstream-access/spec.md`
- [x] 2.5 `market-data`: dodaj trasy proxy `GET /instruments`, `GET /instruments/search`, `GET /asset-classes` przekazujące do gatewaya własnym poświadczeniem, bez zmiany kształtu odpowiedzi
- [x] 2.6 `market-data`: odmowa gatewaya na trasie proxy MUST być rozróżnialna od pustego wyniku wyszukiwania — istniejący globalny `@app.exception_handler(GatewayError)` już mapuje na 502/504
- [x] 2.7 Testy do `specs/market-data-api/spec.md` (delta tej zmiany)
- [x] 2.8 `terminal`: przepisz `gatewaySource.ts` na wywołania do `market-data`; usuń `gatewayHttp` z `config.ts`, proxy `/api` z `vite.config.ts` i `VITE_GATEWAY_HTTP`/`GATEWAY_PROXY_TARGET` z `.env.example`. `ping()` przełączony z `/capabilities` (gatewayowe, nieproxowane) na `/asset-classes`. Kontrakt terminala zregenerowany (`pnpm contract:generate`) pod nowe trasy `market-data`
- [x] 2.9 `terminal`: ścieżki API względne — już tak działało (`archiveHttp`). Easy Auth to konfiguracja Static Web Apps, nie kod — wchodzi w grupie 5; nic tu do zaimplementowania
- [x] 2.10 Uruchom oba moduły lokalnie z włączonym uwierzytelnianiem i potwierdź, że wyszukiwanie instrumentów w terminalu działa end-to-end przez `market-data` — **zweryfikowane na żywych procesach** (nie tylko testami): gateway i market-data odpalone lokalnie z pasującym kluczem, potwierdzone przez `curl`: `/` bez klucza 200, `/asset-classes` bez/ze złym kluczem 401×2, z kluczem 200; `market-data`'s proxy realnie sięga do capital.com i zwraca dane; WebSocket bez klucza dostaje realne HTTP 403 na handshake, z kluczem łączy się i odbiera `{"kind":"status","state":"connected"}`

## 3. Bootstrap stanu Terraforma

- [x] 3.1 `infra/bootstrap/` z providerem `azurerm` i stanem lokalnym — bez backendu zdalnego, bo to on tu powstaje
- [x] 3.2 Grupa zasobów (`rg-tradingcenter-tfstate`), konto magazynu (`sttradingcenterstate`) i kontener (`tfstate`); wersjonowanie blobów włączone, retencja usuniętych 30 dni
- [x] 3.3 `terraform apply` w `bootstrap/` — zastosowane na subskrypcji `mgrzeskait@outlook.com` / `FreeTrial_2014-09-01`, nazwy w `outputs.tf`
- [x] 3.4 `.gitignore` — `infra/**/.terraform/` i `*.tfplan` zignorowane; **stan bootstrapu i `.terraform.lock.hcl` commitowane celowo** (design.md: „nic wrażliwego", a odtwarzalność tego jednorazowego roota jest warta więcej niż szum w diffie)
- [ ] 3.5 **Zdejmij limit wydatków subskrypcji** — krok operatorski, MUST być wykonany przed trzydziestym dniem od założenia konta. Poza zasięgiem automatyzacji: to decyzja o rozliczeniach, nie coś do zrobienia z CLI

## 4. Baza

**Odkrycie w trakcie realizacji, zmieniające plan:** administrator Entra serwera Postgres
Flexible Server omija każdy `GRANT` na każdej bazie — to nie jest rola z uprawnieniami,
to superużytkownik. Gdyby to samo konto (`mgrzeskait@outlook.com`) było jednocześnie
tożsamością „deweloperską", cała ochrona przed pomyłkowym `alembic upgrade` na produkcji
byłaby fikcją — administrator i tak dobija do `market_data`, GRANT-y go nie dotyczą.
Rozstrzygnięcie z użytkownikiem: **osobny Service Principal** `sp-tradingcenter-market-data-dev`
(`infra/entra.tf`, provider `azuread`) jako tożsamość „deweloperska" zamiast osobistego
konta. Osobiste konto zostaje wyłącznie administratorem — do naprawy awarii i do
DBeavera — nigdy poświadczeniem czytanym automatycznie przez proces. Konsekwencja dla
roli „operatorskiej": skoro DBeaver i tak łączy się kontem administratora (per decyzję
użytkownika), **`SELECT`-only wobec niego nie jest egzekwowalne** — zaakceptowane wprost
jako ograniczenie dla projektu jednoosobowego, nie ukryte.

- [x] 4.1 `infra/main.tf` z backendem `azurerm` na kontenerze z grupy 3 oraz `infra/variables.tf` (region, nazwy, wersja Postgresa, adres dewelopera)
- [x] 4.2 `azurerm_postgresql_flexible_server`: `B_Standard_B1ms`, wersja 17, `storage_mb = 32768`, `backup_retention_days = 7`, `zone = "2"` (przypisane przez Azure przy tworzeniu, przypięte jawnie żeby plan nie chciał tego cofać)
- [x] 4.3 Wymuś TLS na poziomie serwera — `require_secure_transport = ON`
- [x] 4.4 Utwórz obie bazy: `market_data` i `market_data_dev`
- [x] 4.5 Przypisz administratora Entra dla serwera (`mgrzeskait@outlook.com`) — droga powrotna przy błędnej konfiguracji ról, **wyłącznie do tego celu i do DBeavera, nigdy do automatycznych połączeń**
- [x] 4.6 Reguła firewalla na adres dewelopera czytany ze zmiennej (`infra/terraform.tfvars`, gitignored)
- [ ] 4.7 Rola aplikacyjna: odczyt i zapis wyłącznie na `market_data` — **przeniesione do grupy 5**: potrzebuje tożsamości zarządzanej App Service, która jeszcze nie istnieje
- [x] 4.8 Rola deweloperska: `sp-tradingcenter-market-data-dev` (Service Principal, nie osobiste konto) — `CREATE`/`USAGE` na schemacie `public` w `market_data_dev`, `CONNECT` na `market_data_dev` odebrane od `PUBLIC` i nadane wyłącznie tej roli, **jawny `REVOKE ALL ... FROM` na `market_data`**
- [x] 4.9 ~~Rola operatorska: `SELECT` na obu bazach~~ — **zmienione decyzją użytkownika**: operator (DBeaver) używa konta administratora; `docs/dbeaver-azure-connection.html` do poprawienia w grupie 11, żeby nie obiecywał uprawnienia, którego nie ma
- [x] 4.10 Odbierz `PUBLIC` domyślne prawa na obu bazach — `REVOKE CONNECT ... FROM PUBLIC` na `market_data` i `market_data_dev`
- [x] 4.11 **Sprawdzone ręcznie, nie tylko planem**: token roli deweloperskiej (client credentials flow) połączył się i wykonał `CREATE TABLE` na `market_data_dev`, a na `market_data` dostał `InsufficientPrivilegeError: permission denied for database "market_data" — User does not have CONNECT privilege`. Sprawdzenie roli operatorskiej nie dotyczy — patrz 4.9

## 5. Key Vault i plan aplikacji

- [x] 5.1 `infra/key-vault.tf`: sejf z losowym przyrostkiem w nazwie (miękkie usuwanie) i sekretami capital.com — `kv-tradingctr-58hw`; wartości sekretów (`capital-api-key`, `capital-identifier`, `capital-password`, `gateway-api-key`) ustawione poza Terraformem, `az keyvault secret set` z lokalnych `.env`, zgodnie z design.md ("wartość nie przechodzi przez kod Terraforma")
- [x] 5.2 `infra/app-service.tf`: plan `B1` Linux, **`worker_count = 1` z komentarzem, dlaczego nie wolno tego zmienić**, bez autoskalowania
- [x] 5.3 Aplikacja `capital-gateway`: `always_on`, `websockets_enabled`, tożsamość `SystemAssigned`, `ip_restriction_default_action = "Deny"` z wyjątkiem na adresy wyjściowe planu czytane z zasobu (`market_data.possible_outbound_ip_address_list`, dynamic block)
- [x] 5.4 Aplikacja `market-data`: `always_on`, `websockets_enabled`, tożsamość `SystemAssigned`, Easy Auth z Entra ID — `unauthenticated_action = "Return401"` (nie redirect: `terminal` woła przez `fetch()`, przekierowanie zwróciłoby HTML zamiast JSON-a; obsługa 401 po stronie `terminal` to osobne zadanie, poza tą grupą)
- [x] 5.5 Uprawnienia odczytu sekretów dla obu tożsamości (`azurerm_key_vault_access_policy`, `Get`/`List`); w ustawieniach aplikacji wyłącznie odwołania `@Microsoft.KeyVault(SecretUri=...)`
- [x] 5.6 Dopisz do reguły firewalla bazy adresy wyjściowe planu — czytane z zasobu (`for_each` po `market_data.possible_outbound_ip_address_list`), nigdy ręcznie; 32 reguły zastosowane. **Wymaga dwóch przebiegów apply przy pierwszym uruchomieniu** — `for_each` na poziomie zasobu nie policzy planu po liście, która nie istnieje, dopóki aplikacja nie powstanie (komentarz w `database.tf`)
- [x] 5.7 **(dawne 4.7)** Rola aplikacyjna w Postgresie: `pgaadauth_create_principal_with_oid('app-tradingcenter-market-data', <object_id>, 'service', false, false)` — sygnatura funkcji ma inną kolejność argumentów niż w 4.8 (`rolename, objectid, objecttype, isadmin, ismfa`, nie `oid, rolename, isadmin`); `CONNECT`+`CREATE`/`USAGE` wyłącznie na `market_data`, jawny `REVOKE ALL` na `market_data_dev`. **Sprawdzone ręcznie, częściowo**: `has_database_privilege` z konta administratora potwierdza `CONNECT`=true na `market_data`, false na `market_data_dev`. Token samej tożsamości zarządzanej nie do zdobycia z zewnątrz — `IDENTITY_ENDPOINT`/`IDENTITY_HEADER` istnieją tylko w procesie kontenera aplikacji, nie w konsoli Kudu/SCM, a kod jeszcze nie jest wdrożony (grupa 7). Pełna weryfikacja żywym tokenem tożsamości zarządzanej — przy 8.6 lub pierwszym wdrożeniu `market-data`
- [x] 5.7 `infra/monitoring.tf`: Application Insights — workspace-based, `log-tradingcenter` + `appi-tradingcenter`
- [x] 5.8 `terraform fmt`, `terraform validate`, `apply` — zastosowane (dwie fazy przez błąd `for_each` po nieistniejącej jeszcze liście, plus jedna poprawka: `IpSecurityRestriction.Description` nie może zawierać przecinka, Azure odrzucało to 400-tką)

## 6. Federacja OIDC

- [x] 6.1 `infra/github-oidc.tf`: aplikacja Entra (`app-tradingcenter-github-actions`), dwa poświadczenia federowane (`ref:refs/heads/main` do wdrożeń/apply, `pull_request` wyłącznie do planu), `Contributor` na `rg-tradingcenter`. Przy okazji: `Storage Blob Data Contributor` na koncie stanu dla tej tożsamości **i** dla operatora — `Owner` na subskrypcji nie daje dostępu data-plane do Storage, więc bez tego backend `use_azuread_auth` zablokowałby też lokalny `terraform`. Backend w `main.tf` przełączony na `use_azuread_auth = true`, potwierdzone `terraform init -reconfigure` + `plan` bez dryfu
- [x] 6.2 Ustaw `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` jako **`vars`, nie `secrets`** — `gh variable set`, potwierdzone `gh variable list`
- [x] 6.3 Potwierdź, że w repozytorium i w GitHub Secrets nie ma **żadnego** sekretu do Azure — `gh secret list` puste

## 7. Wdrożenia

- [x] 7.1 `Dockerfile` dla `capital-gateway` — multi-stage, `uv sync` w builderze, runtime `python:3.12-slim-bookworm`, port 80. **Lokalna weryfikacja builda nieudana**: Docker Desktop na tej maszynie wraca `"only one connection allowed"` przy `load metadata` dla `ghcr.io`/`docker.io`, powtarzalnie, niezależnie od zawartości Dockerfile — wygląda na lokalny problem buildera, nie błąd w pliku. Realna weryfikacja zostaje na 7.4 (build w GitHub Actions, czyste środowisko)
- [x] 7.2 `Dockerfile` dla `market-data` — jak wyżej, plus `migrations/` i `alembic.ini` w obrazie; migracje NIE uruchamiają się automatycznie przy starcie (jawna decyzja, komentarz w pliku)
- [x] 7.3 Workflow wdrożenia gatewaya (`deploy-gateway.yml`): build, publikacja do GHCR z tagiem `github.sha`, `azure/login@v2` przez OIDC, `azure/webapps-deploy@v3`, `id-token: write`
- [ ] 7.4 Pierwsze wdrożenie gatewaya i sprawdzenie całego łańcucha na module, który już działa — **wstrzymane**: wymaga scalenia do `main` (poświadczenie federowane akceptuje tylko `ref:refs/heads/main` i `pull_request` — `workflow_dispatch` z tego brancha nie uwierzytelni się do Azure), a to pierwszy realny push na współdzielony branch z tej sesji. Czeka na decyzję użytkownika
- [x] 7.5 Workflow wdrożenia `market-data` (`deploy-market-data.yml`) — analogicznie do 7.3
- [x] 7.6 `infra/static-web-app.tf`: plan Free, wbudowane logowanie — **odkrycie przy apply**: West Europe (region z reszty platformy) odrzuca nowych klientów Static Web Apps na tej subskrypcji (`RequestDisallowedByAzure`); przestawione na East US 2, jedyny z pozostałych czterech dopuszczalnych regionów bliższy Europie
- [x] 7.7 Workflow wdrożenia `terminal` na Static Web Apps (`deploy-terminal.yml`) — **odstępstwo od celu „żaden sekret Azure"**: `Azure/static-web-apps-deploy` nie ma ścieżki OIDC, wyłącznie token wdrożeniowy (`AZURE_STATIC_WEB_APPS_API_TOKEN`, z `terraform output terminal_api_key`, ustawiony jako GitHub secret). Wymuszone przez narzędzia Azure, nie wybór projektu — opisane wprost w komentarzu workflow. Build produkcyjny w trybie pełnego URL-a wprost do `market-data` (`VITE_ARCHIVE_HTTP`/`VITE_ARCHIVE_WS`) — SWA i tak nie potrafi proxować WebSocketu, więc to jedyny tryb, który w ogóle działa; CORS i obsługa 401 po stronie przeglądarki pozostają otwarte (patrz notatka w grupie 5)
- [x] 7.8 Workflow Terraforma (`terraform.yml`): `plan` na pull requestach (komentarz z planem), `apply` po push do `main`. `infra/terraform.tfvars` jest per-operator i gitignored — te same trzy wartości (adres IP dewelopera, `postgres_admin_object_id`, `postgres_admin_upn`) powielone jako `TF_VAR_*` w GitHub vars, bo CI nie jest operatorem z własnym `.tfvars`
- [x] 7.9 Potwierdź, że `checks.yml` nadal przechodzi bez zmian — nie dotknięty (diff ograniczony do `infra/`, `.github/workflows/deploy-*.yml`, `Dockerfile`/`.dockerignore`); `ruff check` czysty w obu modułach Python. Jeden test (`test_start_without_a_gateway_key_is_refused`) pada lokalnie, ale to artefakt uruchomienia z realnym `.env` w katalogu — `monkeypatch.delenv` nie odcina odczytu przez `pydantic-settings` z pliku; w CI (bez `.env`) nieistotne, niezwiązane z tą zmianą

## 8. Połączenie `market-data` z bazą

- [x] 8.1 Rozszerz konfigurację o tryb uwierzytelniania tożsamością i wymóg TLS; czytelny błąd startu, gdy konfiguracja nie wymusza szyfrowania — `DATABASE_USER` + trzy opcjonalne `AZURE_CLIENT_ID`/`AZURE_CLIENT_SECRET`/`AZURE_TENANT_ID` (razem albo wcale) w `config.py`; `DATABASE_URL` MUST NOT nieść poświadczenia, MUST mieć `sslmode` z `{require, verify-ca, verify-full}`
- [x] 8.2 Wepnij pobieranie poświadczenia w moment nawiązywania połączenia przez pulę, nie w start procesu — `password` w `asyncpg.create_pool`/`connect` to callable (`_TokenProvider`), wywoływany przez asyncpg per fizyczne połączenie, nie raz przy starcie
- [x] 8.3 Odnawiaj poświadczenie tak, by połączenie nawiązane po okresie jego ważności zestawiało się poprawnie — konsekwencja 8.2: każde nowe połączenie woła `_TokenProvider` od nowa, `DefaultAzureCredential`/`ClientSecretCredential` cache'ują i odnawiają wewnętrznie
- [x] 8.4 Poświadczenie nie trafia do logów — log połączenia niesie host, port i nazwę bazy — `_connection_target()`, wyłącznie `host:port/dbname`
- [x] 8.5 Testy do `specs/market-data-database-connection/spec.md` — `test_config.py` (TLS, brak poświadczenia w URL, `database_user`), `test_db.py` (`_credential`, `_TokenProvider`, odnawianie, brak wycieku do logu — z fikcyjnym poświadczeniem, bez sieci)
- [x] 8.6 Migracje na `market_data_dev` kontem deweloperskim, potem na `market_data` kontem aplikacyjnym — **dev zweryfikowane w pełni, na żywo**: `alembic upgrade head` przez `sp-tradingcenter-market-data-dev` (token Entra, TLS) przeszło na `market_data_dev`; ta sama rola na `market_data` dostała `InsufficientPrivilegeError: User does not have CONNECT privilege` (spójne z 4.11). **Strona aplikacyjna (`market_data`, tożsamość zarządzana) wstrzymana**, ten sam powód co w 5.7: token tożsamości zarządzanej nie do zdobycia poza wdrożonym App Service — do zrobienia przy pierwszym realnym wdrożeniu (7.4/8.6 razem). Po drodze poprawka w `migrations/env.py`: SQLAlchemy przekazuje `sslmode` z URL jako dosłowny kwarg do `asyncpg.connect()`, którego ten nie rozumie (`ssl=`, nie `sslmode=`) — asyncpg samo parsuje `sslmode` z surowego DSN, więc `pool()`/`connect()` w `db.py` nigdy na to nie trafiły

## 9. Środowisko lokalne

- [x] 9.1 Zaktualizuj `modules/market-data/.env.example`: host w Azure, `market_data_dev`, `sslmode=require`, bez hasła; opis portu 55432 znika — dodane `DATABASE_USER` i trójka `AZURE_CLIENT_ID`/`AZURE_CLIENT_SECRET`/`AZURE_TENANT_ID` (tożsamość deweloperska)
- [x] 9.2 Usuń `compose.yaml` — kontener `tradingcenter-db` zatrzymany (`docker compose down`, bez `-v`: wolumen `tradingcenter-db-data` zostaje na dysku, nieużywany)
- [x] 9.3 Wytnij ze `scripts/dev.sh` obsługę kontenera: sprawdzanie Dockera i `docker compose`, `DB_PORT`, wykrywanie kolizji portu, `up -d db`, oczekiwanie na `healthy`, sprzątanie, komunikat o `docker compose down`
- [x] 9.4 To samo w `scripts/dev.ps1`, zachowując parzystość komunikatów z `dev.sh`
- [x] 9.5 Zastąp kontrolę zgodności portu kontrolą, że `.env` istnieje i wskazuje `market_data_dev` — pomyłkowe wskazanie produkcji ma być zauważone przed startem
- [x] 9.6 Zaktualizuj `README.md`: uruchamianie środowiska, Docker potrzebny wyłącznie do `pytest` — główny `README.md` i `modules/market-data/README.md`
- [x] 9.7 Potwierdź, że `modules/market-data/tests/conftest.py` **pozostał bez zmian** i `pytest` przechodzi z testami bazodanowymi — `git diff` na plik pusty, 480 passed / 7 skipped
- [x] 9.8 Uruchom `market-data` lokalnie przeciw `market_data_dev` i potwierdź zapis świec end-to-end — **zweryfikowane na żywo**: `./scripts/dev.sh --no-terminal`, `POST /pairs` na `US100`/`MINUTE`, backfill zapisał 2470 świec do `market_data_dev` w Azure tożsamością deweloperską. Po drodze naprawiony przedistniejący błąd: `dev.sh`/`dev.ps1` sprawdzały gotowość gatewaya przez `/capabilities`, trasę wymagającą klucza od grupy 1 — przestawione na `/`

## 10. Monitoring

- [x] 10.1 Wystaw z `market-data` metrykę wieku najnowszej świecy do Application Insights — bez niej najważniejszy alert nie ma na czym stanąć — `market_data/telemetry.py`: `market_data.candle_age_seconds`, gauge obserwowalny OpenTelemetry, odświeżany co 60s w tle (`refresh_loop`), wyłącznie dla par, których gateway nie zgłasza jako `MARKET_CLOSED`. `azure-monitor-opentelemetry` konfigurowane wyłącznie gdy `APPLICATIONINSIGHTS_CONNECTION_STRING` ustawiony — lokalnie no-op. 7 nowych testów (`test_telemetry.py`), zweryfikowane też na żywo (start modułu przeciw realnej bazie, `/health` 200, czyste zamknięcie pętli)
- [x] 10.2 Alert: wiek najnowszej świecy przekracza próg w godzinach handlu — `alert-candle-age-stale` na `market_data.candle_age_seconds` > 600s. „W godzinach handlu” zakodowane w samej metryce (10.1 pomija pary z zamkniętym rynkiem), nie w harmonogramie alertu. `skip_metric_validation = true` — moduł jeszcze nie wdrożony (7.4), metryka nigdy nie dotarła do Application Insights, więc walidacja definicji metryki po stronie Azure odrzuciłaby regułę
- [x] 10.3 Alert: baza nie odpowiada (`is_db_alive`, `connections_failed`) — `alert-database-connections-failed` na wbudowaną metrykę Postgres Flexible Server `connections_failed` > 0. `is_db_alive` potraktowane jako opis zamiaru, nie osobna metryka do zbudowania — nie istnieje jako wbudowana metryka platformy, a `/health` już zwraca stan bazy przez HTTP
- [x] 10.4 Alert: `storage_percent > 80%` — `alert-database-storage-high`
- [x] 10.5 Alert: `MemoryPercentage > 85%` na planie — `alert-plan-memory-high`
- [x] 10.6 Alert: `Http5xx` na gatewayu — `alert-gateway-http-5xx`
- [x] 10.7 **Bez alertu na CPU** — na `B1` procesor skacze przy każdym uzupełnianiu i reguła kłamałaby; potwierdzone: w `monitoring.tf` nie ma `azurerm_monitor_metric_alert` na CPU, z komentarzem wprost mówiącym, że tak ma zostać. Grupa alertów woła jeden `azurerm_monitor_action_group` (e-mail operatora — nowa zmienna `operator_email`, per-operator jak reszta `terraform.tfvars`, powielona jako `TF_VAR_OPERATOR_EMAIL` w GitHub vars dla CI)

## 11. Domknięcie

- [x] 11.1 `ruff check` i `pytest` dla obu modułów, `pnpm test` dla terminala, `terraform fmt` i `validate` dla `infra/` — wszystko zielone: capital-gateway 154 passed/8 skipped (bez lokalnego `.env`, jak w CI — z nim jeden test pada na wyciek realnego klucza przez `pydantic-settings`, artefakt lokalny, nieistotny dla CI), market-data 487 passed/7 skipped, terminal 224 passed + `contract:check`/`lint`/`typecheck` czyste, `terraform fmt`/`validate` czyste
- [x] 11.2 Sprawdź, że w repozytorium nie został żaden trwały sekret — `.env.example`, `README.md`, `scripts/`, `infra/`, workflowy — przeszukane `.env.example` (puste pola sekretów), historia gita (brak realnego `AZURE_CLIENT_SECRET` w jakimkolwiek commicie), `infra/*.tf` (tylko nazwy sekretów Key Vault, nie wartości), workflowy (wyłącznie `secrets.GITHUB_TOKEN`, token efemeryczny platformy), `.gitignore` pokrywa `.env`/`.env.*`/`*.tfvars`
- [x] 11.3 Rozstrzygnij drugie pytanie otwarte z `design.md` o obsługę Entra w DBeaverze i popraw `docs/dbeaver-azure-connection.html`, jeśli odpowiedź tego wymaga — **rozstrzygnięte**: DBeaver Community nie obsługuje natywnie Entra ID dla PostgreSQL-a (funkcja Lite/Enterprise/Ultimate); ręczne wklejanie tokenu zostaje, ze wzmianką o skrypcie `~/.pgpass` jako alternatywie. Przy okazji poprawiony dokument w miejscu, gdzie był nieaktualny względem decyzji z grupy 4: opisywał nieistniejącą już czwartą rolę operatorską z samym `SELECT` — teraz opisuje rzeczywisty stan (DBeaver łączy się kontem administratora, pełny dostęp do obu baz, `Read-only connection` jako jedyna, nieegzekwowana przez bazę ochrona). Dodana też uwaga o koncie gościa B2B (UPN inny niż login), odkryta ręcznie w grupie 8
- [ ] 11.4 Zweryfikuj wdrożoną platformę end-to-end: logowanie do terminala, wykres z archiwum, zapis świec przez ingest
