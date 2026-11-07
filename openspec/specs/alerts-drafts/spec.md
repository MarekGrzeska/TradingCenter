# alerts-drafts Specification

## Purpose
Reguła opisana zdaniem: model zamienia zdanie operatora na szkic reguły z katalogu, a operator zatwierdza
go jak każdą inną regułę. Model pomaga ją napisać, ale nigdy nie decyduje, że reguła powstaje.
## Requirements
### Requirement: Zdanie może zmieniać istniejącą regułę

Operator MUST móc podać razem ze zdaniem identyfikator istniejącej reguły i dostać szkic tej reguły ze zmianą z
tego zdania, w tej samej strukturze co każdy szkic. Pola, których zdanie nie dotyczy, MUST zostać takie, jakie były,
także te, których model nie wypełnia (bot, sufit na godzinę, włączenie). Szkic zmiany MUST przechodzić tę samą
walidację co zapis i MUST NOT zmieniać żadnej reguły; zużyte tokeny MUST wchodzić w ten sam dobowy sufit. Nieznany
identyfikator MUST być odmową „nie ma takiej reguły”, bez pytania modelu.

#### Scenario: Zmiana progu

- **WHEN** operator pisze „podnieś próg do 1,12” do reguły EURUSD powyżej 1,10 wysyłanej przez wskazanego bota
- **THEN** szkic MUST mieć próg 1,12, a instrument, adresata, bota i czas martwy tej reguły bez zmian
- **AND** reguła w bazie MUST pozostać z progiem 1,10

#### Scenario: Reguła, której nie ma

- **WHEN** operator prosi o zmianę reguły o identyfikatorze, którego nie ma
- **THEN** odpowiedź MUST być odmową, a model MUST NOT zostać zapytany

### Requirement: Szkic jest propozycją, nigdy zapisem

Operator MUST móc podać zdanie i dostać szkic reguły w tej samej strukturze, którą przyjmuje zapis.
Utworzenie szkicu MUST NOT tworzyć ani zmieniać żadnej reguły. Regułę ze szkicu tworzy wyłącznie
zapis wykonany przez operatora.

#### Scenario: Zdanie o cenie

- **WHEN** operator pisze „daj znać, gdy EURUSD przebije 1,10 w górę, nie częściej niż raz na godzinę”
- **THEN** odpowiedź MUST być szkicem reguły stanu z instrumentem EURUSD, porównaniem „powyżej”, progiem 1,10 i czasem martwym jednej godziny
- **AND** lista reguł MUST pozostać bez zmian

### Requirement: Szkic przechodzi tę samą walidację co zapis

Szkic MUST zostać sprawdzony walidacją zapisu reguły, zanim trafi do operatora. Szkic, który jej nie
przechodzi, MUST zostać zwrócony razem z nazwanymi wadami, a nie odrzucony bez słowa. Szkic MUST
odwoływać się wyłącznie do narzędzi, typów zdarzeń, atrybutów, instrumentów i adresatów, które
katalog i brama znają w chwili tworzenia.

#### Scenario: Zdanie o nieśledzonym instrumencie

- **WHEN** operator pisze o instrumencie, którego archiwum nie śledzi
- **THEN** szkic MUST nazwać ten instrument jako wadę, zamiast podstawić inny

#### Scenario: Zdanie bez adresata

- **WHEN** zdanie nie mówi, komu wysłać, a brama zna jednego odbierającego adresata
- **THEN** szkic MUST wskazać tego adresata i MUST powiedzieć, że został wybrany domyślnie

### Requirement: Brak klucza modelu jest konfiguracją wspieraną

Gdy klucz modelu pakietu nie jest ustawiony, pakiet MUST działać w całości poza szkicami. Prośba o
szkic MUST być wtedy odmową nazywającą brakujące ustawienie, a trasa stanu MUST mówić, że szkice są
niedostępne.

#### Scenario: Prośba o szkic bez klucza

- **WHEN** operator prosi o szkic, a klucz modelu nie jest ustawiony
- **THEN** odpowiedź MUST być odmową nazywającą ustawienie, a reguły MUST działać dalej

### Requirement: Szkice mają dobowy sufit kosztu

Pakiet MUST zapisywać zużycie tokenów każdego szkicu i MUST odmówić kolejnego szkicu po przekroczeniu
dobowego sufitu z ustawień, nazywając sufit.

#### Scenario: Sufit wyczerpany

- **WHEN** zużycie szkiców z bieżącej doby osiągnęło sufit
- **THEN** prośba o szkic MUST być odmową nazywającą sufit, a zapis reguły z formularza MUST działać

