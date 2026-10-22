## MODIFIED Requirements

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
