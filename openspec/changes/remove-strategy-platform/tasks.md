## 0. Przed startem

- [ ] 0.1 (odroczone decyzją operatora — konflikty z gałęzią telegrama rozwiązywane później) `feat/telegram-terminal` zmergowana i wdrożona; rebase tej gałęzi na `main`, delta `strategy-alerts` odtworzona z aktualnej głównej specyfikacji
- [x] 0.2 Za zgodą operatora, odczyt bazy `teams` na produkcji: wyzwalacze i definicje zespołów nazywające `list_strategies`, `pending_setups`, `recent_decisions`, `last_decision`; wynik i decyzja operatora zapisane tu
  - 18.10.2026: żadna rewizja żadnego zespołu (`team_revisions.definition`) i żaden wyzwalacz (`triggers.tool_name`) nie nazywa żadnego z czterech narzędzi — nie ma czego usuwać

## 1. Wydanie A — workbench

- [x] 1.1 Usunąć `strategy/`, `tests/strategy/`, `migrations/strategy/`, `alembic-strategy.ini`, `workbench/archive_client.py`, `tests/test_market_in_process.py`
- [x] 1.2 `workbench/app.py`, `config.py`, `alembic_env.py`: bez montowania `/strategy`, bez źródeł lokalnych strategii, bez `for_strategy`, bez `strategy_database_url`
- [x] 1.3 `Dockerfile`, `pyproject.toml` (`include`, opis), `.env.example`, `README.md`; komentarze w `agent/tools/registry.py`, `teams/tools/client.py`, `teams/scheduler/clock.py`
- [x] 1.4 Testy wspólne: `conftest.py`, `test_layering.py` (lista pakietów), `test_database_server_mode.py`, `test_server_mode.py`; `tests/teams/test_scheduler_triggers.py` — atrapa pod neutralną nazwą, odwołanie do ogólnego wymagania „Warunek jest czytany narzędziami serwera narzędzi”
- [x] 1.5 (czeka na telegram) Jeśli telegram wszedł: cel `strategy.setup` i jego przypisania usunięte tak, jak tamta zmiana traktuje cel bez producenta
  - 18.10.2026: przypisania `strategy.setup` nie ma (jedyne to `*`). Wiersz w `purposes` zostaje, ostatnio widziany 12:00 UTC, przed wydaniem A — cele są obserwowane, nie deklarowane, a telegram nie ma ścieżki ich usuwania
- [x] 1.6 `uv run pytest -m "not live"`, `ruff check .`, `pyright` w `modules/workbench` — zielone

## 2. Wydanie A — terminal

- [x] 2.1 Usunąć `src/strategy/**` i `src/data/contract.strategy.generated.ts`; zakładka z `src/app/tabs.ts`, reguły `.watch-*` z `index.css`
- [x] 2.2 `src/data/config.ts`, `config.test.ts`, `marketData.ts`: bez `strategyHttp`, scope'u i tożsamości strategii; `vite.config.ts` bez proxy `/strategy-api`; `scripts/contract.mjs` bez wpisu; `.env.example`, `README.md`
- [x] 2.3 `pnpm test`, `lint`, `typecheck`, `contract:check` — zielone (skill `contract-sync`)

## 3. Wydanie A — repozytorium i deploy

- [x] 3.1 `.github/workflows/deploy-vps.yml`: bez `VITE_ENTRA_SCOPE_STRATEGY` i `VITE_STRATEGY_HTTP`; `STRATEGY_DB_PASSWORD` zostaje do wydania B
- [x] 3.2 `scripts/dev.py`: `STRATEGY_*` w `RETIRED_SETTINGS`, bez łańcucha migracji, bazy lokalnej i adresu dokumentacji (lokalny kontener zachowuje starą bazę do `docker compose down -v`); w compose znika też `STRATEGY_DATABASE_POOL_SIZE`; `measure-duplication.py`; `scripts/tests/{test_dev,test_open_paths,test_pool_budget}.py`; `uv run pytest` w `scripts/`
- [x] 3.3 `CLAUDE.md` (tabela, komendy, prefiksy, klucze blokad, `ALERT_DESTINATION`), `README.md`, `docs/architecture.md`, `docs/przewodnik-po-modulach.html`, `docs/kiedy-produkcja-milczy.html`, `packages/tc-runtime/README.md`, komentarze w `infra/entra.tf` i `infra/terraform.tfvars.example`; test sufitu `CLAUDE.md` zielony
- [x] 3.4 Skille: `contract-sync`, `db-cost-check` (+ `scripts/explain.sh`), `system-review` (+ `references/`)
- [x] 3.5 Usunąć `openspec/changes/the-screen-is-mostly-refusals/`; `openspec validate --all --strict`
- [x] 3.6 PR, merge, `deploy-watch` — wydanie zdrowe, `/strategy` odpowiada 404
  - #305, `deploy-vps` zielony 18.10.2026 13:00 UTC; obraz workbencha `cd85148` nie zawiera pakietu `strategy` (z zewnątrz drzwi odpowiadają 401 przed routerem, więc dowodem jest obraz, nie kod HTTP)

## 4. Wydanie B — baza

- [x] 4.1 Potwierdzić, że ostatni nocny zrzut `strategy` jest na komputerze operatora
  - `Documents\tradingcenter-backups\strategy-20261018T023001Z.dump`, 21 MB; zadanie `tradingcenter-pull-backups` 18.10.2026 13:58, wynik 0
- [x] 4.2 `deploy/postgres/ensure-databases.sh`: `retire strategy` (`DROP DATABASE IF EXISTS … WITH (FORCE)`, `DROP ROLE IF EXISTS`) zamiast `ensure strategy`
- [x] 4.3 `deploy/docker-compose.yml` bez `STRATEGY_*`; `env.required`, `fill-github-environment.sh`, `deploy-vps.yml` bez `STRATEGY_DB_PASSWORD`; `backup.sh`, `backup-check.sh` bez `strategy`
- [x] 4.4 (zrobione w wydaniu A) `scripts/dev.py` bez `strategy` w `LOGICAL_DATABASES`
- [ ] 4.5 PR, merge, `deploy-watch`; `prod-health` — baza `strategy` nie istnieje, nocny zrzut przechodzi
- [ ] 4.6 Za zgodą operatora: `gh secret delete STRATEGY_DB_PASSWORD --env vps`

## 5. Zamknięcie

- [ ] 5.1 `git grep -i strateg` zwraca tylko `docs/archive/`, `openspec/changes/archive/` i datowane migawki w `docs/`
- [ ] 5.2 Archiwizacja zmiany; katalogi `openspec/specs/strategy-*` i `terminal-strategy-configurator` usunięte
