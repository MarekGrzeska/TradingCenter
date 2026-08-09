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

- [ ] 5.1 `infra/key-vault.tf`: sejf z losowym przyrostkiem w nazwie (miękkie usuwanie) i sekretami capital.com
- [ ] 5.2 `infra/app-service.tf`: plan `B1` Linux, **`worker_count = 1` z komentarzem, dlaczego nie wolno tego zmienić**, bez autoskalowania
- [ ] 5.3 Aplikacja `capital-gateway`: `always_on`, `websockets_enabled`, tożsamość `SystemAssigned`, `ip_restriction_default_action = "Deny"` z wyjątkiem na adresy wyjściowe planu czytane z zasobu
- [ ] 5.4 Aplikacja `market-data`: `always_on`, `websockets_enabled`, tożsamość `SystemAssigned`, Easy Auth z Entra ID
- [ ] 5.5 Uprawnienia odczytu sekretów dla obu tożsamości; w ustawieniach aplikacji wyłącznie odwołania `@Microsoft.KeyVault(SecretUri=...)`
- [ ] 5.6 Dopisz do reguły firewalla bazy adresy wyjściowe planu — czytane z zasobu, nigdy ręcznie
- [ ] 5.7 **(dawne 4.7)** Rola aplikacyjna w Postgresie: `pgaadauth_create_principal_with_oid` na `object_id` tożsamości zarządzanej `market-data`, `CONNECT`+`CREATE`/`USAGE` wyłącznie na `market_data`, jawny `REVOKE ALL` na `market_data_dev`. Sprawdź ręcznie jak w 4.11, tym razem tokenem tożsamości zarządzanej
- [ ] 5.7 `infra/monitoring.tf`: Application Insights
- [ ] 5.8 `terraform fmt`, `terraform validate`, `apply`

## 6. Federacja OIDC

- [ ] 6.1 `infra/github-oidc.tf`: aplikacja Entra, poświadczenie federowane dla repozytorium, przypisanie roli na grupie zasobów
- [ ] 6.2 Ustaw `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` jako **`vars`, nie `secrets`**
- [ ] 6.3 Potwierdź, że w repozytorium i w GitHub Secrets nie ma **żadnego** sekretu do Azure

## 7. Wdrożenia

- [ ] 7.1 `Dockerfile` dla `capital-gateway`
- [ ] 7.2 `Dockerfile` dla `market-data`
- [ ] 7.3 Workflow wdrożenia gatewaya: build, publikacja do GHCR z tagiem `github.sha` (**nie `latest`**), `azure/login@v2` przez OIDC, `azure/webapps-deploy@v3`. Uprawnienia `id-token: write`
- [ ] 7.4 Pierwsze wdrożenie gatewaya i sprawdzenie całego łańcucha na module, który już działa
- [ ] 7.5 Workflow wdrożenia `market-data`
- [ ] 7.6 `infra/static-web-app.tf`: plan Free, wbudowane logowanie
- [ ] 7.7 Workflow wdrożenia `terminal` na Static Web Apps
- [ ] 7.8 Workflow Terraforma: `plan` na pull requestach, `apply` po scaleniu do `main`
- [ ] 7.9 Potwierdź, że `checks.yml` nadal przechodzi bez zmian

## 8. Połączenie `market-data` z bazą

- [ ] 8.1 Rozszerz konfigurację o tryb uwierzytelniania tożsamością i wymóg TLS; czytelny błąd startu, gdy konfiguracja nie wymusza szyfrowania
- [ ] 8.2 Wepnij pobieranie poświadczenia w moment nawiązywania połączenia przez pulę, nie w start procesu
- [ ] 8.3 Odnawiaj poświadczenie tak, by połączenie nawiązane po okresie jego ważności zestawiało się poprawnie
- [ ] 8.4 Poświadczenie nie trafia do logów — log połączenia niesie host, port i nazwę bazy
- [ ] 8.5 Testy do `specs/market-data-database-connection/spec.md`
- [ ] 8.6 Migracje na `market_data_dev` kontem deweloperskim, potem na `market_data` kontem aplikacyjnym

## 9. Środowisko lokalne

- [ ] 9.1 Zaktualizuj `modules/market-data/.env.example`: host w Azure, `market_data_dev`, `sslmode=require`, bez hasła; opis portu 55432 znika
- [ ] 9.2 Usuń `compose.yaml`
- [ ] 9.3 Wytnij ze `scripts/dev.sh` obsługę kontenera: sprawdzanie Dockera i `docker compose`, `DB_PORT`, wykrywanie kolizji portu, `up -d db`, oczekiwanie na `healthy`, sprzątanie, komunikat o `docker compose down`
- [ ] 9.4 To samo w `scripts/dev.ps1`, zachowując parzystość komunikatów z `dev.sh`
- [ ] 9.5 Zastąp kontrolę zgodności portu kontrolą, że `.env` istnieje i wskazuje `market_data_dev` — pomyłkowe wskazanie produkcji ma być zauważone przed startem
- [ ] 9.6 Zaktualizuj `README.md`: uruchamianie środowiska, Docker potrzebny wyłącznie do `pytest`
- [ ] 9.7 Potwierdź, że `modules/market-data/tests/conftest.py` **pozostał bez zmian** i `pytest` przechodzi z testami bazodanowymi
- [ ] 9.8 Uruchom `market-data` lokalnie przeciw `market_data_dev` i potwierdź zapis świec end-to-end

## 10. Monitoring

- [ ] 10.1 Wystaw z `market-data` metrykę wieku najnowszej świecy do Application Insights — bez niej najważniejszy alert nie ma na czym stanąć
- [ ] 10.2 Alert: wiek najnowszej świecy przekracza próg w godzinach handlu
- [ ] 10.3 Alert: baza nie odpowiada (`is_db_alive`, `connections_failed`)
- [ ] 10.4 Alert: `storage_percent > 80%`
- [ ] 10.5 Alert: `MemoryPercentage > 85%` na planie
- [ ] 10.6 Alert: `Http5xx` na gatewayu
- [ ] 10.7 **Bez alertu na CPU** — na `B1` procesor skacze przy każdym uzupełnianiu i reguła kłamałaby; potwierdź, że nie powstał

## 11. Domknięcie

- [ ] 11.1 `ruff check` i `pytest` dla obu modułów, `pnpm test` dla terminala, `terraform fmt` i `validate` dla `infra/`
- [ ] 11.2 Sprawdź, że w repozytorium nie został żaden trwały sekret — `.env.example`, `README.md`, `scripts/`, `infra/`, workflowy
- [ ] 11.3 Rozstrzygnij drugie pytanie otwarte z `design.md` o obsługę Entra w DBeaverze i popraw `docs/dbeaver-azure-connection.html`, jeśli odpowiedź tego wymaga
- [ ] 11.4 Zweryfikuj wdrożoną platformę end-to-end: logowanie do terminala, wykres z archiwum, zapis świec przez ingest
