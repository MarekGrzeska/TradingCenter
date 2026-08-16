## MODIFIED Requirements

### Requirement: Rysunki są trwałe i mają własną tożsamość

Każdy rysunek MUST dostać identyfikator, po którym da się go wskazać, oraz MUST zostać
zapisany wraz z chwilą powstania i sesją rozmowy, w której padł.

Zapis MUST przeżyć restart modułu i odświeżenie przeglądarki. Rysunek postawiony przed
tygodniem MUST dać się odczytać tak samo jak postawiony przed sekundą — to jest cała
różnica między rysunkiem a poleceniem wykresu, które opisuje jedną chwilę.

Każdy rysunek MUST nieść **stan widoczności**: zgaszony rysunek nie jest rysowany, ale
nadal istnieje. Zgaszenie MUST NOT zmienić niczego innego w rysunku — ani jego
identyfikatora, ani chwili powstania, ani cen, etykiety czy koloru — bo zapalony z powrotem
MUST być dokładnie tym samym rysunkiem. Bez tego jedyną drogą do czystego wykresu jest
kasowanie, czyli utrata wszystkiego, czego rysunek dotąd dorobił się poza swoją ceną.

Stan widoczności MUST należeć do rysunku, nie do ekranu: MUST przeżyć to samo, co sam
rysunek — odświeżenie strony, restart modułu i zmianę rozmowy — i MUST być ten sam
wszędzie tam, gdzie ten rysunek widać. Widoczność trzymana per ekran byłaby drugą
odpowiedzią na pytanie „czy to jest naniesione", a rysunek należy do instrumentu, nie do
widoku.

Liczba rysunków na jednym instrumencie MUST być ograniczona z góry, a sufit MUST liczyć
także zgaszone. Wykres, na którym stoi kilkaset linii, nie pokazuje niczego, a odczyt bez
kresu jest odczytem, którego rozmiaru nikt nie zna; sufit, który da się obejść gaszeniem,
nie jest sufitem.

#### Scenario: Rysunek przeżywa odświeżenie strony

- **WHEN** operator odświeża terminal po tym, jak agent postawił poziom
- **THEN** poziom jest nadal na wykresie

#### Scenario: Rysunek przeżywa rozmowę

- **WHEN** operator zaczyna nową rozmowę po tym, jak w poprzedniej powstały rysunki
- **THEN** rysunki są nadal na wykresie i nadal dają się odczytać

#### Scenario: Zgaszenie przeżywa odświeżenie strony

- **WHEN** operator odświeża terminal po zgaszeniu poziomu
- **THEN** poziom jest nadal zgaszony

#### Scenario: Zapalony rysunek jest tym samym rysunkiem

- **WHEN** rysunek zostaje zgaszony, a potem zapalony z powrotem
- **THEN** ma ten sam identyfikator, tę samą chwilę powstania, te same ceny, etykietę i kolor

#### Scenario: Sufit rysunków na instrumencie

- **WHEN** agent próbuje postawić rysunek na instrumencie, który ma ich już tyle, ile wynosi sufit
- **THEN** rysunek nie powstaje, a agent dostaje odmowę mówiącą o suficie

#### Scenario: Zgaszone liczą się do sufitu

- **WHEN** agent próbuje postawić rysunek na instrumencie, który ma tyle rysunków, ile wynosi sufit, z czego część zgaszonych
- **THEN** rysunek nie powstaje

### Requirement: Agent stawia i kasuje rysunki narzędziem

Moduł MUST publikować modelowi narzędzie, którym stawia rysunki i kasuje istniejące,
wskazując je identyfikatorem. Tym samym narzędziem MUST dać się rysunek **zgasić
i zapalić**, wskazując go identyfikatorem tak samo jak przy kasowaniu.

Gaszenie i kasowanie MUST być dwiema różnymi operacjami, a nie jedną: model proszony
o schowanie linii, który ma tylko kasowanie, kasuje — i to jest dokładnie ta strata, przed
którą chroni przyrostowość poniżej.

Narzędzie MUST działać **przyrostowo**, nie deklaratywnie: niesie rysunki do dołożenia,
identyfikatory do skasowania oraz identyfikatory do zgaszenia i zapalenia, nigdy
„komplet, który ma zostać". Odwrotnie niż polecenie wykresu (`agent-chart-control`,
„Narzędzie ustawia zawartość aktywnego slotu") — bo tam pominięcie kosztuje jedną świecę
wskaźnika, a tutaj kosztowałoby wsparcia, które operator zbierał tygodniami, skasowane
przez przeoczenie modelu.

Jedno wywołanie MUST zostać wykonane w całości albo wcale: wywołanie stawiające trzy
rysunki, z których jeden jest nie do przyjęcia, MUST NOT postawić żadnego. Ta sama reguła
MUST obejmować gaszenie i zapalanie.

Wywołanie, które każe jeden identyfikator zgasić i zapalić naraz, MUST zostać odrzucone
z nazwaniem tego identyfikatora — dwa sprzeczne polecenia o jednym rysunku nie mają
rozstrzygnięcia, które model mógłby przewidzieć.

#### Scenario: Agent stawia wsparcie i opór

- **WHEN** operator prosi o naniesienie wsparcia i oporu, a agent woła narzędzie z dwoma poziomami
- **THEN** oba pojawiają się na wykresie tego instrumentu

#### Scenario: Agent kasuje rysunek, który sam postawił

- **WHEN** agent woła narzędzie z identyfikatorem rysunku do skasowania
- **THEN** rysunek znika z wykresu

#### Scenario: Agent gasi rysunek zamiast go kasować

- **WHEN** operator prosi o schowanie poziomu, a agent woła narzędzie z jego identyfikatorem do zgaszenia
- **THEN** poziom znika z wykresu
- **AND** nadal daje się odczytać jako zgaszony

#### Scenario: Agent zapala z powrotem

- **WHEN** agent woła narzędzie z identyfikatorem zgaszonego rysunku do zapalenia
- **THEN** rysunek jest znowu na wykresie

#### Scenario: Zgaszenie i zapalenie jednego rysunku naraz

- **WHEN** agent woła narzędzie, podając ten sam identyfikator do zgaszenia i do zapalenia
- **THEN** nic się nie zmienia
- **AND** agent dostaje odmowę nazywającą ten identyfikator

#### Scenario: Wywołanie z jednym rysunkiem nie do przyjęcia

- **WHEN** agent woła narzędzie z trzema poziomami, z których jeden ma kolor spoza palety
- **THEN** nie powstaje żaden z nich
- **AND** agent dostaje odmowę nazywającą ten kolor

#### Scenario: Gaszenie identyfikatora, którego nie ma

- **WHEN** agent woła narzędzie każąc zgasić dwa rysunki, z których jeden nie istnieje na tym instrumencie
- **THEN** żaden z nich nie zostaje zgaszony
- **AND** agent dostaje odmowę nazywającą ten identyfikator

#### Scenario: Agent nie kasuje przez pominięcie

- **WHEN** agent woła narzędzie stawiające jeden poziom na instrumencie, który ma już trzy inne
- **THEN** na instrumencie są cztery poziomy

#### Scenario: Agent nie gasi przez pominięcie

- **WHEN** agent woła narzędzie gaszące jeden poziom na instrumencie, który ma już trzy inne zapalone
- **THEN** pozostałe trzy są nadal zapalone

### Requirement: Agent odczytuje rysunki narzędziem

Moduł MUST publikować modelowi narzędzie odczytujące rysunki wskazanego instrumentu wraz
z ich identyfikatorami, kształtami, cenami, etykietami, chwilą powstania oraz tym, czy są
zgaszone.

Odczyt MUST mówić o zgaszonych tak samo jak o zapalonych, i MUST odróżniać jedne od
drugich. Odczyt, który je pomija, każe modelowi gasić zgaszone i nie pozwala odpowiedzieć,
co na instrumencie w ogóle stoi; odczyt, który ich nie odróżnia, każe mu opowiadać
operatorowi o liniach, których operator nie widzi.

Odczyt MUST być możliwy dla instrumentu, którego terminal akurat nie pokazuje: pytanie
„co mamy naniesione na złocie" MUST NOT wymagać, żeby złoto było na ekranie.

Odczyt MUST NOT niczego zmieniać — dwa odczyty pod rząd MUST dać ten sam wynik.

Identyfikator z odczytu MUST być tym samym identyfikatorem, którym narzędzie kasujące
i gaszące wskazuje rysunek. Model, który odczytał, MUST móc skasować i zgasić bez
zgadywania.

#### Scenario: Pytanie o naniesione poziomy

- **WHEN** operator pyta, co jest naniesione na instrumencie
- **THEN** model odczytuje rysunki i wymienia je z cenami i etykietami

#### Scenario: Odczyt mówi, który rysunek jest zgaszony

- **WHEN** model odczytuje rysunki instrumentu, na którym część jest zgaszona
- **THEN** dostaje wszystkie
- **AND** widzi przy każdym, czy jest zgaszony

#### Scenario: Odczyt instrumentu spoza ekranu

- **WHEN** model odczytuje rysunki instrumentu, którego żaden slot nie pokazuje
- **THEN** dostaje je tak samo jak dla instrumentu widocznego

#### Scenario: Odczyt, potem skasowanie

- **WHEN** model odczytuje rysunki, a następnie kasuje jeden z odczytanych identyfikatorów
- **THEN** ten rysunek znika, a pozostałe zostają

#### Scenario: Odczyt, potem zgaszenie

- **WHEN** model odczytuje rysunki, a następnie gasi jeden z odczytanych identyfikatorów
- **THEN** ten rysunek jest zgaszony, a pozostałe zostają takie, jakie były
