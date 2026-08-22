# polymarket-data-tracking Specification

## Purpose
Rozstrzyga, co moduł w ogóle zbiera: które wydarzenie predykcyjne jest obserwowane, kto o tym
decyduje, jak obserwacje są grupowane i co zostaje po zakończeniu obserwacji.
## Requirements
### Requirement: Obserwacja jest jawną decyzją

Moduł MUST zbierać ceny wyłącznie dla wydarzeń jawnie wskazanych do obserwacji — przez operatora
kontraktem REST albo przez model narzędziem. MUST NOT zaczynać obserwacji jako skutku ubocznego
przeszukania publicznej bazy dostawcy, odczytu archiwum ani wyświetlenia czegokolwiek. Zbieranie
kosztuje ruch do dostawcy utrzymywany bez przerwy, więc MUST być skutkiem decyzji, a nie oglądania.

Wydarzenie MUST dać się wskazać zarówno adresem strony dostawcy, jak i samym identyfikatorem
wydarzenia w jego bazie. Operator kopiuje adres z przeglądarki, model ma identyfikator
z przeszukania — obie drogi prowadzą do tej samej obserwacji, a nie do dwóch.

Lista obserwacji MUST być trwała i MUST przeżyć restart modułu.

#### Scenario: Przeszukanie publicznej bazy

- **WHEN** ktokolwiek przeszukuje publiczną bazę dostawcy przez ten moduł
- **THEN** żadne z odnalezionych wydarzeń nie zostaje objęte obserwacją
- **AND** odpowiedź stwierdza, dla których wyników obserwacja już trwa

#### Scenario: Wskazanie adresem i identyfikatorem

- **WHEN** to samo wydarzenie zostaje wskazane raz adresem strony dostawcy, a raz jego
  identyfikatorem
- **THEN** powstaje jedna obserwacja, nie dwie

#### Scenario: Restart modułu

- **WHEN** moduł zostaje zatrzymany i uruchomiony ponownie
- **THEN** obserwuje dokładnie te wydarzenia, które obserwował przed zatrzymaniem
- **AND** nie wymaga ponownego wskazania ich przez nikogo

### Requirement: Obserwacja obejmuje wydarzenie wraz z jego rynkami i wynikami

Wydarzenie u dostawcy jest zbiorem rynków, a rynek zbiorem wyników — i to wynik, nie rynek, ma
cenę. Moduł MUST zapisywać przy obserwacji całą tę strukturę: wydarzenie, jego rynki i wyniki
każdego rynku wraz z identyfikatorami, po których cena jest u dostawcy odpytywana. MUST NOT
zakładać, że rynek ma dokładnie dwa wyniki — rynek dwuwynikowy jest szczególnym przypadkiem,
a nie kształtem, do którego pozostałe się przycina.

Struktura MUST być odświeżalna: dostawca MAY dołożyć rynek do trwającego wydarzenia albo
rozstrzygnąć pojedynczy rynek, a moduł MUST to odnotować bez wskazywania wydarzenia od nowa.

#### Scenario: Wydarzenie wielorynkowe

- **WHEN** obserwacją zostaje objęte wydarzenie o kilku rynkach, z których część ma więcej niż
  dwa wyniki
- **THEN** zapisane zostają wszystkie rynki i wszystkie ich wyniki
- **AND** żaden rynek MUST NOT zostać pominięty z powodu liczby wyników

#### Scenario: Dostawca dokłada rynek do wydarzenia

- **WHEN** u dostawcy przybywa rynek w obserwowanym wydarzeniu
- **THEN** moduł dopisuje go do struktury tego wydarzenia
- **AND** zaczyna zbierać jego ceny bez wskazywania wydarzenia od nowa

### Requirement: Obserwacje dają się grupować

Operator MUST móc tworzyć grupy obserwacji i przypisywać do nich wydarzenia. Grupa jest kategorią
lokalną tego modułu i MUST NOT być mylona z tagiem dostawcy: tag opisuje publiczną bazę i służy
do jej przeglądania, grupa opisuje to, co obserwujemy, i służy do odczytu.

Wydarzenie MAY nie należeć do żadnej grupy. Skasowanie grupy MUST NOT kasować obserwacji ani ich
historii — wydarzenia z tej grupy zostają obserwowane bez grupy.

#### Scenario: Odczyt zawężony do grupy

- **WHEN** ktokolwiek odczytuje obserwacje jednej grupy
- **THEN** dostaje wyłącznie wydarzenia do niej przypisane

#### Scenario: Skasowanie grupy

- **WHEN** grupa zostaje skasowana
- **THEN** wydarzenia do niej przypisane są nadal obserwowane
- **AND** ani jedna próbka ceny nie zostaje usunięta

### Requirement: Liczba obserwowanych wydarzeń ma znany sufit

Każde obserwowane wydarzenie to stały ruch do dostawcy w takcie próbkowania, a rozpoczęcie
obserwacji jest zdolnością modelu. Moduł MUST odmówić objęcia obserwacją wydarzenia ponad
skonfigurowany sufit i MUST nazwać powód wprost, wskazując, że najpierw trzeba zakończyć inną
obserwację. Odmowa MUST NOT być cichym przycięciem taktu ani cichym pominięciem części rynków.

Sufit MUST obowiązywać niezależnie od tego, którą powierzchnią przyszła decyzja — narzędzie
i kontrakt REST podlegają temu samemu limitowi.

#### Scenario: Sufit osiągnięty

- **WHEN** ktokolwiek wskazuje wydarzenie do obserwacji, gdy sufit został osiągnięty
- **THEN** moduł odmawia, stwierdzając, że sufit został osiągnięty
- **AND** dotychczasowe obserwacje działają dalej bez zmian

#### Scenario: Sufit obowiązuje obie powierzchnie

- **WHEN** sufit zostaje osiągnięty decyzjami złożonymi przez kontrakt REST, a kolejne wydarzenie
  wskazuje narzędzie
- **THEN** moduł odmawia tak samo

### Requirement: Zakończenie obserwacji zatrzymuje zbieranie i nie rusza danych

Zakończenie obserwacji MUST zatrzymać próbkowanie wydarzenia i zwolnić związany z nim ruch do
dostawcy. MUST NOT usunąć ani jednej zebranej próbki: zebrana historia rozstrzygniętego albo
porzuconego rynku jest materiałem, na którym da się coś sprawdzić, a jej wartość nie kończy się
wraz z zainteresowaniem.

Ponowne objęcie obserwacją tego samego wydarzenia MUST podjąć zbieranie i MUST zachować historię
zebraną wcześniej, uzupełniając przerwę, a nie zaczynając od pustego miejsca.

#### Scenario: Zakończenie obserwacji

- **WHEN** obserwacja wydarzenia zostaje zakończona
- **THEN** moduł przestaje próbkować jego rynki
- **AND** zebrana historia pozostaje odczytywalna

#### Scenario: Ponowne objęcie obserwacją

- **WHEN** wydarzenie, którego obserwację zakończono, zostaje objęte obserwacją ponownie
- **THEN** wcześniejsza historia jest nadal odczytywalna
- **AND** moduł uzupełnia przerwę, zamiast zaczynać serię od nowa

### Requirement: Rozstrzygnięty rynek przestaje być próbkowany sam

Rynek rozstrzygnięty u dostawcy ma cenę, która się już nie zmieni. Moduł MUST przestać go
próbkować, gdy tylko dostawca ogłosi rozstrzygnięcie, i MUST zapisać, że rynek jest
rozstrzygnięty oraz z jakim wynikiem. Rozstrzygnięcie MUST NOT być mylone z zakończeniem
obserwacji: to pierwsze robi dostawca, to drugie człowiek albo model.

#### Scenario: Rynek zostaje rozstrzygnięty

- **WHEN** dostawca ogłasza rozstrzygnięcie obserwowanego rynku
- **THEN** moduł przestaje go próbkować
- **AND** zapisuje stan rozstrzygnięcia wraz z wynikiem, który wygrał
- **AND** historia tego rynku pozostaje odczytywalna

#### Scenario: Wydarzenie rozstrzygnięte w całości

- **WHEN** wszystkie rynki obserwowanego wydarzenia są rozstrzygnięte
- **THEN** wydarzenie pozostaje na liście obserwacji, oznaczone jako rozstrzygnięte
- **AND** MUST NOT zniknąć z niej samoczynnie

### Requirement: Obserwacje są wyliczalne wraz ze swoim stanem

Sama obecność wydarzenia na liście nie dowodzi, że ceny przychodzą. Odczyt listy obserwacji MUST
dla każdego wydarzenia nieść: jego rynki i wyniki, grupę, stan (obserwowany albo rozstrzygnięty),
moment ostatniej zebranej próbki oraz to, dokąd wstecz sięga zebrana historia.

Obserwacja, dla której najświeższa próbka jest starsza niż kilka taktów próbkowania, MUST być
oznaczona jako taka, w której zbieranie nie nadąża albo ustało — cisza w danych MUST NOT wyglądać
tak samo jak cisza na rynku.

#### Scenario: Odczyt listy obserwacji

- **WHEN** ktokolwiek odczytuje listę obserwacji
- **THEN** dla każdego wydarzenia dostaje jego rynki i wyniki, grupę, stan, moment ostatniej
  próbki i najstarszy moment zebranej historii

#### Scenario: Zbieranie ustało po cichu

- **WHEN** dla obserwowanego, nierozstrzygniętego rynku najświeższa próbka jest starsza niż kilka
  taktów próbkowania
- **THEN** stan tej obserwacji stwierdza, że zbieranie nie nadąża albo ustało

