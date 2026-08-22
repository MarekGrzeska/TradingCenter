# A strategy is a catalogue entry

## Why

Stack ma dziś wszystkie surowce systemu transakcyjnego — archiwum świec z indykatorami,
zespoły agentów z limitami, konto demo za bezpiecznikiem — ale nie ma miejsca, któremu
wolno powiedzieć „jest setup" i uzasadnić dlaczego. Market-data ma zakaz decydowania
(słuszny), agent w workbenchu nie jest deterministyczny (nieusuwalnie). Zamiast budować
osobny „system SMC", wprowadzamy moduł-platformę, w którym strategia jest wpisem
katalogu — tym samym wzorcem, którym market-data rozwiązał indykatory: wspólny kontrakt
wpisu, wspólna maszyneria wokół, dodanie kolejnej strategii nie dotyka maszynerii.

## What Changes

- Nowy moduł `modules/strategy`: własny proces (port 8080), własna baza logiczna
  `strategy` w tym samym kontenerze dev, migracje we własnym lifespanie pod advisory
  lockiem — wzorzec polymarket-data, bez odstępstw.
- Katalog strategii: wpis deklaruje fakty (indykatory market-data + rozdzielczości
  + parametry), własne parametry z zakresami i czystą funkcję
  `evaluate(fakty, parametry) -> Decision` — bez I/O i bez zegara. Pierwszy wpis to
  celowo banalna strategia odniesienia (baseline) na istniejących indykatorach; SMC
  wchodzi jako drugi wpis i MUST NOT wymagać zmian w runtime.
- Runtime platformy: pętla wyłącznie na domkniętych świecach, pobieranie faktów
  z market-data po REST (jedyne I/O), wspólne bramki (pokrycie danych, limity strat
  w R), zapis każdej decyzji z powodem i snapshotem wejścia, tryb shadow — wiele
  strategii równolegle, żadna nie dotyka konta.
- Read-only powierzchnia MCP (`/mcp`, jak market-data i polymarket-data):
  m.in. `pending_setups` — pole liczbowe, na którym trigger workbencha budzi team;
  moduł niczego nie wykonuje na koncie, wykonanie zostaje przy teamach i TradeGuard.
- Backtest wewnątrz modułu: sterownik odtwarzania i symulator kosztów wołają to samo
  `evaluate()` co pętla live; wynik przypisany do wersji parametrów, porównywalny
  między strategiami na tych samych danych.
- Poza zakresem: nowe indykatory SMC w market-data (zwykła ścieżka branch–testy–PR,
  bez zmiany wymagań), zmiany w terminalu, faza aktywna na demo (osobna decyzja po
  zmierzonym backteście).

## Capabilities

### New Capabilities

- `strategy-catalogue`: kontrakt wpisu strategii — deklaracja faktów, parametry
  z zakresami, czysta `evaluate`, kształt `Decision`; baseline przed SMC.
- `strategy-runtime`: pętla na domkniętych świecach, fakty z market-data, wspólne
  bramki, zapis decyzji z powodem, tryb shadow, odmowy startu (baza, konfiguracja).
- `strategy-tools`: powierzchnia MCP tylko-do-odczytu; `pending_setups` jako hak dla
  triggerów workbencha; tożsamość wołającego jak w pozostałych powierzchniach.
- `strategy-backtest`: odtwarzanie świeca po świecy przez to samo `evaluate`, model
  kosztów, walk-forward, metryki i atrybucja po cechach decyzji.
- `strategy-database-connection`: identity albo loopback, nigdy oba i nigdy żadne —
  ta sama reguła, którą mają pozostałe schematy.

### Modified Capabilities

<!-- brak — żadne istniejące wymaganie się nie zmienia; workbench-triggers i market-data
     są konsumowane po istniejących kontraktach -->

## Impact

- Nowy katalog `modules/strategy` (FastAPI + uv, editable `tc-runtime`/`tc-mcp-kit`).
- `scripts/dev.py`: wiersz w `SERVICES` (port 8080), `strategy` w `LOGICAL_DATABASES`,
  wpis w `MIGRATION_CHAINS`; `scripts/grant-schema-ownership.sql` raz na nową bazę.
- CI: job modułu w `checks.yml`; deploy `deploy-strategy.yml` z `deploy_probe.py`;
  `infra/`: App Service + tożsamość zarządzana + wpis modułu do `allowed_applications`
  market-data (konsument REST) — stąd ta zmiana jest OpenSpec także kategorią infra.
- Workbench i market-data: bez zmian w kodzie; nowy moduł jest tylko ich klientem.

Artefakty: design.md i tasks.md powstają (decyzje o kontrakcie i kolejność budowy są
treścią tej zmiany); review.md — na zamknięcie, po implementacji, wg szablonu repo.
