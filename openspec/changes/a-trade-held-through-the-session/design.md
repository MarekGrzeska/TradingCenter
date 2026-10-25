## Context

Motywacja w proposal.md. Stan, który kształtuje podejście:

- Czas w języku to `hour`, `minute`, `weekday` liczone z `starts` w UTC (`evaluate.py`, `_name`). Rejestr nazw jest jeden
  (`vocabulary.py`), a `GET /language` i `strategy_language` są z niego drukowane, więc nowa nazwa dociera do agenta bez
  zmiany promptu.
- Strefy sesji na wykresie (`market_data/indicators/catalogue/zones.py`, `_SESSION_TYPES`) mają strefę i godziny jako
  parametry `from_hour`/`to_hour`. Wyjście to strefy, a nie linie, więc język ich nie przyjmuje (`strategies-language`).
  Pakiety się nie importują.
- Silnik liczy ryzyko od stopu w `_open` i odrzuca wejście bez niego. `run_trades.initial_stop` i `result_r` są
  `NOT NULL`, a `CHECK` zna sześć przyczyn wyjścia (`0001_documents_and_runs.py`).
- Warunki instrumentu z bramy już niosą `margin_factor` i `margin_factor_unit`, a `broker_costs.py` czyta je przez
  `/market`, tylko pomija te dwa pola.
- Pieniądz to jednostki × punkty, bez wielkości kontraktu i bez przeliczenia walut (D6 zmiany
  `a-strategy-is-a-document`).

## Goals / Non-Goals

**Goals:**
- Strategia operatora z 25.10 da się zapisać bez zmiany jej reguł, i agent może ją napisać sam.
- Żaden zapisany dokument nie zmienia znaczenia, a żaden zapisany wynik się nie przesuwa.

**Non-Goals:**
- Kalendarz giełdy: święta i skrócone sesje (osobna zmiana, kalendarz XNYS z biblioteki).
- Godziny lokalne dla `hour`/`minute`/`weekday`.
- Próg zamknięcia przez brokera (D6).

## Decisions

### D1. Sesja to nazwany wpis rejestru języka

`NEW_YORK`, `LONDON` i `TOKYO` stoją w `vocabulary.py` ze strefą IANA, otwarciem i zamknięciem w czasie lokalnym, od
poniedziałku do piątku. Nowy rodzaj argumentu (`Arg.SESSION`) przyjmuje wyłącznie te nazwy, więc `close > NEW_YORK`
jest błędem typu, a nie liczbą. Godziny są powtórzone z katalogu wykresu. Test w `tests/`, czyli poza oboma pakietami,
porównuje obie tabele, żeby strategia czytała tę samą sesję, którą operator widzi na wykresie.

*Odrzucone:*
- Strefy `session_range_*` z katalogu: to zakres high/low okna, a nie zegar, a język przyjmuje tylko linie. Trzeba
  by zmienić kontrakt katalogu dla pytania, na które odpowiada sam zegar.
- `timezone` w dokumencie z lokalnymi `hour`/`minute`: godziny sesji nadal byłyby wpisane na sztywno, a agent musiałby
  je znać. Te same nazwy znaczyłyby co innego zależnie od pola, co komplikuje walidację i streszczenie.
- Sesje definiowane w dokumencie: agent wymyślałby godziny. Trzy sesje pokrywają instrumenty archiwum, a czwarta to
  jedna linia rejestru.

### D2. Numer świecy liczony zegarem, nie liczbą świec w danych

`session_bar` to `(lokalny start świecy − otwarcie) // okres + 1` dla świec zaczynających się w sesji, a 0 dla
pozostałych. Gdyby liczyć świece obecne w danych, brak świecy 9:30 zrobiłby z 9:35 „pierwszą”, czyli inną strategię
niż opisana. Zegar w takim dniu po prostu nie daje sygnału.

Otwarcie i zamknięcie w UTC liczy `zoneinfo` raz na dzień kalendarzowy zakresu, a świece dostają je wektorowo
(`searchsorted`). Zmiana czasu wypada nocą, poza każdą z trzech sesji, więc jedno przesunięcie na dzień jest dokładne.
Faza pierwsza (D4 zmiany `a-strategy-is-a-document`) liczy to na numpy dla całej osi.

### D3. `minutes_to_session_close` jest ujemne po zamknięciu

Wartość pusta po zamknięciu daje fałsz w każdym porównaniu. Jedna brakująca świeca 15:50 zostawiłaby wtedy pozycję
otwartą na noc, a to błąd, którego raport by nie pokazał. Z wartością ujemną warunek `<= 5` łapie pierwszą świecę po
luce. Pusta jest tylko w dzień bez sesji.

### D4. Bez stopu R jest puste, a każda transakcja ma wynik w % kapitału przy wejściu

*Odrzucone:*
- Sztuczny daleki stop: zmienia strategię, bo może się wypełnić, i daje R bez znaczenia.
- Jawna jednostka ryzyka (`exits.risk`, np. `at_entry(atr(14))`): R z formuły, której nic nie egzekwuje, wygląda jak
  ryzyko, a nim nie jest. Dwie strategie miałyby R mierzone różnymi miarami pod tą samą nazwą.
- R od MAE po fakcie: mianownik zależałby od wyniku.

Procent liczony jest od kapitału w chwili wejścia, bo od niego liczy się wielkość pozycji. Suma procentów nie jest
zwrotem, bo zwrot się składa; zwrot to `return_pct` z krzywej. Zyskowność, profit factor i serie strat liczą się z
pieniądza. Znak R i pieniądza jest zawsze ten sam, bo mianownik R jest dodatni, więc dla strategii ze stopem te liczby
się nie zmieniają.

MAE to najgorszy wynik pozycji na minutach po stronie wyjścia, liczony w tej samej pętli minut, która już sprawdza
stop i cel. Koszt jest więc stały na minutę.

### D5. Depozyt w osobnej tabeli instrumentu, pobrany przy pierwszej potrzebie

Tabela `instrument_margins` (symbol, `margin_factor` jako ułamek, źródło, surowa wartość i jednostka brokera). Pierwotnie
miała to być kolumna `cost_profiles`, ale implementacja pokazała przypadek, który ją wyklucza: uruchomienie `without_costs`
albo z kosztami w żądaniu nie ma profilu kosztów, a może być liczone według depozytu. Depozyt nie jest kosztem, więc nie
wisi na profilu kosztów. Pobiera go pierwsze uruchomienie z `margin_fraction`, a operator zmienia przez
`PUT /margins/{symbol}`. Uruchomienie kopiuje użytą wartość do `request`, tak jak koszty.

Zmierzone na demo 25.10.2026 (`GET /instruments/{symbol}/terms` bramy): US100, US500 i GOLD po 5 `PERCENTAGE`, EURUSD
3,333333 `PERCENTAGE`, wszystkie w USD z `lot_size` 1. Nagranie `market_gold.json` w testach bramy ma 100%, czyli jest
starsze niż obecne warunki konta. Nie jest wzorem.

*Odrzucone:*
- Depozyt w dokumencie (`sizing.margin_factor`): fakt brokera w strategii, wpisywany przez agenta, który go nie zna.
  To ta sama zasada, z której agent nie podaje kosztów.
- Odczyt przy każdym uruchomieniu: zmiana depozytu u brokera przesunęłaby porównanie dwóch uruchomień.

`notional_fraction` nie potrzebuje niczego od brokera. Przy depozycie 5% `margin_fraction` 0,05 to ta sama pozycja co
`notional_fraction` 1, czyli wartość równa kapitałowi. Agent może tak to wyjaśnić operatorowi.

### D6. Brak kapitału na progu zero, nie na progu brokera

Silnik traktuje zerowy kapitał jak stop: poziom `entry − side × (kapitał − finansowanie) / units` jest przeliczany na
każdej minucie z narosłym finansowaniem. Luka wypełnia się po pierwszej cenie za nią, a po zamknięciu nie ma już
wejść.

*Odrzucone:*
- 50% depozytu wg ESMA: broker nie podaje progu w API, a zależy on od statusu klienta. Wartość domyślna byłaby liczbą,
  której nikt nie wybrał.
- Kontynuacja z ujemnym kapitałem: `fixed_units` handlowałoby dalej z konta, którego nie ma.

Zero to granica, której nie przekroczy żaden rachunek. Broker zamyka wcześniej, więc wynik wokół tej granicy pozostaje
optymistyczny (Risks).

### D7. Schemat 1, silnik 3

Dokument dostaje same dodatki, więc `SCHEMA_VERSION` zostaje (komentarz w `document.py`). Silnik dostaje nowe pola
transakcji i raportu, a `out_of_capital` może przesunąć wynik strategii, która traciła cały kapitał. Dlatego
`ENGINE_VERSION` rośnie do 3, a złote strategie są nagrywane od nowa. Stare raporty i transakcje nie są przeliczane:
nowe pola mają w nich `NULL`, a terminal pokazuje brak wartości.

## Risks / Trade-offs

- [Sesja zegarowa wchodzi w święto, w które CFD ma notowania] → poza zakresem z nazwy w proposal.md. Kalendarz XNYS
  to następna zmiana, a do tego czasu streszczenie mówi „bez świąt giełdowych”.
- [Depozyt z dziś zastosowany do historii] → depozyty detaliczne na indeksach są stałe od 2018 (ESMA), a wartość
  jest zapisana w raporcie. Historii depozytów broker nie podaje.
- [`margin_fraction` w modelu bez wielkości kontraktu (D6 `a-strategy-is-a-document`)] → depozyt liczony jest w tych
  samych jednostkach nominalnych co pieniądz raportu. Jest spójny w modelu, ale nie jest kwotą w walucie rachunku.
- [Próg zero jest łagodniejszy niż broker] → zapisany w D6. Próg brokera może dojść, gdy da się go odczytać albo gdy
  operator zechce go ustawić.
- [Godziny sesji powtórzone w dwóch pakietach] → test porównujący obie tabele.

## Migration Plan

Migracja `0005` jest addytywna i pakiet stosuje ją sam w `lifespan` pod blokadą 8130:
- `run_trades.initial_stop` i `result_r` bez `NOT NULL`;
- nowe kolumny `result_pct` i `mae_pct`, `NULL` dla istniejących wierszy;
- `CHECK` przyczyn wyjścia z `out_of_capital`;
- tabela `instrument_margins` (D5).

`headline` nowych uruchomień niesie `return_pct`. Wycofanie obrazu działa na nowym schemacie, bo stary kod nie czyta
nowych kolumn. Wyjątek to strona transakcji uruchomienia bez stopu: stary kod nie przyjmie tam `NULL` w `result_r` i
odmówi tylko tej strony. `downgrade` przywraca `NOT NULL` tylko wtedy, gdy takich wierszy nie ma, a w przeciwnym razie
odmawia z ich liczbą.
