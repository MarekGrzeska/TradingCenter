## Verdict

Wdrożone: `get_last_price` oddaje cenę z okresu w toku, gdy rynek handluje, i ostatnią
zamkniętą, gdy nie. Archiwum udostępnia świecę w toku odczytem HTTP — `GET
/candles/{symbol}/forming` — czytając to, co hub i tak trzyma w pamięci dla każdej
śledzonej pary, i nie zapisując niczego. Bez wskazanej rozdzielczości wybiera najdrobniejszą,
która **ma** świecę w toku; wskazaną honoruje; odpowiedź nazywa użytą.

Brak ceny bieżącej niesie jeden z trzech powodów, a rozróżnienie „rynek zamknięty" od
„rynek otwarty i cisza" jest tym, po co ta zmiana w ogóle ma enum zamiast pola
nullowalnego. Drugi z nich to awaria zbierania i jedyny, który wymaga czegoś od operatora
teraz.

Przegląd znalazł dwie rzeczy. Jedna to rozejście się implementacji z własnym projektem, w
której racja była po stronie kodu — poprawiony został projekt. Druga to prawdziwy błąd w
tym, co model dostaje do przeczytania: notatka o „rynku otwartym" padała także wtedy, gdy
nikt nie ustalił, czy rynek jest otwarty. Naprawiona, z testem. Szczegóły w Findings.

## Verified

Windows 11, Docker w tle — testy `db` market-daty weszły same.

- `cd modules/market-data && uv run pytest -q` → `1019 passed, 7 skipped` (było 1008)
- `cd modules/market-data && uv run ruff check .` → `All checks passed!`
- `cd modules/market-data && uv run pyright` → `0 errors, 0 warnings, 0 informations`
- `cd modules/market-mcp && uv run pytest -q` → `122 passed, 2 warnings` (było 117)
- `cd modules/market-mcp && uv run ruff check .` → `All checks passed!`
- `cd modules/market-mcp && uv run pyright` → `0 errors`
- `cd modules/market-mcp && uv run python scripts/contract.py check` → `Contract is up to date.`
- `cd modules/terminal && pnpm test` → `502 passed`
- `cd modules/terminal && pnpm typecheck` → czysto; `pnpm lint` → czysto
- `cd modules/terminal && pnpm contract:check` → `Contract is up to date.`
- `openspec validate last-price-is-the-forming-candle --strict` → `Change ... is valid`

Kontrakt przeszedł przez oba generatory: `contract.generated.ts` urósł o 95 linii,
`contract/market-data.openapi.json` o 132. Żaden nie był ruszany ręcznie, oba `check`
przechodzą, i żadna linia `archive.ts` ani `types.ts` się nie zmieniła — terminal ma
świecę w toku ze strumienia i nowej drogi nie czyta.

Co pokrywają nowe testy:

| Gdzie | Asercja |
|---|---|
| `test_app.py` | odczyt w trakcie sesji; wybór bez wskazania; **stojący feed minutowy nie zasłania ceny godzinowej**; rozdzielczość wskazana bije finszą; rynek zamknięty; rynek otwarty i cisza; gateway milczący ≠ rynek zamknięty; para nieśledzona |
| `test_app.py` | odczyt niczego nie utrwala; odczyt nie zostawia po sobie pokoju |
| `test_get_last_price.py` | cena z okresu w toku z notatką o ruchomym zakresie; rozdzielczość wskazana jedzie do archiwum; pominięta nie jedzie wcale; fallback po zamknięciu rynku; fallback przy stojącym zbieraniu; **milczący gateway nie jest raportowany jako otwarty rynek**; najdrobniejsza śledzona gdy nie wskazano; para nieśledzona; para bez ani jednej świecy |
| `test_refusal_shape.py` | odmowa archiwum na nowej trasie ma ten sam kształt co na starych |

**Czego nie zweryfikowano uruchomieniem.** Przebiegu przez prawdziwy gateway z otwartym
rynkiem — stos jest operatora i to on go uruchamia. Wszystko poniżej HTTP chodzi przeciw
prawdziwemu PostgreSQL-owi, ale „przy otwartej sesji US100 agent podaje cenę sprzed sekund"
jest twierdzeniem, które rozstrzyga wyłącznie żywy feed. Zadanie 4.4 zostaje niezaznaczone.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| **Low** | `openspec/.../design.md` | Projekt mówił, że trasa czyta `Room.forming` **pod uchwytem pokoju**. Implementacja czyta bez zamka, i to jest wersja poprawna: `publish` przypisuje `room.forming` między dwoma `await`-ami, więc czytelnik widzi świecę sprzed albo po, nigdy połowy — asyncio nie wywłaszcza między instrukcjami. Wzięcie zamka nie dokłada nic do tej gwarancji, a każe odczytowi HTTP przeczekać zapis do bazy i rozgłoszenie do wszystkich subskrybentów, które ten sam zamek trzymają. Poprawiony `design.md` i treść zadania 1.1, nie kod. | fixed |
| **Low** | `market_data/hub.py` | `forming()` używa `.get`, nie `_room` — i to jest jedyna rzecz, która musi tu zostać przy życiu. `_room` to `setdefault`, a `unsubscribe` sprząta wyłącznie pokoje, na które trafi; pokój utworzony przez odczyt symbolu, którego nikt nie subskrybuje, nie zostałby usunięty nigdy. Przeciek pamięci proporcjonalny do liczby symboli, o które ktokolwiek zapytał. Zabezpieczone testem na `room_count`. | observation |
| **Medium** | `market_mcp/uncertainty.py` | Zdanie dla `no_quotes` mówiło modelowi „rynek jest otwarty i archiwum nic nie dostaje". `no_quotes` odpala jednak także wtedy, gdy gateway w ogóle nie odpowiedział o sesji (`market_open: null`) — a wtedy to zdanie podaje jako fakt jedyną rzecz, której nikt nie ustalił, i robi to w module, którego cały sens polega na nazywaniu tego, czego nie wie. Znalezione przy pisaniu tego przeglądu, nie przez test. Naprawione: `no_live_price_sentence` bierze `market_open` i przy `None` mówi „nie udało się ustalić, czy rynek jest otwarty — albo giełda jest zamknięta, albo zbieranie stanęło". Test na obu gałęziach. | fixed |
| **Low** | `market_mcp/tools/_shared.py` | `PERIOD_SECONDS` przeniesione z `tools/indicators.py`, bo drugie narzędzie zaczęło go potrzebować. Ta sama tabela istnieje w `market_data/periods.py` — i ma tam zostać, bo między modułami nie ma biblioteki. Dwie kopie, jedna po każdej stronie druta, świadomie. | accepted |

## Gaps

- **Ani jedna świeca w toku nie przeszła przez prawdziwy gateway w tej zmianie.** Testy
  wkładają ją do huba tak, jak robi to `candle_sink`, co jest tą samą drogą — ale
  „ta sama droga" jest wnioskiem z lektury `app.py`, nie obserwacją.
- **`market_open` przy gatewayu w dole.** Ścieżka jest przetestowana po obu stronach druta
  (`FakeInstruments` zwracające `None` → `no_quotes`; notatka mówiąca „nie udało się
  ustalić"), ale nie zaobserwowana na prawdziwym gatewayu, który odmawia. `MarketStatus`
  cache'uje `None` jak każdą inną odpowiedź, więc przy dłuższej awarii gatewaya odpowiedź
  przez minutę nie będzie umiała powiedzieć, czy rynek handluje.
- **Jeden proces.** Świeca w toku żyje w pamięci instancji. Przy dwóch odpowiedź zależałaby
  od tego, która odebrała żądanie. Zapisane w `design.md` jako ryzyko, nie rozwiązane —
  skalowanie nie jest dziś pytaniem.

## Follow-ups

- Zadanie 4.4: przebieg ręczny przy otwartym rynku i przy zamkniętym. Do wykonania przez
  operatora.
- Rozważyć, czy `no_quotes` przy `market_open: null` nie zasługuje na własny stan w
  kontrakcie archiwum, zamiast rozgałęzienia w zdaniu po stronie market-mcp. Dziś oba
  przypadki jadą jednym słowem i rozróżnia je dopiero `market_open` obok.
