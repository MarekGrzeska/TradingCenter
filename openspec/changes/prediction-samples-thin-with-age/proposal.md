## Why

`price_samples` to największa rzecz w bazie, która rośnie bez granicy. Przegląd z 23 września 2026
(`docs/przeglad-2026-09-23.html`, ustalenie „Archiwum Polymarket rośnie bez granicy"): 21,07 mln próbek,
2,93 GB, +≈312 tys. próbek i +≈63 MB na dobę. Nic ich nie usuwa ani nie zagęszcza. Jedna próbka na minutę
na każdy wynik jest potrzebna, gdy rynek żyje, ale nikt nie czyta minutowego wykresu rynku sprzed trzech
miesięcy — a każdy odczyt, backfill i indeks płaci za wszystkie te wiersze.

Specyfikacja już to przewiduje: `polymarket-data-store`, „Archiwum nie kasuje się samo", mówi, że archiwum
MAY zagęszczać próbki starsze niż próg, że zagęszczenie MUST być odróżnialne w odczycie i MUST NOT zmieniać
ogłaszanego zakresu — i że retencja MUST być decyzją zapisaną w specyfikacji. Tej decyzji nikt dotąd nie
zapisał. Faza 1 przeglądu (#268) zmniejszyła przyrost u źródła (backfill 30 dni zamiast 90); ta zmiana
ustala, co dzieje się z tym, co już jest.

## What Changes

- **Próg i takt jako wymaganie**: próbki starsze niż **30 dni** są zagęszczane do **jednej na godzinę
  na wynik** — ostatnia próbka z każdej godziny, z jej własnym `observed_at`, więc wartość zostaje
  prawdziwą obserwacją, nie średnią.
- **Odróżnialność**: próbka zachowana przez zagęszczenie niesie znacznik (kolumna `thinned_at`), a odczyt
  historii mówi, od którego momentu takt jest godzinowy. Pytanie „czy w tej minucie było notowanie" dla
  okresu zagęszczonego odpowiada „nie wiadomo na tym takcie", nie „cisza na rynku".
- **Zakresy bez zmian**: `collected_ranges` dalej ogłasza okres jako zebrany; zagęszczenie niczego z niego
  nie wycina.
- **Wykonanie**: zadanie w pętli próbkowania raz na dobę, porcjami po wyniku, pod tym samym budżetem puli
  co próbkowanie (`sampler_db_concurrency`) — nigdy jedno zapytanie na całą tabelę.
- **Szacunek**: przy dzisiejszym tempie ≈ 60× mniej wierszy dla wszystkiego starszego niż 30 dni; tabela
  przestaje rosnąć liniowo z czasem obserwacji i rośnie z liczbą obserwowanych wyników.

Do decyzji operatora przed `/opsx:apply`: próg (30 dni) i takt (godzina). Alternatywą jest usuwanie próbek
rynków rozstrzygniętych dawniej niż N dni — tańsze, ale wbrew scenariuszowi „Rynek rozstrzygnięty przed
miesiącem", więc wymagałoby zmiany istniejącego wymagania, a nie tylko dopisania nowego.

## Capabilities

### Modified Capabilities
- `polymarket-data-store`: retencja przestaje być możliwością i staje się zapisaną decyzją.

## Impact

- `modules/workbench/polymarket_data/` (pętla, magazyn, odczyt historii), nowa migracja `polymarket`.
- Kontrakt `/polymarket` zyskuje pole mówiące o takcie historii — `contract:generate` w terminalu i pocket.
- `design.md` i `tasks.md` powstaną po decyzji o progu i takcie; dziś to propozycja do rozstrzygnięcia.
