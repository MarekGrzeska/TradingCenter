## MODIFIED Requirements

### Requirement: Odpowiedź płynie strumieniem

Odpowiedź agenta MUST docierać do wołającego przyrostowo, w miarę jak powstaje, a nie
jednym blokiem po jej zakończeniu. Strumień MUST kończyć się zdarzeniem oznaczającym
domknięcie odpowiedzi — cisza na łączu jest nieodróżnialna od zerwania, a wołający MUST
mieć na czym oprzeć różnicę.

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
