## Why

Operator 25.10.2026 chce mieć backtesty na osobnym ekranie, z możliwością zestawienia uruchomień różnych strategii.
W zakładce Strategies formularz, lista uruchomień i raport stały pod edytorem jednej strategii, przez co ekran pisania był
długi, a uruchomień dwóch strategii nie dało się zobaczyć razem.

## What Changes

- Nowa zakładka **Backtests** w grupie Trading: wybór strategii (albo „wszystkie”), formularz uruchomienia wybranej
  strategii, lista uruchomień z nazwą strategii, gdy pokazuje wszystkie, i raport wybranego uruchomienia.
- Zakładka Strategies traci formularz, listę i raport. Zostaje pisanie, czat, streszczenie i historia rewizji, plus odnośnik
  „Backtesty tej strategii”, który otwiera zakładkę Backtests z tą strategią.
- Wymagania formularza, listy i raportu się nie zmieniają, zmienia się tylko miejsce, w którym stoją.

## Capabilities

### New Capabilities
Brak.

### Modified Capabilities
- `terminal-strategies`: backtesty mają własną zakładkę.

## Impact

- `modules/terminal`: `BacktestsView`, wpis w `app/tabs.ts`, `RunsPanel` z kolumną strategii, `runs(null)` w API.
  Kontrakt bez zmian: `GET /runs` bez `strategy_id` już zwraca wszystkie.
- `design.md` i `review.md` pominięte: zmiana układu ekranu bez nowego kontraktu ani danych.
