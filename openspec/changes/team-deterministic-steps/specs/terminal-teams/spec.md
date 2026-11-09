## ADDED Requirements

### Requirement: Krok widać na obrazie zespołu i składa się go w tym samym widoku

Terminal MUST pokazywać kroki zespołu na tym samym obrazie co agentów, z zależnościami prowadzącymi do i od nich.
Krok MUST być odróżnialny od agenta i MUST pokazywać nazwę swojego przepisu.

W widoku zespołu terminal MUST pozwalać:
- dodać krok, z wyborem przepisu z katalogu ogłaszanego przez moduł, a nie z własnej listy;
- edytować parametry kroku;
- usunąć krok;
- prowadzić zależności do kroku i od niego.

Nadpisanie rozmiaru w kroku MUST być widoczne przy kroku bez otwierania jego panelu. Puste pole rozmiaru MUST być
opisane jako „z dokumentu strategii”.

Terminal MUST pozwalać ustawić i usunąć powiadomienie zapasowe agenta. Odmowę zapisu nazywającą krok MUST pokazać
przy tym kroku.

#### Scenario: Otwarcie zespołu z krokiem

- **WHEN** operator otwiera zespół z krokiem `strategy_execute` i agentem reporterem
- **THEN** widzi krok i agenta połączonych zależnością
- **AND** przy kroku nazwę przepisu i nadpisany rozmiar, jeśli krok go niesie

#### Scenario: Zespół bez kroków

- **WHEN** operator otwiera zespół zapisany przed wprowadzeniem kroków
- **THEN** obraz i edytor wyglądają jak przed zmianą

### Requirement: Przebieg pokazuje stan i wynik kroku

W trakcie przebiegu terminal MUST pokazywać przy kroku, czy czeka, pracuje, czy skończył. Po zakończeniu MUST
pokazywać decyzję, streszczenie i pełny wynik kroku, jego wywołania narzędzi i zlecenia przy nim złożone, tak jak przy
agencie. Powiadomienie zapasowe wysłane w przebiegu MUST być widoczne przy agencie, w którego zastępstwie poszło.

#### Scenario: Krok złożył zlecenie

- **WHEN** krok w trwającym przebiegu składa zlecenie
- **THEN** przy kroku pojawia się zlecenie z symbolem, kierunkiem, wielkością i skutkiem
- **AND** po zakończeniu kroku widać jego decyzję i streszczenie
