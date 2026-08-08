## Why

Dodanie pary z jawną, płytką datą OD dociąga dwa razy więcej historii niż operator poprosił —
cicho, bez odmowy i bez śladu w niczym, co operator wtedy widzi.

Ujawniło to dodanie kolumny „Data since" w `Instruments`: operator dodał US100 w interwałach od
`5m` do `1W`, z datą OD 2026-01-01. Zlecenie policzyło i pobrało dokładnie to, o co poproszono —
sprawdzone w `collection_job_chunks`, każdy kawałek zaczyna się od 2026-01-01. Ale obok zlecenia,
w tym samym momencie, żywy ingest uruchomił dla tej samej pary własne, niezależne domykanie luki
(`PairIngest._close_gap` → `fill_gap`), które dla pary bez żadnej świecy sięga po stałą,
skonfigurowaną globalnie głębokość (`default_bars`, domyślnie 5000 świec) — i o `collect_from` nic
nie wie. Dla `1D`/`4h`/`1W`, gdzie 5000 świec to lata, a nie miesiące, archiwum skończyło z danymi
od 2009, 2023 i 1991 — nikt o to nie prosił, i nic tego nie powiedziało.

## What Changes

- `fill_gap` (a więc i `bars_to_close_gap`, którą woła) dla pary bez żadnej świecy MUST NOT sięgać
  dalej wstecz niż `collect_from` tej pary. Para dodana bez jawnej daty OD ma `collect_from`
  wyliczone z tej samej skonfigurowanej głębokości (`default_collect_from`), więc dla niej
  zachowanie się nie zmienia — zmienia się wyłącznie dla pary, której operator dał jawną, płytszą
  datę.
- Dwa niezależne mechanizmy dociągania wstecz (zlecenie i cichy fill) zostają nazwane wprost jako
  dwa mechanizmy, z jasną granicą, za co odpowiada który — decyzja, czy fill ma się w ogóle
  wstrzymać, gdy zlecenie już pokrywa parę, zapada w design.md, nie w tym proposalu.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `market-data-ingest`: uzupełnianie wstecz dla pary bez żadnej świecy przestaje ignorować
  `collect_from` — scenariusz „Nowo dodana para" przestaje mówić „do skonfigurowanej głębokości"
  bez zastrzeżeń, bo to nie zawsze prawda.

## Impact

**market-data**: `ingest/backfill.py` (`bars_to_close_gap`, `fill_gap` — potrzebują odczytu
`collect_from` tej pary, którego dziś nie robią), `ingest/live.py` jeśli sygnatura `_close_gap`
się zmieni, ewentualnie nowy lekki odczyt w `tracking.py` (dziś jest tylko `read_tracked`/
`read_all`, żadne nie czyta jednej pary tanio).

**Zasięg**: wyłącznie `market-data`. Terminal nie wie o `fill_gap` i nic tu nie zmienia — kolumna
„Data since", która to ujawniła, już działa poprawnie i pokazuje prawdę; to backend miał dawać
nieprawdziwe dane, nie terminal je źle czytał.

**Dane już w archiwum**: to nie jest migracja. Świece, które ten błąd już zebrał (jak w opisanym
przypadku US100), zostają — są prawdziwymi danymi z providera, tylko zebranymi bez pytania.
Operator, który chce się ich pozbyć, ma do tego `delete-archived-pair-data`.
