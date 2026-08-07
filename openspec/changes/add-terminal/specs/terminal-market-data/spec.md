## Purpose

Jedno wejście na świece i strumień dla całego terminala: skąd biorą się dane, jak historia zszywa
się z tym, co przychodzi na żywo, i jak wiele wykresów patrzących na to samo dzieli jedno
połączenie zamiast otwierać po jednym każdy.

## ADDED Requirements

### Requirement: Źródło danych jest wymienne za jednym interfejsem

Terminal MUST czytać świece i strumień wyłącznie przez jeden interfejs, opisujący odczyt historii
i subskrypcję na żywo. MUST istnieć co najmniej dwie implementacje tego interfejsu: czytająca z
`capital-gateway` oraz mock generujący dane bez sieci. Żaden widok MUST NOT wiedzieć, która
implementacja go obsługuje.

#### Scenario: Przełączenie źródła

- **WHEN** operator przełącza źródło danych w interfejsie
- **THEN** wykresy i wyszukiwarka zaczynają czytać z nowego źródła
- **AND** nie wymaga to zmiany w żadnym widoku

#### Scenario: Dołożenie trzeciego źródła

- **WHEN** pojawia się kolejna implementacja interfejsu, na przykład czytająca z bazy świec
- **THEN** wpięcie jej MUST NOT wymagać zmian w wykresie, w siatce ani w wyszukiwarce

#### Scenario: Praca bez gatewaya

- **WHEN** `capital-gateway` jest nieosiągalny, a wybrane źródło to mock
- **THEN** terminal działa w całości: rysuje świece, zmienia interwały i pokazuje ruch na żywo

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
(łączenie, połączony, wznawianie, zamknięty) MUST być dostępny odbiorcom. Po wznowieniu terminal
MUST domknąć lukę w świecach, zamiast zostawić dziurę w serii.

#### Scenario: Połączenie pada

- **WHEN** strumień się zrywa
- **THEN** odbiorcy widzą stan wznawiania, a terminal ponawia próby z rosnącym odstępem

#### Scenario: Połączenie wraca

- **WHEN** strumień zostaje wznowiony po przerwie
- **THEN** terminal dociąga świece z okresu przerwy i uzupełnia nimi serię
- **AND** odbiorcy widzą stan połączony

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
