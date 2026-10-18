## Purpose

Reguła opisana zdaniem: model zamienia zdanie operatora na szkic reguły z katalogu, a operator zatwierdza
go jak każdą inną regułę. Model pomaga ją napisać, ale nigdy nie decyduje, że reguła powstaje.

## ADDED Requirements

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
