## Why

Platforma strategii w obecnej postaci — katalog wpisów, słownik węzłów reguły, pętla oceniająca,
backtest — nie jest kształtem, na którym operator chce budować dalej. Zostanie napisana od nowa,
inaczej, i nie warto, żeby nowa wersja dziedziczyła po starej kod, schemat bazy, kontrakt ani
wymagania. Dopóki stara stoi, kosztuje: pętlę co 60 s na produkcji, siedem trzymanych kontraktów,
zakładkę terminala, ~5,4 tys. linii pakietu i drugie tyle testów, które każda zmiana w workbenchu
musi przejść.

## What Changes

- **BREAKING** Pakiet `modules/workbench/strategy/` znika w całości, razem z backtestem
  (`strategy.backtest`), katalogiem (`baseline_ma_cross`), interpreterem reguł, pętlą, alertami
  i obiema powierzchniami. Workbench przestaje montować `/strategy` — REST, `/mcp` i rekord
  wołających znikają; cztery narzędzia (`list_strategies`, `pending_setups`, `recent_decisions`,
  `last_decision`) przestają docierać do rozmowy i zespołów.
- Łańcuch migracji `strategy` (`alembic-strategy.ini`, `migrations/strategy/`) i jego blokada
  8080 znikają z procesu; `workbench/archive_client.py` (droga strategii do archiwum świec)
  znika, bo nikt inny jej nie używa.
- **BREAKING** Baza `strategy` i jej rola zostają **usunięte** na produkcji i w dev — z nimi
  definicje, rewizje, obserwacje, decyzje i zapisane raporty backtestu (`backtest_runs`).
  Usunięcie robi wdrożenie, nie operator, w drugim kroku, po tym jak pierwszy wydał się zdrowo.
- **BREAKING** Terminal traci zakładkę „Strategie”, `src/strategy/**`, kontrakt
  `contract.strategy.generated.ts`, `VITE_STRATEGY_HTTP`, `VITE_ENTRA_SCOPE_STRATEGY` i proxy
  `/strategy-api`.
- Deploy, CI, skrypty i skille przestają wymieniać strategię: `STRATEGY_*` w compose,
  `STRATEGY_DB_PASSWORD` w `env.required` i w środowisku `vps`, listy baz w kopiach
  zapasowych, `dev.py`, `db-cost-check`, `system-review`, `contract-sync`.
- Otwarta zmiana `the-screen-is-mostly-refusals` (ekran strategii, 2 zadania otwarte) traci
  przedmiot i zostaje usunięta bez archiwizacji.
- `review.md` powstaje po zadaniach, nie teraz — schemat każe recenzować implementację.
- Poza zakresem: nowa platforma strategii. Przedrostek `/strategy`, nazwa bazy i klucz blokady
  są po tej zmianie wolne dla niej.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `strategy-alerts`, `strategy-backtest`, `strategy-catalogue`, `strategy-configurator`,
  `strategy-database-connection`, `strategy-liveness`, `strategy-runtime`, `strategy-tools`,
  `terminal-strategy-configurator`: każde wymaganie usunięte; katalogi specyfikacji znikają
  przy archiwizacji.
- `teams-triggers`: znika „Decyzja platformy strategii jest źródłem warunku”; ogólne czytanie
  warunku po nazwie narzędzia zostaje bez zmian.
- `telegram-gateway-delivery`: uzasadnienie „Wysłanie jest jednym aktem…” przestaje powoływać
  się na `strategy-alerts`.

## Impact

- `modules/workbench`: `strategy/`, `tests/strategy/`, `migrations/strategy/`,
  `alembic-strategy.ini`, `workbench/{app,config,alembic_env,archive_client}.py`, `Dockerfile`,
  `pyproject.toml`, `.env.example`, `README.md`, `tests/{conftest,test_layering,
  test_market_in_process,test_database_server_mode,test_server_mode}.py`, komentarze w
  `agent/tools/registry.py`, `teams/tools/client.py`, `teams/scheduler/clock.py`.
- `modules/terminal`: `src/strategy/**`, `src/app/tabs.ts`, `src/data/{config,marketData}.ts`,
  `scripts/contract.mjs`, `vite.config.ts`, `index.css`, `.env.example`, `README.md`.
- `deploy/`: `docker-compose.yml`, `env.required`, `postgres/ensure-databases.sh`,
  `scripts/{backup,backup-check,fill-github-environment}.sh`; `.github/workflows/deploy-vps.yml`.
- `scripts/`: `dev.py`, `measure-duplication.py`, `tests/{test_dev,test_open_paths,
  test_pool_budget}.py`. `.claude/skills/`, `CLAUDE.md`, `README.md`, `docs/architecture.md`,
  `packages/tc-runtime/README.md`.
- `infra/`: tylko komentarze — żadnej zmiany zasobów, więc żadnego `terraform apply`.
- Dane produkcyjne w `teams`: wyzwalacze i definicje zespołów nazywające narzędzia strategii
  przestaną działać (design.md, „Ryzyka”).
- Koliduje z niezmergowaną gałęzią `feat/telegram-terminal` (zmiana
  `telegram-bots-from-the-terminal` dotyka `strategy/alerts.py` i `strategy-alerts`) — design.md,
  „Kolejność względem telegrama”.
