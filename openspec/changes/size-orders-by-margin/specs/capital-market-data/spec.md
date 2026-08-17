## ADDED Requirements

### Requirement: Warunki handlowe instrumentu są osobnym odczytem

Moduł MUST publikować warunki, na jakich provider pozwala handlować instrumentem: wymóg
depozytu wraz z jednostką, w jakiej provider go podaje, najmniejszy i największy dopuszczalny
rozmiar zlecenia, krok, o jaki rozmiar wolno zmieniać, wielkość lota oraz walutę rozliczenia.

Odczyt MUST być osobny od wyszukiwania i wyliczania instrumentów. Provider podaje te pola
wyłącznie w opisie pojedynczego instrumentu, a nie w wynikach obchodu katalogu, więc doklejenie
ich do listy oznaczałoby żądanie na każdy jej element.

Moduł MUST podawać jednostkę wymogu depozytu obok jego wartości i MUST NOT przeliczać go na
dźwignię ani na kwotę. Konsument, który dostał samą liczbę bez jednostki, nie ma jak odróżnić
procentu od mnożnika, a moduł, który zgadłby za niego, popełniłby ten błąd raz dla wszystkich.

Odczyt MUST NOT nieść ceny. Cena instrumentu jest już w wyszukiwaniu i w świecach; trzecie
miejsce, w którym się pojawia, to trzecia odpowiedź, która może być z innej chwili.

#### Scenario: Odczyt warunków instrumentu

- **WHEN** konsument prosi o warunki handlowe instrumentu, którym da się handlować
- **THEN** dostaje wymóg depozytu z jednostką, najmniejszy i największy rozmiar zlecenia, krok
  rozmiaru, wielkość lota i walutę rozliczenia

#### Scenario: Warunki instrumentu spoza providera

- **WHEN** konsument prosi o warunki instrumentu, którego provider nie zna
- **THEN** moduł odmawia, nazywając symbol

#### Scenario: Provider nie podaje któregoś z warunków

- **WHEN** provider pomija któreś z pól opisujących warunki
- **THEN** moduł zwraca je jako nieznane
- **AND** MUST NOT podstawiać w to miejsce wartości domyślnej
