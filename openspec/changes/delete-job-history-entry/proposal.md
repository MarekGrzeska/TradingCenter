## Why

Historia dociągania rośnie w nieskończoność i nie da się z niej niczego usunąć. Zlecenie
pomyłkowe, zlecenie na parę, której już nie ma, dziesięć prób tego samego backfillu —
wszystkie zostają w zakładce na zawsze i przykrywają to, o co zakładka jest pytana
najczęściej: co się właśnie stało. Operator ma dziś jedno narzędzie na porządek w tej
liście — skasowanie danych pary — a ono usuwa świece, czyli robi coś zupełnie innego niż
to, czego potrzebuje.

## What Changes

- Nowa operacja w archiwum: skasowanie wpisu historii jednego zlecenia. Usuwa zlecenie
  i wszystkie jego kawałki, i **nie dotyka świec** — dane zebrane przez to zlecenie
  zostają w archiwum, razem z pokryciem, które z nich wynika.
- Skasowanie jest odmawiane, dopóki zlecenie ma kawałek w toku albo oczekujący: nie da
  się usunąć zapisu pracy, którą ktoś właśnie wykonuje.
- Zakładka historii dostaje drogę do tego skasowania z dialogu zlecenia — tam, gdzie
  zlecenie widać jako całość, i tam, gdzie już stoi ponowienie. Przed skasowaniem
  operator dostaje potwierdzenie mówiące, ilu par i ilu kawałków dotyczy, oraz to, że
  świece zostają.
- Skasowanie wpisu historii **nie jest** zdarzeniem historii: nie zostawia po sobie
  wiersza „skasowano", inaczej lista rosłaby dokładnie tak, jak rośnie dziś.

## Capabilities

### New Capabilities

Brak — obie zmiany rozszerzają istniejące zdolności.

### Modified Capabilities

- `market-data-jobs`: nowe wymaganie — zlecenie da się usunąć z historii, wraz z jego
  kawałkami, bez ruszania zebranych świec; usunięcie zlecenia z pracą w toku jest
  odmawiane.
- `terminal-collection-history`: nowe wymaganie — wpis dociągnięcia da się usunąć
  z zakładki, wyłącznie przez dialog zlecenia i wyłącznie po potwierdzeniu nazywającym
  zakres skutku.

## Impact

- `modules/market-data`: `market_data/jobs/store.py` (usunięcie zlecenia i jego
  kawałków w jednej transakcji), `market_data/jobs/__init__.py`,
  `market_data/routers/jobs.py` (`DELETE /jobs/{job_id}`), testy jednostkowe i `-m db`.
- Kontrakt między modułami: nowa ścieżka w dokumencie OpenAPI archiwum, więc
  `modules/terminal` MUST przegenerować `src/data/contract.generated.ts`
  (`pnpm contract:generate`).
- `modules/terminal`: `src/data/source.ts` i `src/data/archive.ts` (nowa metoda klienta),
  `src/history/CollectionHistoryView.tsx` (akcja w dialogu, potwierdzenie, przeładowanie
  listy), testy.
- Bez migracji: klucz obcy `collection_job_chunks.job_id` nie ma `ON DELETE CASCADE`,
  więc kawałki usuwa jawnie ta sama transakcja. Schemat bazy się nie zmienia.
