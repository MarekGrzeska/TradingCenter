## Why

Po etapie 2 (`a-strategy-from-a-description`) pierwszy backtest wymaga od operatora ręcznego wpisania kosztów
instrumentu, a rozmowy z agentem w zakładce Strategies prawie nie widać: panel jest zwiniętym paskiem na prawej
krawędzi. Operator 25.10.2026 postanowił, że koszty mają się ustawiać same z danych capital.com i że ma być możliwy
świadomy backtest bez kosztów. Chce też widzieć rozmowę przy tworzeniu strategii.

## What Changes

- **Brama** podaje w warunkach instrumentu jego finansowanie overnight w takiej postaci, w jakiej publikuje je
  capital.com: stawkę longa i shorta z jednostką oraz chwilę naliczenia. Archiwum `/market` przekazuje te warunki tak
  jak dziś katalog i wyszukiwanie.
- **Profil kosztów pochodzi od brokera.** Gdy uruchomienie nie podaje kosztów, a instrument nie ma profilu, pakiet
  pobiera go sam przez `/market` w procesie. Spread liczy z bieżących bid i ask, finansowanie i godzinę rozliczenia
  bierze z warunków instrumentu. Profil zapisuje się ze źródłem, chwilą pobrania i surowymi wartościami. Operator może
  go poprawić albo odświeżyć z brokera, ale nie musi niczego wpisywać.
- **Backtest bez kosztów** to jawny wybór: `without_costs` w żądaniu i w narzędziu agenta. Raport i zakładka oznaczają
  takie uruchomienie jako nierealistyczne. Zera wpisane ręcznie dalej są zwykłym modelem kosztów.
- **Agent nadal nie podaje liczb kosztów.** Dostaje je od pakietu albo, na wyraźną prośbę operatora, uruchamia bez
  kosztów.
- **Osobny czat w oknie tworzenia strategii**, obok edytora, tak jak „opisz zdaniem” w Alertach. Każda strategia ma
  swoją rozmowę z agentem, który pisze ją z opisu, dopytuje i zapisuje rewizje. Nowa strategia zaczyna się od pustej
  rozmowy w tym oknie. Rozmowa tej strategii wraca po ponownym otwarciu strategii, także z innego urządzenia, bo
  strategia pamięta jej identyfikator. Panel agenta z prawej strony terminala zostaje bez zmian.

**Poza zakresem:** godzinowy profil spreadu z historii (broker podaje jeden bieżący spread), aktualizacja profilu przy
każdym uruchomieniu (dwa uruchomienia przestałyby być porównywalne), narzędzie agenta do ustawiania liczb kosztów.

## Capabilities

### New Capabilities
Brak.

### Modified Capabilities
- `capital-market-data`: warunki instrumentu niosą finansowanie overnight z jednostką i chwilą naliczenia.
- `market-data-api`: archiwum przekazuje warunki instrumentu, tak jak katalog i wyszukiwanie.
- `strategies-backtest`: model kosztów jest jawny, ale nie musi go podawać wołający (profil od brokera albo
  `without_costs`); profil pochodzi od brokera i zna swoje źródło.
- `strategies-api`: trasa odświeżenia profilu z brokera.
- `strategies-reports`: raport oznacza uruchomienie bez kosztów i źródło kosztów.
- `strategies-tools`: `run_backtest` bierze koszty od pakietu albo uruchamia bez kosztów; nie odmawia z braku profilu.
- `strategies-documents`: strategia pamięta swoją rozmowę.
- `terminal-strategies`: formularz z kosztami od brokera i przełącznikiem „bez kosztów”; czat strategii w oknie
  tworzenia.

## Impact

- `modules/capital-gateway`: `InstrumentTerms` w `dtos.py` i `mapping.py`, fixture `market_gold.json` już ma te pola.
  Kontrakt bramy się zmienia, więc snapshot w `trading-mcp` trzeba regenerować (skill `contract-sync`).
- `modules/workbench/market_data`: proxy `GET /instruments/{symbol}/terms` i rekord wołających.
- `modules/workbench/strategies`: `broker_costs.py`, migracja `0003` (źródło, chwila i surowe wartości profilu,
  `strategies.conversation_id`), `PUT /strategies/{id}/conversation`,
  `RunIn.costs` opcjonalne i `without_costs`, odczyt przez `archive.py`, `run_backtest`, raport.
- `modules/terminal`: formularz uruchomienia, oznaczenie w raporcie, czat strategii (druga instancja
  `agentChatStore` bez zapisu w `localStorage`, wspólne komponenty transkryptu i pola wpisu), kontrakty strategii i
  archiwum.
- `review.md` powstanie po zadaniach: zmienia się kontrakt bramy i źródło liczb, od których zależy każdy wynik.
