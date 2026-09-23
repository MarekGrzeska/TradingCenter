# polymarket-data-tools Specification

## Purpose
Zestaw narzędzi, który moduł publikuje klientowi MCP: na jakie pytania o rynki predykcyjne
odpowiada, co wolno mu zmienić — i czego nie ma w nim nigdy.
## Requirements
### Requirement: Zestaw zmienia wyłącznie listę obserwacji

Zestaw MUST zawierać narzędzia czytające publiczną bazę dostawcy i własne archiwum oraz narzędzia
zmieniające **wyłącznie listę obserwacji i jej grupy**: objęcie wydarzenia obserwacją, utworzenie,
przemianowanie i skasowanie grupy oraz przeniesienie obserwowanego wydarzenia do innej grupy albo
poza wszystkie. Żadne inne narzędzie zmieniające stan MUST NOT być publikowane.

Grupa jest wyłącznie sposobem porządkowania listy i nie wisi na niej żadna zebrana dana, dlatego
narzędzie MAY grupę skasować — ale skasowanie grupy MUST NOT kończyć żadnej obserwacji ani usuwać
żadnej próbki: wydarzenia wracają bez grupy albo trafiają najpierw do grupy wskazanej przez model.
Narzędzie kasujące grupę MUST być jedynym w zestawie oznaczonym jako destrukcyjne.

W szczególności żadne narzędzie MUST NOT kasować zebranej historii, MUST NOT usuwać obserwacji,
MUST NOT zmieniać konfiguracji modułu i MUST NOT sięgać po cokolwiek związanego z rachunkiem,
zleceniem albo pozycją — ten system na Polymarkecie niczego nie handluje i granica przebiega tam,
gdzie zaczynałby się pieniądz.

**Zdjęcie obserwacji z listy MUST NOT być osiągalne narzędziem**, i jest to zaostrzenie tej
reguły, nie jej ominięcie. Odkąd jedyne wyjście z listy zabiera ze sobą całą zebraną historię,
narzędzie zdejmujące obserwację byłoby narzędziem kasującym historię — dokładnie tym, czego
zdanie wyżej zabrania. Model, który uderzy w sufit obserwacji, MUST dostać odmowę odsyłającą go do
operatora, a MUST NOT robić sobie miejsca kosztem obserwacji, której nie zakładał.

Odstępstwo od reguły „zestaw wyłącznie czyta", którą trzyma `market-data-tools`, jest tu świadome
i ograniczone: tam zapisem byłoby mutowanie archiwum świec, tu zapisem jest lista obserwacji i jej
porządek — dokładnie to, co operator klika w terminalu. Ograniczenie MUST być sprawdzane testem,
a nie pilnowane przy review: narzędzia stoją w tym samym procesie co zapis, więc kasujące
wywołanie jest o jeden import stąd.

#### Scenario: Lista narzędzi nie zawiera kasowania

- **WHEN** klient MCP prosi o listę narzędzi
- **THEN** na liście MUST NOT być narzędzia kasującego historię, usuwającego obserwację,
  zmieniającego konfigurację ani dotykającego rachunku
- **AND** jedyne narzędzia zmieniające stan dopisują do listy obserwacji albo zmieniają jej grupy

#### Scenario: Model kasuje grupę

- **WHEN** model kasuje grupę, do której przypisane są wydarzenia
- **THEN** wydarzenia pozostają obserwowane wraz z całą zebraną historią
- **AND** trafiają do grupy wskazanej przez model albo zostają bez grupy

#### Scenario: Model prosi o skasowanie danych

- **WHEN** model formułuje prośbę „przestań obserwować to wydarzenie i skasuj jego historię"
- **THEN** odpowiedź nazywa usunięcie obserwacji czynnością operatora w terminalu, a nie chwilową
  odmową
- **AND** MUST NOT zdejmować obserwacji z listy ani w części, ani w całości

#### Scenario: Model uderza w sufit obserwacji

- **WHEN** model próbuje objąć obserwacją wydarzenie, a sufit obserwacji jest osiągnięty
- **THEN** odmowa MUST powiedzieć, że zwolnienie miejsca należy do operatora
- **AND** MUST NOT wskazywać modelowi narzędzia, którym zdjąłby cudzą obserwację

#### Scenario: Narzędzie sięga poza listę obserwacji

- **WHEN** kod narzędzia wywołuje operację zmieniającą stan inny niż lista obserwacji i jej grupy
- **THEN** MUST to wywrócić testy modułu, zanim zmiana zostanie wdrożona

### Requirement: Zestaw domyka drogę od pytania do obserwacji

Zestaw MUST pozwalać modelowi dojść od pytania operatora do obserwacji bez wiedzy zdobytej gdzie
indziej: znaleźć wydarzenia po frazie, przejrzeć publiczną bazę kategoriami dostawcy z porządkiem
i stronicowaniem, sprawdzić, co już jest obserwowane, objąć wybrane obserwacją i przypisać je do
grupy. Model MUST NOT musieć znać identyfikatora wydarzenia z góry ani zgadywać fraz, gdy operator
pyta o całą kategorię.

Zestaw MUST pozwalać odczytać to, co zebrano: strukturę obserwowanego wydarzenia z ostatnimi cenami
wszystkich wyników, historię ceny wyniku w oknie i zmiany w oknach. Odpowiedź o cenie MUST nieść
moment, z którego pochodzi, i wiek tej ceny — cena bez momentu jest liczbą, o której nie wiadomo,
czy opisuje teraz, czy zeszły tydzień.

Odpowiedź MUST odróżniać dane własne od danych pobranych od dostawcy na żywo.

#### Scenario: Operator pyta o kategorię, nie o wydarzenie

- **WHEN** operator prosi o rynki dotyczące pewnego tematu, a model nie zna żadnego wydarzenia
- **THEN** zestaw pozwala mu przejrzeć publiczną bazę kategoriami i porządkiem, nie tylko frazą
- **AND** wynik wskazuje, które z wydarzeń są już obserwowane

#### Scenario: Model obejmuje wydarzenie obserwacją

- **WHEN** model obejmuje obserwacją wybrane wydarzenie i przypisuje je do grupy
- **THEN** obserwacja jest tą samą obserwacją, którą widzi operator w terminalu
- **AND** próbkowanie i uzupełnianie przeszłości ruszają bez dalszego wywołania

#### Scenario: Cena niesie swój wiek

- **WHEN** narzędzie odpowiada ostatnią ceną wyniku
- **THEN** odpowiedź MUST nieść moment tej ceny i to, ile czasu od niego minęło

#### Scenario: Pytanie o wydarzenie nieobserwowane

- **WHEN** model pyta o historię wydarzenia, którego moduł nie obserwuje
- **THEN** odpowiedź MUST nazwać to wprost i odesłać do narzędzia obejmującego obserwacją
- **AND** MUST NOT podstawić w jego miejsce danych pobranych na żywo jako historii archiwum

### Requirement: Zapis przez narzędzie podlega tym samym granicom co zapis operatora

Sufit liczby obserwowanych wydarzeń, odmowa dla wydarzenia nieznanego dostawcy i niepodzielność
objęcia obserwacją MUST obowiązywać narzędzie dokładnie tak samo jak kontrakt REST. Odmowa wobec
modelu MUST nazywać przyczynę na tyle wprost, żeby model mógł zaproponować operatorowi następny
krok — w szczególności odmowa z powodu sufitu MUST powiedzieć, że najpierw trzeba zakończyć inną
obserwację.

Zapis dokonany narzędziem MUST zostawiać ślad odróżniający go od zapisu dokonanego przez operatora.

#### Scenario: Model przekracza sufit

- **WHEN** model obejmuje obserwacją wydarzenie ponad sufit
- **THEN** dostaje odmowę mówiącą, że sufit został osiągnięty i co trzeba zrobić najpierw
- **AND** żadna dotychczasowa obserwacja nie zostaje zmieniona

#### Scenario: Ślad zapisu narzędziem

- **WHEN** obserwacja powstaje przez wywołanie narzędzia
- **THEN** zapis odnotowuje, że decyzja przyszła tą powierzchnią

### Requirement: Opis narzędzia jest częścią kontraktu

Opis narzędzia jest jedyną rzeczą, którą model o nim wie, więc MUST być traktowany jak kontrakt.
Każde publikowane narzędzie MUST nieść opis, typowane parametry, wpisany sufit swojej odpowiedzi
oraz jawnie nazwane jednostki i strefę czasową.

Cena wyniku jest prawdopodobieństwem, nie kwotą, i jej skala MUST być nazwana w opisie —
narzędzie oddające 0,62 tam, gdzie model spodziewa się 62, myli się o dwa rzędy wielkości bez
jednego błędu po drodze.

#### Scenario: Narzędzie bez kompletnego opisu

- **WHEN** do zestawu trafia narzędzie bez opisu, bez wpisanego sufitu albo bez nazwanej skali ceny
- **THEN** MUST to wywrócić test powierzchni narzędzi, zanim moduł zostanie wdrożony

#### Scenario: Czas jest jednoznaczny

- **WHEN** narzędzie przyjmuje albo zwraca moment w czasie
- **THEN** jego opis MUST nazywać strefę, a odpowiedź MUST podawać moment w UTC

### Requirement: Powierzchnia narzędzi ma zapisany sufit

Cały zestaw — opisy, schematy wejścia i schematy wyjścia razem — jest czytany przez model
w **każdej** turze rozmowy, a ten moduł jest trzecim serwerem narzędzi w tym systemie, więc jego
rozmiar dokłada się do dwóch pozostałych. Moduł MUST trzymać zserializowaną postać tego, co
ogłasza, poniżej sufitu zapisanego w jego własnym teście, i MUST wywrócić ten test, gdy sufit
zostanie przekroczony.

Podniesienie sufitu MUST być świadomą zmianą tego testu, nie skutkiem ubocznym dodania narzędzia.

Schemat odpowiedzi MUST być publikowany i MUST być sprawdzany wobec tego, co narzędzie naprawdę
oddaje.

#### Scenario: Zestaw urósł ponad sufit

- **WHEN** zmiana dokłada narzędzie, pole albo akapit opisu, po którym zserializowany zestaw
  przekracza sufit
- **THEN** test powierzchni narzędzi MUST wywrócić się, nazywając zmierzoną wielkość i sufit

#### Scenario: Odpowiedź niezgodna z ogłoszonym schematem

- **WHEN** narzędzie oddaje odpowiedź, której ogłoszony schemat nie opisuje
- **THEN** MUST to wywrócić testy modułu, a nie ujawnić się dopiero przy realnym wywołaniu

### Requirement: Narzędzie pyta, zanim utworzy grupę podobną do istniejącej

Zestaw MUST pozwalać modelowi odczytać istniejące grupy, zanim nazwie nową. Nazwa różniąca się od
istniejącej wyłącznie wielkością liter albo białymi znakami MUST wskazywać tę istniejącą grupę, a
MUST NOT tworzyć drugiej.

Nazwa, która istniejącej grupy nie wskazuje, ale ją **przypomina**, MUST być odmową niosącą listę
podobnych grup — i dotyczy to zarówno tworzenia grupy, jak i objęcia obserwacją z nową grupą.
Model MAY taką grupę utworzyć, jawnie potwierdzając, że chodzi o inną kategorię. Reguła jest
tylko narzędzia: operator w terminalu wpisuje nazwę świadomie i kontrakt REST jej nie stosuje.

Model zostawiony sam sobie tworzył tę samą kategorię w kilku pisowniach, a sprzątał operator.

#### Scenario: Ta sama nazwa w innej pisowni

- **WHEN** model tworzy grupę „ crypto ", a istnieje grupa „Crypto"
- **THEN** odpowiedź wskazuje istniejącą grupę „Crypto" i mówi, że niczego nie utworzono

#### Scenario: Nazwa podobna do istniejącej

- **WHEN** model tworzy grupę „tariff", a istnieje grupa „Tariffs"
- **THEN** odpowiedź jest odmową niosącą „Tariffs" jako podobną grupę
- **AND** grupa „tariff" powstaje dopiero, gdy model potwierdzi, że chodzi o inną kategorię

#### Scenario: Objęcie obserwacją z podobną grupą

- **WHEN** model obejmuje wydarzenie obserwacją z grupą przypominającą istniejącą
- **THEN** odpowiedź jest odmową niosącą podobne grupy
- **AND** obserwacja nie powstaje

