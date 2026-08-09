## Why

Wszystko, co ten monorepo zbudował, działa dziś wyłącznie na jednej maszynie. `capital-gateway`
i `market-data` chodzą z terminala, `terminal` z `vite dev`, a archiwum świec leży w kontenerze bez
kopii zapasowej — `docker compose down -v` kasuje je bezpowrotnie, a zebranie trzech lat świec
minutowych dla stu instrumentów kosztuje około dwudziestu siedmiu godzin odpytywania providera.

Ta zmiana stawia całą platformę w Azure, opisaną Terraformem, i buduje mechanizm, który wdraża
każdy z modułów bez ręcznego kroku i bez przechowywanego sekretu. Dobór usług, ceny i uzasadnienie:
`docs/azure-infrastructure-proposal.html`.

Jest w tym jedna rzecz pilniejsza niż reszta. **`capital-gateway` nie ma dziś żadnego
uwierzytelniania**, a wystawia `POST /orders`, `DELETE /positions/{position_id}` i
`PUT /positions/{position_id}`. Dopóki proces stoi na `localhost`, jest to dług. W dniu pierwszego
wdrożenia staje się endpointem handlowym w internecie. Ograniczenia dostępu na poziomie App Service
są konfiguracją, a konfigurację psuje jeden błędny wpis — uwierzytelnianie w kodzie jest warunkiem,
którego nie da się przypadkiem wyłączyć.

## What Changes

### Infrastruktura opisana Terraformem

- **`infra/bootstrap/`** ze stanem lokalnym: grupa zasobów, konto magazynu i kontener na stan
  Terraforma. Uruchamiane raz, rozwiązuje problem kury i jajka.
- **`infra/`** ze stanem w Blob Storage: App Service Plan `B1` (Linux, **`worker_count = 1`, bez
  autoskalowania**), dwie aplikacje na tym planie, PostgreSQL Flexible Server, Static Web App,
  Key Vault, Application Insights, pięć reguł alertowych.
- **Baza**: `B_Standard_B1ms`, PostgreSQL 17, 32 GB, `backup_retention_days = 7`, wymuszony TLS,
  **dwie bazy logiczne** (`market_data`, `market_data_dev`) i **trzy role o rozłącznych
  uprawnieniach** — aplikacyjna, deweloperska, operatorska.
- **Sekrety**: poświadczenia capital.com w Key Vault, w ustawieniach aplikacji wyłącznie odwołanie
  `@Microsoft.KeyVault(SecretUri=...)`. Do bazy moduły łączą się tożsamością, bez hasła.
- **Sieć**: `capital-gateway` niepubliczny (`ip_restriction_default_action = "Deny"`, wyjątek dla
  adresów wyjściowych planu czytanych z zasobu), `market-data` publiczny za Easy Auth, `terminal`
  publiczny za wbudowanym logowaniem Static Web Apps.

### Automatyzacja wdrożeń

- **Federacja OIDC dla GitHub Actions** — aplikacja Entra, poświadczenie federowane, przypisanie
  roli. **W repozytorium nie ma żadnego sekretu do Azure**, nawet klucza wdrożeniowego; identyfikatory
  dzierżawy i subskrypcji idą przez `vars`, nie `secrets`.
- **Workflow wdrożeniowy** dla `capital-gateway` i `market-data`: budowa obrazu, publikacja do GHCR
  z tagiem `github.sha`, wdrożenie na App Service. Dla `terminal`: build i publikacja do Static Web
  Apps.
- **Workflow Terraforma**: `plan` na pull requestach, `apply` po scaleniu do `main`.

### Uwierzytelnianie w `capital-gateway`

- **BREAKING** — każde wywołanie tras i WebSocketa modułu wymaga poświadczenia. Bez niego moduł
  odpowiada `401`. Wyjątkiem jest wyłącznie sonda zdrowia, której potrzebuje platforma.
- **BREAKING** — w produkcji moduł nie publikuje interaktywnej dokumentacji API ani schematu
  OpenAPI (`docs_url=None`, `openapi_url=None`). Poza produkcją bez zmian — generowanie kontraktu
  z OpenAPI musi dalej działać.
- `market-data` przedstawia się gatewayowi poświadczeniem; brak konfiguracji to odmowa startu, nie
  ciche wywołanie bez uwierzytelnienia. **`terminal` nie łączy się z gatewayem wcale** — gateway ma
  być niepubliczny (sekcja 5 dokumentu infrastruktury), więc jedynym możliwym wywołującym jest
  proces po stronie serwera. Przeglądarka nie jest miejscem, w którym da się bezpiecznie trzymać
  współdzielony klucz: trafiłby do każdego zapytania widocznego w narzędziach deweloperskich.
- **`market-data` zyskuje trasę proxy po katalog instrumentów** (`GET /instruments`,
  `GET /instruments/search`, `GET /asset-classes`), przekazującą do gatewaya własnym, już
  istniejącym poświadczeniem. `terminal` przestaje wołać gatewaya bezpośrednio i woła wyłącznie
  `market-data` — ten sam moduł, z którego i tak czyta świece. Chronione tym samym Easy Auth co
  reszta tras `market-data`.

### Środowisko lokalne

- **BREAKING** — `compose.yaml` znika w całości, a wraz z nim `docker compose up -d db`. Praca
  lokalna korzysta z `market_data_dev` na serwerze w Azure. Ze `scripts/dev.sh` i `scripts/dev.ps1`
  znika obsługa kontenera z bazą; `modules/market-data/.env.example` wskazuje na Azure
  z `sslmode=require`. Każdy istniejący `.env` wymaga ręcznej aktualizacji, a dane z lokalnego
  kontenera nie są migrowane.
- **Testcontainers zostają nietknięte.** `modules/market-data/tests/conftest.py` nadal stawia własny
  PostgreSQL i nadal robi `TRUNCATE` między przypadkami — na serwerze współdzielonym skasowałoby to
  archiwum, a przy współbieżnych przebiegach w CI kasowałoby je wzajemnie. Docker przestaje być
  potrzebny do codziennej pracy i pozostaje potrzebny do `pytest`.

## Capabilities

### New Capabilities

- `capital-access-control`: kto może wywoływać `capital-gateway` i czego moduł o sobie nie ujawnia
  na produkcji.
- `market-data-database-connection`: na jakich warunkach `market-data` łączy się ze swoją bazą, gdy
  ta stoi poza maszyną modułu — szyfrowanie, tożsamość zamiast hasła, poświadczenie, które wygasa.
- `market-data-upstream-access`: czym `market-data` przedstawia się gatewayowi i co robi, gdy nie ma
  czym.

### Modified Capabilities

- `market-data-api`: dochodzą trasy proxujące katalog instrumentów do gatewaya — jedyny sposób,
  w jaki `terminal` może go teraz osiągnąć, skoro gateway jest niepubliczny.

Poza tym semantyka archiwum, strumienia, handlu i sesji z providerem się nie zmienia — te same
świece, to samo pokrycie, ta sama jedna sesja z jednym `RateGate`. Dlatego `capital-session`,
`capital-trading`, `capital-streaming` i reszta rodziny `market-data-*` zostają bez zmian.

## Impact

**Nowy katalog `infra/`**: `bootstrap/` ze stanem lokalnym oraz `main.tf`, `variables.tf`,
`resource-group.tf`, `database.tf`, `app-service.tf`, `static-web-app.tf`, `key-vault.tf`,
`github-oidc.tf`, `monitoring.tf`, `outputs.tf` ze stanem zdalnym.

**Nowe workflowy** w `.github/workflows/`: wdrożenie trzech modułów oraz `plan`/`apply` Terraforma.
Istniejący `checks.yml` bez zmian.

**capital-gateway**: warstwa uwierzytelniania przed trasami i WebSocketem, warunkowe wyłączenie
dokumentacji API, `config.py`, `.env.example`, `Dockerfile` (nowy), `README.md`, testy.

**market-data**: klient gatewaya (poświadczenie w żądaniach REST i przy zestawianiu WebSocketa),
`db.py` (TLS i tożsamość zamiast hasła), `config.py`, `.env.example`, `Dockerfile` (nowy),
`README.md`, testy. **`tests/conftest.py` bez zmian.**

**terminal**: `gatewaySource.ts` przepisany na wywołania do `market-data` zamiast do gatewaya;
`config.ts` traci `gatewayHttp` jako osobny adres. Poświadczenie do `market-data` (Easy Auth), ścieżki
API względne, konfiguracja builda pod Static Web Apps.

**Repozytorium**: `compose.yaml` usunięty, `scripts/dev.sh` i `scripts/dev.ps1` odchudzone,
`README.md` w części o uruchamianiu środowiska.

**Zależność operatorska, nie implementacyjna**: subskrypcja Azure MUST zostać przełączona na
Pay-As-You-Go przed trzydziestym dniem od założenia — inaczej limit wydatków wyłącza wszystko
i darmowy rok bazy przepada.

**Poza zakresem**: integracja z siecią wirtualną i prywatny endpoint bazy, wysoka dostępność bazy,
środowisko przejściowe (staging) — darmowy limit obejmuje 750 godzin **jednej** instancji B1ms.
