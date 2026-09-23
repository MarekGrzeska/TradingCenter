## ADDED Requirements

### Requirement: Próbki starsze niż trzydzieści dni są zagęszczane do jednej na godzinę

Archiwum MUST zagęszczać próbki wyniku starsze niż 30 dni do jednej na godzinę: z każdej godziny zostaje
ostatnia próbka z jej własnym momentem i wartością, a pozostałe są usuwane. Zachowana próbka MUST nieść
znacznik zagęszczenia, a odczyt historii MUST mówić, od którego momentu takt jest godzinowy.

Zagęszczenie MUST NOT zmieniać zakresu, który archiwum ogłasza jako zebrany, i MUST przebiegać porcjami,
pod tym samym budżetem połączeń co próbkowanie.

#### Scenario: Wykres rynku sprzed dwóch miesięcy

- **WHEN** konsument odczytuje historię wyniku sprzed dwóch miesięcy
- **THEN** dostaje jedną próbkę na godzinę dla okresu starszego niż 30 dni
- **AND** odczyt mówi, od którego momentu takt jest godzinowy

#### Scenario: Pytanie o minutę w okresie zagęszczonym

- **WHEN** konsument pyta o cenę w minucie okresu zagęszczonego, dla której nie ma próbki
- **THEN** archiwum MUST NOT odpowiedzieć, że w tej minucie nie było notowania
- **AND** okres pozostaje ogłoszony jako zebrany

#### Scenario: Świeże próbki

- **WHEN** próbka ma mniej niż 30 dni
- **THEN** zagęszczenie jej nie dotyka
