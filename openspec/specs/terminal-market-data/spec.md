## Purpose

Jedno wejście na świece i strumień dla całego terminala: skąd biorą się dane, jak historia zszywa
się z tym, co przychodzi na żywo, i jak wiele wykresów patrzących na to samo dzieli jedno
połączenie zamiast otwierać po jednym każdy.

## Requirements

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

### Requirement: Znaczniki czasu są sprowadzone do jednej postaci

Historia z gatewaya niesie czas jako łańcuch ISO, a strumień jako sekundy od epoki, liczone od
początku okresu świecy. Interfejs MUST oddawać obie strony w jednej postaci — sekundach od epoki na
początku okresu — żeby świeca z historii i świeca ze strumienia trafiały w ten sam punkt osi czasu.

#### Scenario: Historia styka się ze strumieniem

- **WHEN** świeca ze strumienia dotyczy okresu obecnego już w historii
- **THEN** obie mają identyczny znacznik czasu i podmieniają się, zamiast stanąć obok siebie jako
  dwie świece

#### Scenario: Świeca ze strumienia wyprzedza historię

- **WHEN** świeca ze strumienia dotyczy okresu późniejszego niż ostatnia świeca historii
- **THEN** dopisuje się na końcu serii, zachowując porządek rosnący i nie zostawiając luki

### Requirement: Jedno połączenie obsługuje wielu odbiorców tej samej pary

Wiele wykresów MAY patrzeć na ten sam symbol i tę samą rozdzielczość. Terminal MUST otwierać wtedy
jedno połączenie na taką parę i rozsyłać z niego do wszystkich odbiorców. Połączenie MUST zostać
zamknięte, gdy odejdzie ostatni odbiorca.

#### Scenario: Dwa sloty na tę samą parę

- **WHEN** dwa sloty siatki pokazują ten sam symbol w tej samej rozdzielczości
- **THEN** terminal utrzymuje jedno połączenie i oba sloty dostają te same wiadomości

#### Scenario: Ostatni odbiorca odchodzi

- **WHEN** znika ostatni widok subskrybujący daną parę
- **THEN** połączenie zostaje zamknięte, zamiast żyć dalej w tle

#### Scenario: Sześć różnych par naraz

- **WHEN** siatka pokazuje sześć różnych par symbol plus rozdzielczość
- **THEN** terminal utrzymuje najwyżej po jednym połączeniu na parę i nie otwiera ich więcej przy
  przerysowaniu widoku

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

### Requirement: Świeca w budowie jest oznaczona jako niepewna

Świeca w budowie zmienia się przy każdym kwotowaniu i po restarcie źródła zaniża swój zakres.
Interfejs MUST przenosić informację, że dana świeca jest w budowie, a odbiorca MUST móc ją odróżnić
od świecy zamkniętej.

#### Scenario: Świeca się zamyka

- **WHEN** przychodzi świeca zamknięta dla okresu, który był w budowie
- **THEN** zastępuje świecę w budowie jako wartość autorytatywna

### Requirement: Zapytanie o dane nazywa swoją porażkę

Odczyt historii i subskrypcja MUST kończyć się błędem, który da się pokazać operatorowi: nieznany
symbol, nieobsługiwana rozdzielczość, źródło nieosiągalne. Komunikat MUST NOT być surowym błędem
sieci i MUST NOT nieść poświadczeń.

#### Scenario: Nieznany symbol

- **WHEN** terminal prosi o historię symbolu, którego źródło nie zna
- **THEN** dostaje błąd nazywający symbol i mówiący, że nie został znaleziony

#### Scenario: Źródło nieosiągalne

- **WHEN** źródło danych nie odpowiada
- **THEN** terminal dostaje błąd mówiący, że źródło jest nieosiągalne, a nie pustą serię świec
