## Verdict

Moduł stoi na produkcji, zbiera i odpowiada. Grupy 1–9 weszły w całości; z grupy 10 zrobione
jest wdrożenie, `apply` operatora i sprawdzenie odmów, a sprawdzenie „historia czytelna
godzinę później" jest odroczone do czasu, aż jakieś wydarzenie tyle pochodzi — odhaczone jako
odroczone, nie jako zrobione.

**Przegląd diffa znalazł pięć rzeczy w tym module i wszystkie pięć są realne.** Jedna z nich
jest niewykonanym wymaganiem, nie usterką: `backfill_event` nie miał wywołania poza testami,
więc obietnica „the recent past is being filled in" — składana przez trasę REST i przez
narzędzie — nie była dotrzymywana, a dziewięćdziesiąt dni dojeżdżało dopiero przy następnym
restarcie. Naprawione, każde z testem czerwieniejącym po cofnięciu poprawki.

Czego następny czytelnik nie powinien wziąć za przeoczenie: `REST_CALLER_APPLICATION_IDS`
było puste **celowo** do czasu, aż terminal dostał podstronę (`polymarket-screen-opens-the-archive`),
i przez ten czas trasa kasująca historię nie miała żadnych drzwi — co było stanem zamierzonym
dla czynności nieodwracalnej.

## Verified

Uruchomione, nie zadeklarowane:

```
polymarket-data   uv run pytest -q      143 passed, 4 skipped
                  uv run pytest -m db   (w tym powyżej, testcontainers)
                  uv run ruff check .   All checks passed
                  uv run pyright        0 errors, 0 warnings
                  --run-live            4 passed (pomiary na dostawcy)
scripts           uv run pytest -q      120 passed
infra             terraform fmt/validate/plan/apply     0 to destroy
```

Przeciw produkcji, po wdrożeniu:

```
GET  /                    200  {"service":"polymarket-data"}
GET  /mcp   (bez tokenu)  401
GET  /events (bez tokenu) 401
obraz na App Service      ghcr.io/…/polymarket-data:<sha merge'a>
plan po apply             No changes
```

`GET /` odpowiadające 200 jest tu najmocniejszym pojedynczym sygnałem: moduł nie serwuje,
dopóki nie doprowadzi własnej bazy do rewizji swojego obrazu pod blokadą doradczą — więc 200
znaczy, że migracja przeszła i rola `app-tradingcenter-polymarket-data` ma to, co miała mieć.

Rozdział powierzchni sprawdzony na żywo, nie z konfiguracji: `allowedApplications` niesie
workbench i terminal, `TOOL_CALLER_APPLICATION_IDS` wyłącznie workbench,
`REST_CALLER_APPLICATION_IDS` wyłącznie terminal.

Narzędzia zapisujące sprawdzone przez model: agent sam objął obserwacją wydarzenia i opisał,
co śledzi.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| krytyczne | `ingest.py:165` | `backfill_event` bez wywołania poza testami. Objęcie obserwacją uruchamiało próbkowanie i nic więcej, a obie powierzchnie odpowiadały, że przeszłość jest uzupełniana. Wymaganie „Uzupełnianie MUST ruszać przy objęciu wydarzenia obserwacją" nie było spełnione. | FIXED |
| krytyczne | `store.py:90` | `upsert_event` czyścił `tracking_ended_at` bezwarunkowo, a sampler woła go co takt, żeby odświeżyć rynki. Zakończenie obserwacji w trakcie taktu było po cichu cofane. | FIXED |
| poważne | `ingest.py:81` | `close_gaps()` awaitowane w całości przed pierwszym `tick()`, a idzie sekwencyjnie po wyniku i po oknie. Restart z pełną listą obserwacji nie zbierał nic na żywo przez cały czas nadrabiania — wprost przeciw „uzupełnianie MUST NOT zagłodzić bieżącego próbkowania". | FIXED |
| poważne | `ingest.py:152` | Takt zapisywany jako zakres zerowej szerokości. Dwa takty nigdy się nie stykają, więc nic się nie scala: wiersz na wynik na minutę (ok. 368 tys. dziennie dla wydarzenia o 256 wynikach), a `is_collected` fałszywe przez 59 z 60 sekund. | FIXED |
| średnie | `ingest.py:191` | `if since >= oldest: since = max(since, oldest)` — warunek odwrócony, poprawka to gwarantowany no-op. Granica „nic starszego nie istnieje" nie ograniczała niczego i każdy restart pytał ponownie o te same puste okna. | FIXED |

Cztery z pięciu mają wspólny kształt i to jest jedyna rzecz warta wyniesienia z tego
przeglądu: **jednostka poprawna i przetestowana, okablowanie nieistniejące albo odwrócone.**
`backfill_event` był poprawny i nikt go nie wołał. Warunek granicy był napisany i wykonywał
no-op. `record_collected` scala poprawnie i dostawał argumenty, których nie da się scalić.
Testy jednostek przechodziły w każdym z tych przypadków — bo każda jednostka działała.
