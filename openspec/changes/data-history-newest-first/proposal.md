## Why

`Data History` jest ułożona alfabetycznie po symbolu, potem po interwale, a dopiero wewnątrz jednej
pary od najnowszego. Dla operatora, który właśnie coś zlecił albo skasował, znaczy to, że jego
zdarzenie jest gdzieś w środku tabeli — pod `GOLD`, jeśli akurat dotyczyło `US100` — i trzeba go
poszukać.

Ta zakładka odpowiada przede wszystkim na pytanie „co się właśnie dzieje i co się właśnie stało".
Odpowiedź na to pytanie jest zawsze najnowszym wierszem, a układ alfabetyczny umieszcza ją
w przypadkowym miejscu.

## What Changes

- Cała `Data History` MUST być ułożona od najnowszego zdarzenia do najstarszego, jednym porządkiem
  czasu, niezależnie od instrumentu i interwału. Symbol i interwał przestają być kluczami
  sortowania.
- Wiersze pozostają per instrument i per interwał — zmienia się ich kolejność, nie to, czym są.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `terminal-collection-history`: dochodzi wymaganie o kolejności całej zakładki. Dziś spec mówi
  o kolejności tylko wewnątrz jednej pary („Wiele dociągnięć tej samej pary") i o wspólnym
  porządku czasu dla skasowań i dociągnięć („Skasowanie danych widać w historii"); o układzie
  całości nie mówi nic, a on istnieje i jest widoczny.

## Impact

**terminal**: `history/CollectionHistoryView.tsx` — funkcja `combinedEntries` i jej test.

**Koszt, który przyjmujemy świadomie**: dziś skasowanie sąsiaduje w tabeli z dociągnięciem, które
odwróciło, bo obie rzeczy dotyczą tej samej pary i para jest kluczem sortowania. Po zmianie między
nie wejdą zdarzenia innych par. To realna strata dla czytania „dlaczego ta para ma teraz płytszy
zakres" i jest nazwana w design.md wraz z tym, co ją równoważy.
