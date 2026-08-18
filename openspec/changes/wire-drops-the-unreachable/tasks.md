## 1. Drut traci ostatnie dociągnięcie

- [ ] 1.1 `market_data/contract.py`: usunąć model `FillOut` i pole `last_fill`
      w `TrackedPairOut`
- [ ] 1.2 `market_data/routers/pairs.py`: przestać wypełniać to pole i przestać
      importować `FillOut`
- [ ] 1.3 `market_data/ingest/supervisor.py`: usunąć `_fills`, `last_fill()`, `fills()`,
      `report()` i `_record_fill` — po 1.2 nie ma ich czytelnika
- [ ] 1.4 `market_data/ingest/live.py`: usunąć hak `on_fill` i jego dwa wywołania;
      `FillOutcome` zostaje, bo `_close_gap()` nadal nim odpowiada
- [ ] 1.5 testy market-data: `tests/test_pairs.py` traci trzy asercje o `last_fill`,
      `tests/fakes.py` traci `FakeIngest.last_fill`, `tests/test_ingest.py:1021` traci
      odczyt zapamiętanego dociągnięcia

## 2. Drut traci stan, którego nikt nie umie osiągnąć

- [ ] 2.1 `market_data/contract.py`: `warmup_kind` bez `"anchored"`,
      `IndicatorResultOut` bez `anchored_at`, opisy obu pól bez wzmianki o kotwicy
- [ ] 2.2 test w market-data: zbiór wariantów `warmup_kind` na drucie równy zbiorowi
      `warmup.kind` w katalogu — czerwony przy różnicy w obie strony (design.md, D3)
- [ ] 2.3 sprawdzić, że test czerwienieje na kodzie sprzed 2.1

## 3. Konsumenci

- [ ] 3.1 terminal: `pnpm contract:generate`, potem `src/data/types.ts`
      (`IndicatorWarmupKind` bez `"anchored"`, `IndicatorResult` bez `anchoredAt`)
      i `src/data/archive.ts` (mapowanie `anchored_at`)
- [ ] 3.2 terminal: fixture'y w `src/data/archive.test.ts` tracą pola, których wire
      już nie niesie
- [ ] 3.3 market-mcp: `uv run python scripts/contract.py check`, a gdy czerwony —
      zregenerować snapshot

## 4. Domknięcie

- [ ] 4.1 `uv run pytest`, `ruff`, `pyright` w market-data
- [ ] 4.2 `pnpm contract:check`, `pnpm lint`, `pnpm typecheck`, `pnpm test` w terminalu
- [ ] 4.3 `uv run pytest` w market-mcp
- [ ] 4.4 zdecydować o `review.md` (proposal.md, „Artefakty tej zmiany")
