## Why

Reguła „bez wspólnej biblioteki" (`docs/architecture.md`, „Why no shared library") kosztuje
dziś **~959 linii ręcznie utrzymywanej kopii** w modułach Pythona — i płacimy tę cenę
błędami, nie tylko objętością. Audyt z 18 sierpnia 2026 wskazał cztery klasy dryfu, z
których każda jest tym samym zdarzeniem: poprawka ląduje w jednej kopii i nigdy nie dociera
do drugiej. Najdroższa z nich siedziała na ścieżce zleceń — retry `session-gone` naprawiony
w `teams` 17 sierpnia, nieobecny w `agent`, który woła to samo `trading-mcp`.

Reguła powstała z dobrego powodu i ten powód zostaje uszanowany: moduł ma dawać się wdrożyć,
przetestować i skasować niezależnie. Zmienia się mechanizm, nie cel — pakiet jest
zapiekany w obraz przy buildzie, więc niezależność wdrożenia pozostaje nietknięta, a znika
wyłącznie ręczny transport poprawek.

## What Changes

- **BREAKING dla reguły architektury, nie dla żadnego kontraktu.** Repozytorium przestaje
  zakazywać współdzielenia kodu źródłowego **w czasie builda**. Granice runtime — kontrakt
  HTTP/MCP, osobne bazy, osobne tożsamości, imienne listy wywołujących — nie zmieniają się
  ani o milimetr. `docs/architecture.md` i `CLAUDE.md` dostają nową regułę w miejsce starej,
  z zapisanym powodem i warunkami.
- Powstają **dwa** pakiety pod `packages/`, wyciągnięte z istniejących najlepszych kopii i
  brane przez konsumentów jako zależność ścieżkowa (`[tool.uv.sources]`), nie przez uv
  workspace — patrz `design.md`, D3:
  - `packages/tc-runtime` — `db.py` (advisory lock z kluczem jako parametrem zamiast stałej
    per moduł), `migrate.py`, `schema_version.py`, `auth.py` (odczyt principala z Easy Auth),
    `routers/models.py`, middleware tożsamości wołającego dla modułów MCP oraz jedna
    implementacja `_detail` ze spłaszczaniem listy walidacyjnej.
  - `packages/tc-openai` — `provider.py` z dwoma wariantami wejścia: historia rozmowy
    (`agent`) i briefing (`teams`).
- **`tc-mcp-kit` z planu nie powstaje.** Pomiar pokazał, że poza jednym plikiem rusztowanie
  MCP nie jest kopią, tylko trzema plikami, które różnią się, bo różnią się moduły — patrz
  `design.md`, decyzja D1.
- `checks.yml` dostaje job `packages`: zmiana w `packages/` odpala testy **wszystkich**
  modułów zależnych, a nie tylko tego, którego dotyczy diff.
- Dockerfile'e modułów zależnych kopiują `packages/` przed `uv sync`, więc obraz nadal
  zawiera wszystko, czego potrzebuje, i deployuje się osobno.

**Poza zakresem, świadomie.** Usunięcie martwego balastu, które plan iteracji 1 wiązał z tą
zmianą (transport `stdio` w market-mcp, `teams_scope` z zależnością `azure-identity`, zasoby
MCP bez konsumenta, `provider_params`, zapasowe klucze `CAPITAL_*_SECONDARY`), idzie osobną
zmianą. Powód: usunięcie `stdio` kasuje **opublikowane wymaganie** „Dwa transporty, jeden
zestaw narzędzi" z `market-mcp-transport`, a z pakietami nie ma wspólnego nic poza terminem.
Dwie zmiany czyta się i wycofuje osobno, a od 18 sierpnia 2026 propozycja jest tania.

## Capabilities

### New Capabilities

Brak. Ta zmiana nie dodaje modułom żadnego zachowania.

### Modified Capabilities

Brak. Żadne wymaganie w `openspec/specs/` nie zmienia się: przeniesienie kodu do pakietu
budowanego razem z modułem nie zmienia niczego, co moduł robi, publikuje ani czego odmawia.
Testy każdego modułu przechodzą przed i po, bez zmiany treści — to jest kryterium akceptacji
tej zmiany, nie skutek uboczny.

Zmiana ma więc `skip_specs: true` w `.openspec.yaml`. Kwalifikuje się do OpenSpeca przez
**czwartą kategorię** wyzwalacza dodaną 18 sierpnia 2026 — regułę architektoniczną, którą
`CLAUDE.md` nazywa nośną (`openspec/config.yaml`) — i to jest dokładnie ten przypadek, dla
którego tę kategorię dopisano: zmiana bez delty specyfikacji, a najbardziej konsekwentna
architektonicznie w planie.

## Impact

**Kod.** `agent`, `teams`, `market-data` (`db.py`, `migrate.py`, `schema_version.py`,
`auth.py`, `routers/models.py`, `provider.py`); `market-mcp`, `teams-mcp`, `trading-mcp`
(`network_identity.py`, helper `_detail`). Nowy katalog `packages/`; `[tool.uv.sources]` w
`pyproject.toml` każdego konsumenta.

**Build i CI.** Siedem Dockerfile'ów modułów Pythona; `checks.yml` (nowy job `packages` i
filtr ścieżek dla niego); nowy `.dockerignore` w katalogu głównym; `deploy-*.yml` każdego
konsumenta.

*Poprawione przy wdrożeniu grupy 1.* Stało tu, że żaden `deploy-*.yml` się nie zmienia.
Nieprawda: zależność ścieżkowa prowadzi poza katalog modułu, więc kontekst builda musi być
katalogiem głównym repozytorium (`context: .` plus `file:`), a bez `.dockerignore`
kontekstem stałoby się każde `.venv` i `node_modules` w drzewie. Szczegóły w `design.md`, D3.

**Dokumentacja.** `docs/architecture.md` („Why no shared library" → nowa reguła z warunkami),
`CLAUDE.md` (nagłówek o braku wspólnej biblioteki, sekcja o modułach), README modułów, które
tłumaczą duplikację regułą.

**Czego nie dotyka.** Żadnego `contract.py`, żadnego DTO na drucie, żadnej migracji, żadnego
pliku w `infra/`, żadnej bazy. Terminal nie jest ruszany w ogóle.

## Artefakty tej zmiany

`design.md` — **tak**, jest realna decyzja z alternatywami: ile pakietów i według jakiego
progu dzielimy kod. `tasks.md` — **tak**, zmiana jest wielotygodniowa i idzie modułami.
`review.md` — **do decyzji po wdrożeniu**; od 18 sierpnia 2026 jest opcjonalny
(`openspec/config.yaml`, `rules.review`), a ta zmiana jest kandydatem na jeden z niewielu,
które go zasługują: przenosi kod, którego jedynym dowodem poprawności są testy siedmiu
modułów.
