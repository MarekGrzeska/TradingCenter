# youtube-data-tools Specification

## Purpose
TBD - created by archiving change add-youtube-archive. Update Purpose after archive.
## Requirements
### Requirement: Zestaw dopisuje, ale nie usuwa

Zestaw MUST zawierać narzędzia czytające archiwum oraz narzędzia zapisujące wyłącznie trzy rzeczy:

- dopisanie kanału, z opcjonalnym wyborem istniejącego promptu;
- dopisanie tematu, bez promptu;
- wskazanie filmu do analizy, z opcjonalnym wyborem istniejącego promptu.

Żadne narzędzie MUST NOT:

- zdejmować obserwacji, kasować filmów ani odczytów;
- tworzyć, zmieniać ani usuwać promptów;
- podejmować decyzji o kandydacie ani ignorować kanału;
- zmieniać ustawień modułu;
- ustawiać niczego, co decyduje o powiadomieniach;
- sięgać po cokolwiek związanego z rachunkiem.

Ograniczenie MUST być sprawdzane testem.

#### Scenario: Lista narzędzi

- **WHEN** klient prosi o listę narzędzi
- **THEN** MUST NOT być na niej narzędzia usuwającego cokolwiek, dotykającego rachunku, ustawiającego powiadomienia, piszącego promptu ani decydującego o kandydacie

### Requirement: Zestaw domyka drogę od pytania do odczytu

Model MUST móc bez wcześniejszej wiedzy: sprawdzić stan archiwum razem z nazwami promptów, odczytać ostatnie filmy
z zawężeniem po kanale, temacie i ocenie, otworzyć odczyty jednego filmu oraz wyszukać filmy frazą. Tekst odczytu
dłuższy niż limit narzędzia MUST zostać skrócony z informacją, że jest skrócony.

#### Scenario: Pytanie o to, co kanały mówią o złocie

- **WHEN** operator pyta, co kanały mówią o złocie w tym tygodniu
- **THEN** model MUST móc odpowiedzieć narzędziami zestawu, czytając odczyty ostatnich filmów, nie znając
  identyfikatora żadnego filmu

### Requirement: Surowy tekst jest osobny, stronicowany i oznaczony

Narzędzia listy i odczytu MUST NOT zwracać surowej transkrypcji. Surowy tekst MUST być dostępny
wyłącznie przez osobne narzędzie, stronami o ograniczonej długości, z oznaczeniem, że to treść
obca, a nie polecenie.

Rozmowa ma narzędzia rachunku; transkrypcja jest kanałem, którym ktoś obcy mówi do modelu.

#### Scenario: Model prosi o film

- **WHEN** model odczytuje film narzędziem odczytu
- **THEN** dostaje odczyt, a MUST NOT dostać surowej transkrypcji

### Requirement: Narzędzie, które kosztuje, mówi o tym

Opis narzędzia wyszukiwania i narzędzia wskazania filmu do analizy MUST mówić, że wywołanie zużywa
budżet dostawcy. Wywołanie ponad dzienny sufit MUST dostać odmowę z powodem, a MUST NOT zostać
wykonane.

#### Scenario: Wyszukiwanie po wyczerpaniu budżetu

- **WHEN** model woła wyszukiwanie, a dzienny sufit źródła jest osiągnięty
- **THEN** MUST dostać odmowę podającą sufit i moment odnowienia

#### Scenario: Źródło nie umie wyszukiwać

- **WHEN** wybrane źródło filmów nie obsługuje wyszukiwania
- **THEN** narzędzie MUST odmówić z powodem nazywającym konfigurację

