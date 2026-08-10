## Why

Terminal pokazuje dziś rzeczy, których operator nie potrzebuje, i nie pokazuje jednej, której
potrzebuje. Rozwinięcie instrumentu powtarza to, co mówi zakładka Data History — stan zbierania,
najnowszą świecę, pokryte przedziały — a nie odpowiada na pytanie, po które się je otwiera: ile tych
danych właściwie jest i ile miejsca zajmują. Do tego kilka drobiazgów, które osobno nie są warte
zmiany, a razem są: znacznik `forming` mówiący to, co widać na wykresie gołym okiem, kolumna wolumenu
z CFD, której nie da się uczciwie czytać, nazwy interwałów w dwóch różnych konwencjach (`MINUTE_5`
w wykresie, `5m` w Instruments), trzy puste zakładki i wszystkie daty w UTC, przeliczane w głowie.

## What Changes

- Rozwinięcie instrumentu w Instruments przestaje pokazywać stan zbierania i najnowszą świecę. Na
  ich miejsce, dla każdego interwału: liczba zebranych świec, szacowana objętość danych i moment,
  od którego dane sięgają. Ostrzeżenie o lukach w pokryciu zostaje — ale wyłącznie gdy luka
  faktycznie jest; interwał pokryty jednym ciągłym przedziałem nie dostaje żadnej wzmianki o
  pokryciu. Kasowanie pojedynczego interwału zostaje.
- Kolumna „Data since" znika z wiersza instrumentu — ta data mieszka teraz przy interwale,
  którego dotyczy.
- `market-data` zaczyna podawać przy każdej śledzonej parze liczbę zebranych świec i szacowaną
  objętość — **zmiana kontraktu**, `TrackedPairOut`.
- Wykres przestaje pokazywać znacznik `forming`.
- Wykres przestaje pokazywać wolumen — CFD nie niesie prawdziwego, więc pokazywanie go jest gorsze
  niż niepokazywanie.
- Interwały nazywają się w całym terminalu tak samo: `m1`, `m5`, `m15`, `m30`, `h1`, `h4`, `day`,
  `week`. Nazwy z drutu (`MINUTE_5`) przestają docierać na ekran.
- Zakładki `Positions`, `Orders` i `Account` znikają wraz z mechanizmem „zakładka na przyszłość".
- Każda data i oś czasu wykresu jest w `Europe/Warsaw`, z widoczną nazwą strefy.
- Pole wyboru instrumentu na wykresie dostaje ten sam rozmiar czcionki co pole interwału i przestaje
  być pogrubione (bez zmiany wymagań — sama prezentacja).

## Capabilities

### New Capabilities

Żadnych.

### Modified Capabilities

- `market-data-tracking`: śledzona para niesie liczbę zebranych świec i szacowaną objętość danych.
- `market-data-api`: odczyt listy śledzonych par podaje obie te liczby przez kontrakt.
- `terminal-data-manager`: wiersz przestaje nieść datę początku danych; rozwinięcie przestaje
  pokazywać świeżość i pełny zakres pokrycia, a zaczyna podawać objętość archiwum per interwał i
  ostrzega o pokryciu tylko wtedy, gdy w nim są luki.
- `terminal-chart`: znika oznaczanie świecy w budowie na ekranie i wolumen w odczycie spod kursora.
- `terminal-shell`: dochodzi jednolite nazewnictwo interwałów i polska strefa czasowa; znika
  zakładka oznaczona jako przygotowana na przyszłość.

## Impact

- `market-data`: `tracking.py` (zapytanie `_SELECT_STATUS`), `contract.py` (`TrackedPairOut`),
  `jobs/plan.py` (stała `ESTIMATED_BYTES_PER_CANDLE` przestaje być prywatna dla wyceny zlecenia).
  Bez migracji — obie liczby są liczone z tego, co już leży w bazie.
- `terminal`: `contract.generated.ts` (regeneracja), `data/archive.ts`, `data/types.ts`,
  `instruments/InstrumentsView.tsx`, `instruments/format.ts`, `instruments/resolutionAbbr.ts`,
  `instruments/AddInstrumentWizard.tsx`, `chart/Chart.tsx`, `grid/SymbolField.tsx`,
  `history/CollectionHistoryView.tsx`, `app/tabs.ts`, `app/ComingSoon.tsx` (znika).
- Adresy `/positions`, `/orders`, `/account` przestają istnieć — otwarcie ich trafia na stronę
  nieznanej zakładki. Zakładek nikt nie używa, więc nie jest to **BREAKING** dla nikogo poza
  zakładką w przeglądarce.
- `Bar.forming` zostaje w danych i w kontrakcie — znika tylko jego rysowanie.
