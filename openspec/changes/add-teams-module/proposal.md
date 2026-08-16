## Why

Moduł `agent` prowadzi jedną rozmowę operatora z modelem: jeden prompt, jeden model, jedna
sesja. Nie ma dziś sposobu, żeby rozdzielić pracę między kilku agentów o różnych rolach,
kazać im pracować nad wspólną decyzją i sprawdzić, który układ ról daje lepsze wyniki — a to
jest właśnie eksperyment, dla którego to repozytorium powstało. Każda próba oznacza dziś
przepisanie kodu, więc żadne dwa warianty nie są porównywalne.

Ta zmiana wprowadza moduł, w którym zespół agentów jest **daną, nie kodem**: operator składa
go w terminalu, zapisuje do katalogu i uruchamia jego przebiegi, a ślad każdego przebiegu
zostaje w bazie w postaci pozwalającej zestawić warianty ze sobą.

## What Changes

- Nowy moduł `modules/teams` — piąty moduł back-endu, port 8050, własna baza logiczna
  `teams`, własna tożsamość Entra, migracje we własnym `lifespan` pod advisory lockiem.
- **Definicja zespołu jest grafem zapisanym jako dane** (JSONB), wersjonowanym append-only.
  Węzeł to agent (rola, prompt, wytyczne, model, podzbiór narzędzi), krawędź to zależność
  między agentami. Przebieg zawsze wskazuje konkretną rewizję, więc edycja zespołu nigdy nie
  zmienia historii eksperymentów.
- Definicja jest kompilowana do wykonania: każdy węzeł dostaje własną pętlę model↔narzędzia
  z ograniczeniem liczby rund, a kolejność wykonania bierze się z krawędzi.
- **Zbiorczy katalog modeli modułu**, z którego każdy agent wybiera swój model niezależnie —
  tańszy dla ról zbierających dane, droższy dla roli podejmującej decyzję.
- Narzędzia w tej fazie to **wyłącznie odczyt rynku przez `market-mcp`**, tą samą drogą co
  dzisiejszy agent czatu. Brak skonfigurowanego adresu narzędzi pozostaje stanem wspieranym.
- Ślad przebiegu: kroki agentów, wywołania narzędzi i zużycie tokenów, ze stawką kopiowaną na
  wiersz w momencie zapisu.
- Limity kosztu na przebieg i dzienne na zespół; przekroczenie zatrzymuje przebieg ze
  statusem i powodem, zamiast pozwolić mu biec dalej.
- Terminal dostaje zakładkę `teams`: canvas do składania zespołu i oglądania jego zależności,
  listę katalogu oraz podgląd przebiegu na żywo.
- Kontrakt modułu jest **generowany** do terminala ścieżką `market-data`, a nie przepisywany
  ręcznie ścieżką `agent`; `scripts/contract.mjs` przestaje być zaszyty na jedno źródło.
- Infrastruktura: App Service, rejestracja Entra, baza, sekret `teams-openai-api-key` w Key
  Vault, `deploy-teams.yml` i job w `checks.yml`.

**Poza zakresem tej zmiany, świadomie:** narzędzia tradingowe i jakikolwiek dostęp do
`capital-gateway` (faza 2), scheduler i triggery (faza 3), analityka porównawcza rewizji oraz
automatyczne układanie grafu (faza 4). Zespół w tej fazie kończy pracę **rekomendacją zapisaną
w śladzie** — nie składa zleceń.

## Capabilities

### New Capabilities
- `teams-catalogue`: czym jest definicja zespołu, jak powstaje rewizja, co moduł odrzuca przy
  zapisie i co katalog udostępnia.
- `teams-runs`: uruchomienie przebiegu, kolejność pracy agentów, ograniczenie rund, statusy,
  ślad i strumień na żywo.
- `teams-tool-access`: na jakich warunkach moduł łączy się z serwerem narzędzi, jak agent
  dostaje swój podzbiór narzędzi, czym różni się odmowa od niedostępności i dlaczego moduł nie
  trzyma kopii cudzego katalogu.
- `teams-models`: katalog modeli modułu i wybór modelu osobno dla każdego agenta.
- `teams-usage`: licznikowanie zużycia per wywołanie modelu oraz limity kosztu, które
  zatrzymują przebieg.
- `teams-database-connection`: własna baza, tożsamość zamiast hasła, TLS i samodzielna
  migracja przy starcie.
- `teams-browser-access`: kto może wołać moduł i czego moduł nie ujawnia.
- `terminal-teams`: zakładka terminala — canvas do składania zespołu i oglądania zależności,
  katalog, uruchomienie przebiegu i podgląd jego postępu.

### Modified Capabilities

Żadnej — i to jest sprawdzone, nie założone. Trzy miejsca, w których zmiany można by się
spodziewać, przewidziały ją same: `terminal-shell` wymaga, żeby rejestr zakładek był otwarty,
`market-mcp-transport` mówi o „wołającym" i nigdzie nie wylicza, kto nim jest — drugi wołający
to wpis w `allowed_applications`, a nie inne zachowanie modułu — a `terminal-identity` opisuje
poświadczenie do archiwum; dostęp do modułu agentowego opisuje `agent-browser-access`, więc
odpowiednikiem dla tej zmiany jest nowe `teams-browser-access`, nie delta do tożsamości.

## Impact

**Nowy kod:** `modules/teams/` w całości — pakiet, `pyproject.toml`, `Dockerfile`,
`.env.example`, `migrations/`, testy. Bliźniaki kopiowane z `agent`, nie importowane:
`db.py`, `migrate.py`, `schema_version.py`, `auth.py`, `provider.py`, `tools/client.py`,
`openapi.py`.

**Zmieniany kod:** `modules/terminal` — nowa zależność `@xyflow/react`, wpis w
`src/app/tabs.ts`, katalog widoków, `src/data/config.ts` o adres `VITE_TEAMS_HTTP`,
`vite.config.ts` o proxy `/teams-api`, oraz `scripts/contract.mjs`, który musi obsłużyć drugie
źródło schematu.

**Infrastruktura:** `infra/app-service.tf`, `infra/entra.tf`, `infra/database.tf`,
`infra/key-vault.tf`. Zastosowanie planu pozostaje robotą operatora, a nowa aplikacja wymaga
przebiegu `-target` przed regułami zapory, które czytają jej adresy wyjściowe. Jednorazowo,
raz na bazę, operator uruchamia `scripts/grant-schema-ownership.sql`.

**CI:** `.github/workflows/checks.yml` — filtr i job modułu, oraz rozszerzenie filtra
terminala o `modules/teams/teams/contract.py`. Nowy `.github/workflows/deploy-teams.yml`.

**Bez zmian:** `capital-gateway`, `market-data` i `market-mcp` nie zmieniają ani wiersza kodu.
`market-mcp` zyskuje drugiego wołającego, co jest wpisem w `allowed_applications`, a nie
zmianą jego zachowania.
