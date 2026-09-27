# Tasks — the-screen-is-mostly-refusals

## 1. Kontrakt

- [x] 1.1 `modules/strategy/strategy/openapi.py` — dokument drukowany bez uruchamiania procesu, wzorem `polymarket_data.openapi`
- [x] 1.2 Źródło `strategy` w `modules/terminal/scripts/contract.mjs`; `pnpm contract:generate` i `contract:check`
- [x] 1.3 `modules/strategy/` w filtrze joba `terminal` w `checks.yml`

## 2. Tożsamość i konfiguracja

- [x] 2.1 `infra`: delegowany zakres w `module.strategy_easy_auth` + adres w wyjściach terminala
- [x] 2.2 `config.ts`: `strategyHttp`, `VITE_ENTRA_SCOPE_STRATEGY`, domyślny `/strategy-api`
- [x] 2.3 Proxy w `vite.config.ts` i trasa w konfiguracji Static Web App; `.env.example` terminala

## 3. Klient

- [x] 3.1 `src/strategy/strategyApi.ts`: katalog, obserwacje, decyzje, raporty — mapowanie typów generowanych na to, czego chcą widoki
- [x] 3.2 Testy klienta: odmowa tożsamości odróżniona od awarii źródła, odmowa 422 niesie powód

## 4. Ekran

- [x] 4.1 `StrategyView`: katalog wpisów i lista obserwacji z przełącznikiem aktywności
- [x] 4.2 Lista decyzji z powodem i rodzajem odmowy widocznym bez otwierania szczegółów
- [x] 4.3 Szczegóły decyzji: poziomy, stosunek zysku do ryzyka, odczyty i wersja parametrów — 27 września 2026: kliknięcie wiersza otwiera `DecisionDetail` (powód; dla wejścia kierunek, wejście, obrona, cel, R, ocena; zestaw parametrów z wersją i wartościami, rewizja reguły, odczyty tej świecy i cechy setupu)
- [x] 4.4 Dialog zakładania obserwacji z walidacją zakresów parametrów
- [x] 4.5 Raporty backtestu: metryki z modelem kosztów, wersją parametrów i zakresem; bez akcji uruchamiającej — 27 września 2026: `BacktestsPanel` pod decyzjami, zawężany wybraną strategią; pusty stan mówi, że przebieg to komenda (`python -m strategy.backtest --keep`), nie przycisk
- [x] 4.6 Zakładka w `tabs.ts`

## 5. Sprawdzenie

- [x] 5.1 `pnpm test`, `lint`, `typecheck`, `contract:check`
- [x] 5.2 `uv run pytest`, `ruff`, `pyright` w `modules/strategy` (nowy `openapi.py`)
- [x] 5.3 `openspec validate the-screen-is-mostly-refusals --strict`
- [x] 5.4 `terraform fmt -check`, `validate`
