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

- [ ] 2.1 `market-data`: dodaj poświadczenie do żądań REST i do zestawiania WebSocketa; brak konfiguracji MUST przerwać start
- [ ] 2.2 `market-data`: odróżnij odmowę dostępu od braku danych — odmowa MUST NOT zapisać pokrycia ani oznaczyć okresu jako zebranego
- [ ] 2.3 `market-data`: poświadczenie nie trafia do logów
- [ ] 2.4 Testy do `specs/market-data-upstream-access/spec.md`
- [ ] 2.5 `market-data`: dodaj trasy proxy `GET /instruments`, `GET /instruments/search`, `GET /asset-classes` przekazujące do gatewaya własnym poświadczeniem, bez zmiany kształtu odpowiedzi
- [ ] 2.6 `market-data`: odmowa gatewaya na trasie proxy MUST być rozróżnialna od pustego wyniku wyszukiwania
- [ ] 2.7 Testy do `specs/market-data-api/spec.md` (delta tej zmiany)
- [ ] 2.8 `terminal`: przepisz `gatewaySource.ts` na wywołania do `market-data`; usuń `gatewayHttp` z `config.ts` jako osobny adres i `GATEWAY_PROXY_TARGET` z `vite.config.ts`
- [ ] 2.9 `terminal`: poświadczenie do `market-data` (Easy Auth), ścieżki API względne
- [ ] 2.10 Uruchom oba moduły lokalnie z włączonym uwierzytelnianiem i potwierdź, że wyszukiwanie instrumentów w terminalu działa end-to-end przez `market-data`

## 3. Bootstrap stanu Terraforma

- [ ] 3.1 `infra/bootstrap/` z providerem `azurerm` i stanem lokalnym — bez backendu zdalnego, bo to on tu powstaje
- [ ] 3.2 Grupa zasobów, konto magazynu i kontener na stan; włącz wersjonowanie blobów
- [ ] 3.3 `terraform apply` w `bootstrap/`, nazwy do `outputs.tf`
- [ ] 3.4 Dopisz `infra/**/*.tfstate*` i `infra/**/.terraform/` do `.gitignore`
- [ ] 3.5 **Zdejmij limit wydatków subskrypcji** — krok operatorski, MUST być wykonany przed trzydziestym dniem od założenia konta

## 4. Baza

- [ ] 4.1 `infra/main.tf` z backendem `azurerm` na kontenerze z grupy 3 oraz `infra/variables.tf` (region, nazwy, wersja Postgresa, adres dewelopera)
- [ ] 4.2 `azurerm_postgresql_flexible_server`: `B_Standard_B1ms`, wersja 17, `storage_mb = 32768`, `backup_retention_days = 7`, `zone = "1"`
- [ ] 4.3 Wymuś TLS na poziomie serwera
- [ ] 4.4 Utwórz obie bazy: `market_data` i `market_data_dev`
- [ ] 4.5 Przypisz administratora Entra dla serwera — droga powrotna przy błędnej konfiguracji ról
- [ ] 4.6 Reguła firewalla na adres dewelopera czytany ze zmiennej
- [ ] 4.7 Rola aplikacyjna: odczyt i zapis wyłącznie na `market_data`
- [ ] 4.8 Rola deweloperska: odczyt i zapis wyłącznie na `market_data_dev`, **bez `CONNECT` na `market_data`**
- [ ] 4.9 Rola operatorska: `SELECT` na obu bazach — konto do DBeavera
- [ ] 4.10 Odbierz `PUBLIC` domyślne prawa na obu bazach
- [ ] 4.11 **Sprawdź rozłączność ręcznie**: konto deweloperskie MUST dostać odmowę przy połączeniu z `market_data`, konto operatorskie MUST dostać odmowę przy `INSERT`. Zanotuj wynik w `review.md`

## 5. Key Vault i plan aplikacji

- [ ] 5.1 `infra/key-vault.tf`: sejf z losowym przyrostkiem w nazwie (miękkie usuwanie) i sekretami capital.com
- [ ] 5.2 `infra/app-service.tf`: plan `B1` Linux, **`worker_count = 1` z komentarzem, dlaczego nie wolno tego zmienić**, bez autoskalowania
- [ ] 5.3 Aplikacja `capital-gateway`: `always_on`, `websockets_enabled`, tożsamość `SystemAssigned`, `ip_restriction_default_action = "Deny"` z wyjątkiem na adresy wyjściowe planu czytane z zasobu
- [ ] 5.4 Aplikacja `market-data`: `always_on`, `websockets_enabled`, tożsamość `SystemAssigned`, Easy Auth z Entra ID
- [ ] 5.5 Uprawnienia odczytu sekretów dla obu tożsamości; w ustawieniach aplikacji wyłącznie odwołania `@Microsoft.KeyVault(SecretUri=...)`
- [ ] 5.6 Dopisz do reguły firewalla bazy adresy wyjściowe planu — czytane z zasobu, nigdy ręcznie
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
