# Tasks — the-screen-is-mostly-refusals

## 1. Kontrakt

- [ ] 1.1 `modules/strategy/strategy/openapi.py` — dokument drukowany bez uruchamiania procesu, wzorem `polymarket_data.openapi`
- [ ] 1.2 Źródło `strategy` w `modules/terminal/scripts/contract.mjs`; `pnpm contract:generate` i `contract:check`
- [ ] 1.3 `modules/strategy/` w filtrze joba `terminal` w `checks.yml`

## 2. Tożsamość i konfiguracja

- [ ] 2.1 `infra`: delegowany zakres w `module.strategy_easy_auth` + adres w wyjściach terminala
- [ ] 2.2 `config.ts`: `strategyHttp`, `VITE_ENTRA_SCOPE_STRATEGY`, domyślny `/strategy-api`
- [ ] 2.3 Proxy w `vite.config.ts` i trasa w konfiguracji Static Web App; `.env.example` terminala

## 3. Klient

- [ ] 3.1 `src/strategy/strategyApi.ts`: katalog, obserwacje, decyzje, raporty — mapowanie typów generowanych na to, czego chcą widoki
- [ ] 3.2 Testy klienta: odmowa tożsamości odróżniona od awarii źródła, odmowa 422 niesie powód

## 4. Ekran

- [ ] 4.1 `StrategyView`: katalog wpisów i lista obserwacji z przełącznikiem aktywności
- [ ] 4.2 Lista decyzji z powodem i rodzajem odmowy widocznym bez otwierania szczegółów
- [ ] 4.3 Szczegóły decyzji: poziomy, stosunek zysku do ryzyka, odczyty i wersja parametrów
- [ ] 4.4 Dialog zakładania obserwacji z walidacją zakresów parametrów
- [ ] 4.5 Raporty backtestu: metryki z modelem kosztów, wersją parametrów i zakresem; bez akcji uruchamiającej
- [ ] 4.6 Zakładka w `tabs.ts`

## 5. Sprawdzenie

- [ ] 5.1 `pnpm test`, `lint`, `typecheck`, `contract:check`
- [ ] 5.2 `uv run pytest`, `ruff`, `pyright` w `modules/strategy` (nowy `openapi.py`)
- [ ] 5.3 `openspec validate the-screen-is-mostly-refusals --strict`
- [ ] 5.4 `terraform fmt -check`, `validate`
