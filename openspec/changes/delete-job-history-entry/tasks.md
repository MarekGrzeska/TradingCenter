## 1. Archiwum: usunięcie zlecenia

- [ ] 1.1 `market_data/jobs/store.py`: wyjątek `JobStillRunning` obok `UnknownJob`
- [ ] 1.2 `market_data/jobs/store.py`: `delete_job(conn, job_id)` — jedna transakcja,
      kawałki zlecenia wybrane `FOR UPDATE`, odmowa gdy któryś jest `pending` albo
      `running`, `UnknownJob` dla nieznanego id, jawny `DELETE` kawałków przed zleceniem
- [ ] 1.3 `market_data/jobs/__init__.py`: `delete_job` i `JobStillRunning` w imporcie i `__all__`
- [ ] 1.4 `market_data/routers/jobs.py`: `DELETE /jobs/{job_id}`, `status_code=204`,
      `responses` z 404 i 409, opis mówiący, że świece zostają w archiwum

## 2. Testy archiwum

- [ ] 2.1 `tests/test_jobs_store.py`: usunięcie zlecenia zakończonego usuwa je wraz z kawałkami
- [ ] 2.2 `tests/test_jobs_store.py`: odmowa `JobStillRunning` dla zlecenia z kawałkiem
      `pending` i osobno z kawałkiem `running`; zlecenie i kawałki zostają nietknięte
- [ ] 2.3 `tests/test_jobs_store.py`: `UnknownJob` dla nieznanego id, nic innego nie ubywa
- [ ] 2.4 `-m db`: świece i pokrycie pary bez zmian po usunięciu zlecenia, które je zebrało
- [ ] 2.5 `-m db`: usunięcie jednego z kilku zleceń tej samej pary zostawia pozostałe
      odczytywalne z tym samym wynikiem
- [ ] 2.6 test routera: 204 dla usunięcia, 404 dla nieznanego id, 409 dla zlecenia w toku
- [ ] 2.7 `uv run pytest`, `uv run pytest -m db`, `uv run ruff check .`, `uv run pyright`

## 3. Kontrakt

- [ ] 3.1 `modules/terminal`: `pnpm contract:generate`, `src/data/contract.generated.ts`
      niesie nową ścieżkę (plik nigdy nie edytowany ręcznie)
- [ ] 3.2 `pnpm contract:check` przechodzi

## 4. Terminal: klient

- [ ] 4.1 `src/data/source.ts`: `deleteJob(jobId: number, signal: AbortSignal): Promise<void>`
      w `ArchiveAdmin`
- [ ] 4.2 `src/data/archive.ts`: `deleteJob` przez `http.send` z `method: "DELETE"`
      (odpowiedź bez treści, więc nie `http.json`)
- [ ] 4.3 `src/data/archive.test.ts`: udane usunięcie, 404 → `not-found`, 409 → `refused`

## 5. Terminal: zakładka

- [ ] 5.1 `src/history/CollectionHistoryView.tsx`: przycisk „Remove from history" w treści
      dialogu zlecenia, tylko gdy żadna para zlecenia nie jest `running`
- [ ] 5.2 Drugi `ConfirmDialog` (`tone="danger"`) z potwierdzeniem nazywającym liczbę par
      i kawałków oraz stwierdzającym, że zebrane świece zostają w archiwum
- [ ] 5.3 Po udanym usunięciu: `onChanged()` i zamknięcie dialogu; po nieudanym — dialog
      zostaje z nazwaną przyczyną, wiersze na miejscu
- [ ] 5.4 Przy zleceniu w toku dialog mówi, dlaczego usunięcie jest niedostępne
- [ ] 5.5 `src/history/CollectionHistoryView.test.tsx`: usunięcie znika wiersze zlecenia,
      potwierdzenie niesie liczby i zdanie o świecach, brak przycisku przy wierszu pary,
      zlecenie w toku bez usunięcia, nieudane usunięcie zostawia wiersze
- [ ] 5.6 `pnpm test`, `pnpm lint`, `pnpm typecheck`

## 6. Domknięcie

- [ ] 6.1 `openspec validate delete-job-history-entry --strict`
- [ ] 6.2 `review.md`
