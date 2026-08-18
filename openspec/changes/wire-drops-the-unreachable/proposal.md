## Why

Plan refactoru (iteracja 5) zapowiadał „usunięcie martwych pól z drutu" i wskazywał sześć
pól, których żaden konsument nie czyta. Pomiar konsumpcji się potwierdził — żadne z tych
sześciu nie ma odpowiednika camelCase w `archive.ts`, a `market-mcp` deklaruje w swoich
modelach tylko to, czego naprawdę używa. Ale **pięć z sześciu jest opublikowanym
wymaganiem**, i to takim, które robi dokładnie to, po co je napisano:

- `price_side` na świecach i na świecy w budowie — `market-data-store`, „Jedna strona ceny
  w całym archiwum": *strona ceny MUST być zapisana wprost przy danych, a nie dorozumiana,
  żeby dołożenie kiedyś drugiej strony nie zmieszało obu w jednej serii*;
- `warmup_from` — `market-data-indicators`, „Rozgrzewka jest wyliczona, jawna i niezależna
  od punktu startu": *odpowiedź MUST podawać, dokąd odczyt naprawdę sięgnął*;
- `expires_in_seconds` — `market-data-browser-access`: *dostaje poświadczenie wraz
  z informacją, jak długo jest ważne*.

Terminal ich nie czyta i to jest luka terminala, nie balast archiwum. Usunięcie ich
znaczyłoby edytowanie wymagania po to, żeby dopasować je do przeoczenia konsumenta.

Zostają dwie rzeczy, których **żadne wymaganie nie żąda**, a które kontrakt niesie:

1. **`last_fill` i model `FillOut`** (46 linii). Wymaganie „Śledzone pary są wyliczalne wraz
   ze swoim stanem" (`market-data-tracking`) wylicza, co niesie wpis pary — symbol,
   rozdzielczość, stan połączenia, najnowsza i najstarsza świeca, moment pokrycia, liczba
   świec, szacowana objętość. Ostatniego dociągnięcia nie ma na tej liście.
2. **Stan `anchored`**, którego nic nie umie wyprodukować. `warmup_kind` deklaruje
   `Literal["fixed", "decay", "anchored"]`, a katalog zna dwa rodzaje rozgrzewki —
   zmierzone uruchomieniem na 63 wpisach: **51 `fixed`, 12 `decay`, zero `anchored`**.
   Towarzyszące `anchored_at` nie jest ustawiane w module ani razu, więc na drucie jest
   zawsze `null`. Terminal niesie po swojej stronie ten sam martwy wariant.

Druga jest gorsza od zwykłego martwego pola: kontrakt obiecuje stan, do którego producent
nie może dojść, a każdy konsument musi go obsłużyć. Odczyt `anchoredAt` w terminalu
(`archive.ts`) to gałąź, która nigdy nie wykona się inaczej niż na `null`.

## What Changes

- Z `market_data/contract.py` znika `FillOut` i pole `last_fill` w `TrackedPairOut`.
  Wraz z nimi przestaje być osiągalny **cały łańcuch pod tym polem** w ingest — `_fills`,
  `last_fill()`, `fills()`, `report()`, `_record_fill` oraz hak `on_fill` w `live.py`,
  który nikt inny nie ustawia. `report()` nie ma dziś wywołującego, więc po zdjęciu pola
  z drutu nie zostaje ani jeden czytelnik tego zapisu.
- `warmup_kind` traci wariant `"anchored"`, a `IndicatorResultOut` traci `anchored_at`.
  Terminal traci ten sam wariant w `types.ts` i mapowanie w `archive.ts`.
- `FillOutcome` **zostaje** — backfill i live nadal go produkują i nadal jest tym, czym
  kończy się dociągnięcie. Zmienia się to, że nikt go już nie zapamiętuje „na potem".
- Dochodzi test tego trybu awarii: **każdy rodzaj rozgrzewki, który drut deklaruje, musi
  dać się wyprodukować przez jakiś wpis katalogu.** Bez niego ta sama rozbieżność wróci
  następnym razem, gdy katalog straci ostatni wpis jakiegoś rodzaju.

**Poza zakresem, świadomie.** Cztery pola, które terminal ignoruje, a specyfikacja ich
żąda, zostają nietknięte. Jeżeli kiedyś okaże się, że wymaganie było za szerokie, to jest
osobna decyzja o *wymaganiu*, a nie sprzątanie kontraktu — i wtedy delta specyfikacji jest
jej właściwym miejscem.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

Brak — i to jest teza tej zmiany, nie jej efekt uboczny. Obie usuwane rzeczy nie
występują w żadnym wymaganiu w `openspec/specs/`, co zostało sprawdzone dla każdej
z osobna. Wszystko, czego wymaganie żąda, zostaje na drucie.

Zmiana ma więc `skip_specs: true`. Kwalifikuje się do OpenSpeca przez **drugą kategorię**
wyzwalacza — kontrakt między modułami (`market_data/contract.py`).

## Impact

**Kod.** `market-data`: `contract.py`, `routers/pairs.py`, `ingest/supervisor.py`,
`ingest/live.py`. `terminal`: `src/data/types.ts`, `src/data/archive.ts` i wygenerowany
`src/data/contract.generated.ts`.

**Kontrakt i jego kopie.** `pnpm contract:generate` w terminalu; snapshot market-mcp
(`contract/market-data.openapi.json`) przez `uv run python scripts/contract.py check`.
`checks.yml` wciąga przy tym diffie job terminala **i** job market-mcp — obie kopie tego
schematu są sprawdzane tym samym przebiegiem.

**Czego nie dotyka.** Żadnej migracji, żadnej bazy, żadnego pliku w `infra/`, żadnego
modułu MCP poza jego snapshotem, `capital-gateway` w ogóle.

## Artefakty tej zmiany

`design.md` — **tak**: jest realna decyzja z alternatywą, która została odrzucona na
podstawie dowodu, a nie gustu — czym właściwie jest „martwe pole". `tasks.md` — **tak**,
bo praca idzie w dwóch modułach i kolejność ma znaczenie (drut przed regeneracją).
`review.md` — **do decyzji po wdrożeniu**; kandydat, bo zmiana rusza kontrakt, którego
jedyną obroną są testy dwóch konsumentów.
