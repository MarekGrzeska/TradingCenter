## Verdict

Wpis historii jednego zlecenia da się usunąć: `DELETE /jobs/{job_id}` zdejmuje zlecenie
i jego kawałki, nie rusza ani jednej świecy, i odmawia z 409, dopóki którykolwiek kawałek
jest `pending` albo `running`. W terminalu droga prowadzi wyłącznie przez dialog zlecenia,
a potwierdzenie nazywa liczbę par i kawałków oraz mówi wprost, że świece zostają.

Świadomie poza zakresem: usuwanie hurtem, usuwanie wpisów o skasowaniu danych i cofanie
usunięcia — wszystkie trzy wymienione w `design.md` jako Non-Goals, żaden nie jest
przeoczeniem. Nie ma migracji, bo schemat się nie zmienia: kawałki usuwa jawny `DELETE`
w tej samej transakcji, a nie kaskada na kluczu obcym.

Do przeczytania przez późniejszego czytelnika: dwie poprawki w
`modules/terminal/scripts/contract.mjs` nie należą do tej zdolności. Bez nich
`pnpm contract:generate` nie uruchamiało się na Windows w ogóle, a gdy już się
uruchomiło, psuło kodowanie całego wygenerowanego pliku — przystanek 3 obowiązkowej
drogi kontraktu był tam martwy.

## Verified

Uruchomione na `feat/delete-job-history-entry`, commit `151cecc`:

| Komenda | Wynik |
|---|---|
| `uv run pytest` (market-data) | `1 failed, 556 passed, 7 skipped` — porażka to `test_openapi.py::test_the_document_prints_with_no_environment_at_all`, sprawdzona jako wcześniejsza (ta sama porażka na czystym drzewie, `git stash -u`) |
| `uv run pytest -m db` | `318 passed, 7 skipped, 239 deselected` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run pyright` | `0 errors, 0 warnings, 0 informations` |
| `pnpm contract:check` (terminal) | `Contract is up to date.` |
| `pnpm test` (terminal) | `3 failed, 293 passed` — te same trzy porażki co na czystym drzewie (`284 passed` przed zmianą, 9 testów dopisanych) |
| `pnpm typecheck`, `pnpm lint` | bez uwag |

Obie serie wcześniejszych porażek są środowiskowe i widoczne wyłącznie na tej maszynie:

- `test_the_document_prints_with_no_environment_at_all` uruchamia podproces z
  `env={"PATH": "/usr/bin:/bin"}`, co na Windows zabiera `SystemRoot` i kończy się
  `WinError 10106` przy imporcie `asyncio`. Sam generator działa —
  `uv run python -m market_data.openapi` kończy się zerem i niesie nową ścieżkę `delete`.
- Trzy testy terminala porównują `toLocaleString()` z `"1,000"`, a locale tej maszyny
  drukuje `1 000`.

Żadna z nich nie dotyczy plików tej zmiany i żadna nie została „naprawiona" po drodze.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| medium | `modules/terminal/scripts/contract.mjs:65` | `execFileSync("npx", …)` — node 22 nie uruchomi `npx.cmd` bez powłoki, więc `pnpm contract:generate` kończyło się `spawnSync npx ENOENT`; przystanek 3 drogi kontraktu był na Windows niewykonalny, a `contract:check` niemożliwy do uruchomienia lokalnie | FIXED w `151cecc` — uruchamiane jest `bin/cli.js` generatora przez `process.execPath` |
| medium | `modules/terminal/scripts/contract.mjs:38` | stdout Pythona wracał w kodowaniu ANSI, więc pierwszy udany `generate` zamienił każdą półpauzę w dokumencie na `U+FFFD` — 24 linie różnicy nieopisujące żadnej zmiany kontraktu, a plik jest w repozytorium | FIXED w `151cecc` — `PYTHONIOENCODING=utf-8` i `PYTHONUTF8=1` dla tego podprocesu |
| low | `tests/test_jobs_store.py` (test dopisywany w tej zmianie) | odczyt świec liczony do `MOMENT` włącznie, a zakresy w tym module są półotwarte — test przechodził z 2 zamiast 3 świec i mylnie oskarżał `delete_job` | FIXED przed commitem `151cecc` |

Poza tym w diffie nie ma zastrzeżeń. Wyścig z runnerem — jedyne miejsce, gdzie ta operacja
mogła być naprawdę niepoprawna — jest domknięty w obie strony: `SELECT … FOR UPDATE` na
kawałkach zlecenia sprawia, że `_CLAIM_PENDING_CHUNK` (z `FOR UPDATE SKIP LOCKED`) omija
wiersze trzymane przez usuwanie, a jeśli runner był pierwszy, usuwanie czeka na jego
commit i czyta już `running`, po czym odmawia.

Zmiana kontraktu niesie jedną linię niezwiązaną z tą zdolnością: FastAPI drukuje dziś
`Unprocessable Content` tam, gdzie zatwierdzona wersja pliku miała `Unprocessable Entity`.
To zaległy dryf generatora, wyrównany przy okazji, a nie skutek nowej ścieżki.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **market-data-jobs — Wpis historii zlecenia da się usunąć** | |
| Usunięcie zlecenia zakończonego | `tests/test_jobs_store.py::test_deleting_a_settled_job_takes_its_chunks_with_it` · `tests/test_app.py::test_removing_a_settled_job_from_the_history_is_204_and_it_is_gone` |
| …a świece zostają | `tests/test_jobs_store.py::test_deleting_a_job_leaves_its_candles_and_coverage_untouched` · `tests/test_app.py::test_removing_a_job_keeps_the_candles_it_collected` |
| Usunięcie zlecenia, w którym coś trwa | `tests/test_jobs_store.py::test_deleting_a_job_with_a_pending_chunk_is_refused` · `::test_deleting_a_job_with_a_running_chunk_is_refused` · `tests/test_app.py::test_removing_a_job_with_work_still_open_is_409` |
| Usunięcie zlecenia, którego nie ma | `tests/test_jobs_store.py::test_deleting_an_unknown_job_is_refused_and_removes_nothing` · `tests/test_app.py::test_removing_an_unknown_job_is_404` |
| Pozostałe zlecenia po usunięciu | `tests/test_jobs_store.py::test_deleting_one_job_leaves_the_pairs_other_jobs_alone` |
| Usunięcie przeżywa restart | **brak testu** — patrz Gaps |
| **terminal-collection-history — Wpis dociągnięcia da się usunąć z zakładki** | |
| Operator usuwa zlecenie | `src/history/CollectionHistoryView.test.tsx::removes the job's rows once the operator confirms` |
| Potwierdzenie nazywa skutek | `src/history/CollectionHistoryView.test.tsx::says how much it covers and that the candles stay, before removing anything` |
| Usunięcie stoi przy całości, nie przy parze | `src/history/CollectionHistoryView.test.tsx::keeps removal off the pair's row, where it would promise less than it does` |
| Zlecenie w toku | `src/history/CollectionHistoryView.test.tsx::does not offer removal while the job is still running, and says why` |
| Usunięcie zawodzi | `src/history/CollectionHistoryView.test.tsx::keeps the rows and names the reason when the removal itself fails` |
| Wpis o skasowaniu danych | `src/history/CollectionHistoryView.test.tsx::opens nothing from a deletion entry, which came from no job` (test sprzed tej zmiany: z wpisu o skasowaniu nie otwiera się dialog, więc nie prowadzi z niego żadna droga do usunięcia) |
| Warstwa klienta (204, 404, 409) | `src/data/archive.test.ts::deletes a job with no body to read back` · `::marks deleting a job that is still running as a refusal` · `::marks deleting an unknown job as not-found` |

## Gaps

- **„Usunięcie przeżywa restart" nie ma własnego testu.** Trwałość jest tu własnością
  `DELETE` w zatwierdzonej transakcji, a nie kodu tej zmiany, i żaden test w tym module
  nie restartuje procesu, żeby to sprawdzić — analogiczne wymaganie „Historia zleceń
  przeżywa restart" opiera się na `interrupt_orphaned_chunks`, czyli na kodzie, który
  restart wykonuje. Zapisane jako luka, nie jako coś obejścia wartego.
- **„Usunięcie MUST NOT zostawiać po sobie wpisu w historii"** jest sprawdzone pośrednio:
  test usuwający zlecenie stwierdza, że po przeładowaniu zostaje wyłącznie wiersz drugiego
  zlecenia. Brak osobnego testu na to, że nie pojawia się wiersz typu „usunięto" — bo nic
  takiego nie istnieje na wire, więc nie ma czego udawać w atrapie archiwum.
