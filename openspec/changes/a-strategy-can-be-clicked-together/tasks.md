# Tasks — a-strategy-can-be-clicked-together

## 1. Język reguły

- [ ] 1.1 `strategy/rule.py`: modele węzłów (liczbowe, logiczne), `RuleDefinition` z faktami,
      parametrami, bramkami, setupami i cechami; sufity liczby faktów, węzłów i głębokości
- [ ] 1.2 Test warstwy: `rule.py` i `interpreter.py` podlegają tej samej regule co wpis
      katalogu — żadnego we/wy, żadnego zegara, wolno znać wyłącznie kontrakt

## 2. Interpreter

- [ ] 2.1 `strategy/interpreter.py`: ocena drzewa z logiką trójwartościową, przesunięcie
      ramki dla `crossed`/`previous`, kolejność bramka → setup → poziomy → cechy
- [ ] 2.2 `spec_from_rule`: rewizja jako zwykły `StrategySpec`, `evaluate` = `partial`
- [ ] 2.3 Test determinizmu: to samo drzewo i te same fakty dwukrotnie → identyczna decyzja
- [ ] 2.4 Bliźniak `baseline_ma_cross` jako reguła + test złoty decyzja po decyzji

## 3. Rewizje w bazie

- [ ] 3.1 Migracja 0003: `strategy_definitions`, `strategy_revisions`, nullowalne
      `strategy_revision_id` w `parameter_sets`, `watches`, `decisions`, `backtest_runs`
- [ ] 3.2 `store.py`: zapis definicji i rewizji (append-only), odczyt rewizji po numerze,
      zestaw parametrów związany z rewizją, decyzja niosąca rewizję
- [ ] 3.3 `resolver.py`: jedno miejsce scalające wpisy z obrazu i rewizje z bazy
- [ ] 3.4 Test: odtworzenie decyzji z jej rewizji, jej zestawu parametrów i jej snapshotu

## 4. Odmowa przy zapisie

- [ ] 4.1 `Archive.announced_catalogue()`: pełny katalog wskaźników (parametry z zakresami, linie)
- [ ] 4.2 `rule_validation.py`: wszystkie odmowy z wymagania „Definicja jest odrzucana
      w chwili zapisu", każda nazywająca to, co ją wywołało
- [ ] 4.3 Odmowa, gdy archiwum nie odpowiada — zapis nie dochodzi do skutku

## 5. Powierzchnie modułu

- [ ] 5.1 REST: `/definitions` (lista, zapis, odczyt) i `/definitions/{id}/revisions`;
      trzy testy na widok
- [ ] 5.2 `contract.py`: modele węzłów na drucie, rewizja w `DecisionOut`, `WatchOut`,
      `ParameterSetOut` i `BacktestRunOut`
- [ ] 5.3 `/mcp`: `list_strategies` widzi oba źródła, `last_decision` i `recent_decisions`
      niosą rewizję; test „zestaw wyłącznie czyta" dalej przechodzi
- [ ] 5.4 Pętla i zakładanie obserwacji: przypięcie rewizji, zgodność zestawu parametrów
      z rewizją, `check_facts_are_announced` bez zmian

## 6. Backtest

- [ ] 6.1 `--revision`, rewizja w `Report` i w `backtest_runs`; `compare` nie odmawia na
      różnych rewizjach i drukuje je
- [ ] 6.2 Test: wpis kodowy liczy się bez odczytu z bazy

## 7. Terminal

- [ ] 7.1 `pnpm contract:generate` po zmianie `strategy/contract.py`
- [ ] 7.2 `strategyApi.ts`: definicje, rewizje, mapowanie węzłów; rewizja w decyzji
- [ ] 7.3 Ekran konfiguratora: lista definicji z rewizjami, edytor drzewa z wybierakami
      z katalogu archiwum, odmowa modułu pokazana przy tym, co ją wywołało
- [ ] 7.4 Wpis z obrazu oznaczony i bez kontrolek edycji; trzy testy na widok

## 8. Domknięcie

- [ ] 8.1 `CLAUDE.md` i `modules/strategy/README.md`: wpis bywa też wierszem w tabeli —
      wskaźnik na aktualny stan, bo archiwum zmian jest przycinane
- [ ] 8.2 `checks.yml`: sprawdzić, czy `modules/strategy/` paruje z jobem terminala tak,
      jak paruje `market_data/contract.py`
- [ ] 8.3 `review.md` wg szablonu repo
