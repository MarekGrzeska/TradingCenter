# market-mcp-answers Specification

## Purpose
Kształt odpowiedzi każdego narzędzia: ile jej maksymalnie jest, co się dzieje, gdy jest
jej za dużo, jak niesie niepewność archiwum i jak wygląda odmowa, której model ma
posłuchać.
## Requirements
### Requirement: Odpowiedź ma sufit, a odcięcie nie jest ciche

Każde narzędzie MUST mieć górną granicę wielkości swojej odpowiedzi, wpisaną w jego opis.
Żądanie mieszczące się powyżej tej granicy MUST być streszczone — świece agregowane do
grubszych okresów, listy obcinane do najbliższych albo najnowszych — a nie oddane w
całości.

Odcięcie i agregacja MUST być nazwane w treści odpowiedzi: ile pozycji pominięto albo do
jakiego okresu zagregowano. Odpowiedź, która milczy o tym, że jest wycinkiem, zostaje
streszczona operatorowi jako całość.

Żądanie przekraczające granicę na tyle, że streszczenie przestałoby odpowiadać na zadane
pytanie, MUST być odmówione, a odmowa MUST nazwać, co zmniejszyć.

#### Scenario: Zakres większy niż sufit świec

- **WHEN** model prosi o świece z okna, w którym mieści się więcej świec niż sufit
  narzędzia
- **THEN** odpowiedź niesie świece zagregowane do grubszego okresu
- **AND** treść odpowiedzi MUST mówić, że jest zagregowana i do czego

#### Scenario: Lista poziomów dłuższa niż sufit

- **WHEN** obliczenie daje więcej poziomów, niż narzędzie oddaje
- **THEN** odpowiedź niesie te najbliższe cenie
- **AND** MUST podać, ile pozycji pominięto

#### Scenario: Żądanie nie do streszczenia

- **WHEN** żądanie przekracza sufit na tyle, że streszczenie nie odpowiedziałoby na
  pytanie
- **THEN** narzędzie MUST odmówić
- **AND** odmowa MUST nazwać parametr do zmiany — zakres, rozdzielczość albo liczbę
  wskaźników

### Requirement: Niepewność archiwum jedzie w treści odpowiedzi

Archiwum rozróżnia „nie ma świecy, bo rynek był zamknięty" od „nikt nie zweryfikował tego
przedziału", odróżnia serię zebraną od policzonej i wie, kiedy rozgrzewka wskaźnika nie
zmieściła się w historii. Każde z tych rozróżnień MUST dotrzeć do modelu jako zdanie w
treści odpowiedzi, a nie zginąć w streszczeniu.

Pusta seria świec MUST NOT być oddana bez wyjaśnienia. Brak świec czyta się jak cisza
rynku i jest to dokładnie ta jedna pewna zła odpowiedź, przed którą archiwum broni się
całą swoją strukturą.

#### Scenario: Zakres z niezweryfikowanym przedziałem

- **WHEN** odpowiedź obejmuje przedział, którego archiwum nigdy nie zweryfikowało
- **THEN** treść odpowiedzi MUST nazwać ten przedział
- **AND** MUST powiedzieć, że brak świec tam nie znaczy, że rynek stał

#### Scenario: Seria policzona, nie zebrana

- **WHEN** archiwum oddaje serię wyprowadzoną z rozdzielczości drobniejszej
- **THEN** odpowiedź MUST to nazwać

#### Scenario: Wskaźnik bez pełnej rozgrzewki

- **WHEN** wskaźnik został policzony, ale archiwum nie miało dla niego dość historii
- **THEN** odpowiedź MUST nazwać wartość wstępną i podać, ilu świec rozgrzewki zabrakło

### Requirement: Trzy rodzaje „nie wiem" są rozróżnione

Odpowiedź, w której czegoś brakuje, MUST nazywać powód, a moduł MUST rozróżniać co
najmniej trzy: pary nikt nie zbiera, przedziału nikt nie zweryfikował, archiwum nie
odpowiedziało. Model nie ma jak ich rozróżnić, jeśli nie zostaną mu nazwane, a każdy
prowadzi operatora gdzie indziej.

Awaria archiwum MUST NOT być przedstawiona jako brak danych.

#### Scenario: Archiwum nie odpowiada

- **WHEN** wywołanie do archiwum kończy się przekroczeniem czasu albo błędem serwera
- **THEN** odpowiedź MUST nazwać to awarią po stronie modułu
- **AND** MUST NOT przedstawić tego jako braku danych ani jako ciszy rynku

#### Scenario: Para niezbierana kontra rynek zamknięty

- **WHEN** narzędzie nie ma świec do oddania
- **THEN** odpowiedź MUST rozróżnić, czy pary nikt nie zbiera, czy przedział nie został
  zweryfikowany

### Requirement: Odmowa jest odpowiedzią o jednym kształcie

Odmowa MUST być oznaczona jako błąd wywołania narzędzia i MUST nieść zdanie mówiące, co
zrobić inaczej, żeby żądanie się powiodło. Wszystkie narzędzia MUST odmawiać w tym samym
kształcie — model uczy się go raz.

Odmowa pochodząca z archiwum MUST być przepisana w słowach, w których archiwum ją
sformułowało, a nie zastąpiona własnym streszczeniem: te zdania są pisane dla człowieka i
niosą powód.

#### Scenario: Odmowa niesie poprawkę

- **WHEN** narzędzie odmawia wykonania żądania
- **THEN** odpowiedź MUST nazwać parametr, którego zmiana pozwoli żądaniu się powieść

#### Scenario: Odmowa archiwum przepisana

- **WHEN** archiwum odmawia obliczenia i podaje powód
- **THEN** powód MUST znaleźć się w odpowiedzi narzędzia
