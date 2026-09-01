## Verdict

Poprawka jest jednym zdaniem kodu i to jest jej najlepsza własność: `is_new_setup` czyta
`previous.notified_at` zamiast poprzestawać na kierunku. `previous` było już wczytywane przez
`evaluate_once` przed oceną, więc ponowienie nie kosztuje ani jednego zapytania na przebieg — to
było głównym argumentem przeciw alternatywie z osobnym znacznikiem „ostatnio zapowiedziany
kierunek", która byłaby drugą kopią stanu leżącego już w tabeli.

Reszta zmiany to droga tej jednej wartości do miejsca, w którym się o nią pyta: `notified_at`
dochodzi do `_DECISION_COLUMNS` i do `RecordedDecision`. Kontrakt REST zostaje nietknięty i to jest
sprawdzone, nie założone — `routers/decisions.py::_out` wymienia pola po nazwie, więc nowe pole na
dataclassie nie ma jak wyjść na wire, a `pnpm contract:generate` w terminalu wypisuje
`contract.strategy.generated.ts` bajt w bajt ten sam.

Jedna rzecz, której późniejszy czytelnik nie powinien wziąć za skutek uboczny: **brama podłączona
przy już stojącym wejściu zapowie je przy pierwszym przebiegu.** To wynika wprost z reguły —
poprzednia decyzja nie ma znacznika, bo nie było komu powiedzieć — i jest chciane. Bez tego świeżo
podłączony kanał milczałby aż do zmiany kierunku, co przy strategii na świecach godzinowych bywa
dobą. Ma własny test i własny scenariusz w specyfikacji, żeby nie wyglądało na przypadek.

## Verified

| Co | Wynik |
|---|---|
| `modules/strategy`: `uv run pytest -q` | **321 passed** (było 317; cztery nowe) |
| `modules/strategy`: `ruff check .` · `pyright` | All checks passed · 0 errors, 0 warnings |
| `modules/terminal`: `pnpm contract:generate` | `contract.strategy.generated.ts` bez zmian |
| `openspec validate a-refused-alert-is-tried-again --strict` | valid |

`pnpm contract:check` na tej maszynie czerwienieje na `contract.social.generated.ts`, i **nie ma to
związku z tą zmianą**: różnica jest wyłącznie w zakończeniach wierszy (checkout CRLF przeciw
generacji LF), `git diff` na tym pliku jest pusty, a CI czyta go z LF. `social-data` nie jest tu
tknięte.

**Trzy nowe testy sprawdzone na czerwono**, przez cofnięcie poprawki i ponowne uruchomienie:

```
FAILED TestWhichDecisionIsWorthSaying::test_the_same_setup_is_announced_again_when_nobody_was_told
FAILED TestThroughTheLoop::test_a_refused_setup_is_tried_again_on_the_next_bar
FAILED TestThroughTheLoop::test_a_gateway_configured_later_announces_the_setup_that_is_standing
3 failed, 12 passed
```

Czwarty — `test_a_decision_carries_whether_anybody_was_told` w `test_store.py` — czerwienieje przez
brak pola, nie przez asercję, więc nie jest liczony do tamtych trzech.

Nie uruchamiane: nic przeciw produkcji. Ta zmiana nie ma kroku operatora — żadnego `apply`, żadnego
ustawienia, żadnej migracji, bo kolumna `notified_at` istnieje od `0004_the_announced_marker`.
Zachowanie zobaczy pierwszy przebieg pętli po wdrożeniu, w którym brama odmówi.

## Findings

Przegląd własnego diffu dał jedno ustalenie i jest ono zapisane, a nie naprawione.

| Severity | Where | Finding | Status |
|---|---|---|---|
| Drobne | `strategy/alerts.py:106` | Ponowienie ma rozdzielczość jednej świecy, nie jednego przebiegu: pętla budzi się częściej, niż domykają się świece, a `evaluate_once` kończy na „already decided", zanim dojdzie do `is_new_setup`. Odmowa bramy na świecy godzinnej jest więc ponawiana za godzinę, nie za minutę. Zgodne ze specyfikacją, która mówi o przebiegu dochodzącym „do tej samej decyzji", i tańsze niż ponawianie co takt — ale nie jest to zdanie, które da się przeczytać z samego `is_new_setup`. | **z projektu, zapisane tutaj** |

Poza tym nic. W szczególności deduplikacja nie osłabła: `test_the_same_setup_on_the_next_bar_is_not_announced_again`
przechodzi bez zmiany, bo jego pierwsza wysyłka się udaje i stawia znacznik w tej samej sekundzie.

## Spec coverage

### strategy-alerts — „Ta sama decyzja nie powiadamia dwa razy" (MODIFIED)

| Requirement / Scenario | Proven by |
|---|---|
| Wejście utrzymuje się przez kolejne przebiegi | `test_alerts.py::TestWhichDecisionIsWorthSaying::test_the_same_setup_standing_from_the_previous_bar_is_not_announced`, `TestThroughTheLoop::test_the_same_setup_on_the_next_bar_is_not_announced_again` |
| Powtórzenie po nieudanej wysyłce | `TestWhichDecisionIsWorthSaying::test_the_same_setup_is_announced_again_when_nobody_was_told`, `TestThroughTheLoop::test_a_refused_setup_is_tried_again_on_the_next_bar` |
| Brama podłączona przy stojącym wejściu | `TestThroughTheLoop::test_a_gateway_configured_later_announces_the_setup_that_is_standing` |

Reguła jest sprawdzona **dwa razy i na dwóch wysokościach celowo**, bo to są dwa różne twierdzenia:
w `TestWhichDecisionIsWorthSaying` — że czysta funkcja odpowiada tak, jak mówi wymaganie;
w `TestThroughTheLoop` — że pętla naprawdę jej o to pyta i że znacznik dojeżdża do bazy. Drugie bez
pierwszego przechodziłoby przez przypadek, pierwsze bez drugiego przechodziłoby nad kodem, którego
nikt nie woła — a to była dokładnie ta usterka.

Nośnik znacznika ma własny test w warstwie, która go trzyma: `test_store.py::TestDecisions::test_a_decision_carries_whether_anybody_was_told`.

## Gaps

Brak. Trzy scenariusze wymagania mają po teście, a jedyne, czego ta zmiana nie dowodzi, to że
ponowienie zadziała przeciw prawdziwej bramie — co jest tą samą luką, jaką ma każda ścieżka do
`telegram-gateway` i jaką zamyka dopiero pierwszy przebieg na produkcji.
