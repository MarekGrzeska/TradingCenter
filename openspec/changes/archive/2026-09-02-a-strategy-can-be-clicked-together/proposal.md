# A strategy can be clicked together

## Why

`a-strategy-is-a-catalogue-entry` postawiło platformę i podjęło decyzję nr 1: **wpis
strategii jest kodem w obrazie, w bazie są tylko parametry**. Ta zmiana odwraca jej połowę
i robi to jawnie, bo cicha rozbieżność między specyfikacją a ekranem jest najgorszym
z wyjść.

Argument tamtej decyzji brzmiał: strategia jako dane wymagałaby interpretera, a interpreter
i tak jest kodem do wdrożenia. Jest — **raz**. Tamten rachunek policzył koszt interpretera
jako koszt na strategię, podczas gdy kosztem na strategię jest to, co zostało wybrane:
każda nowa reguła to gałąź, review i wdrożenie. Przy pierwszej strategii to była cena
uczciwa. Przy dziesiątej odmianie tego samego pomysłu — z innym progiem, innym okresem,
innym filtrem reżimu — jest to podatek płacony za każdym razem, gdy operator chce sprawdzić
wariant.

Drugi argument tamtej decyzji był mocniejszy i wymaga odpowiedzi, nie przemilczenia:
**strategia bez przejrzanego kodu nie powinna istnieć.** Wyklikana reguła nigdy nie
przechodzi review, więc review zastępują cztery rzeczy naraz, i wszystkie cztery są
przedmiotem tej zmiany:

1. reguła jest totalnym drzewem wyrażeń bez efektów ubocznych — nie umie zrobić nic poza
   odpowiedzeniem na fakty, których sama nie pobiera;
2. definicja jest odrzucana w chwili zapisu, wzorem definicji zespołów, a nie przy
   pierwszej świecy;
3. moduł nadal nie ma drogi do konta — decyduje, nie wykonuje, i test nad całym pakietem
   dalej tego pilnuje;
4. wyklikana strategia musi pobić `baseline_ma_cross` w backteście na tych samych danych
   i kosztach, zanim ktokolwiek na niej cokolwiek zbuduje.

## What Changes

- **Reguła jako dane: typowane drzewo wyrażeń w JSON, bez składni tekstowej.** Zamknięty
  słownik węzłów (`const`, `param`, `fact`, `bar`, arytmetyka, porównania, logika trójwarto-
  ściowa, `crossed`, `previous`), jedna gramatyka w dwóch użyciach — warunek i poziom. Bez
  pętli, bez zmiennych, bez funkcji użytkownika, z sufitami na liczbę węzłów i głębokość.
  Nie parser, nie DSL: konfigurator składa drzewo, więc klasa błędów składniowych nie
  istnieje.
- **Interpreter jest `evaluate`.** Wyklikana strategia nie jest nowym bytem obok
  `StrategySpec` — jest `StrategySpec` zbudowanym z rewizji, którego `evaluate` to
  `partial(interpret, rule)`. Pętla, bramki, zapis decyzji i backtest nie zmieniają się.
  Propagacja braku odczytu (`None`) staje się własnością interpretera zamiast obowiązkiem
  autora wpisu.
- **Rewizje strategii obok wersji parametrów.** Nowe tabele `strategy_definitions`
  i `strategy_revisions` (rewizja niezmienna, wzorem `team_revisions`). Zestaw parametrów
  wiąże się z rewizją, nie ze strategią. Decyzja, obserwacja i przebieg backtestu niosą
  rewizję, którą powstały.
- **Odmowa przy zapisie.** Katalog wskaźników archiwum — który już ogłasza parametry
  z `min`/`max` i nazwy linii — jest źródłem tego, co w ogóle da się wyklikać. Definicja
  nazywająca nieogłoszony wskaźnik, nieistniejącą linię, parametr spoza zakresu albo zakres
  własnego parametru szerszy niż zakres wskaźnika zostaje odrzucona w chwili zapisu.
  Sprawdzenie przy zakładaniu obserwacji **zostaje** — katalog archiwum może się zmienić
  między zapisem a uruchomieniem.
- **`baseline_ma_cross` zostaje kodem** i dostaje bliźniaka: tę samą regułę wyrażoną jako
  drzewo, spiętą testem złotym. To jedyny uczciwy test wyrazistości i poprawności
  interpretera, a podłoga do bicia, którą można przestawić klikaniem, nie jest podłogą.
- **Backtest nad rewizją z bazy**: `--revision`, rewizja w raporcie i w `backtest_runs`,
  porównanie dwóch rewizji jednej definicji jako zamierzone użycie. Wpis kodowy dalej
  liczy się bez odczytu z bazy.
- **Konfigurator w terminalu**: lista definicji z rewizjami, edytor drzewa oparty na
  katalogu wskaźników, podgląd odmowy z modułu.
- Poza zakresem: wykonanie na koncie (niezmiennie), strategie tickowe i portfelowe,
  automatyczne strojenie parametrów, import definicji z pliku.

## Capabilities

### New Capabilities

- `strategy-configurator`: reguła jako dane — słownik węzłów, czystość i totalność
  interpretera, odmowa przy zapisie, niezmienne rewizje, wpis kodowy obok wyklikanego.
- `terminal-strategy-configurator`: ekran, na którym reguła powstaje — z zakresów, które
  ogłasza archiwum, i z odmową modułu pokazaną tam, gdzie powstała.

### Modified Capabilities

- `strategy-catalogue`: wpis pochodzi z obrazu **albo** z zapisanej rewizji; oba spełniają
  ten sam kontrakt. Czystość oceny obejmuje interpreter. Decyzja niesie rewizję reguły obok
  wersji parametrów.
- `strategy-runtime`: odtworzenie zapisanej oceny wymaga rewizji, pod którą zapadła.
- `strategy-backtest`: raport nazywa rewizję reguły obok kosztów, parametrów i zakresu.

## Impact

- `modules/strategy`: nowe `rule.py` (język), `interpreter.py` (ocena), `resolver.py`
  (scalenie dwóch źródeł wpisów), `rule_validation.py` (odmowa przy zapisie), migracja
  0003, router definicji, rozszerzone `contract.py`, `store.py`, `tools/platform.py`
  i komenda backtestu.
- `modules/terminal`: `contract.strategy.generated.ts` regenerowany, konfigurator
  i rozszerzone `strategyApi.ts`. Job terminala w CI odpali się z pary z `strategy/`, o ile
  ta para w `checks.yml` istnieje — sprawdzane w tej zmianie.
- `market-data`: **bez zmian**. Wszystko, czego potrzebuje konfigurator, katalog wskaźników
  już ogłasza.
- `infra/`: bez zmian — żadnego nowego zasobu, żadnej nowej tożsamości.
- Otwarta zmiana `the-screen-is-mostly-refusals` trzyma spec `terminal-strategy` i ma dwa
  niedomknięte zadania (szczegóły decyzji, raporty backtestu). Dlatego ekran konfiguratora
  wchodzi jako **osobna** zdolność, a nie jako modyfikacja tamtej: dwie otwarte zmiany
  nad jednym specem to konflikt, który nikomu niczego nie kupuje. Obie te pozycje będą
  musiały pokazać rewizję — odnotowane tam, nie robione tutaj.

Artefakty: design.md niesie odwrócenie decyzji nr 1 i słownik węzłów; tasks.md kolejność
budowy; review.md na zamknięcie, wg szablonu repo.
