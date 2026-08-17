## MODIFIED Requirements

### Requirement: Operator zarządza naniesionymi obiektami z listy

Terminal MUST pokazywać listę obiektów naniesionych na instrument aktywnego slotu: kształt,
ceny, etykietę i to, kiedy powstały. Lista jest jedyną drogą, którą operator cofa to, co
narysował agent (`agent-tools`, „Agent zapisuje w widoku terminala i na rachunku
demonstracyjnym"), więc MUST być dostępna bez rozmowy z agentem.

Operator MUST móc z listy usunąć pojedynczy obiekt oraz poprawić jego ceny i etykietę.
Skutek MUST być widoczny na wykresie od razu, bez przeładowania strony.

Operator MUST móc z listy **zgasić i zapalić** pojedynczy obiekt, nie usuwając go. Lista
MUST pokazywać obiekty zgaszone razem z zapalonymi i MUST mówić, które są które: obiekt
zgaszony nie jest rysowany, więc lista jest jedyną drogą, którą da się go zapalić
z powrotem, a lista, która go pomija, gasi go bezpowrotnie.

Nieudane usunięcie, nieudana poprawka albo nieudane zgaszenie MUST zostać powiedziane,
a lista i wykres MUST zostać takie, jakie były — obiekt, który zniknął z ekranu, ale nie
z zapisu, wróciłby przy następnym odczycie i czytałby się jak usterka.

Instrument bez naniesionych obiektów MUST dawać pustą listę mówiącą, że nic nie jest
naniesione — a nie brak listy, którego nie da się odróżnić od nieudanego odczytu.
Instrument, na którym wszystko jest zgaszone, MUST NOT czytać się jak instrument bez
obiektów.

#### Scenario: Operator usuwa poziom z listy

- **WHEN** operator usuwa poziom z listy obiektów
- **THEN** poziom znika z wykresu od razu
- **AND** nie wraca po odświeżeniu strony

#### Scenario: Operator poprawia cenę z listy

- **WHEN** operator zmienia cenę obiektu na liście
- **THEN** obiekt rysuje się na nowej cenie

#### Scenario: Operator gasi poziom z listy

- **WHEN** operator gasi poziom na liście obiektów
- **THEN** poziom znika z wykresu od razu
- **AND** zostaje na liście, oznaczony jako zgaszony

#### Scenario: Operator zapala poziom z listy

- **WHEN** operator zapala zgaszony poziom na liście obiektów
- **THEN** poziom jest znowu na wykresie

#### Scenario: Usunięcie się nie powiodło

- **WHEN** usunięcie obiektu kończy się błędem
- **THEN** obiekt zostaje na liście i na wykresie
- **AND** terminal mówi, że usunięcie się nie powiodło

#### Scenario: Zgaszenie się nie powiodło

- **WHEN** zgaszenie obiektu kończy się błędem
- **THEN** obiekt jest nadal zapalony na liście i na wykresie
- **AND** terminal mówi, że się nie powiodło

#### Scenario: Instrument bez obiektów

- **WHEN** aktywny slot pokazuje instrument, na który nic nie naniesiono
- **THEN** lista mówi, że nic nie jest naniesione

#### Scenario: Instrument z samymi zgaszonymi obiektami

- **WHEN** aktywny slot pokazuje instrument, na którym wszystkie obiekty są zgaszone
- **THEN** lista pokazuje je wszystkie jako zgaszone
- **AND** nie mówi, że nic nie jest naniesione
