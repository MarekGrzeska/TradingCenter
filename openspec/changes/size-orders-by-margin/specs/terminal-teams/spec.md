## Purpose

Zakładka, w której operator składa zespół i patrzy, jak pracuje: co widać na obrazie zespołu,
jak edytuje się role i zależności, skąd bierze się lista katalogu i co pokazuje przebieg
w trakcie.

## ADDED Requirements

### Requirement: Wywołanie narzędzia w oknie outputów da się rozwinąć

Okno, w którym operator czyta, co agenci napisali, MUST pozwalać rozwinąć wpis wywołanego
narzędzia i zobaczyć argumenty, którymi je wywołano, oraz treść wyniku albo powód odmowy.
Wpisy MUST być zwinięte, dopóki operator ich nie rozwinie.

To ta sama potrzeba, którą transkrypt czatu zaspokaja od początku: wynik narzędzia jest tym,
z czego wzięła się odpowiedź modelu, a wpis mówiący samo „ok" każe brać ją na słowo. Odczyt
zespołu jest tu trudniejszy niż rozmowy — agentów jest kilku, a wynik jednego bywa całym
wejściem następnego.

Okno MUST powiedzieć wprost, kiedy treści wywołania jeszcze nie ma, i MUST NOT pokazywać jej
braku jako pustej odpowiedzi. Przebieg w trakcie zgłasza wywołania szybciej, niż okno je
doczytuje, a pusty wynik czyta się jak narzędzie, które nic nie zwróciło.

#### Scenario: Operator rozwija wywołanie

- **WHEN** operator rozwija wpis wywołania w oknie outputów
- **THEN** widzi argumenty, którymi narzędzie wywołano, i treść wyniku albo powód odmowy

#### Scenario: Wpisy są zwinięte na wejściu

- **WHEN** operator otwiera okno outputów przebiegu, w którym agenci wywoływali narzędzia
- **THEN** wywołania są wypisane zwinięte
- **AND** żadne z nich nie zajmuje ekranu, dopóki nie zostanie rozwinięte

#### Scenario: Treść wywołania jeszcze nie dotarła

- **WHEN** operator rozwija wywołanie, którego treści okno jeszcze nie odczytało
- **THEN** wpis mówi, że treść nie została jeszcze odczytana
- **AND** MUST NOT pokazywać pustego wyniku ani pustych argumentów

#### Scenario: Wywołanie zakończone odmową

- **WHEN** operator rozwija wpis wywołania oznaczonego jako odmowa
- **THEN** widzi powód odmowy
