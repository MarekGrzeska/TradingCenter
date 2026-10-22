## MODIFIED Requirements

### Requirement: Symulacja odtwarza zachowania prawdziwych dostawców

Moduł MUST mieć symulowane źródło filmów, symulowanego dostawcę transkrypcji i symulowany model,
wybierane tym samym ustawieniem co prawdziwe. Ich zachowanie MUST wynikać ze scenariusza, który MUST
umieć opisać co najmniej: filmy pojawiające się w czasie od startu, to, co w filmie jest powiedziane
(także nic), odmowę dostawcy z zadanym odsetkiem, opóźnienie odpowiedzi, koszt każdego wywołania w
jednostce dostawcy (sekundy filmu, w tym brak tekstu, który też kosztuje), wyczerpanie dziennego
limitu, wyszukiwanie po frazie oraz model zwracający odpowiedź niezgodną ze schematem.

#### Scenario: Film, w którym nic nie powiedziano

- **WHEN** film w scenariuszu nie ma mowy
- **THEN** dostawca transkrypcji MUST odpowiedzieć brakiem tekstu, a jego zużycie MUST wynieść długość filmu w sekundach

#### Scenario: Odmowa w co drugim zapytaniu

- **WHEN** scenariusz ustawia odmowę z odsetkiem 50%
- **THEN** dostawca MUST odmawiać w przybliżeniu co drugim zapytaniem, powtarzalnie dla tego samego ziarna losowania

#### Scenario: Wyszukiwanie tematu

- **WHEN** temat wyszukuje frazę, a scenariusz ma pasujące filmy
- **THEN** źródło MUST je zwrócić i MUST policzyć koszt wyszukiwania w jednostkach źródła
