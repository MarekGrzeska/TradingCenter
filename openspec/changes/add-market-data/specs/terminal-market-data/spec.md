## MODIFIED Requirements

### Requirement: Źródło danych jest wymienne za jednym interfejsem

Terminal MUST czytać świece i strumień wyłącznie przez jeden interfejs, opisujący odczyt historii
i subskrypcję na żywo. Interfejs MUST mieć więcej niż jedną implementację: świece i strumień
obsługuje archiwum, a katalog instrumentów pozostaje w `capital-gateway`, bo to on jest jego
właścicielem. Złożenie obu w jedną instancję MUST być ukryte przed widokami — żaden widok
MUST NOT wiedzieć, która implementacja obsługuje które wywołanie, ani MUST NOT budować jej sam.

#### Scenario: Dołożenie kolejnego źródła

- **WHEN** pojawia się kolejna implementacja interfejsu, na przykład czytająca z innej bazy świec
- **THEN** wpięcie jej MUST NOT wymagać zmian w wykresie, w siatce ani w wyszukiwarce

#### Scenario: Jedna instancja na całą aplikację

- **WHEN** wiele widoków czyta dane w tym samym czasie
- **THEN** korzystają z tej samej instancji źródła, żeby współdzieliły jeden zestaw połączeń
- **AND** żaden widok nie tworzy własnej

#### Scenario: Świece i instrumenty idą z różnych miejsc

- **WHEN** widok prosi o świece, a następnie o instrumenty
- **THEN** świece pochodzą z archiwum, a instrumenty z gatewaya
- **AND** widok nie wie, że wywołania trafiły do dwóch różnych systemów

#### Scenario: Jedno ze źródeł nie odpowiada

- **WHEN** archiwum jest nieosiągalne, a gateway działa
- **THEN** wyszukiwarka instrumentów działa dalej
- **AND** wykres pokazuje, że źródło świec jest nieosiągalne, zamiast pustej serii

### Requirement: Zerwane połączenie wraca samo i mówi o sobie

Strumień MUST być wznawiany po zerwaniu, z odstępem rosnącym między próbami, a stan połączenia
(łączenie, połączony, wznawianie, zamknięty) MUST być dostępny odbiorcom. Luka powstała w czasie
przerwy MUST zostać domknięta, ale terminal MUST NOT dociągać jej sam — subskrypcja rozpoczyna się
snapshotem, więc ponowne połączenie przynosi brakujące świece razem ze stanem bieżącym.

Odmowa, której ponawianie nie naprawi, MUST być odróżniona od zerwania i MUST NOT być ponawiana
bez końca. Archiwum odmawia subskrypcji pary nieśledzonej **przed** handshake'em, a przeglądarka
nie udostępnia statusu odrzuconego handshake'u — nieudane połączenie wygląda więc tak samo jak
niedostępne archiwum. Terminal MUST rozstrzygnąć, które z dwojga zaszło, zanim osiądzie w pętli
ponawiania, i MUST pokazać powód odmowy zamiast stanu wznawiania. Rozstrzygnięcie MUST kosztować
najwyżej jedno pytanie na serię niepowodzeń, a jego własna porażka MUST być czytana jako „ponawiaj
dalej", bo źródło, które nie odpowiada, jest właśnie tym przypadkiem, dla którego ponawianie
istnieje.

#### Scenario: Wykres pary, której nikt nie archiwizuje

- **WHEN** widok subskrybuje parę, która nie jest śledzona, a archiwum odmawia połączenia
- **THEN** wykres mówi, że ta para nie jest archiwizowana, i wskazuje, gdzie to zmienić
- **AND** terminal przestaje ponawiać, zamiast pokazywać wznawianie bez końca

#### Scenario: Archiwum nie odpowiada również na pytanie o powód

- **WHEN** połączenie nie dochodzi do skutku, a rozstrzygnięcie powodu też się nie udaje
- **THEN** terminal ponawia dalej z rosnącym odstępem, bo to jest przypadek zerwania

#### Scenario: Połączenie pada

- **WHEN** strumień się zrywa
- **THEN** odbiorcy widzą stan wznawiania, a terminal ponawia próby z rosnącym odstępem

#### Scenario: Połączenie wraca

- **WHEN** strumień zostaje wznowiony po przerwie
- **THEN** snapshot z ponownej subskrypcji uzupełnia świece z okresu przerwy
- **AND** odbiorcy widzą stan połączony
- **AND** terminal nie wysyła osobnego zapytania o historię, żeby domknąć lukę

#### Scenario: Snapshot styka się z posiadaną serią

- **WHEN** snapshot niesie świece, które terminal już ma
- **THEN** świece o tych samych znacznikach czasu podmieniają się, zamiast tworzyć duplikaty
