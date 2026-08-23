# Tasks — a-strategy-can-be-clicked-together

## 1. Język reguły

- [x] 1.1 `strategy/rule.py`: modele węzłów (liczbowe, logiczne), `RuleDefinition` z faktami,
      parametrami, bramkami, setupami i cechami; sufity liczby faktów, węzłów i głębokości
- [x] 1.2 Test warstwy: `rule.py` i `interpreter.py` podlegają tej samej regule co wpis
      katalogu — żadnego we/wy, żadnego zegara, wolno znać wyłącznie kontrakt

## 2. Interpreter

- [x] 2.1 `strategy/interpreter.py`: ocena drzewa z logiką trójwartościową, przesunięcie
      ramki dla `crossed`/`previous`, kolejność bramka → setup → poziomy → cechy
- [x] 2.2 `spec_from_rule`: rewizja jako zwykły `StrategySpec`, `evaluate` = `partial`
- [x] 2.3 Test determinizmu: to samo drzewo i te same fakty dwukrotnie → identyczna decyzja
- [x] 2.4 Bliźniak `baseline_ma_cross` jako reguła + test złoty decyzja po decyzji

## 3. Rewizje w bazie

- [x] 3.1 Migracja 0003: `strategy_definitions`, `strategy_revisions`, nullowalne
      `strategy_revision_id` w `parameter_sets`, `watches`, `decisions`, `backtest_runs`
- [x] 3.2 `store.py`: zapis definicji i rewizji (append-only), odczyt rewizji po numerze,
      zestaw parametrów związany z rewizją, decyzja niosąca rewizję
- [x] 3.3 `resolver.py`: jedno miejsce scalające wpisy z obrazu i rewizje z bazy
- [x] 3.4 Test: odtworzenie decyzji z jej rewizji, jej zestawu parametrów i jej snapshotu

## 4. Odmowa przy zapisie

- [x] 4.1 `Archive.announced_catalogue()`: pełny katalog wskaźników (parametry z zakresami, linie)
- [x] 4.2 `rule_validation.py`: wszystkie odmowy z wymagania „Definicja jest odrzucana
      w chwili zapisu", każda nazywająca to, co ją wywołało
- [x] 4.3 Odmowa, gdy archiwum nie odpowiada — zapis nie dochodzi do skutku

## 5. Powierzchnie modułu

- [x] 5.1 REST: `/definitions` (lista, zapis, odczyt) i `/definitions/{id}/revisions`;
      trzy testy na widok
- [x] 5.2 `contract.py`: modele węzłów na drucie, rewizja w `DecisionOut`, `WatchOut`,
      `ParameterSetOut` i `BacktestRunOut`
- [x] 5.3 `/mcp`: `list_strategies` widzi oba źródła, `last_decision` i `recent_decisions`
      niosą rewizję; test „zestaw wyłącznie czyta" dalej przechodzi
- [x] 5.4 Pętla i zakładanie obserwacji: przypięcie rewizji, zgodność zestawu parametrów
      z rewizją, `check_facts_are_announced` bez zmian

## 6. Backtest

- [x] 6.1 `--revision`, rewizja w `Report` i w `backtest_runs`; `compare` nie odmawia na
      różnych rewizjach i drukuje je
- [x] 6.2 Test: wpis kodowy liczy się bez odczytu z bazy

## 7. Terminal

- [x] 7.1 `pnpm contract:generate` po zmianie `strategy/contract.py`
- [x] 7.2 `strategyApi.ts`: definicje, rewizje, mapowanie węzłów; rewizja w decyzji
- [x] 7.3 Ekran konfiguratora: lista definicji z rewizjami, edytor drzewa z wybierakami
      z katalogu archiwum, odmowa modułu pokazana przy tym, co ją wywołało
- [x] 7.4 Wpis z obrazu oznaczony i bez kontrolek edycji; trzy testy na widok
- [ ] 7.5 Ręczna próba szwu: wyklikać regułę na działającym stacku, założyć na niej
      obserwację i odczytać decyzję z jej rewizją
      *(operatorska — wymaga uruchomionego archiwum i bazy; kontener bazy i porty są
      współdzielone między worktree. Kształty po obu stronach drutu pokryte testami,
      niepokryte są ręce operatora.)*

## 8. Domknięcie

- [x] 8.1 `CLAUDE.md` i `modules/strategy/README.md`: wpis bywa też wierszem w tabeli —
      wskaźnik na aktualny stan, bo archiwum zmian jest przycinane
- [x] 8.2 `checks.yml`: sprawdzić, czy `modules/strategy/` paruje z jobem terminala tak,
      jak paruje `market_data/contract.py` — **była luka**: filtr nie obejmował `rule.py`,
      przez które przechodzi cały słownik węzłów
- [x] 8.3 `review.md` wg szablonu repo
