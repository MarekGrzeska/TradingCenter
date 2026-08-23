## MODIFIED Requirements

### Requirement: Zestaw zmienia wyłącznie listę obserwacji

Zestaw MUST zawierać narzędzia czytające publiczną bazę dostawcy i własne archiwum oraz narzędzia
zmieniające **wyłącznie listę obserwacji**: objęcie wydarzenia obserwacją i utworzenie grupy.
Żadne inne narzędzie zmieniające stan MUST NOT być publikowane.

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
i ograniczone: tam zapisem byłoby mutowanie archiwum świec, tu zapisem jest dopisanie do listy
obserwacji — dokładnie to, co operator klika w terminalu. Ograniczenie MUST być sprawdzane testem,
a nie pilnowane przy review: narzędzia stoją w tym samym procesie co zapis, więc kasujące
wywołanie jest o jeden import stąd.

#### Scenario: Lista narzędzi nie zawiera kasowania

- **WHEN** klient MCP prosi o listę narzędzi
- **THEN** na liście MUST NOT być narzędzia kasującego historię, usuwającego obserwację,
  zmieniającego konfigurację ani dotykającego rachunku
- **AND** jedyne narzędzia zmieniające stan dopisują do listy obserwacji albo tworzą grupę

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

- **WHEN** kod narzędzia wywołuje operację zmieniającą stan inny niż dopisanie obserwacji i grup
- **THEN** MUST to wywrócić testy modułu, zanim zmiana zostanie wdrożona
