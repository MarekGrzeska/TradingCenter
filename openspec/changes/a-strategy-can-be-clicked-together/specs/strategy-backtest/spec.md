## MODIFIED Requirements

### Requirement: Wynik nazywa swoje koszty i swoje parametry

Raport backtestu MUST nazywać model kosztów (spread, prowizję, poślizg), wersję zestawu
parametrów strategii, rewizję reguły — gdy przebieg liczył wpis pochodzący z bazy — oraz
zakres danych, na którym powstał. Wynik bez modelu kosztów MUST NOT być prezentowany jako
wynik strategii. Powtórzenie backtestu z tych samych składników MUST dawać ten sam raport.

Archiwum trzyma stronę bid — koszt transakcyjny jest w danych niewidoczny, a strategia
o wysokim stosunku zysku do ryzyka potrafi stracić całą przewagę na spreadzie. Raport,
który nie mówi, co założył, mówi tylko tyle, że ktoś go wygenerował. Rewizja dochodzi do tej
listy z tej samej racji: dwa przebiegi tej samej definicji sprzed i po zmianie reguły są
z zewnątrz nierozróżnialne, a różnią się dokładnie tym, co się badało.

#### Scenario: Raport z przebiegu

- **WHEN** backtest kończy przebieg
- **THEN** raport niesie model kosztów, wersję parametrów i zakres danych
- **AND** ponowny przebieg z tych samych składników daje ten sam raport

#### Scenario: Przebieg nad rewizją z bazy

- **WHEN** backtest liczy wyklikaną strategię
- **THEN** przebieg wykonuje się nad wskazaną rewizją definicji, a nie nad jej bieżącym brzmieniem
- **AND** raport nazywa tę rewizję obok kosztów, parametrów i zakresu

### Requirement: Strategie porównuje się na tych samych danych i kosztach

Porównanie strategii MUST zestawiać przebiegi wykonane na tym samym zakresie danych i tym
samym modelu kosztów; raport porównawczy MUST odmówić zestawienia przebiegów, których
składniki się różnią, nazywając różnicę. Różna rewizja reguły MUST NOT być powodem odmowy —
zestawienie dwóch rewizji jednej definicji jest zamierzonym użyciem — ale każdy zestawiony
przebieg MUST nazywać swoją rewizję.

Po to istnieje strategia odniesienia: „strategia działa" nie znaczy nic, dopóki nie znaczy
„bije prosty punkt odniesienia o tyle, po kosztach". Porównanie na różnych danych to
porównanie pogody w dwóch miastach. Rewizja jest odwrotnym przypadkiem: to jedyna rzecz,
którą przy porównaniu chce się zmieniać świadomie, więc odmowa byłaby zakazem zadania
pytania, dla którego ta komenda powstała.

#### Scenario: Zestawienie dwóch strategii

- **WHEN** operator zestawia przebiegi dwóch strategii na tym samym zakresie i modelu kosztów
- **THEN** raport porównawczy staje obok siebie na wspólnych metrykach

#### Scenario: Zestawienie przebiegów o różnych składnikach

- **WHEN** operator zestawia przebiegi wykonane na różnych zakresach lub kosztach
- **THEN** zestawienie zostaje odrzucone z powodem nazywającym różnicę

#### Scenario: Zestawienie dwóch rewizji jednej definicji

- **WHEN** operator zestawia przebiegi dwóch rewizji tej samej definicji na tym samym
  zakresie i modelu kosztów
- **THEN** zestawienie dochodzi do skutku
- **AND** każdy przebieg jest w nim rozpoznawalny po swojej rewizji
