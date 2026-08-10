## MODIFIED Requirements

### Requirement: Śledzone pary są zarządzalne przez kontrakt

Moduł MUST udostępniać przez swój kontrakt dodanie pary do śledzonych, skasowanie jej oraz odczyt
listy wraz ze stanem każdej pary. Konfiguracja MUST NOT wymagać dostępu do plików ani restartu.
Dodanie MUST przyjmować wiele par naraz wraz z jednym momentem, od którego historia ma zostać
pokryta, i MUST odpowiadać wynikiem osobno dla każdej pary — odmowa dla jednej MUST NOT przekreślać
pozostałych. Żądanie bez podanego momentu początku MUST pozostać ważne i MUST znaczyć domyślną
głębokość z konfiguracji, żeby konsument sprzed tej zmiany działał dalej.

Odczyt listy MUST nieść dla każdej pary liczbę zebranych świec oraz szacowaną objętość, jaką
zajmują. Konsument MUST NOT musieć wyliczać żadnej z tych liczb sam: liczby świec nie da się
wyprowadzić z zakresu dat, a mnożnik objętości należy do modułu, który dane przechowuje, a nie do
tego, który je pokazuje.

Skasowanie pary przez kontrakt MUST zatrzymać zbieranie i usunąć zebrane dane tej pary. Odpowiedź
MUST nieść liczbę usuniętych świec, bo to jedyny moment, w którym konsument może się dowiedzieć, ile
danych właśnie zniknęło.

#### Scenario: Dodanie pary

- **WHEN** konsument dodaje parę przez kontrakt
- **THEN** para zostaje zapisana jako śledzona, a odpowiedź to potwierdza

#### Scenario: Odczyt listy z objętością danych

- **WHEN** konsument odczytuje listę śledzonych par
- **THEN** każda para niesie liczbę zebranych świec i szacowaną objętość w bajtach
- **AND** obie liczby dotyczą wyłącznie tej pary, a nie całego archiwum

#### Scenario: Dodanie wielu par jednym żądaniem

- **WHEN** konsument dodaje kilka par wraz z momentem początku
- **THEN** wszystkie zostają zapisane jako śledzone
- **AND** odpowiedź niesie identyfikator zlecenia dociągnięcia historii dla tych par

#### Scenario: Jedna z par zostaje odrzucona

- **WHEN** wśród dodawanych par jedna zostaje odrzucona, a pozostałe nie
- **THEN** odpowiedź stwierdza to osobno dla każdej pary, nazywając powód odmowy
- **AND** pary przyjęte są śledzone

#### Scenario: Żądanie bez momentu początku

- **WHEN** konsument dodaje parę bez podania momentu początku
- **THEN** moduł przyjmuje żądanie
- **AND** historia jest dociągana do domyślnej głębokości z konfiguracji

#### Scenario: Dodanie pary nieznanej providerowi

- **WHEN** konsument dodaje parę, której symbolu provider nie zna
- **THEN** moduł odmawia i nazywa symbol jako nieznaleziony

#### Scenario: Usunięcie pary

- **WHEN** konsument kasuje parę przez kontrakt
- **THEN** zbieranie ustaje, a świece i pokrycie tej pary przestają istnieć
- **AND** odpowiedź niesie liczbę usuniętych świec

#### Scenario: Skasowanie pary, która nie jest śledzona

- **WHEN** konsument kasuje parę, której moduł nie zna
- **THEN** moduł odmawia i nazywa parę jako nieśledzoną
- **AND** MUST NOT kasować niczego innego
