# teams-mcp-tools Specification

## Purpose
Co model dostaje do ręki, kiedy operator prosi o zespół zdaniem zamiast formularzem: zestaw
narzędzi mówiący językiem zadania, a nie językiem tras HTTP modułu `teams`, i granica między
tym, co narzędzie robi, a tym, o czym musi powiedzieć.
## Requirements
### Requirement: Zestaw jest zredukowany do zadań operatora, nie odwzorowuje tras

Zestaw narzędzi MUST być mniejszy niż powierzchnia HTTP modułu `teams` i MUST być pogrupowany
wedle tego, co operator chce zrobić — założyć zespół, poprawić go, uruchomić, przeczytać
wynik — a nie wedle tego, jak `teams` dzieli swoje trasy. Narzędzie MUST NOT wymagać od modelu
złożenia dwóch wywołań tam, gdzie operator wypowiedział jedno życzenie.

Katalog, w którym „załóż zespół" to trzy wywołania w ustalonej kolejności, jest katalogiem, w
którym model pomyli kolejność — a każda pomyłka kosztuje turę i pieniądze. Redukcja jest tą
samą zasadą, którą `market-mcp` stosuje wobec `market-data`, przeniesioną na moduł, którego
trasy są liczniejsze i bardziej ze sobą splecione.

#### Scenario: Zespół zakładany jednym wywołaniem

- **WHEN** operator opisuje zespół zdaniem, a model woła narzędzie zakładające zespół
- **THEN** powstaje zespół wraz z jego pierwszą rewizją
- **AND** odpowiedź niesie identyfikator zespołu i rewizji, wystarczający do kolejnego kroku

#### Scenario: Poprawka nie wymaga odczytania całej definicji

- **WHEN** model poprawia jedną rolę w istniejącym zespole
- **THEN** MUST móc to zrobić bez przepisywania niezmienionych ról
- **AND** powstaje nowa rewizja, a poprzednia zostaje nietknięta

### Requirement: Narzędzie zapisujące jest oznaczone jako zmieniające stan

Każde narzędzie, które tworzy albo zmienia cokolwiek w module `teams`, MUST być ogłoszone jako
zmieniające stan. Narzędzie wyłącznie czytające MUST być ogłoszone jako czytające.

Oznaczenie nie jest ozdobą: `teams` odmawia harmonogramu nad rewizją z narzędziem, którego nie
potwierdzi jako odczyt, i czyta to z ogłoszenia serwera. Serwer, który nie oznacza swoich
narzędzi, przenosi tę decyzję na zgadywanie po drugiej stronie.

#### Scenario: Katalog rozróżnia odczyt od zapisu

- **WHEN** konsument czyta ogłoszony katalog narzędzi
- **THEN** przy każdym narzędziu widać, czy zmienia stan
- **AND** narzędzia zakładające zespół, zapisujące rewizję, uruchamiające przebieg i
  zakładające harmonogram są oznaczone jako zmieniające stan

### Requirement: Opis narzędzia jest częścią kontraktu

Opis każdego narzędzia MUST nieść to, czego model potrzebuje, żeby wołać je poprawnie bez
zgadywania: co narzędzie robi, czego wymaga, co odpowiada i czego **nie** zrobi. Opis MUST
nazywać granice, które zatrzymają wywołanie — dobową granicę kosztu zespołu i granice handlowe.

Model nie ma innego źródła wiedzy o tym module niż te zdania. Opis, który przemilcza granicę,
zamienia odmowę modułu w niespodziankę, którą model tłumaczy operatorowi zgadywaniem.

#### Scenario: Opis niesie warunki odmowy

- **WHEN** model czyta opis narzędzia uruchamiającego przebieg
- **THEN** opis mówi, że przebieg może zostać odmówiony przez dobową granicę kosztu zespołu
- **AND** mówi, że odmowa nazywa liczbę, która ją spowodowała

### Requirement: Zestaw odpowiada na pytania o to, co się wydarzyło

Zestaw MUST umożliwiać odczytanie śladu przebiegu — kto pracował, co odpowiedział, jakie
narzędzia wołał, ile to kosztowało — w kształcie, z którego model może wyciągnąć wniosek o
poprawce. Odczyt śladu MUST być możliwy bez uruchamiania czegokolwiek.

Poprawianie zespołu jest powodem, dla którego ta zmiana powstaje. Zestaw pozwalający tylko
zakładać i uruchamiać zostawia najdroższą część pracy tam, gdzie jest dzisiaj.

#### Scenario: Model czyta ślad zakończonego przebiegu

- **WHEN** operator pyta, dlaczego przebieg wyszedł tak, jak wyszedł
- **THEN** model MUST móc odczytać ślad tego przebiegu i jego koszt
- **AND** MUST NOT musieć w tym celu uruchamiać przebiegu ponownie

#### Scenario: Przebieg wciąż trwa

- **WHEN** model czyta ślad przebiegu, który jeszcze pracuje
- **THEN** dostaje stan bieżący wraz z informacją, że przebieg nie jest zakończony
- **AND** MUST NOT przedstawić stanu częściowego jako wyniku końcowego

### Requirement: Harmonogram założony przy wyłączonym zegarze mówi o tym wprost

Narzędzie zakładające harmonogram albo wyzwalacz MUST powiedzieć, gdy budzenie się modułu
`teams` jest wyłączone ustawieniem. Zapis MUST się mimo to udać.

Harmonogram zapisany do bazy, o którym operator sądzi, że działa, jest gorszy niż odmowa —
a zegar jest dziś na produkcji wyłączony i pozostanie wyłączony, dopóki ktoś nie zobaczy jego
pierwszego wyzwolenia.

#### Scenario: Zegar wyłączony

- **WHEN** model zakłada harmonogram, a budzenie się modułu `teams` jest wyłączone
- **THEN** harmonogram zostaje zapisany
- **AND** odpowiedź narzędzia mówi, że nic nie wyzwoli, dopóki zegar nie zostanie włączony

### Requirement: Zestaw obejmuje zarządzanie harmonogramem, nie samo jego założenie

Zestaw MUST pozwalać modelowi zatrzymać, wznowić, poprawić i usunąć harmonogram oraz
wyzwalacz — nie tylko go założyć. Poprawka MUST NOT wymagać usunięcia i założenia od nowa:
harmonogram poprawiony zachowuje swoją historię wyzwoleń, a założony od nowa jej nie ma.

Operator, który zakłada harmonogram zdaniem, poprawia go też zdaniem. Zestaw, który umie
tylko zakładać, zostawia katalog rosnący w jedną stronę i odsyła do terminala po każdą
zmianę — a wtedy zdanie w rozmowie jest krótszą drogą do drugiego harmonogramu niż do
poprawienia pierwszego.

Narzędzie usuwające MUST nazywać w swoim opisie to, co usunięcie zabiera nieodwracalnie
(historię wyzwoleń) i czego nie rusza (przebiegi), bo model nie ma innego źródła tej wiedzy.

#### Scenario: Model zatrzymuje harmonogram

- **WHEN** operator prosi, żeby harmonogram przestał na razie chodzić
- **THEN** model ma narzędzie, którym go wyłącza, bez usuwania
- **AND** ten sam harmonogram daje się wznowić

#### Scenario: Poprawka zachowuje wpis

- **WHEN** model zmienia porę harmonogramu
- **THEN** harmonogram zostaje ten sam, z tą samą historią
- **AND** nie powstaje drugi wpis

#### Scenario: Model usuwa wyzwalacz

- **WHEN** operator prosi o usunięcie wyzwalacza
- **THEN** model ma narzędzie, którym go usuwa
- **AND** odpowiedź mówi, że historia wyzwoleń zniknęła razem z nim

#### Scenario: Opis narzędzia usuwającego mówi, co znika

- **WHEN** model czyta opis narzędzia usuwającego harmonogram
- **THEN** opis mówi, że historia wyzwoleń znika bezpowrotnie
- **AND** mówi, że przebiegi i ich koszt zostają
