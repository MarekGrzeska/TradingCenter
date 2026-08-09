## Why

Kontrakt między `market-data` a terminalem jest napisany dwa razy, ręcznie, i nic nie sprawdza, czy
obie kopie mówią to samo.

Po stronie serwera: [`contract.py`](modules/market-data/market_data/contract.py) — 20 modeli, 101
pól, z których FastAPI buduje schemat OpenAPI o 27 komponentach. Po stronie terminala:
[`archive.ts`](modules/terminal/src/data/archive.ts) — 13 interfejsów `Raw*` przepisanych z ręki
i 9 funkcji `map*`, razem około 250 linii, których jedyną treścią jest `snake_case` → `camelCase`,
ISO → epoch i rzutowanie stringów na unie.

Dziś obie kopie się zgadzają — sprawdzone pole po polu na `PairEstimateOut` ↔ `RawPairEstimate` —
więc to nie jest naprawa błędu, tylko usunięcie klasy błędów, zanim któryś wystąpi. Klasa jest
nieprzyjemna, bo cicha: zmiana nazwy pola po stronie serwera nie wywołuje niczego, co by się
zepsuło głośno. `raw.candles_written` staje się `undefined`, `undefined` przechodzi przez mapper,
i operator widzi pustą komórkę w `Data History` zamiast błędu. Nic w buildzie, w testach ani
w typach o tym nie powie — bo `Raw*` są ręcznym opisem tego, co terminal *sądzi*, że serwer
przysyła, a nie tego, co przysyła naprawdę.

Rosnąca powierzchnia to pogarsza: reworkiem doszły zlecenia, kawałki, wyceny i usunięcia, czyli
połowa dzisiejszych `Raw*`. Następne rozszerzenie kontraktu doda kolejne ręczne kopie.

## What Changes

- `market-data` zyskuje sposób na zrzucenie swojego schematu OpenAPI **bez uruchamiania serwera**.
  FastAPI buduje schemat z modeli Pydantic, więc jest on dostępny w procesie; sprawdzone, że
  `app.openapi()` działa offline i zwraca 27 komponentów, w tym 25 pól z `format: date-time`.
- Terminal zyskuje wygenerowany, **wersjonowany w repo** plik z typami tego schematu i skrypt,
  który go odtwarza. `Raw*` przestają być ręcznym opisem, a stają się aliasami do wygenerowanych
  typów.
- Rozjazd kontraktu zaczyna być wykrywany przez `tsc`, nie przez operatora. Pole usunięte albo
  przemianowane po stronie serwera przestaje się kompilować w mapperze, który go używa.
- Skrypt sprawdzający (`contract:check`) regeneruje plik i przewraca się, gdy wynik różni się od
  tego, co jest w repo — żeby zmiana kontraktu nie mogła wejść bez zaktualizowanego pliku.
- Funkcje `map*` **zostają pisane ręcznie**. Nie są przepisywaniem — robią konwersję ISO → epoch,
  której wymaga spec `terminal-market-data` („Znaczniki czasu są sprowadzone do jednej postaci"),
  i zwężają stringi do unii domenowych. To decyzje, nie transkrypcja.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

Brak. Zmiana jest narzędziowa: żadne zachowanie działającego systemu się nie zmienia — te same
odpowiedzi, te same kształty na drucie, ten sam ekran. Zmienia się wyłącznie to, skąd terminal bierze
opis kontraktu i kiedy dowiaduje się o rozjeździe. Dlatego `.openspec.yaml` niesie `skip_specs: true`,
zamiast wymyślać wymaganie po to, żeby przejść walidację.

## Impact

**market-data**: mały punkt wejścia drukujący `app.openapi()` jako JSON. Bez zmian w trasach,
modelach i odpowiedziach.

**terminal**: nowa zależność deweloperska do generowania typów, dwa skrypty w `package.json`,
wygenerowany plik w `src/data/`, oraz `archive.ts` — 13 interfejsów `Raw*` zamienionych na aliasy.
`map*`, `translateMessage`, `createArchiveSource` bez zmian w treści.

**Kolejność względem `slim-market-data-app`**: ta zmiana powinna wejść pierwsza. Rozbicie tras na
routery może niechcący ruszyć schemat OpenAPI — inne `tags`, inne `operationId`, inna kolejność —
a wygenerowany plik pod kontrolą wersji zamienia to z niewidocznego skutku ubocznego w widoczny
diff.
