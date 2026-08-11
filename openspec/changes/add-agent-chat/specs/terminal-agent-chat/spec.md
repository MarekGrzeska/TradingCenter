## Purpose

Opisuje panel agenta w terminalu jako rzecz, z której operator korzysta: gdzie wisi, jak
przełącza się między rozmowami, jak wybiera model i co widzi, gdy odpowiedź jeszcze
płynie albo już się nie uda.

## ADDED Requirements

### Requirement: Panel należy do terminala, nie do zakładki

Panel agenta MUST być dostępny z każdej zakładki i MUST NOT gubić rozmowy przy jej zmianie:
przejście z wykresu do historii zbierania MUST zostawić transkrypt tam, gdzie był, łącznie
z odpowiedzią, która w tej chwili płynie. Panel rozwinięty MUST odsuwać treść zakładki, a
nie ją zakrywać — operator czyta wykres i rozmowę naraz, bo o wykres pyta.

Stan zwinięcia MUST przetrwać przeładowanie terminala: panel zabiera szerokość wykresom i
operator, który go zamknął, MUST NOT zastać go otwartym.

#### Scenario: Zmiana zakładki w trakcie odpowiedzi

- **WHEN** operator zmienia zakładkę, gdy odpowiedź agenta jeszcze płynie
- **THEN** panel zostaje na ekranie z tą samą rozmową
- **AND** odpowiedź płynie dalej do tego samego dymka

#### Scenario: Przeładowanie terminala

- **WHEN** operator zwija panel i przeładowuje terminal
- **THEN** panel jest zwinięty

### Requirement: Operator wybiera rozmowę albo zaczyna nową

Panel MUST pokazywać listę wcześniejszych rozmów operatora, uporządkowaną od ostatnio
używanej, i MUST pozwalać otworzyć każdą z nich oraz zacząć nową. Otwarcie rozmowy MUST
wczytać jej transkrypt z modułu — transkrypt jest po stronie modułu i przeglądarka MUST NOT
być jego jedynym źródłem.

Terminal MUST pamiętać, która rozmowa była otwarta, i wracać do niej po przeładowaniu.
Operator, który po każdym odświeżeniu ląduje w pustej rozmowie, przestaje panelu używać.

#### Scenario: Powrót do wcześniejszej rozmowy

- **WHEN** operator wybiera rozmowę z listy
- **THEN** panel pokazuje jej transkrypt wczytany z modułu
- **AND** kolejna wypowiedź dopisuje się do tej rozmowy

#### Scenario: Nowa rozmowa

- **WHEN** operator zaczyna nową rozmowę
- **THEN** panel pokazuje pusty transkrypt
- **AND** rozmowa pojawia się na liście dopiero po pierwszej wymianie zdań

#### Scenario: Przeładowanie z otwartą rozmową

- **WHEN** operator przeładowuje terminal z otwartą rozmową
- **THEN** panel wraca do tej samej rozmowy

### Requirement: Model wybiera się w oknie agenta

Panel MUST pozwalać wybrać model dla rozmowy spośród tych, które moduł publikuje, i MUST
pokazywać, którym modelem rozmowa jest prowadzona. Wybierak MUST być zbudowany z katalogu
modułu — terminal MUST NOT nieść listy modeli we własnym kodzie.

Wybierak MUST pokazywać różnicę kosztu między modelami. Wybór między trzema nazwami bez tej
informacji jest zgadywaniem, a różnica między najtańszym a najdroższym jest
dwudziestopięciokrotna.

#### Scenario: Wybór modelu przed pytaniem

- **WHEN** operator wybiera model i wysyła wiadomość
- **THEN** odpowiedź powstaje na wybranym modelu

#### Scenario: Katalog niedostępny

- **WHEN** katalog modeli nie daje się wczytać
- **THEN** panel mówi, że wyboru modelu nie da się teraz pokazać
- **AND** MUST NOT podstawiać listy modeli z własnego kodu

### Requirement: Widać, że odpowiedź powstaje

Panel MUST pokazywać odpowiedź w miarę, jak przychodzi, a przed pierwszym jej fragmentem
MUST pokazywać, że wypowiedź została przyjęta i czekanie trwa. Operator MUST NOT stać przed
niezmienionym ekranem, na którym równie dobrze mogło nic się nie wysłać.

Zerwanie strumienia MUST być widoczne jako błąd, odróżnialny od odpowiedzi zakończonej.
Odpowiedź niepełna MUST być oznaczona jako niepełna, a nie pokazana jako całość.

#### Scenario: Odpowiedź w trakcie

- **WHEN** operator wysyła wiadomość
- **THEN** panel pokazuje, że odpowiedź powstaje, zanim przyjdzie jej pierwszy fragment
- **AND** dopisuje kolejne fragmenty w miarę, jak przychodzą

#### Scenario: Strumień pęka

- **WHEN** strumień zostaje zerwany przed zakończeniem odpowiedzi
- **THEN** panel oznacza odpowiedź jako niepełną i podaje, że wystąpił błąd
- **AND** to, co dotarło, zostaje na ekranie

#### Scenario: Moduł agenta jest nieosiągalny

- **WHEN** moduł agenta nie odpowiada
- **THEN** panel mówi to wprost
- **AND** MUST NOT pokazywać wypowiedzi agenta, która nie powstała
