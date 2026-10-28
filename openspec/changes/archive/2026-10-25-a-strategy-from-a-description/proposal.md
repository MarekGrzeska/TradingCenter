## Why

Etap 1 (`a-strategy-is-a-document`) dał silnik i zapis, ale strategię da się dziś napisać tylko ręcznie, jako JSON
wysłany pod REST, a raport przeczytać jako surowy słownik. Operator zdecydował 24.10.2026, że głównym autorem jest
agent piszący z opisu po polsku, a edytor służy do podglądu i poprawek (`docs/strategie/strategie-i-backtesty-research.html`,
sekcja „Agent i edytor”). Etap 2 daje temu ekran i narzędzia.

## What Changes

- **Narzędzia strategii w rozmowie**: opis języka, lista i odczyt strategii, walidacja, zapis rewizji, uruchomienie
  backtestu, odczyt wyniku i porównanie wyników. Wywoływane jako funkcje, tak jak narzędzia innych pakietów. Trafiają
  tylko do rozmowy: nie do zespołów, nie do katalogu alertów i nie pod `/mcp`. Agent zapisuje rewizje sam, jako
  autor `agent`. Kosztów nie podaje: bierze je z profilu instrumentu, który ustawia operator.
- **Tura wie, którą strategię operator ma otwartą**: identyfikator, rewizję i niezapisany tekst edytora. To kontekst
  tury, taki jak migawka wykresu, i nie trafia do transkryptu.
- **Zakładka Strategies w terminalu**: lista strategii, edytor tekstu dokumentu z podpowiedziami z `GET /language` i
  walidacją na żywo, streszczenie obok, historia rewizji z różnicami, formularz uruchomienia, lista uruchomień, raport
  z krzywą kapitału oraz transakcje na wykresie ceny. Po każdej turze agenta zakładka czyta stan od nowa.
- **Pakiet strategii**:
  - streszczenie dokumentu po polsku, wyprowadzone deterministycznie z samego dokumentu;
  - różnice między rewizjami liczone po ścieżkach dokumentu;
  - lista rewizji;
  - zapis, który wskazuje rewizję bazową i dostaje odmowę, gdy ktoś zapisał w międzyczasie;
  - profile kosztów per instrument;
  - zapis, kto poprosił o uruchomienie;
  - kluczowe metryki na liście uruchomień;
  - raport jako typowany model kontraktu, z dzienną krzywą kapitału (`ENGINE_VERSION` 2).
- **Wyjątek od nazw interwałów**: tekst dokumentu w edytorze jest tekstem języka i niesie jego nazwy (`HOUR_4`). Reszta
  zakładki, łącznie ze streszczeniem, używa nazw terminala (`h4`).

**Poza zakresem:** walidacja z etapu 3 (podział IS/OOS, walk-forward, siatka, Monte Carlo, Deflated Sharpe),
porównanie uruchomień na ekranie (w tym etapie porównuje tylko narzędzie), strategie w pocket, narzędzia dla zespołów,
nowe źródła serii, L4.

## Capabilities

### New Capabilities
- `strategies-tools`: powierzchnia narzędzi pakietu w rozmowie. Co każde narzędzie robi i czego odmawia, skąd biorą
  się koszty, ile uruchomień agenta może czekać i komu narzędzia nie są dawane.
- `terminal-strategies`: zakładka Strategies, czyli lista, edytor, streszczenie, historia, uruchomienia, raport i
  współpraca z panelem agenta.

### Modified Capabilities
- `strategies-documents` (z niezarchiwizowanej `a-strategy-is-a-document`, więc tylko ADDED): streszczenie, różnice,
  lista rewizji, zapis z rewizją bazową.
- `strategies-backtest` (tylko ADDED): profil kosztów instrumentu i to, kto poprosił o uruchomienie.
- `strategies-reports` (tylko ADDED): dzienna krzywa kapitału w raporcie.
- `strategies-api` (tylko ADDED): nowe trasy, typowany raport, metryki na liście uruchomień.
- `agent-chat`: tura MAY nieść otwartą strategię.
- `agent-tools`: lista zmian stanu, które agent wykonuje narzędziem, obejmuje rewizje strategii i zakolejkowane
  backtesty, a przy okazji listę obserwacji Polymarket, którą `polymarket-data-tools` już dopuszcza.
- `terminal-shell`: wyjątek dla tekstu dokumentu strategii w wymaganiu o nazwach interwałów.

## Impact

- `modules/workbench/strategies`:
  - nowe moduły: `summary.py`, `changes.py`, `costs_store.py`, `compare.py`, `mcp_app.py` i `tools/`;
  - migracja `0002`: tabela `cost_profiles` i kolumna `runs.requested_by`;
  - nowe trasy i typowany `ReportOut` w `contract.py`;
  - krzywa w `reports.py`, `ENGINE_VERSION` 2 i ponowne nagranie złotych strategii.
- `modules/workbench/workbench/app.py`: narzędzia strategii w rejestrze rozmowy, ale nie zespołów.
- `modules/workbench/agent`: `SendMessageIn.strategy` i kontekst w `turn.py`.
- `modules/terminal`:
  - zakładka w `src/strategies/`, ładowana leniwie;
  - CodeMirror 6 jako nowa zależność;
  - `VITE_STRATEGIES_HTTP` i proxy `/strategies-api`;
  - znaczniki transakcji w `Chart`;
  - `contract.strategies.generated.ts`.
- Kontrakty: nowy kontrakt strategii terminala oraz regenerowany kontrakt agenta w terminalu i w pocket (skill
  `contract-sync`).
- `.github/workflows/deploy-vps.yml` (`VITE_STRATEGIES_HTTP`), `CLAUDE.md` (tabela modułów), README pakietu.
- Bez zmian w `infra/`: lista `STRATEGIES_REST_CALLER_APPLICATION_IDS` na serwerze już ma terminal.
- `review.md` powstanie po zadaniach, bo agent dostaje narzędzia zapisujące i nową drogę do kolejki uruchomień.
