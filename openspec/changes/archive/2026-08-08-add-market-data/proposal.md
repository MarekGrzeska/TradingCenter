## Why

`capital-gateway` jest oknem na providera, nie archiwum — i mówi to o sobie wprost. Skutek widać
przy każdym wykresie: głęboki odczyt historii to dziesiątki żądań i dziesiątki sekund, a to, co
przeleciało strumieniem wczoraj, nie istnieje dziś nigdzie. Terminal ogląda rynek wyłącznie w
oknie, które akurat zdąży pobrać.

Drugi powód jest ostrzejszy: **capital.com nie trzyma historii w nieskończoność i nie da się jej
odtworzyć szybciej niż pozwala limit dziesięciu żądań na sekundę**. Każdy dzień bez archiwum to
dzień danych, których później może już nie być. Backtesty i agenci, którzy mają przyjść po
terminalu, potrzebują serii ciągłych i powtarzalnych, a nie tego, co provider akurat zwróci.

## What Changes

- Nowy moduł `modules/market-data` — Python 3.12, FastAPI, własna baza PostgreSQL — stojący
  samodzielnie i rozmawiający z `capital-gateway` wyłącznie po jego opublikowanym kontrakcie.
- **Archiwum świec**: świeca zamknięta jest zapisywana raz i nadpisywana wyłącznie wtedy, gdy
  provider przyśle dla tego samego okresu wartość autorytatywną. Świeca w budowie nigdy nie trafia
  do bazy.
- **Śledzone pary konfiguruje operator z terminala.** Nie ma listy w pliku ani automatycznego
  dopisywania przy pierwszym wyświetleniu wykresu — para (symbol, rozdzielczość) jest archiwizowana
  dlatego, że ktoś świadomie tak zdecydował, i przestaje być archiwizowana, gdy tę decyzję cofnie.
- **Ingest w dwóch trybach**: nasłuch na żywo przez WebSocket gatewaya oraz uzupełnianie wstecz
  przez jego `/history`. Po każdym restarcie moduł domyka lukę, zamiast zostawić dziurę.
- **Wiedza o własnej kompletności**: archiwum przechowuje zakresy pokrycia, żeby odróżnić „rynek był
  wtedy zamknięty" od „tych danych nam brakuje". Bez tego moduł w nieskończoność odpytuje providera
  o ten sam weekend.
- **Kontrakt dla terminala**: odczyt zakresu świec po HTTP oraz subskrypcja, której **pierwsza
  wiadomość niesie snapshot** — ostatnie świece zamknięte plus świeca w budowie — a kolejne niosą
  już tylko zmiany. Szew między historią a danymi na żywo przestaje istnieć po stronie wykresu.
- **Terminal dostaje panel konfiguracji** śledzonych par oraz drugą implementację
  `MarketDataSource`. Świece i strumień idą odtąd z archiwum; instrumenty i handel zostają
  w gatewayu.
- Rozdzielczości pochodne (`MINUTE_5` … `HOUR_4`) są **wyliczane z serii minutowej**, a nie
  pobierane osobno. `DAY` i `WEEK` przychodzą z providera, bo ich granica zależy od sesji rynku,
  a nie od zegara — co `capital-streaming` już stwierdza.

## Capabilities

### New Capabilities

- `market-data-store`: co archiwum przechowuje i co wie o własnej kompletności — tożsamość świecy,
  nadpisywanie wartością autorytatywną, jedna strona ceny, zakresy pokrycia oraz odróżnienie luki
  od zamkniętego rynku.
- `market-data-tracking`: śledzona para jako decyzja operatora — dodanie, usunięcie, trwałość
  między restartami i natychmiastowy skutek dla ingestu.
- `market-data-ingest`: nasłuch na żywo, uzupełnianie wstecz, domknięcie luki po restarcie oraz
  budżet żądań, który nie zagładza ruchu interaktywnego idącego przez tego samego gatewaya.
- `market-data-api`: kontrakt konsumenta — odczyt zakresu, subskrypcja ze snapshotem, raport
  pokrycia, zarządzanie śledzonymi parami i nazywanie własnych porażek.
- `terminal-data-manager`: panel, z którego operator wskazuje, co ma być archiwizowane i w jakich
  rozdzielczościach, oraz widzi, co archiwum faktycznie zebrało.

### Modified Capabilities

- `terminal-market-data`: interfejs źródła danych przestaje mieć jedną implementację. Świece
  i strumień obsługuje archiwum, instrumenty zostają w gatewayu, a widoki nadal widzą jedną
  instancję jednego interfejsu.

## Impact

- Nowy katalog `modules/market-data/` z własnym `pyproject.toml`, `README.md`, `.env.example`
  i testami. Usunięcie katalogu usuwa moduł — poza migracjami bazy, która jest jego własnością.
- Nowa zależność infrastrukturalna: **PostgreSQL**. To pierwszy moduł w repozytorium, który ma stan
  trwały, więc pojawia się w nim wszystko, czego dotąd nie było: migracje, kopie zapasowe
  i konfiguracja połączenia.
- `capital-gateway` **nie zmienia zachowania**. Jest konsumowany przez `/instruments/{symbol}/history`
  i `/ws/stream` dokładnie tak, jak je opublikował.
- Ograniczenie liczby śledzonych par wynika z gatewaya: trzyma on jedno połączenie do providera na
  parę (symbol, rozdzielczość), a provider limituje sesje. Ten sufit jest w tej zmianie **przyjęty
  i udokumentowany**, nie usuwany — subskrypcja zbiorcza w gatewayu to osobna zmiana.
- `modules/terminal` dostaje nową zakładkę i drugą implementację źródła; wykres, siatka
  i wyszukiwarka nie zmieniają się.
- `README.md` repozytorium i `docs/architecture.md` dostają moduł w tabeli i na rysunku.
