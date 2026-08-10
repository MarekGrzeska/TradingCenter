## MODIFIED Requirements

### Requirement: Zapisywana jest wyłącznie świeca zamknięta

Świeca w budowie zmienia się przy każdym kwotowaniu i po restarcie źródła zaniża swój zakres.
Archiwum MUST NOT utrwalać świecy oznaczonej jako w budowie. Trafia do niego wyłącznie świeca
zamknięta.

Reguła obowiązuje niezależnie od tego, którą drogą świeca przyszła. Odczyt historii sięgający
chwili bieżącej zwraca także okres, który jeszcze trwa, i taka świeca MUST NOT zostać
utrwalona tak samo jak ta ze strumienia — archiwum MUST NOT zakładać, że wszystko, co
przyszło z historii, jest zamknięte. Cena jest tu wyższa niż przy strumieniu, bo świeca
utrwalona z historii zatrzymuje kolejne uzupełnianie: zaległość liczy się od najnowszej
posiadanej świecy, więc bieżący okres zapisany jako fakt wygląda jak archiwum, które jest na
bieżąco, i zostaje z częściowymi wartościami do czasu, aż postarzeje się o dwa okresy.

#### Scenario: Strumień niesie świecę w budowie

- **WHEN** ze strumienia przychodzi świeca oznaczona jako w budowie
- **THEN** archiwum nie zapisuje jej
- **AND** świeca pozostaje dostępna konsumentom jako wartość ulotna, nieutrwalona

#### Scenario: Odczyt historii niesie okres, który jeszcze trwa

- **WHEN** odczyt historii zwraca świecę oznaczoną jako należącą do okresu, który się nie
  domknął
- **THEN** archiwum nie zapisuje jej, a zapisuje pozostałe świece z tego samego odczytu
- **AND** zakres pokrycia obejmuje okres tak samo jak dotąd, bo został sprawdzony

#### Scenario: Okres się zamyka

- **WHEN** dla okresu, który był w budowie, przychodzi świeca zamknięta
- **THEN** archiwum zapisuje wartości ze świecy zamkniętej

### Requirement: Archiwum wie, co pokrywa

Brak świecy o 3:00 w sobotę i brak świecy, bo ingest nie działał, wyglądają w danych identycznie.
Archiwum MUST przechowywać dla każdej śledzonej pary zakresy czasu, dla których dane zostały
zweryfikowane, żeby te dwa przypadki dało się rozróżnić.

Granica „provider nie ma nic starszego" jest częścią tego zapisu i kosztuje więcej niż reszta:
na jej podstawie moduł pomija pracę, do której sam z siebie nigdy nie wróci. Dlatego MUST być
zapisana tam, gdzie dane faktycznie się skończyły — na najstarszej świecy, którą odczyt przyniósł
— a nie na krawędzi okna, o które zapytano. Te dwa punkty dzieli wszystko, czego provider nie
miał, a zapisanie tego drugiego ogłasza jako sprawdzone coś, czego nikt nie sprawdził.

Granica MUST przestać obowiązywać, gdy ktoś jawnie prosi o dane starsze od niej. Historia
u providera z czasem się pogłębia, zapis mógł powstać z odpowiedzi, która nie znaczyła tego, co
się jej przypisało, a operator proszący o wcześniejszą datę wyraża dokładnie jedno: żeby
sprawdzić to jeszcze raz. Archiwum MUST wtedy zdjąć granicę i zaplanować pełny zakres, MUST NOT
zaś przyciąć prośby po cichu do wartości, którą trzyma. Samo odczytanie stanu pokrycia ani wycena
pracy MUST NOT zdejmować granicy — robi to wyłącznie ścieżka, która faktycznie zleca zbieranie.

#### Scenario: Brak świecy wewnątrz pokrycia

- **WHEN** w zweryfikowanym zakresie nie ma świecy dla danego okresu
- **THEN** archiwum stwierdza, że rynek był wtedy zamknięty, a nie że brakuje danych

#### Scenario: Brak świecy poza pokryciem

- **WHEN** żądany okres wypada poza jakimkolwiek zweryfikowanym zakresem
- **THEN** archiwum stwierdza, że tego okresu nie zebrało

#### Scenario: Historia instrumentu się skończyła

- **WHEN** uzupełnianie wstecz dochodzi do miejsca, w którym provider nie ma starszych danych
- **THEN** jako najstarsza możliwa granica pokrycia zostaje zapisany znacznik czasu najstarszej
  świecy, którą ten odczyt przyniósł
- **AND** kolejne uzupełnianie nie sięga już przed tę granicę

#### Scenario: Odczyt kończy się bez ani jednej świecy

- **WHEN** odczyt sięgający wstecz nie przynosi żadnej świecy
- **THEN** archiwum MUST NOT zapisać dla tej pary granicy najstarszego osiągalnego momentu
- **AND** zakres pozostaje możliwy do zebrania przy kolejnej próbie

#### Scenario: Prośba o dane starsze niż zapisana granica

- **WHEN** zlecenie zbierania jest tworzone dla pary z datą początku wcześniejszą niż zapisana
  granica najstarszego osiągalnego momentu
- **THEN** archiwum zdejmuje tę granicę i planuje cały żądany zakres
- **AND** granica zostaje zapisana na nowo dopiero wtedy, gdy provider potwierdzi ją ponownie

#### Scenario: Odczyt stanu pokrycia nie zmienia granicy

- **WHEN** konsument odczytuje stan pokrycia pary albo prosi o wycenę pracy z datą początku
  wcześniejszą niż zapisana granica
- **THEN** granica pozostaje zapisana bez zmian
- **AND** wycena pokazuje ten sam zakres, który zostałby zaplanowany, gdyby zlecenie powstało
