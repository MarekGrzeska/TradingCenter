## ADDED Requirements

### Requirement: Automatyczne logowanie ma jedno podejście

Terminal MUST podjąć automatyczne logowanie najwyżej raz na jedno wejście na stronę. Powrót
z logowania, które nie skończyło się zalogowaniem, MUST NOT wywołać kolejnego automatycznego
przekierowania — terminal MUST wtedy stwierdzić, że operator nie jest zalogowany, i zostawić
zalogowanie jako decyzję operatora.

Pętla przekierowań jest jedyną poważną ceną tego wygodnego zachowania i jedyną, której operator
nie umie przerwać: strona, która sama wysyła w logowanie po każdym nieudanym powrocie, nie daje się
ani odczytać, ani zamknąć w zwykły sposób.

#### Scenario: Logowanie nie doszło do skutku

- **WHEN** operator wraca z logowania, które się nie powiodło
- **THEN** terminal nie wysyła go tam ponownie
- **AND** pokazuje stan „nie jestem zalogowany" wraz z możliwością zalogowania się na żądanie

#### Scenario: Operator wyszedł z logowania samodzielnie

- **WHEN** operator przerwał logowanie i wrócił do terminala
- **THEN** terminal zostaje na tym, co potrafi pokazać bez tożsamości
- **AND** MUST NOT wysyłać go w logowanie po raz kolejny bez jego decyzji

## MODIFIED Requirements

### Requirement: Operator loguje się kontem organizacji

Terminal MUST pozwolić operatorowi zalogować się kontem organizacji i MUST z tego logowania
uzyskać poświadczenie przeznaczone dla archiwum, a nie dla siebie. Poświadczenie MUST być
odnawiane bez udziału operatora, dopóki jego sesja na to pozwala; dopiero gdy ciche odnowienie się
nie powiedzie, terminal MUST poprosić o ponowne zalogowanie.

Terminal MUST rozpocząć logowanie sam, gdy tożsamość jest skonfigurowana, a operator nie jest
zalogowany. Bez tożsamości terminal nie pokaże ani świecy, ani instrumentu, ani historii — czekanie,
aż operator znajdzie przycisk w rogu ekranu, każe mu odgadnąć jedyną rzecz, jaką i tak trzeba zrobić.
Nie dotyczy to tożsamości nieskonfigurowanej: terminal MUST NOT wywoływać wtedy logowania w ogóle,
bo nie ma dokąd wysłać ani po co.

Stan zalogowania MUST być widoczny w powłoce, obok stanu źródeł danych — operator, który nie
widzi świec, MUST móc odróżnić „archiwum nie odpowiada" od „nie jestem zalogowany", bo są to
dwie różne sytuacje z dwiema różnymi odpowiedziami. Wskaźnik MUST zostawiać zalogowanie na żądanie
także wtedy, gdy automatyczne logowanie już się nie powiodło.

#### Scenario: Pierwsze wejście do terminala

- **WHEN** operator otwiera terminal ze skonfigurowaną tożsamością i nie jest zalogowany
- **THEN** terminal sam rozpoczyna logowanie kontem organizacji, bez działania operatora
- **AND** po powrocie z logowania pokazuje widok, na który operator wchodził, a nie stronę startową

#### Scenario: Uruchomienie bez skonfigurowanej tożsamości

- **WHEN** operator otwiera terminal, w którym tożsamość nie jest skonfigurowana
- **THEN** żadne logowanie się nie zaczyna
- **AND** terminal pokazuje dane tak samo jak dotąd

#### Scenario: Poświadczenie wygasa w trakcie pracy

- **WHEN** poświadczenie traci ważność, a sesja operatora jest nadal ważna
- **THEN** terminal odnawia je po cichu
- **AND** operator nie widzi ani logowania, ani przerwy w danych

#### Scenario: Sesja wygasła

- **WHEN** ciche odnowienie poświadczenia się nie powiedzie
- **THEN** terminal stwierdza, że operator nie jest zalogowany, i proponuje zalogowanie
- **AND** MUST NOT pokazywać tego jako niedostępności archiwum
