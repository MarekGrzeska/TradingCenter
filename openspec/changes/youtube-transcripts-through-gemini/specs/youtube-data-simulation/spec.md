## MODIFIED Requirements

### Requirement: Symulacja odtwarza zachowania prawdziwych dostawców

Moduł MUST mieć symulowane źródło filmów, symulowanego dostawcę napisów, symulowanego dostawcę
słuchającego i symulowany model, wybierane tym samym ustawieniem co prawdziwe. Ich zachowanie MUST
wynikać ze scenariusza, który MUST umieć opisać co najmniej: filmy pojawiające się w czasie od
startu, napisy dostępne od razu, po zadanym czasie albo nigdy, to, co film mówi (dla dostawcy
słuchającego), blokadę dostawcy (stałą albo z zadanym odsetkiem), opóźnienie odpowiedzi, koszt
każdego wywołania w jednostce dostawcy (w tym płatny brak napisów i sekundy filmu), wyczerpanie
dziennego limitu, wyszukiwanie po frazie oraz model zwracający odpowiedź niezgodną ze schematem.

#### Scenario: Napisy po dwóch godzinach

- **WHEN** scenariusz mówi, że napisy filmu pojawiają się dwie godziny po publikacji
- **THEN** próby przed tym momentem MUST kończyć się brakiem napisów, a pierwsza po nim — tekstem

#### Scenario: Film bez napisów słuchany przez symulację

- **WHEN** film w scenariuszu nie ma napisów, ale ma zapisaną mowę, a łańcuch kończy się symulowanym dostawcą słuchającym
- **THEN** transkrypcja MUST przyjść od dostawcy słuchającego, a jego zużycie MUST wynieść długość filmu w sekundach

#### Scenario: Blokada w co dziesiątym zapytaniu

- **WHEN** scenariusz ustawia blokadę z odsetkiem 10%
- **THEN** dostawca MUST odpowiadać blokadą w przybliżeniu co dziesiątym zapytaniem, powtarzalnie
  dla tego samego ziarna losowania

#### Scenario: Wyszukiwanie tematu

- **WHEN** temat wyszukuje frazę, a scenariusz ma pasujące filmy
- **THEN** źródło MUST je zwrócić i MUST policzyć koszt wyszukiwania w jednostkach źródła
