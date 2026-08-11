# market-data-monitoring Specification

## Purpose

Co moduł mówi o własnym zbieraniu na zewnątrz procesu — do systemu monitoringu, nie do API.
Chodzi o jedną rzecz: żeby operator dowiedział się, że para przestała być uzupełniana, zanim
zauważy to po nieruchomym wykresie, i żeby próg tego powiadomienia dało się ustawić raz dla
wszystkich rozdzielczości.

## Requirements

### Requirement: Spóźnienie zbierania jest raportowane w jednostce niezależnej od rozdzielczości

Wiek najnowszej świecy w sekundach nie daje się porównywać między rozdzielczościami: świeca
`DAY` starsza o dwadzieścia godzin jest zdrowa, a świeca `MINUTE` starsza o dwadzieścia minut
nie jest. Moduł MUST raportować spóźnienie zbierania także w **okresach** danej rozdzielczości,
tak by ta sama liczba znaczyła to samo dla każdej śledzonej pary.

Wartość MUST być liczona po odjęciu czasu, jakiego świeca potrzebuje na dotarcie po zamknięciu
okresu — ten sam zapas, którym moduł posługuje się, orzekając stan pary — i MUST NOT być
ujemna.

#### Scenario: Zdrowa para na najkrótszej i najdłuższej rozdzielczości

- **WHEN** para `MINUTE` i para `WEEK` są zbierane normalnie, każda ze świecą sprzed
  niespełna jednego okresu
- **THEN** obie raportują spóźnienie mniejsze niż jeden okres
- **AND** żadna z nich nie przekracza progu, który przekracza para faktycznie zatrzymana

#### Scenario: Para przestała być uzupełniana

- **WHEN** najnowsza świeca pary jest starsza o wielokrotność okresu tej pary
- **THEN** raportowane spóźnienie rośnie proporcjonalnie do liczby pominiętych okresów
- **AND** jest tej samej wielkości co dla pary o innej rozdzielczości pominiętej tyle samo razy

#### Scenario: Świeca dopiero co zamknięta, jeszcze nieodebrana

- **WHEN** okres zamknął się przed chwilą, a świeca nie zdążyła jeszcze dotrzeć od dostawcy
- **THEN** raportowane spóźnienie wynosi zero, a nie ułamek okresu

#### Scenario: Rynek zamknięty

- **WHEN** gateway podaje, że rynek instrumentu jest zamknięty
- **THEN** para nie jest w ogóle raportowana, tak samo jak w metryce sekundowej

### Requirement: Wiek w sekundach pozostaje dostępny

Liczba okresów jest dobra dla progu i zła dla człowieka czytającego wykres metryki: nie da się
z niej odczytać, o której godzinie zbieranie stanęło. Moduł MUST nadal raportować wiek
najnowszej świecy w sekundach, obok metryki w okresach, dla tych samych par i z tym samym
wykluczeniem zamkniętych rynków.

#### Scenario: Diagnoza po fakcie

- **WHEN** operator ogląda historię metryk po awarii
- **THEN** ma dostępny wiek w sekundach dla każdej pary, z podziałem na symbol i rozdzielczość

### Requirement: Jeden próg wystarcza dla wszystkich śledzonych rozdzielczości

Powiadomienie o zatrzymanym zbieraniu MUST dać się skonfigurować jedną granicą, wspólną dla
wszystkich śledzonych par, i ta granica MUST rozróżniać parę zdrową od zatrzymanej niezależnie
od tego, jakie rozdzielczości są akurat zbierane. Dodanie pary o dowolnej rozdzielczości
MUST NOT wprowadzać powiadomienia w stan trwałego zapalenia.

#### Scenario: Dodanie pary o długim okresie

- **WHEN** operator zaczyna zbierać parę `DAY` obok zbieranych już par minutowych
- **THEN** powiadomienie pozostaje w stanie spoczynku, dopóki żadna z par nie jest zatrzymana

#### Scenario: Zatrzymanie jednej pary spośród wielu

- **WHEN** jedna ze zbieranych par przestaje być uzupełniana przy otwartym rynku
- **THEN** powiadomienie zmienia stan na zapalone
