# Review — wire-drops-the-unreachable

Napisany, bo ta zmiana ma własność, której jej testy nie mają: **usunięcie za dużo
z kontraktu nie zaczerwieniłoby niczego.** Nie ma testu na pole, którego nikt nie czyta —
to jest definicja tego pola. Weryfikacja jest więc argumentem, nie przebiegiem, i to ją
ten dokument zapisuje.

## Co zostało zweryfikowane i czym

| Twierdzenie | Czym sprawdzone |
|---|---|
| `warmup_kind` deklaruje wariant, którego katalog nie produkuje | uruchomienie katalogu: **51 `fixed`, 12 `decay`, 0 `anchored`** na 63 wpisach |
| `anchored_at` jest zawsze `null` | grep po module: dwa trafienia, oba to własna deklaracja pola i docstring — żadnego przypisania |
| obrona łapie oba kierunki rozjazdu | odwrócenie fixa dwukrotnie: przywrócenie `"anchored"` czerwieni `test_every_declared_kind_is_producible_by_some_entry`, zawężenie drutu do `Literal["fixed"]` czerwieni `test_every_kind_the_catalogue_produces_is_declared` |
| nikt nie czyta usuwanych pól | brak odpowiednika camelCase w `archive.ts`/`types.ts` — mapper konwertuje snake→camel, więc pole czytane musiałoby go mieć; `market-mcp` nie deklaruje żadnego z nich |
| dokument nie zmienił się poza tym, co zamierzone | regeneracja obu kopii schematu: snapshot market-mcp **2 wstawki, 91 usunięć**, wszystkie w `FillOut`, `last_fill`, `anchored_at`, `anchored` |
| trzy moduły dalej zielone | market-data 1028, market-mcp 140, terminal 912 |

## Znalezisko: własna reguła tej zmiany o mało nie zawiodła przy pierwszym użyciu

D1 mówi, że martwe jest to, czego **nie żąda wymaganie i nie czyta konsument**. Zastosowana
do `last_fill` dała „żadne wymaganie tego nie żąda" — i to była nieprawda. Wymaganie
istnieje (`market-data-ingest`, „Ingest raportuje swój postęp i porażki") i jest ostrzejsze,
niż to pole umiało spełnić.

Znalazł je **docstring testu**, który je cytował, a nie kwerenda, która miała je znaleźć.
Powód jest strukturalny, nie przypadkowy: grep szedł po `last_fill`, a specyfikacje nie
nazywają pól na drucie — mówią o zdolnościach. Grep po identyfikatorze **z zasady** nie
znajdzie wymagania.

Propozycja i design zostały poprawione osobnym commitem, zanim ruszył kod
(`0d84752`). Poprawiony powód jest mocniejszy od pierwotnego: usuwana jest **druga
implementacja spełnionego wymagania, i ta, która łamała jego klauzulę trwałości**.

Reguła na przyszłość, dopisana jako D1a: kwerendę po `openspec/specs/` robi się po
słowach, którymi specyfikacja opisuje *do czego pole służy*, nie po jego nazwie.

## Świadomie przyjęta regresja

Ewidencja zleceń pokrywa dociągnięcia zaplanowane jako zlecenie. Dociągnięcia, które
`PairIngest` domyka sam — przy starcie pary i po zerwaniu feedu — przestają być widoczne
inaczej niż w logu, czyli tam, gdzie wymaganie ich nie chce.

Decyzja operatora, świadoma: to źródło i tak nie było trwałe, więc jego usunięcie nie
oddala od zgodności, tylko przestaje udawać, że się do niej zbliża. W praktyce operator nie
traci nic, czego widział — terminal tego pola nigdy nie pokazywał. **Zamknięcie luki na
dobre znaczy zapisywać te dociągnięcia tam, gdzie leżą kawałki zleceń, i jest osobną
zmianą z migracją.**

## Czego ten przegląd nie sprawdził

Czy `IndicatorsOut.price_side` naprawdę mieści się w wymaganiu `market-data-store`, którego
scenariusz mówi o odczycie *świec*, a nie serii z nich policzonej. Zostawione jako otwarte
pytanie w `design.md` i rozstrzygnięte zachowawczo — pole zostaje. Próg po stronie
zachowawczej, bo pomyłka w drugą stronę kasuje wymaganie.
