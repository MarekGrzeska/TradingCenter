## ADDED Requirements

### Requirement: Zwinięty wiersz identyfikuje obserwację i nie udaje odczytu

Wydarzenie zwinięte MUST nieść to, po czym operator je rozpozna i czym może w nim ruszyć: tytuł,
grupę, stan zbierania i usunięcie. Zwinięty wiersz MUST NOT pokazywać prawdopodobieństwa żadnego
wyniku — ani liczbą, ani paskiem, ani „liderem" rynku.

Skrót do jednej ceny na rynek jest sprowadzeniem rynku do jednej ceny „za", którego widok
rozwinięty ma zakaz; zwinięcie nie jest wyjątkiem od tej reguły, tylko miejscem, w którym łatwo
ją obejść. Odczyt jest po rozwinięciu, gdzie każdy rynek niesie wszystkie swoje wyniki.

**Stan zbierania zostaje**, mimo że nie jest ani tytułem, ani grupą: obecność na liście nie
dowodzi, że ceny przychodzą, i zwinięty wiersz jest jedynym miejscem, w którym operator dowie się
o zatrzymanym zbieraniu, zanim cokolwiek rozwinie.

#### Scenario: Wydarzenie zwinięte

- **WHEN** operator ogląda listę obserwacji bez rozwijania żadnej
- **THEN** każdy wiersz niesie tytuł, grupę, stan zbierania i sposób usunięcia
- **AND** MUST NOT nieść prawdopodobieństwa żadnego wyniku

#### Scenario: Rozwinięcie wydarzenia

- **WHEN** operator rozwija wydarzenie
- **THEN** widok pokazuje jego rynki wraz ze wszystkimi wynikami i ich prawdopodobieństwami

## MODIFIED Requirements

### Requirement: Kasowanie zebranej historii jest tutaj i wymaga potwierdzenia

Terminal MUST udostępniać operatorowi usunięcie obserwacji wraz z całą zebraną historią, i MUST
być jedynym miejscem, w którym da się to zrobić. Czynność MUST wymagać potwierdzenia nazywającego,
czego dotyczy i że jest nieodwracalna.

Nieodwracalność jest tu inna niż przy archiwum świec i MUST być powiedziana wprost: dostawca nie
oddaje historii rynku, który się rozstrzygnął, a dla pozostałych sięga tylko tak daleko, jak sięga.
Usunięte dane w większości przypadków nie dadzą się zebrać ponownie żadnym kosztem.

Zakres MUST być nazwany jako całość, a nie jako jedna z dwóch rzeczy do wyboru: zatrzymania
zbierania bez usunięcia nie ma, więc potwierdzenie MUST NOT sugerować, że obserwacja przetrwa
czynność albo że historia przetrwa usunięcie obserwacji.

#### Scenario: Usunięcie zebranej historii

- **WHEN** operator potwierdza usunięcie
- **THEN** wydarzenie znika z listy obserwacji wraz z całą swoją historią

#### Scenario: Potwierdzenie mówi, co się stanie

- **WHEN** operator sięga po usunięcie
- **THEN** widok MUST zażądać potwierdzenia
- **AND** potwierdzenie MUST nazwać zakres usunięcia — wydarzenie i wszystko, co dla niego
  zebrano — oraz jego nieodwracalność

#### Scenario: Odstąpienie od usunięcia

- **WHEN** operator nie potwierdza usunięcia
- **THEN** nic nie zostaje usunięte

## REMOVED Requirements

### Requirement: Zakończenie obserwacji nie rusza danych i mówi o tym

**Reason**: zakładka przestaje oferować zatrzymanie obserwacji, bo moduł przestaje je udostępniać.
Wymaganie istniało po to, żeby przycisk zatrzymujący zbieranie nie czytał się jak przycisk
kasujący dane — a najpewniejszym sposobem, żeby się tak nie czytał, okazało się nie mieć go wcale.
Zostaje jedna czynność i jedno potwierdzenie, które nazywa całość.

**Migration**: nic po stronie operatora. Wydarzenia zatrzymane wcześniej znikają z listy razem
z historią przy migracji modułu; wydarzenie, którego operator nie chce zbierać, usuwa się jednym
przyciskiem, który tam już jest.
