## ADDED Requirements

### Requirement: Operator zatrzymuje turę w trakcie

Moduł MUST przyjmować żądanie zatrzymania tury trwającej w danej rozmowie i MUST je
odróżniać od porzucenia strumienia. Porzucenie łącza zostaje tym, czym jest — tura biegnie
dalej i zapisuje się w całości — a zatrzymanie kończy turę na tym, co model zdążył
wypowiedzieć.

Tura zatrzymana MUST zostać zapisana: częściowa wypowiedź agenta trafia do transkryptu z
oznaczeniem, że została zatrzymana, odróżnialnym od oznaczenia wypowiedzi urwanej błędem
modelu. Wołający, który odczyta transkrypt po fakcie, MUST móc stwierdzić, że to operator
przerwał, a nie że model padł — to dwie różne rzeczy do zrobienia następnym razem.

Zużycie tury zatrzymanej MUST zostać zapisane na tych samych zasadach co zużycie tury
dokończonej. Wywołania narzędzi, które padły przed zatrzymaniem, MUST zostać przy tej
wypowiedzi.

Strumień tury zatrzymanej MUST domknąć się zdarzeniem oznaczającym zatrzymanie,
odróżnialnym od domknięcia odpowiedzi i od błędu.

Zatrzymanie MUST działać na najbliższej granicy, a nie w dowolnym miejscu: wywołanie
narzędzia, które już zostało wysłane, MUST dojść do końca i MUST zostać zapisane wraz z
tym, jak się skończyło. Dopiero po nim tura się kończy i następna runda modelu MUST NOT
wystartować. Porzucenie wysłanego wywołania zostawiłoby zapis mówiący mniej, niż się
wydarzyło — po tej stronie są narzędzia, które piszą.

Żądanie zatrzymania rozmowy, w której nic w tej chwili nie biegnie, MUST być bezpieczne i
MUST NOT zmieniać transkryptu. Żądanie zatrzymania cudzej rozmowy MUST być nieodróżnialne
od żądania dla rozmowy nieistniejącej.

#### Scenario: Operator zatrzymuje odpowiedź w połowie

- **WHEN** operator żąda zatrzymania tury, gdy model wypowiedział część odpowiedzi
- **THEN** strumień domyka się zdarzeniem zatrzymania, odróżnialnym od domknięcia i od
  błędu
- **AND** to, co model zdążył wypowiedzieć, jest w transkrypcie z oznaczeniem zatrzymania
- **AND** zużycie tej tury jest zapisane

#### Scenario: Zatrzymanie zastaje trwające wywołanie narzędzia

- **WHEN** operator żąda zatrzymania w chwili, gdy agent czeka na wynik wywołanego
  narzędzia
- **THEN** wywołanie dochodzi do końca i trafia do transkryptu wraz z tym, jak się
  skończyło
- **AND** następna runda modelu MUST NOT wystartować
- **AND** tura kończy się jako zatrzymana

#### Scenario: Zatrzymana odróżnia się od urwanej błędem

- **WHEN** wołający odczytuje transkrypt sesji, w której jedna tura została zatrzymana
  przez operatora, a inna urwała się błędem modelu
- **THEN** obie wypowiedzi są oznaczone, a oznaczenia są od siebie odróżnialne

#### Scenario: Zatrzymanie tury, której nie ma

- **WHEN** operator żąda zatrzymania rozmowy, w której żadna tura w tej chwili nie biegnie
- **THEN** żądanie kończy się bez błędu
- **AND** transkrypt pozostaje niezmieniony

#### Scenario: Zatrzymanie cudzej rozmowy

- **WHEN** żądanie zatrzymania dotyczy rozmowy należącej do kogoś innego
- **THEN** odpowiedź jest nieodróżnialna od odpowiedzi o rozmowie nieistniejącej

## MODIFIED Requirements

### Requirement: Odpowiedź płynie strumieniem

Odpowiedź agenta MUST docierać do wołającego przyrostowo, w miarę jak powstaje, a nie
jednym blokiem po jej zakończeniu. Strumień MUST kończyć się zdarzeniem oznaczającym jedno
z trzech zakończeń tury — domknięcie odpowiedzi, błąd albo zatrzymanie przez operatora — i
te trzy MUST być od siebie odróżnialne. Cisza na łączu jest nieodróżnialna od zerwania, a
wołający MUST mieć na czym oprzeć różnicę.

Strumień MUST nieść także wywołania narzędzi, którymi agent dochodzi do odpowiedzi, jako
zdarzenia odróżnialne od fragmentu tekstu, od domknięcia i od błędu. Wywołanie MUST
dotrzeć w chwili, w której się rozstrzygnęło, a nie po zakończeniu całej tury: runda
narzędzi trwa sekundy, w których nie powstaje żaden fragment tekstu, i bez tego jest dla
wołającego nieodróżnialna od modelu, który się zawiesił.

Zdarzenie wywołania MUST nieść nazwę narzędzia, argumenty, którymi je wywołano, to jak
się skończyło, jego wynik albo powód odmowy oraz czas trwania. Wynik MUST być tą samą
treścią, którą dostał model — wołający, który widzi streszczenie, nie ma jak stwierdzić,
że model dostał coś innego.

Wypowiedź agenta MUST być zapisana w transkrypcie w całości, także wtedy, gdy strumień
zostanie porzucony w połowie: operator, który zamknął panel, MUST znaleźć pełną odpowiedź
po powrocie do sesji. To samo MUST dotyczyć wywołań narzędzi tej tury — wołający, który
odczyta transkrypt po zakończeniu tury, MUST dostać te same wywołania, które niósł
strumień.

Wołający, który nie zna rodzaju zdarzenia, MUST móc je pominąć bez utraty odpowiedzi.

#### Scenario: Fragmenty docierają przed końcem odpowiedzi

- **WHEN** model generuje długą odpowiedź
- **THEN** wołający dostaje jej kolejne fragmenty przed jej zakończeniem

#### Scenario: Wywołanie narzędzia dociera w trakcie tury

- **WHEN** model wywołuje narzędzie i czeka na jego wynik
- **THEN** wołający dostaje zdarzenie tego wywołania, zanim przyjdzie domknięcie
  odpowiedzi
- **AND** zdarzenie niesie nazwę, argumenty, wynik albo powód odmowy oraz czas trwania

#### Scenario: Wywołanie odmówione dociera tak samo

- **WHEN** narzędzie odmawia zamiast odpowiedzieć
- **THEN** wołający dostaje zdarzenie tego wywołania z powodem odmowy
- **AND** tura toczy się dalej, a odmowa MUST NOT być podana jako błąd strumienia

#### Scenario: Wołający rozłącza się w trakcie

- **WHEN** wołający zamyka połączenie w trakcie strumienia
- **THEN** odpowiedź zostaje dokończona i zapisana w transkrypcie
- **AND** ponowny odczyt sesji zwraca ją w całości, wraz z wywołaniami narzędzi tej tury

#### Scenario: Model przerywa w połowie

- **WHEN** wywołanie modelu kończy się błędem po wysłaniu części fragmentów
- **THEN** strumień niesie zdarzenie błędu, odróżnialne od domknięcia odpowiedzi
- **AND** to, co model zdążył wypowiedzieć, MUST być zapisane wraz z oznaczeniem, że
  odpowiedź jest niepełna
- **AND** wywołania, które zdążyły paść przed błędem, MUST zostać przy tej wypowiedzi
