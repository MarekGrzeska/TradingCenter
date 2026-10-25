## MODIFIED Requirements

### Requirement: Uruchomienie z formularza i profil kosztów

Formularz uruchomienia MUST przyjmować zakres w dniach strefy polskiej, parametry z wartościami domyślnymi i
zadeklarowanymi zakresami, model kosztów, kapitał i ziarno. Model kosztów MUST być wypełniony z profilu kosztów
instrumentu. Zmiana w formularzu MUST dotyczyć tylko tego uruchomienia, a profil zmienia się osobno. Przed wysłaniem
formularz MUST pokazywać, ile świec serii wykonania rewizji obejmie zakres, z nazwą tej serii, wobec sufitu pakietu.
Instrument bez profilu MUST dawać formularz z pustymi kosztami i możliwością zapisania ich jako profil. Odmowa pakietu
MUST pojawić się przy polu, którego dotyczy.

#### Scenario: Zakres ponad sufit

- **WHEN** operator wybiera zakres, który obejmuje więcej świec serii wykonania, niż pakiet przyjmuje
- **THEN** formularz MUST to powiedzieć przed wysłaniem i nazwać sufit

#### Scenario: Instrument bez profilu kosztów

- **WHEN** operator otwiera formularz dla instrumentu bez profilu
- **THEN** koszty MUST być puste, a formularz MUST pozwalać zapisać wpisane koszty jako profil instrumentu

#### Scenario: Długi zakres strategii na M5

- **WHEN** operator wybiera dziesięć lat dla rewizji z serią wykonania `MINUTE_5`
- **THEN** formularz MUST liczyć świece M5, a nie minuty, i MUST NOT blokować wysłania z powodu sufitu
